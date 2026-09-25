"""Single-cycle public market snapshot acquisition."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.exchange.client import BinancePublicClient, PublicMarketDataClient
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import MarketKline
from ai4binance.schemas import (
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
    is_spot_market_type,
)


class LocalMarketPublicClient(BinancePublicClient):
    """Reuse public parsers with the archive's exchange-listed Unicode identities."""

    @staticmethod
    def _symbol(value: str) -> str:
        return ParquetOHLCVArchive._validate_identity(value, "1m", "local_read")


@dataclass(frozen=True, slots=True)
class LocalMarketSnapshotTransport:
    """Serve the existing public client from the collector's shared snapshots."""

    directory: Path
    maximum_age_seconds: float = 900
    ticker_snapshot_filename: str = "ticker-24hr.json"
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if self.ticker_snapshot_filename not in {
            "ticker-24hr.json",
            "wallet-price-coverage.json",
        }:
            raise ValueError("ticker snapshot filename is unsupported")

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        if path == "/api/v3/time":
            return {"serverTime": int(self.clock().timestamp() * 1000)}
        filenames = {
            "/api/v3/exchangeInfo": "exchange-info.json",
            "/api/v3/ticker/price": self.ticker_snapshot_filename,
            "/api/v3/ticker/24hr": self.ticker_snapshot_filename,
            "/api/v3/ticker/bookTicker": "ticker-bookTicker.json",
            "/fapi/v1/exchangeInfo": "exchange-info.json",
            "/fapi/v1/ticker/24hr": "ticker-24hr.json",
            "/fapi/v1/ticker/bookTicker": "ticker-bookTicker.json",
            "/fapi/v1/premiumIndex": "premium-index.json",
        }
        if path not in filenames:
            raise ExchangePayloadError("shared collector owns market-data acquisition")
        try:
            if (self.directory / filenames[path]).stat().st_size > 8_000_000:
                raise ValueError("shared snapshot exceeds its size limit")
            payload = json.loads(
                (self.directory / filenames[path]).read_text(encoding="utf-8")
            )
            observed = datetime.fromisoformat(payload["observed_at"])
            if observed.utcoffset() is None:
                raise ValueError("shared snapshot timestamp is naive")
            age = (self.clock() - observed).total_seconds()
            maximum_age = (
                86400 if path.endswith("exchangeInfo") else self.maximum_age_seconds
            )
            if not 0 <= age <= maximum_age:
                raise ValueError("shared snapshot is stale")
            symbol = str((params or {}).get("symbol", ""))
            rows = (
                payload["payload"]["symbols"]
                if path.endswith("exchangeInfo")
                else payload["rows"]
            )
            if not symbol and not path.endswith("ticker/price"):
                return {"symbols": rows} if path.endswith("exchangeInfo") else rows
            matching = [item for item in rows if item.get("symbol") == symbol]
            if len(matching) != 1:
                raise ValueError("shared snapshot symbol is missing or duplicated")
            item = matching[0]
            if path.endswith("exchangeInfo"):
                return {"symbols": [item]}
            if path.endswith("ticker/price"):
                return {"symbol": symbol, "price": item["lastPrice"]}
            return item
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise ExchangePayloadError(
                "canonical local market snapshot is unavailable"
            ) from error


@dataclass(frozen=True, slots=True)
class DataAcquisitionAgent:
    """Build one immutable shared snapshot from public Spot market data."""

    client: PublicMarketDataClient
    market_type: str = "Spot"
    candle_limit: int = 250
    minimum_closed_candles: int = 200
    max_workers: int = 4
    archive: ParquetOHLCVArchive | None = None
    depth_path: Path | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not is_spot_market_type(self.market_type):
            raise ValueError("public data acquisition supports only Spot market_type")
        if not 2 <= self.candle_limit <= 1000:
            raise ValueError("candle_limit must be between 2 and 1000")
        if not 2 <= self.minimum_closed_candles <= self.candle_limit:
            raise ValueError(
                "minimum_closed_candles must be between 2 and candle_limit"
            )
        if not 1 <= self.max_workers <= 8:
            raise ValueError("max_workers must be between 1 and 8")

    def acquire(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
    ) -> MarketSnapshot:
        """Fetch each public input once and return a cycle-consistent snapshot."""
        if not timeframes or len(set(timeframes)) != len(timeframes):
            raise ValueError("timeframes must be non-empty and unique")
        for timeframe in timeframes:
            timeframe_duration(timeframe)

        server_time = self.client.server_time()
        symbol_info = self.client.exchange_info(symbol)
        SymbolFilters.from_symbol_info(symbol_info)
        latest_price = self.client.ticker_price(symbol_info.symbol)
        book = self.client.book_ticker(symbol_info.symbol)
        raw_klines = self._fetch_klines(symbol_info.symbol, timeframes)
        observed_at = self.clock() if self.depth_path is not None else server_time
        if observed_at.utcoffset() is None or observed_at < server_time:
            raise ValueError("data acquisition clock must follow server time")

        candles_by_timeframe: dict[str, tuple[OHLCVCandle, ...]] = {}
        freshness: dict[str, dict[str, object]] = {}
        last_close_times: dict[str, datetime] = {}
        for timeframe in timeframes:
            closed = tuple(
                kline
                for kline in raw_klines[timeframe]
                if kline.close_time <= server_time
            )
            candles_by_timeframe[timeframe] = tuple(
                kline.to_candle() for kline in closed
            )
            duration = timeframe_duration(timeframe)
            last_close = closed[-1].close_time if closed else None
            age_seconds = (
                max(0.0, (server_time - last_close).total_seconds())
                if last_close is not None
                else None
            )
            stale = (
                last_close is None
                or age_seconds is None
                or age_seconds > (duration.total_seconds() * 2)
            )
            freshness[timeframe] = {
                "last_close": last_close.isoformat() if last_close else None,
                "age_seconds": age_seconds,
                "stale": stale,
                "closed_candle_count": len(closed),
            }
            if last_close is not None:
                last_close_times[timeframe] = last_close

        data_valid = all(
            len(candles_by_timeframe[timeframe]) >= self.minimum_closed_candles
            and not bool(freshness[timeframe]["stale"])
            for timeframe in timeframes
        )
        snapshot_id = self._snapshot_id(
            symbol_info.symbol,
            observed_at,
            latest_price,
            last_close_times,
        )
        return MarketSnapshot(
            snapshot_id=snapshot_id,
            created_at=observed_at,
            exchange="Binance",
            market_type=self.market_type,
            symbol=symbol_info.symbol,
            timeframes=timeframes,
            ohlcv_by_timeframe=candles_by_timeframe,
            latest_price=latest_price,
            bid=book.bid,
            ask=book.ask,
            spread=book.spread,
            order_book_summary={
                "best_bid": str(book.bid),
                "best_ask": str(book.ask),
                "spread": str(book.spread),
                **self._local_depth_summary(symbol_info.symbol, observed_at),
            },
            exchange_filters={
                name: dict(values) for name, values in symbol_info.filters.items()
            },
            server_time=server_time,
            data_freshness=freshness,
            data_quality=(
                DataQuality.DATA_VALID if data_valid else DataQuality.DATA_INVALID
            ),
            market_metadata={
                "trading_status": symbol_info.status,
                "base_asset": symbol_info.base_asset,
                "quote_asset": symbol_info.quote_asset,
                "source": (
                    "CANONICAL_LOCAL_MARKET_ARCHIVE"
                    if self.archive is not None
                    else "BINANCE_PUBLIC_REST"
                ),
                "closed_candles_only": True,
            },
        )

    def _local_depth_summary(
        self, symbol: str, observed_at: datetime
    ) -> dict[str, object]:
        """Reuse sequence-verified local depth without creating another collector."""
        if self.depth_path is None:
            return {}
        from ai4binance.data.market_depth import read_local_depth

        try:
            depth = read_local_depth(self.depth_path, "spot", symbol, now=observed_at)
            event_at = float(str(depth["event_at"]))
            if not 0 <= observed_at.timestamp() - event_at <= 30:
                raise ValueError("local depth event is stale or future-dated")
            bids = cast(list[list[str]], depth["bids"])
            asks = cast(list[list[str]], depth["asks"])
            if not bids or not asks:
                raise ValueError("local depth must contain both sides")
            return {
                "bid_depth": str(sum((Decimal(row[1]) for row in bids), Decimal(0))),
                "ask_depth": str(sum((Decimal(row[1]) for row in asks), Decimal(0))),
                "depth_source": "CANONICAL_LOCAL_DEPTH_JOURNAL",
                "depth_last_update_id": depth["lastUpdateId"],
                "depth_received_at": depth["received_at"],
                "depth_event_at": event_at,
                "depth_coverage": depth["coverage"],
            }
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            return {"depth_status": "UNAVAILABLE"}

    def _fetch_klines(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
    ) -> dict[str, tuple[MarketKline, ...]]:
        if self.archive is not None:
            local: dict[str, tuple[MarketKline, ...]] = {}
            for timeframe in timeframes:
                try:
                    manifest = self.archive.manifest(symbol, timeframe)
                    if manifest.gap_count:
                        raise ValueError("local market dataset has gaps")
                    candles = self.archive.read(symbol, timeframe)[-self.candle_limit :]
                    local[timeframe] = tuple(
                        MarketKline(
                            open_time=candle.timestamp,
                            close_time=candle.timestamp
                            + timeframe_duration(timeframe)
                            - timedelta(milliseconds=1),
                            open=candle.open,
                            high=candle.high,
                            low=candle.low,
                            close=candle.close,
                            volume=candle.volume,
                        )
                        for candle in candles
                    )
                except (OSError, ValueError):
                    local[timeframe] = ()
            return local
        workers = min(self.max_workers, len(timeframes))
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="ai4binance-data",
        ) as executor:
            futures = {
                timeframe: executor.submit(
                    self.client.klines,
                    symbol,
                    timeframe,
                    self.candle_limit,
                )
                for timeframe in timeframes
            }
            return {timeframe: futures[timeframe].result() for timeframe in timeframes}

    @staticmethod
    def _snapshot_id(
        symbol: str,
        server_time: datetime,
        latest_price: object,
        last_close_times: dict[str, datetime],
    ) -> str:
        components = [symbol, server_time.isoformat(), str(latest_price)]
        components.extend(
            f"{timeframe}:{last_close_times[timeframe].isoformat()}"
            for timeframe in sorted(last_close_times)
        )
        digest = sha256("|".join(components).encode("utf-8")).hexdigest()[:20]
        return f"binance:{symbol}:{digest}"

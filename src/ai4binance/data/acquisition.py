"""Single-cycle public market snapshot acquisition."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.exchange.client import PublicMarketDataClient
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import MarketKline
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle


@dataclass(frozen=True, slots=True)
class DataAcquisitionAgent:
    """Build one immutable shared snapshot from public Spot market data."""

    client: PublicMarketDataClient
    candle_limit: int = 250
    minimum_closed_candles: int = 200
    max_workers: int = 4

    def __post_init__(self) -> None:
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
            server_time,
            latest_price,
            last_close_times,
        )
        return MarketSnapshot(
            snapshot_id=snapshot_id,
            created_at=server_time,
            exchange="Binance",
            market_type="Spot",
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
                "source": "BINANCE_PUBLIC_REST",
                "closed_candles_only": True,
            },
        )

    def _fetch_klines(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
    ) -> dict[str, tuple[MarketKline, ...]]:
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

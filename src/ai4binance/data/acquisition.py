"""Single-cycle public market snapshot acquisition."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import cast

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.domain.market_data import MarketDataProvenance
from ai4binance.exchange.client import BinancePublicClient, PublicMarketDataClient
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import MarketKline
from ai4binance.schemas import (
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
    is_spot_market_type,
)


@dataclass(frozen=True, slots=True)
class ArchivedMarketSnapshotAcquisition:
    """Validate native archived candles at one explicit research cutoff.

    Retrieval and mutable partition hashes are lineage, not semantic identity.
    Candle closure does not establish historical source publication time.
    """

    archive: ParquetOHLCVArchive
    market_type: str
    history_limit: int = 250
    minimum_closed_candles: int = 200
    require_futures_enrichment: bool = False
    local_candle_limits: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        if self.market_type not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError("archived snapshots require an explicit supported market")
        if not 1 <= self.minimum_closed_candles <= self.history_limit <= 10_000:
            raise ValueError("archived snapshot candle bounds are invalid")
        if self.local_candle_limits is not None:
            for timeframe, limit in self.local_candle_limits.items():
                timeframe_duration(timeframe)
                if isinstance(limit, bool) or not (
                    self.minimum_closed_candles <= limit <= self.history_limit
                ):
                    raise ValueError("archived per-timeframe candle limit is invalid")

    def acquire(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        *,
        cutoff: datetime,
    ) -> MarketSnapshot:
        """Keep missing, invalid, stale and post-cutoff data fail closed."""
        if cutoff.utcoffset() is None:
            raise ValueError("snapshot cutoff must be timezone-aware")
        cutoff = cutoff.astimezone(UTC)
        if not timeframes or len(set(timeframes)) != len(timeframes):
            raise ValueError("timeframes must be non-empty and unique")
        symbol = ParquetOHLCVArchive._validate_identity(symbol, timeframes[0], "read")
        candles_by_timeframe: dict[str, tuple[OHLCVCandle, ...]] = {}
        freshness: dict[str, object] = {}
        lineage: dict[str, object] = {}
        blockers: list[str] = (
            ["FUTURES_ENRICHMENT_UNVERIFIED"] if self.require_futures_enrichment else []
        )
        semantic_rows: dict[str, object] = {}
        for timeframe in timeframes:
            duration = timeframe_duration(timeframe)
            limit = (self.local_candle_limits or {}).get(timeframe, self.history_limit)
            required = (self.local_candle_limits or {}).get(
                timeframe, self.minimum_closed_candles
            )
            candles: tuple[OHLCVCandle, ...] = ()
            reasons: list[str] = []
            try:
                manifest = self.archive.manifest(symbol, timeframe)
                if not manifest.source.startswith(
                    ("BINANCE_PUBLIC_REST_", "BINANCE_VISION_")
                ):
                    raise ValueError(
                        "archive source is not verified Binance provenance"
                    )
                candles = self.archive.read_window(
                    symbol,
                    timeframe,
                    start_at=cutoff - duration * (limit + 1),
                    end_at=cutoff - duration,
                )[-limit:]
                # A concurrent canonical writer may replace a partition between
                # reads. Do not bind new rows to an earlier partition checksum.
                if self.archive.manifest(symbol, timeframe) != manifest:
                    raise ValueError("archive changed during snapshot acquisition")
                if any(
                    following.timestamp - current.timestamp != duration
                    for current, following in pairwise(candles)
                ):
                    reasons.append("DATASET_GAP")
                lineage[timeframe] = {
                    "source": manifest.source,
                    "dataset_sha256": manifest.sha256,
                    "dataset_row_count": manifest.row_count,
                    "partition_generated_at": manifest.generated_at,
                    "publication_time_status": "NOT_VERIFIED",
                    "volume_unit": "BASE_ASSET",
                }
            except OSError, ValueError:
                candles = ()
                reasons.append("ARCHIVE_UNAVAILABLE_OR_INVALID")
            if len(candles) < required:
                reasons.append("INSUFFICIENT_CLOSED_CANDLES")
            last_end = candles[-1].timestamp + duration if candles else None
            age = (cutoff - last_end).total_seconds() if last_end else None
            stale = age is None or age >= duration.total_seconds()
            if stale:
                reasons.append("STALE_OR_MISSING")
            candles_by_timeframe[timeframe] = candles
            freshness[timeframe] = {
                "period_end_exclusive": last_end.isoformat() if last_end else None,
                "last_open": candles[-1].timestamp.isoformat() if candles else None,
                "age_seconds": age,
                "stale": stale,
                "closed_candle_count": len(candles),
                "required": True,
                "required_candle_count": required,
                "blocking_reasons": reasons,
            }
            blockers.extend(f"{timeframe}:{reason}" for reason in reasons)
            semantic_rows[timeframe] = [
                [
                    candle.timestamp.isoformat(),
                    *(
                        str(value)
                        for value in (
                            candle.open,
                            candle.high,
                            candle.low,
                            candle.close,
                            candle.volume,
                        )
                    ),
                ]
                for candle in candles
            ]
        semantic = {
            "version": "1.0",
            "market": self.market_type,
            "symbol": symbol,
            "cutoff": cutoff.isoformat(),
            "history_limit": self.history_limit,
            "minimum_closed_candles": self.minimum_closed_candles,
            "local_candle_limits": dict(self.local_candle_limits or {}),
            "candles": semantic_rows,
            "blocking_reasons": blockers,
        }
        digest = sha256(
            json.dumps(
                semantic, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        event_timeframe = min(timeframes, key=timeframe_duration)
        event_candles = candles_by_timeframe[event_timeframe]
        return MarketSnapshot(
            snapshot_id=f"binance:archive:{digest}",
            created_at=cutoff,
            exchange="Binance",
            market_type=self.market_type,
            symbol=symbol,
            timeframes=timeframes,
            ohlcv_by_timeframe=candles_by_timeframe,
            latest_price=event_candles[-1].close if event_candles else None,
            bid=None,
            ask=None,
            spread=None,
            data_freshness=freshness,
            data_quality=DataQuality.DATA_INVALID
            if blockers
            else DataQuality.DATA_VALID,
            provenance_class=MarketDataProvenance.HISTORICAL_REAL,
            market_metadata={
                "semantic_sha256": digest,
                "source_lineage": lineage,
                "blocking_reasons": blockers,
                "publication_time_status": "NOT_VERIFIED",
                "historical_live_availability_verified": False,
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )


class LocalMarketSnapshotError(ExchangePayloadError):
    """Expose a sanitized collector failure without disclosing payload contents."""

    def __init__(
        self,
        blocker_code: str,
        source_filename: str,
        *,
        observed_at: datetime | None = None,
        cutoff_at: datetime | None = None,
    ) -> None:
        super().__init__("canonical local market snapshot is unavailable")
        self.blocker_code = blocker_code
        self.source_filename = source_filename
        self.observed_at = observed_at
        self.cutoff_at = cutoff_at


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
            "/fapi/v1/premiumIndex": "premiumIndex.json",
        }
        if path not in filenames:
            raise ExchangePayloadError("shared collector owns market-data acquisition")
        if (
            path.endswith("premiumIndex")
            and not (self.directory / filenames[path]).exists()
        ):
            filenames[path] = "premium-index.json"
        observed_at: datetime | None = None
        cutoff_at: datetime | None = None
        try:
            if (self.directory / filenames[path]).stat().st_size > 8_000_000:
                raise ValueError("LOCAL_MARKET_SNAPSHOT_OVERSIZED")
            payload = json.loads(
                (self.directory / filenames[path]).read_text(encoding="utf-8")
            )
            if path.startswith("/fapi/") and payload.get("source") != path:
                raise ValueError("LOCAL_MARKET_SNAPSHOT_SOURCE_INVALID")
            observed = datetime.fromisoformat(payload["observed_at"])
            if observed.utcoffset() is None:
                raise ValueError("LOCAL_MARKET_SNAPSHOT_TIMESTAMP_INVALID")
            observed_at, cutoff_at = observed, self.clock()
            maximum_age = (
                86400 if path.endswith("exchangeInfo") else self.maximum_age_seconds
            )
            self._validate_receipt_time(observed, cutoff_at, maximum_age)
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
                raise ValueError("LOCAL_MARKET_SNAPSHOT_SYMBOL_INVALID")
            item = matching[0]
            if path.endswith("exchangeInfo"):
                return {"symbols": [item]}
            if path.endswith("ticker/price"):
                return {"symbol": symbol, "price": item["lastPrice"]}
            return item
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            safe_codes = {
                "LOCAL_MARKET_SNAPSHOT_OVERSIZED",
                "LOCAL_MARKET_SNAPSHOT_TIMESTAMP_INVALID",
                "LOCAL_MARKET_SNAPSHOT_STALE",
                "LOCAL_MARKET_SNAPSHOT_FUTURE",
                "LOCAL_MARKET_SNAPSHOT_SYMBOL_INVALID",
                "LOCAL_MARKET_SNAPSHOT_SOURCE_INVALID",
            }
            code = (
                "LOCAL_MARKET_SNAPSHOT_MISSING"
                if isinstance(error, FileNotFoundError)
                else str(error)
                if str(error) in safe_codes
                else "LOCAL_MARKET_SNAPSHOT_INVALID"
            )
            raise LocalMarketSnapshotError(
                code,
                filenames[path],
                observed_at=observed_at,
                cutoff_at=cutoff_at,
            ) from error

    @staticmethod
    def _validate_receipt_time(
        observed: datetime,
        cutoff: datetime,
        maximum_age: float,
    ) -> None:
        """Distinguish future and expired receipts without widening freshness."""
        age = (cutoff - observed).total_seconds()
        if age < 0:
            raise ValueError("LOCAL_MARKET_SNAPSHOT_FUTURE")
        if age > maximum_age:
            raise ValueError("LOCAL_MARKET_SNAPSHOT_STALE")

    def attach_futures_context(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Attach collector-owned public evidence without network acquisition.

        Missing, future, stale, and wrong-symbol evidence stays unavailable.
        This current-observation reader must never enrich historical replay.
        """
        if snapshot.market_type != "USD_M_FUTURES":
            raise ValueError("local Futures context requires a USD-M snapshot")
        ParquetOHLCVArchive._validate_identity(snapshot.symbol, "5m", "local_read")
        if abs((self.clock() - snapshot.created_at).total_seconds()) > 1:
            raise ValueError(
                "local Futures context cannot enrich a historical snapshot"
            )
        snapshot = self._attach_futures_liquidity(snapshot)
        metadata = dict(snapshot.market_metadata)
        metadata.pop("futures_context_blockers", None)
        snapshot = replace(snapshot, market_metadata=metadata, derivatives_snapshot={})
        failure_code = "FUTURES_MARK_PRICE_UNAVAILABLE_OR_INVALID"
        try:
            premium = self.get_json(
                "/fapi/v1/premiumIndex", {"symbol": snapshot.symbol}
            )
            if not isinstance(premium, Mapping):
                raise ValueError("local Futures market evidence is invalid")
            as_of = datetime.fromtimestamp(int(str(premium["time"])) / 1000, tz=UTC)
            if (
                not 0
                <= (snapshot.created_at - as_of).total_seconds()
                <= self.maximum_age_seconds
            ):
                raise ValueError("local Futures mark-price evidence is stale")
            failure_code = "FUTURES_OPEN_INTEREST_UNAVAILABLE_OR_INVALID"
            oi, oi_time = self._latest_open_interest(snapshot)
            return replace(
                snapshot,
                derivatives_snapshot={
                    "symbol": snapshot.symbol,
                    "market": "USD_M_FUTURES",
                    "as_of": min(as_of, oi_time).isoformat(),
                    "source_count": 2,
                    "funding_rate": premium["lastFundingRate"],
                    "mark_price": premium["markPrice"],
                    "index_price": premium["indexPrice"],
                    "open_interest": str(oi),
                    "source": "CANONICAL_LOCAL_COLLECTOR",
                },
            )
        except (
            ExchangePayloadError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            IndexError,
            ArithmeticError,
        ) as error:
            if str(error) in {
                "FUTURES_OPEN_INTEREST_UNAVAILABLE",
                "FUTURES_OPEN_INTEREST_UNAVAILABLE_OR_INVALID",
                "FUTURES_OPEN_INTEREST_INVALID",
                "FUTURES_OPEN_INTEREST_SYMBOL_MISMATCH",
                "FUTURES_OPEN_INTEREST_STALE_OR_FUTURE",
                "FUTURES_OPEN_INTEREST_CONFLICT",
            }:
                failure_code = str(error)
            return replace(
                snapshot,
                derivatives_snapshot={},
                market_metadata={
                    **snapshot.market_metadata,
                    "futures_context_blockers": (failure_code,),
                },
            )

    def _attach_futures_liquidity(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Validate listing and book evidence independently from derivatives.

        Missing open interest must not discard independently verified liquidity.
        Invalid liquidity removes any previous listing, filters, and spread.
        """
        metadata = dict(snapshot.market_metadata)
        metadata.pop("trading_status", None)
        metadata.pop("futures_liquidity_blockers", None)
        metadata.pop("futures_liquidity_failure", None)
        empty = replace(
            snapshot,
            bid=None,
            ask=None,
            spread=None,
            exchange_filters={},
            market_metadata=metadata,
        )
        source_filename = "exchange-info.json"
        try:
            exchange = self.get_json(
                "/fapi/v1/exchangeInfo", {"symbol": snapshot.symbol}
            )
            if not isinstance(exchange, Mapping):
                raise ValueError("FUTURES_LIQUIDITY_PAYLOAD_INVALID")
            symbol_info = exchange["symbols"][0]
            self._validate_futures_listing_identity(symbol_info, snapshot.symbol)
            filters = self._validated_futures_filters(symbol_info.get("filters"))
            if not isinstance(symbol_info["status"], str):
                raise ValueError("FUTURES_LIQUIDITY_TRADING_STATUS_INVALID")
            source_filename = "ticker-bookTicker.json"
            book = self.get_json(
                "/fapi/v1/ticker/bookTicker", {"symbol": snapshot.symbol}
            )
            if not isinstance(book, Mapping):
                raise ValueError("FUTURES_LIQUIDITY_PAYLOAD_INVALID")
            book_time = datetime.fromtimestamp(int(str(book["time"])) / 1000, tz=UTC)
            if (
                not 0
                <= (snapshot.created_at - book_time).total_seconds()
                <= self.maximum_age_seconds
            ):
                raise ValueError("FUTURES_LIQUIDITY_BOOK_STALE_OR_FUTURE")
            bid, ask = Decimal(str(book["bidPrice"])), Decimal(str(book["askPrice"]))
            if not bid.is_finite() or not ask.is_finite() or not 0 < bid <= ask:
                raise ValueError("FUTURES_LIQUIDITY_SPREAD_INVALID")
            return replace(
                empty,
                bid=bid,
                ask=ask,
                spread=ask - bid,
                exchange_filters=filters,
                market_metadata={**metadata, "trading_status": symbol_info["status"]},
            )
        except (
            ExchangePayloadError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            IndexError,
            ArithmeticError,
        ) as error:
            return self._liquidity_failure(empty, source_filename, error)

    @staticmethod
    def _validate_futures_listing_identity(listing: object, symbol: str) -> None:
        """Require the same perpetual, quote-margined identity as the universe owner."""
        if not isinstance(listing, Mapping):
            raise ValueError("FUTURES_LIQUIDITY_LISTING_IDENTITY_INVALID")
        base, quote = listing.get("baseAsset"), listing.get("quoteAsset")
        if (
            listing.get("symbol") != symbol
            or listing.get("contractType") != "PERPETUAL"
            or not isinstance(base, str)
            or not base
            or not isinstance(quote, str)
            or not quote
            or base + quote != symbol
            or listing.get("marginAsset") != quote
        ):
            raise ValueError("FUTURES_LIQUIDITY_LISTING_IDENTITY_INVALID")

    @staticmethod
    def _validated_futures_filters(raw: object) -> dict[str, dict[str, object]]:
        """Validate public Futures constraints without applying order or risk policy.

        Futures MIN_NOTIONAL uses notional, unlike the Spot minNotional field.
        PRICE_FILTER zero values disable individual rules in the exchange contract.
        Unrelated exchange filters remain intact for their owning consumers.
        """
        try:
            if not isinstance(raw, list) or not raw:
                raise ValueError
            filters: dict[str, dict[str, object]] = {}
            for item in raw:
                if not isinstance(item, Mapping):
                    raise ValueError
                name = item.get("filterType")
                if not isinstance(name, str) or not name or name in filters:
                    raise ValueError
                filters[name] = dict(item)
            LocalMarketSnapshotTransport._futures_filter_numbers(
                filters["MIN_NOTIONAL"], ("notional",)
            )
            for name, fields in (
                ("PRICE_FILTER", ("minPrice", "maxPrice", "tickSize")),
                ("LOT_SIZE", ("minQty", "maxQty", "stepSize")),
                ("MARKET_LOT_SIZE", ("minQty", "maxQty", "stepSize")),
            ):
                values = LocalMarketSnapshotTransport._futures_filter_numbers(
                    filters[name], fields
                )
                minimum, maximum, step = values
                if name == "PRICE_FILTER":
                    if minimum > 0 and maximum > 0 and minimum > maximum:
                        raise ValueError
                elif maximum <= 0 or step <= 0 or minimum > maximum:
                    raise ValueError
            return filters
        except (KeyError, ValueError, TypeError, ArithmeticError) as error:
            raise ValueError("FUTURES_LIQUIDITY_FILTERS_INVALID") from error

    @staticmethod
    def _futures_filter_numbers(
        values: Mapping[str, object], fields: tuple[str, ...]
    ) -> tuple[Decimal, ...]:
        """Reject absent, boolean, nonnumeric, non-finite, and negative constraints."""
        result: list[Decimal] = []
        for field in fields:
            raw = values[field]
            if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
                raise ValueError
            value = Decimal(str(raw))
            if not value.is_finite() or value < 0:
                raise ValueError
            result.append(value)
        return tuple(result)

    @staticmethod
    def _liquidity_failure(
        empty: MarketSnapshot,
        source_filename: str,
        error: Exception,
    ) -> MarketSnapshot:
        """Retain bounded public-source diagnostics and remove unsafe inputs."""
        reason = str(error)
        observed_at = None
        if isinstance(error, LocalMarketSnapshotError):
            reason = error.blocker_code
            observed_at = error.observed_at
        safe_reasons = {
            "LOCAL_MARKET_SNAPSHOT_MISSING",
            "LOCAL_MARKET_SNAPSHOT_OVERSIZED",
            "LOCAL_MARKET_SNAPSHOT_TIMESTAMP_INVALID",
            "LOCAL_MARKET_SNAPSHOT_STALE",
            "LOCAL_MARKET_SNAPSHOT_FUTURE",
            "LOCAL_MARKET_SNAPSHOT_SYMBOL_INVALID",
            "LOCAL_MARKET_SNAPSHOT_SOURCE_INVALID",
            "LOCAL_MARKET_SNAPSHOT_INVALID",
            "FUTURES_LIQUIDITY_PAYLOAD_INVALID",
            "FUTURES_LIQUIDITY_LISTING_IDENTITY_INVALID",
            "FUTURES_LIQUIDITY_FILTERS_INVALID",
            "FUTURES_LIQUIDITY_TRADING_STATUS_INVALID",
            "FUTURES_LIQUIDITY_BOOK_STALE_OR_FUTURE",
            "FUTURES_LIQUIDITY_SPREAD_INVALID",
        }
        if reason not in safe_reasons:
            reason = "FUTURES_LIQUIDITY_PAYLOAD_INVALID"
        code = (
            reason if reason.startswith("FUTURES_") else f"FUTURES_LIQUIDITY_{reason}"
        )
        return replace(
            empty,
            market_metadata={
                **empty.market_metadata,
                "futures_liquidity_blockers": (f"{code}:{source_filename}",),
                "futures_liquidity_failure": {
                    "source_filename": source_filename,
                    "reason_code": reason,
                    "observed_at": observed_at.isoformat()
                    if isinstance(observed_at, datetime)
                    else None,
                    "cutoff_at": empty.created_at.isoformat(),
                },
            },
        )

    def _latest_open_interest(
        self, snapshot: MarketSnapshot
    ) -> tuple[Decimal, datetime]:
        directory = (
            self.directory.parent / snapshot.symbol / "details" / "open_interest"
        )
        current = directory / "current.json"
        pages = sorted(
            (p for p in directory.glob("*.json") if p.stem.isdigit()),
            key=lambda p: int(p.stem),
            reverse=True,
        )[:4]
        if current.exists():
            pages = [current]
        points: list[tuple[datetime, Decimal]] = []
        for page in pages:
            payload = self._open_interest_payload(page, snapshot)
            if payload.get("source") != "/futures/data/openInterestHist":
                continue
            previous: datetime | None = None
            for row in cast(list[Mapping[str, object]], payload["rows"]):
                stamp, value = self._open_interest_point(
                    row, snapshot, current=page == current, previous=previous
                )
                previous = stamp
                if (
                    0
                    <= (snapshot.created_at - stamp).total_seconds()
                    <= self.maximum_age_seconds
                ):
                    points.append((stamp, value))
        if not points:
            if current.exists():
                raise ValueError("FUTURES_OPEN_INTEREST_STALE_OR_FUTURE")
            raise ValueError("FUTURES_OPEN_INTEREST_UNAVAILABLE")
        if any(len({v for t, v in points if t == stamp}) != 1 for stamp, _ in points):
            raise ValueError("FUTURES_OPEN_INTEREST_CONFLICT")
        stamp, value = max(points, key=lambda point: point[0])
        return value, stamp

    def _open_interest_point(
        self,
        row: Mapping[str, object],
        snapshot: MarketSnapshot,
        *,
        current: bool,
        previous: datetime | None,
    ) -> tuple[datetime, Decimal]:
        """Validate source identity and positive finite OI before using a point."""
        if row.get("symbol") != snapshot.symbol:
            raise ValueError("FUTURES_OPEN_INTEREST_SYMBOL_MISMATCH")
        stamp = datetime.fromtimestamp(int(str(row["timestamp"])) / 1000, tz=UTC)
        value = Decimal(str(row["sumOpenInterest"]))
        if not value.is_finite() or value <= 0:
            raise ValueError("FUTURES_OPEN_INTEREST_INVALID")
        if current:
            if previous is not None and stamp - previous != timedelta(minutes=5):
                raise ValueError("FUTURES_OPEN_INTEREST_CONFLICT")
            if stamp > snapshot.created_at:
                raise ValueError("FUTURES_OPEN_INTEREST_STALE_OR_FUTURE")
        return stamp, value

    def _open_interest_payload(
        self, page: Path, snapshot: MarketSnapshot
    ) -> dict[str, object]:
        """Read one receipt once and fail closed on unavailable current evidence."""
        if page.is_symlink() or page.stat().st_size > 8_000_000:
            raise ValueError("FUTURES_OPEN_INTEREST_INVALID")
        payload = json.loads(page.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("FUTURES_OPEN_INTEREST_INVALID")
        if page.name != "current.json":
            return payload
        expected = {
            "source": "/futures/data/openInterestHist",
            "symbol": snapshot.symbol,
            "status": "CURRENT",
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        rows = payload.get("rows")
        if (
            any(payload.get(key) != value for key, value in expected.items())
            or payload.get("execution_allowed") is not False
            or not isinstance(rows, list)
            or not 1 <= len(rows) <= 4
        ):
            raise ValueError("FUTURES_OPEN_INTEREST_UNAVAILABLE_OR_INVALID")
        observed = datetime.fromisoformat(payload["observed_at"])
        if observed.utcoffset() is None or not (
            0
            <= (snapshot.created_at - observed).total_seconds()
            <= self.maximum_age_seconds
        ):
            raise ValueError("FUTURES_OPEN_INTEREST_STALE_OR_FUTURE")
        return payload


@dataclass(frozen=True, slots=True)
class DataAcquisitionAgent:
    """Build one immutable shared snapshot from public Spot market data."""

    client: PublicMarketDataClient
    market_type: str = "Spot"
    candle_limit: int = 250
    minimum_closed_candles: int = 200
    local_candle_limits: Mapping[str, int] | None = None
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
        if self.local_candle_limits is not None:
            if self.archive is None:
                raise ValueError("per-timeframe candle limits require a local archive")
            for timeframe, limit in self.local_candle_limits.items():
                timeframe_duration(timeframe)
                if isinstance(limit, bool) or not (
                    self.minimum_closed_candles <= limit <= 10_000
                ):
                    raise ValueError("local candle limit is invalid")
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
            len(candles_by_timeframe[timeframe])
            >= (
                self.local_candle_limits.get(timeframe, self.minimum_closed_candles)
                if self.local_candle_limits is not None
                else self.minimum_closed_candles
            )
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
            provenance_class=MarketDataProvenance.LIVE_SOURCE,
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
        except OSError, sqlite3.Error, ValueError, KeyError, TypeError:
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
                    last = datetime.fromisoformat(manifest.last_timestamp)
                    duration = timeframe_duration(timeframe)
                    limit = (
                        self.local_candle_limits.get(timeframe, self.candle_limit)
                        if self.local_candle_limits is not None
                        else self.candle_limit
                    )
                    candles = self.archive.read_window(
                        symbol,
                        timeframe,
                        start_at=last - duration * (limit - 1),
                        end_at=last,
                    )
                    local[timeframe] = tuple(
                        MarketKline(
                            open_time=candle.timestamp,
                            close_time=candle.timestamp
                            + duration
                            - timedelta(milliseconds=1),
                            open=candle.open,
                            high=candle.high,
                            low=candle.low,
                            close=candle.close,
                            volume=candle.volume,
                        )
                        for candle in candles
                    )
                except OSError, ValueError:
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

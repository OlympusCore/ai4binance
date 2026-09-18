"""Canonical Binance WebSocket ingestion for direct native timeframes."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.parse import quote

from websockets.asyncio.client import connect

from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_sync import MARKET_HISTORY_TIMEFRAMES
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.exchange.public_stream import (
    BinanceSpotKlineParser,
    SpotKlineUpdate,
)
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified
from ai4binance.schemas import OHLCVCandle

_SAFE_STATE: dict[str, object] = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}


class MarketStreamGapError(ValueError):
    """Signal that REST gap recovery must complete before live ingestion resumes."""


@dataclass(frozen=True, slots=True)
class AdaptiveSubscriptionPlan:
    """Build one bounded base feed plus candidate-only microstructure feeds."""

    symbols: tuple[str, ...]
    candidates: tuple[str, ...] = ()
    maximum_candidates: int = 10
    maximum_streams: int = 1_024
    include_mark_price: bool = False

    def __post_init__(self) -> None:
        normalized = tuple(
            dict.fromkeys(symbol.strip().upper() for symbol in self.symbols)
        )
        candidate_set = frozenset(normalized)
        candidates = tuple(
            dict.fromkeys(
                symbol.strip().upper()
                for symbol in self.candidates
                if symbol.strip().upper() in candidate_set
            )
        )[: self.maximum_candidates]
        if (
            not normalized
            or len(normalized) > 50
            or any(
                not symbol.isascii() or not symbol.isalnum() for symbol in normalized
            )
            or not 1 <= self.maximum_candidates <= 10
            or not 1 <= self.maximum_streams <= 1_024
        ):
            raise ValueError("adaptive subscription plan is invalid")
        object.__setattr__(self, "symbols", normalized)
        object.__setattr__(self, "candidates", candidates)
        if len(self.streams()) > self.maximum_streams:
            raise ValueError("adaptive subscription plan exceeds connection capacity")

    def streams(self) -> tuple[str, ...]:
        """Return deterministic combined-stream names."""

        base = tuple(
            stream
            for symbol in self.symbols
            for stream in (
                *(
                    f"{symbol.lower()}@kline_{timeframe}"
                    for timeframe in MARKET_HISTORY_TIMEFRAMES
                ),
                f"{symbol.lower()}@ticker",
                f"{symbol.lower()}@bookTicker",
            )
        )
        enhanced = tuple(
            stream
            for symbol in self.candidates
            for stream in (
                f"{symbol.lower()}@aggTrade",
                f"{symbol.lower()}@depth5@100ms",
                *(
                    (f"{symbol.lower()}@markPrice@1s",)
                    if self.include_mark_price
                    else ()
                ),
            )
        )
        return (*base, *enhanced)


@dataclass(slots=True)
class SharedMarketCache:
    """Persist atomic local ticker and book snapshots for all read consumers."""

    directory: Path
    required_symbols: frozenset[str] = frozenset()
    _tickers: dict[str, dict[str, object]] = field(default_factory=dict, init=False)
    _books: dict[str, dict[str, object]] = field(default_factory=dict, init=False)
    _premiums: dict[str, dict[str, object]] = field(default_factory=dict, init=False)

    def apply(self, payload: Mapping[str, object], observed_at: datetime) -> bool:
        """Apply supported ticker/book events and report whether state changed."""

        event_type = payload.get("e")
        symbol = payload.get("s")
        if not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum():
            return False
        symbol = symbol.upper()
        if event_type == "24hrTicker":
            last_price = payload.get("c")
            if not isinstance(last_price, (str, int, float)):
                return False
            self._tickers[symbol] = {
                "symbol": symbol,
                "lastPrice": str(last_price),
                "quoteVolume": str(payload.get("q", "0")),
                "volume": str(payload.get("v", "0")),
            }
            return True
        if event_type == "bookTicker" or (
            event_type is None and "b" in payload and "a" in payload
        ):
            bid = payload.get("b")
            ask = payload.get("a")
            if not isinstance(bid, (str, int, float)) or not isinstance(
                ask, (str, int, float)
            ):
                return False
            self._books[symbol] = {
                "symbol": symbol,
                "bidPrice": str(bid),
                "askPrice": str(ask),
            }
            return True
        if event_type == "markPriceUpdate":
            mark_price = payload.get("p")
            index_price = payload.get("i")
            funding_rate = payload.get("r")
            event_time = payload.get("E")
            next_funding_time = payload.get("T", 0)
            numeric_text = (str, int, float)
            if (
                not isinstance(mark_price, numeric_text)
                or not isinstance(index_price, numeric_text)
                or not isinstance(funding_rate, numeric_text)
                or not isinstance(event_time, numeric_text)
                or not isinstance(next_funding_time, numeric_text)
            ):
                return False
            self._premiums[symbol] = {
                "symbol": symbol,
                "markPrice": str(mark_price),
                "indexPrice": str(index_price),
                "lastFundingRate": str(funding_rate),
                "time": int(event_time),
                "nextFundingTime": int(next_funding_time),
            }
            return True
        return False

    def flush(self, observed_at: datetime) -> None:
        """Write cycle-consistent cache projections for local-only readers."""

        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("cache observation timestamp must be timezone-aware")
        for name, rows in (
            ("ticker-24hr.json", self._tickers),
            ("ticker-bookTicker.json", self._books),
            ("premium-index.json", self._premiums),
        ):
            if (
                name != "premium-index.json"
                and self.required_symbols
                and not self.required_symbols.issubset(rows)
            ):
                continue
            write_json_object_verified(
                self.directory / name,
                {
                    "observed_at": observed_at.astimezone(UTC).isoformat(),
                    "rows": [rows[key] for key in sorted(rows)],
                    **_SAFE_STATE,
                },
                blocker="MARKET_GATEWAY_CACHE_WRITE_FAILED",
                subject_id=f"market-gateway:{name}",
            )


@dataclass(slots=True)
class DirectTimeframeWriter:
    """Append closed native-timeframe candles without local resampling."""

    archive: ParquetOHLCVArchive
    source: str

    def append(
        self,
        symbol: str,
        timeframe: str,
        candle: OHLCVCandle,
        observed_at: datetime,
    ) -> None:
        if timeframe not in MARKET_HISTORY_TIMEFRAMES:
            raise ValueError("native market timeframe is unsupported")
        if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() is None:
            raise ValueError("candle timestamp must be timezone-aware")

        try:
            manifest = self.archive.manifest(symbol, timeframe)
        except FileNotFoundError:
            manifest = None
        if manifest is not None:
            last = datetime.fromisoformat(manifest.last_timestamp)
            if candle.timestamp > last + timeframe_duration(timeframe):
                raise MarketStreamGapError("native stream gap requires REST recovery")
        self.archive.update(
            symbol,
            timeframe,
            (candle,),
            source=self.source,
            generated_at=observed_at,
        )


@dataclass(slots=True)
class CanonicalMarketStreamProcessor:
    """Validate combined-stream events and update only canonical local state."""

    market: str
    writer: DirectTimeframeWriter
    cache: SharedMarketCache
    parser: BinanceSpotKlineParser = field(default_factory=BinanceSpotKlineParser)
    cache_flush_interval_seconds: float = 1.0
    activity_observer: Callable[[datetime], None] | None = field(
        default=None, repr=False
    )
    monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)
    _last_cache_flush: float = field(default=0.0, init=False, repr=False)

    def process(self, raw_message: str | bytes) -> str:
        """Process one event and return a bounded outcome code."""

        encoded = (
            raw_message.decode("utf-8")
            if isinstance(raw_message, bytes)
            else raw_message
        )
        decoded = json.loads(encoded)
        if not isinstance(decoded, Mapping):
            raise ValueError("combined market stream payload must be an object")
        payload = decoded.get("data", decoded)
        if not isinstance(payload, Mapping):
            raise ValueError("combined market stream data must be an object")
        event_type = payload.get("e")
        if event_type == "kline":
            update = self.parser.parse(raw_message)
            if not isinstance(update, SpotKlineUpdate):
                return "RECONNECT_REQUIRED"
            self._observe_activity(update.event_time)
            if update.interval not in MARKET_HISTORY_TIMEFRAMES or not update.is_closed:
                return "IGNORED_OPEN_OR_UNSUPPORTED_KLINE"
            self.writer.append(
                update.symbol,
                update.interval,
                update.as_candle(),
                update.event_time,
            )
            return f"CLOSED_{update.interval.upper()}_APPLIED"
        observed_at = datetime.now(UTC)
        if self.cache.apply(payload, observed_at):
            self._observe_activity(observed_at)
            now = self.monotonic()
            if now - self._last_cache_flush >= self.cache_flush_interval_seconds:
                self.cache.flush(observed_at)
                self._last_cache_flush = now
            return "CACHE_UPDATED"
        return "IGNORED_UNSUPPORTED_EVENT"

    def _observe_activity(self, observed_at: datetime) -> None:
        if self.activity_observer is not None:
            self.activity_observer(observed_at)


MessageHandler = Callable[[str | bytes], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CombinedStreamConnectionManager:
    """One combined WebSocket connection with bounded planned rollover."""

    base_url: str
    plan: AdaptiveSubscriptionPlan
    maximum_connection_age: timedelta = timedelta(hours=23, minutes=50)
    receive_timeout_seconds: float = 30.0
    maximum_message_bytes: int = 65_536

    def __post_init__(self) -> None:
        if (
            not self.base_url.startswith("wss://")
            or self.maximum_connection_age <= timedelta(0)
            or self.maximum_connection_age >= timedelta(hours=24)
            or self.receive_timeout_seconds <= 0
        ):
            raise ValueError("combined stream connection configuration is invalid")

    @property
    def url(self) -> str:
        streams = "/".join(self.plan.streams())
        return f"{self.base_url.rstrip('/')}?streams={quote(streams, safe='/@_')}"

    async def run_once(self, handler: MessageHandler) -> str:
        """Consume until planned rollover or provider disconnect."""

        started = datetime.now(UTC)
        async with connect(
            self.url,
            max_size=self.maximum_message_bytes,
            ping_interval=None,
            close_timeout=5,
        ) as websocket:
            while datetime.now(UTC) - started < self.maximum_connection_age:
                try:
                    message = await asyncio.wait_for(
                        websocket.recv(), timeout=self.receive_timeout_seconds
                    )
                except TimeoutError:
                    continue
                if not isinstance(message, (str, bytes)):
                    raise ValueError("binary stream fragments are unsupported")
                await handler(message)
        return "PLANNED_ROLLOVER"


@dataclass(slots=True)
class BinanceMarketDataGateway:
    """Run separate Spot/Futures pools against one canonical local read path."""

    spot: CombinedStreamConnectionManager
    futures: CombinedStreamConnectionManager
    spot_processor: CanonicalMarketStreamProcessor
    futures_processor: CanonicalMarketStreamProcessor
    flush_interval_seconds: float = 1.0

    async def run_once(self) -> tuple[str, str]:
        """Run both market connections; a failure cancels the sibling fail closed."""

        async def consume(
            processor: CanonicalMarketStreamProcessor,
            message: str | bytes,
        ) -> None:
            processor.process(message)

        results = await asyncio.gather(
            self.spot.run_once(lambda message: consume(self.spot_processor, message)),
            self.futures.run_once(
                lambda message: consume(self.futures_processor, message)
            ),
        )
        observed_at = datetime.now(UTC)
        self.spot_processor.cache.flush(observed_at)
        self.futures_processor.cache.flush(observed_at)
        return cast(tuple[str, str], tuple(results))


def build_gateway(
    dataset_root: Path,
    *,
    spot_symbols: Sequence[str],
    futures_symbols: Sequence[str],
    spot_candidates: Sequence[str] = (),
    futures_candidates: Sequence[str] = (),
    activity_observer: Callable[[datetime], None] | None = None,
) -> BinanceMarketDataGateway:
    """Build the credential-free canonical live gateway for bounded universes."""

    spot_plan = AdaptiveSubscriptionPlan(tuple(spot_symbols), tuple(spot_candidates))
    futures_plan = AdaptiveSubscriptionPlan(
        tuple(futures_symbols),
        tuple(futures_candidates),
        include_mark_price=True,
    )
    spot_cache = SharedMarketCache(
        dataset_root / "spot" / "metadata", frozenset(spot_plan.symbols)
    )
    futures_cache = SharedMarketCache(
        dataset_root / "usd_m_futures" / "metadata",
        frozenset(futures_plan.symbols),
    )
    return BinanceMarketDataGateway(
        spot=CombinedStreamConnectionManager(
            "wss://stream.binance.com:9443/stream", spot_plan
        ),
        futures=CombinedStreamConnectionManager(
            "wss://fstream.binance.com/stream", futures_plan
        ),
        spot_processor=CanonicalMarketStreamProcessor(
            "SPOT",
            DirectTimeframeWriter(
                ParquetOHLCVArchive(dataset_root / "spot"),
                "BINANCE_SPOT_WEBSOCKET_DIRECT",
            ),
            spot_cache,
            activity_observer=activity_observer,
        ),
        futures_processor=CanonicalMarketStreamProcessor(
            "USD_M_FUTURES",
            DirectTimeframeWriter(
                ParquetOHLCVArchive(dataset_root / "usd_m_futures"),
                "BINANCE_USD_M_FUTURES_WEBSOCKET_DIRECT",
            ),
            futures_cache,
            activity_observer=activity_observer,
        ),
    )

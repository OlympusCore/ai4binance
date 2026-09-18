"""Fail-closed Binance Spot public kline stream contract and ingest bridge."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import cast

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.events.models import DomainEvent
from ai4binance.exchange.stream_state import PublicStreamRecovery, StreamTransition
from ai4binance.schemas import OHLCVCandle

SUPPORTED_DECISION_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


@dataclass(frozen=True, slots=True)
class BinanceSpotStreamPolicy:
    """Official public stream limits used before a network adapter exists."""

    maximum_message_bytes: int = 65_536
    maximum_streams_per_connection: int = 1_024
    maximum_control_messages_per_second: int = 5
    pong_deadline: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        limits = (
            self.maximum_message_bytes,
            self.maximum_streams_per_connection,
            self.maximum_control_messages_per_second,
        )
        if min(limits) < 1 or self.pong_deadline <= timedelta(0):
            raise ValueError("Binance Spot stream policy is invalid")

    def validate_subscriptions(self, subscriptions: tuple[str, ...]) -> None:
        if (
            not subscriptions
            or len(subscriptions) > self.maximum_streams_per_connection
            or len(set(subscriptions)) != len(subscriptions)
            or any(not item or item != item.lower() for item in subscriptions)
        ):
            raise ValueError(
                "stream subscriptions must be unique bounded lowercase text"
            )


@dataclass(frozen=True, slots=True)
class SpotKlineUpdate:
    """Normalized Binance Spot kline update with source trade lineage."""

    event_time: datetime
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    first_trade_id: int
    last_trade_id: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int
    is_closed: bool

    def __post_init__(self) -> None:
        for value in (self.event_time, self.open_time, self.close_time):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("kline timestamps must be timezone-aware")
        if (
            not self.symbol
            or self.symbol != self.symbol.upper()
            or not self.symbol.isascii()
            or not self.symbol.isalnum()
        ):
            raise ValueError("kline symbol must be normalized ASCII text")
        if self.interval not in SUPPORTED_DECISION_INTERVALS:
            raise ValueError("kline interval is unsupported")
        expected_close = (
            self.open_time
            + timeframe_duration(self.interval)
            - timedelta(milliseconds=1)
        )
        if (
            self.close_time != expected_close
            or self.event_time < self.open_time
            or (self.is_closed and self.event_time < self.close_time)
        ):
            raise ValueError("kline time bounds are invalid")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if any(not value.is_finite() or value < 0 for value in values):
            raise ValueError("kline values must be finite and non-negative")
        if self.low > min(self.open, self.close) or self.high < max(
            self.open, self.close
        ):
            raise ValueError("kline OHLC relationship is invalid")
        no_trades = self.trade_count == 0
        if self.trade_count < 0 or (
            no_trades and (self.first_trade_id != -1 or self.last_trade_id != -1)
        ):
            raise ValueError("empty kline trade lineage is invalid")
        if not no_trades and (
            self.first_trade_id < 0 or self.first_trade_id > self.last_trade_id
        ):
            raise ValueError("kline trade lineage is invalid")

    @property
    def sequence_bounds(self) -> tuple[int, int] | None:
        if self.trade_count == 0:
            return None
        return self.first_trade_id, self.last_trade_id

    def as_candle(self) -> OHLCVCandle:
        if not self.is_closed:
            raise ValueError("open kline cannot become a decision candle")
        return OHLCVCandle(
            timestamp=self.open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )

    def to_domain_event(
        self,
        *,
        sequence: int,
        previous_hash: str = "GENESIS",
    ) -> DomainEvent:
        """Create one journal-ready event without granting execution authority."""
        if not self.is_closed:
            raise ValueError("open kline cannot be journaled as closed")
        timestamp_ms = int(self.open_time.timestamp() * 1_000)
        return DomainEvent.create(
            event_id=f"binance:{self.symbol}:{self.interval}:{timestamp_ms}",
            aggregate_id=f"market:{self.symbol}:{self.interval}",
            event_type="SPOT_KLINE_CLOSED",
            sequence=sequence,
            occurred_at=self.event_time,
            payload=(
                ("close", str(self.close)),
                ("close_time", self.close_time.isoformat()),
                ("first_trade_id", str(self.first_trade_id)),
                ("high", str(self.high)),
                ("interval", self.interval),
                ("last_trade_id", str(self.last_trade_id)),
                ("low", str(self.low)),
                ("open", str(self.open)),
                ("open_time", self.open_time.isoformat()),
                ("symbol", self.symbol),
                ("trade_count", str(self.trade_count)),
                ("volume", str(self.volume)),
            ),
            previous_hash=previous_hash,
        )


@dataclass(frozen=True, slots=True)
class SpotStreamServerShutdown:
    event_time: datetime

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("shutdown timestamp must be timezone-aware")


SpotStreamMessage = SpotKlineUpdate | SpotStreamServerShutdown


@dataclass(frozen=True, slots=True)
class KlineIngestResult:
    transition: StreamTransition
    update: SpotKlineUpdate | None
    candle: OHLCVCandle | None
    blockers: tuple[str, ...]
    decision_eligible: bool
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.decision_eligible is not (
            self.candle is not None and not self.blockers
        ):
            raise ValueError("kline decision eligibility must fail closed")
        if self.execution_allowed:
            raise ValueError("public stream evidence cannot authorize execution")


@dataclass(slots=True)
class BinanceSpotKlineParser:
    policy: BinanceSpotStreamPolicy = BinanceSpotStreamPolicy()

    def parse(self, raw_message: str | bytes) -> SpotStreamMessage:
        encoded = (
            raw_message.encode("utf-8") if isinstance(raw_message, str) else raw_message
        )
        if not encoded or len(encoded) > self.policy.maximum_message_bytes:
            raise ExchangePayloadError("stream message size is invalid")
        try:
            decoded = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ExchangePayloadError("stream message is invalid JSON") from None
        envelope = self._mapping(decoded, "stream message")
        payload = envelope
        stream_name: str | None = None
        if "stream" in envelope or "data" in envelope:
            stream_name = self._text(envelope.get("stream"), "stream")
            payload = self._mapping(envelope.get("data"), "data")
        event_type = self._text(payload.get("e"), "event type")
        event_time = self._milliseconds(payload.get("E"), "event time")
        if event_type == "serverShutdown":
            return SpotStreamServerShutdown(event_time)
        if event_type != "kline":
            raise ExchangePayloadError("unsupported public stream event")
        kline = self._mapping(payload.get("k"), "kline")
        symbol = self._text(payload.get("s"), "symbol")
        if self._text(kline.get("s"), "kline symbol") != symbol:
            raise ExchangePayloadError("kline symbol identity mismatch")
        try:
            update = SpotKlineUpdate(
                event_time=event_time,
                symbol=symbol,
                interval=self._text(kline.get("i"), "interval"),
                open_time=self._milliseconds(kline.get("t"), "open time"),
                close_time=self._milliseconds(kline.get("T"), "close time"),
                first_trade_id=self._integer(kline.get("f"), "first trade ID"),
                last_trade_id=self._integer(kline.get("L"), "last trade ID"),
                open=self._decimal(kline.get("o"), "open"),
                high=self._decimal(kline.get("h"), "high"),
                low=self._decimal(kline.get("l"), "low"),
                close=self._decimal(kline.get("c"), "close"),
                volume=self._decimal(kline.get("v"), "volume"),
                trade_count=self._integer(kline.get("n"), "trade count"),
                is_closed=self._boolean(kline.get("x"), "closed"),
            )
        except ValueError as error:
            raise ExchangePayloadError("kline payload contract is invalid") from error
        expected_stream = f"{update.symbol.lower()}@kline_{update.interval}"
        if stream_name is not None and stream_name != expected_stream:
            raise ExchangePayloadError("combined stream identity mismatch")
        return update

    @staticmethod
    def _mapping(value: object, name: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ExchangePayloadError(f"{name} must be an object")
        return cast(Mapping[str, object], value)

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value:
            raise ExchangePayloadError(f"{name} must be non-empty text")
        return value

    @staticmethod
    def _integer(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExchangePayloadError(f"{name} must be an integer")
        return value

    @classmethod
    def _milliseconds(cls, value: object, name: str) -> datetime:
        milliseconds = cls._integer(value, name)
        if milliseconds < 0:
            raise ExchangePayloadError(f"{name} must be non-negative")
        return datetime.fromtimestamp(milliseconds / 1_000, tz=UTC)

    @staticmethod
    def _decimal(value: object, name: str) -> Decimal:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ExchangePayloadError(f"{name} must be numeric text")
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            raise ExchangePayloadError(f"{name} must be decimal-compatible") from None
        if not parsed.is_finite():
            raise ExchangePayloadError(f"{name} must be finite")
        return parsed

    @staticmethod
    def _boolean(value: object, name: str) -> bool:
        if not isinstance(value, bool):
            raise ExchangePayloadError(f"{name} must be boolean")
        return value


@dataclass(slots=True)
class PublicKlineIngestor:
    """Bridge validated kline messages into the existing recovery state machine."""

    symbol: str
    interval: str
    recovery: PublicStreamRecovery = field(default_factory=PublicStreamRecovery)
    parser: BinanceSpotKlineParser = field(default_factory=BinanceSpotKlineParser)
    _latest_closed_at: datetime | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        normalized = self.symbol.strip().upper()
        if (
            not normalized
            or not normalized.isascii()
            or not normalized.isalnum()
            or self.interval not in SUPPORTED_DECISION_INTERVALS
        ):
            raise ValueError("public kline ingestor identity is invalid")
        self.symbol = normalized

    def bootstrap(
        self,
        *,
        snapshot_sequence: int,
        connected_at: datetime,
    ) -> StreamTransition:
        self.recovery.start()
        self.recovery.connected(connected_at)
        return self.recovery.apply_snapshot(snapshot_sequence, connected_at)

    def ingest(
        self,
        raw_message: str | bytes,
        *,
        queue_depth: int = 0,
    ) -> KlineIngestResult:
        message = self.parser.parse(raw_message)
        if isinstance(message, SpotStreamServerShutdown):
            transition = self.recovery.server_shutdown()
            return KlineIngestResult(
                transition,
                None,
                None,
                transition.blockers,
                False,
            )
        if message.symbol != self.symbol or message.interval != self.interval:
            raise ExchangePayloadError("kline stream does not match ingestor identity")
        bounds = message.sequence_bounds
        if bounds is None:
            return KlineIngestResult(
                self.recovery.reject_unsequenced_update(),
                message,
                None,
                ("KLINE_TRADE_SEQUENCE_UNAVAILABLE",),
                False,
            )
        transition = self.recovery.apply_update(
            bounds[0],
            bounds[1],
            message.event_time,
            queue_depth=queue_depth,
        )
        if transition.blockers:
            return KlineIngestResult(
                transition,
                message,
                None,
                transition.blockers,
                False,
            )
        if not message.is_closed:
            return KlineIngestResult(
                transition,
                message,
                None,
                ("OPEN_KLINE_NOT_DECISION_ELIGIBLE",),
                False,
            )
        if (
            self._latest_closed_at is not None
            and message.close_time <= self._latest_closed_at
        ):
            return KlineIngestResult(
                transition,
                message,
                None,
                ("DUPLICATE_OR_OLD_CLOSED_KLINE",),
                False,
            )
        self._latest_closed_at = message.close_time
        candle = message.as_candle()
        return KlineIngestResult(transition, message, candle, (), True)

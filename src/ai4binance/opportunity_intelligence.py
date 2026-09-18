"""Canonical opportunity-intelligence observations and feature primitives.

The contracts in this module are research evidence only. Risk, validation,
decision governance, and execution remain separate veto-producing owners.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise

from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.indicators import atr, relative_volume
from ai4binance.schemas import MarketSnapshot, OHLCVCandle

ZERO = Decimal("0")
ONE = Decimal("1")
PRIMARY_OPPORTUNITY_TIMEFRAMES = ("15m", "1h", "4h")
TIMEFRAME_DURATIONS: Mapping[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "6h": timedelta(hours=6),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
}


class MultiTimeframeAlignmentState(StrEnum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    CONFLICTING = "CONFLICTING"
    TRANSITIONAL = "TRANSITIONAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNKNOWN = "UNKNOWN"


class CandleDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class CandlestickPattern(StrEnum):
    REJECTION = "REJECTION"
    STRONG_CONTINUATION = "STRONG_CONTINUATION"
    INSIDE_BAR = "INSIDE_BAR"
    OUTSIDE_BAR = "OUTSIDE_BAR"
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    INDECISION = "INDECISION"
    RANGE_EXPANSION = "RANGE_EXPANSION"
    RANGE_CONTRACTION = "RANGE_CONTRACTION"
    EXTENDED = "EXTENDED"


class ChartPatternLifecycleState(StrEnum):
    FORMING = "FORMING"
    POTENTIAL = "POTENTIAL"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class OpportunityEventType(StrEnum):
    OPPORTUNITY_OBSERVED = "OPPORTUNITY_OBSERVED"
    OPPORTUNITY_FORMING = "OPPORTUNITY_FORMING"
    OPPORTUNITY_UPDATED = "OPPORTUNITY_UPDATED"
    OPPORTUNITY_QUALIFIED = "OPPORTUNITY_QUALIFIED"
    OPPORTUNITY_CONFIRMED = "OPPORTUNITY_CONFIRMED"
    OPPORTUNITY_REJECTED = "OPPORTUNITY_REJECTED"
    OPPORTUNITY_BLOCKED = "OPPORTUNITY_BLOCKED"
    OPPORTUNITY_INVALIDATED = "OPPORTUNITY_INVALIDATED"
    OPPORTUNITY_EXPIRED = "OPPORTUNITY_EXPIRED"
    OPPORTUNITY_VIRTUAL_ELIGIBLE = "OPPORTUNITY_VIRTUAL_ELIGIBLE"
    OPPORTUNITY_VIRTUAL_EXECUTED = "OPPORTUNITY_VIRTUAL_EXECUTED"
    OPPORTUNITY_OUTCOME_EVALUATED = "OPPORTUNITY_OUTCOME_EVALUATED"
    OPPORTUNITY_CLOSED = "OPPORTUNITY_CLOSED"


@dataclass(frozen=True, slots=True)
class TimeframeCandleReference:
    timeframe: str
    candle_id: str
    open_time: datetime
    close_time: datetime
    closed: bool
    stale: bool

    def __post_init__(self) -> None:
        if not self.timeframe.strip() or not self.candle_id.strip():
            raise ValueError("timeframe candle identity is required")
        _require_aware(self.open_time, "candle open time")
        _require_aware(self.close_time, "candle close time")
        if self.close_time <= self.open_time:
            raise ValueError("candle close time must follow open time")

    def to_payload(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe,
            "candle_id": self.candle_id,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "closed": self.closed,
            "stale": self.stale,
        }


@dataclass(frozen=True, slots=True)
class MultiTimeframeDiagnostic:
    decision_time: datetime
    source_snapshot_id: str
    candle_references: tuple[TimeframeCandleReference, ...]
    higher_tf_bias: CandleDirection
    setup_tf_state: CandleDirection
    trigger_tf_state: CandleDirection
    alignment_status: MultiTimeframeAlignmentState
    blockers: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = "opportunity-mtf:v1"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_aware(self.decision_time, "decision time")
        if not self.source_snapshot_id.strip() or not self.schema_version.strip():
            raise ValueError("multi-timeframe diagnostic identity is required")
        timeframes = tuple(item.timeframe for item in self.candle_references)
        if len(set(timeframes)) != len(timeframes):
            raise ValueError("multi-timeframe candle references must be unique")
        _require_unique_nonblank(self.blockers, "multi-timeframe blockers")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("multi-timeframe diagnostic cannot authorize execution")

    @property
    def complete(self) -> bool:
        return (
            not self.blockers
            and tuple(item.timeframe for item in self.candle_references)
            == PRIMARY_OPPORTUNITY_TIMEFRAMES
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "decision_time": self.decision_time.isoformat(),
            "source_snapshot_id": self.source_snapshot_id,
            "candle_references": tuple(
                item.to_payload() for item in self.candle_references
            ),
            "higher_tf_bias": self.higher_tf_bias.value,
            "setup_tf_state": self.setup_tf_state.value,
            "trigger_tf_state": self.trigger_tf_state.value,
            "alignment_status": self.alignment_status.value,
            "blockers": self.blockers,
            "schema_version": self.schema_version,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class CandleGeometry:
    body_size: Decimal
    candle_range: Decimal
    body_to_range_ratio: Decimal
    upper_wick: Decimal
    lower_wick: Decimal
    upper_wick_ratio: Decimal
    lower_wick_ratio: Decimal
    close_location: Decimal
    range_vs_atr: Decimal | None
    range_vs_recent_range: Decimal | None
    relative_volume: Decimal | None
    direction: CandleDirection

    def __post_init__(self) -> None:
        magnitudes = (
            self.body_size,
            self.candle_range,
            self.upper_wick,
            self.lower_wick,
        )
        ratios = (
            self.body_to_range_ratio,
            self.upper_wick_ratio,
            self.lower_wick_ratio,
            self.close_location,
        )
        if any(value < ZERO for value in magnitudes):
            raise ValueError("candle geometry cannot be negative")
        if any(not ZERO <= value <= ONE for value in ratios):
            raise ValueError("candle geometry ratios must be bounded")
        for value in (
            self.range_vs_atr,
            self.range_vs_recent_range,
            self.relative_volume,
        ):
            if value is not None and (not value.is_finite() or value < ZERO):
                raise ValueError("candle relative geometry must be finite")

    def to_payload(self) -> dict[str, object]:
        return {
            "body_size": str(self.body_size),
            "candle_range": str(self.candle_range),
            "body_to_range_ratio": str(self.body_to_range_ratio),
            "upper_wick": str(self.upper_wick),
            "lower_wick": str(self.lower_wick),
            "upper_wick_ratio": str(self.upper_wick_ratio),
            "lower_wick_ratio": str(self.lower_wick_ratio),
            "close_location": str(self.close_location),
            "range_vs_atr": _optional_decimal(self.range_vs_atr),
            "range_vs_recent_range": _optional_decimal(self.range_vs_recent_range),
            "relative_volume": _optional_decimal(self.relative_volume),
            "direction": self.direction.value,
        }


@dataclass(frozen=True, slots=True)
class CandlestickEvidence:
    geometry: CandleGeometry
    patterns: tuple[CandlestickPattern, ...]
    reason_codes: tuple[str, ...]
    rule_version: str = "candlestick-geometry:v1"

    def __post_init__(self) -> None:
        if len(set(self.patterns)) != len(self.patterns):
            raise ValueError("candlestick patterns must be unique")
        _require_unique_nonblank(self.reason_codes, "candlestick reason codes")


@dataclass(frozen=True, slots=True)
class ChartPatternObservation:
    pattern_id: str
    pattern_type: str
    directional_bias: CandleDirection
    timeframe: str
    start_time: datetime
    last_observation_time: datetime
    pivot_available_time: datetime
    anchor_points: tuple[tuple[str, datetime, Decimal], ...]
    boundary_model: tuple[tuple[str, str], ...]
    formation_progress: Decimal
    confirmation_condition: str
    invalidation_condition: str
    state: ChartPatternLifecycleState
    evidence_refs: tuple[str, ...]
    version: str = "chart-pattern:v1"

    def __post_init__(self) -> None:
        text = (
            self.pattern_id,
            self.pattern_type,
            self.timeframe,
            self.confirmation_condition,
            self.invalidation_condition,
            self.version,
        )
        if any(not value.strip() for value in text):
            raise ValueError("chart-pattern identity and rules are required")
        for value in (
            self.start_time,
            self.last_observation_time,
            self.pivot_available_time,
        ):
            _require_aware(value, "chart-pattern timestamp")
        if not ZERO <= self.formation_progress <= ONE:
            raise ValueError("chart-pattern formation progress must be 0..1")
        if not self.anchor_points:
            raise ValueError("chart-pattern anchors are required")
        if self.state is ChartPatternLifecycleState.CONFIRMED and (
            self.pivot_available_time > self.last_observation_time
        ):
            raise ValueError("chart pattern cannot confirm before pivot availability")
        _require_unique_nonblank(self.evidence_refs, "chart-pattern evidence")


@dataclass(frozen=True, slots=True)
class OpportunityLifecycleEvent:
    event_id: str
    event_type: OpportunityEventType
    opportunity_id: str
    lifecycle_state: OpportunityLifecycleState
    event_time: datetime
    cycle_id: str
    snapshot_id: str
    reason_codes: tuple[str, ...]
    decision_id: str | None = None
    virtual_execution_id: str | None = None
    closure_review_id: str | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    market: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    evaluation_stage: str | None = None
    missing_fields: tuple[str, ...] = field(default_factory=tuple)
    retryability: str | None = None
    schema_version: str = "opportunity-ledger:v1"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        identity = (
            self.event_id,
            self.opportunity_id,
            self.cycle_id,
            self.snapshot_id,
            self.schema_version,
        )
        if any(not value.strip() for value in identity):
            raise ValueError("opportunity lifecycle event identity is required")
        _require_aware(self.event_time, "opportunity event time")
        _require_unique_nonblank(self.reason_codes, "opportunity reason codes")
        _require_unique_nonblank(self.evidence_refs, "opportunity evidence refs")
        lineage = (
            self.decision_id,
            self.virtual_execution_id,
            self.closure_review_id,
        )
        if any(value is not None and not value.strip() for value in lineage):
            raise ValueError("opportunity lineage references cannot be blank")
        diagnostics = (
            self.market,
            self.symbol,
            self.timeframe,
            self.evaluation_stage,
            self.retryability,
        )
        if any(value is not None and not value.strip() for value in diagnostics):
            raise ValueError("opportunity diagnostic fields cannot be blank")
        _require_unique_nonblank(self.missing_fields, "opportunity missing fields")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity lifecycle event cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "opportunity_id": self.opportunity_id,
            "lifecycle_state": self.lifecycle_state.value,
            "event_time": self.event_time.isoformat(),
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "decision_id": self.decision_id,
            "virtual_execution_id": self.virtual_execution_id,
            "closure_review_id": self.closure_review_id,
            "reason_codes": self.reason_codes,
            "evidence_refs": self.evidence_refs,
            "schema_version": self.schema_version,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }
        optional = {
            "market": self.market,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "evaluation_stage": self.evaluation_stage,
            "retryability": self.retryability,
        }
        payload.update({key: value for key, value in optional.items() if value})
        if self.missing_fields:
            payload["missing_fields"] = self.missing_fields
        return payload


@dataclass(frozen=True, slots=True)
class OpportunityLifecycleLedger:
    """Append-only deterministic view with exact-event idempotency."""

    events: tuple[OpportunityLifecycleEvent, ...] = ()

    def append(self, event: OpportunityLifecycleEvent) -> OpportunityLifecycleLedger:
        existing = next(
            (item for item in self.events if item.event_id == event.event_id), None
        )
        if existing is not None:
            if existing != event:
                raise ValueError("opportunity event identity cannot change content")
            return self
        history = self.history(event.opportunity_id)
        if history:
            latest = history[-1]
            if event.event_time < latest.event_time:
                raise ValueError("opportunity lifecycle event time cannot regress")
            if not _valid_lifecycle_transition(
                latest.lifecycle_state, event.lifecycle_state
            ):
                raise ValueError("opportunity lifecycle transition is invalid")
        elif event.lifecycle_state not in {
            OpportunityLifecycleState.NEW,
            OpportunityLifecycleState.DISCOVERED,
            OpportunityLifecycleState.WATCH_ONLY,
            OpportunityLifecycleState.SETUP_FORMING,
        }:
            raise ValueError("opportunity lifecycle must begin with observation")
        return OpportunityLifecycleLedger((*self.events, event))

    def history(self, opportunity_id: str) -> tuple[OpportunityLifecycleEvent, ...]:
        return tuple(
            item for item in self.events if item.opportunity_id == opportunity_id
        )

    def first_seen_at(self, opportunity_id: str) -> datetime | None:
        history = self.history(opportunity_id)
        return history[0].event_time if history else None


def build_multi_timeframe_diagnostic(
    snapshot: MarketSnapshot,
    *,
    decision_time: datetime | None = None,
    timeframe_votes: Mapping[str, float] | None = None,
    maximum_stale_bars: int = 2,
) -> MultiTimeframeDiagnostic:
    """Select only candles knowable at decision time and classify TF relations."""
    observed_at = decision_time or snapshot.created_at
    _require_aware(observed_at, "decision time")
    if maximum_stale_bars < 0:
        raise ValueError("maximum stale bars cannot be negative")
    references: list[TimeframeCandleReference] = []
    selected: dict[str, tuple[OHLCVCandle, ...]] = {}
    blockers: list[str] = []
    for timeframe in PRIMARY_OPPORTUNITY_TIMEFRAMES:
        duration = TIMEFRAME_DURATIONS[timeframe]
        source = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
        if any(
            current.timestamp <= previous.timestamp
            for previous, current in pairwise(source)
        ):
            blockers.append(f"TIMEFRAME_SEQUENCE_INVALID:{timeframe}")
            continue
        closed = tuple(
            candle for candle in source if candle.timestamp + duration <= observed_at
        )
        if not closed:
            blockers.append(f"MISSING_CLOSED_TIMEFRAME:{timeframe}")
            continue
        selected[timeframe] = closed
        candle = closed[-1]
        close_time = candle.timestamp + duration
        stale = observed_at - close_time > duration * maximum_stale_bars
        freshness = snapshot.data_freshness.get(timeframe, {})
        if isinstance(freshness, Mapping) and isinstance(freshness.get("stale"), bool):
            stale = bool(freshness["stale"])
        if stale:
            blockers.append(f"STALE_TIMEFRAME:{timeframe}")
        references.append(
            TimeframeCandleReference(
                timeframe=timeframe,
                candle_id=_candle_id(snapshot.snapshot_id, timeframe, candle),
                open_time=candle.timestamp,
                close_time=close_time,
                closed=True,
                stale=stale,
            )
        )
    biases = {
        timeframe: _timeframe_bias(
            selected.get(timeframe, ()),
            None if timeframe_votes is None else timeframe_votes.get(timeframe),
        )
        for timeframe in PRIMARY_OPPORTUNITY_TIMEFRAMES
    }
    return MultiTimeframeDiagnostic(
        decision_time=observed_at,
        source_snapshot_id=snapshot.snapshot_id,
        candle_references=tuple(references),
        higher_tf_bias=biases["4h"],
        setup_tf_state=biases["1h"],
        trigger_tf_state=biases["15m"],
        alignment_status=_alignment_state(biases, bool(blockers)),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def candle_geometry(
    candle: OHLCVCandle,
    *,
    atr_value: Decimal | None = None,
    recent_range: Decimal | None = None,
    relative_volume_value: Decimal | None = None,
) -> CandleGeometry:
    candle_range = candle.high - candle.low
    body = abs(candle.close - candle.open)
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    denominator = candle_range if candle_range > ZERO else ONE
    direction = (
        CandleDirection.BULLISH
        if candle.close > candle.open
        else CandleDirection.BEARISH
        if candle.close < candle.open
        else CandleDirection.NEUTRAL
    )
    return CandleGeometry(
        body_size=body,
        candle_range=candle_range,
        body_to_range_ratio=body / denominator if candle_range > ZERO else ZERO,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        upper_wick_ratio=upper_wick / denominator if candle_range > ZERO else ZERO,
        lower_wick_ratio=lower_wick / denominator if candle_range > ZERO else ZERO,
        close_location=(candle.close - candle.low) / denominator
        if candle_range > ZERO
        else ZERO,
        range_vs_atr=(
            candle_range / atr_value
            if atr_value is not None and atr_value > ZERO
            else None
        ),
        range_vs_recent_range=(
            candle_range / recent_range
            if recent_range is not None and recent_range > ZERO
            else None
        ),
        relative_volume=relative_volume_value,
        direction=direction,
    )


def analyze_candlestick(
    candles: Sequence[OHLCVCandle],
    *,
    atr_period: int = 14,
    volume_window: int = 20,
) -> CandlestickEvidence:
    if len(candles) < 2:
        raise ValueError("candlestick analysis requires two closed candles")
    rows = tuple(candles)
    previous, current = rows[-2:]
    atr_value = atr(rows, min(atr_period, len(rows) - 1))
    recent_ranges = tuple(item.high - item.low for item in rows[:-1][-20:])
    recent_range = sum(recent_ranges, ZERO) / Decimal(len(recent_ranges))
    volume_ratio = (
        relative_volume(rows, min(volume_window, len(rows) - 1))
        if len(rows) > 2
        else None
    )
    geometry = candle_geometry(
        current,
        atr_value=atr_value,
        recent_range=recent_range,
        relative_volume_value=volume_ratio,
    )
    patterns: list[CandlestickPattern] = []
    if geometry.body_to_range_ratio <= Decimal("0.1"):
        patterns.append(CandlestickPattern.INDECISION)
    if max(geometry.upper_wick_ratio, geometry.lower_wick_ratio) >= Decimal("0.6"):
        patterns.append(CandlestickPattern.REJECTION)
    if geometry.body_to_range_ratio >= Decimal("0.65"):
        patterns.append(CandlestickPattern.STRONG_CONTINUATION)
    if current.high < previous.high and current.low > previous.low:
        patterns.append(CandlestickPattern.INSIDE_BAR)
    if current.high > previous.high and current.low < previous.low:
        patterns.append(CandlestickPattern.OUTSIDE_BAR)
    if (
        previous.close < previous.open
        and current.close > current.open
        and current.open <= previous.close
        and current.close >= previous.open
    ):
        patterns.append(CandlestickPattern.BULLISH_ENGULFING)
    if (
        previous.close > previous.open
        and current.close < current.open
        and current.open >= previous.close
        and current.close <= previous.open
    ):
        patterns.append(CandlestickPattern.BEARISH_ENGULFING)
    if geometry.range_vs_recent_range is not None:
        if geometry.range_vs_recent_range >= Decimal("1.5"):
            patterns.append(CandlestickPattern.RANGE_EXPANSION)
        elif geometry.range_vs_recent_range <= Decimal("0.6"):
            patterns.append(CandlestickPattern.RANGE_CONTRACTION)
    if geometry.range_vs_atr is not None and geometry.range_vs_atr >= Decimal("1.8"):
        patterns.append(CandlestickPattern.EXTENDED)
    unique_patterns = tuple(dict.fromkeys(patterns))
    return CandlestickEvidence(
        geometry=geometry,
        patterns=unique_patterns,
        reason_codes=tuple(f"CANDLE_{pattern.value}" for pattern in unique_patterns)
        or ("CANDLE_GEOMETRY_ONLY",),
    )


def detect_chart_pattern(
    candles: Sequence[OHLCVCandle],
    *,
    timeframe: str,
    snapshot_id: str,
    decision_time: datetime,
    pivot_confirmation_bars: int = 3,
    expiry_bars: int = 20,
) -> ChartPatternObservation | None:
    """Detect a small double-top/bottom family without future pivot leakage."""
    _require_aware(decision_time, "pattern decision time")
    if timeframe not in TIMEFRAME_DURATIONS:
        raise ValueError("chart-pattern timeframe is unsupported")
    if pivot_confirmation_bars < 1 or expiry_bars < pivot_confirmation_bars:
        raise ValueError("chart-pattern confirmation or expiry is invalid")
    duration = TIMEFRAME_DURATIONS[timeframe]
    rows = tuple(
        candle for candle in candles if candle.timestamp + duration <= decision_time
    )
    if len(rows) < 12:
        return None
    midpoint = len(rows) // 2
    first_half = rows[:midpoint]
    second_half = rows[midpoint:]
    first_high = max(enumerate(first_half), key=lambda item: item[1].high)
    second_high = max(
        enumerate(second_half, start=midpoint), key=lambda item: item[1].high
    )
    first_low = min(enumerate(first_half), key=lambda item: item[1].low)
    second_low = min(
        enumerate(second_half, start=midpoint), key=lambda item: item[1].low
    )
    tolerance = atr(rows, min(14, len(rows) - 1)) * Decimal("0.35")
    if abs(first_high[1].high - second_high[1].high) <= tolerance:
        pattern_type = "DOUBLE_TOP"
        bias = CandleDirection.BEARISH
        anchors = (first_high, second_high)
        neckline = min(item.low for item in rows[first_high[0] : second_high[0] + 1])
        confirmed = rows[-1].close < neckline
        boundary_price = max(item[1].high for item in anchors) + tolerance
        failed = rows[-1].close > boundary_price
        boundary = (("neckline", str(neckline)), ("tolerance", str(tolerance)))
        confirmation = f"CLOSE_BELOW={neckline}"
        invalidation = f"CLOSE_ABOVE={boundary_price}"
    elif abs(first_low[1].low - second_low[1].low) <= tolerance:
        pattern_type = "DOUBLE_BOTTOM"
        bias = CandleDirection.BULLISH
        anchors = (first_low, second_low)
        neckline = max(item.high for item in rows[first_low[0] : second_low[0] + 1])
        confirmed = rows[-1].close > neckline
        boundary_price = min(item[1].low for item in anchors) - tolerance
        failed = rows[-1].close < boundary_price
        boundary = (("neckline", str(neckline)), ("tolerance", str(tolerance)))
        confirmation = f"CLOSE_ABOVE={neckline}"
        invalidation = f"CLOSE_BELOW={boundary_price}"
    else:
        return None
    second_index, second_anchor = anchors[1]
    pivot_available_time = second_anchor.timestamp + duration * (
        pivot_confirmation_bars + 1
    )
    bars_after_anchor = len(rows) - second_index - 1
    if bars_after_anchor > expiry_bars:
        state = ChartPatternLifecycleState.EXPIRED
    elif (
        decision_time < pivot_available_time
        or bars_after_anchor < pivot_confirmation_bars
    ):
        state = ChartPatternLifecycleState.FORMING
    elif failed:
        state = ChartPatternLifecycleState.INVALIDATED
    elif confirmed:
        state = ChartPatternLifecycleState.CONFIRMED
    elif bars_after_anchor == expiry_bars:
        state = ChartPatternLifecycleState.FAILED
    else:
        state = ChartPatternLifecycleState.POTENTIAL
    anchor_points = tuple(
        (
            f"anchor_{index + 1}",
            candle.timestamp,
            candle.high if pattern_type == "DOUBLE_TOP" else candle.low,
        )
        for index, (_row_index, candle) in enumerate(anchors)
    )
    payload = "|".join(
        (
            snapshot_id,
            timeframe,
            pattern_type,
            *(item[1].isoformat() for item in anchor_points),
        )
    )
    return ChartPatternObservation(
        pattern_id=f"pattern:{sha256(payload.encode('utf-8')).hexdigest()[:16]}",
        pattern_type=pattern_type,
        directional_bias=bias,
        timeframe=timeframe,
        start_time=rows[0].timestamp,
        last_observation_time=decision_time,
        pivot_available_time=pivot_available_time,
        anchor_points=anchor_points,
        boundary_model=boundary,
        formation_progress=min(
            ONE, Decimal(bars_after_anchor) / Decimal(pivot_confirmation_bars)
        ),
        confirmation_condition=confirmation,
        invalidation_condition=invalidation,
        state=state,
        evidence_refs=(f"snapshot:{snapshot_id}", "CLOSED_CANDLE_GEOMETRY"),
    )


def opportunity_event_id(
    opportunity_id: str,
    event_type: OpportunityEventType,
    event_time: datetime,
    snapshot_id: str,
) -> str:
    payload = "|".join(
        (opportunity_id, event_type.value, event_time.isoformat(), snapshot_id)
    )
    return f"opportunity-event:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _timeframe_bias(
    candles: Sequence[OHLCVCandle], vote: float | None
) -> CandleDirection:
    if vote is not None:
        if vote > 0:
            return CandleDirection.BULLISH
        if vote < 0:
            return CandleDirection.BEARISH
        return CandleDirection.NEUTRAL
    if len(candles) < 2:
        return CandleDirection.NEUTRAL
    return (
        CandleDirection.BULLISH
        if candles[-1].close > candles[-2].close
        else CandleDirection.BEARISH
        if candles[-1].close < candles[-2].close
        else CandleDirection.NEUTRAL
    )


def _alignment_state(
    biases: Mapping[str, CandleDirection], has_blockers: bool
) -> MultiTimeframeAlignmentState:
    if has_blockers:
        return MultiTimeframeAlignmentState.INSUFFICIENT_DATA
    higher, setup, trigger = biases["4h"], biases["1h"], biases["15m"]
    directional = {CandleDirection.BULLISH, CandleDirection.BEARISH}
    if higher in directional and higher is setup and setup is trigger:
        return MultiTimeframeAlignmentState.ALIGNED
    if higher in directional and higher is setup and trigger is CandleDirection.NEUTRAL:
        return MultiTimeframeAlignmentState.PARTIALLY_ALIGNED
    if setup in directional and setup is trigger and higher is not setup:
        return MultiTimeframeAlignmentState.TRANSITIONAL
    if CandleDirection.BULLISH in {
        higher,
        setup,
        trigger,
    } and CandleDirection.BEARISH in {higher, setup, trigger}:
        return MultiTimeframeAlignmentState.CONFLICTING
    return MultiTimeframeAlignmentState.UNKNOWN


def _candle_id(snapshot_id: str, timeframe: str, candle: OHLCVCandle) -> str:
    payload = f"{snapshot_id}|{timeframe}|{candle.timestamp.isoformat()}"
    return f"candle:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _valid_lifecycle_transition(
    current: OpportunityLifecycleState,
    target: OpportunityLifecycleState,
) -> bool:
    if current is target:
        return True
    terminal = {
        OpportunityLifecycleState.INVALIDATED,
        OpportunityLifecycleState.EXPIRED,
        OpportunityLifecycleState.CLOSED,
        OpportunityLifecycleState.REJECTED,
    }
    if current in terminal:
        return False
    progression = {
        OpportunityLifecycleState.DISCOVERED: 0,
        OpportunityLifecycleState.NEW: 0,
        OpportunityLifecycleState.WATCH_ONLY: 0,
        OpportunityLifecycleState.SETUP_FORMING: 1,
        OpportunityLifecycleState.DEVELOPING: 2,
        OpportunityLifecycleState.RESEARCH_CANDIDATE: 2,
        OpportunityLifecycleState.CONFIRMATION_PENDING: 3,
        OpportunityLifecycleState.QUALIFIED: 4,
        OpportunityLifecycleState.CONFIRMED: 5,
        OpportunityLifecycleState.VALIDATION_PENDING: 6,
        OpportunityLifecycleState.PAPER_ELIGIBLE: 7,
        OpportunityLifecycleState.VIRTUAL_ELIGIBLE: 8,
    }
    terminal_targets = {
        OpportunityLifecycleState.BLOCKED,
        OpportunityLifecycleState.REJECTED,
        OpportunityLifecycleState.INVALIDATED,
        OpportunityLifecycleState.EXPIRED,
        OpportunityLifecycleState.CLOSED,
    }
    if target in terminal_targets:
        return True
    if current is OpportunityLifecycleState.BLOCKED:
        return target is OpportunityLifecycleState.WATCH_ONLY
    return progression.get(target, -1) >= progression.get(current, 100)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_unique_nonblank(values: Sequence[str], name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blank values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


__all__ = (
    "PRIMARY_OPPORTUNITY_TIMEFRAMES",
    "TIMEFRAME_DURATIONS",
    "CandleDirection",
    "CandleGeometry",
    "CandlestickEvidence",
    "CandlestickPattern",
    "ChartPatternLifecycleState",
    "ChartPatternObservation",
    "MultiTimeframeAlignmentState",
    "MultiTimeframeDiagnostic",
    "OpportunityEventType",
    "OpportunityLifecycleEvent",
    "OpportunityLifecycleLedger",
    "TimeframeCandleReference",
    "analyze_candlestick",
    "build_multi_timeframe_diagnostic",
    "candle_geometry",
    "detect_chart_pattern",
    "opportunity_event_id",
)

"""Confirmed-swing market-structure analysis with no look-ahead authority."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.indicators import atr
from ai4binance.intelligence.contracts import (
    ConfirmedSwing,
    ScenarioDirection,
    StructureEvent,
    StructureState,
    SwingKind,
    TimeframeStructureEvidence,
)
from ai4binance.schemas import OHLCVCandle

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MarketStructureEngine:
    """Build a deterministic confirmed-swing graph for one timeframe."""

    pivot_left: int = 2
    pivot_right: int = 2
    minimum_candles: int = 20

    @staticmethod
    def alternating_swings(
        swings: tuple[ConfirmedSwing, ...],
    ) -> tuple[ConfirmedSwing, ...]:
        """Collapse same-side pivots without inventing intrabar ordering."""
        result: list[ConfirmedSwing] = []
        timestamps = Counter(s.occurred_at for s in swings)
        ambiguous = {stamp for stamp, count in timestamps.items() if count > 1}
        for swing in swings:
            if swing.occurred_at in ambiguous:
                continue
            if result and swing.kind is result[-1].kind:
                more_extreme = (
                    swing.price > result[-1].price
                    if swing.kind is SwingKind.HIGH
                    else swing.price < result[-1].price
                )
                if more_extreme:
                    result[-1] = swing
            else:
                result.append(swing)
        return tuple(result)

    def __post_init__(self) -> None:
        if self.pivot_left < 1 or self.pivot_right < 1:
            raise ValueError("pivot confirmation windows must be positive")
        if self.minimum_candles < self.pivot_left + self.pivot_right + 3:
            raise ValueError("minimum_candles is too small for pivot confirmation")

    def analyze(
        self,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        *,
        as_of: datetime | None = None,
    ) -> TimeframeStructureEvidence:
        """Return confirmed structure or an explicit windowed fallback."""
        if not timeframe.strip():
            raise ValueError("structure timeframe cannot be empty")
        duration = timeframe_duration(timeframe)
        if as_of is not None:
            if as_of.utcoffset() is None:
                raise ValueError("structure as_of must be timezone-aware")
            candles = tuple(c for c in candles if c.timestamp + duration <= as_of)
        if len(candles) < self.minimum_candles:
            raise ValueError("market structure history is insufficient")
        if any(
            current.timestamp <= previous.timestamp
            for previous, current in pairwise(candles)
        ):
            raise ValueError("market structure candles must be strictly chronological")
        swings = self._confirmed_swings(timeframe, candles)
        state, method, warnings = self._state(candles, swings)
        events = self._events(timeframe, candles, swings, state)
        invalidation = self._invalidation(swings, state)
        sample = candles[-self.minimum_candles :]
        confidence = self._confidence(state, method, swings)
        return TimeframeStructureEvidence(
            timeframe=timeframe,
            state=state,
            method=method,
            range_low=min(item.low for item in sample),
            range_high=max(item.high for item in sample),
            invalidation_level=invalidation,
            confidence=confidence,
            swings=swings,
            events=events,
            reason_codes=("MARKET_STRUCTURE_EVALUATED",),
            warnings=warnings,
        )

    def _confirmed_swings(
        self,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
    ) -> tuple[ConfirmedSwing, ...]:
        raw: list[tuple[int, SwingKind, Decimal]] = []
        stop = len(candles) - self.pivot_right
        for index in range(self.pivot_left, stop):
            current = candles[index]
            left = candles[index - self.pivot_left : index]
            right = candles[index + 1 : index + self.pivot_right + 1]
            if current.high > max(item.high for item in left) and current.high >= max(
                item.high for item in right
            ):
                raw.append((index, SwingKind.HIGH, current.high))
            if current.low < min(item.low for item in left) and current.low <= min(
                item.low for item in right
            ):
                raw.append((index, SwingKind.LOW, current.low))
        previous: dict[SwingKind, Decimal] = {}
        swings: list[ConfirmedSwing] = []
        ordered = sorted(raw, key=lambda item: (item[0], item[1].value))
        for index, kind, price in ordered:
            confirmation = index + self.pivot_right
            history = candles[max(0, confirmation - 14) : confirmation + 1]
            volatility = atr(history, min(14, len(history) - 1))
            prior = previous.get(kind)
            label = self._label(kind, price, prior)
            significance = (
                abs(price - prior) / volatility
                if prior is not None and volatility > ZERO
                else ZERO
            )
            swings.append(
                ConfirmedSwing(
                    timeframe=timeframe,
                    kind=kind,
                    candle_index=index,
                    occurred_at=candles[index].timestamp,
                    available_at=candles[index + self.pivot_right].timestamp
                    + timeframe_duration(timeframe),
                    price=price,
                    label=label,
                    atr_significance=significance,
                )
            )
            previous[kind] = price
        return tuple(swings)

    def _state(
        self,
        candles: tuple[OHLCVCandle, ...],
        swings: tuple[ConfirmedSwing, ...],
    ) -> tuple[StructureState, str, tuple[str, ...]]:
        highs = tuple(item for item in swings if item.kind is SwingKind.HIGH)
        lows = tuple(item for item in swings if item.kind is SwingKind.LOW)
        if len(highs) >= 2 and len(lows) >= 2:
            high_label = highs[-1].label
            low_label = lows[-1].label
            if high_label == "HH" and low_label == "HL":
                return StructureState.BULLISH, "CONFIRMED_SWING_GRAPH", ()
            if high_label == "LH" and low_label == "LL":
                return StructureState.BEARISH, "CONFIRMED_SWING_GRAPH", ()
            if high_label == "EH" and low_label == "EL":
                return StructureState.RANGE, "CONFIRMED_SWING_GRAPH", ()
            return StructureState.TRANSITION, "CONFIRMED_SWING_GRAPH", ()
        previous = candles[-20:-10]
        recent = candles[-10:]
        previous_high = max(item.high for item in previous)
        previous_low = min(item.low for item in previous)
        recent_high = max(item.high for item in recent)
        recent_low = min(item.low for item in recent)
        warning = ("CONFIRMED_SWING_PAIR_INCOMPLETE",)
        if recent_high > previous_high and recent_low > previous_low:
            return StructureState.BULLISH, "WINDOWED_STRUCTURE_FALLBACK", warning
        if recent_high < previous_high and recent_low < previous_low:
            return StructureState.BEARISH, "WINDOWED_STRUCTURE_FALLBACK", warning
        if recent_high == previous_high and recent_low == previous_low:
            return StructureState.RANGE, "WINDOWED_STRUCTURE_FALLBACK", warning
        return StructureState.TRANSITION, "WINDOWED_STRUCTURE_FALLBACK", warning

    def _events(
        self,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        swings: tuple[ConfirmedSwing, ...],
        state: StructureState,
    ) -> tuple[StructureEvent, ...]:
        del state
        events: list[StructureEvent] = []
        consumed: set[tuple[SwingKind, datetime]] = set()
        duration = timeframe_duration(timeframe)
        for index in range(self.minimum_candles, len(candles)):
            candle, previous = candles[index], candles[index - 1]
            visible = tuple(s for s in swings if s.available_at <= candle.timestamp)
            prior_state, _, _ = self._state(candles[:index], visible)
            for kind, direction in (
                (SwingKind.HIGH, ScenarioDirection.LONG),
                (SwingKind.LOW, ScenarioDirection.SHORT),
            ):
                pivot = next((s for s in reversed(visible) if s.kind is kind), None)
                if pivot is None or (kind, pivot.occurred_at) in consumed:
                    continue
                crossed = (
                    previous.close <= pivot.price < candle.close
                    if kind is SwingKind.HIGH
                    else previous.close >= pivot.price > candle.close
                )
                if not crossed:
                    continue
                aligned = (
                    prior_state is StructureState.BULLISH
                    if kind is SwingKind.HIGH
                    else prior_state is StructureState.BEARISH
                )
                suffix = "UP" if kind is SwingKind.HIGH else "DOWN"
                event_type = f"{'BOS' if aligned else 'CHOCH'}_{suffix}"
                consumed.add((kind, pivot.occurred_at))
                events.append(
                    StructureEvent(
                        event_type=event_type,
                        direction=direction,
                        level=pivot.price,
                        occurred_at=candle.timestamp + duration,
                        evidence_ref=f"market_structure:{timeframe}:{event_type}:{pivot.occurred_at.isoformat()}",
                    )
                )
        return tuple(events)

    @staticmethod
    def _invalidation(
        swings: tuple[ConfirmedSwing, ...],
        state: StructureState,
    ) -> Decimal | None:
        if state is StructureState.BULLISH:
            return next(
                (item.price for item in reversed(swings) if item.kind is SwingKind.LOW),
                None,
            )
        if state is StructureState.BEARISH:
            return next(
                (
                    item.price
                    for item in reversed(swings)
                    if item.kind is SwingKind.HIGH
                ),
                None,
            )
        return None

    @staticmethod
    def _label(
        kind: SwingKind,
        price: Decimal,
        previous: Decimal | None,
    ) -> str:
        if previous is None:
            return "INITIAL_HIGH" if kind is SwingKind.HIGH else "INITIAL_LOW"
        if kind is SwingKind.HIGH:
            return "HH" if price > previous else "LH" if price < previous else "EH"
        return "HL" if price > previous else "LL" if price < previous else "EL"

    @staticmethod
    def _confidence(
        state: StructureState,
        method: str,
        swings: tuple[ConfirmedSwing, ...],
    ) -> float:
        if method == "WINDOWED_STRUCTURE_FALLBACK":
            return 0.5 if state is not StructureState.TRANSITION else 0.35
        base = min(0.9, 0.55 + len(swings) * 0.025)
        return round(base if state is not StructureState.TRANSITION else base * 0.75, 6)

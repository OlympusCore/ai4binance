"""Deterministic dynamic trend-zone projection from canonical evidence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.indicators import atr
from ai4binance.intelligence.contracts import (
    SwingKind,
    TimeframeStructureEvidence,
    TrendGeometryEvidence,
    TrendGeometryState,
)
from ai4binance.schemas import (
    AgentResult,
    MarketSnapshot,
    OHLCVCandle,
    is_usable_agent_result,
)

ZERO = Decimal("0")
TIMEFRAME_PRIORITY = ("1d", "4h", "1h", "15m", "5m")


@dataclass(frozen=True, slots=True)
class TrendGeometryEngine:
    """Build one auditable dynamic zone without becoming direction authority."""

    window_bars: int = 30

    def __post_init__(self) -> None:
        if self.window_bars < 20:
            raise ValueError("trend geometry window must be at least 20 bars")

    def build(
        self,
        snapshot: MarketSnapshot,
        structures: tuple[TimeframeStructureEvidence, ...],
        result: AgentResult | None,
    ) -> tuple[TrendGeometryEvidence, ...]:
        if result is None or not is_usable_agent_result(result) or result.blockers:
            return ()
        if (
            result.snapshot_id != snapshot.snapshot_id
            or result.timestamp != snapshot.created_at
            or result.symbol != snapshot.symbol
            or result.agent_name != "trend_channel"
        ):
            return ()
        pivot_lines = tuple(
            line
            for structure in structures
            for kind in (SwingKind.LOW, SwingKind.HIGH)
            if (line := self._pivot_line(snapshot, structure, kind)) is not None
        )
        if pivot_lines:
            return pivot_lines
        timeframe = self._source_timeframe(snapshot, result.calculation_metadata)
        if timeframe is None:
            return ()
        candles = tuple(
            c
            for c in snapshot.ohlcv_by_timeframe.get(timeframe, ())
            if c.timestamp + timeframe_duration(timeframe) <= snapshot.created_at
        )
        if len(candles) < self.window_bars:
            return ()
        recent = candles[-self.window_bars :]
        # Hold out both lifecycle bars so a break cannot refit its own baseline.
        training = recent[:-2]
        slope = (training[-1].close - training[0].close) / Decimal(len(training) - 1)
        volatility = atr(training, 14)
        width = volatility
        if width <= ZERO:
            return ()
        intercept = recent[0].close
        errors = tuple(
            abs(candle.close - (intercept + slope * Decimal(index)))
            for index, candle in enumerate(training)
        )
        mean_error = sum(errors, ZERO) / Decimal(len(errors))
        normalized_error = mean_error / volatility if volatility > ZERO else ZERO
        touch_count = sum(1 for error in errors if error <= width)
        state, break_state, retest_state = self._lifecycle(
            recent[-2].close,
            recent[-1].close,
            intercept + slope * Decimal(len(recent) - 2),
            intercept + slope * Decimal(len(recent) - 1),
            width,
            slope,
        )
        anchors = self._anchors(training, None)
        confidence = min(result.confidence, self._fit_confidence(normalized_error))
        return (
            TrendGeometryEvidence(
                source_timeframe=timeframe,
                slope=slope,
                channel_width=width,
                state=state.value,
                touch_quality=self._touch_quality(touch_count, len(training)),
                evidence_ref="trend_channel:DYNAMIC_ZONE",
                confidence=confidence,
                anchor_points=anchors,
                intercept=intercept,
                touch_count=touch_count,
                atr_normalized_error=normalized_error,
                age_bars=len(recent) - 1,
                break_state=break_state,
                retest_state=retest_state,
                compression_state=self._compression_state(recent),
                acceleration_state=self._acceleration_state(recent),
                atr_normalized_slope=slope / volatility,
                blockers=("CONFIRMED_TREND_ANCHORS_UNAVAILABLE",),
            ),
        )

    def _pivot_line(
        self,
        snapshot: MarketSnapshot,
        structure: TimeframeStructureEvidence,
        kind: SwingKind,
    ) -> TrendGeometryEvidence | None:
        duration = timeframe_duration(structure.timeframe)
        candles = tuple(
            c
            for c in snapshot.ohlcv_by_timeframe.get(structure.timeframe, ())
            if c.timestamp + duration <= snapshot.created_at
        )
        if len(candles) < self.window_bars:
            return None
        pivots = tuple(
            s
            for s in structure.swings
            if s.kind is kind and s.available_at <= candles[-2].timestamp
        )
        if len(pivots) < 2:
            return None
        first, second = pivots[-2:]
        span = Decimal(str((second.occurred_at - first.occurred_at) / duration))
        if span <= ZERO:
            return None
        slope = (second.price - first.price) / span
        training = tuple(
            c for c in candles if c.timestamp + duration <= second.available_at
        )
        if len(training) < 15:
            return None
        width = atr(training[-self.window_bars :], 14)
        if width <= ZERO:
            return None
        observed = tuple(c for c in candles if c.timestamp >= first.occurred_at)
        centers = tuple(
            first.price
            + slope * Decimal(str((c.timestamp - first.occurred_at) / duration))
            for c in observed
        )
        sign = Decimal("1") if kind is SwingKind.LOW else Decimal("-1")
        distances = tuple(
            sign * (c.close - center)
            for c, center in zip(observed, centers, strict=True)
        )
        broken = tuple(
            i
            for i, (c, distance) in enumerate(zip(observed, distances, strict=True))
            if c.timestamp >= second.available_at and distance < -width
        )
        current = distances[-1]
        if broken and current < -width:
            state, break_state, retest = (
                TrendGeometryState.BREAK,
                "BROKEN",
                "NOT_RETESTED",
            )
        elif broken and abs(current) <= width:
            state, break_state, retest = (
                TrendGeometryState.RETEST,
                "BROKEN",
                "RETEST_PENDING",
            )
        elif broken:
            state, break_state, retest = (
                TrendGeometryState.FALSE_BREAK,
                "FALSE_BREAK",
                "RECLAIMED",
            )
        else:
            state, break_state, retest = (
                TrendGeometryState.VALID,
                "UNBROKEN",
                "NOT_RETESTED",
            )
        contacts = tuple(
            c.low <= center + width and c.high >= center - width
            for c, center in zip(observed, centers, strict=True)
        )
        touches = sum(
            touch and (i == 0 or not contacts[i - 1])
            for i, touch in enumerate(contacts)
        )
        errors = tuple(
            abs((c.low if kind is SwingKind.LOW else c.high) - center)
            for c, center in zip(observed, centers, strict=True)
        )
        error = sum(errors, ZERO) / Decimal(len(errors)) / width
        identity = (
            f"{snapshot.market_type}|{snapshot.symbol}|{structure.timeframe}|{kind}|"
            f"{first.occurred_at.isoformat()}:{first.price}|"
            f"{second.occurred_at.isoformat()}:{second.price}"
        )
        geometry_id = "trend:" + sha256(identity.encode()).hexdigest()[:20]
        return TrendGeometryEvidence(
            source_timeframe=structure.timeframe,
            slope=slope,
            channel_width=width,
            state=state.value,
            touch_quality=self._touch_quality(touches, len(observed)),
            evidence_ref=geometry_id,
            confidence=structure.confidence,
            anchor_points=(
                (first.occurred_at, first.price),
                (second.occurred_at, second.price),
            ),
            intercept=first.price,
            touch_count=touches,
            atr_normalized_error=error,
            age_bars=max(
                0,
                int(
                    (candles[-1].timestamp + duration - second.available_at) / duration
                ),
            ),
            break_state=break_state,
            retest_state=retest,
            compression_state=self._compression_state(candles[-self.window_bars :]),
            acceleration_state=self._acceleration_state(candles[-self.window_bars :]),
            geometry_id=geometry_id,
            method="CONFIRMED_PIVOT_SUPPORT"
            if kind is SwingKind.LOW
            else "CONFIRMED_PIVOT_RESISTANCE",
            atr_normalized_slope=slope / width,
        )

    @staticmethod
    def _source_timeframe(
        snapshot: MarketSnapshot,
        metadata: Mapping[str, object],
    ) -> str | None:
        explicit = metadata.get("source_timeframe")
        if (
            isinstance(explicit, str)
            and explicit in snapshot.timeframes
            and len(snapshot.ohlcv_by_timeframe.get(explicit, ())) >= 30
        ):
            return explicit
        return next(
            (
                timeframe
                for timeframe in TIMEFRAME_PRIORITY
                if len(snapshot.ohlcv_by_timeframe.get(timeframe, ())) >= 55
            ),
            None,
        )

    @staticmethod
    def _lifecycle(
        previous_close: Decimal,
        current_close: Decimal,
        previous_center: Decimal,
        current_center: Decimal,
        width: Decimal,
        slope: Decimal,
    ) -> tuple[TrendGeometryState, str, str]:
        previous_outside = abs(previous_close - previous_center) > width
        current_outside = abs(current_close - current_center) > width
        if previous_outside and not current_outside:
            return TrendGeometryState.RETEST, "FALSE_BREAK", "RETEST_CONFIRMED"
        if current_outside:
            return TrendGeometryState.BREAK, "BROKEN", "NOT_RETESTED"
        if slope == ZERO:
            return TrendGeometryState.SIDEWAYS, "UNBROKEN", "NOT_RETESTED"
        if abs(current_close - current_center) > width * Decimal("0.75"):
            return TrendGeometryState.WEAKENING, "UNBROKEN", "NOT_RETESTED"
        return TrendGeometryState.VALID, "UNBROKEN", "NOT_RETESTED"

    @staticmethod
    def _anchors(
        candles: tuple[OHLCVCandle, ...],
        structure: TimeframeStructureEvidence | None,
    ) -> tuple[tuple[datetime, Decimal], ...]:
        if structure is not None and len(structure.swings) >= 2:
            return tuple(
                (swing.occurred_at, swing.price) for swing in structure.swings[-2:]
            )
        return (
            (candles[0].timestamp, candles[0].close),
            (candles[-1].timestamp, candles[-1].close),
        )

    @staticmethod
    def _touch_quality(touch_count: int, total: int) -> str:
        ratio = touch_count / total
        return "HIGH" if ratio >= 0.7 else "MEDIUM" if ratio >= 0.4 else "LOW"

    @staticmethod
    def _fit_confidence(normalized_error: Decimal) -> float:
        return float(max(ZERO, min(Decimal("1"), Decimal("1") - normalized_error)))

    @staticmethod
    def _compression_state(candles: tuple[OHLCVCandle, ...]) -> str:
        midpoint = len(candles) // 2
        first = atr(candles[:midpoint], min(14, midpoint - 1))
        second = atr(candles[midpoint:], min(14, len(candles[midpoint:]) - 1))
        if first <= ZERO:
            return "NOT_MEASURED"
        ratio = second / first
        if ratio < Decimal("0.8"):
            return "COMPRESSING"
        if ratio > Decimal("1.2"):
            return "EXPANDING"
        return "STABLE"

    @staticmethod
    def _acceleration_state(candles: tuple[OHLCVCandle, ...]) -> str:
        midpoint = len(candles) // 2
        first_slope = (candles[midpoint - 1].close - candles[0].close) / Decimal(
            midpoint - 1
        )
        second_slope = (candles[-1].close - candles[midpoint].close) / Decimal(
            len(candles) - midpoint - 1
        )
        if abs(second_slope) > abs(first_slope) * Decimal("1.5"):
            return "ACCELERATING"
        if abs(second_slope) * Decimal("1.5") < abs(first_slope):
            return "DECELERATING"
        return "STABLE"

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None

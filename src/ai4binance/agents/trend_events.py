"""Research-only deterministic trend event intelligence."""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.registry import AgentDefinition
from ai4binance.indicators import (
    closes,
    confirmed_swings,
    cross_over,
    cross_under,
    ema,
    supertrend,
)
from ai4binance.schemas import AgentResult, AgentStatus, MarketSnapshot, OHLCVCandle


class TrendEventsAgent(BaseAgent):
    """Combine Supertrend state, EMA cross events and confirmed swing slope."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        observations: list[
            tuple[str, int, Decimal, tuple[str, ...], Decimal | None]
        ] = []
        for timeframe in self.definition.supported_timeframes:
            candles = snapshot.ohlcv_by_timeframe.get(timeframe, ())
            if len(candles) >= 15:
                observations.append(self._observe(timeframe, candles))
        if not observations:
            return self.result(
                snapshot,
                status=AgentStatus.INSUFFICIENT_DATA,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("TREND_EVENTS_WARMUP_MISSING",),
                reason_codes=("INSUFFICIENT_CLOSED_CANDLES",),
            )
        vote = sum(item[1] for item in observations) / len(observations)
        setups = tuple(event for item in observations for event in item[3])
        evidence = tuple(
            f"{timeframe}:SUPERTREND_{'BULLISH' if direction > 0 else 'BEARISH'}"
            for timeframe, direction, _, _, _ in observations
        )
        metadata = {
            timeframe: {
                "supertrend_direction": direction,
                "supertrend_band": str(band),
                "events": events,
                "confirmed_trendline_slope": str(slope) if slope is not None else None,
                "atr_period": 14,
                "price_source": "OHLC4",
                "multiplier": "2",
            }
            for timeframe, direction, band, events, slope in observations
        }
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=max(-1.0, min(1.0, vote)),
            score=50.0 + (abs(vote) * 30.0),
            confidence=min(0.75, 0.35 + (abs(vote) * 0.3)),
            evidence=evidence,
            detected_setups=setups,
            regime_compatibility="TREND_OR_TRANSITION",
            warnings=("RESEARCH_ONLY_OOS_VALIDATION_REQUIRED",),
            reason_codes=("CLOSED_CANDLE_TREND_EVENTS",),
            calculation_metadata=metadata,
        )

    @staticmethod
    def _observe(
        timeframe: str,
        candles: Sequence[OHLCVCandle],
    ) -> tuple[str, int, Decimal, tuple[str, ...], Decimal | None]:
        trend = supertrend(candles, period=14, multiplier=Decimal("2"))[-1]
        events: list[str] = []
        values = closes(candles)
        if len(values) >= 201:
            fast_previous = ema(values[:-1], 50)
            slow_previous = ema(values[:-1], 200)
            fast_current = ema(values, 50)
            slow_current = ema(values, 200)
            if cross_over(fast_previous, slow_previous, fast_current, slow_current):
                events.append(f"GOLDEN_CROSS:{timeframe}")
            elif cross_under(fast_previous, slow_previous, fast_current, slow_current):
                events.append(f"DEATH_CROSS:{timeframe}")
        swings = confirmed_swings(candles)
        highs = tuple(point for point in swings if point.kind == "HIGH")
        slope = None
        if len(highs) >= 2:
            left, right = highs[-2:]
            slope = (right.price - left.price) / Decimal(right.index - left.index)
        return timeframe, trend.direction, trend.band, tuple(events), slope


def build_trend_events_agent(definition: AgentDefinition) -> BaseAgent | None:
    """Return the governed trend-events implementation for its definition."""
    return TrendEventsAgent(definition) if definition.name == "trend_events" else None

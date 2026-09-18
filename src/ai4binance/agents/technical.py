"""Deterministic core technical agents backed by transparent indicators."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import fsum

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.registry import AgentDefinition
from ai4binance.indicators import atr, clamp, closes, ema, relative_volume, rsi
from ai4binance.opportunity_intelligence import (
    CandlestickPattern,
    MultiTimeframeAlignmentState,
    analyze_candlestick,
    build_multi_timeframe_diagnostic,
)
from ai4binance.schemas import AgentResult, AgentStatus, MarketSnapshot, OHLCVCandle

ZERO = Decimal("0")
ONE = Decimal("1")


def _insufficient(agent: BaseAgent, snapshot: MarketSnapshot) -> AgentResult:
    return agent.result(
        snapshot,
        status=AgentStatus.INSUFFICIENT_DATA,
        data_quality=snapshot.data_quality,
        applicable=False,
        blockers=("INDICATOR_WARMUP_INSUFFICIENT",),
        reason_codes=("INSUFFICIENT_CLOSED_CANDLES",),
    )


def _vote_from_spread(fast: Decimal, slow: Decimal, volatility: Decimal) -> float:
    denominator = volatility if volatility > ZERO else abs(slow) * Decimal("0.001")
    if denominator <= ZERO:
        return 0.0
    normalized = clamp((fast - slow) / denominator, -ONE, ONE)
    return float(normalized)


def _score_from_vote(vote: float) -> float:
    return round(min(100.0, 50.0 + (abs(vote) * 50.0)), 6)


def _available(
    snapshot: MarketSnapshot,
    minimum: int,
) -> tuple[tuple[str, tuple[OHLCVCandle, ...]], ...]:
    return tuple(
        (timeframe, tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ())))
        for timeframe in snapshot.timeframes
        if len(snapshot.ohlcv_by_timeframe.get(timeframe, ())) >= minimum
    )


@dataclass(frozen=True, slots=True)
class MovingAverageAgent(BaseAgent):
    """Evaluate deterministic EMA-20/EMA-50 direction across timeframes."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 51)
        if not available:
            return _insufficient(self, snapshot)
        votes: list[float] = []
        metrics: dict[str, object] = {}
        for timeframe, candles in available:
            close_values = closes(candles)
            fast = ema(close_values, 20)
            slow = ema(close_values, 50)
            volatility = atr(candles, 14)
            vote = _vote_from_spread(fast, slow, volatility)
            votes.append(vote)
            metrics[timeframe] = {
                "ema_20": str(fast),
                "ema_50": str(slow),
                "vote": vote,
            }
        vote = fsum(votes) / len(votes)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=_score_from_vote(vote),
            confidence=round(abs(vote), 6),
            evidence=("EMA_20_50_RELATION",),
            reason_codes=("MOVING_AVERAGE_EVALUATED",),
            calculation_metadata={"timeframes": metrics},
        )


@dataclass(frozen=True, slots=True)
class TrendAgent(BaseAgent):
    """Combine EMA state and recent directional persistence."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 51)
        if not available:
            return _insufficient(self, snapshot)
        votes: list[float] = []
        metrics: dict[str, object] = {}
        for timeframe, candles in available:
            close_values = closes(candles)
            fast = ema(close_values, 20)
            slow = ema(close_values, 50)
            volatility = atr(candles, 14)
            ema_vote = _vote_from_spread(fast, slow, volatility)
            persistence = (
                sum(
                    1 if current > previous else -1 if current < previous else 0
                    for previous, current in zip(
                        close_values[-11:-1],
                        close_values[-10:],
                        strict=True,
                    )
                )
                / 10.0
            )
            vote = (ema_vote * 0.7) + (persistence * 0.3)
            votes.append(vote)
            metrics[timeframe] = {
                "ema_vote": ema_vote,
                "persistence": persistence,
                "vote": vote,
            }
        vote = fsum(votes) / len(votes)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=_score_from_vote(vote),
            confidence=round(abs(vote), 6),
            evidence=("EMA_TREND", "DIRECTIONAL_PERSISTENCE"),
            reason_codes=("TREND_EVALUATED",),
            calculation_metadata={"timeframes": metrics},
        )


@dataclass(frozen=True, slots=True)
class MomentumAgent(BaseAgent):
    """Evaluate Wilder RSI without treating overbought/oversold as reversal."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 15)
        if not available:
            return _insufficient(self, snapshot)
        votes: list[float] = []
        warnings: list[str] = []
        metrics: dict[str, object] = {}
        for timeframe, candles in available:
            value = rsi(closes(candles), 14)
            vote = float(clamp((value - Decimal("50")) / Decimal("50"), -ONE, ONE))
            votes.append(vote)
            if value >= Decimal("70") or value <= Decimal("30"):
                warnings.append(f"MOMENTUM_EXTREME:{timeframe}")
            metrics[timeframe] = {"rsi_14": str(value), "vote": vote}
        vote = fsum(votes) / len(votes)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=_score_from_vote(vote),
            confidence=round(abs(vote), 6),
            evidence=("RSI_14",),
            warnings=tuple(warnings),
            reason_codes=("MOMENTUM_EVALUATED",),
            calculation_metadata={"timeframes": metrics},
        )


@dataclass(frozen=True, slots=True)
class VolatilityAgent(BaseAgent):
    """Measure ATR percentage as a risk-context score, not direction."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 15)
        if not available:
            return _insufficient(self, snapshot)
        ratios: list[Decimal] = []
        metrics: dict[str, object] = {}
        warnings: list[str] = []
        for timeframe, candles in available:
            value = atr(candles, 14)
            ratio = value / candles[-1].close if candles[-1].close > ZERO else ZERO
            ratios.append(ratio)
            if ratio > Decimal("0.08"):
                warnings.append(f"ABNORMAL_VOLATILITY:{timeframe}")
            metrics[timeframe] = {
                "atr_14": str(value),
                "atr_ratio": str(ratio),
            }
        mean_ratio = sum(ratios, ZERO) / Decimal(len(ratios))
        suitable = Decimal("0.001") <= mean_ratio <= Decimal("0.08")
        score = 80.0 if suitable else 35.0
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL if warnings else AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            score=score,
            confidence=0.8 if suitable else 0.35,
            evidence=("ATR_14_PERCENT",),
            warnings=tuple(warnings),
            reason_codes=("VOLATILITY_EVALUATED",),
            calculation_metadata={
                "mean_atr_ratio": str(mean_ratio),
                "timeframes": metrics,
            },
        )


@dataclass(frozen=True, slots=True)
class VolumeAgent(BaseAgent):
    """Evaluate relative volume and align it with latest price direction."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 21)
        if not available:
            return _insufficient(self, snapshot)
        votes: list[float] = []
        scores: list[float] = []
        metrics: dict[str, object] = {}
        for timeframe, candles in available:
            ratio = relative_volume(candles, 20)
            direction = (
                1.0
                if candles[-1].close > candles[-2].close
                else -1.0
                if candles[-1].close < candles[-2].close
                else 0.0
            )
            participation = min(1.0, float(ratio / Decimal("2")))
            vote = direction * participation
            votes.append(vote)
            scores.append(min(100.0, float(ratio * Decimal("50"))))
            metrics[timeframe] = {
                "relative_volume_20": str(ratio),
                "vote": vote,
            }
        vote = fsum(votes) / len(votes)
        score = fsum(scores) / len(scores)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=round(score, 6),
            confidence=round(min(1.0, score / 100.0), 6),
            evidence=("RELATIVE_VOLUME_20",),
            reason_codes=("VOLUME_EVALUATED",),
            calculation_metadata={"timeframes": metrics},
        )


@dataclass(frozen=True, slots=True)
class MarketStructureAgent(BaseAgent):
    """Classify deterministic HH/HL or LH/LL structure over two windows."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 20)
        if not available:
            return _insufficient(self, snapshot)
        votes: list[float] = []
        metrics: dict[str, object] = {}
        for timeframe, candles in available:
            sample = candles[-20:]
            previous, recent = sample[:10], sample[10:]
            previous_high = max(item.high for item in previous)
            previous_low = min(item.low for item in previous)
            recent_high = max(item.high for item in recent)
            recent_low = min(item.low for item in recent)
            if recent_high > previous_high and recent_low > previous_low:
                state, vote = "HH_HL", 1.0
            elif recent_high < previous_high and recent_low < previous_low:
                state, vote = "LH_LL", -1.0
            else:
                state, vote = "MIXED", 0.0
            votes.append(vote)
            metrics[timeframe] = {
                "structure": state,
                "previous_high": str(previous_high),
                "previous_low": str(previous_low),
                "recent_high": str(recent_high),
                "recent_low": str(recent_low),
            }
        vote = fsum(votes) / len(votes)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=75.0 if vote else 50.0,
            confidence=round(abs(vote), 6),
            evidence=("WINDOWED_SWING_STRUCTURE",),
            reason_codes=("MARKET_STRUCTURE_EVALUATED",),
            calculation_metadata={"timeframes": metrics},
        )


@dataclass(frozen=True, slots=True)
class SupportResistanceAgent(BaseAgent):
    """Return rolling structural zones without false point precision."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 20)
        if not available:
            return _insufficient(self, snapshot)
        metrics: dict[str, object] = {}
        windows: dict[str, object] = {}
        votes: list[float] = []
        for timeframe, candles in available:
            sample = candles[-min(50, len(candles)) :]
            support = min(item.low for item in sample)
            resistance = max(item.high for item in sample)
            current = sample[-1].close
            span = resistance - support
            location = (current - support) / span if span > ZERO else Decimal("0.5")
            vote = float(clamp((Decimal("0.5") - location) * Decimal("2"), -ONE, ONE))
            votes.append(vote)
            bias = (
                "NEAR_SUPPORT"
                if location <= Decimal("0.33")
                else "MID_RANGE"
                if location <= Decimal("0.67")
                else "NEAR_RESISTANCE"
            )
            metrics[timeframe] = {
                "support": str(support),
                "resistance": str(resistance),
                "current_close": str(current),
                "span": str(span),
                "range_location": str(location),
                "bias": bias,
                "window_bars": len(sample),
            }
            windows[timeframe] = len(sample)
        vote = fsum(votes) / len(votes)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=_score_from_vote(vote),
            confidence=round(abs(vote), 6),
            evidence=("ROLLING_SUPPORT_RESISTANCE",),
            reason_codes=("STRUCTURAL_LEVELS_EVALUATED",),
            calculation_metadata={
                "method": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe_count": len(metrics),
                "window_bars": windows,
                "timeframes": metrics,
            },
        )


@dataclass(frozen=True, slots=True)
class PriceActionAgent(BaseAgent):
    """Detect contextual two-candle engulfing triggers only."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        available = _available(snapshot, 2)
        detections: list[str] = []
        votes: list[float] = []
        geometry: dict[str, object] = {}
        for timeframe, candles in available:
            evidence = analyze_candlestick(candles)
            bullish = CandlestickPattern.BULLISH_ENGULFING in evidence.patterns
            bearish = CandlestickPattern.BEARISH_ENGULFING in evidence.patterns
            geometry[timeframe] = evidence.geometry.to_payload()
            if bullish:
                detections.append(f"BULLISH_ENGULFING:{timeframe}")
                votes.append(1.0)
            elif bearish:
                detections.append(f"BEARISH_ENGULFING:{timeframe}")
                votes.append(-1.0)
        if not detections:
            return self.result(
                snapshot,
                status=AgentStatus.NOT_APPLICABLE,
                data_quality=snapshot.data_quality,
                applicable=False,
                reason_codes=("NO_CONTEXTUAL_PRICE_ACTION_TRIGGER",),
            )
        vote = fsum(votes) / len(votes)
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=70.0,
            confidence=0.65,
            evidence=tuple(detections),
            detected_setups=tuple(detections),
            reason_codes=("PRICE_ACTION_TRIGGER_DETECTED",),
            calculation_metadata={
                "method": "CANONICAL_CANDLE_GEOMETRY",
                "timeframes": geometry,
            },
        )


@dataclass(frozen=True, slots=True)
class MultiTimeframeAgent(BaseAgent):
    """Measure explicit 4h context, 1h setup, and 15m trigger relationships."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        diagnostic = build_multi_timeframe_diagnostic(snapshot)
        if diagnostic.blockers:
            return self.result(
                snapshot,
                status=AgentStatus.INSUFFICIENT_DATA,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=diagnostic.blockers,
                reason_codes=("MULTI_TIMEFRAME_INCOMPLETE",),
                calculation_metadata=diagnostic.to_payload(),
            )
        references = {item.timeframe: item for item in diagnostic.candle_references}
        votes: dict[str, float] = {}
        for timeframe in ("15m", "1h", "4h"):
            reference = references[timeframe]
            candles = tuple(
                candle
                for candle in snapshot.ohlcv_by_timeframe[timeframe]
                if candle.timestamp <= reference.open_time
            )
            if len(candles) < 51:
                return _insufficient(self, snapshot)
            values = closes(candles)
            votes[timeframe] = _vote_from_spread(
                ema(values, 20),
                ema(values, 50),
                atr(candles, 14),
            )
        diagnostic = build_multi_timeframe_diagnostic(
            snapshot,
            timeframe_votes=votes,
        )
        vote = votes["4h"] * 0.5 + votes["1h"] * 0.3 + votes["15m"] * 0.2
        conflict = (
            diagnostic.alignment_status is MultiTimeframeAlignmentState.CONFLICTING
        )
        score = max(0.0, abs(vote) * 100.0 - (25.0 if conflict else 0.0))
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL if conflict else AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=round(score, 6),
            confidence=round(abs(vote), 6),
            evidence=("EMA_MULTI_TIMEFRAME_ALIGNMENT",),
            warnings=("TIMEFRAME_DIRECTION_CONFLICT",) if conflict else (),
            reason_codes=("MULTI_TIMEFRAME_EVALUATED",),
            calculation_metadata={
                **diagnostic.to_payload(),
                "timeframe_votes": votes,
                "relationship_weights": {"4h": 0.5, "1h": 0.3, "15m": 0.2},
                "conflict": conflict,
            },
        )


@dataclass(frozen=True, slots=True)
class MarketRegimeAgent(BaseAgent):
    """Classify trend/range regime from the highest available timeframe."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        selected: tuple[str, Sequence[OHLCVCandle]] | None = None
        for timeframe in ("1d", "4h", "1h", "15m"):
            candles = snapshot.ohlcv_by_timeframe.get(timeframe, ())
            if len(candles) >= 51:
                selected = timeframe, candles
                break
        if selected is None:
            return _insufficient(self, snapshot)
        timeframe, candles = selected
        values = closes(candles)
        volatility = atr(candles, 14)
        vote = _vote_from_spread(ema(values, 20), ema(values, 50), volatility)
        ratio = volatility / candles[-1].close if candles[-1].close > ZERO else ZERO
        if ratio > Decimal("0.08"):
            regime = "ABNORMAL_MARKET"
        elif vote >= 0.7:
            regime = "STRONG_UPTREND"
        elif vote > 0.2:
            regime = "WEAK_UPTREND"
        elif vote <= -0.7:
            regime = "STRONG_DOWNTREND"
        elif vote < -0.2:
            regime = "WEAK_DOWNTREND"
        elif ratio < Decimal("0.01"):
            regime = "COMPRESSION"
        else:
            regime = "RANGE"
        return self.result(
            snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=80.0,
            confidence=0.75,
            evidence=("EMA_ATR_REGIME",),
            regime_compatibility=regime,
            reason_codes=("MARKET_REGIME_CLASSIFIED",),
            calculation_metadata={
                "regime": regime,
                "source_timeframe": timeframe,
                "atr_ratio": str(ratio),
            },
        )


CORE_TECHNICAL_AGENT_TYPES: Mapping[str, type[BaseAgent]] = {
    "moving_average": MovingAverageAgent,
    "trend": TrendAgent,
    "momentum": MomentumAgent,
    "volatility": VolatilityAgent,
    "volume": VolumeAgent,
    "market_structure": MarketStructureAgent,
    "support_resistance": SupportResistanceAgent,
    "price_action": PriceActionAgent,
    "multi_timeframe": MultiTimeframeAgent,
    "market_regime": MarketRegimeAgent,
}


def build_core_technical_agent(definition: AgentDefinition) -> BaseAgent | None:
    """Return a real deterministic agent for implemented core families."""
    agent_type = CORE_TECHNICAL_AGENT_TYPES.get(definition.name)
    return agent_type(definition) if agent_type is not None else None

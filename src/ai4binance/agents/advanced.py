"""Deterministic research-only advanced technical and context agents."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from math import sqrt

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.registry import AgentDefinition
from ai4binance.indicators import atr, closes, relative_volume, rsi
from ai4binance.intelligence.patterns import (
    ElliottWaveHypothesisEngine,
    FibonacciConfluenceEngine,
    HarmonicPatternEngine,
)
from ai4binance.intelligence.trading import ScenarioEngine
from ai4binance.opportunity_intelligence import (
    CandleDirection,
    CandlestickPattern,
    analyze_candlestick,
    detect_chart_pattern,
)
from ai4binance.schemas import AgentResult, AgentStatus, MarketSnapshot, OHLCVCandle

ZERO = Decimal("0")
EXTERNAL_SNAPSHOT_FIELDS = {
    "sentiment": "sentiment_snapshot",
    "news": "news_snapshot",
    "derivatives": "derivatives_snapshot",
    "long_short": "derivatives_snapshot",
    "onchain": "onchain_snapshot",
    "whale": "onchain_snapshot",
}
EXTERNAL_MAX_AGE = {
    "news": timedelta(hours=24),
    "sentiment": timedelta(hours=24),
    "derivatives": timedelta(hours=2),
    "long_short": timedelta(hours=2),
    "whale": timedelta(hours=24),
    "onchain": timedelta(hours=24),
}
ORDER_BOOK_AGENTS = {"order_flow", "liquidity_analysis"}
ADVANCED_AGENT_NAMES = {
    "trend_channel",
    "candlestick",
    "chart_pattern",
    "fibonacci",
    "harmonic_pattern",
    "elliott_wave",
    "divergence",
    "ichimoku",
    "volume_profile",
    "order_flow",
    "liquidity_analysis",
    "smc",
    "wyckoff",
    "breakout_retest",
    "mean_reversion",
    "statistics",
    "correlation",
    "sentiment",
    "news",
    "derivatives",
    "long_short",
    "whale",
    "onchain",
}


@dataclass(frozen=True, slots=True)
class _Feature:
    vote: float
    score: float
    confidence: float
    evidence: tuple[str, ...]
    setups: tuple[str, ...] = ()
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AdvancedTechnicalAgent(BaseAgent):
    """Calculate advanced evidence without hard-gate or execution authority."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        name = self.definition.name
        if name in EXTERNAL_SNAPSHOT_FIELDS:
            return self._external(snapshot, EXTERNAL_SNAPSHOT_FIELDS[name])
        if name in ORDER_BOOK_AGENTS:
            return self._order_book(snapshot)
        candles = self._candles(snapshot)
        if candles is None:
            return self._insufficient(snapshot, "ADVANCED_OHLCV_INSUFFICIENT")
        feature = (
            self._structural_pattern(name, snapshot, prior_results)
            if name
            in {"chart_pattern", "fibonacci", "harmonic_pattern", "elliott_wave"}
            else self._calculate(name, candles, snapshot)
        )
        if feature is None:
            return self.result(
                snapshot,
                status=AgentStatus.NOT_APPLICABLE,
                data_quality=snapshot.data_quality,
                applicable=False,
                warnings=("RESEARCH_ONLY_UNVALIDATED",),
                reason_codes=("RULE_BASED_SETUP_NOT_DETECTED",),
                calculation_metadata={"method": name},
            )
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=feature.vote,
            score=feature.score,
            confidence=feature.confidence,
            evidence=feature.evidence,
            detected_setups=feature.setups,
            warnings=("RESEARCH_ONLY_UNVALIDATED",),
            reason_codes=("ADVANCED_RULE_EVALUATED",),
            calculation_metadata={
                **(feature.metadata or {}),
                "source_timeframe": next(
                    timeframe
                    for timeframe in ("1d", "4h", "1h", "15m")
                    if timeframe in self.definition.supported_timeframes
                    and len(snapshot.ohlcv_by_timeframe.get(timeframe, ())) >= 55
                ),
            },
        )

    def _structural_pattern(
        self,
        name: str,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> _Feature | None:
        """Reuse canonical confirmed structure; legacy close proxies are not inputs."""
        structures = ScenarioEngine()._structures(snapshot, prior_results)
        timeframe = next(
            (
                tf
                for tf in ("1d", "4h", "1h", "15m")
                if tf in self.definition.supported_timeframes
                and len(snapshot.ohlcv_by_timeframe.get(tf, ())) >= 55
            ),
            None,
        )
        structure = next((s for s in structures if s.timeframe == timeframe), None)
        if structure is None:
            return None
        if name == "chart_pattern":
            pattern = detect_chart_pattern(
                snapshot.ohlcv_by_timeframe[structure.timeframe],
                timeframe=structure.timeframe,
                snapshot_id=snapshot.snapshot_id,
                decision_time=snapshot.created_at,
                symbol=snapshot.symbol,
                market=snapshot.market_type,
                structure=structure,
            )
            if pattern is None:
                return None
            vote = (
                0.5
                if pattern.directional_bias is CandleDirection.BULLISH
                else -0.5
                if pattern.directional_bias is CandleDirection.BEARISH
                else 0.0
            )
            return self._feature(
                vote,
                f"RULE_BASED_{pattern.pattern_type}",
                setups=(pattern.pattern_type,),
                pattern_id=pattern.pattern_id,
                lifecycle_state=pattern.state.value,
                formation_progress=str(pattern.formation_progress),
                confirmation_condition=pattern.confirmation_condition,
                invalidation_condition=pattern.invalidation_condition,
                method="CONFIRMED_SWING_GRAPH",
            )
        detectors = {
            "fibonacci": FibonacciConfluenceEngine.detect,
            "harmonic_pattern": HarmonicPatternEngine.detect,
            "elliott_wave": ElliottWaveHypothesisEngine.detect,
        }
        metadata = detectors[name](structure)
        if metadata is None:
            return None
        raw_vote = metadata.pop("directional_vote", 0.0)
        return replace(
            self._feature(float(str(raw_vote)), str(metadata["method"])),
            metadata=metadata,
        )

    def _candles(self, snapshot: MarketSnapshot) -> tuple[OHLCVCandle, ...] | None:
        for timeframe in ("1d", "4h", "1h", "15m"):
            candles = tuple(snapshot.ohlcv_by_timeframe.get(timeframe, ()))
            if timeframe in self.definition.supported_timeframes and len(candles) >= 55:
                return candles
        return None

    def _calculate(
        self,
        name: str,
        candles: tuple[OHLCVCandle, ...],
        snapshot: MarketSnapshot,
    ) -> _Feature | None:
        handlers = {
            "trend_channel": self._trend_channel,
            "candlestick": self._candlestick,
            "chart_pattern": self._chart_pattern,
            "fibonacci": self._fibonacci,
            "harmonic_pattern": self._harmonic,
            "elliott_wave": self._elliott,
            "divergence": self._divergence,
            "ichimoku": self._ichimoku,
            "volume_profile": self._volume_profile,
            "smc": self._smc,
            "wyckoff": self._wyckoff,
            "breakout_retest": self._breakout_retest,
            "mean_reversion": self._mean_reversion,
            "statistics": self._statistics,
            "correlation": self._correlation,
        }
        handler = handlers.get(name)
        return handler(candles, snapshot) if handler is not None else None

    def _trend_channel(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature:
        recent = candles[-30:]
        slope = (recent[-1].close - recent[0].close) / Decimal(len(recent) - 1)
        volatility = atr(recent, 14)
        vote = self._bounded(slope / volatility if volatility > ZERO else ZERO)
        direction = (
            "UPTREND" if vote > 0.15 else "DOWNTREND" if vote < -0.15 else "SIDEWAYS"
        )
        return self._feature(
            vote,
            "LINEAR_CHANNEL_SLOPE",
            method="TREND_CHANNEL",
            window_bars=len(recent),
            start_close=str(recent[0].close),
            end_close=str(recent[-1].close),
            slope=str(slope),
            atr_14=str(volatility),
            channel_width=str(volatility),
            direction=direction,
        )

    def _candlestick(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature | None:
        evidence = analyze_candlestick(candles)
        bullish = CandlestickPattern.BULLISH_ENGULFING in evidence.patterns
        bearish = CandlestickPattern.BEARISH_ENGULFING in evidence.patterns
        if not bullish and not bearish:
            return None
        vote = 1.0 if bullish else -1.0
        setup = "BULLISH_ENGULFING" if bullish else "BEARISH_ENGULFING"
        return self._feature(
            vote,
            "CONTEXTUAL_ENGULFING",
            setups=(setup,),
            method="CANONICAL_CANDLE_GEOMETRY",
            geometry=evidence.geometry.to_payload(),
            pattern_family=tuple(item.value for item in evidence.patterns),
        )

    def _chart_pattern(
        self, candles: tuple[OHLCVCandle, ...], snapshot: MarketSnapshot
    ) -> _Feature | None:
        timeframe = next(
            (
                item
                for item in ("1d", "4h", "1h", "15m")
                if tuple(snapshot.ohlcv_by_timeframe.get(item, ())) == candles
            ),
            "1h",
        )
        pattern = detect_chart_pattern(
            candles,
            timeframe=timeframe,
            snapshot_id=snapshot.snapshot_id,
            decision_time=snapshot.created_at,
            symbol=snapshot.symbol,
            market=snapshot.market_type,
        )
        if pattern is None:
            return None
        vote = 0.5 if pattern.directional_bias is CandleDirection.BULLISH else -0.5
        return self._feature(
            vote,
            f"RULE_BASED_{pattern.pattern_type}",
            setups=(pattern.pattern_type,),
            pattern_id=pattern.pattern_id,
            lifecycle_state=pattern.state.value,
            pivot_available_time=pattern.pivot_available_time.isoformat(),
            formation_progress=str(pattern.formation_progress),
            confirmation_condition=pattern.confirmation_condition,
            invalidation_condition=pattern.invalidation_condition,
            evidence_refs=pattern.evidence_refs,
        )

    def _fibonacci(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature:
        recent = candles[-55:]
        low = min(candle.low for candle in recent)
        high = max(candle.high for candle in recent)
        span = high - low
        ratio = (recent[-1].close - low) / span if span > ZERO else Decimal("0.5")
        vote = self._bounded((ratio - Decimal("0.5")) * Decimal("2"))
        nearest = min(
            (Decimal("0.382"), Decimal("0.5"), Decimal("0.618")),
            key=lambda item: abs(item - ratio),
        )
        if ratio <= Decimal("0.382"):
            zone = "LOWER_RETRACEMENT_ZONE"
        elif ratio <= Decimal("0.618"):
            zone = "MID_RETRACEMENT_ZONE"
        else:
            zone = "UPPER_RETRACEMENT_ZONE"
        return self._feature(
            vote,
            "SWING_RETRACEMENT_CONTEXT",
            method="FIBONACCI_RETRACEMENT",
            window_bars=len(recent),
            swing_low=str(low),
            swing_high=str(high),
            swing_span=str(span),
            current_close=str(recent[-1].close),
            ratio=str(ratio),
            nearest_level=str(nearest),
            retracement_zone=zone,
            reference_levels=(
                "0.236",
                "0.382",
                "0.500",
                "0.618",
                "0.786",
            ),
        )

    def _harmonic(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature | None:
        points = tuple(candles[index].close for index in (-41, -31, -21, -11, -1))
        legs = tuple(abs(current - previous) for previous, current in pairwise(points))
        if min(legs) <= ZERO:
            return None
        ab_cd = legs[1] / legs[3]
        if Decimal("0.8") <= ab_cd <= Decimal("1.2"):
            vote = 0.4 if points[-1] > points[-2] else -0.4
            return self._feature(vote, "BOUNDED_ABCD_GEOMETRY", ab_cd=str(ab_cd))
        return None

    def _elliott(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature | None:
        points = tuple(candles[index].close for index in (-51, -41, -31, -21, -11, -1))
        changes = tuple(current - previous for previous, current in pairwise(points))
        bullish = all(change > ZERO for change in changes[::2]) and all(
            change < ZERO for change in changes[1::2]
        )
        bearish = all(change < ZERO for change in changes[::2]) and all(
            change > ZERO for change in changes[1::2]
        )
        if not bullish and not bearish:
            return None
        return self._feature(
            0.35 if bullish else -0.35,
            "RULE_BASED_ELLIOTT_WAVE_PROXY",
            setups=("ELLIOTT_WAVE",),
            theory="ELLIOTT_WAVE_PRINCIPLE",
            heuristic="ALTERNATING_SWINGS_PROXY",
        )

    def _divergence(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature | None:
        values = closes(candles)
        price_change = values[-1] - values[-15]
        rsi_change = rsi(values[-30:-14], 14) - rsi(values[-16:], 14)
        if price_change > ZERO and rsi_change > ZERO:
            return self._feature(-0.4, "BEARISH_PRICE_RSI_DIVERGENCE")
        if price_change < ZERO and rsi_change < ZERO:
            return self._feature(0.4, "BULLISH_PRICE_RSI_DIVERGENCE")
        return None

    def _ichimoku(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature:
        conversion = self._midpoint(candles[-9:])
        base = self._midpoint(candles[-26:])
        span_b = self._midpoint(candles[-52:])
        cloud_top = max((conversion + base) / 2, span_b)
        cloud_bottom = min((conversion + base) / 2, span_b)
        close = candles[-1].close
        vote = 0.7 if close > cloud_top else -0.7 if close < cloud_bottom else 0.0
        return self._feature(vote, "ICHIMOKU_CLOUD_LOCATION")

    def _volume_profile(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature:
        recent = candles[-50:]
        weighted = sum((candle.close * candle.volume for candle in recent), ZERO)
        volume = sum((candle.volume for candle in recent), ZERO)
        poc = weighted / volume if volume > ZERO else recent[-1].close
        volatility = atr(recent, 14)
        vote = self._bounded((recent[-1].close - poc) / volatility)
        return self._feature(vote, "VOLUME_WEIGHTED_POC_PROXY", poc=str(poc))

    def _smc(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature | None:
        current = candles[-1]
        prior = candles[-21:-1]
        low = min(candle.low for candle in prior)
        high = max(candle.high for candle in prior)
        if current.low < low < current.close:
            return self._feature(
                0.5, "RULE_BASED_LIQUIDITY_SWEEP", setups=("BULLISH_SWEEP",)
            )
        if current.high > high > current.close:
            return self._feature(
                -0.5, "RULE_BASED_LIQUIDITY_SWEEP", setups=("BEARISH_SWEEP",)
            )
        return None

    def _wyckoff(
        self, candles: tuple[OHLCVCandle, ...], snapshot: MarketSnapshot
    ) -> _Feature | None:
        sweep = self._smc(candles, snapshot)
        if sweep is None or relative_volume(candles, 20) < Decimal("1.2"):
            return None
        setup = "SPRING_PROXY" if sweep.vote > 0 else "UPTHRUST_PROXY"
        return self._feature(
            sweep.vote, "VOLUME_CONFIRMED_WYCKOFF_PROXY", setups=(setup,)
        )

    def _breakout_retest(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature | None:
        current, previous = candles[-1], candles[-2]
        resistance = max(candle.high for candle in candles[-22:-2])
        support = min(candle.low for candle in candles[-22:-2])
        if previous.close > resistance and current.low <= resistance < current.close:
            return self._feature(
                0.6, "BREAKOUT_RETEST_CONFIRMED", setups=("BULLISH_BREAKOUT_RETEST",)
            )
        if previous.close < support and current.high >= support > current.close:
            return self._feature(
                -0.6, "BREAKOUT_RETEST_CONFIRMED", setups=("BEARISH_BREAKOUT_RETEST",)
            )
        return None

    def _mean_reversion(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature:
        values = tuple(float(value) for value in closes(candles[-30:]))
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        deviation = sqrt(variance)
        zscore = (values[-1] - mean) / deviation if deviation > 0 else 0.0
        return self._feature(
            max(-1.0, min(1.0, -zscore / 2)), "CLOSE_ZSCORE", zscore=zscore
        )

    def _statistics(
        self, candles: tuple[OHLCVCandle, ...], _snapshot: MarketSnapshot
    ) -> _Feature:
        values = tuple(float(value) for value in closes(candles[-51:]))
        returns = tuple(
            (current / previous) - 1
            for previous, current in pairwise(values)
            if previous > 0
        )
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / len(returns)
        vote = max(-1.0, min(1.0, mean / sqrt(variance))) if variance > 0 else 0.0
        return self._feature(
            vote, "RETURN_DISTRIBUTION", mean_return=mean, volatility=sqrt(variance)
        )

    def _correlation(
        self, candles: tuple[OHLCVCandle, ...], snapshot: MarketSnapshot
    ) -> _Feature | None:
        raw = snapshot.market_metadata.get("benchmark_closes")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return None
        benchmark = self._decimal_sequence(raw)
        asset = closes(candles[-len(benchmark) :])
        if len(benchmark) < 20 or len(asset) != len(benchmark):
            return None
        correlation = self._pearson(asset, benchmark)
        return self._feature(
            0.0, "BENCHMARK_RETURN_CORRELATION", correlation=correlation
        )

    def _external(self, snapshot: MarketSnapshot, field_name: str) -> AgentResult:
        raw = getattr(snapshot, field_name)
        source_count = self._number(raw.get("source_count"))
        vote = self._number(raw.get("directional_vote"))
        score = self._number(raw.get("score"))
        as_of = self._timestamp(raw.get("as_of"))
        derivatives_context = self.definition.name in {"derivatives", "long_short"}
        if source_count is None or source_count < 1 or as_of is None:
            return self._insufficient(
                snapshot, "EXTERNAL_EVIDENCE_MISSING_OR_UNSOURCED"
            )
        if not derivatives_context and (vote is None or score is None):
            return self._insufficient(
                snapshot, "EXTERNAL_EVIDENCE_MISSING_OR_UNSOURCED"
            )
        maximum_age = EXTERNAL_MAX_AGE[self.definition.name]
        age = snapshot.created_at - as_of
        if age < timedelta(0) or age > maximum_age:
            return self._insufficient(snapshot, "EXTERNAL_EVIDENCE_STALE_OR_FUTURE")
        bounded_vote = max(-1.0, min(1.0, vote if vote is not None else 0.0))
        bounded_score = max(0.0, min(100.0, score if score is not None else 50.0))
        warning = (
            "SUPPLEMENTARY_FUTURES_CONTEXT_ONLY"
            if derivatives_context
            else "SUPPLEMENTARY_SPOT_EVIDENCE_ONLY"
        )
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=bounded_vote,
            score=bounded_score,
            confidence=min(0.5, source_count / 10),
            evidence=("SOURCED_EXTERNAL_SNAPSHOT",),
            warnings=(warning,),
            reason_codes=("EXTERNAL_CONTEXT_EVALUATED",),
            calculation_metadata={
                "source_count": source_count,
                "field": field_name,
                "as_of": as_of.isoformat(),
                "age_seconds": age.total_seconds(),
            },
        )

    def _order_book(self, snapshot: MarketSnapshot) -> AgentResult:
        bid_depth = self._number(snapshot.order_book_summary.get("bid_depth"))
        ask_depth = self._number(snapshot.order_book_summary.get("ask_depth"))
        if bid_depth is None or ask_depth is None or bid_depth + ask_depth <= 0:
            return self._insufficient(snapshot, "ORDER_BOOK_DEPTH_MISSING")
        vote = (bid_depth - ask_depth) / (bid_depth + ask_depth)
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=max(-1.0, min(1.0, vote)),
            score=abs(vote) * 100,
            confidence=0.35,
            evidence=("TOP_LEVEL_DEPTH_IMBALANCE",),
            warnings=("TRANSIENT_ORDER_BOOK_EVIDENCE",),
            reason_codes=("ORDER_BOOK_IMBALANCE_EVALUATED",),
            calculation_metadata={"bid_depth": bid_depth, "ask_depth": ask_depth},
        )

    def _insufficient(self, snapshot: MarketSnapshot, blocker: str) -> AgentResult:
        return self.result(
            snapshot,
            status=AgentStatus.INSUFFICIENT_DATA,
            data_quality=snapshot.data_quality,
            applicable=False,
            blockers=(blocker,),
            warnings=("RESEARCH_ONLY_AGENT",),
            reason_codes=("ADVANCED_AGENT_INSUFFICIENT_DATA",),
        )

    @staticmethod
    def _feature(
        vote: float, evidence: str, *, setups: tuple[str, ...] = (), **metadata: object
    ) -> _Feature:
        bounded = max(-1.0, min(1.0, vote))
        return _Feature(
            bounded,
            min(100.0, 50.0 + abs(bounded) * 40),
            0.4,
            (evidence,),
            setups,
            metadata,
        )

    @staticmethod
    def _bounded(value: Decimal) -> float:
        return float(max(Decimal("-1"), min(Decimal("1"), value)))

    @staticmethod
    def _midpoint(candles: Sequence[OHLCVCandle]) -> Decimal:
        return (
            max(candle.high for candle in candles)
            + min(candle.low for candle in candles)
        ) / 2

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None
        return float(number) if number.is_finite() else None

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

    @staticmethod
    def _decimal_sequence(values: Sequence[object]) -> tuple[Decimal, ...]:
        parsed: list[Decimal] = []
        for value in values:
            number = AdvancedTechnicalAgent._number(value)
            if number is None:
                return ()
            parsed.append(Decimal(str(number)))
        return tuple(parsed)

    @staticmethod
    def _pearson(left: Sequence[Decimal], right: Sequence[Decimal]) -> float:
        left_values = tuple(float(value) for value in left)
        right_values = tuple(float(value) for value in right)
        left_mean = sum(left_values) / len(left_values)
        right_mean = sum(right_values) / len(right_values)
        numerator = sum(
            (x - left_mean) * (y - right_mean)
            for x, y in zip(left_values, right_values, strict=True)
        )
        left_variance = sum((value - left_mean) ** 2 for value in left_values)
        right_variance = sum((value - right_mean) ** 2 for value in right_values)
        denominator = sqrt(left_variance * right_variance)
        return numerator / denominator if denominator > 0 else 0.0


def build_advanced_agent(definition: AgentDefinition) -> BaseAgent | None:
    """Return a governed advanced implementation when one is registered."""
    return (
        AdvancedTechnicalAgent(definition)
        if definition.name in ADVANCED_AGENT_NAMES
        else None
    )

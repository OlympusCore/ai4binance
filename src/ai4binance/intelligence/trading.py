"""Deterministic synthesis from existing evidence into bounded scenarios."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import cast

from ai4binance.domain import Action, CandidateStatus, TradeCandidate
from ai4binance.intelligence.contracts import (
    CalibrationState,
    ConfidenceComponent,
    ConfirmedSwing,
    DerivativesContextEvidence,
    PatternHypothesisEvidence,
    ScenarioDirection,
    ScenarioHypothesis,
    ScenarioState,
    ScenarioType,
    StructuralLevelEvidence,
    StructureEvent,
    StructureState,
    SwingKind,
    TimeframeStructureEvidence,
    TradingIntelligenceState,
    TrendGeometryEvidence,
)
from ai4binance.intelligence.derivatives import FuturesContextEngine
from ai4binance.intelligence.levels import StructuralLevelMapEngine
from ai4binance.intelligence.patterns import PatternHypothesisFabric
from ai4binance.intelligence.trend import TrendGeometryEngine
from ai4binance.schemas import (
    AgentResult,
    DataQuality,
    MarketSnapshot,
    is_usable_agent_result,
)

ZERO = Decimal("0")
STRUCTURE_PRIORITY = ("1d", "4h", "1h", "15m", "5m")


@dataclass(frozen=True, slots=True)
class TradingIntelligenceEngine:
    """Normalize canonical observations and form hierarchical scenarios."""

    level_map_engine: StructuralLevelMapEngine = field(
        default_factory=StructuralLevelMapEngine
    )
    trend_geometry_engine: TrendGeometryEngine = field(
        default_factory=TrendGeometryEngine
    )
    pattern_hypothesis_fabric: PatternHypothesisFabric = field(
        default_factory=PatternHypothesisFabric
    )
    futures_context_engine: FuturesContextEngine = field(
        default_factory=FuturesContextEngine
    )
    minimum_scenario_separation: float = 0.10

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_scenario_separation <= 1.0:
            raise ValueError("scenario separation must be between zero and one")

    def build(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> TradingIntelligenceState:
        """Build one snapshot-bound state without recalculating indicators."""
        identity_blockers = self._identity_blockers(snapshot, agent_results)
        structures = self._structures(snapshot, agent_results)
        levels = self._levels(snapshot, agent_results, structures)
        trend_geometry = self._trend_geometry(snapshot, agent_results, structures)
        pattern_hypotheses = self._patterns(snapshot, agent_results)
        derivatives = self._derivatives(snapshot, agent_results)
        cost_ratio, cost_blockers = self._cost_model(snapshot, derivatives)
        scenarios, selected_id, scenario_blockers, warnings = self._scenarios(
            snapshot,
            agent_results,
            structures,
            levels,
            trend_geometry,
            pattern_hypotheses,
            derivatives,
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *identity_blockers,
                    *scenario_blockers,
                    *derivatives.blockers,
                )
            )
        )
        if identity_blockers or derivatives.blockers:
            selected_id = None
        return TradingIntelligenceState(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            timestamp=snapshot.created_at,
            structures=structures,
            levels=levels,
            trend_geometry=trend_geometry,
            pattern_hypotheses=pattern_hypotheses,
            derivatives_context=derivatives,
            scenarios=scenarios,
            selected_scenario_id=selected_id,
            estimated_round_trip_cost_ratio=cost_ratio,
            cost_blockers=cost_blockers,
            blockers=blockers,
            warnings=warnings,
        )

    def blocked(
        self,
        snapshot: MarketSnapshot,
        blockers: tuple[str, ...],
    ) -> TradingIntelligenceState:
        """Return an explicit state when an upstream hard gate exits early."""
        unique = tuple(dict.fromkeys(blockers or ("TRADING_INTELLIGENCE_BLOCKED",)))
        scenario = self._no_valid_scenario(snapshot, unique)
        return TradingIntelligenceState(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            timestamp=snapshot.created_at,
            structures=(),
            levels=(),
            trend_geometry=(),
            pattern_hypotheses=(),
            derivatives_context=DerivativesContextEvidence(
                status="BLOCKED",
                source_count=0,
                as_of=None,
                blockers=unique,
            ),
            scenarios=(scenario,),
            selected_scenario_id=None,
            blockers=unique,
        )

    def bind_candidates(
        self,
        candidates: tuple[TradeCandidate, ...],
        state: TradingIntelligenceState,
    ) -> tuple[TradeCandidate, ...]:
        """Bind candidates to one selected scenario before risk arbitration."""
        primary = state.selected_scenario
        if primary is None:
            blockers = tuple(
                dict.fromkeys(
                    (
                        "TRADING_INTELLIGENCE_NO_SELECTED_SCENARIO",
                        *state.blockers,
                    )
                )
            )
            return tuple(
                replace(
                    candidate,
                    status=CandidateStatus.RESEARCH_ONLY,
                    blockers=tuple(dict.fromkeys((*candidate.blockers, *blockers))),
                )
                for candidate in candidates
            )
        bound: list[TradeCandidate] = []
        for candidate in candidates:
            direction = (
                ScenarioDirection.LONG
                if candidate.action is Action.BUY
                else ScenarioDirection.SHORT
            )
            if direction is not primary.direction:
                bound.append(
                    replace(
                        candidate,
                        status=CandidateStatus.RESEARCH_ONLY,
                        blockers=tuple(
                            dict.fromkeys(
                                (
                                    *candidate.blockers,
                                    "SCENARIO_DIRECTION_NOT_SELECTED",
                                )
                            )
                        ),
                    )
                )
                continue
            status = candidate.status
            candidate_blockers = list(candidate.blockers)
            if primary.state is ScenarioState.FORMING:
                if status is CandidateStatus.READY_FOR_RISK:
                    status = CandidateStatus.WAIT_FOR_RETEST
                candidate_blockers.append("SCENARIO_CONFIRMATION_PENDING")
            elif primary.state is not ScenarioState.CONFIRMED:
                status = CandidateStatus.RESEARCH_ONLY
                candidate_blockers.extend(("SCENARIO_NOT_CONFIRMED", *primary.blockers))
            net_risk_reward = self._net_risk_reward(
                candidate,
                state.estimated_round_trip_cost_ratio,
            )
            if candidate.market_type == "USD_M_FUTURES" and net_risk_reward is None:
                status = CandidateStatus.RESEARCH_ONLY
                candidate_blockers.extend(state.cost_blockers)
            bound.append(
                replace(
                    candidate,
                    status=status,
                    scenario_id=primary.scenario_id,
                    scenario_type=primary.scenario_type.value,
                    scenario_state=primary.state.value,
                    scenario_invalidation=(
                        str(primary.invalidation_level)
                        if primary.invalidation_level is not None
                        else None
                    ),
                    structural_risk_reward=candidate.risk_reward,
                    net_risk_reward=net_risk_reward,
                    estimated_round_trip_cost_ratio=(
                        state.estimated_round_trip_cost_ratio
                    ),
                    expected_r=None,
                    probability_calibration_state=primary.calibration_state.value,
                    entry_trigger=self._entry_trigger(primary),
                    entry_state=(
                        "ENTRY_VALID"
                        if primary.state is ScenarioState.CONFIRMED
                        else "ENTRY_NOT_READY"
                    ),
                    entry_expiry=self._entry_expiry(
                        candidate.timestamp,
                        candidate.timeframe,
                    ),
                    target_sources=("STRATEGY_ENGINE_STRUCTURAL_TARGET",),
                    evidence=tuple(
                        dict.fromkeys(
                            (
                                *candidate.evidence,
                                f"SCENARIO_ID:{primary.scenario_id}",
                                f"SCENARIO_TYPE:{primary.scenario_type.value}",
                            )
                        )
                    ),
                    blockers=tuple(dict.fromkeys(candidate_blockers)),
                )
            )
        return tuple(bound)

    @classmethod
    def _cost_model(
        cls,
        snapshot: MarketSnapshot,
        derivatives: DerivativesContextEvidence,
    ) -> tuple[Decimal | None, tuple[str, ...]]:
        blockers: list[str] = []
        latest_price = snapshot.latest_price
        if latest_price is None or latest_price <= ZERO or snapshot.spread is None:
            blockers.append("COST_SPREAD_EVIDENCE_UNAVAILABLE")
            spread_ratio = None
        else:
            spread_ratio = snapshot.spread / latest_price
        fee_ratio = cls._decimal(
            snapshot.market_metadata.get("estimated_fee_ratio")
            or snapshot.market_metadata.get("fee_ratio")
        )
        slippage_ratio = cls._decimal(
            snapshot.market_metadata.get("estimated_slippage_ratio")
        )
        if fee_ratio is None or fee_ratio < ZERO:
            blockers.append("COST_FEE_EVIDENCE_UNAVAILABLE")
        if slippage_ratio is None or slippage_ratio < ZERO:
            blockers.append("COST_SLIPPAGE_EVIDENCE_UNAVAILABLE")
        funding_ratio = ZERO
        if snapshot.market_type == "USD_M_FUTURES":
            if derivatives.funding_rate is None:
                blockers.append("COST_FUNDING_EVIDENCE_UNAVAILABLE")
            else:
                funding_ratio = abs(derivatives.funding_rate)
        if blockers:
            return None, tuple(dict.fromkeys(blockers))
        assert spread_ratio is not None
        assert fee_ratio is not None
        assert slippage_ratio is not None
        round_trip = spread_ratio + (fee_ratio * 2) + (slippage_ratio * 2)
        return round_trip + funding_ratio, ()

    @staticmethod
    def _net_risk_reward(
        candidate: TradeCandidate,
        cost_ratio: Decimal | None,
    ) -> Decimal | None:
        if cost_ratio is None:
            return None
        entry = candidate.entry_price
        risk = abs(entry - candidate.invalidation_level)
        gross_reward = abs(candidate.take_profit_levels[0] - entry)
        net_reward = gross_reward - (entry * cost_ratio)
        if risk <= ZERO or net_reward <= ZERO:
            return None
        return cast(Decimal, net_reward / risk)

    @staticmethod
    def _identity_blockers(
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[str, ...]:
        return tuple(
            f"TRADING_INTELLIGENCE_IDENTITY_MISMATCH:{name}"
            for name, result in sorted(agent_results.items())
            if result.snapshot_id != snapshot.snapshot_id
            or result.symbol != snapshot.symbol
            or result.timestamp != snapshot.created_at
        )

    def _structures(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[TimeframeStructureEvidence, ...]:
        result = agent_results.get("market_structure")
        if result is None or not is_usable_agent_result(result):
            return ()
        raw_timeframes = self._mapping(result.calculation_metadata.get("timeframes"))
        structures: list[TimeframeStructureEvidence] = []
        for timeframe in STRUCTURE_PRIORITY:
            if timeframe not in snapshot.timeframes:
                continue
            raw = self._mapping(raw_timeframes.get(timeframe))
            if not raw:
                continue
            state = self._structure_state(raw.get("structure_state"))
            if state is None:
                state = self._legacy_structure_state(raw.get("structure"))
            low = self._decimal(raw.get("range_low") or raw.get("recent_low"))
            high = self._decimal(raw.get("range_high") or raw.get("recent_high"))
            if state is None or low is None or high is None or high < low:
                continue
            invalidation = self._decimal(raw.get("invalidation_level"))
            confidence = self._float(raw.get("structure_confidence"))
            structures.append(
                TimeframeStructureEvidence(
                    timeframe=timeframe,
                    state=state,
                    method=str(raw.get("structure_method", "WINDOWED_STRUCTURE")),
                    range_low=low,
                    range_high=high,
                    invalidation_level=invalidation,
                    confidence=(
                        max(0.0, min(1.0, confidence))
                        if confidence is not None
                        else result.confidence
                    ),
                    swings=self._swings(raw.get("swings"), timeframe),
                    events=self._events(raw.get("events")),
                    reason_codes=("MARKET_STRUCTURE_AGENT_PROJECTION",),
                    warnings=self._string_tuple(raw.get("structure_warnings")),
                )
            )
        return tuple(structures)

    def _levels(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        structures: tuple[TimeframeStructureEvidence, ...],
    ) -> tuple[StructuralLevelEvidence, ...]:
        result = agent_results.get("support_resistance")
        return self.level_map_engine.build(snapshot, structures, result)

    def _trend_geometry(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        structures: tuple[TimeframeStructureEvidence, ...],
    ) -> tuple[TrendGeometryEvidence, ...]:
        result = agent_results.get("trend_channel")
        return self.trend_geometry_engine.build(snapshot, structures, result)

    def _patterns(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[PatternHypothesisEvidence, ...]:
        return self.pattern_hypothesis_fabric.build(snapshot, agent_results)

    def _derivatives(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> DerivativesContextEvidence:
        result = agent_results.get("derivatives")
        return self.futures_context_engine.build(snapshot, result)

    def _scenarios(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        structures: tuple[TimeframeStructureEvidence, ...],
        levels: tuple[StructuralLevelEvidence, ...],
        trend_geometry: tuple[TrendGeometryEvidence, ...],
        patterns: tuple[PatternHypothesisEvidence, ...],
        derivatives: DerivativesContextEvidence,
    ) -> tuple[
        tuple[ScenarioHypothesis, ...],
        str | None,
        tuple[str, ...],
        tuple[str, ...],
    ]:
        by_timeframe = {item.timeframe: item for item in structures}
        macro = by_timeframe.get("1d")
        directional = by_timeframe.get("4h") or by_timeframe.get("1h")
        setup = by_timeframe.get("1h") or directional
        mtf = agent_results.get("multi_timeframe")
        data_quality = agent_results.get("data_quality")
        regime_result = agent_results.get("market_regime")
        regime = self._regime(regime_result)
        if directional is None:
            unavailable = ("DIRECTION_STRUCTURE_UNAVAILABLE",)
            scenario = self._no_valid_scenario(snapshot, unavailable, regime)
            return (scenario,), None, unavailable, ()
        direction = self._structure_direction(directional.state)
        if direction is ScenarioDirection.NEUTRAL:
            scenario = self._neutral_scenario(
                snapshot,
                directional,
                regime,
                mtf,
                data_quality,
                derivatives,
            )
            return (scenario,), scenario.scenario_id, (), ()
        blockers = list(self._hierarchy_blockers(direction, macro, setup, mtf))
        trigger = self._trigger(agent_results)
        trigger_direction = (
            self._direction(trigger.directional_vote)
            if trigger is not None
            else ScenarioDirection.NEUTRAL
        )
        scenario_state, scenario_blockers, trigger_blockers = self._trigger_state(
            direction,
            trigger_direction,
            derivatives,
        )
        blockers.extend(trigger_blockers)
        continuation_type = (
            ScenarioType.LONG_CONTINUATION
            if direction is ScenarioDirection.LONG
            else ScenarioType.SHORT_CONTINUATION
        )
        evidence_for = self._continuation_evidence(
            directional,
            regime,
            direction,
            levels,
            trend_geometry,
            patterns,
            derivatives,
            mtf,
            trigger,
            trigger_direction,
        )
        primary = self._scenario(
            snapshot=snapshot,
            scenario_type=continuation_type,
            direction=direction,
            state=scenario_state,
            structure=directional,
            regime=regime,
            mtf_confidence=mtf.confidence if mtf is not None else 0.0,
            trigger_confidence=trigger.confidence if trigger is not None else 0.0,
            data_confidence=self._data_confidence(snapshot, data_quality),
            context_confidence=(
                derivatives.confidence
                if derivatives.status == "AVAILABLE"
                else 1.0
                if derivatives.status == "NOT_APPLICABLE"
                else 0.0
            ),
            evidence_for=evidence_for,
            evidence_against=tuple(dict.fromkeys(blockers)),
            blockers=scenario_blockers,
        )
        reversal = self._reversal_scenario(
            snapshot,
            directional,
            regime,
            direction,
            trigger,
            trigger_direction,
        )
        scenarios = (primary,) if reversal is None else (primary, reversal)
        if (
            reversal is not None
            and abs(primary.confidence - reversal.confidence)
            < self.minimum_scenario_separation
        ):
            blockers.append("SCENARIO_SEPARATION_INSUFFICIENT")
        selected_id = None if blockers else primary.scenario_id
        return (
            scenarios,
            selected_id,
            tuple(dict.fromkeys(blockers)),
            (),
        )

    def _neutral_scenario(
        self,
        snapshot: MarketSnapshot,
        structure: TimeframeStructureEvidence,
        regime: str,
        mtf: AgentResult | None,
        data_quality: AgentResult | None,
        derivatives: DerivativesContextEvidence,
    ) -> ScenarioHypothesis:
        scenario_type = (
            ScenarioType.BREAKOUT_PENDING
            if "COMPRESSION" in regime
            else ScenarioType.RANGE_MEAN_REVERSION
        )
        return self._scenario(
            snapshot=snapshot,
            scenario_type=scenario_type,
            direction=ScenarioDirection.NEUTRAL,
            state=ScenarioState.FORMING,
            structure=structure,
            regime=regime,
            mtf_confidence=mtf.confidence if mtf is not None else 0.0,
            trigger_confidence=0.0,
            data_confidence=self._data_confidence(snapshot, data_quality),
            context_confidence=(
                derivatives.confidence
                if derivatives.status == "AVAILABLE"
                else 1.0
                if derivatives.status == "NOT_APPLICABLE"
                else 0.0
            ),
            evidence_for=(
                f"STRUCTURE:{structure.timeframe}:{structure.state.value}",
                f"REGIME:{regime}",
            ),
            blockers=("DIRECTIONAL_STRUCTURE_UNRESOLVED",),
        )

    @staticmethod
    def _hierarchy_blockers(
        direction: ScenarioDirection,
        macro: TimeframeStructureEvidence | None,
        setup: TimeframeStructureEvidence | None,
        mtf: AgentResult | None,
    ) -> tuple[str, ...]:
        opposite = (
            StructureState.BEARISH
            if direction is ScenarioDirection.LONG
            else StructureState.BULLISH
        )
        blockers: list[str] = []
        if macro is not None and macro.state is opposite:
            blockers.append("MACRO_STRUCTURE_CONFLICT")
        if setup is not None and setup.state is opposite:
            blockers.append("SETUP_STRUCTURE_CONFLICT")
        if mtf is None or not is_usable_agent_result(mtf):
            blockers.append("MULTI_TIMEFRAME_EVIDENCE_UNAVAILABLE")
        elif mtf.calculation_metadata.get("conflict") is True:
            blockers.append("MULTI_TIMEFRAME_DIRECTION_CONFLICT")
        return tuple(blockers)

    @staticmethod
    def _trigger_state(
        direction: ScenarioDirection,
        trigger_direction: ScenarioDirection,
        derivatives: DerivativesContextEvidence,
    ) -> tuple[ScenarioState, tuple[str, ...], tuple[str, ...]]:
        state = ScenarioState.FORMING
        scenario_blockers: list[str] = []
        global_blockers: list[str] = []
        if trigger_direction is ScenarioDirection.NEUTRAL:
            scenario_blockers.append("ENTRY_TRIGGER_MISSING")
        elif trigger_direction is not direction:
            global_blockers.append("TRIGGER_DIRECTION_CONFLICT")
            scenario_blockers.append("TRIGGER_DIRECTION_CONFLICT")
            state = ScenarioState.BLOCKED
        else:
            state = ScenarioState.CONFIRMED
        if derivatives.status == "BLOCKED":
            state = ScenarioState.BLOCKED
            scenario_blockers.extend(derivatives.blockers)
        return (
            state,
            tuple(dict.fromkeys(scenario_blockers)),
            tuple(global_blockers),
        )

    @staticmethod
    def _continuation_evidence(
        structure: TimeframeStructureEvidence,
        regime: str,
        direction: ScenarioDirection,
        levels: tuple[StructuralLevelEvidence, ...],
        trend_geometry: tuple[TrendGeometryEvidence, ...],
        patterns: tuple[PatternHypothesisEvidence, ...],
        derivatives: DerivativesContextEvidence,
        mtf: AgentResult | None,
        trigger: AgentResult | None,
        trigger_direction: ScenarioDirection,
    ) -> tuple[str, ...]:
        evidence = [
            f"STRUCTURE:{structure.timeframe}:{structure.state.value}",
            f"REGIME:{regime}",
        ]
        evidence.extend(
            item.evidence_ref
            for item in levels
            if item.source_timeframe == structure.timeframe
            and item.freshness != "STALE"
        )
        if derivatives.status == "AVAILABLE":
            evidence.extend(derivatives.evidence_refs)
        evidence.extend(
            item.evidence_ref
            for item in trend_geometry
            if item.source_timeframe == structure.timeframe and not item.blockers
        )
        if mtf is not None:
            evidence.extend(mtf.evidence or ("MULTI_TIMEFRAME_EVALUATED",))
        evidence.extend(
            item.hypothesis_id
            for item in patterns
            if item.direction in {direction, ScenarioDirection.NEUTRAL}
        )
        if trigger is not None and trigger_direction is direction:
            evidence.extend(trigger.evidence or ("ENTRY_TRIGGER_ALIGNED",))
        return tuple(dict.fromkeys(evidence))

    def _reversal_scenario(
        self,
        snapshot: MarketSnapshot,
        structure: TimeframeStructureEvidence,
        regime: str,
        direction: ScenarioDirection,
        trigger: AgentResult | None,
        trigger_direction: ScenarioDirection,
    ) -> ScenarioHypothesis | None:
        if trigger is None or trigger_direction in {
            direction,
            ScenarioDirection.NEUTRAL,
        }:
            return None
        reversal_type = (
            ScenarioType.LONG_REVERSAL
            if trigger_direction is ScenarioDirection.LONG
            else ScenarioType.SHORT_REVERSAL
        )
        return self._scenario(
            snapshot=snapshot,
            scenario_type=reversal_type,
            direction=trigger_direction,
            state=ScenarioState.FORMING,
            structure=structure,
            regime=regime,
            mtf_confidence=0.0,
            trigger_confidence=trigger.confidence,
            evidence_for=trigger.evidence or ("COUNTER_TREND_TRIGGER",),
            evidence_against=("STRUCTURE_REVERSAL_NOT_CONFIRMED",),
            blockers=("STRUCTURE_REVERSAL_NOT_CONFIRMED",),
        )

    def _scenario(
        self,
        *,
        snapshot: MarketSnapshot,
        scenario_type: ScenarioType,
        direction: ScenarioDirection,
        state: ScenarioState,
        structure: TimeframeStructureEvidence,
        regime: str,
        mtf_confidence: float,
        trigger_confidence: float,
        evidence_for: tuple[str, ...],
        data_confidence: float = 1.0,
        context_confidence: float = 1.0,
        evidence_against: tuple[str, ...] = (),
        blockers: tuple[str, ...] = (),
    ) -> ScenarioHypothesis:
        components = (
            ConfidenceComponent("structure", structure.confidence),
            ConfidenceComponent("multi_timeframe", max(0.0, mtf_confidence)),
            ConfidenceComponent("entry_trigger", max(0.0, trigger_confidence)),
            ConfidenceComponent("data_quality", max(0.0, data_confidence)),
            ConfidenceComponent("futures_context", max(0.0, context_confidence)),
        )
        payload = (
            f"{snapshot.snapshot_id}|{scenario_type.value}|{direction.value}|"
            f"{structure.timeframe}|{structure.state.value}"
        )
        digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
        return ScenarioHypothesis(
            scenario_id=f"scenario:{digest}",
            snapshot_id=snapshot.snapshot_id,
            scenario_type=scenario_type,
            direction=direction,
            state=state,
            structure_state=structure.state,
            regime=regime,
            invalidation_level=structure.invalidation_level,
            confidence=min(item.value for item in components),
            confidence_components=components,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            blockers=blockers,
            calibration_state=CalibrationState.NOT_CALIBRATED,
        )

    def _no_valid_scenario(
        self,
        snapshot: MarketSnapshot,
        blockers: tuple[str, ...],
        regime: str = "UNKNOWN",
    ) -> ScenarioHypothesis:
        components = (
            ConfidenceComponent("structure", 0.0),
            ConfidenceComponent("multi_timeframe", 0.0),
            ConfidenceComponent("entry_trigger", 0.0),
            ConfidenceComponent("data_quality", 0.0),
            ConfidenceComponent("futures_context", 0.0),
        )
        digest = sha256(f"{snapshot.snapshot_id}|NO_VALID_SETUP".encode()).hexdigest()[
            :20
        ]
        return ScenarioHypothesis(
            scenario_id=f"scenario:{digest}",
            snapshot_id=snapshot.snapshot_id,
            scenario_type=ScenarioType.NO_VALID_SETUP,
            direction=ScenarioDirection.NEUTRAL,
            state=ScenarioState.NO_VALID_SETUP,
            structure_state=StructureState.UNCERTAIN,
            regime=regime,
            invalidation_level=None,
            confidence=0.0,
            confidence_components=components,
            evidence_for=("NO_DIRECTIONAL_STRUCTURE",),
            evidence_against=blockers,
            blockers=blockers,
        )

    @staticmethod
    def _trigger(
        agent_results: Mapping[str, AgentResult],
    ) -> AgentResult | None:
        return next(
            (
                result
                for name in ("price_action", "candlestick", "breakout_retest")
                if (result := agent_results.get(name)) is not None
                and is_usable_agent_result(result)
                and abs(result.directional_vote) > 0.0
            ),
            None,
        )

    @staticmethod
    def _regime(result: AgentResult | None) -> str:
        if result is None or not is_usable_agent_result(result):
            return "UNKNOWN"
        value = result.calculation_metadata.get("regime")
        return value if isinstance(value, str) and value.strip() else "UNKNOWN"

    @staticmethod
    def _data_confidence(
        snapshot: MarketSnapshot,
        result: AgentResult | None,
    ) -> float:
        if result is not None and is_usable_agent_result(result):
            return result.confidence
        if snapshot.data_quality is DataQuality.DATA_VALID:
            return 1.0
        if snapshot.data_quality is DataQuality.DATA_DEGRADED:
            return 0.5
        return 0.0

    @staticmethod
    def _entry_trigger(scenario: ScenarioHypothesis) -> str:
        return next(
            (
                item
                for item in scenario.evidence_for
                if any(
                    marker in item
                    for marker in ("ENGULFING", "BREAKOUT", "RETEST", "TRIGGER")
                )
            ),
            "SCENARIO_CONFIRMATION",
        )

    @staticmethod
    def _entry_expiry(timestamp: datetime, timeframe: str) -> datetime | None:
        unit = timeframe[-1:].lower()
        raw_value = timeframe[:-1]
        if not raw_value.isdigit():
            return None
        value = int(raw_value)
        if value < 1:
            return None
        delta = {
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }.get(unit)
        return timestamp + delta if delta is not None else None

    @staticmethod
    def _structure_direction(state: StructureState) -> ScenarioDirection:
        if state is StructureState.BULLISH:
            return ScenarioDirection.LONG
        if state is StructureState.BEARISH:
            return ScenarioDirection.SHORT
        return ScenarioDirection.NEUTRAL

    @staticmethod
    def _direction(vote: float) -> ScenarioDirection:
        if vote > 0.0:
            return ScenarioDirection.LONG
        if vote < 0.0:
            return ScenarioDirection.SHORT
        return ScenarioDirection.NEUTRAL

    @staticmethod
    def _structure_state(value: object) -> StructureState | None:
        if not isinstance(value, str):
            return None
        try:
            return StructureState(value)
        except ValueError:
            return None

    @staticmethod
    def _legacy_structure_state(value: object) -> StructureState | None:
        return (
            {
                "HH_HL": StructureState.BULLISH,
                "LH_LL": StructureState.BEARISH,
                "MIXED": StructureState.TRANSITION,
            }.get(value)
            if isinstance(value, str)
            else None
        )

    @classmethod
    def _swings(
        cls,
        value: object,
        timeframe: str,
    ) -> tuple[ConfirmedSwing, ...]:
        if not isinstance(value, (tuple, list)):
            return ()
        swings: list[ConfirmedSwing] = []
        for item in value:
            raw = cls._mapping(item)
            kind_value = raw.get("kind")
            index = cls._integer(raw.get("candle_index"))
            occurred_at = cls._datetime(raw.get("occurred_at"))
            available_at = cls._datetime(raw.get("available_at"))
            price = cls._decimal(raw.get("price"))
            label = raw.get("label")
            significance = cls._decimal(raw.get("atr_significance"))
            try:
                kind = SwingKind(kind_value) if isinstance(kind_value, str) else None
            except ValueError:
                kind = None
            if (
                kind is None
                or index is None
                or occurred_at is None
                or available_at is None
                or price is None
                or not isinstance(label, str)
                or significance is None
            ):
                continue
            try:
                swings.append(
                    ConfirmedSwing(
                        timeframe=timeframe,
                        kind=kind,
                        candle_index=index,
                        occurred_at=occurred_at,
                        available_at=available_at,
                        price=price,
                        label=label,
                        atr_significance=significance,
                    )
                )
            except ValueError:
                continue
        return tuple(swings)

    @classmethod
    def _events(cls, value: object) -> tuple[StructureEvent, ...]:
        if not isinstance(value, (tuple, list)):
            return ()
        events: list[StructureEvent] = []
        for item in value:
            raw = cls._mapping(item)
            event_type = raw.get("event_type")
            direction_value = raw.get("direction")
            level = cls._decimal(raw.get("level"))
            occurred_at = cls._datetime(raw.get("occurred_at"))
            evidence_ref = raw.get("evidence_ref")
            try:
                direction = (
                    ScenarioDirection(direction_value)
                    if isinstance(direction_value, str)
                    else None
                )
            except ValueError:
                direction = None
            if (
                not isinstance(event_type, str)
                or direction is None
                or level is None
                or occurred_at is None
                or not isinstance(evidence_ref, str)
            ):
                continue
            try:
                events.append(
                    StructureEvent(
                        event_type=event_type,
                        direction=direction,
                        level=level,
                        occurred_at=occurred_at,
                        evidence_ref=evidence_ref,
                    )
                )
            except ValueError:
                continue
        return tuple(events)

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        if not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _float(value: object) -> float | None:
        decimal = TradingIntelligenceEngine._decimal(value)
        return float(decimal) if decimal is not None else None

    @staticmethod
    def _integer(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _datetime(value: object) -> datetime | None:
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
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, (tuple, list)):
            return ()
        return tuple(item for item in value if isinstance(item, str) and item.strip())

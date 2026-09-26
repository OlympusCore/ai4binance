"""Deterministic Trading Intelligence evidence-chain tests."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.agents.validation_gate import ValidationGate
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
)
from ai4binance.intelligence.contracts import (
    CalibrationState,
    PatternLifecycleState,
    ScenarioDirection,
    ScenarioState,
    ScenarioType,
    StructureState,
)
from ai4binance.intelligence.derivatives import FuturesContextEngine
from ai4binance.intelligence.patterns import PatternHypothesisFabric
from ai4binance.intelligence.structure import MarketStructureEngine
from ai4binance.intelligence.trading import TradingIntelligenceEngine
from ai4binance.intelligence.trend import TrendGeometryEngine
from ai4binance.research.virtual_runtime_risk import (
    SimulatedLeverageState,
    VirtualPortfolioRiskGovernor,
)
from ai4binance.risk import (
    RiskAssessment,
    RiskContext,
    RiskEngine,
    candidate_risk_distance,
)
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
)
from tests.test_strategy_risk import symbol_filters
from tests.test_technical_agents import NOW, technical_snapshot


def _result(
    name: str,
    *,
    vote: float = 1.0,
    confidence: float = 0.8,
    evidence: tuple[str, ...] = ("DETERMINISTIC_EVIDENCE",),
    metadata: dict[str, object] | None = None,
) -> AgentResult:
    snapshot = technical_snapshot()
    return AgentResult(
        agent_name=name,
        agent_version="test-v1",
        snapshot_id=snapshot.snapshot_id,
        timestamp=snapshot.created_at,
        symbol=snapshot.symbol,
        timeframes=snapshot.timeframes,
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=vote,
        score=80.0,
        confidence=confidence,
        evidence=evidence,
        reason_codes=("TEST_EVIDENCE_READY",),
        calculation_metadata=metadata or {},
    )


def _structure_result(*, macro_state: StructureState) -> AgentResult:
    def projection(state: StructureState, invalidation: str) -> dict[str, object]:
        return {
            "structure_state": state.value,
            "structure_method": "CONFIRMED_SWING_GRAPH",
            "range_low": "0.90",
            "range_high": "1.30",
            "invalidation_level": invalidation,
            "structure_confidence": 0.8,
            "structure_warnings": (),
            "swings": (
                {
                    "kind": "LOW",
                    "candle_index": 10,
                    "occurred_at": (NOW - timedelta(hours=4)).isoformat(),
                    "available_at": (NOW - timedelta(hours=2)).isoformat(),
                    "price": invalidation,
                    "label": "HL",
                    "atr_significance": "1.2",
                },
            ),
            "events": (),
        }

    return _result(
        "market_structure",
        metadata={
            "timeframes": {
                "1d": projection(macro_state, "1.25"),
                "4h": projection(StructureState.BULLISH, "0.95"),
                "1h": projection(StructureState.BULLISH, "0.98"),
                "15m": projection(StructureState.BULLISH, "1.00"),
            }
        },
    )


def _evidence_results(
    *,
    macro_state: StructureState = StructureState.BULLISH,
    include_trigger: bool = True,
) -> dict[str, AgentResult]:
    results = {
        "market_structure": _structure_result(macro_state=macro_state),
        "multi_timeframe": _result(
            "multi_timeframe",
            confidence=0.7,
            evidence=("MTF_DIRECTION_ALIGNED",),
            metadata={"conflict": False},
        ),
        "market_regime": _result(
            "market_regime",
            metadata={"regime": "TRENDING"},
        ),
    }
    if include_trigger:
        results["price_action"] = _result(
            "price_action",
            confidence=0.6,
            evidence=("BULLISH_ENGULFING:15m",),
        )
    return results


def _candidate() -> TradeCandidate:
    snapshot = technical_snapshot()
    return TradeCandidate(
        candidate_id="candidate:long-continuation",
        snapshot_id=snapshot.snapshot_id,
        timestamp=snapshot.created_at,
        symbol=snapshot.symbol,
        timeframe="15m",
        action=Action.BUY,
        setup_name="LONG_CONTINUATION",
        status=CandidateStatus.READY_FOR_RISK,
        entry_zone=PriceZone(Decimal("1.10"), Decimal("1.12")),
        invalidation_level=Decimal("1.00"),
        stop_loss=Decimal("1.00"),
        take_profit_levels=(Decimal("1.30"),),
        trailing_stop=Decimal("0.05"),
        atr=Decimal("0.02"),
        risk_reward=Decimal("1.7"),
        score=80.0,
        confidence=0.7,
    )


def _costed_snapshot() -> MarketSnapshot:
    snapshot = technical_snapshot()
    return replace(
        snapshot,
        market_metadata={
            **snapshot.market_metadata,
            "estimated_fee_ratio": "0.001",
            "estimated_slippage_ratio": "0.001",
        },
    )


def test_confirmed_scenario_uses_weakest_confidence_and_binds_candidate() -> None:
    engine = TradingIntelligenceEngine()
    state = engine.build(_costed_snapshot(), _evidence_results())

    assert state.selected_scenario is not None
    assert state.selected_scenario.scenario_type is ScenarioType.LONG_CONTINUATION
    assert state.selected_scenario.state is ScenarioState.CONFIRMED
    assert state.selected_scenario.confidence == 0.6
    assert state.selected_scenario.calibration_state is CalibrationState.NOT_CALIBRATED
    assert state.structures[1].swings
    assert state.structures[1].swings[0].label == "HL"
    assert state.scenario_separation == 0.6
    assert state.execution_allowed is False
    assert state.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    (candidate,) = engine.bind_candidates((_candidate(),), state)
    assert candidate.status is CandidateStatus.READY_FOR_RISK
    assert candidate.scenario_id == state.selected_scenario_id
    assert candidate.scenario_type == ScenarioType.LONG_CONTINUATION.value
    assert candidate.scenario_state == ScenarioState.CONFIRMED.value
    assert candidate.scenario_invalidation == "0.95"
    assert candidate.gross_risk_reward == Decimal("1.7")
    assert candidate.structural_risk_reward == Decimal("1.1875")
    assert candidate.net_risk_reward is not None
    assert candidate.expected_r is None
    assert candidate.probability_calibration_state == "PROBABILITY_NOT_CALIBRATED"
    assert candidate.entry_trigger == "BULLISH_ENGULFING:15m"
    assert candidate.entry_state == "ENTRY_VALID"
    assert candidate.entry_expiry == candidate.timestamp + timedelta(minutes=15)
    assert candidate.target_sources == ()


def test_macro_conflict_and_missing_trigger_fail_closed() -> None:
    engine = TradingIntelligenceEngine()
    conflicted = engine.build(
        technical_snapshot(),
        _evidence_results(macro_state=StructureState.BEARISH),
    )
    assert conflicted.selected_scenario is None
    assert "MACRO_STRUCTURE_CONFLICT" in conflicted.blockers

    forming = engine.build(
        _costed_snapshot(),
        _evidence_results(include_trigger=False),
    )
    assert forming.selected_scenario is not None
    assert forming.selected_scenario.state is ScenarioState.FORMING
    assert forming.selected_scenario.confidence == 0.0
    (candidate,) = engine.bind_candidates((_candidate(),), forming)
    assert candidate.status is CandidateStatus.WAIT_FOR_RETEST
    assert "SCENARIO_CONFIRMATION_PENDING" in candidate.blockers


def test_competing_scenarios_require_minimum_separation() -> None:
    results = _evidence_results()
    results["price_action"] = _result(
        "price_action",
        vote=-1.0,
        confidence=0.6,
        evidence=("BEARISH_ENGULFING:15m",),
    )

    state = TradingIntelligenceEngine(minimum_scenario_separation=0.7).build(
        technical_snapshot(), results
    )

    assert len(state.scenarios) == 2
    assert state.selected_scenario is None
    assert "SCENARIO_SEPARATION_INSUFFICIENT" in state.blockers


def test_futures_without_derivatives_context_has_no_selected_scenario() -> None:
    snapshot = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    state = TradingIntelligenceEngine().build(snapshot, _evidence_results())

    assert state.selected_scenario is None
    assert state.derivatives_context.status == "BLOCKED"
    assert "FUTURES_DERIVATIVES_CONTEXT_UNAVAILABLE" in state.blockers


def test_typed_futures_context_is_fresh_and_part_of_scenario_confidence() -> None:
    raw = {
        "source_count": 4,
        "as_of": NOW.isoformat(),
        "funding_rate": "0.0001",
        "open_interest": "500000",
        "mark_price": "1.118",
        "index_price": "1.117",
        "taker_buy_sell_ratio": "1.04",
    }
    snapshot = replace(
        technical_snapshot(),
        market_type="USD_M_FUTURES",
        derivatives_snapshot=raw,
    )
    derivatives_result = _result(
        "derivatives",
        confidence=0.4,
        metadata={
            "source_count": 4,
            "as_of": NOW.isoformat(),
        },
    )
    results = {**_evidence_results(), "derivatives": derivatives_result}

    state = TradingIntelligenceEngine().build(snapshot, results)

    assert state.derivatives_context.status == "AVAILABLE"
    assert state.derivatives_context.open_interest == Decimal("500000")
    assert state.derivatives_context.mark_index_divergence is not None
    assert state.derivatives_context.crowding_state == "POSITIVE_FUNDING"
    assert state.selected_scenario is not None
    assert state.selected_scenario.confidence == 0.4
    assert "SOURCED_EXTERNAL_SNAPSHOT" not in state.selected_scenario.evidence_for
    assert "DETERMINISTIC_EVIDENCE" in state.selected_scenario.evidence_for


def test_futures_context_rejects_missing_critical_metric() -> None:
    snapshot = replace(
        technical_snapshot(),
        market_type="USD_M_FUTURES",
        derivatives_snapshot={
            "source_count": 2,
            "as_of": NOW.isoformat(),
            "funding_rate": "0.0001",
            "mark_price": "1.1",
            "index_price": "1.1",
        },
    )
    result = _result(
        "derivatives",
        metadata={"source_count": 2, "as_of": NOW.isoformat()},
    )

    context = FuturesContextEngine().build(snapshot, result)

    assert context.status == "BLOCKED"
    assert "FUTURES_METRIC_MISSING:OPEN_INTEREST" in context.blockers


def test_pattern_fabric_normalizes_lifecycle_without_direction_authority() -> None:
    hypotheses = PatternHypothesisFabric().build(
        technical_snapshot(),
        {
            "fibonacci": _result(
                "fibonacci",
                metadata={"retracement_zone": "MID_RETRACEMENT_ZONE"},
            ),
            "elliott_wave": _result(
                "elliott_wave",
                metadata={"heuristic": "ALTERNATING_SWINGS_PROXY"},
            ),
            "price_action": _result("price_action"),
        },
    )

    lifecycle_by_family = {item.family: item.lifecycle_state for item in hypotheses}
    assert lifecycle_by_family == {
        "ELLIOTT_WAVE": PatternLifecycleState.ALTERNATIVE_UNRESOLVED.value,
        "FIBONACCI": PatternLifecycleState.CONTEXT_ONLY.value,
        "PRICE_ACTION": PatternLifecycleState.CONFIRMED.value,
    }
    assert all(item.primary_direction_signal is False for item in hypotheses)
    assert all(item.execution_allowed is False for item in hypotheses)


def test_futures_risk_requires_net_rr_and_expected_r_requires_calibration() -> None:
    candidate = replace(_candidate(), market_type="USD_M_FUTURES")
    assessment = RiskEngine().evaluate(
        candidate,
        replace(technical_snapshot(), market_type="USD_M_FUTURES"),
        RiskContext(equity_usdt=Decimal("1000")),
        symbol_filters(),
    )

    assert "FUTURES_NET_RISK_REWARD_UNAVAILABLE" in assessment.blockers
    with pytest.raises(ValueError, match="OOS-calibrated"):
        replace(candidate, expected_r=Decimal("0.4"))


def test_cost_model_produces_net_rr_without_overwriting_structural_rr() -> None:
    base = technical_snapshot()
    snapshot = replace(
        base,
        market_metadata={
            **base.market_metadata,
            "estimated_fee_ratio": "0.001",
            "estimated_slippage_ratio": "0.001",
        },
    )
    engine = TradingIntelligenceEngine()
    state = engine.build(snapshot, _evidence_results())

    (candidate,) = engine.bind_candidates((_candidate(),), state)

    assert state.estimated_round_trip_cost_ratio is not None
    assert state.cost_blockers == ()
    assert candidate.structural_risk_reward == Decimal("1.1875")
    assert candidate.net_risk_reward is not None
    assert candidate.net_risk_reward < candidate.gross_risk_reward
    assert candidate.estimated_round_trip_cost_ratio == (
        state.estimated_round_trip_cost_ratio
    )


def test_confirmed_swings_are_available_only_after_right_side_closes() -> None:
    prices = (
        "10",
        "11",
        "12",
        "11",
        "10",
        "9",
        "10",
        "11",
        "13",
        "12",
        "11",
        "10",
        "11",
        "12",
        "14",
        "13",
        "12",
        "11",
        "12",
        "13",
        "15",
        "14",
        "13",
        "12",
    )
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(hours=len(prices) - index),
            open=Decimal(price),
            high=Decimal(price) + Decimal("0.2"),
            low=Decimal(price) - Decimal("0.2"),
            close=Decimal(price),
            volume=Decimal("100"),
        )
        for index, price in enumerate(prices)
    )

    structure = MarketStructureEngine().analyze("1h", candles)

    assert structure.swings
    for swing in structure.swings:
        assert swing.available_at == candles[swing.candle_index + 2].timestamp
        assert swing.available_at > swing.occurred_at


def test_simulated_leverage_governor_is_oos_and_margin_bound() -> None:
    governor = VirtualPortfolioRiskGovernor(maximum_futures_leverage=5)
    eligible = governor.assess_simulated_leverage(
        requested_leverage=3,
        position_notional_usdt=Decimal("2000"),
        available_margin_usdt=Decimal("1000"),
        margin_utilization_ratio=Decimal("0.2"),
        strategy_oos_approved=True,
    )
    reduced = governor.assess_simulated_leverage(
        requested_leverage=10,
        position_notional_usdt=Decimal("2000"),
        available_margin_usdt=Decimal("1000"),
        margin_utilization_ratio=Decimal("0.2"),
        strategy_oos_approved=True,
    )
    blocked = governor.assess_simulated_leverage(
        requested_leverage=3,
        position_notional_usdt=Decimal("2000"),
        available_margin_usdt=Decimal("1000"),
        margin_utilization_ratio=Decimal("0.2"),
        strategy_oos_approved=False,
    )

    assert eligible.state is SimulatedLeverageState.ELIGIBLE
    assert eligible.permitted_leverage == 3
    assert reduced.state is SimulatedLeverageState.REDUCED
    assert reduced.permitted_leverage == 5
    assert blocked.state is SimulatedLeverageState.BLOCKED
    assert blocked.execution_allowed is False
    assert "SIMULATED_LEVERAGE_OOS_APPROVAL_MISSING" in blocked.blockers


def test_orchestrator_projects_one_shared_intelligence_state() -> None:
    state = EnterpriseOrchestrator(minimum_candles=50).analyze(technical_snapshot())

    assert state.trading_intelligence is not None
    assert state.trading_intelligence.snapshot_id == state.snapshot_id
    assert state.trading_intelligence.symbol == state.symbol
    assert state.trading_intelligence.execution_allowed is False
    assert state.trading_intelligence.levels
    assert state.trading_intelligence.trend_geometry
    geometry = state.trading_intelligence.trend_geometry[0]
    assert geometry.anchor_points
    assert geometry.touch_count > 0
    assert geometry.atr_normalized_error >= Decimal("0")
    assert all(
        level.price_low < level.price_high
        for level in state.trading_intelligence.levels
    )
    assert all(level.touch_count >= 1 for level in state.trading_intelligence.levels)
    assert state.candidate_setups
    assert all(candidate.scenario_id for candidate in state.candidate_setups)
    assert all(
        candidate.status is not CandidateStatus.READY_FOR_RISK
        for candidate in state.candidate_setups
    )
    selected = state.trading_intelligence.selected_scenario
    assert selected is not None
    assert selected.direction is ScenarioDirection.LONG
    assert selected.state is ScenarioState.FORMING


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_id", "foreign"),
        ("symbol", "BTCUSDT"),
        ("timestamp", NOW - timedelta(minutes=1)),
        ("market_type", "USD_M_FUTURES"),
    ],
)
def test_candidate_binding_rejects_cross_context_identity(
    field: str, value: object
) -> None:
    engine = TradingIntelligenceEngine()
    state = engine.build(_costed_snapshot(), _evidence_results())
    (candidate,) = engine.bind_candidates(
        (replace(_candidate(), **{field: value}),), state
    )
    assert candidate.status is CandidateStatus.RESEARCH_ONLY
    assert "SCENARIO_CANDIDATE_IDENTITY_MISMATCH" in candidate.blockers
    assert candidate.scenario_id is None


def test_identity_failure_exits_before_interpreting_foreign_evidence() -> None:
    results = _evidence_results()
    results["market_structure"] = replace(
        results["market_structure"], snapshot_id="foreign"
    )
    state = TradingIntelligenceEngine().build(technical_snapshot(), results)
    assert state.selected_scenario is None
    assert state.structures == ()
    assert "TRADING_INTELLIGENCE_IDENTITY_MISMATCH:market_structure" in state.blockers


def test_failed_data_quality_cannot_fall_back_to_snapshot_quality() -> None:
    results = _evidence_results()
    results["data_quality"] = replace(_result("data_quality"), blockers=("STALE_DATA",))
    state = TradingIntelligenceEngine().build(technical_snapshot(), results)
    assert state.selected_scenario is None
    assert "SCENARIO_DATA_QUALITY_UNAVAILABLE" in state.blockers


@pytest.mark.parametrize("evidence", [("BULLISH_ENGULFING:1d",), ("UNKNOWN_TRIGGER",)])
def test_non_execution_timeframe_cannot_confirm_entry(
    evidence: tuple[str, ...],
) -> None:
    results = _evidence_results()
    results["price_action"] = _result("price_action", evidence=evidence)
    state = TradingIntelligenceEngine().build(_costed_snapshot(), results)
    assert state.selected_scenario is not None
    assert state.selected_scenario.state is ScenarioState.FORMING


def test_conflicting_entry_timeframes_cannot_be_averaged_away() -> None:
    results = _evidence_results()
    results["price_action"] = _result(
        "price_action",
        vote=0,
        evidence=("BULLISH_ENGULFING:15m", "BEARISH_ENGULFING:5m"),
    )
    state = TradingIntelligenceEngine().build(_costed_snapshot(), results)
    assert state.selected_scenario is None
    assert "ENTRY_TRIGGER_CONFLICT" in state.blockers


@pytest.mark.parametrize("lifecycle", ["FAILED", "INVALIDATED", "FORMING", "UNKNOWN"])
def test_unconfirmed_trigger_lifecycle_cannot_confirm_scenario(lifecycle: str) -> None:
    results = _evidence_results()
    results["price_action"] = replace(
        results["price_action"], calculation_metadata={"lifecycle_state": lifecycle}
    )
    state = TradingIntelligenceEngine().build(_costed_snapshot(), results)
    assert state.selected_scenario is not None
    assert state.selected_scenario.state is ScenarioState.FORMING
    assert not any(
        item.startswith("pattern:") for item in state.selected_scenario.evidence_for
    )


def test_missing_costs_deny_spot_candidate_and_preserve_missing_provenance() -> None:
    engine = TradingIntelligenceEngine()
    state = engine.build(technical_snapshot(), _evidence_results())
    (candidate,) = engine.bind_candidates((_candidate(),), state)
    assert candidate.status is CandidateStatus.RESEARCH_ONLY
    assert candidate.entry_state == "ENTRY_NOT_READY"
    assert "NET_RISK_REWARD_UNAVAILABLE" in candidate.blockers
    assert candidate.target_sources == ()


def test_zero_fee_is_valid_and_net_rr_includes_loss_side_costs() -> None:
    snapshot = replace(
        _costed_snapshot(),
        market_metadata={
            "estimated_fee_ratio": 0,
            "fee_ratio": "0.05",
            "estimated_slippage_ratio": 0,
        },
    )
    engine = TradingIntelligenceEngine()
    state = engine.build(snapshot, _evidence_results())
    assert (
        state.estimated_round_trip_cost_ratio == snapshot.spread / snapshot.latest_price
    )
    (candidate,) = engine.bind_candidates((_candidate(),), state)
    assert candidate.net_risk_reward == (
        Decimal("0.19") - candidate.entry_price * state.estimated_round_trip_cost_ratio
    ) / candidate_risk_distance(candidate)


def test_validation_rechecks_candidate_and_requires_sizing_evidence() -> None:
    engine = TradingIntelligenceEngine()
    snapshot = _costed_snapshot()
    (candidate,) = engine.bind_candidates(
        (_candidate(),), engine.build(snapshot, _evidence_results())
    )
    candidate = replace(
        candidate, status=CandidateStatus.RESEARCH_ONLY, blockers=("REVOKED_EVIDENCE",)
    )
    results = {
        "risk": _result(
            "risk",
            metadata={
                "candidate_id": candidate.candidate_id,
                "scenario_id": candidate.scenario_id,
                "approved": True,
            },
        )
    }
    signal = ValidationGate().validate(snapshot, results, candidates=(candidate,))
    assert "REVOKED_EVIDENCE" in signal.blockers
    assert "RISK_SIZING_EVIDENCE_INVALID" in signal.blockers
    assert "RISK_APPROVAL_MISSING" in signal.blockers
    assert signal.execution_allowed is False


def test_risk_rejects_forged_scenario_net_rr() -> None:
    engine = TradingIntelligenceEngine()
    snapshot = _costed_snapshot()
    (candidate,) = engine.bind_candidates(
        (_candidate(),), engine.build(snapshot, _evidence_results())
    )
    assessment = RiskEngine().evaluate(
        replace(candidate, net_risk_reward=Decimal("99")),
        snapshot,
        RiskContext(equity_usdt=Decimal("1000")),
        symbol_filters(),
    )
    assert assessment.approved is False
    assert "NET_RISK_REWARD_INCONSISTENT" in assessment.blockers


def test_shared_state_rejects_cross_snapshot_scenarios() -> None:
    state = TradingIntelligenceEngine().build(_costed_snapshot(), _evidence_results())
    with pytest.raises(ValueError, match="snapshot identity"):
        replace(state, scenarios=(replace(state.scenarios[0], snapshot_id="foreign"),))
    with pytest.raises(ValueError, match="blocked intelligence"):
        replace(state, blockers=("REVOKED",))


@pytest.mark.parametrize(
    "invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
)
def test_nonfinite_risk_contracts_fail_closed(invalid: Decimal) -> None:
    with pytest.raises(ValueError, match="equity_usdt"):
        RiskContext(equity_usdt=invalid)
    with pytest.raises(ValueError, match="risk assessment"):
        RiskAssessment("candidate", False, invalid)
    with pytest.raises(ValueError, match="stop_loss"):
        replace(_candidate(), stop_loss=invalid)
    assessment = VirtualPortfolioRiskGovernor().assess_simulated_leverage(
        requested_leverage=3,
        position_notional_usdt=invalid,
        available_margin_usdt=Decimal("1000"),
        margin_utilization_ratio=Decimal("0"),
        strategy_oos_approved=True,
    )
    assert assessment.state is SimulatedLeverageState.BLOCKED


def test_risk_assessment_retains_positional_compatibility() -> None:
    assessment = RiskAssessment(
        "candidate", True, Decimal("100"), Decimal("1"), Decimal("5")
    )
    assert assessment.size_usdt == Decimal("100")
    assert assessment.scenario_id is None


def test_trend_break_is_evaluated_outside_its_fitted_window() -> None:
    snapshot = technical_snapshot()
    candles = tuple(snapshot.ohlcv_by_timeframe["1d"])
    last = replace(candles[-1], close=Decimal("2"), high=Decimal("2.1"))
    snapshot = replace(
        snapshot,
        ohlcv_by_timeframe={**snapshot.ohlcv_by_timeframe, "1d": (*candles[:-1], last)},
    )
    (geometry,) = TrendGeometryEngine().build(
        snapshot, (), _result("trend_channel", metadata={"source_timeframe": "1d"})
    )
    assert geometry.state == "TRENDLINE_BREAK"
    assert geometry.break_state == "BROKEN"
    assert geometry.anchor_points[-1][0] == candles[-3].timestamp
    assert geometry.anchor_points[-1][1] == geometry.intercept + geometry.slope * 27


def test_entry_expiry_overflow_returns_unavailable() -> None:
    assert TradingIntelligenceEngine._entry_expiry(NOW, "999999999999999999d") is None


def test_futures_context_rejects_foreign_agent_identity() -> None:
    context = FuturesContextEngine().build(
        replace(technical_snapshot(), market_type="USD_M_FUTURES"),
        replace(_result("derivatives"), snapshot_id="foreign"),
    )
    assert context.blockers == ("FUTURES_DERIVATIVES_IDENTITY_MISMATCH",)

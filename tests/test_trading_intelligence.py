"""Deterministic Trading Intelligence evidence-chain tests."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
)
from ai4binance.intelligence.contracts import (
    CalibrationState,
    ScenarioDirection,
    ScenarioState,
    ScenarioType,
    StructureState,
)
from ai4binance.intelligence.structure import MarketStructureEngine
from ai4binance.intelligence.trading import TradingIntelligenceEngine
from ai4binance.risk import RiskContext, RiskEngine
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
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


def test_confirmed_scenario_uses_weakest_confidence_and_binds_candidate() -> None:
    engine = TradingIntelligenceEngine()
    state = engine.build(technical_snapshot(), _evidence_results())

    assert state.selected_scenario is not None
    assert state.selected_scenario.scenario_type is ScenarioType.LONG_CONTINUATION
    assert state.selected_scenario.state is ScenarioState.CONFIRMED
    assert state.selected_scenario.confidence == 0.6
    assert state.selected_scenario.calibration_state is CalibrationState.NOT_CALIBRATED
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
    assert candidate.structural_risk_reward == Decimal("1.7")
    assert candidate.net_risk_reward is None
    assert candidate.expected_r is None
    assert candidate.probability_calibration_state == "PROBABILITY_NOT_CALIBRATED"


def test_macro_conflict_and_missing_trigger_fail_closed() -> None:
    engine = TradingIntelligenceEngine()
    conflicted = engine.build(
        technical_snapshot(),
        _evidence_results(macro_state=StructureState.BEARISH),
    )
    assert conflicted.selected_scenario is None
    assert "MACRO_STRUCTURE_CONFLICT" in conflicted.blockers

    forming = engine.build(
        technical_snapshot(),
        _evidence_results(include_trigger=False),
    )
    assert forming.selected_scenario is not None
    assert forming.selected_scenario.state is ScenarioState.FORMING
    assert forming.selected_scenario.confidence == 0.0
    (candidate,) = engine.bind_candidates((_candidate(),), forming)
    assert candidate.status is CandidateStatus.WAIT_FOR_RETEST
    assert "SCENARIO_CONFIRMATION_PENDING" in candidate.blockers


def test_futures_without_derivatives_context_has_no_selected_scenario() -> None:
    snapshot = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    state = TradingIntelligenceEngine().build(snapshot, _evidence_results())

    assert state.selected_scenario is None
    assert state.derivatives_context.status == "BLOCKED"
    assert "FUTURES_DERIVATIVES_CONTEXT_UNAVAILABLE" in state.blockers


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


def test_orchestrator_projects_one_shared_intelligence_state() -> None:
    state = EnterpriseOrchestrator(minimum_candles=50).analyze(technical_snapshot())

    assert state.trading_intelligence is not None
    assert state.trading_intelligence.snapshot_id == state.snapshot_id
    assert state.trading_intelligence.symbol == state.symbol
    assert state.trading_intelligence.execution_allowed is False
    assert state.trading_intelligence.levels
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

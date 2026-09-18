"""Deterministic agent execution and orchestration tests."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.data_quality_gate import DataQualityGate
from ai4binance.agents.evidence_fusion import EvidenceFusionEngine
from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.agents.risk_gate import RiskGate
from ai4binance.agents.specialists import (
    ConfluenceAgent,
    DataQualityAgent,
    ResearchOnlyAgent,
    RiskAgent,
    UniverseLiquidityAgent,
)
from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate
from ai4binance.agents.validation import ValidationAgent
from ai4binance.agents.validation_gate import ValidationGate
from ai4binance.domain import Decision
from ai4binance.reporting import to_primitive
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
)
from tests.test_technical_agents import technical_snapshot

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


def candle(hours_ago: int, *, volume: str = "100") -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=NOW - timedelta(hours=hours_ago),
        open=Decimal("1.00"),
        high=Decimal("1.10"),
        low=Decimal("0.90"),
        close=Decimal("1.05"),
        volume=Decimal(volume),
    )


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id="snapshot-agent-test",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": (candle(2), candle(1))},
        latest_price=Decimal("1.05"),
        bid=Decimal("1.049"),
        ask=Decimal("1.051"),
        spread=Decimal("0.002"),
        exchange_filters={"PRICE_FILTER": {"tickSize": "0.001"}},
        data_freshness={"1h": {"stale": False}},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={"trading_status": "TRADING"},
    )


def eligibility_results(
    market_snapshot: MarketSnapshot,
) -> dict[str, AgentResult]:
    registry = build_default_registry()
    results: dict[str, AgentResult] = {}
    data_agent = DataQualityAgent(registry.get("data_quality"))
    results["data_quality"] = data_agent.run(market_snapshot, results)
    universe_agent = UniverseLiquidityAgent(registry.get("universe_liquidity"))
    results["universe_liquidity"] = universe_agent.run(market_snapshot, results)
    return results


def test_data_quality_agent_validates_and_degrades_candles() -> None:
    registry = build_default_registry()
    agent = DataQualityAgent(registry.get("data_quality"))
    valid = agent.run(snapshot(), {})
    assert valid.status is AgentStatus.SUCCESS
    assert valid.data_quality is DataQuality.DATA_VALID

    gate = DataQualityGate(registry.get("data_quality"))
    assert gate.evaluate(snapshot()) == valid

    zero_volume_snapshot = replace(
        snapshot(),
        ohlcv_by_timeframe={"1h": (candle(2, volume="0"), candle(1))},
    )
    degraded = agent.run(zero_volume_snapshot, {})
    assert degraded.status is AgentStatus.PARTIAL
    assert degraded.data_quality is DataQuality.DATA_DEGRADED
    assert degraded.warnings == ("ZERO_VOLUME:1h",)
    assert gate.evaluate(zero_volume_snapshot) == degraded


def test_data_quality_agent_blocks_duplicate_stale_and_missing_history() -> None:
    registry = build_default_registry()
    agent = DataQualityAgent(registry.get("data_quality"))
    duplicate = candle(1)
    invalid = replace(
        snapshot(),
        ohlcv_by_timeframe={"1h": (duplicate, duplicate)},
        data_freshness={"1h": {"stale": True}},
    )
    result = agent.run(invalid, {})
    assert result.status is AgentStatus.BLOCKED
    assert "DUPLICATE_CANDLES:1h" in result.blockers
    assert "OUT_OF_ORDER_CANDLES:1h" in result.blockers
    assert "STALE_CANDLES:1h" in result.blockers

    missing = replace(snapshot(), ohlcv_by_timeframe={})
    result = agent.run(missing, {})
    assert result.blockers == ("INSUFFICIENT_CANDLES:1h",)


def test_universe_liquidity_agent_blocks_wide_spread_and_missing_filters() -> None:
    registry = build_default_registry()
    data_result = DataQualityAgent(registry.get("data_quality")).run(snapshot(), {})
    agent = UniverseLiquidityAgent(registry.get("universe_liquidity"))
    valid = agent.run(snapshot(), {"data_quality": data_result})
    assert valid.status is AgentStatus.SUCCESS

    gate = UniverseLiquidityGate(registry.get("universe_liquidity"))
    assert gate.evaluate(snapshot(), {"data_quality": data_result}) == valid
    dependency_blocked = gate.evaluate(snapshot(), {})
    assert dependency_blocked.blockers == ("DEPENDENCY_NOT_READY:data_quality",)
    assert dependency_blocked.reason_codes == ("AGENT_DEPENDENCY_BLOCKED",)

    invalid_snapshot = replace(
        snapshot(),
        spread=Decimal("0.1"),
        exchange_filters={},
        market_metadata={},
    )
    blocked = agent.run(invalid_snapshot, {"data_quality": data_result})
    assert blocked.status is AgentStatus.BLOCKED
    assert "SPREAD_EXCEEDS_LIMIT" in blocked.blockers
    assert "EXCHANGE_FILTERS_MISSING" in blocked.blockers


def test_research_only_agent_never_generates_signal_evidence() -> None:
    registry = build_default_registry()
    results = eligibility_results(snapshot())
    agent = ResearchOnlyAgent(registry.get("ichimoku"))
    result = agent.run(snapshot(), results)
    assert result.status is AgentStatus.INSUFFICIENT_DATA
    assert result.applicable is False
    assert result.hard_gate_eligible is False
    assert result.directional_vote == 0.0


class ExplodingAgent(BaseAgent):
    def analyze(
        self,
        market_snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del market_snapshot, prior_results
        raise RuntimeError("secret detail must not escape")


class WrongIdentityAgent(BaseAgent):
    def analyze(
        self,
        market_snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        result = self.result(
            market_snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=DataQuality.DATA_VALID,
            applicable=True,
            reason_codes=("TEST",),
        )
        return replace(result, agent_name="wrong")


class ReadyResultAgent(BaseAgent):
    """Minimal deterministic capability implementation for bundle scheduling tests."""

    def analyze(
        self,
        market_snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        return self.result(
            market_snapshot,
            status=AgentStatus.SUCCESS,
            data_quality=DataQuality.DATA_VALID,
            applicable=True,
            reason_codes=("BUNDLE_TEST",),
        )


class ImmediateFuture:
    """Synchronous future used to observe deterministic scheduler submissions."""

    def __init__(self, value: object) -> None:
        self._value = value

    def result(self) -> object:
        return self._value


class RecordingBundleExecutor:
    """Inline executor that records bundle task submissions without threads."""

    def __init__(self) -> None:
        self.bundle_ids: list[str] = []

    def submit(
        self,
        function: Callable[..., object],
        /,
        *args: object,
    ) -> ImmediateFuture:
        bound_instance = cast(Any, function).__self__
        self.bundle_ids.append(bound_instance.definition.bundle_id)
        return ImmediateFuture(function(*args))


def test_base_agent_fails_closed_and_checks_identity() -> None:
    definition = build_default_registry().get("data_quality")
    failed = ExplodingAgent(definition).run(snapshot(), {})
    assert failed.status is AgentStatus.FAILED
    assert failed.blockers == ("AGENT_INTERNAL_ERROR",)
    assert failed.calculation_metadata["error_type"] == "RuntimeError"
    assert "secret" not in str(to_primitive(failed))

    mismatch = WrongIdentityAgent(definition).run(snapshot(), {})
    assert mismatch.status is AgentStatus.FAILED
    assert mismatch.blockers == ("AGENT_IDENTITY_MISMATCH",)


def test_orchestrator_submits_ready_capabilities_once_per_bundle() -> None:
    registry = build_default_registry()
    orchestrator = EnterpriseOrchestrator(max_workers=1)
    bundle_executor = RecordingBundleExecutor()
    results = eligibility_results(snapshot())
    agents = (
        ReadyResultAgent(registry.get("multi_timeframe")),
        ReadyResultAgent(registry.get("market_regime")),
        ReadyResultAgent(registry.get("momentum")),
    )

    _, bundle_task_count = orchestrator._run_dependency_layers(
        snapshot(),
        agents,
        results,
        bundle_executor,  # type: ignore[arg-type]
    )

    assert bundle_task_count == 2
    assert bundle_executor.bundle_ids == ["market_state", "momentum_participation"]
    assert tuple(results)[-3:] == ("market_regime", "momentum", "multi_timeframe")
    assert all(
        results[name].status is AgentStatus.SUCCESS
        for name in ("market_regime", "momentum", "multi_timeframe")
    )


def agent_result(name: str, score: float, confidence: float) -> AgentResult:
    return AgentResult(
        agent_name=name,
        agent_version="0.1.0",
        snapshot_id=snapshot().snapshot_id,
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframes=("1h",),
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=0.5,
        score=score,
        confidence=confidence,
        reason_codes=("TEST_EVIDENCE",),
    )


def test_confluence_counts_independent_clusters_only() -> None:
    registry = build_default_registry()
    agent = ConfluenceAgent(registry.get("confluence"), registry=registry)
    results = eligibility_results(snapshot())
    results.update(
        {
            "trend": agent_result("trend", 70.0, 0.5),
            "moving_average": agent_result("moving_average", 80.0, 0.9),
            "volume": agent_result("volume", 60.0, 0.8),
        }
    )
    result = agent.run(snapshot(), results)
    assert result.status is AgentStatus.PARTIAL
    assert result.evidence == ("volume", "moving_average")
    assert result.calculation_metadata["independent_confluence_count"] == 2
    assert result.calculation_metadata["selected_agents"] == result.evidence
    assert result.calculation_metadata["rejected_correlated_agents"] == ("trend",)
    assert result.calculation_metadata["directional_agreement"] == 1.0

    engine_result = EvidenceFusionEngine(
        registry.get("confluence"),
        registry,
    ).fuse(snapshot(), results)
    assert engine_result == result


def test_evidence_fusion_engine_preserves_fail_closed_dependency_contract() -> None:
    registry = build_default_registry()
    result = EvidenceFusionEngine(
        registry.get("confluence"),
        registry,
    ).fuse(snapshot(), {})

    assert result.status is AgentStatus.BLOCKED
    assert result.blockers == (
        "DEPENDENCY_NOT_READY:data_quality",
        "DEPENDENCY_NOT_READY:universe_liquidity",
    )
    assert result.reason_codes == ("AGENT_DEPENDENCY_BLOCKED",)
    assert result.hard_gate_eligible is False


def test_risk_agent_blocks_without_complete_trade_plan() -> None:
    registry = build_default_registry()
    agent = RiskAgent(registry.get("risk"))
    result = agent.analyze(snapshot(), {})
    assert result.status is AgentStatus.BLOCKED
    assert result.blockers == ("TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",)

    gate = RiskGate(registry.get("risk"))
    assert gate.evaluate_candidates(snapshot()) == result
    dependency_blocked = gate.evaluate(snapshot(), {})
    assert dependency_blocked.blockers == ("DEPENDENCY_NOT_READY:confluence",)
    assert dependency_blocked.reason_codes == ("AGENT_DEPENDENCY_BLOCKED",)


def test_validation_gate_preserves_research_only_facade_contract() -> None:
    gate = ValidationGate()
    facade = ValidationAgent()

    result = gate.validate(snapshot(), {}, extra_blockers=("TEST_BLOCKER",))

    assert facade.validate(snapshot(), {}, extra_blockers=("TEST_BLOCKER",)) == result
    assert result.execution_allowed is False
    assert result.validation_status.value == "REJECTED"
    assert result.reason_codes == ("VALIDATION_REJECTED", "NO_TRADE_CAPITAL_PROTECTION")
    assert result.blockers == (
        "TEST_BLOCKER",
        "BACKTEST_APPROVAL_MISSING",
        "WALK_FORWARD_APPROVAL_MISSING",
        "OOS_APPROVAL_MISSING",
        "RISK_APPROVAL_MISSING",
    )


def test_risk_agent_evaluates_arbitrated_candidate_and_invalid_filters() -> None:
    from tests.test_strategy_risk import approved_candidate
    from tests.test_strategy_risk import snapshot as strategy_snapshot

    registry = build_default_registry()
    agent = RiskAgent(registry.get("risk"), candidates=(approved_candidate(),))

    evaluated = agent.analyze(strategy_snapshot(), {})

    assert evaluated.status is AgentStatus.BLOCKED
    assert evaluated.blockers == ("EQUITY_UNKNOWN",)
    assert evaluated.calculation_metadata["evaluated_candidate_count"] == 1
    assert evaluated.calculation_metadata["candidate_id"] == "candidate-1"

    invalid_filters = replace(
        strategy_snapshot(),
        exchange_filters={"LOT_SIZE": "invalid"},
    )
    rejected = agent.analyze(invalid_filters, {})
    assert rejected.status is AgentStatus.BLOCKED
    assert rejected.blockers == ("EXCHANGE_FILTERS_INVALID",)


def test_orchestrator_early_exit_and_full_research_cycle_are_fail_closed() -> None:
    orchestrator = EnterpriseOrchestrator(max_workers=4)
    invalid_snapshot = replace(snapshot(), data_quality=DataQuality.DATA_INVALID)
    early = orchestrator.analyze(invalid_snapshot)
    assert tuple(early.agent_results) == ("data_quality",)
    assert "EARLY_EXIT_NO_TRADE" in early.blockers

    ineligible_snapshot = replace(snapshot(), exchange_filters={})
    liquidity_exit = orchestrator.analyze(ineligible_snapshot)
    assert tuple(liquidity_exit.agent_results) == (
        "data_quality",
        "universe_liquidity",
    )
    assert "EARLY_EXIT_NO_TRADE" in liquidity_exit.blockers

    state = orchestrator.analyze(snapshot())
    assert len(state.agent_results) == 38
    assert state.final_decision is not None
    assert state.final_decision.decision_state is Decision.NO_TRADE
    assert state.final_decision.execution_allowed is False
    assert state.agent_results["trend"].status is AgentStatus.INSUFFICIENT_DATA
    assert state.agent_results["harmonic_pattern"].status is AgentStatus.NOT_APPLICABLE
    assert state.agent_results["harmonic_pattern"].reason_codes == (
        "DEPENDENCY_NOT_SCHEDULED:fibonacci",
    )
    assert state.agent_results["confluence"].status is AgentStatus.BLOCKED


def test_orchestrator_output_is_deterministic_across_parallel_runs() -> None:
    orchestrator = EnterpriseOrchestrator(max_workers=8)
    first = to_primitive(orchestrator.analyze(snapshot()))
    second = to_primitive(orchestrator.analyze(snapshot()))
    assert first == second


def test_real_orchestrator_accepts_partial_breakout_retest_evidence() -> None:
    base = technical_snapshot()
    data: dict[str, tuple[OHLCVCandle, ...]] = {}
    for timeframe, raw_candles in base.ohlcv_by_timeframe.items():
        candles = list(raw_candles)
        resistance = max(item.high for item in candles[-22:-2])
        candles[-2] = OHLCVCandle(
            candles[-2].timestamp,
            resistance + Decimal("0.020"),
            resistance + Decimal("0.021"),
            resistance + Decimal("0.009"),
            resistance + Decimal("0.010"),
            Decimal("200"),
        )
        candles[-1] = OHLCVCandle(
            candles[-1].timestamp,
            resistance + Decimal("0.009"),
            resistance + Decimal("0.031"),
            resistance - Decimal("0.001"),
            resistance + Decimal("0.030"),
            Decimal("250"),
        )
        data[timeframe] = tuple(candles)
    latest = data["1h"][-1].close
    market = replace(
        base,
        snapshot_id="orchestrator-breakout",
        ohlcv_by_timeframe=data,
        latest_price=latest,
        bid=latest - Decimal("0.0001"),
        ask=latest + Decimal("0.0001"),
    )

    state = EnterpriseOrchestrator(minimum_candles=50).analyze(market)

    assert state.agent_results["confluence"].status is AgentStatus.PARTIAL
    assert state.agent_results["breakout_retest"].status is AgentStatus.PARTIAL
    assert "breakout_retest" in {item.setup_name for item in state.candidate_setups}
    assert state.final_decision is not None
    assert state.final_decision.execution_allowed is False


@pytest.mark.parametrize("max_workers", [0, 33])
def test_orchestrator_rejects_unbounded_worker_configuration(
    max_workers: int,
) -> None:
    with pytest.raises(ValueError, match="max_workers"):
        EnterpriseOrchestrator(max_workers=max_workers)


def test_orchestrator_rejects_too_small_history_configuration() -> None:
    with pytest.raises(ValueError, match="minimum_candles"):
        EnterpriseOrchestrator(minimum_candles=1)

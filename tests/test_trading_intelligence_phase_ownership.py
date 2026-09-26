"""P0--P14 ownership and non-authoritative intelligence contracts."""

from decimal import Decimal

from ai4binance.intelligence.contracts import (
    PatternHypothesisEvidence,
    PatternLifecycleState,
    ScenarioDirection,
)
from ai4binance.intelligence.inventory import TradingIntelligenceInventory
from ai4binance.intelligence.patterns import (
    ElliottWaveHypothesisEngine,
    FibonacciConfluenceEngine,
    HarmonicPatternEngine,
)
from ai4binance.intelligence.plan import RiskRewardEngine, TradePlanEngine
from ai4binance.intelligence.trading import ScenarioEngine, TradingIntelligenceEngine
from ai4binance.research.virtual_runtime_risk import FuturesLeverageGovernor


def _evidence(
    family: str,
    *,
    direction: ScenarioDirection = ScenarioDirection.LONG,
    attributes: tuple[tuple[str, str], ...] = (),
) -> PatternHypothesisEvidence:
    return PatternHypothesisEvidence(
        hypothesis_id=f"pattern:test:{family}",
        family=family,
        direction=direction,
        lifecycle_state=PatternLifecycleState.FORMING.value,
        confidence=0.6,
        evidence_for=("TEST_DETECTOR_EVIDENCE",),
        attributes=attributes,
    )


def test_p0_p14_inventory_is_complete_ordered_and_importable() -> None:
    inventory = TradingIntelligenceInventory()

    inventory.validate()

    assert tuple(item.phase for item in inventory.phases) == tuple(
        f"P{index}" for index in range(15)
    )


def test_p5_fibonacci_is_neutral_confluence_only() -> None:
    result = FibonacciConfluenceEngine().build(_evidence("FIBONACCI"))

    assert result.direction is ScenarioDirection.NEUTRAL
    assert result.lifecycle_state == PatternLifecycleState.CONTEXT_ONLY.value
    assert ("role", "CONFLUENCE_ONLY") in result.attributes
    assert result.execution_allowed is False


def test_p5_harmonic_geometry_invalidates_without_trade_authority() -> None:
    result = HarmonicPatternEngine().build(
        _evidence("HARMONIC_PATTERN", attributes=(("ab_cd", "1.0"),))
    )

    assert result.geometry_quality == 1.0
    assert result.execution_allowed is False
    assert result.primary_direction_signal is False


def test_p6_elliott_does_not_invent_unobserved_alternatives() -> None:
    alternatives = ElliottWaveHypothesisEngine().build(_evidence("ELLIOTT_WAVE"))

    assert tuple(item.attributes[-1] for item in alternatives) == (
        ("alternative", "OBSERVED_COUNT"),
    )
    assert all(
        item.lifecycle_state == PatternLifecycleState.ALTERNATIVE_UNRESOLVED.value
        and item.execution_allowed is False
        for item in alternatives
    )


def test_p8_p10_have_one_actual_scenario_plan_and_rr_owner() -> None:
    assert TradingIntelligenceEngine is ScenarioEngine
    assert isinstance(ScenarioEngine().trade_plan_engine, TradePlanEngine)
    assert isinstance(TradePlanEngine().risk_reward_engine, RiskRewardEngine)


def test_p11_leverage_governor_remains_oos_bound_and_non_executable() -> None:
    assessment = FuturesLeverageGovernor(
        maximum_futures_leverage=5
    ).assess_simulated_leverage(
        requested_leverage=3,
        position_notional_usdt=Decimal("2000"),
        available_margin_usdt=Decimal("1000"),
        margin_utilization_ratio=Decimal("0.2"),
        strategy_oos_approved=False,
    )

    assert assessment.execution_allowed is False
    assert "SIMULATED_LEVERAGE_OOS_APPROVAL_MISSING" in assessment.blockers

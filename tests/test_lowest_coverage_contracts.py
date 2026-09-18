"""Boundary coverage for the lowest-ranked deterministic contract modules."""

# mypy: disable-error-code="arg-type,assignment"

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import nan
from typing import cast

import pytest

from ai4binance.agents.context_budget import (
    BoundedContextAssembler,
    ConservativeTokenEstimator,
    ContextAssembly,
    ContextBudgetExceededError,
    ContextFragment,
    TokenBudget,
    TokenBudgetGuard,
    TokenUsage,
)
from ai4binance.core.contracts.virtual_governance import (
    DGE_APPROVED_PAPER_ONLY,
    VirtualGovernanceResult,
)
from ai4binance.domain import ValidationStatus
from ai4binance.governance.risk_assessment import (
    RiskAssessmentV2Contract,
    RiskAssessmentV2Result,
    RiskControlEffectiveness,
    RiskControlStatus,
    RiskEvidenceStatus,
    RiskRating,
)
from ai4binance.learning.models import (
    ExperimentCandidate,
    FailureAnalysis,
    LearningSummary,
    ProfitabilityExperiment,
    ProfitabilityMetric,
    ProfitabilityOptimizationLoop,
    StrategyRegimeAttribution,
)
from ai4binance.research.virtual_runtime_portfolio_state import (
    VirtualPortfolioState,
    VirtualPositionSide,
)
from ai4binance.research.virtual_runtime_risk import VirtualPortfolioRiskGovernor

NOW = datetime(2026, 9, 15, tzinfo=UTC)
HASH = "a" * 64


def test_context_budget_rejects_invalid_limits_and_unsafe_assembly() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TokenBudget(max_context=-1)
    with pytest.raises(ValueError, match="output reserve"):
        TokenBudget(context_window=10, output_reserve=11)
    with pytest.raises(ValueError, match="cannot be negative"):
        TokenUsage(-1, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError, match="cannot authorize"):
        ContextAssembly(
            "", TokenUsage(0, 0, 0, 0, 0, 0), (), (), (), execution_allowed=True
        )


def test_context_budget_guard_covers_each_fail_closed_limit() -> None:
    guard = TokenBudgetGuard(
        TokenBudget(
            context_window=10,
            max_system=1,
            max_current_input=1,
            max_history=1,
            max_context=1,
            max_tool_schemas=1,
            output_reserve=1,
        )
    )
    with pytest.raises(ContextBudgetExceededError, match="SYSTEM_TOKEN"):
        guard.validate(TokenUsage(2, 2, 2, 2, 2, 1))
    guard.validate(TokenUsage(1, 1, 1, 1, 1, 1))
    estimator = ConservativeTokenEstimator()
    assert estimator.count("") == 0
    assert estimator.truncate("abcdef", 0) == ""
    assert estimator.truncate("abcdef", 99) == "abcdef"
    assert estimator.count(estimator.truncate("abcdef", 1)) <= 1


def test_context_assembly_drops_restricted_expired_and_over_budget_fragments() -> None:
    budget = TokenBudget(
        context_window=2_000,
        max_system=10,
        max_current_input=10,
        max_history=10,
        max_context=1_000,
        max_fragment=10,
        max_tool_schemas=10,
        output_reserve=10,
    )
    assembler = BoundedContextAssembler(TokenBudgetGuard(budget))
    with pytest.raises(ValueError, match="source and content"):
        ContextFragment("", "value")
    with pytest.raises(ValueError, match="timezone-aware"):
        ContextFragment("bad", "value", expires_at=datetime(2026, 1, 1))
    result = assembler.assemble(
        system="s",
        current_input="i",
        fragments=(
            ContextFragment("expired", "old", expires_at=NOW - timedelta(days=1)),
            ContextFragment("restricted", "hidden", classification="restricted"),
            ContextFragment("large", "x" * 100, priority=2),
            ContextFragment("small", "ok", priority=1),
        ),
    )
    assert set(result.dropped_sources) == {"expired", "restricted"}
    assert result.truncated_sources == ("large",)
    assert result.kept_sources == ("large", "small")
    with pytest.raises(ContextBudgetExceededError, match="ALL_CONTEXT"):
        BoundedContextAssembler(
            TokenBudgetGuard(
                TokenBudget(max_context=0, context_window=1_000, output_reserve=1)
            )
        ).assemble(
            system="", current_input="", fragments=(ContextFragment("only", "x"),)
        )


def _virtual_governance() -> VirtualGovernanceResult:
    return VirtualGovernanceResult(
        decision_id="decision-1",
        status=DGE_APPROVED_PAPER_ONLY,
        blockers=(),
        simulation_allowed=True,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"decision_id": " "}, "identity"),
        ({"blockers": ("",)}, "cannot be blank"),
        ({"blockers": ("A", "A")}, "must be unique"),
        ({"simulation_allowed": "yes"}, "must be boolean"),
        ({"status": "BLOCKED"}, "requires approved"),
        ({"execution_allowed": True}, "cannot authorize"),
        ({"promotion_status": "APPROVED"}, "cannot authorize"),
    ],
)
def test_virtual_governance_contract_remains_paper_only(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_virtual_governance(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"maximum_risk_per_trade_usdt": Decimal("0")}, "must be positive"),
        ({"maximum_open_risk_usdt": Decimal("-1")}, "must be positive"),
        ({"maximum_drawdown_ratio": Decimal("0")}, "drawdown"),
        ({"maximum_drawdown_ratio": Decimal("2")}, "drawdown"),
        ({"maximum_margin_utilization_ratio": Decimal("2")}, "margin utilization"),
        ({"maximum_consecutive_losses": -1}, "cannot be negative"),
        ({"maximum_futures_leverage": 0}, "must be positive"),
    ],
)
def test_virtual_risk_governor_rejects_every_invalid_limit(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(VirtualPortfolioRiskGovernor(), **changes)


def _attribution() -> StrategyRegimeAttribution:
    return StrategyRegimeAttribution(
        "s", "v1", "trend", 1, 1.1, 0.1, 0.2, 0.3, -0.1, 0.5, 1.2
    )


def _experiment() -> ProfitabilityExperiment:
    return ProfitabilityExperiment("exp-1", "measure", ("OOS",))


def _candidate() -> ExperimentCandidate:
    return ExperimentCandidate(
        "candidate-1",
        "strategy",
        "v1",
        "trend",
        1,
        0.1,
        "range",
        0.0,
        "hypothesis",
        "recommendation",
    )


def _loop() -> ProfitabilityOptimizationLoop:
    return ProfitabilityOptimizationLoop(
        "loop-1",
        (
            "ClosedTrades",
            "EdgeLedger",
            "StrategyRegimeAttribution",
            "FailureAnalysis",
            "ImprovementCandidate",
            "BoundedExperiment",
            "WalkForward",
            "OOS",
            "CostStress",
            "HumanReview",
            "PaperCandidate",
        ),
        (ProfitabilityMetric("metric", 1.0),),
        (_attribution(),),
        (
            FailureAnalysis(
                "failure",
                "class",
                "strategy",
                "trend",
                1,
                0.1,
                -0.1,
                "why",
                "candidate",
            ),
        ),
        (_experiment(),),
        (_candidate(),),
    )


def test_learning_models_reject_nonfinite_and_non_research_variants() -> None:
    with pytest.raises(ValueError, match="identity"):
        ProfitabilityMetric("", 1.0)
    with pytest.raises(ValueError, match="requires a value"):
        ProfitabilityMetric("metric", None)
    with pytest.raises(ValueError, match="finite"):
        ProfitabilityMetric("metric", nan)
    for changes, message in (
        ({"strategy_id": ""}, "identity"),
        ({"regime": ""}, "regime"),
        ({"trade_count": 0}, "requires trades"),
        ({"win_rate": nan}, "finite"),
        ({"profit_factor": nan}, "profit factor"),
        ({"payoff_ratio": nan}, "payoff ratio"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(_attribution(), **changes)
    with pytest.raises(ValueError, match="sample size"):
        replace(
            FailureAnalysis("a", "c", "s", "r", 1, 0.1, 0.2, "why", "id"), sample_size=0
        )
    with pytest.raises(ValueError, match="excursion"):
        replace(
            FailureAnalysis("a", "c", "s", "r", 1, 0.1, 0.2, "why", "id"),
            average_mfe_r=nan,
        )
    for changes, message in (
        ({"required_validation": ()}, "validation"),
        ({"human_review_required": False}, "human review"),
        ({"application_state": "APPLIED"}, "applied"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(_experiment(), **changes)
    for changes, message in (
        ({"sample_size": 0}, "sample size"),
        ({"baseline_expectancy_r": nan}, "expectancy"),
        ({"workflow": ()}, "workflow"),
        ({"status": "PROMOTED"}, "status"),
        ({"promotion_status": ValidationStatus.PAPER_APPROVED}, "research only"),
        ({"execution_allowed": True}, "authorize execution"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(_candidate(), **changes)
    for changes, message in (
        ({"loop_id": ""}, "identity"),
        ({"stages": ()}, "stages"),
        (
            {
                "metrics": (
                    ProfitabilityMetric("metric", 1.0),
                    ProfitabilityMetric("metric", 2.0),
                )
            },
            "metric IDs",
        ),
        ({"promotion_status": ValidationStatus.PAPER_APPROVED}, "research only"),
        ({"risk_change_allowed": True}, "authorize execution"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(_loop(), **changes)
    summary = LearningSummary("summary", NOW, (), (), _loop())
    with pytest.raises(ValueError, match="timestamp"):
        replace(summary, created_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="promotion"):
        replace(summary, promotion_evidence_required=False)
    with pytest.raises(ValueError, match="analysis_id"):
        replace(
            FailureAnalysis("a", "c", "s", "r", 1, 0.1, 0.2, "why", "id"),
            analysis_id="",
        )
    with pytest.raises(ValueError, match="identity"):
        replace(_experiment(), objective="")
    with pytest.raises(ValueError, match="candidate_id"):
        replace(_candidate(), candidate_id="")
    with pytest.raises(ValueError, match="experiment IDs"):
        replace(_loop(), experiments=(_experiment(), _experiment()))
    with pytest.raises(ValueError, match="candidate IDs"):
        replace(_loop(), experiment_candidates=(_candidate(), _candidate()))
    with pytest.raises(ValueError, match="identity"):
        replace(summary, summary_id="")
    with pytest.raises(ValueError, match="cannot execute"):
        replace(summary, execution_allowed=True)


def _portfolio(**changes: object) -> VirtualPortfolioState:
    baseline: dict[str, object] = {
        "portfolio_id": "portfolio-1",
        "market": "SPOT",
        "cash_usdt": Decimal("100"),
        "equity_usdt": Decimal("100"),
    }
    baseline.update(changes)
    return VirtualPortfolioState(**baseline)


def test_virtual_portfolio_state_validates_market_and_serialization_boundaries() -> (
    None
):
    state = _portfolio()
    assert VirtualPortfolioState.from_payload(state.to_payload()) == state
    for changes, message in (
        ({"portfolio_id": ""}, "identity"),
        ({"equity_usdt": Decimal("0")}, "equity"),
        ({"cash_usdt": Decimal("-1")}, "non-negative"),
        ({"max_drawdown_ratio": Decimal("2")}, "drawdown"),
        ({"funding_cost_usdt": Decimal("NaN")}, "finite"),
        ({"unrealized_pnl_usdt": Decimal("-201")}, "inconsistent"),
        ({"open_position_count": -1}, "capacity"),
        ({"consecutive_losses": -1}, "consecutive"),
        ({"market": "MARGIN"}, "market"),
        ({"inventory_cost_basis_usdt": Decimal("1")}, "cost basis"),
        ({"position_side": VirtualPositionSide.LONG}, "Futures position"),
    ):
        with pytest.raises(ValueError, match=message):
            _portfolio(**changes)
    futures = _portfolio(
        market="USD_M_FUTURES",
        inventory_quantity=Decimal("0"),
        inventory_cost_basis_usdt=Decimal("0"),
        open_position_count=1,
        position_side=VirtualPositionSide.LONG,
        position_entry_price=Decimal("10"),
        position_mark_price=Decimal("11"),
        position_notional_usdt=Decimal("10"),
        isolated_margin_usdt=Decimal("2"),
        initial_margin_usdt=Decimal("2"),
        maintenance_margin_usdt=Decimal("1"),
        liquidation_price=Decimal("1"),
        leverage=2,
        margin_utilization_ratio=Decimal("0.5"),
    )
    assert futures.market == "USD_M_FUTURES"
    with pytest.raises(ValueError, match="full margin"):
        replace(futures, position_mark_price=None)
    with pytest.raises(ValueError, match="positive leverage"):
        replace(futures, leverage=0)
    with pytest.raises(ValueError, match="margin utilization"):
        replace(futures, margin_utilization_ratio=Decimal("2"))
    with pytest.raises(ValueError, match="directional"):
        replace(futures, open_position_count=0)
    with pytest.raises(ValueError, match="high watermark must be positive"):
        _portfolio(high_watermark_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="cannot trail"):
        _portfolio(high_watermark_usdt=Decimal("99"))
    with pytest.raises(ValueError, match="cash appears"):
        _portfolio(cash_usdt=Decimal("1101"))
    with pytest.raises(ValueError, match="cannot carry Spot"):
        replace(futures, inventory_quantity=Decimal("1"))
    payload = state.to_payload()
    payload["cash_usdt"] = "not-a-decimal"
    with pytest.raises(ValueError, match="cash_usdt"):
        VirtualPortfolioState.from_payload(payload)
    payload = state.to_payload()
    payload["consecutive_losses"] = True
    with pytest.raises(ValueError, match="integer"):
        VirtualPortfolioState.from_payload(payload)
    payload = state.to_payload()
    payload["portfolio_id"] = " "
    with pytest.raises(ValueError, match="non-empty text"):
        VirtualPortfolioState.from_payload(payload)
    payload = state.to_payload()
    payload["cash_usdt"] = "NaN"
    with pytest.raises(ValueError, match="finite"):
        VirtualPortfolioState.from_payload(payload)
    payload = state.to_payload()
    payload["consecutive_losses"] = "01"
    with pytest.raises(ValueError, match="canonical"):
        VirtualPortfolioState.from_payload(payload)


def _assessment() -> RiskAssessmentV2Contract:
    return RiskAssessmentV2Contract(
        assessment_id="assessment",
        cycle_id="cycle",
        snapshot_id="snapshot",
        decision_id="decision",
        assessed_at=NOW,
        owner_id="owner",
        reviewer_id="reviewer",
        affected_parties=("operator",),
        risk_register_ref="risk-register",
        inherent_risk=RiskRating(5, 5),
        current_risk=RiskRating(4, 4),
        residual_risk=RiskRating(2, 2),
        appetite_threshold=4,
        controls=(
            RiskControlEffectiveness("control", 9000, HASH, RiskControlStatus.VERIFIED),
        ),
        evidence_status=RiskEvidenceStatus.VERIFIED,
        result=RiskAssessmentV2Result.PASS,
    )


def test_risk_assessment_contract_rejects_invalid_governance_inputs() -> None:
    with pytest.raises(ValueError, match="between"):
        RiskRating(0, 1)
    with pytest.raises(ValueError, match="control_id"):
        RiskControlEffectiveness("", 1, HASH, RiskControlStatus.VERIFIED)
    with pytest.raises(ValueError, match="effectiveness"):
        RiskControlEffectiveness("id", 10_001, HASH, RiskControlStatus.VERIFIED)
    with pytest.raises(ValueError, match="zero effectiveness"):
        RiskControlEffectiveness("id", 1, HASH, RiskControlStatus.INEFFECTIVE)
    base = _assessment()
    for changes, message in (
        ({"schema_version": "1"}, "schema_version"),
        ({"owner_id": "reviewer"}, "distinct"),
        ({"assessed_at": datetime(2026, 1, 1)}, "UTC"),
        ({"affected_parties": ()}, "cannot be empty"),
        ({"appetite_threshold": 0}, "appetite"),
        ({"controls": ()}, "requires controls"),
        (
            {"current_risk": RiskRating(5, 5), "inherent_risk": RiskRating(4, 4)},
            "cannot exceed",
        ),
        ({"residual_risk": RiskRating(5, 5)}, "cannot exceed"),
        ({"blockers": ("BLOCK",)}, "PASS"),
        ({"evidence_status": RiskEvidenceStatus.UNKNOWN}, "verified evidence"),
        ({"execution_allowed": True}, "cannot grant"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(base, **changes)
    restricted = replace(
        base, result=RiskAssessmentV2Result.RESTRICT, blockers=("BLOCK",)
    )
    assert restricted.to_payload()["semantic_sha256"] == restricted.semantic_sha256
    with pytest.raises(ValueError, match="requires blockers"):
        replace(restricted, blockers=())
    with pytest.raises(ValueError, match="digest"):
        RiskControlEffectiveness("id", 1, "bad", RiskControlStatus.VERIFIED)
    with pytest.raises(ValueError, match="cannot contain blanks"):
        replace(base, affected_parties=("",))
    with pytest.raises(ValueError, match="must be unique"):
        replace(base, blockers=("A", "A"))
    with pytest.raises(ValueError, match="ratings"):
        replace(base, inherent_risk=cast(object, "invalid"))
    with pytest.raises(ValueError, match="controls"):
        replace(base, controls=(cast(object, "invalid"),))
    with pytest.raises(ValueError, match="assessment_id"):
        replace(base, assessment_id="")

from dataclasses import replace
from decimal import Decimal

import pytest

from ai4binance.governance.controls import ControlEligibility
from ai4binance.governance.dge_engine import (
    DecisionGovernanceEngine,
    _control_evaluation,
)
from ai4binance.governance.dge_models import (
    DgeDecisionStatus,
    DgeGovernanceContext,
    DgeMarketAction,
    DgeRuleResult,
    DgeRuleSeverity,
    DgeTradeCandidate,
)
from ai4binance.governance.execution_authority import ExecutionSurface


def candidate(**overrides: object) -> DgeTradeCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate:btc-breakout",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "requested_action": DgeMarketAction.BUY,
        "setup_name": "breakout_retest",
        "score": Decimal("78"),
        "confidence": Decimal("0.70"),
        "risk_reward": Decimal("2.4"),
        "capital_source": "WALLET_ROTATION",
        "evidence_refs": ("semantic-position:abc",),
    }
    values.update(overrides)
    return DgeTradeCandidate(**values)  # type: ignore[arg-type]


def context(**overrides: object) -> DgeGovernanceContext:
    values: dict[str, object] = {
        "context_id": "context:1",
        "data_snapshot_id": "snapshot:1",
        "semantic_graph_id": "semantic-position:abc",
        "position_context_ref": "position-context:1",
        "wallet_verified": True,
        "oos_approved": True,
        "risk_approved": True,
        "validation_approved": True,
        "execution_feasible": True,
        "human_approval_recorded": True,
        "no_new_capital_required": True,
        "evidence_refs": ("position-context:1",),
        "config_hash": "cfg:abc",
    }
    values.update(overrides)
    return DgeGovernanceContext(**values)  # type: ignore[arg-type]


def test_dge_blocks_high_score_candidate_when_required_evidence_is_missing() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(),
        context(wallet_verified=False, oos_approved=False, risk_approved=False),
    )

    assert decision.requested_action is DgeMarketAction.BUY
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert decision.governance_status is DgeDecisionStatus.WATCH_ONLY
    assert "EVID.CRITICAL_EVIDENCE_MISSING" in decision.hard_blockers
    assert "VAL.OOS_NOT_VALIDATED" in decision.hard_blockers
    assert "RISK.VETO" in decision.hard_blockers
    assert decision.paper_execution_allowed is False
    assert decision.live_execution_allowed is False
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert decision.control_evaluation.hard_gate_passed is False
    assert decision.control_evaluation.eligibility is ControlEligibility.NO_TRADE


@pytest.mark.parametrize(
    ("context_overrides", "expected_blocker", "expected_authority"),
    [
        (
            {"risk_approved": False},
            "RISK.VETO",
            "RISK_ENGINE",
        ),
        (
            {"oos_approved": False},
            "VAL.OOS_NOT_VALIDATED",
            "VALIDATION_ENGINE",
        ),
        (
            {"validation_approved": False},
            "VAL.ROBUSTNESS_NOT_VALIDATED",
            "VALIDATION_ENGINE",
        ),
        (
            {"blockers": ("LIVE_EXECUTION_DISABLED",)},
            "EXEC.LIVE_EXECUTION_UNAUTHORIZED",
            "EXECUTION_ENGINE",
        ),
    ],
)
def test_dge_perfect_score_cannot_override_authority_vetoes(
    context_overrides: dict[str, object],
    expected_blocker: str,
    expected_authority: str,
) -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(
            score=Decimal("100"), confidence=Decimal("1"), risk_reward=Decimal("9")
        ),
        context(**context_overrides),
    )

    assert expected_blocker in decision.hard_blockers
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert decision.quality_scores.governance_score == Decimal("0")
    assert decision.paper_execution_allowed is False
    assert decision.live_execution_allowed is False
    assert decision.execution_allowed is False
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    matching_blocker = next(
        item
        for item in decision.control_evaluation.hard_blockers
        if item.reason_code == expected_blocker
    )
    assert matching_blocker.active is True
    assert matching_blocker.resolution_authority.value == expected_authority
    assert decision.control_evaluation.hard_gate_passed is False
    assert decision.control_evaluation.eligibility is ControlEligibility.NO_TRADE


def test_strategy_candidate_context_and_decision_cannot_bypass_dge_authority() -> None:
    with pytest.raises(ValueError, match="candidate cannot arrive"):
        candidate(execution_allowed=True)

    with pytest.raises(ValueError, match="context cannot authorize execution"):
        context(execution_allowed=True)

    with pytest.raises(ValueError, match="context cannot authorize execution"):
        context(live_eligibility_status="EXECUTION_ALLOWED")

    approved_paper = DecisionGovernanceEngine().evaluate(candidate(), context())
    assert approved_paper.simulated_execution_allowed is False
    assert approved_paper.paper_execution_allowed is True
    assert approved_paper.auto_execution_allowed is False
    assert approved_paper.autonomous_learning_allowed is False
    assert approved_paper.bounded_self_improvement_allowed is False
    assert approved_paper.requires_manual_confirmation is True
    assert approved_paper.execution_surface is ExecutionSurface.BINANCE_MARKET
    assert approved_paper.execution_allowed is False
    assert approved_paper.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="DGE cannot authorize live execution"):
        replace(approved_paper, execution_allowed=True)
    with pytest.raises(ValueError, match="DGE cannot authorize live execution"):
        replace(approved_paper, promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="DGE cannot authorize live execution"):
        replace(approved_paper, live_execution_allowed=True)


def test_dge_rejects_external_capital_and_coin_dependency_bias() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(capital_source="EXTERNAL_DEPOSIT"),
        context(position_dependency_bias_detected=True),
    )

    assert "RISK.RISK_BUDGET_UNAVAILABLE" in decision.hard_blockers
    assert "GOV.POLICY_CONFLICT" in decision.hard_blockers
    assert decision.governed_action is DgeMarketAction.NO_TRADE


def test_dge_blocks_privacy_leak_remediation_candidate_from_execution() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(
            candidate_id="privacy-remediation:kvkk-leak",
            requested_action=DgeMarketAction.HOLD,
            setup_name="privacy_leak_remediation",
            score=Decimal("100"),
            confidence=Decimal("1"),
        ),
        context(
            blockers=(
                "privacy:KVKK_PUBLIC_PRIVACY_LEAK",
                "privacy:NO_GITHUB_CLOUD_SHARE",
            ),
        ),
    )

    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert decision.hard_blockers == ("GOV.UNKNOWN_CONTROL_CLASSIFICATION",)
    assert "DGE_CONTEXT_BLOCKER:privacy:KVKK_PUBLIC_PRIVACY_LEAK" in (
        decision.failed_rules
    )
    assert "classify_control_in_blocker_registry" in decision.required_changes
    assert decision.paper_execution_allowed is False
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_dge_is_deterministic_for_same_candidate_and_context() -> None:
    engine = DecisionGovernanceEngine()
    first = engine.evaluate(candidate(), context())
    second = engine.evaluate(candidate(), context())

    assert first.decision_id == second.decision_id
    assert first.governance_status is DgeDecisionStatus.APPROVED_PAPER_ONLY
    assert first.simulated_execution_allowed is False
    assert first.paper_execution_allowed is True
    assert first.auto_execution_allowed is False
    assert first.autonomous_learning_allowed is False
    assert first.requires_manual_confirmation is True
    assert first.live_execution_allowed is False
    assert first.quality_scores.governance_score > Decimal("0")


def test_dge_virtual_market_surface_allows_autonomous_simulation_only() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(),
        context(execution_surface=ExecutionSurface.VIRTUAL_MARKET),
    )

    assert decision.governance_status is DgeDecisionStatus.APPROVED_PAPER_ONLY
    assert decision.simulated_execution_allowed is True
    assert decision.paper_execution_allowed is True
    assert decision.auto_execution_allowed is True
    assert decision.autonomous_learning_allowed is True
    assert decision.bounded_self_improvement_allowed is True
    assert decision.simulated_spot_allowed is True
    assert decision.simulated_futures_allowed is True
    assert decision.requires_manual_confirmation is False
    assert decision.execution_surface is ExecutionSurface.VIRTUAL_MARKET


def test_dge_blocked_virtual_market_returns_decision_without_profile_conflict() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(),
        context(
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            oos_approved=False,
            validation_approved=False,
            human_approval_recorded=False,
        ),
    )

    assert decision.governance_status is DgeDecisionStatus.WATCH_ONLY
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert "VAL.OOS_NOT_VALIDATED" in decision.hard_blockers
    assert decision.simulated_execution_allowed is False
    assert decision.paper_execution_allowed is False
    assert decision.auto_execution_allowed is False
    assert decision.autonomous_learning_allowed is False
    assert decision.requires_manual_confirmation is True


def test_dge_data_quality_failure_is_first_class_and_non_executable() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(),
        context(data_quality_passed=False),
    )

    assert decision.governance_status is DgeDecisionStatus.DATA_UNAVAILABLE
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert "DATA.DATA_QUALITY_FAILED" in decision.hard_blockers
    assert decision.quality_scores.data_quality_score == Decimal("0")
    assert decision.quality_scores.governance_score == Decimal("0")
    assert decision.control_evaluation.active_hard_blocker_count == 1
    assert decision.control_evaluation.hard_blockers[0].reason_code == (
        "DATA.DATA_QUALITY_FAILED"
    )
    assert decision.paper_execution_allowed is False
    assert decision.live_execution_allowed is False


def test_dge_low_confidence_is_visible_but_non_executable() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(confidence=Decimal("0.20")),
        context(),
    )

    assert decision.governance_status is DgeDecisionStatus.LOW_CONFIDENCE
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert decision.required_changes == ("keep_strategy_in_research",)
    assert decision.paper_execution_allowed is False


def test_dge_liquidity_failure_blocks_even_high_score_candidates() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(score=Decimal("95"), confidence=Decimal("0.90")),
        context(liquidity_approved=False),
    )

    assert decision.governance_status is DgeDecisionStatus.WATCH_ONLY
    assert "LIQ.APPROVAL_MISSING" in decision.hard_blockers
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert decision.control_evaluation.base_score == Decimal("95")
    assert decision.control_evaluation.hard_gate_passed is False
    assert decision.control_evaluation.total_penalty == Decimal("0")
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_dge_mtf_conflict_downgrades_to_manual_review() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(),
        context(mtf_aligned=False),
    )

    assert decision.governance_status is DgeDecisionStatus.MANUAL_REVIEW
    assert "EVID.CRITICAL_CONFLICT_UNRESOLVED" in decision.soft_blockers
    assert decision.governed_action is DgeMarketAction.BUY
    assert decision.control_evaluation.hard_gate_passed is True
    assert decision.control_evaluation.soft_penalties[0].reason_code == (
        "EVID.CRITICAL_CONFLICT_UNRESOLVED"
    )
    assert decision.control_evaluation.adjusted_score < (
        decision.control_evaluation.base_score
    )
    assert decision.paper_execution_allowed is False


@pytest.mark.parametrize(
    ("threshold_name", "threshold_value", "expected_message"),
    [
        (
            "minimum_score",
            Decimal("-1"),
            "DGE minimum score must be between zero and 100",
        ),
        (
            "minimum_confidence",
            Decimal("1.1"),
            "DGE minimum confidence must be between zero and one",
        ),
        (
            "minimum_risk_reward",
            Decimal("0"),
            "DGE minimum risk/reward must be positive",
        ),
    ],
)
def test_dge_rejects_invalid_threshold_configuration(
    threshold_name: str,
    threshold_value: Decimal,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        invalid_engine_configuration(threshold_name, threshold_value)


def invalid_engine_configuration(
    threshold_name: str,
    threshold_value: Decimal,
) -> DecisionGovernanceEngine:
    if threshold_name == "minimum_score":
        return DecisionGovernanceEngine(minimum_score=threshold_value)
    if threshold_name == "minimum_confidence":
        return DecisionGovernanceEngine(minimum_confidence=threshold_value)
    return DecisionGovernanceEngine(minimum_risk_reward=threshold_value)


def test_dge_snapshot_integrity_failure_is_critical_data_unavailable() -> None:
    decision = DecisionGovernanceEngine().evaluate(
        candidate(),
        context(snapshot_integrity_verified=False),
    )

    assert decision.governance_status is DgeDecisionStatus.DATA_UNAVAILABLE
    assert decision.governed_action is DgeMarketAction.NO_TRADE
    assert decision.hard_blockers == ("DATA.SNAPSHOT_INCOMPLETE",)
    assert decision.control_evaluation.hard_blockers[0].severity.value == "CRITICAL"
    assert decision.control_evaluation.hard_blockers[0].resolution_authority.value == (
        "GOVERNANCE_CONTROL_PLANE"
    )
    assert decision.paper_execution_allowed is False


def test_dge_unknown_rule_severity_fails_closed_as_unknown_control() -> None:
    engine = DecisionGovernanceEngine()
    evaluation = _control_evaluation(
        decision_id="dge:test-unknown-severity",
        candidate=candidate(),
        context=context(),
        rules=(
            DgeRuleResult(
                "DGE_CONTEXT_BLOCKER:unknown",
                False,
                DgeRuleSeverity.INFO,
                ("NOT_IN_CANONICAL_REGISTRY",),
            ),
        ),
        rule_registry=engine.rule_registry,
    )

    assert evaluation.hard_gate_passed is False
    assert evaluation.eligibility is ControlEligibility.NO_TRADE
    assert evaluation.hard_blockers[0].reason_code == (
        "GOV.UNKNOWN_CONTROL_CLASSIFICATION"
    )
    assert evaluation.hard_blockers[0].producer == "DecisionGovernanceEngine"

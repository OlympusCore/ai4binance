from decimal import Decimal

import pytest

from ai4binance.governance.controls import ControlEligibility, build_control_evaluation
from ai4binance.governance.dge_models import (
    DecisionCandidate,
    DgeDecisionStatus,
    DgeGovernanceContext,
    DgeLayerEvaluation,
    DgeMarketAction,
    DgeMarketPlan,
    DgePolicyVersions,
    DgeQualityScores,
    DgeRuleResult,
    DgeRuleSeverity,
    DgeSetupTier,
    DgeTradeCandidate,
    GovernedDecision,
    TradeDecision,
    deterministic_decision_id,
)
from ai4binance.governance.execution_authority import (
    ExecutionAutomationMode,
    ExecutionSurface,
)
from ai4binance.governance.rules import (
    GovernanceRule,
    default_governance_rule_catalog,
    governance_rule_index,
)


def dge_candidate(**overrides: object) -> DgeTradeCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate:test",
        "symbol": "HOTUSDT",
        "market": "SPOT",
        "requested_action": DgeMarketAction.BUY,
        "setup_name": "breakout",
        "score": Decimal("75"),
        "confidence": Decimal("0.70"),
        "risk_reward": Decimal("2"),
        "primary_timeframe": "1h",
        "mtf_bias": "aligned",
        "regime": "trend",
        "evidence_refs": ("evidence:1",),
    }
    values.update(overrides)
    return DgeTradeCandidate(**values)  # type: ignore[arg-type]


def dge_context(**overrides: object) -> DgeGovernanceContext:
    values: dict[str, object] = {
        "context_id": "context:test",
        "data_snapshot_id": "snapshot:1",
        "semantic_graph_id": "graph:1",
        "position_context_ref": "position:none",
        "blockers": (),
        "evidence_refs": ("evidence:1",),
        "rule_set_version": "dge-rules-v1",
        "config_hash": "cfg",
    }
    values.update(overrides)
    return DgeGovernanceContext(**values)  # type: ignore[arg-type]


def governed_decision(**overrides: object) -> GovernedDecision:
    values: dict[str, object] = {
        "timestamp_utc": "2026-08-08T00:00:00Z",
        "decision_id": "dge:test",
        "candidate_id": "candidate:test",
        "symbol": "HOTUSDT",
        "market_type": "SPOT",
        "requested_action": DgeMarketAction.BUY,
        "governed_action": DgeMarketAction.BUY,
        "governance_status": DgeDecisionStatus.APPROVED_PAPER_ONLY,
        "setup_tier": DgeSetupTier.C,
        "primary_timeframe": "1h",
        "mtf_bias": "aligned",
        "regime": "range",
        "quality_scores": DgeQualityScores(signal_score=Decimal("70")),
        "market_plan": DgeMarketPlan(),
        "layer_evaluations": (),
        "hard_blockers": (),
        "soft_blockers": (),
        "warnings": (),
        "required_changes": (),
        "passed_rules": ("rule:ok",),
        "failed_rules": (),
        "reason_summary": "virtual-market simulation criteria passed",
        "evidence_refs": ("evidence:1",),
        "rule_set_version": "dge-rules-v1",
        "config_hash": "cfg",
        "data_snapshot_id": "snapshot:1",
        "semantic_graph_id": "graph:1",
        "policy_versions": DgePolicyVersions(),
        "simulated_execution_allowed": True,
        "paper_execution_allowed": True,
    }
    values.update(overrides)
    return GovernedDecision(**values)  # type: ignore[arg-type]


def test_dge_quality_scores_are_bounded() -> None:
    scores = DgeQualityScores(
        signal_score=Decimal("80"),
        evidence_score=Decimal("75"),
        data_quality_score=Decimal("100"),
        mtf_score=Decimal("90"),
        regime_score=Decimal("70"),
        liquidity_score=Decimal("100"),
        risk_score=Decimal("80"),
        execution_score=Decimal("60"),
        confidence_score=Decimal("65"),
        governance_score=Decimal("78.25"),
    )

    assert scores.governance_score == Decimal("78.25")


def test_canonical_decision_contract_names_preserve_legacy_aliases() -> None:
    assert DecisionCandidate is DgeTradeCandidate
    assert TradeDecision is GovernedDecision
    assert DecisionCandidate.__name__ == "DecisionCandidate"
    assert TradeDecision.__name__ == "TradeDecision"

    with pytest.raises(ValueError, match="cannot arrive with execution authority"):
        DecisionCandidate(
            candidate_id="candidate:authority-check",
            symbol="BTCUSDT",
            market="SPOT",
            requested_action=DgeMarketAction.BUY,
            setup_name="breakout",
            score=Decimal("70"),
            confidence=Decimal("0.7"),
            primary_timeframe="1h",
            mtf_bias="aligned",
            regime="trend",
            execution_allowed=True,
        )


def test_dge_quality_scores_reject_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="signal_score"):
        DgeQualityScores(signal_score=Decimal("101"))


def test_dge_market_plan_rejects_non_positive_structure() -> None:
    with pytest.raises(ValueError, match="entry"):
        DgeMarketPlan(entry=Decimal("0"))
    with pytest.raises(ValueError, match="take-profit levels must be positive"):
        DgeMarketPlan(take_profit_levels=(Decimal("1"), Decimal("0")))
    with pytest.raises(ValueError, match="take-profit levels must be unique"):
        DgeMarketPlan(take_profit_levels=(Decimal("2"), Decimal("2")))


def test_dge_policy_versions_are_nonblank_and_tupled() -> None:
    versions = DgePolicyVersions(
        policy_version="policy",
        config_version="config",
        strategy_version="strategy",
        parameter_version="parameters",
        ontology_version="ontology",
    )

    assert versions.as_tuple() == (
        "policy",
        "config",
        "strategy",
        "parameters",
        "ontology",
    )
    with pytest.raises(ValueError, match="policy versions"):
        DgePolicyVersions(config_version=" ")


def test_dge_layer_evaluation_rejects_blank_and_duplicate_lists() -> None:
    with pytest.raises(ValueError, match="layer evaluation identity"):
        DgeLayerEvaluation(
            layer_id=" ",
            status=DgeDecisionStatus.WATCH_ONLY,
            primary_reason="WATCH",
        )
    with pytest.raises(ValueError, match="hard blockers must be unique"):
        DgeLayerEvaluation(
            layer_id="layer",
            status=DgeDecisionStatus.BLOCKED,
            primary_reason="blocked",
            hard_blockers=("BLOCKER", "BLOCKER"),
        )
    with pytest.raises(ValueError, match="evidence refs cannot contain blanks"):
        DgeLayerEvaluation(
            layer_id="layer",
            status=DgeDecisionStatus.WATCH_ONLY,
            primary_reason="watch",
            evidence_refs=("evidence:1", " "),
        )


def test_dge_trade_candidate_rejects_invalid_inputs_and_execution_authority() -> None:
    with pytest.raises(ValueError, match="candidate identity"):
        dge_candidate(candidate_id=" ")
    with pytest.raises(ValueError, match="candidate score"):
        dge_candidate(score=Decimal("-1"))
    with pytest.raises(ValueError, match="confidence"):
        dge_candidate(confidence=Decimal("1.1"))
    with pytest.raises(ValueError, match="risk_reward"):
        dge_candidate(risk_reward=Decimal("0"))
    with pytest.raises(ValueError, match="market context"):
        dge_candidate(primary_timeframe=" ")
    with pytest.raises(ValueError, match="evidence refs must be unique"):
        dge_candidate(evidence_refs=("evidence:1", "evidence:1"))
    with pytest.raises(ValueError, match="execution authority"):
        dge_candidate(execution_allowed=True)
    assert dge_candidate(market="spot").market == "SPOT"
    assert dge_candidate(market="USD_M_FUTURES").market == "USD_M_FUTURES"
    assert dge_candidate(market="governance").market == "GOVERNANCE"
    with pytest.raises(
        ValueError,
        match="DGE market type must be SPOT or USD_M_FUTURES",
    ):
        dge_candidate(market="options")


def test_dge_governance_context_rejects_identity_lists_and_execution_authority() -> (
    None
):
    with pytest.raises(ValueError, match="governance context identity"):
        dge_context(context_id=" ")
    with pytest.raises(ValueError, match="context blockers must be unique"):
        dge_context(blockers=("BLOCKER", "BLOCKER"))
    with pytest.raises(ValueError, match="context evidence refs cannot contain blanks"):
        dge_context(evidence_refs=("evidence:1", " "))
    with pytest.raises(ValueError, match="cannot authorize execution"):
        dge_context(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        dge_context(live_eligibility_status="LIVE_ELIGIBLE")


def test_dge_rule_result_rejects_inconsistent_rule_outcomes() -> None:
    assert (
        DgeRuleResult(
            rule_id="DGE_RULE_OK",
            passed=True,
            severity=DgeRuleSeverity.INFO,
            evidence_refs=("evidence:1",),
        ).passed
        is True
    )
    with pytest.raises(ValueError, match="rule identity"):
        DgeRuleResult(" ", True, DgeRuleSeverity.INFO)
    with pytest.raises(ValueError, match="rule blockers cannot contain blanks"):
        DgeRuleResult("DGE_RULE_BAD", False, DgeRuleSeverity.HARD, blockers=(" ",))
    with pytest.raises(ValueError, match="passed DGE rules"):
        DgeRuleResult(
            "DGE_RULE_BAD",
            True,
            DgeRuleSeverity.HARD,
            blockers=("BLOCKER",),
        )
    with pytest.raises(ValueError, match="failed DGE rules require blockers"):
        DgeRuleResult("DGE_RULE_BAD", False, DgeRuleSeverity.HARD)


def test_non_executable_statuses_cannot_allow_paper_execution() -> None:
    with pytest.raises(ValueError, match="non-executable DGE statuses"):
        GovernedDecision(
            timestamp_utc="2026-08-08T00:00:00Z",
            decision_id="dge:test",
            candidate_id="candidate:test",
            symbol="HOTUSDT",
            market_type="SPOT",
            requested_action=DgeMarketAction.BUY,
            governed_action=DgeMarketAction.HOLD,
            governance_status=DgeDecisionStatus.LOW_CONFIDENCE,
            setup_tier=DgeSetupTier.C,
            primary_timeframe="1h",
            mtf_bias="mixed",
            regime="range",
            quality_scores=DgeQualityScores(confidence_score=Decimal("20")),
            market_plan=DgeMarketPlan(),
            layer_evaluations=(
                DgeLayerEvaluation(
                    layer_id="test",
                    status=DgeDecisionStatus.LOW_CONFIDENCE,
                    primary_reason="LOW_CONFIDENCE",
                ),
            ),
            hard_blockers=(),
            soft_blockers=(),
            warnings=(),
            required_changes=(),
            passed_rules=("rule:ok",),
            failed_rules=(),
            reason_summary="low confidence",
            evidence_refs=("evidence:1",),
            rule_set_version="dge-rules-v1",
            config_hash="cfg",
            data_snapshot_id="snapshot:1",
            semantic_graph_id="graph:1",
            policy_versions=DgePolicyVersions(),
            simulated_execution_allowed=True,
            paper_execution_allowed=True,
        )


def test_governed_decision_normalizes_market_type() -> None:
    decision = governed_decision(
        market_type="spot",
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        authority_profile_id="VIRTUAL_AUTONOMOUS_SIMULATION_V1",
        automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
        simulated_execution_allowed=True,
        paper_execution_allowed=True,
        auto_execution_allowed=True,
        autonomous_learning_allowed=True,
        bounded_self_improvement_allowed=True,
        simulated_spot_allowed=True,
        simulated_futures_allowed=True,
        requires_manual_confirmation=False,
    )

    assert decision.market_type == "SPOT"

    with pytest.raises(
        ValueError,
        match="DGE market type must be SPOT or USD_M_FUTURES",
    ):
        governed_decision(market_type="options")


def test_governed_decision_carries_control_evaluation() -> None:
    decision = GovernedDecision(
        timestamp_utc="2026-08-08T00:00:00Z",
        decision_id="dge:test",
        candidate_id="candidate:test",
        symbol="HOTUSDT",
        market_type="SPOT",
        requested_action=DgeMarketAction.BUY,
        governed_action=DgeMarketAction.BUY,
        governance_status=DgeDecisionStatus.APPROVED_PAPER_ONLY,
        setup_tier=DgeSetupTier.C,
        primary_timeframe="1h",
        mtf_bias="aligned",
        regime="range",
        quality_scores=DgeQualityScores(signal_score=Decimal("70")),
        market_plan=DgeMarketPlan(),
        layer_evaluations=(),
        hard_blockers=(),
        soft_blockers=(),
        warnings=(),
        required_changes=(),
        passed_rules=("rule:ok",),
        failed_rules=(),
        reason_summary="virtual-market simulation criteria passed",
        evidence_refs=("evidence:1",),
        control_evaluation=build_control_evaluation(
            evaluation_id="control:dge:test",
            base_score=Decimal("70"),
            eligibility_when_clear=ControlEligibility.ELIGIBLE,
        ),
        rule_set_version="dge-rules-v1",
        config_hash="cfg",
        data_snapshot_id="snapshot:1",
        semantic_graph_id="graph:1",
        policy_versions=DgePolicyVersions(),
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        authority_profile_id="VIRTUAL_AUTONOMOUS_SIMULATION_V1",
        automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
        simulated_execution_allowed=True,
        paper_execution_allowed=True,
        auto_execution_allowed=True,
        autonomous_learning_allowed=True,
        bounded_self_improvement_allowed=True,
        simulated_spot_allowed=True,
        simulated_futures_allowed=True,
        requires_manual_confirmation=False,
    )

    assert decision.control_evaluation.eligibility is ControlEligibility.ELIGIBLE


def test_governed_decision_virtual_market_requires_autonomous_simulation_profile() -> (
    None
):
    decision = governed_decision(
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
        authority_profile_id="VIRTUAL_AUTONOMOUS_SIMULATION_V1",
        automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
        simulated_execution_allowed=True,
        auto_execution_allowed=True,
        autonomous_learning_allowed=True,
        bounded_self_improvement_allowed=True,
        simulated_spot_allowed=True,
        simulated_futures_allowed=True,
        requires_manual_confirmation=False,
    )

    assert decision.execution_surface is ExecutionSurface.VIRTUAL_MARKET
    assert decision.auto_execution_allowed is True

    with pytest.raises(ValueError, match="autonomous simulation must match"):
        governed_decision(
            execution_surface=ExecutionSurface.VIRTUAL_MARKET,
            authority_profile_id="VIRTUAL_AUTONOMOUS_SIMULATION_V1",
            automation_mode=ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION,
            simulated_execution_allowed=True,
            auto_execution_allowed=False,
            autonomous_learning_allowed=True,
            bounded_self_improvement_allowed=True,
            simulated_spot_allowed=True,
            simulated_futures_allowed=True,
            requires_manual_confirmation=False,
        )


def test_governed_decision_rejects_identity_duplicates_and_execution_bypass() -> None:
    with pytest.raises(ValueError, match="governed decision identity"):
        governed_decision(decision_id=" ")
    with pytest.raises(ValueError, match="governed decision lists must be unique"):
        governed_decision(passed_rules=("rule:ok", "rule:ok"))
    with pytest.raises(
        ValueError, match="governed decision lists cannot contain blanks"
    ):
        governed_decision(evidence_refs=("evidence:1", " "))
    with pytest.raises(ValueError, match="unique layer ids"):
        governed_decision(
            layer_evaluations=(
                DgeLayerEvaluation(
                    "duplicate",
                    DgeDecisionStatus.WATCH_ONLY,
                    "watch",
                ),
                DgeLayerEvaluation(
                    "duplicate",
                    DgeDecisionStatus.WATCH_ONLY,
                    "watch",
                ),
            )
        )
    with pytest.raises(ValueError, match="hard-blocked decisions"):
        governed_decision(hard_blockers=("HARD_BLOCKER",))
    with pytest.raises(ValueError, match="NO_TRADE decisions"):
        governed_decision(governed_action=DgeMarketAction.NO_TRADE)
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        governed_decision(promotion_status="PAPER")
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        governed_decision(live_execution_allowed=True)


def test_deterministic_decision_id_is_stable_and_input_sensitive() -> None:
    candidate = dge_candidate()
    context = dge_context(
        policy_versions=DgePolicyVersions(
            policy_version="policy",
            config_version="config",
            strategy_version="strategy",
            parameter_version="parameters",
            ontology_version="ontology",
        )
    )

    decision_id = deterministic_decision_id(
        candidate,
        context,
        ("DGE_DATA_QUALITY_GATE",),
    )

    assert decision_id.startswith("dge:")
    assert decision_id == deterministic_decision_id(
        candidate,
        context,
        ("DGE_DATA_QUALITY_GATE",),
    )
    assert decision_id != deterministic_decision_id(
        candidate,
        context,
        ("DGE_RISK_APPROVED",),
    )


def test_default_rule_catalog_is_unique_and_versioned() -> None:
    rules = default_governance_rule_catalog()
    indexed = governance_rule_index(rules)

    assert len(indexed) == len(rules)
    assert indexed["DGE_DATA_QUALITY_GATE"].version == "1.0.0"
    assert indexed["DGE_DATA_QUALITY_GATE"].enabled is True
    assert indexed["DGE_VALIDATION_APPROVED"].severity is DgeRuleSeverity.HARD


def test_governance_rule_rejects_blank_identity_fields() -> None:
    with pytest.raises(ValueError, match="DGE governance rule identity"):
        GovernanceRule(
            " ",
            "Rule Name",
            "Rule description.",
            "test",
            DgeRuleSeverity.HARD,
        )


def test_governance_rule_rejects_duplicate_scope_values() -> None:
    with pytest.raises(ValueError, match="DGE allowed regimes must be unique"):
        GovernanceRule(
            "DGE_TEST_SCOPE_DUPLICATE",
            "Scope Duplicate",
            "Rule description.",
            "test",
            DgeRuleSeverity.HARD,
            allowed_regimes=("TREND", "TREND"),
        )


def test_governance_rule_rejects_blank_scope_values() -> None:
    with pytest.raises(ValueError, match="DGE market types cannot contain blanks"):
        GovernanceRule(
            "DGE_TEST_SCOPE_BLANK",
            "Scope Blank",
            "Rule description.",
            "test",
            DgeRuleSeverity.HARD,
            market_types=("SPOT", " "),
        )


def test_governance_rule_index_rejects_duplicate_rule_ids() -> None:
    rule = GovernanceRule(
        "DGE_TEST_DUPLICATE",
        "Duplicate",
        "Rule description.",
        "test",
        DgeRuleSeverity.HARD,
    )

    with pytest.raises(ValueError, match="duplicate DGE rule id: DGE_TEST_DUPLICATE"):
        governance_rule_index((rule, rule))

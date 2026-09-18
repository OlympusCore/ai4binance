"""Shadow-rule counterfactual helpers for DGE Kaizen measurement."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.governance.dge_engine import DecisionGovernanceEngine
from ai4binance.governance.dge_models import (
    DgeGovernanceContext,
    DgeTradeCandidate,
    GovernedDecision,
)


@dataclass(frozen=True, slots=True)
class DgeShadowDecisionDiff:
    shadow_rule_id: str
    baseline_decision: GovernedDecision
    shadow_decision: GovernedDecision
    would_change_decision: bool
    changed_fields: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.shadow_rule_id.strip():
            raise ValueError("DGE shadow rule id is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or self.baseline_decision.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or self.shadow_decision.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE shadow diff cannot authorize execution")


def evaluate_shadow_without_blocker(
    candidate: DgeTradeCandidate,
    context: DgeGovernanceContext,
    *,
    blocker: str,
    dge: DecisionGovernanceEngine | None = None,
) -> DgeShadowDecisionDiff:
    """Evaluate a counterfactual where one blocker is ignored in shadow mode."""

    engine = dge or DecisionGovernanceEngine()
    baseline = engine.evaluate(candidate, context)
    shadow_context = _context_without_blocker(context, blocker)
    shadow = engine.evaluate(candidate, shadow_context)
    changed_fields = tuple(
        field
        for field in (
            "governance_status",
            "governed_action",
            "hard_blockers",
            "soft_blockers",
            "failed_rules",
        )
        if getattr(baseline, field) != getattr(shadow, field)
    )
    return DgeShadowDecisionDiff(
        shadow_rule_id=f"SHADOW_WITHOUT_{blocker}",
        baseline_decision=baseline,
        shadow_decision=shadow,
        would_change_decision=bool(changed_fields),
        changed_fields=changed_fields,
    )


def _context_without_blocker(
    context: DgeGovernanceContext,
    blocker: str,
) -> DgeGovernanceContext:
    blockers = tuple(item for item in context.blockers if item != blocker)
    return DgeGovernanceContext(
        context_id=context.context_id,
        data_snapshot_id=context.data_snapshot_id,
        semantic_graph_id=context.semantic_graph_id,
        position_context_ref=context.position_context_ref,
        wallet_verified=context.wallet_verified,
        snapshot_integrity_verified=context.snapshot_integrity_verified,
        data_quality_passed=(
            True
            if blocker == "DATA_QUALITY_GATE_FAILED"
            else context.data_quality_passed
        ),
        required_timeframes_present=context.required_timeframes_present,
        liquidity_approved=(
            True
            if blocker == "LIQUIDITY_APPROVAL_MISSING"
            else context.liquidity_approved
        ),
        regime_compatible=context.regime_compatible,
        mtf_aligned=(
            True if blocker == "MTF_ALIGNMENT_CONFLICT" else context.mtf_aligned
        ),
        structure_valid=context.structure_valid,
        negative_evidence_clear=context.negative_evidence_clear,
        oos_approved=(
            True if blocker == "OOS_APPROVAL_MISSING" else context.oos_approved
        ),
        risk_approved=(
            True if blocker == "RISK_APPROVAL_MISSING" else context.risk_approved
        ),
        validation_approved=(
            True
            if blocker in {"VALIDATION_VETO", "VAL.ROBUSTNESS_NOT_VALIDATED"}
            else context.validation_approved
        ),
        execution_feasible=context.execution_feasible,
        human_approval_recorded=context.human_approval_recorded,
        position_dependency_bias_detected=context.position_dependency_bias_detected,
        no_new_capital_required=context.no_new_capital_required,
        execution_surface=context.execution_surface,
        blockers=blockers,
        evidence_refs=context.evidence_refs,
        rule_set_version=context.rule_set_version,
        config_hash=context.config_hash,
        evaluation_timestamp_utc=context.evaluation_timestamp_utc,
        policy_versions=context.policy_versions,
    )

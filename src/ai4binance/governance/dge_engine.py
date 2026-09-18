"""Deterministic Decision Governance Engine foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from ai4binance.governance.blockers import (
    BLOCKER_REGISTRY_PATH,
    BlockerDefinition,
    BlockerDomain,
    BlockerRegistry,
    load_blocker_registry,
)
from ai4binance.governance.controls import (
    ControlEligibility,
    ControlEvaluation,
    ControlResolutionAuthority,
    ControlSeverity,
    ControlSource,
    HardBlocker,
    SoftPenalty,
    build_control_evaluation,
)
from ai4binance.governance.dge_models import (
    DgeDecisionStatus,
    DgeGovernanceContext,
    DgeLayerEvaluation,
    DgeMarketAction,
    DgeQualityScores,
    DgeRuleResult,
    DgeRuleSeverity,
    DgeTradeCandidate,
    GovernedDecision,
    deterministic_decision_id,
)
from ai4binance.governance.execution_authority import authority_profile_for_surface
from ai4binance.governance.rules import (
    GovernanceRule,
    default_governance_rule_catalog,
    governance_rule_index,
)


@dataclass(frozen=True, slots=True)
class DecisionGovernanceEngine:
    """Evaluate opportunities conservatively before any execution layer."""

    minimum_score: Decimal = Decimal("60")
    minimum_confidence: Decimal = Decimal("0.50")
    minimum_risk_reward: Decimal = Decimal("2")
    rule_registry: tuple[GovernanceRule, ...] = field(
        default_factory=default_governance_rule_catalog,
    )

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.minimum_score <= Decimal("100"):
            raise ValueError("DGE minimum score must be between zero and 100")
        if not Decimal("0") <= self.minimum_confidence <= Decimal("1"):
            raise ValueError("DGE minimum confidence must be between zero and one")
        if self.minimum_risk_reward <= Decimal("0"):
            raise ValueError("DGE minimum risk/reward must be positive")
        governance_rule_index(self.rule_registry)

    def evaluate(
        self,
        candidate: DgeTradeCandidate,
        context: DgeGovernanceContext,
    ) -> GovernedDecision:
        rules = self._rules(candidate, context)
        hard_blockers = tuple(
            dict.fromkeys(
                blocker
                for rule in rules
                if not rule.passed
                and rule.severity in {DgeRuleSeverity.HARD, DgeRuleSeverity.CRITICAL}
                for blocker in rule.blockers
            )
        )
        soft_blockers = tuple(
            dict.fromkeys(
                blocker
                for rule in rules
                if not rule.passed
                and rule.severity in {DgeRuleSeverity.SOFT, DgeRuleSeverity.WARNING}
                for blocker in rule.blockers
            )
        )
        warnings = tuple(
            dict.fromkeys(
                blocker
                for rule in rules
                if not rule.passed and rule.severity is DgeRuleSeverity.WARNING
                for blocker in rule.blockers
            )
        )
        failed_rules = tuple(rule.rule_id for rule in rules if not rule.passed)
        passed_rules = tuple(rule.rule_id for rule in rules if rule.passed)
        governed_action = (
            DgeMarketAction.NO_TRADE if hard_blockers else candidate.requested_action
        )
        status = self._status(candidate, hard_blockers, soft_blockers)
        quality_scores = _quality_scores(candidate, context, hard_blockers)
        layer_evaluations = _layer_evaluations(status, hard_blockers, soft_blockers)
        decision_id = deterministic_decision_id(candidate, context, failed_rules)
        authority_profile = authority_profile_for_surface(context.execution_surface)
        control_evaluation = _control_evaluation(
            decision_id=decision_id,
            candidate=candidate,
            context=context,
            rules=rules,
            rule_registry=self.rule_registry,
        )
        evidence_refs = _canonical_evidence_refs(
            (*candidate.evidence_refs, *context.evidence_refs)
        )
        return GovernedDecision(
            timestamp_utc=context.evaluation_timestamp_utc,
            decision_id=decision_id,
            candidate_id=candidate.candidate_id,
            symbol=candidate.symbol,
            market_type=candidate.market,
            requested_action=candidate.requested_action,
            governed_action=governed_action,
            governance_status=status,
            setup_tier=candidate.setup_tier,
            primary_timeframe=candidate.primary_timeframe,
            mtf_bias=candidate.mtf_bias,
            regime=candidate.regime,
            quality_scores=quality_scores,
            market_plan=candidate.market_plan,
            layer_evaluations=layer_evaluations,
            hard_blockers=hard_blockers,
            soft_blockers=soft_blockers,
            warnings=warnings,
            required_changes=_required_changes(hard_blockers, soft_blockers),
            passed_rules=passed_rules,
            failed_rules=failed_rules,
            reason_summary=_reason_summary(
                status,
                hard_blockers,
                soft_blockers,
                context.execution_surface,
            ),
            evidence_refs=evidence_refs,
            control_evaluation=control_evaluation,
            rule_set_version=context.rule_set_version,
            config_hash=context.config_hash,
            data_snapshot_id=context.data_snapshot_id,
            semantic_graph_id=context.semantic_graph_id,
            policy_versions=context.policy_versions,
            execution_surface=context.execution_surface,
            authority_profile_id=authority_profile.authority_profile_id,
            automation_mode=authority_profile.automation_mode,
            simulated_execution_allowed=(
                status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                and authority_profile.simulated_execution_allowed
            ),
            paper_execution_allowed=status is DgeDecisionStatus.APPROVED_PAPER_ONLY,
            auto_execution_allowed=(
                status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                and authority_profile.auto_execution_allowed
            ),
            autonomous_learning_allowed=(
                status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                and authority_profile.autonomous_learning_allowed
            ),
            bounded_self_improvement_allowed=(
                status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                and authority_profile.bounded_self_improvement_allowed
            ),
            simulated_spot_allowed=(
                status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                and authority_profile.simulated_spot_allowed
            ),
            simulated_futures_allowed=(
                status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                and authority_profile.simulated_futures_allowed
            ),
            requires_manual_confirmation=(
                authority_profile.requires_manual_confirmation
                if status is DgeDecisionStatus.APPROVED_PAPER_ONLY
                else True
            ),
        )

    def _rules(
        self,
        candidate: DgeTradeCandidate,
        context: DgeGovernanceContext,
    ) -> tuple[DgeRuleResult, ...]:
        rule_index = governance_rule_index(self.rule_registry)
        rules = [
            _rule(
                rule_index,
                "DGE_SNAPSHOT_INTEGRITY",
                context.snapshot_integrity_verified,
                _canonical_blocker_code("SNAPSHOT_INTEGRITY_UNVERIFIED"),
            ),
            _rule(
                rule_index,
                "DGE_DATA_QUALITY_GATE",
                context.data_quality_passed,
                _canonical_blocker_code("DATA_QUALITY_GATE_FAILED"),
            ),
            _rule(
                rule_index,
                "DGE_REQUIRED_TIMEFRAMES_PRESENT",
                context.required_timeframes_present,
                _canonical_blocker_code("REQUIRED_TIMEFRAMES_MISSING"),
            ),
            _rule(
                rule_index,
                "DGE_LIQUIDITY_APPROVED",
                context.liquidity_approved,
                _canonical_blocker_code("LIQUIDITY_APPROVAL_MISSING"),
            ),
            _rule(
                rule_index,
                "DGE_WALLET_POSITION_CONTEXT_VERIFIED",
                context.wallet_verified,
                _canonical_blocker_code("WALLET_POSITION_CONTEXT_UNVERIFIED"),
            ),
            _rule(
                rule_index,
                "DGE_NO_COIN_DEPENDENCY_BIAS",
                not context.position_dependency_bias_detected,
                _canonical_blocker_code("COIN_ATTACHMENT_BIAS_BLOCKED"),
            ),
            _rule(
                rule_index,
                "DGE_NO_EXTERNAL_CAPITAL_REQUIRED",
                context.no_new_capital_required
                and candidate.capital_source.strip().upper() != "EXTERNAL_DEPOSIT",
                _canonical_blocker_code("EXTERNAL_CAPITAL_NOT_ALLOWED"),
            ),
            _rule(
                rule_index,
                "DGE_REGIME_COMPATIBLE",
                context.regime_compatible,
                _canonical_blocker_code("REGIME_INCOMPATIBLE_WITH_STRATEGY"),
            ),
            _rule(
                rule_index,
                "DGE_MTF_ALIGNED",
                context.mtf_aligned,
                _canonical_blocker_code("MTF_ALIGNMENT_CONFLICT"),
            ),
            _rule(
                rule_index,
                "DGE_NEGATIVE_EVIDENCE_CLEAR",
                context.negative_evidence_clear,
                _canonical_blocker_code("NEGATIVE_EVIDENCE_PRESENT"),
            ),
            _rule(
                rule_index,
                "DGE_STRUCTURE_VALID",
                context.structure_valid,
                _canonical_blocker_code("STRUCTURAL_INVALIDATION_MISSING"),
            ),
            _rule(
                rule_index,
                "DGE_OOS_APPROVED",
                context.oos_approved,
                _canonical_blocker_code("OOS_APPROVAL_MISSING"),
            ),
            _rule(
                rule_index,
                "DGE_RISK_APPROVED",
                context.risk_approved,
                _canonical_blocker_code("RISK_APPROVAL_MISSING"),
            ),
            _rule(
                rule_index,
                "DGE_VALIDATION_APPROVED",
                context.validation_approved,
                _canonical_blocker_code("VAL.ROBUSTNESS_NOT_VALIDATED"),
            ),
            _rule(
                rule_index,
                "DGE_EXECUTION_FEASIBLE_FOR_PAPER_ONLY",
                context.execution_feasible,
                _canonical_blocker_code("EXECUTION_FEASIBILITY_MISSING"),
            ),
            _rule(
                rule_index,
                "DGE_HUMAN_REVIEW_RECORDED",
                context.human_approval_recorded,
                _canonical_blocker_code("HUMAN_REVIEW_REQUIRED"),
            ),
            _rule(
                rule_index,
                "DGE_SCORE_THRESHOLD",
                candidate.score >= self.minimum_score,
                _canonical_blocker_code("SETUP_SCORE_BELOW_DGE_THRESHOLD"),
            ),
            _rule(
                rule_index,
                "DGE_CONFIDENCE_THRESHOLD",
                candidate.confidence >= self.minimum_confidence,
                _canonical_blocker_code("SETUP_CONFIDENCE_BELOW_DGE_THRESHOLD"),
            ),
            _rule(
                rule_index,
                "DGE_RISK_REWARD_THRESHOLD",
                candidate.risk_reward is not None
                and candidate.risk_reward >= self.minimum_risk_reward,
                _canonical_blocker_code("MIN_RISK_REWARD_NOT_MET"),
            ),
        ]
        rules.extend(
            DgeRuleResult(
                f"DGE_CONTEXT_BLOCKER:{blocker}",
                False,
                DgeRuleSeverity.HARD,
                (_canonical_blocker_code(blocker),),
            )
            for blocker in context.blockers
        )
        return tuple(rules)

    @staticmethod
    def _status(
        candidate: DgeTradeCandidate,
        hard_blockers: tuple[str, ...],
        soft_blockers: tuple[str, ...],
    ) -> DgeDecisionStatus:
        if hard_blockers:
            if any(
                blocker
                in {
                    "DATA.SNAPSHOT_INCOMPLETE",
                    "DATA.DATA_QUALITY_FAILED",
                }
                for blocker in hard_blockers
            ):
                return DgeDecisionStatus.DATA_UNAVAILABLE
            if hard_blockers == ("STRAT.NOT_APPROVED_FOR_STAGE",):
                return DgeDecisionStatus.LOW_CONFIDENCE
            return (
                DgeDecisionStatus.WATCH_ONLY
                if candidate.score >= Decimal("50")
                else DgeDecisionStatus.NO_TRADE
            )
        if soft_blockers:
            return DgeDecisionStatus.MANUAL_REVIEW
        return DgeDecisionStatus.APPROVED_PAPER_ONLY


def _rule(
    rule_index: dict[str, GovernanceRule],
    rule_id: str,
    passed: bool,
    blocker: str,
) -> DgeRuleResult:
    rule = rule_index[rule_id]
    effective_passed = passed if rule.enabled else True
    return DgeRuleResult(
        rule_id,
        effective_passed,
        rule.severity,
        () if effective_passed else (blocker,),
    )


def _reason_summary(
    status: DgeDecisionStatus,
    hard_blockers: tuple[str, ...],
    soft_blockers: tuple[str, ...],
    execution_surface: object,
) -> str:
    if hard_blockers:
        return "DGE keeps the opportunity visible but blocks execution: " + ", ".join(
            hard_blockers[:6]
        )
    if soft_blockers:
        return "DGE requires manual review before paper eligibility."
    if status is DgeDecisionStatus.APPROVED_PAPER_ONLY:
        if str(execution_surface) == "VIRTUAL_MARKET":
            return (
                "DGE autonomous virtual-market simulation criteria passed; "
                "live execution remains blocked."
            )
        return (
            "DGE manual-only Binance market criteria passed; "
            "live execution remains blocked."
        )
    return "DGE returned a conservative non-executable decision."


def _quality_scores(
    candidate: DgeTradeCandidate,
    context: DgeGovernanceContext,
    hard_blockers: tuple[str, ...],
) -> DgeQualityScores:
    confidence_score = candidate.confidence * Decimal("100")
    evidence_score = Decimal("100") if context.oos_approved else Decimal("30")
    data_quality_score = Decimal("100") if context.data_quality_passed else Decimal("0")
    mtf_score = Decimal("100") if context.mtf_aligned else Decimal("50")
    regime_score = Decimal("100") if context.regime_compatible else Decimal("0")
    liquidity_score = Decimal("100") if context.liquidity_approved else Decimal("0")
    risk_score = Decimal("100") if context.risk_approved else Decimal("0")
    execution_score = Decimal("100") if context.execution_feasible else Decimal("50")
    governance_score = _governance_score(
        signal_score=candidate.score,
        evidence_score=evidence_score,
        data_quality_score=data_quality_score,
        mtf_score=mtf_score,
        regime_score=regime_score,
        liquidity_score=liquidity_score,
        risk_score=risk_score,
        execution_score=execution_score,
        confidence_score=confidence_score,
        hard_blockers=hard_blockers,
    )
    return DgeQualityScores(
        signal_score=candidate.score,
        evidence_score=evidence_score,
        data_quality_score=data_quality_score,
        mtf_score=mtf_score,
        regime_score=regime_score,
        liquidity_score=liquidity_score,
        risk_score=risk_score,
        execution_score=execution_score,
        confidence_score=confidence_score,
        governance_score=governance_score,
    )


def _governance_score(
    *,
    signal_score: Decimal,
    evidence_score: Decimal,
    data_quality_score: Decimal,
    mtf_score: Decimal,
    regime_score: Decimal,
    liquidity_score: Decimal,
    risk_score: Decimal,
    execution_score: Decimal,
    confidence_score: Decimal,
    hard_blockers: tuple[str, ...],
) -> Decimal:
    if hard_blockers:
        return Decimal("0")
    weighted = (
        signal_score * Decimal("0.20")
        + evidence_score * Decimal("0.15")
        + data_quality_score * Decimal("0.15")
        + mtf_score * Decimal("0.10")
        + regime_score * Decimal("0.10")
        + liquidity_score * Decimal("0.10")
        + risk_score * Decimal("0.10")
        + execution_score * Decimal("0.05")
        + confidence_score * Decimal("0.05")
    )
    return weighted.quantize(Decimal("0.01"))


def _layer_evaluations(
    status: DgeDecisionStatus,
    hard_blockers: tuple[str, ...],
    soft_blockers: tuple[str, ...],
) -> tuple[DgeLayerEvaluation, ...]:
    return (
        DgeLayerEvaluation(
            layer_id="DGE_LAYER_FINAL_AUTHORITY",
            status=status,
            primary_reason=(
                hard_blockers[0]
                if hard_blockers
                else soft_blockers[0]
                if soft_blockers
                else "DGE_PAPER_ONLY_CRITERIA_PASSED"
            ),
            hard_blockers=hard_blockers,
            soft_blockers=soft_blockers,
        ),
    )


def _required_changes(
    hard_blockers: tuple[str, ...],
    soft_blockers: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _required_change_for(blocker)
            for blocker in (*hard_blockers, *soft_blockers)
        )
    )


def _required_change_for(blocker: str) -> str:
    mapping = {
        "DATA.SNAPSHOT_INCOMPLETE": "refresh_verified_market_snapshot",
        "DATA.DATA_QUALITY_FAILED": "restore_fresh_complete_ohlcv_data",
        "LIQ.APPROVAL_MISSING": "wait_for_spread_depth_slippage_to_normalize",
        "EVID.CRITICAL_CONFLICT_UNRESOLVED": "resolve_conflicting_evidence",
        "EVID.CRITICAL_EVIDENCE_MISSING": "attach_required_evidence",
        "VAL.OOS_NOT_VALIDATED": "complete_oos_validation",
        "VAL.ROBUSTNESS_NOT_VALIDATED": "obtain_validation_approval",
        "RISK.VETO": "obtain_risk_manager_approval",
        "EXEC.HUMAN_CONFIRMATION_MISSING": "record_human_review",
        "EXEC.ORDER_CONSTRAINT_INVALID": "restore_execution_feasibility_evidence",
        "STRAT.NOT_APPROVED_FOR_STAGE": "keep_strategy_in_research",
        "RISK.RISK_LIMIT_EXCEEDED": "restore_risk_limit_compliance",
        "GOV.UNKNOWN_CONTROL_CLASSIFICATION": "classify_control_in_blocker_registry",
    }
    return mapping.get(blocker, f"resolve_{blocker.lower()}")


def _control_evaluation(
    *,
    decision_id: str,
    candidate: DgeTradeCandidate,
    context: DgeGovernanceContext,
    rules: tuple[DgeRuleResult, ...],
    rule_registry: tuple[GovernanceRule, ...],
) -> ControlEvaluation:
    rule_index = governance_rule_index(rule_registry)
    hard_blockers: list[HardBlocker] = []
    soft_penalties: list[SoftPenalty] = []
    for rule_result in rules:
        if rule_result.passed:
            continue
        rule = rule_index.get(rule_result.rule_id)
        for blocker in rule_result.blockers:
            canonical_blocker = _canonical_blocker_code(blocker)
            if rule_result.severity in {DgeRuleSeverity.HARD, DgeRuleSeverity.CRITICAL}:
                hard_blockers.append(
                    _hard_blocker_from_rule(
                        rule_result, canonical_blocker, rule, context
                    )
                )
            elif rule_result.severity in {
                DgeRuleSeverity.SOFT,
                DgeRuleSeverity.WARNING,
            }:
                soft_penalties.append(
                    _soft_penalty_from_rule(
                        rule_result, canonical_blocker, rule, context
                    )
                )
            else:
                hard_blockers.append(
                    HardBlocker(
                        blocker_id=f"hard:{rule_result.rule_id}:{blocker}",
                        blocker_type="UNKNOWN_CONTROL_CLASSIFICATION",
                        source=ControlSource.GOVERNANCE,
                        severity=ControlSeverity.CRITICAL,
                        reason_code="GOV.UNKNOWN_CONTROL_CLASSIFICATION",
                        evidence_refs=_canonical_evidence_refs(context.evidence_refs),
                        policy_ref=f"policy:dge:{rule_result.rule_id}",
                        policy_version=context.policy_versions.policy_version,
                        control_ref=f"control:dge:{rule_result.rule_id}",
                        control_version=context.rule_set_version,
                        producer="DecisionGovernanceEngine",
                        source_component="governance.dge_engine",
                        resolution_authority=(
                            ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE
                        ),
                    )
                )
    return build_control_evaluation(
        evaluation_id=f"control:{decision_id}",
        base_score=candidate.score,
        hard_blockers=tuple(hard_blockers),
        soft_penalties=tuple(soft_penalties),
        eligibility_when_clear=ControlEligibility.ELIGIBLE,
        eligibility_when_blocked=ControlEligibility.NO_TRADE,
        policy_version=context.policy_versions.policy_version,
    )


def _hard_blocker_from_rule(
    rule_result: DgeRuleResult,
    reason_code: str,
    rule: GovernanceRule | None,
    context: DgeGovernanceContext,
) -> HardBlocker:
    definition = _blocker_definition(reason_code)
    source = (
        _control_source(rule.category)
        if rule is not None
        else _control_source_for_definition(
            definition,
            fallback_category="governance",
        )
    )
    return HardBlocker(
        blocker_id=f"hard:{rule_result.rule_id}:{reason_code}",
        blocker_type=rule.category.upper() if rule is not None else "CONTEXT_BLOCKER",
        source=source,
        severity=_control_severity(rule_result.severity),
        reason_code=reason_code,
        evidence_refs=_canonical_evidence_refs(context.evidence_refs),
        policy_ref=definition.policy_ref,
        policy_version=definition.policy_version,
        control_ref=definition.control_ref,
        control_version=definition.control_version,
        producer=definition.producer,
        source_component=definition.source_component,
        scope=definition.scope.value,
        resolution_authority=_resolution_authority(source),
    )


def _soft_penalty_from_rule(
    rule_result: DgeRuleResult,
    reason_code: str,
    rule: GovernanceRule | None,
    context: DgeGovernanceContext,
) -> SoftPenalty:
    definition = _blocker_definition(reason_code)
    source = (
        _control_source(rule.category)
        if rule is not None
        else _control_source_for_definition(
            definition,
            fallback_category="governance",
        )
    )
    return SoftPenalty(
        penalty_id=f"soft:{rule_result.rule_id}:{reason_code}",
        penalty_type=rule.category.upper() if rule is not None else "GOVERNANCE_REVIEW",
        source=source,
        reason_code=reason_code,
        value=_soft_penalty_value(rule_result.severity),
        max_value=Decimal("15"),
        evidence_refs=_canonical_evidence_refs(context.evidence_refs),
        policy_ref=definition.policy_ref,
        policy_version=definition.policy_version,
        control_ref=definition.control_ref,
        control_version=definition.control_version,
        producer=definition.producer,
        source_component=definition.source_component,
        scope=definition.scope.value,
        penalty_group=_penalty_group(source),
    )


@lru_cache(maxsize=1)
def _blocker_registry() -> BlockerRegistry:
    repo_root = Path(__file__).resolve().parents[3]
    return load_blocker_registry(repo_root / BLOCKER_REGISTRY_PATH)


def _blocker_definition(reason_code: str) -> BlockerDefinition:
    return _blocker_registry().require_known_code(reason_code)


def _canonical_blocker_code(reason_code: str) -> str:
    try:
        return _blocker_registry().require_known_code(reason_code).blocker_code
    except ValueError:
        return "GOV.UNKNOWN_CONTROL_CLASSIFICATION"


def _control_source(category: str) -> ControlSource:
    mapping = {
        "data_quality": ControlSource.DATA_QUALITY,
        "liquidity": ControlSource.LIQUIDITY,
        "portfolio": ControlSource.RISK,
        "regime": ControlSource.STRATEGY,
        "mtf": ControlSource.MARKET_STRUCTURE,
        "negative_evidence": ControlSource.EVIDENCE,
        "structure": ControlSource.MARKET_STRUCTURE,
        "validation": ControlSource.VALIDATION,
        "risk": ControlSource.RISK,
        "execution": ControlSource.EXECUTION,
        "human_review": ControlSource.HUMAN_REVIEW,
        "setup_quality": ControlSource.SCORING,
        "system_safety": ControlSource.GOVERNANCE,
    }
    return mapping.get(category, ControlSource.GOVERNANCE)


def _control_source_for_definition(
    definition: BlockerDefinition,
    *,
    fallback_category: str,
) -> ControlSource:
    mapping = {
        BlockerDomain.DATA: ControlSource.DATA_QUALITY,
        BlockerDomain.EVIDENCE: ControlSource.EVIDENCE,
        BlockerDomain.RISK: ControlSource.RISK,
        BlockerDomain.VALIDATION: ControlSource.VALIDATION,
        BlockerDomain.STRATEGY: ControlSource.STRATEGY,
        BlockerDomain.EXECUTION: ControlSource.EXECUTION,
        BlockerDomain.LIQUIDITY: ControlSource.LIQUIDITY,
        BlockerDomain.SECURITY: ControlSource.SECURITY,
        BlockerDomain.GOVERNANCE: ControlSource.GOVERNANCE,
    }
    return mapping.get(definition.domain, _control_source(fallback_category))


def _control_severity(severity: DgeRuleSeverity) -> ControlSeverity:
    if severity is DgeRuleSeverity.CRITICAL:
        return ControlSeverity.CRITICAL
    if severity is DgeRuleSeverity.HARD:
        return ControlSeverity.HIGH
    if severity is DgeRuleSeverity.WARNING:
        return ControlSeverity.WARNING
    return ControlSeverity.MEDIUM


def _resolution_authority(source: ControlSource) -> ControlResolutionAuthority:
    mapping = {
        ControlSource.DATA_QUALITY: ControlResolutionAuthority.DATA_QUALITY_ENGINE,
        ControlSource.RISK: ControlResolutionAuthority.RISK_ENGINE,
        ControlSource.VALIDATION: ControlResolutionAuthority.VALIDATION_ENGINE,
        ControlSource.GOVERNANCE: (ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE),
        ControlSource.LIQUIDITY: ControlResolutionAuthority.LIQUIDITY_ENGINE,
        ControlSource.EXECUTION: ControlResolutionAuthority.EXECUTION_ENGINE,
        ControlSource.SECURITY: ControlResolutionAuthority.SECURITY_ASSURANCE,
        ControlSource.STRATEGY: ControlResolutionAuthority.STRATEGY_GOVERNANCE,
        ControlSource.EVIDENCE: ControlResolutionAuthority.EVIDENCE_FABRIC,
        ControlSource.HUMAN_REVIEW: ControlResolutionAuthority.HUMAN_REVIEW,
    }
    return mapping.get(source, ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE)


def _soft_penalty_value(severity: DgeRuleSeverity) -> Decimal:
    if severity is DgeRuleSeverity.WARNING:
        return Decimal("3")
    return Decimal("5")


def _penalty_group(source: ControlSource) -> str:
    mapping = {
        ControlSource.LIQUIDITY: "LIQUIDITY_QUALITY",
        ControlSource.MARKET_STRUCTURE: "MARKET_STRUCTURE",
        ControlSource.EVIDENCE: "EVIDENCE_QUALITY",
        ControlSource.GOVERNANCE: "GOVERNANCE_REVIEW",
        ControlSource.HUMAN_REVIEW: "GOVERNANCE_REVIEW",
    }
    return mapping.get(source, source.value)


def _canonical_evidence_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(values)))

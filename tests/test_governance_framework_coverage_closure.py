"""Close fail-closed branch gaps in the canonical governance framework."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest

from ai4binance.governance import framework as governance

NOW = datetime(2026, 9, 8, 21, 30, tzinfo=UTC)
HASH = "a" * 64

InvalidFactory = Callable[[], object]


def _mutated[T](instance: T, **changes: object) -> T:
    """Return an isolated frozen-contract clone with deliberate internal drift."""
    clone = copy.copy(instance)
    for field_name, value in changes.items():
        object.__setattr__(clone, field_name, value)
    return clone


def _checks(
    failed: governance.ExecutionGateCheckId | None = None,
) -> MappingProxyType[governance.ExecutionGateCheckId, bool]:
    return MappingProxyType(
        {check: check is not failed for check in governance.ExecutionGateCheckId}
    )


def _risk_assessment() -> governance.RiskAssessmentContract:
    return governance.RiskAssessmentContract(
        risk_assessment_id="risk-coverage",
        cycle_id="cycle-coverage",
        decision_id="decision-coverage",
        market_risk=governance.RiskState.LOW,
        liquidity_risk=governance.RiskState.LOW,
        volatility_risk=governance.RiskState.MEDIUM,
        execution_risk=governance.RiskState.LOW,
        strategy_risk=governance.RiskState.LOW,
        evidence_risk=governance.RiskState.LOW,
        portfolio_risk=governance.RiskState.MEDIUM,
        governance_risk=governance.RiskState.LOW,
        result=governance.RiskAssessmentResult.RESTRICT,
        risk_budget_usdt=Decimal("10"),
        max_loss_usdt=Decimal("5"),
        risk_reward=Decimal("2"),
        blockers=("PORTFOLIO_RISK_RESTRICTED",),
    )


def _portfolio_state() -> governance.PortfolioStateContract:
    return governance.PortfolioStateContract(
        portfolio_state_id="portfolio-coverage",
        cycle_id="cycle-coverage",
        snapshot_id="snapshot-coverage",
        observed_at=NOW,
    )


def _paper_execution_gate() -> governance.ExecutionGateResult:
    return governance.build_execution_gate_result(
        "gate-coverage",
        "decision-coverage",
        governance.ExecutionMode.PAPER,
        _checks(),
    )


def _invalid_execution_gate(**changes: object) -> governance.ExecutionGateResult:
    values: dict[str, object] = {
        "gate_result_id": "gate-invalid",
        "decision_id": "decision-coverage",
        "mode": governance.ExecutionMode.PAPER,
        "checks": _checks(),
        "accepted": True,
        "blockers": (),
        "execution_allowed": True,
    }
    values.update(changes)
    return governance.ExecutionGateResult(**cast(Any, values))


def _architecture_without_backbone() -> governance.CoreArchitecture:
    architecture = governance.AI4BINANCE_CORE_ARCHITECTURE
    domains = tuple(
        replace(domain, backbone=False)
        if domain.domain_id is governance.CanonicalDomainId.EVENT_FABRIC
        else domain
        for domain in architecture.domains
    )
    return replace(architecture, domains=domains)


def _release_record() -> governance.GovernanceReleaseRecord:
    return governance.GovernanceReleaseRecord(
        grr_id="release-coverage",
        component_id="component-coverage",
        component_version="1.0.0",
        environment=governance.GovernanceReleaseEnvironment.PAPER,
        operating_envelope_id="envelope-coverage",
        approval=governance.GovernanceApproval(
            governance.GovernanceApprovalStatus.APPROVED,
            approver="governance-owner",
        ),
        approved_at=NOW,
    )


def _evidence() -> governance.Evidence:
    return governance.Evidence(
        evidence_id="evidence-coverage",
        source_id="source-coverage",
        source_type="LOCAL_FIXTURE",
        observed_at=NOW,
        retrieved_at=NOW,
        provenance=governance.EvidenceProvenance(
            source_reference="local://coverage-fixture",
            content_hash=HASH,
            parser_version="1.0.0",
        ),
        quality=governance.EvidenceQuality(
            source_reliability=1.0,
            freshness_score=1.0,
            confirmation_score=1.0,
            manipulation_risk=0.0,
        ),
        status=governance.EvidenceVerificationStatus.VERIFIED,
    )


def _evidence_completeness() -> governance.EvidenceCompleteness:
    return governance.EvidenceCompleteness(
        required_domains=("license", "integrity", "evidence"),
        received_domains=("license", "integrity", "evidence"),
        missing_domains=(),
        conflicts=(),
        completeness_score=1.0,
        minimum_met=True,
    )


def _research_evaluation() -> governance.ResearchEvaluationResult:
    return governance.ResearchEvaluationResult(
        research_unit_id="research-unit-coverage",
        research_scorecard_id="research-scorecard:coverage:v1",
        hard_gates_passed=True,
        evidence_completeness=_evidence_completeness(),
        research_score=72.5,
        action_ceiling=governance.ActionCeiling.RESEARCH,
        result=governance.ResearchUnitResult.POC_CANDIDATE,
    )


def _research_unit() -> governance.ResearchUnit:
    return governance.ResearchUnit(
        research_unit_id="research-unit-coverage",
        source=governance.ResearchUnitSource(source_id="radar-coverage"),
        capability_candidate_id="capability-candidate-coverage",
        hypothesis="The candidate may improve deterministic diagnostics.",
        expected_value="Improve research evidence after independent validation.",
        duplicate_capability_check=governance.DuplicateCapabilityCheck(
            governance.DuplicateCapabilityCheckStatus.CLEAR
        ),
        license=governance.ResearchLicense(
            governance.ResearchLicenseStatus.KNOWN,
            governance.ResearchReuseMode.REVIEW_ONLY,
        ),
        integrity=governance.ResearchIntegrity(),
        score=governance.ResearchScore(scorecard_id="scorecard-coverage"),
        result=governance.ResearchUnitResult.RESEARCH_ONLY,
        evidence=("evidence-coverage",),
    )


def _decision_cycle() -> governance.DecisionCycleContext:
    return governance.DecisionCycleContext(
        cycle_id="cycle-coverage",
        snapshot_id="snapshot-coverage",
        created_at=NOW,
        symbol="BTCUSDT",
        timeframes=governance.CANONICAL_DEFAULT_TIMEFRAMES,
        market_snapshot="market-snapshot-coverage",
        feature_snapshot="feature-snapshot-coverage",
        evidence_context="evidence-context-coverage",
        risk_state="risk-state-coverage",
        workflow_state="workflow-state-coverage",
        data_quality_state="quality-state-coverage",
        decision_state="decision-state-coverage",
    )


def _registry_entry() -> governance.GovernedRegistryEntry:
    return governance.GovernedRegistryEntry(
        entry_id="indicator:coverage:1",
        registry=governance.RegistryKind.INDICATOR,
        name="Coverage Indicator",
        version="1",
        owner="FeatureEngineering",
        concept=governance.EngineeringConcept.FEATURE_ENGINEERING,
    )


def _registry_catalog() -> governance.GovernanceRegistryCatalog:
    return governance.build_ai4binance_governance_registry_catalog()


def _invalid_core_constitution_change_control(
    **changes: object,
) -> governance.CoreConstitution:
    control = _mutated(governance.ConstitutionalChangeControl(), **changes)
    return replace(governance.AI4BINANCE_CORE_CONSTITUTION, change_control=control)


INVALID_CASES: tuple[tuple[str, InvalidFactory], ...] = (
    (
        "change-control-governance-role",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            governance_gate_role="NOT_POLICY_ELIGIBILITY",
        ),
    ),
    (
        "change-control-human-role",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            human_governance_role="AUTONOMOUS_AUTHORITY",
        ),
    ),
    (
        "change-control-human-free-classes",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            change_classes_without_human_governance=(
                governance.ChangeApprovalClass.C0_NON_BEHAVIORAL,
            ),
        ),
    ),
    (
        "change-control-approval-packet-classes",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            approval_packet_required_change_classes=(
                governance.ChangeApprovalClass.C2_BEHAVIORAL,
            ),
        ),
    ),
    (
        "change-control-sync-classes",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            constitution_sync_change_classes=(
                governance.ChangeApprovalClass.C3_GOVERNED,
            ),
        ),
    ),
    (
        "change-control-double-approval-classes",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            double_approval_change_classes=(
                governance.ChangeApprovalClass.C4_CONSEQUENTIAL,
            ),
        ),
    ),
    (
        "change-control-high-assurance-classes",
        lambda: replace(
            governance.ConstitutionalChangeControl(),
            high_assurance_change_classes=(governance.ChangeApprovalClass.C3_GOVERNED,),
        ),
    ),
    (
        "constitution-quality-role",
        lambda: _invalid_core_constitution_change_control(
            quality_gate_role="NOT_TECHNICAL_TRUTH"
        ),
    ),
    (
        "constitution-human-role",
        lambda: _invalid_core_constitution_change_control(
            human_governance_role="AUTONOMOUS_AUTHORITY"
        ),
    ),
    (
        "constitution-risk-tier",
        lambda: _invalid_core_constitution_change_control(
            risk_tiered_human_governance=False
        ),
    ),
    (
        "domain-owner",
        lambda: replace(governance.AI4BINANCE_CORE_ARCHITECTURE.domains[0], owner=" "),
    ),
    (
        "architecture-identity",
        lambda: replace(governance.AI4BINANCE_CORE_ARCHITECTURE, architecture_id=" "),
    ),
    ("architecture-backbone", _architecture_without_backbone),
    (
        "ownership-risk-owner",
        lambda: governance.EntityOwnership(
            "TechnicalOwner",
            "LogicalOwner",
            risk_owner_required=True,
        ),
    ),
    (
        "ownership-approval-owner",
        lambda: governance.EntityOwnership(
            "TechnicalOwner",
            "LogicalOwner",
            approval_owner_required=True,
        ),
    ),
    (
        "entity-rule-domain",
        lambda: replace(
            governance.AI4BINANCE_ENTITY_RULE_CATALOG,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "technical-timeframes",
        lambda: replace(
            governance.AI4BINANCE_DETERMINISTIC_ANALYTICS_CATALOG.technical_families[0],
            allowed_timeframes=(),
        ),
    ),
    (
        "deterministic-feature-families",
        lambda: replace(
            governance.AI4BINANCE_DETERMINISTIC_ANALYTICS_CATALOG,
            feature_families=(),
        ),
    ),
    (
        "validation-domain",
        lambda: replace(
            governance.AI4BINANCE_VALIDATION_DOMAIN,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "validation-stages",
        lambda: replace(governance.AI4BINANCE_VALIDATION_DOMAIN, stages=()),
    ),
    (
        "hard-blocker-live-state",
        lambda: governance.HardBlockerDecisionResult(
            blockers=(governance.HardBlockerCode.DATA_UNAVAILABLE,),
            result="NO_TRADE",
            live_eligibility_status="LIVE_ELIGIBLE",
        ),
    ),
    (
        "risk-controls",
        lambda: replace(governance.AI4BINANCE_RISK_CONTROL_SET, controls=()),
    ),
    (
        "risk-prohibited-practices",
        lambda: replace(
            governance.AI4BINANCE_RISK_CONTROL_SET,
            prohibited_practices=(),
        ),
    ),
    (
        "risk-assessment-domain",
        lambda: replace(
            _risk_assessment(),
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "risk-assessment-negative-budget",
        lambda: replace(_risk_assessment(), risk_budget_usdt=Decimal("-1")),
    ),
    (
        "risk-assessment-nonpositive-rr",
        lambda: replace(_risk_assessment(), risk_reward=Decimal("0")),
    ),
    (
        "portfolio-components",
        lambda: replace(_portfolio_state(), components=()),
    ),
    (
        "execution-domain",
        lambda: _invalid_execution_gate(domain=governance.CanonicalDomainId.GOVERNANCE),
    ),
    (
        "execution-check-keys",
        lambda: _invalid_execution_gate(checks=MappingProxyType({})),
    ),
    (
        "execution-failed-accepted",
        lambda: _invalid_execution_gate(
            checks=_checks(governance.ExecutionGateCheckId.OOS),
            accepted=True,
            blockers=(governance.ExecutionGateCheckId.OOS.value,),
            execution_allowed=False,
        ),
    ),
    (
        "execution-failed-blocker-mismatch",
        lambda: _invalid_execution_gate(
            checks=_checks(governance.ExecutionGateCheckId.OOS),
            accepted=False,
            blockers=(),
            execution_allowed=False,
        ),
    ),
    (
        "execution-passing-with-blocker",
        lambda: _invalid_execution_gate(blockers=("UNEXPECTED_BLOCKER",)),
    ),
    (
        "execution-acceptance-mismatch",
        lambda: _invalid_execution_gate(execution_allowed=False),
    ),
    (
        "trailing-domain",
        lambda: replace(
            governance.AI4BINANCE_TRAILING_STOP_RULE,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "trailing-trigger",
        lambda: replace(
            governance.AI4BINANCE_TRAILING_STOP_RULE,
            trigger=cast(Any, governance.ExecutionMode.PAPER),
        ),
    ),
    (
        "trailing-review-dimensions",
        lambda: replace(
            governance.AI4BINANCE_TRAILING_STOP_RULE,
            closure_review_dimensions=(),
        ),
    ),
    (
        "learning-allowed-actions",
        lambda: replace(governance.AI4BINANCE_CONTROLLED_LEARNING, allowed_actions=()),
    ),
    (
        "learning-prohibited-actions",
        lambda: replace(
            governance.AI4BINANCE_CONTROLLED_LEARNING,
            prohibited_actions=(),
        ),
    ),
    (
        "learning-lifecycle",
        lambda: replace(governance.AI4BINANCE_CONTROLLED_LEARNING, lifecycle=()),
    ),
    (
        "safe-state-domain",
        lambda: replace(
            governance.AI4BINANCE_SAFE_STATE,
            domain=governance.CanonicalDomainId.RISK,
        ),
    ),
    (
        "core-vnext-fail-result",
        lambda: replace(
            governance.AI4BINANCE_CORE_VNEXT_IDENTITY,
            fail_closed_rule=_mutated(
                governance.AI4BINANCE_CORE_VNEXT_IDENTITY.fail_closed_rule,
                result="WAIT",
            ),
        ),
    ),
    (
        "master-default-auto-live",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            defaults=_mutated(
                governance.AI4BINANCE_CORE_META,
                allow_auto_live_orders=True,
            ),
        ),
    ),
    (
        "master-default-trading-mode",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            defaults=_mutated(governance.AI4BINANCE_CORE_META, trading_mode="live"),
        ),
    ),
    (
        "master-default-order-mode",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            defaults=_mutated(
                governance.AI4BINANCE_CORE_META,
                execution_order_mode="auto",
            ),
        ),
    ),
    (
        "master-deterministic-responsibilities",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            deterministic_core_owns=(),
        ),
    ),
    (
        "master-validation-evidence",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            required_validation_evidence=(),
        ),
    ),
    (
        "master-safe-state-actions",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            safe_state_actions=(),
        ),
    ),
    (
        "master-audit-fields",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            audit_trace_fields=(),
        ),
    ),
    (
        "master-missing-evidence",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            missing_evidence_result="PASS",
        ),
    ),
    (
        "master-unknown-critical-state",
        lambda: replace(
            governance.AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
            unknown_critical_state_result="CONTINUE",
        ),
    ),
    (
        "platform-flow-nodes",
        lambda: replace(
            governance.AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW,
            nodes=(),
        ),
    ),
    (
        "platform-flow-duplicate-computation",
        lambda: replace(
            governance.AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW,
            duplicate_computation_risk_reduced=False,
        ),
    ),
    (
        "platform-flow-fake-maturity",
        lambda: replace(
            governance.AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW,
            fake_maturity_risk_reduced=False,
        ),
    ),
    (
        "platform-flow-oos-hard-gate",
        lambda: replace(
            governance.AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW,
            oos_free_hard_gate_risk_reduced=False,
        ),
    ),
    (
        "standard-output-missing-feeds",
        lambda: replace(
            governance.AI4BINANCE_STANDARD_DECISION_OUTPUT,
            missing_feeds_value="UNKNOWN",
        ),
    ),
    (
        "standard-output-default-quality",
        lambda: replace(
            governance.AI4BINANCE_STANDARD_DECISION_OUTPUT,
            default_quality="TRADE",
        ),
    ),
    (
        "canonical-output-version",
        lambda: replace(
            governance.AI4BINANCE_CANONICAL_DECISION_OUTPUT,
            schema_version="3.0.0",
        ),
    ),
    (
        "continuous-assurance-domain",
        lambda: replace(
            governance.AI4BINANCE_CONTINUOUS_ASSURANCE_ENGINE,
            domain=governance.CanonicalDomainId.RISK,
        ),
    ),
    (
        "continuous-assurance-safe-state",
        lambda: replace(
            governance.AI4BINANCE_CONTINUOUS_ASSURANCE_ENGINE,
            safe_state=_mutated(
                governance.AI4BINANCE_SAFE_STATE, decision_result="WAIT"
            ),
        ),
    ),
    (
        "definition-of-done-domain",
        lambda: governance.GovernanceDefinitionOfDone(
            component_id="component-coverage",
            domain=governance.CanonicalDomainId.RISK,
        ),
    ),
    (
        "definition-of-done-false",
        lambda: governance.GovernanceDefinitionOfDone(
            component_id="component-coverage",
            done=False,
        ),
    ),
    (
        "operating-envelope-domain",
        lambda: replace(
            governance.AI4BINANCE_APPROVED_OPERATING_ENVELOPE,
            domain=governance.CanonicalDomainId.RISK,
        ),
    ),
    (
        "release-domain",
        lambda: replace(
            _release_record(),
            domain=governance.CanonicalDomainId.RISK,
        ),
    ),
    (
        "observation-retrieval-order",
        lambda: governance.EvidenceObservation(
            observation_id="observation-coverage",
            source_id="source-coverage",
            observed_at=NOW,
            retrieved_at=NOW - timedelta(seconds=1),
        ),
    ),
    (
        "evidence-retrieval-order",
        lambda: replace(_evidence(), retrieved_at=NOW - timedelta(seconds=1)),
    ),
    (
        "evidence-domain",
        lambda: replace(_evidence(), domain=governance.CanonicalDomainId.GOVERNANCE),
    ),
    (
        "evidence-pack-domain",
        lambda: governance.EvidencePack(
            evidence_pack_id="pack-coverage",
            evidence_ids=("evidence-coverage",),
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "evidence-pack-mutable",
        lambda: governance.EvidencePack(
            evidence_pack_id="pack-coverage",
            evidence_ids=("evidence-coverage",),
            immutable=False,
        ),
    ),
    (
        "evidence-fabric-objects",
        lambda: replace(governance.AI4BINANCE_APPEND_ONLY_EVIDENCE_FABRIC, objects=()),
    ),
    (
        "evidence-completeness-domain",
        lambda: replace(
            _evidence_completeness(),
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "audit-record-fields",
        lambda: replace(
            governance.AI4BINANCE_AUDIT_OBSERVABILITY_CATALOG,
            minimum_record_fields=(),
        ),
    ),
    (
        "decision-lineage-domain",
        lambda: replace(
            governance.build_decision_lineage("lineage-coverage", "cycle-coverage"),
            domain=governance.CanonicalDomainId.EVIDENCE,
        ),
    ),
    (
        "api-key-policy-domain",
        lambda: governance.ApiKeySecretPolicy(
            domain=governance.CanonicalDomainId.GOVERNANCE
        ),
    ),
    (
        "security-nested-policy-domain",
        lambda: replace(
            governance.AI4BINANCE_SECURITY_CONTRACT,
            api_key_policy=_mutated(
                governance.AI4BINANCE_SECURITY_CONTRACT.api_key_policy,
                domain=governance.CanonicalDomainId.GOVERNANCE,
            ),
        ),
    ),
    (
        "restricted-license-adoption",
        lambda: governance.ResearchLicense(
            governance.ResearchLicenseStatus.RESTRICTED,
            governance.ResearchReuseMode.ADOPT_IDEA,
        ),
    ),
    (
        "research-scorecard-reference",
        lambda: governance.ResearchScore(
            scorecard_id="scorecard-coverage",
            research_scorecard_id=" ",
        ),
    ),
    (
        "research-score-target",
        lambda: governance.ResearchScore(
            scorecard_id="scorecard-coverage",
            score_target="Repository",
        ),
    ),
    (
        "research-score-stars",
        lambda: governance.ResearchScore(
            scorecard_id="scorecard-coverage",
            github_stars_secondary_only=False,
        ),
    ),
    (
        "research-pipeline-domain",
        lambda: governance.ResearchEvaluationPipeline(
            domain=governance.CanonicalDomainId.GOVERNANCE
        ),
    ),
    (
        "research-evaluation-domain",
        lambda: replace(
            _research_evaluation(),
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "research-evaluation-pipeline-order",
        lambda: replace(
            _research_evaluation(),
            pipeline=_mutated(governance.ResearchEvaluationPipeline(), stages=()),
        ),
    ),
    (
        "research-evaluation-weights",
        lambda: replace(
            _research_evaluation(),
            pipeline=_mutated(
                governance.ResearchEvaluationPipeline(),
                weights_embedded=True,
            ),
        ),
    ),
    (
        "research-unit-domain",
        lambda: replace(
            _research_unit(),
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "research-unit-flow",
        lambda: replace(_research_unit(), flow=()),
    ),
    (
        "research-unit-reason-without-blocker",
        lambda: replace(
            _research_unit(),
            not_trading_eligible_reason="NOT_TRADING_ELIGIBLE",
        ),
    ),
    (
        "research-contract-pipeline-order",
        lambda: replace(
            governance.AI4BINANCE_RESEARCH_CAPABILITY_CONTRACT,
            evaluation_pipeline=_mutated(
                governance.ResearchEvaluationPipeline(),
                stages=(),
            ),
        ),
    ),
    (
        "intelligence-fabric-domain",
        lambda: replace(
            governance.AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "intelligence-fabric-sources",
        lambda: replace(
            governance.AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC,
            sources=(),
        ),
    ),
    (
        "intelligence-fabric-indexes",
        lambda: replace(
            governance.AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC,
            indexes=(),
        ),
    ),
    (
        "intelligence-fabric-output",
        lambda: replace(
            governance.AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC,
            produces="RadarFinding",
        ),
    ),
    (
        "governance-pyramid-evidence",
        lambda: replace(
            governance.AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL.pyramid[0],
            required_evidence=(),
        ),
    ),
    (
        "web-radar-pipeline",
        lambda: replace(
            governance.AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT,
            evidence_pipeline=(),
        ),
    ),
    (
        "web-radar-credentialless",
        lambda: replace(
            governance.AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT,
            credentialless_default=False,
        ),
    ),
    (
        "web-radar-domain",
        lambda: replace(
            governance.AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "loops-step-entities",
        lambda: replace(
            governance.AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT.steps[0],
            input_entities=(),
        ),
    ),
    (
        "loops-step-evidence",
        lambda: replace(
            governance.AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT.steps[0],
            required_evidence=(),
        ),
    ),
    (
        "loops-radar-authority",
        lambda: replace(
            governance.AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT,
            web_intelligence_radar=_mutated(
                governance.AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT,
                decision_authority="EXECUTION_AUTHORITY",
            ),
        ),
    ),
    (
        "loops-domain",
        lambda: replace(
            governance.AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "digital-company-loops-domain",
        lambda: replace(
            governance.AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL,
            loops_contract=_mutated(
                governance.AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT,
                domain=governance.CanonicalDomainId.GOVERNANCE,
            ),
        ),
    ),
    (
        "digital-company-domain",
        lambda: replace(
            governance.AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL,
            domain=governance.CanonicalDomainId.LEARNING,
        ),
    ),
    (
        "decision-cycle-symbol",
        lambda: replace(_decision_cycle(), symbol="btcusdt"),
    ),
    (
        "capability-implementation",
        lambda: governance.CapabilityImplementation(" ", "oracle:coverage:1"),
    ),
    (
        "oracle-domain",
        lambda: governance.OracleDefinition(
            oracle_id="oracle:coverage:1",
            capability_id="coverage",
            expected_behavior="Return the deterministic expected result.",
            version="1",
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "score-contribution-weight",
        lambda: governance.ScoreContribution(
            governance.ScoreContributionLevel.LOW,
            " ",
        ),
    ),
    (
        "hard-gate-ineligible-promotion",
        lambda: governance.HardGateContract(
            governance.HardGateEligibility.FALSE,
            promoted=True,
        ),
    ),
    (
        "capability-validation-profile",
        lambda: governance.CapabilityValidationContract(" "),
    ),
    (
        "capability-validation-stages",
        lambda: governance.CapabilityValidationContract(
            "validation:coverage:1",
            stage_status=(),
        ),
    ),
    (
        "capability-identity",
        lambda: replace(
            governance.build_structure_capability_contracts()[0],
            capability_id=" ",
        ),
    ),
    (
        "capability-supported-markets",
        lambda: replace(
            governance.build_structure_capability_contracts()[0],
            supported_markets=(),
        ),
    ),
    (
        "capability-inputs",
        lambda: replace(
            governance.build_structure_capability_contracts()[0],
            inputs=(),
        ),
    ),
    (
        "capability-repainting-guard",
        lambda: replace(
            governance.build_structure_capability_contracts()[0],
            repainting=_mutated(governance.CapabilitySafetyGuard(), allowed=True),
        ),
    ),
    (
        "capability-lookahead-guard",
        lambda: replace(
            governance.build_structure_capability_contracts()[0],
            lookahead=_mutated(governance.CapabilitySafetyGuard(), allowed=True),
        ),
    ),
    (
        "capability-live-authority",
        lambda: replace(
            governance.build_structure_capability_contracts()[0],
            execution_allowed=True,
        ),
    ),
    (
        "capability-coverage-identity",
        lambda: governance.CapabilityCoverage(capability_id=" "),
    ),
    (
        "capability-gap-complete-evidence",
        lambda: replace(
            governance.AI4BINANCE_CAPABILITY_GAP_REGISTRY.gaps[0],
            coverage=_mutated(
                governance.AI4BINANCE_CAPABILITY_GAP_REGISTRY.gaps[0].coverage,
                evidence_complete=True,
            ),
        ),
    ),
    (
        "capability-gap-registry-domain",
        lambda: replace(
            governance.AI4BINANCE_CAPABILITY_GAP_REGISTRY,
            domain=governance.CanonicalDomainId.GOVERNANCE,
        ),
    ),
    (
        "capability-gap-registry-promotion",
        lambda: replace(
            governance.AI4BINANCE_CAPABILITY_GAP_REGISTRY,
            gaps=(
                _mutated(
                    governance.AI4BINANCE_CAPABILITY_GAP_REGISTRY.gaps[0],
                    promotion_eligible=True,
                ),
                *governance.AI4BINANCE_CAPABILITY_GAP_REGISTRY.gaps[1:],
            ),
        ),
    ),
    (
        "agent-capability-empty",
        lambda: governance.AgentCapabilityGovernance(
            agent_id="agent-coverage",
            capability_ids=(),
            capability_coverage=(),
        ),
    ),
    (
        "registry-entry-identity",
        lambda: replace(_registry_entry(), entry_id=" "),
    ),
    (
        "capability-chain-identity",
        lambda: replace(
            governance.build_structure_capability_chains()[0],
            formula_id=" ",
        ),
    ),
    (
        "market-data-description",
        lambda: replace(governance.build_market_data_contracts()[0], description=" "),
    ),
    (
        "registry-catalog-identity",
        lambda: replace(
            _registry_catalog(),
            catalog_id=" ",
        ),
    ),
    (
        "registry-catalog-definitions",
        lambda: replace(
            _registry_catalog(),
            definitions=(
                *_registry_catalog().definitions,
                _registry_catalog().definitions[0],
            ),
        ),
    ),
    (
        "registry-catalog-entries",
        lambda: replace(
            _registry_catalog(),
            entries=(_registry_entry(), _registry_entry()),
        ),
    ),
)


@pytest.mark.parametrize(
    ("case_name", "factory"),
    INVALID_CASES,
    ids=[case_name for case_name, _factory in INVALID_CASES],
)
def test_missing_contract_guards_fail_closed(
    case_name: str,
    factory: InvalidFactory,
) -> None:
    assert case_name
    with pytest.raises(ValueError, match=r".+"):
        factory()


def test_remaining_non_error_branches_preserve_safe_results() -> None:
    no_blocker_result = governance.decision_result_for_hard_blockers(())
    paper_gate = _paper_execution_gate()

    assert no_blocker_result.result == "CONTINUE"
    assert no_blocker_result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert paper_gate.accepted is True
    assert paper_gate.execution_allowed is True
    assert paper_gate.mode is governance.ExecutionMode.PAPER


def test_remaining_blocker_reducers_report_missing_evidence() -> None:
    contract = governance.build_structure_capability_contracts()[0]
    matrix = governance.CapabilityValidationMatrix.from_contract(contract)
    chain = _mutated(governance.build_structure_capability_chains()[0], test_ids=())

    assert "CAPABILITY_VALIDATION_REGIME_EVIDENCE_MISSING" in matrix.blockers
    assert "CAPABILITY_TESTS_MISSING" in chain.blockers
    assert contract.execution_allowed is False
    assert contract.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_timestamp_contract_rejects_non_utc_offset() -> None:
    non_utc = timezone(timedelta(hours=3))
    with pytest.raises(ValueError, match="must use UTC timezone"):
        governance.EvidenceObservation(
            observation_id="observation-offset",
            source_id="source-coverage",
            observed_at=NOW.astimezone(non_utc),
            retrieved_at=NOW.astimezone(non_utc),
        )

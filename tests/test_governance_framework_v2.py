from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from math import nan
from types import MappingProxyType
from typing import Any, cast

import pytest

from ai4binance.agents import (
    AgentAnatomyPart,
    AgentAuthorityContract,
    AgentCapabilitiesContract,
    AgentContract,
    AgentEvidenceLayer,
    AgentEvidenceReference,
    AgentEvidenceStatus,
    AgentFailureContract,
    AgentIdentityContract,
    AgentInputsContract,
    AgentIntelligenceType,
    AgentObservation,
    AgentOutputsContract,
    AgentValidationContract,
    VerificationCheck,
    VerificationLayer,
    VerificationResult,
)
from ai4binance.agents.catalog import build_default_registry
from ai4binance.governance import (
    AI4BINANCE_APPEND_ONLY_EVIDENCE_FABRIC,
    AI4BINANCE_APPROVED_OPERATING_ENVELOPE,
    AI4BINANCE_AUDIT_OBSERVABILITY_CATALOG,
    AI4BINANCE_CANONICAL_DECISION_OUTPUT,
    AI4BINANCE_CANONICAL_ENTITY_ONTOLOGY,
    AI4BINANCE_CAPABILITY_GAP_REGISTRY,
    AI4BINANCE_CONTINUOUS_ASSURANCE_ENGINE,
    AI4BINANCE_CONTROLLED_LEARNING,
    AI4BINANCE_CORE_ARCHITECTURE,
    AI4BINANCE_CORE_CONSTITUTION,
    AI4BINANCE_CORE_META,
    AI4BINANCE_CORE_VNEXT_IDENTITY,
    AI4BINANCE_DECISION_CORE_PIPELINE,
    AI4BINANCE_DECISION_STATE_MACHINE,
    AI4BINANCE_DETERMINISTIC_ANALYTICS_CATALOG,
    AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL,
    AI4BINANCE_ENTITY_RULE_CATALOG,
    AI4BINANCE_EVENT_FABRIC_CONTRACT,
    AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC,
    AI4BINANCE_EXTERNAL_STANDARDS_MAPPING,
    AI4BINANCE_GOVERNANCE_PRIMITIVES,
    AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW,
    AI4BINANCE_HUMAN_DECISION_OUTPUT_FORMAT,
    AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT,
    AI4BINANCE_MASTER_CORE_INSTRUCTIONS,
    AI4BINANCE_RELATIONSHIP_RULE_CATALOG,
    AI4BINANCE_RESEARCH_CAPABILITY_CONTRACT,
    AI4BINANCE_RISK_CONTROL_SET,
    AI4BINANCE_SAFE_STATE,
    AI4BINANCE_SECURITY_CONTRACT,
    AI4BINANCE_STANDARD_DECISION_OUTPUT,
    AI4BINANCE_TRAILING_STOP_RULE,
    AI4BINANCE_VALIDATION_DOMAIN,
    AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT,
    CANONICAL_EXECUTION_ROUTE,
    MANDATORY_REGISTRY_KINDS,
    ActionCeiling,
    AdvisoryLlmAllowedAction,
    AdvisoryLlmProhibitedAction,
    AgentCapabilityGovernance,
    ApiKeySecretPolicy,
    ApiKeyStorageLocation,
    AppendOnlyEvidenceFabric,
    ApprovedOperatingEnvelope,
    ApprovedOperatingEnvelopeExecution,
    ArchitecturePlane,
    AuditObservabilityCatalog,
    AuditObservabilityChannel,
    AuditRecord,
    AuditRecordField,
    AuditTraceField,
    AuthorityPrinciple,
    CanonicalCycleStep,
    CanonicalDecisionOutputContract,
    CanonicalDecisionStateMachine,
    CanonicalDomainDefinition,
    CanonicalDomainId,
    CanonicalEntityOntology,
    CanonicalEventType,
    CapabilityContract,
    CapabilityCoverage,
    CapabilityFamily,
    CapabilityGap,
    CapabilityGapArea,
    CapabilityGapPriorityStep,
    CapabilityGapRegistry,
    CapabilityGapStatus,
    CapabilityImplementation,
    CapabilityRole,
    CapabilitySafetyGuard,
    CapabilityStatus,
    CapabilityValidationChain,
    CapabilityValidationContract,
    CapabilityValidationMatrix,
    ChangeApprovalClass,
    ClosureReviewDimension,
    ConstitutionalChangeControl,
    ContinuousAssuranceDomain,
    ContinuousAssuranceEngine,
    ContinuousAssuranceState,
    ControlledLearningAllowedAction,
    ControlledLearningContract,
    ControlledLearningLifecycleStep,
    ControlledLearningProhibitedAction,
    CoreArchitecture,
    CoreAuthorityOwner,
    CoreConstitution,
    CoreConstitutionRule,
    CoreConstitutionRuleId,
    CoreEntity,
    CoreMeta,
    CoreVNextDescriptor,
    CoreVNextIdentity,
    CoreVNextPrinciple,
    CriticalArchitectureImprovement,
    CycleAgentObservationRef,
    DecisionCorePipeline,
    DecisionCycleContext,
    DecisionLifecycleState,
    DecisionLineage,
    DecisionLineageStep,
    DecisionPipelineStage,
    DecisionScoreGovernanceResult,
    DecisionTerminalState,
    DeterministicAnalyticsCatalog,
    DeterministicCoreResponsibility,
    DeterministicFeatureFamily,
    DigitalCompanyOperatingModel,
    DuplicateCapabilityCheck,
    DuplicateCapabilityCheckStatus,
    EngineeringConcept,
    EntityFamily,
    EntityLifecycleStatus,
    EntityOwnership,
    EntityRuleCatalog,
    EntityRuleId,
    EventEnvelope,
    EventFabricContract,
    Evidence,
    EvidenceClaim,
    EvidenceCompleteness,
    EvidenceContradiction,
    EvidenceFabricStage,
    EvidenceIndexKind,
    EvidenceObjectKind,
    EvidenceObservation,
    EvidencePack,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSource,
    EvidenceVerificationStatus,
    ExecutionGateCheckId,
    ExecutionGateResult,
    ExecutionMode,
    ExecutionRouteStep,
    ExternalFrameworkId,
    ExternalIntelligenceEvidenceFabric,
    ExternalIntelligenceSource,
    ExternalStandardsMappingContract,
    FailClosedDecisionRule,
    GovernanceApproval,
    GovernanceApprovalStatus,
    GovernanceDefinitionOfDone,
    GovernanceDefinitionOfReady,
    GovernanceDoneCriterion,
    GovernanceMaturity,
    GovernancePrimitive,
    GovernancePrimitiveCatalog,
    GovernancePyramidLayer,
    GovernancePyramidLevel,
    GovernanceReadyCriterion,
    GovernanceRegistryCatalog,
    GovernanceReleaseEnvironment,
    GovernanceReleaseRecord,
    GovernedCapabilityPlatformFlow,
    GovernedRegistryEntry,
    HardBlockerCode,
    HardBlockerDecisionResult,
    HardGateContract,
    HardGateEligibility,
    HumanDecisionColumn,
    HumanDecisionOutputFormat,
    ImmutableEntityKind,
    IntelligenceRetrievalTechnique,
    LegalSourceMetadata,
    LegalSourceStatus,
    LoopsSelfImprovementContract,
    LoopsStage,
    LoopsStep,
    MarketDataContract,
    MarketDataKind,
    MasterCoreInstructions,
    NeverFabricateDataKind,
    NormalizedMarketDataRecord,
    OracleDefinition,
    PersistentEntityIdentity,
    PlatformFlowEdge,
    PlatformFlowNode,
    PolicyAsCodeDocument,
    PolicyAsCodeEngine,
    PolicyAsCodeRule,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyEvaluation,
    PolicyRequest,
    PortfolioStateComponent,
    PortfolioStateContract,
    ProhibitedRiskPractice,
    RawMarketDataRecord,
    RegistryDefinition,
    RegistryKind,
    RelationshipRule,
    RelationshipRuleCatalog,
    RelationshipRuleId,
    RelationshipTriple,
    RelationshipType,
    ResearchCapabilityDomainContract,
    ResearchCapabilityStep,
    ResearchEvaluationPipeline,
    ResearchEvaluationResult,
    ResearchEvaluationStage,
    ResearchIntegrity,
    ResearchLicense,
    ResearchLicenseStatus,
    ResearchReuseMode,
    ResearchScore,
    ResearchUnit,
    ResearchUnitResult,
    ResearchUnitSource,
    RiskAssessmentContract,
    RiskAssessmentResult,
    RiskControlId,
    RiskControlSet,
    RiskCriticalityTier,
    RiskState,
    SafeState,
    SafeStateAction,
    ScoreContribution,
    ScoreContributionLevel,
    SecretProhibitedSink,
    SecurityControlDomain,
    SecurityDomainContract,
    SpotDecisionAuthority,
    StandardDecisionOutputContract,
    StandardDecisionSection,
    StateSeparationKind,
    StructuralCapabilityId,
    TechnicalFamilyGovernance,
    TechnicalFamilyId,
    TradingImpactingDoneCriterion,
    TrailingStopDirection,
    TrailingStopRuleContract,
    TrailingStopTrigger,
    UnknownRepresentation,
    UnsafeDecisionState,
    ValidationDomainContract,
    ValidationEvidenceStatus,
    ValidationStage,
    VersionedTradingComponent,
    WebIntelligenceRadarContract,
    action_ceiling_for_maturity,
    build_ai4binance_governance_registry_catalog,
    build_append_only_evidence_fabric,
    build_approved_operating_envelope,
    build_audit_observability_catalog,
    build_canonical_decision_output_contract,
    build_canonical_decision_state_machine,
    build_canonical_entity_ontology,
    build_capability_coverage_matrix,
    build_capability_gap_registry,
    build_continuous_assurance_engine,
    build_controlled_learning_contract,
    build_core_architecture,
    build_core_constitution,
    build_core_meta,
    build_core_vnext_identity,
    build_decision_core_pipeline,
    build_decision_lineage,
    build_deterministic_analytics_catalog,
    build_digital_company_operating_model,
    build_entity_rule_catalog,
    build_event_fabric_contract,
    build_execution_gate_result,
    build_external_intelligence_evidence_fabric,
    build_external_standards_mapping_contract,
    build_governance_primitive_catalog,
    build_governed_capability_platform_flow,
    build_human_decision_output_format,
    build_loops_self_improvement_contract,
    build_market_data_contracts,
    build_master_core_instructions,
    build_relationship_rule_catalog,
    build_research_capability_domain_contract,
    build_risk_control_set,
    build_safe_state,
    build_security_domain_contract,
    build_standard_decision_output_contract,
    build_structure_capability_chains,
    build_structure_capability_contracts,
    build_trailing_stop_rule_contract,
    build_validation_domain_contract,
    build_web_intelligence_radar_contract,
    decision_result_for_hard_blockers,
    deny_all_policy_as_code,
)

NOW = datetime(2026, 8, 13, 17, 0, tzinfo=UTC)
HASH = "a" * 64


def test_core_meta_keeps_fail_closed_paper_defaults() -> None:
    meta = build_core_meta()

    assert meta is not AI4BINANCE_CORE_META
    assert meta.schema_version == "2.0.0"
    assert meta.platform == "AI4Binance EnterpriseAI vNext"
    assert meta.environment == "paper"
    assert meta.exchange == "Binance"
    assert meta.default_market == "spot"
    assert meta.default_symbol == "HOTUSDT"
    assert meta.default_timeframes == ("5m", "15m", "1h", "4h", "1d")
    assert meta.trading_mode == "paper"
    assert meta.execution_order_mode == "manual"
    assert meta.allow_auto_live_orders is False
    assert meta.fail_policy == "NO_TRADE"
    assert meta.timezone == "UTC"


def test_core_meta_rejects_live_and_timezone_drift() -> None:
    with pytest.raises(ValueError, match="automatic live orders"):
        CoreMeta(allow_auto_live_orders=True)

    with pytest.raises(ValueError, match="UTC"):
        CoreMeta(timezone="Europe/Istanbul")

    with pytest.raises(ValueError, match="default_timeframes"):
        CoreMeta(default_timeframes=("1h",))


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"schema_version": "1.0.0"}, "schema_version"),
        ({"platform": "AI4Binance Legacy"}, "platform drift"),
        ({"environment": "live"}, "paper environment"),
        ({"trading_mode": "live"}, "paper environment"),
        ({"exchange": "Kraken"}, "exchange must be Binance"),
        ({"default_market": "futures"}, "default_market"),
        ({"default_symbol": "BTCUSDT"}, "default_symbol"),
        ({"execution_order_mode": "auto"}, "execution_order_mode"),
        ({"fail_policy": "WAIT"}, "fail_policy"),
    ],
)
def test_core_meta_rejects_additional_default_drift(
    kwargs: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        CoreMeta(**cast(Any, kwargs))


def test_core_vnext_identity_maps_unsafe_states_to_no_trade() -> None:
    identity = build_core_vnext_identity()

    assert identity is not AI4BINANCE_CORE_VNEXT_IDENTITY
    assert identity.title == "AI4BINANCE CORE vNext"
    assert identity.descriptors == (
        CoreVNextDescriptor.AI4BINANCE,
        CoreVNextDescriptor.ONTOLOGY_DRIVEN,
        CoreVNextDescriptor.EVIDENCE_BASED,
        CoreVNextDescriptor.RISK_CONTROLLED,
        CoreVNextDescriptor.DETERMINISTIC,
        CoreVNextDescriptor.MULTI_AGENT,
        CoreVNextDescriptor.CONTINUOUSLY_ASSURED,
        CoreVNextDescriptor.ALGORITHMIC_TRADING_DECISION_PLATFORM,
    )
    assert identity.principles == (
        CoreVNextPrinciple.DATA_CREATES_OBSERVATIONS,
        CoreVNextPrinciple.EVIDENCE_SUPPORTS_CLAIMS,
        CoreVNextPrinciple.AGENTS_ANALYZE,
        CoreVNextPrinciple.STRATEGIES_IDENTIFY_SETUPS,
        CoreVNextPrinciple.SCORING_RANKS_OPPORTUNITIES,
        CoreVNextPrinciple.GOVERNANCE_DECIDES_ELIGIBILITY,
        CoreVNextPrinciple.RISK_CONSTRAINS_EXPOSURE,
        CoreVNextPrinciple.EXECUTION_OBEYS,
        CoreVNextPrinciple.AUDIT_PRESERVES_LINEAGE,
        CoreVNextPrinciple.HUMAN_RETAINS_AUTHORITY,
        CoreVNextPrinciple.LEARNING_PROPOSES,
        CoreVNextPrinciple.VALIDATION_PROMOTES,
    )
    assert identity.fail_closed_rule.unsafe_states == (
        UnsafeDecisionState.UNKNOWN,
        UnsafeDecisionState.INCONSISTENT,
        UnsafeDecisionState.UNVALIDATED,
        UnsafeDecisionState.UNAUTHORIZED,
        UnsafeDecisionState.STALE,
        UnsafeDecisionState.UNSAFE,
    )
    assert identity.fail_closed_rule.result == "NO_TRADE"
    assert identity.final_live_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="title"):
        CoreVNextIdentity(title="AI4BINANCE CORE")
    with pytest.raises(ValueError, match="descriptors"):
        CoreVNextIdentity(descriptors=tuple(CoreVNextDescriptor)[:-1])
    with pytest.raises(ValueError, match="principles"):
        CoreVNextIdentity(principles=tuple(CoreVNextPrinciple)[:-1])
    with pytest.raises(ValueError, match="unsafe states"):
        FailClosedDecisionRule(unsafe_states=tuple(UnsafeDecisionState)[:-1])
    with pytest.raises(ValueError, match="NO_TRADE"):
        FailClosedDecisionRule(result="WAIT")
    with pytest.raises(ValueError, match="LIVE_ORDER_BLOCKED"):
        CoreVNextIdentity(final_live_status="LIVE_APPROVED")


def test_master_core_instructions_enforce_advisory_and_fail_closed_defaults() -> None:
    instructions = build_master_core_instructions()

    assert instructions is not AI4BINANCE_MASTER_CORE_INSTRUCTIONS
    assert instructions.version == "2.0"
    assert instructions.defaults.default_symbol == "HOTUSDT"
    assert instructions.defaults.exchange == "Binance"
    assert instructions.defaults.default_timeframes == ("5m", "15m", "1h", "4h", "1d")
    assert instructions.defaults.trading_mode == "paper"
    assert instructions.defaults.execution_order_mode == "manual"
    assert instructions.defaults.allow_auto_live_orders is False
    assert instructions.canonical_cycle == tuple(CanonicalCycleStep)
    assert instructions.decision_order == tuple(DecisionPipelineStage)
    assert instructions.llm_allowed_actions == (
        AdvisoryLlmAllowedAction.RETRIEVE,
        AdvisoryLlmAllowedAction.CLASSIFY,
        AdvisoryLlmAllowedAction.EXPLAIN,
        AdvisoryLlmAllowedAction.SUMMARIZE,
        AdvisoryLlmAllowedAction.IDENTIFY_CONFLICTS,
        AdvisoryLlmAllowedAction.PROPOSE_RESEARCH,
        AdvisoryLlmAllowedAction.RECOMMEND_CANDIDATE_EXPERIMENTS,
    )
    assert instructions.llm_prohibited_actions == (
        AdvisoryLlmProhibitedAction.AUTHORIZE_TRADES,
        AdvisoryLlmProhibitedAction.OVERRIDE_RISK,
        AdvisoryLlmProhibitedAction.OVERRIDE_GOVERNANCE,
        AdvisoryLlmProhibitedAction.BYPASS_HARD_GATES,
        AdvisoryLlmProhibitedAction.CHANGE_APPROVED_RISK_LIMITS,
        AdvisoryLlmProhibitedAction.PROMOTE_PARAMETERS,
        AdvisoryLlmProhibitedAction.PROMOTE_STRATEGIES,
        AdvisoryLlmProhibitedAction.EXECUTE_LIVE_ORDERS,
    )
    assert instructions.deterministic_core_owns == (
        DeterministicCoreResponsibility.FEATURE_CALCULATION,
        DeterministicCoreResponsibility.SETUP_QUALIFICATION,
        DeterministicCoreResponsibility.DETERMINISTIC_SCORING,
        DeterministicCoreResponsibility.BLOCKER_EVALUATION,
        DeterministicCoreResponsibility.ACTION_CLASSIFICATION,
        DeterministicCoreResponsibility.RISK_CALCULATIONS,
        DeterministicCoreResponsibility.EXECUTION_ELIGIBILITY,
    )
    assert instructions.never_fabricate == tuple(NeverFabricateDataKind)
    assert instructions.required_validation_evidence == (
        ValidationStage.BACKTEST,
        ValidationStage.WALK_FORWARD,
        ValidationStage.OOS,
        ValidationStage.MONTE_CARLO,
        ValidationStage.REGIME_TESTS,
    )
    assert instructions.safe_state_actions == tuple(SafeStateAction)
    assert instructions.audit_trace_fields == tuple(AuditTraceField)
    assert instructions.agents_final_decision_authority is False
    assert instructions.llm_advisory_only is True
    assert instructions.search_first_for_reasons_not_to_trade is True
    assert instructions.high_score_overrides_hard_blocker is False
    assert instructions.social_claim_can_authorize_trade is False
    assert instructions.missing_evidence_result == "UNKNOWN"
    assert instructions.data_unavailable_result == "DATA_UNAVAILABLE"
    assert instructions.weak_evidence_result == "LOW_CONFIDENCE"
    assert instructions.unknown_critical_state_result == "DENY / NO_TRADE"
    assert instructions.live_default_status == "LIVE_ORDER_BLOCKED"
    assert instructions.immutable_historical_records is True

    with pytest.raises(ValueError, match="version"):
        MasterCoreInstructions(version="2.1")
    with pytest.raises(ValueError, match="canonical cycle"):
        MasterCoreInstructions(
            canonical_cycle=tuple(reversed(tuple(CanonicalCycleStep)))
        )
    with pytest.raises(ValueError, match="decision order"):
        MasterCoreInstructions(
            decision_order=tuple(reversed(tuple(DecisionPipelineStage)))
        )
    with pytest.raises(ValueError, match="allowed actions"):
        MasterCoreInstructions(llm_allowed_actions=tuple(AdvisoryLlmAllowedAction)[:-1])
    with pytest.raises(ValueError, match="prohibited actions"):
        MasterCoreInstructions(
            llm_prohibited_actions=tuple(AdvisoryLlmProhibitedAction)[:-1]
        )
    with pytest.raises(ValueError, match="never-fabricate"):
        MasterCoreInstructions(never_fabricate=tuple(NeverFabricateDataKind)[:-1])
    with pytest.raises(ValueError, match="final trade decisions"):
        MasterCoreInstructions(agents_final_decision_authority=True)
    with pytest.raises(ValueError, match="advisory only"):
        MasterCoreInstructions(llm_advisory_only=False)
    with pytest.raises(ValueError, match="reasons not to trade"):
        MasterCoreInstructions(search_first_for_reasons_not_to_trade=False)
    with pytest.raises(ValueError, match="hard blocker"):
        MasterCoreInstructions(high_score_overrides_hard_blocker=True)
    with pytest.raises(ValueError, match="social claim"):
        MasterCoreInstructions(social_claim_can_authorize_trade=True)
    with pytest.raises(ValueError, match="DATA_UNAVAILABLE"):
        MasterCoreInstructions(data_unavailable_result="NO_TRADE")
    with pytest.raises(ValueError, match="LOW_CONFIDENCE"):
        MasterCoreInstructions(weak_evidence_result="UNKNOWN")
    with pytest.raises(ValueError, match="LIVE_ORDER_BLOCKED"):
        MasterCoreInstructions(live_default_status="LIVE_APPROVED")
    with pytest.raises(ValueError, match="immutable"):
        MasterCoreInstructions(immutable_historical_records=False)


def test_decision_output_contracts_keep_human_and_machine_outputs_fail_closed() -> None:
    human = build_human_decision_output_format()
    standard = build_standard_decision_output_contract()
    canonical = build_canonical_decision_output_contract()
    machine = build_canonical_decision_state_machine()

    assert human is not AI4BINANCE_HUMAN_DECISION_OUTPUT_FORMAT
    assert standard is not AI4BINANCE_STANDARD_DECISION_OUTPUT
    assert canonical is not AI4BINANCE_CANONICAL_DECISION_OUTPUT
    assert machine is not AI4BINANCE_DECISION_STATE_MACHINE
    assert human.columns == (
        HumanDecisionColumn.COIN,
        HumanDecisionColumn.DIRECTION,
        HumanDecisionColumn.QUALITY,
        HumanDecisionColumn.ORDER,
        HumanDecisionColumn.ENTRY,
        HumanDecisionColumn.STOP_LOSS,
        HumanDecisionColumn.TP1,
        HumanDecisionColumn.TP2,
        HumanDecisionColumn.TP3,
        HumanDecisionColumn.LEVERAGE,
        HumanDecisionColumn.BUDGET_MARGIN,
        HumanDecisionColumn.RISK_REWARD,
        HumanDecisionColumn.NEWS_RISK,
        HumanDecisionColumn.DECISION,
    )
    assert human.spot_leverage_value == "N/A"
    assert human.unavailable_value == "DATA_UNAVAILABLE"
    assert human.low_confidence_value == "LOW_CONFIDENCE"
    assert human.fabricate_missing_prices_allowed is False
    assert standard.sections == (
        StandardDecisionSection.BASIC_DECISION,
        StandardDecisionSection.MARKET_OUTLOOK,
        StandardDecisionSection.SETUP_TECHNICAL_EVIDENCE,
        StandardDecisionSection.LIQUIDITY_DERIVATIVES_INTELLIGENCE,
        StandardDecisionSection.RISK_GOVERNANCE,
        StandardDecisionSection.TRADE_PLAN,
        StandardDecisionSection.EXECUTION_TAGGING,
        StandardDecisionSection.CLOSURE_REVIEW,
        StandardDecisionSection.LEARNING_RECORD,
    )
    assert standard.missing_feeds_value == "DATA_UNAVAILABLE"
    assert standard.default_quality == "NO_TRADE"
    assert standard.execution_allowed_default is False
    assert canonical.schema_version == "2.0.0"
    assert canonical.no_fabricated_prices is True
    assert canonical.template["meta"]["symbol"] == "HOTUSDT"
    assert canonical.template["meta"]["market"] == "SPOT"
    assert canonical.template["setup"]["quality"] == "NO_TRADE"
    assert canonical.template["setup"]["pattern_type"] is None
    assert canonical.template["decision"]["action"] == "NO_TRADE"
    assert canonical.template["decision"]["confidence"] is None
    assert canonical.template["decision"]["execution_allowed"] is False
    assert canonical.template["risk"]["result"] == "BLOCK"
    assert canonical.template["execution"]["trading_mode"] == "paper"
    assert canonical.template["execution"]["order_mode"] == "manual"
    assert canonical.template["execution"]["status"] == "NOT_EXECUTED"
    assert canonical.template["trade_plan"]["entry"] is None
    assert canonical.template["trade_plan"]["entry_rationale"] is None
    assert canonical.template["trade_plan"]["stop_loss"] is None
    assert canonical.template["trade_plan"]["tp1"] is None
    assert canonical.template["trade_plan"]["tp2"] is None
    assert canonical.template["trade_plan"]["tp3"] is None
    assert canonical.template["trade_plan"]["discovery_method"] is None
    assert canonical.template["trade_plan"]["markets"] == []
    assert canonical.template["trade_plan"]["timeframes"] == []
    assert canonical.template["trade_plan"]["market_conditions"] == {
        "trend_state": "UNKNOWN",
        "range_state": "UNKNOWN",
        "choppy_state": "UNKNOWN",
        "volatile_state": "UNKNOWN",
        "determination_method": None,
        "early_exit_conditions": [],
    }
    assert canonical.template["trade_plan"]["risk_controls"] == {
        "position_size": None,
        "daily_loss_limit": None,
        "weekly_loss_limit": None,
        "monthly_loss_limit": None,
        "max_positions": None,
        "max_capital_per_position": None,
        "hold_through_major_events": None,
        "hold_overnight": None,
        "hold_weekend": None,
    }
    assert canonical.template["trade_plan"]["review"] == {
        "review_cadence": None,
        "mistake_tracking": [],
        "improvement_actions": [],
    }
    assert machine.progression == (
        DecisionLifecycleState.CREATED,
        DecisionLifecycleState.DATA_PENDING,
        DecisionLifecycleState.DATA_VALIDATED,
        DecisionLifecycleState.SNAPSHOT_READY,
        DecisionLifecycleState.FEATURES_READY,
        DecisionLifecycleState.OBSERVATIONS_READY,
        DecisionLifecycleState.EVIDENCE_VALIDATED,
        DecisionLifecycleState.SETUP_EVALUATED,
        DecisionLifecycleState.DECISION_EVALUATED,
        DecisionLifecycleState.RISK_EVALUATED,
        DecisionLifecycleState.GOVERNANCE_EVALUATED,
        DecisionLifecycleState.EXECUTION_GATE_EVALUATED,
    )
    assert machine.terminal_states == (
        DecisionTerminalState.NO_TRADE,
        DecisionTerminalState.WAIT,
        DecisionTerminalState.HOLD,
        DecisionTerminalState.PAPER_READY,
        DecisionTerminalState.MANUAL_READY,
        DecisionTerminalState.LIVE_BLOCKED,
        DecisionTerminalState.EXECUTED,
    )

    with pytest.raises(ValueError, match="columns"):
        HumanDecisionOutputFormat(columns=tuple(HumanDecisionColumn)[:-1])
    with pytest.raises(ValueError, match="Spot leverage"):
        HumanDecisionOutputFormat(spot_leverage_value="1x")
    with pytest.raises(ValueError, match="DATA_UNAVAILABLE"):
        HumanDecisionOutputFormat(unavailable_value="0")
    with pytest.raises(ValueError, match="LOW_CONFIDENCE"):
        HumanDecisionOutputFormat(low_confidence_value="UNKNOWN")
    with pytest.raises(ValueError, match="fabricated"):
        HumanDecisionOutputFormat(fabricate_missing_prices_allowed=True)
    with pytest.raises(ValueError, match="sections"):
        StandardDecisionOutputContract(sections=tuple(StandardDecisionSection)[:-1])
    with pytest.raises(ValueError, match="execution allowed"):
        StandardDecisionOutputContract(execution_allowed_default=True)

    mutated_template = build_canonical_decision_output_contract().template
    mutated_template["setup"]["pattern_type"] = "REVERSAL_PATTERN"
    with pytest.raises(ValueError, match="template drifted"):
        CanonicalDecisionOutputContract(template=mutated_template)
    with pytest.raises(ValueError, match="fabricated"):
        CanonicalDecisionOutputContract(no_fabricated_prices=False)
    with pytest.raises(ValueError, match="progression"):
        CanonicalDecisionStateMachine(
            progression=tuple(reversed(tuple(DecisionLifecycleState)))
        )
    with pytest.raises(ValueError, match="terminal states"):
        CanonicalDecisionStateMachine(terminal_states=tuple(DecisionTerminalState)[:-1])


def test_governed_capability_platform_flow_keeps_agents_as_bounded_actors() -> None:
    flow = build_governed_capability_platform_flow()

    assert flow is not AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW
    assert flow.nodes == tuple(PlatformFlowNode)
    assert flow.model_identity == "governed capability platform"
    assert flow.agent_role == "actor executing governed capabilities"
    assert flow.multi_agent_trading_system is False
    assert flow.agent_is_feature_proxy is False
    assert flow.duplicate_computation_risk_reduced is True
    assert flow.fake_maturity_risk_reduced is True
    assert flow.oos_free_hard_gate_risk_reduced is True
    assert flow.critical_improvements == (
        CriticalArchitectureImprovement.CAPABILITY_FIRST_GOVERNANCE,
        CriticalArchitectureImprovement.FORMULA_ORACLE_LINEAGE,
        CriticalArchitectureImprovement.CAPABILITY_COVERAGE_MATRIX,
        CriticalArchitectureImprovement.APPEND_ONLY_EVIDENCE_FABRIC,
        CriticalArchitectureImprovement.EVIDENCE_COMPLETENESS_GATE,
        CriticalArchitectureImprovement.ACTION_CEILING,
        CriticalArchitectureImprovement.RESEARCH_UNIT_LIFECYCLE,
        CriticalArchitectureImprovement.SINGLE_EVENT_ENVELOPE,
    )
    assert flow.edges == (
        PlatformFlowEdge(
            PlatformFlowNode.ENTERPRISE_AI, PlatformFlowNode.GOVERNANCE_REGISTRY
        ),
        PlatformFlowEdge(
            PlatformFlowNode.GOVERNANCE_REGISTRY, PlatformFlowNode.EVENT_FABRIC
        ),
        PlatformFlowEdge(PlatformFlowNode.EVENT_FABRIC, PlatformFlowNode.MARKET_DATA),
        PlatformFlowEdge(PlatformFlowNode.MARKET_DATA, PlatformFlowNode.DATA_QUALITY),
        PlatformFlowEdge(
            PlatformFlowNode.DATA_QUALITY, PlatformFlowNode.CANONICAL_SNAPSHOT
        ),
        PlatformFlowEdge(
            PlatformFlowNode.CANONICAL_SNAPSHOT, PlatformFlowNode.FEATURE_SNAPSHOT
        ),
        PlatformFlowEdge(
            PlatformFlowNode.FEATURE_SNAPSHOT,
            PlatformFlowNode.EXTERNAL_INTELLIGENCE,
        ),
        PlatformFlowEdge(
            PlatformFlowNode.FEATURE_SNAPSHOT,
            PlatformFlowNode.ANALYTIC_CAPABILITIES,
        ),
        PlatformFlowEdge(
            PlatformFlowNode.EXTERNAL_INTELLIGENCE, PlatformFlowNode.EVIDENCE_FABRIC
        ),
        PlatformFlowEdge(
            PlatformFlowNode.ANALYTIC_CAPABILITIES, PlatformFlowNode.AGENT_OBSERVATIONS
        ),
        PlatformFlowEdge(
            PlatformFlowNode.EVIDENCE_FABRIC,
            PlatformFlowNode.EVIDENCE_COMPLETENESS,
        ),
        PlatformFlowEdge(
            PlatformFlowNode.AGENT_OBSERVATIONS,
            PlatformFlowNode.EVIDENCE_COMPLETENESS,
        ),
        PlatformFlowEdge(
            PlatformFlowNode.EVIDENCE_COMPLETENESS, PlatformFlowNode.SETUP_ENGINE
        ),
        PlatformFlowEdge(
            PlatformFlowNode.SETUP_ENGINE, PlatformFlowNode.DETERMINISTIC_CORE
        ),
        PlatformFlowEdge(
            PlatformFlowNode.DETERMINISTIC_CORE, PlatformFlowNode.ACTION_CEILING
        ),
        PlatformFlowEdge(PlatformFlowNode.ACTION_CEILING, PlatformFlowNode.RISK_ENGINE),
        PlatformFlowEdge(
            PlatformFlowNode.RISK_ENGINE, PlatformFlowNode.DECISION_GOVERNANCE
        ),
        PlatformFlowEdge(
            PlatformFlowNode.DECISION_GOVERNANCE, PlatformFlowNode.EXECUTION_GATES
        ),
        PlatformFlowEdge(PlatformFlowNode.EXECUTION_GATES, PlatformFlowNode.NO_TRADE),
        PlatformFlowEdge(
            PlatformFlowNode.EXECUTION_GATES, PlatformFlowNode.PAPER_MANUAL
        ),
        PlatformFlowEdge(
            PlatformFlowNode.PAPER_MANUAL, PlatformFlowNode.EXECUTION_RECORD
        ),
        PlatformFlowEdge(
            PlatformFlowNode.EXECUTION_RECORD, PlatformFlowNode.POSITION_LIFECYCLE
        ),
        PlatformFlowEdge(
            PlatformFlowNode.POSITION_LIFECYCLE, PlatformFlowNode.CLOSURE_REVIEW
        ),
        PlatformFlowEdge(PlatformFlowNode.CLOSURE_REVIEW, PlatformFlowNode.LESSON),
        PlatformFlowEdge(PlatformFlowNode.LESSON, PlatformFlowNode.LEARNING_CANDIDATE),
        PlatformFlowEdge(
            PlatformFlowNode.LEARNING_CANDIDATE, PlatformFlowNode.RESEARCH_UNIT
        ),
        PlatformFlowEdge(PlatformFlowNode.RESEARCH_UNIT, PlatformFlowNode.VALIDATION),
        PlatformFlowEdge(
            PlatformFlowNode.VALIDATION, PlatformFlowNode.GOVERNED_PROMOTION
        ),
    )

    with pytest.raises(ValueError, match="capability platform"):
        GovernedCapabilityPlatformFlow(
            edges=flow.edges,
            model_identity="multi-agent trading system",
        )
    with pytest.raises(ValueError, match="agents must remain actors"):
        GovernedCapabilityPlatformFlow(
            edges=flow.edges,
            agent_role="final decision authority",
        )
    with pytest.raises(ValueError, match="not modeled"):
        GovernedCapabilityPlatformFlow(
            edges=flow.edges,
            multi_agent_trading_system=True,
        )
    with pytest.raises(ValueError, match="agent presence"):
        GovernedCapabilityPlatformFlow(
            edges=flow.edges,
            agent_is_feature_proxy=True,
        )
    with pytest.raises(ValueError, match="platform flow edges"):
        GovernedCapabilityPlatformFlow(edges=flow.edges[:-1])
    with pytest.raises(ValueError, match="critical architecture"):
        GovernedCapabilityPlatformFlow(
            edges=flow.edges,
            critical_improvements=tuple(CriticalArchitectureImprovement)[:-1],
        )


def test_raw_market_data_records_are_immutable_and_utc_aware() -> None:
    raw = RawMarketDataRecord(
        record_id="raw-ohlcv-1",
        kind=MarketDataKind.OHLCV,
        source_id="binance-spot-rest",
        observed_at=NOW,
        payload_hash=HASH,
    )

    assert raw.immutable is True
    assert raw.observed_at.tzinfo is UTC

    with pytest.raises(ValueError, match="immutable"):
        RawMarketDataRecord(
            record_id="raw-ohlcv-2",
            kind=MarketDataKind.OHLCV,
            source_id="binance-spot-rest",
            observed_at=NOW,
            payload_hash=HASH,
            immutable=False,
        )

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        RawMarketDataRecord(
            record_id="raw-ohlcv-3",
            kind=MarketDataKind.OHLCV,
            source_id="binance-spot-rest",
            observed_at=datetime(2026, 8, 13, 17, 0),
            payload_hash=HASH,
        )


def test_normalization_cannot_overwrite_raw_market_records() -> None:
    normalized = NormalizedMarketDataRecord(
        normalized_record_id="norm-ohlcv-1",
        raw_record_id="raw-ohlcv-1",
        kind=MarketDataKind.OHLCV,
        normalizer_version="normalizer-v1",
        created_at=NOW,
        payload_hash=HASH,
    )

    assert normalized.overwrite_raw is False

    with pytest.raises(ValueError, match="separate record"):
        NormalizedMarketDataRecord(
            normalized_record_id="raw-ohlcv-1",
            raw_record_id="raw-ohlcv-1",
            kind=MarketDataKind.OHLCV,
            normalizer_version="normalizer-v1",
            created_at=NOW,
            payload_hash=HASH,
        )

    with pytest.raises(ValueError, match="must not overwrite"):
        NormalizedMarketDataRecord(
            normalized_record_id="norm-ohlcv-2",
            raw_record_id="raw-ohlcv-2",
            kind=MarketDataKind.OHLCV,
            normalizer_version="normalizer-v1",
            created_at=NOW,
            payload_hash=HASH,
            overwrite_raw=True,
        )


def test_decision_cycle_context_requires_one_shared_snapshot_for_all_agents() -> None:
    context = DecisionCycleContext(
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        created_at=NOW,
        symbol="HOTUSDT",
        timeframes=("5m", "15m", "1h", "4h", "1d"),
        market_snapshot="market-snapshot-1",
        feature_snapshot="feature-snapshot-1",
        evidence_context="evidence-context-1",
        risk_state="risk-state-1",
        workflow_state="workflow-state-1",
        data_quality_state="data-quality-state-1",
        decision_state="decision-state-1",
        agent_observations=(
            CycleAgentObservationRef(
                agent_id="StructureAgent",
                observation_id="obs-1",
                snapshot_id="snapshot-1",
            ),
        ),
    )

    assert context.snapshot_id == "snapshot-1"
    assert context.agent_observations[0].snapshot_id == context.snapshot_id

    with pytest.raises(ValueError, match="same snapshot_id"):
        DecisionCycleContext(
            cycle_id="cycle-2",
            snapshot_id="snapshot-1",
            created_at=NOW,
            symbol="HOTUSDT",
            timeframes=("5m", "15m", "1h", "4h", "1d"),
            market_snapshot="market-snapshot-1",
            feature_snapshot="feature-snapshot-1",
            evidence_context="evidence-context-1",
            risk_state="risk-state-1",
            workflow_state="workflow-state-1",
            data_quality_state="data-quality-state-1",
            decision_state="decision-state-1",
            agent_observations=(
                CycleAgentObservationRef(
                    agent_id="StructureAgent",
                    observation_id="obs-2",
                    snapshot_id="snapshot-2",
                ),
            ),
        )

    with pytest.raises(ValueError, match="timeframes"):
        DecisionCycleContext(
            cycle_id="cycle-3",
            snapshot_id="snapshot-1",
            created_at=NOW,
            symbol="HOTUSDT",
            timeframes=("1h",),
            market_snapshot="market-snapshot-1",
            feature_snapshot="feature-snapshot-1",
            evidence_context="evidence-context-1",
            risk_state="risk-state-1",
            workflow_state="workflow-state-1",
            data_quality_state="data-quality-state-1",
            decision_state="decision-state-1",
        )


def test_decision_core_pipeline_order_is_immutable() -> None:
    pipeline = build_decision_core_pipeline()

    assert pipeline is not AI4BINANCE_DECISION_CORE_PIPELINE
    assert pipeline.domain is CanonicalDomainId.DECISION
    assert pipeline.stages == (
        DecisionPipelineStage.DATA_READINESS,
        DecisionPipelineStage.HARD_BLOCKER_CHECK,
        DecisionPipelineStage.EVIDENCE_COMPLETENESS,
        DecisionPipelineStage.CAPABILITY_ELIGIBILITY,
        DecisionPipelineStage.SETUP_QUALIFICATION,
        DecisionPipelineStage.DETERMINISTIC_100_POINT_SCORE,
        DecisionPipelineStage.ACTION_CEILING,
        DecisionPipelineStage.RISK_ASSESSMENT,
        DecisionPipelineStage.GOVERNANCE_ELIGIBILITY,
        DecisionPipelineStage.TRADE_PLAN,
        DecisionPipelineStage.EXECUTION_GATE,
    )

    with pytest.raises(ValueError, match="07_DECISION"):
        DecisionCorePipeline(domain=CanonicalDomainId.RISK)

    with pytest.raises(ValueError, match="stage order"):
        DecisionCorePipeline(stages=tuple(reversed(tuple(DecisionPipelineStage))))


def test_action_ceiling_is_set_by_governance_maturity_not_score() -> None:
    result = DecisionScoreGovernanceResult(
        deterministic_score=92.0,
        governance_maturity=GovernanceMaturity.PAPER_APPROVED,
        action_ceiling=ActionCeiling.PAPER,
    )

    assert result.action_ceiling is ActionCeiling.PAPER
    assert action_ceiling_for_maturity(GovernanceMaturity.PAPER_APPROVED) is (
        ActionCeiling.PAPER
    )
    assert action_ceiling_for_maturity(GovernanceMaturity.OOS_VALIDATED) is (
        ActionCeiling.RESEARCH
    )
    assert action_ceiling_for_maturity(GovernanceMaturity.LIVE_ELIGIBLE) is (
        ActionCeiling.MANUAL_REVIEW
    )

    with pytest.raises(ValueError, match="score cannot raise"):
        DecisionScoreGovernanceResult(
            deterministic_score=100.0,
            governance_maturity=GovernanceMaturity.PAPER_APPROVED,
            action_ceiling=ActionCeiling.MANUAL_REVIEW,
        )

    with pytest.raises(ValueError, match="between 0 and 100"):
        DecisionScoreGovernanceResult(
            deterministic_score=101.0,
            governance_maturity=GovernanceMaturity.PAPER_APPROVED,
            action_ceiling=ActionCeiling.PAPER,
        )


def test_external_intelligence_evidence_fabric_contract() -> None:
    fabric = build_external_intelligence_evidence_fabric()

    assert fabric is not AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC
    assert fabric.domain is CanonicalDomainId.INTELLIGENCE
    assert fabric.sources == (
        ExternalIntelligenceSource.NEWS,
        ExternalIntelligenceSource.SOCIAL,
        ExternalIntelligenceSource.TELEGRAM,
        ExternalIntelligenceSource.X,
        ExternalIntelligenceSource.GITHUB,
        ExternalIntelligenceSource.ARXIV,
        ExternalIntelligenceSource.SEC,
        ExternalIntelligenceSource.CVE,
        ExternalIntelligenceSource.MEDIUM,
        ExternalIntelligenceSource.SUBSTACK,
        ExternalIntelligenceSource.SECURITY,
        ExternalIntelligenceSource.REGULATORY,
        ExternalIntelligenceSource.PROJECT_OFFICIAL_SOURCES,
        ExternalIntelligenceSource.EXCHANGE_ANNOUNCEMENTS,
        ExternalIntelligenceSource.TOKENOMICS,
        ExternalIntelligenceSource.ON_CHAIN,
        ExternalIntelligenceSource.WHALE,
        ExternalIntelligenceSource.MACRO,
        ExternalIntelligenceSource.RESEARCH,
    )
    assert fabric.pipeline == (
        EvidenceFabricStage.SOURCE,
        EvidenceFabricStage.INGESTION,
        EvidenceFabricStage.NORMALIZATION,
        EvidenceFabricStage.ENTITY_RESOLUTION,
        EvidenceFabricStage.CLAIM_EVENT_EXTRACTION,
        EvidenceFabricStage.SOURCE_VALIDATION,
        EvidenceFabricStage.EVIDENCE_SCORING,
        EvidenceFabricStage.INDEXING,
        EvidenceFabricStage.HYBRID_RETRIEVAL,
        EvidenceFabricStage.EVIDENCE_PACK,
    )
    assert fabric.indexes == (
        EvidenceIndexKind.VECTOR,
        EvidenceIndexKind.LEXICAL,
        EvidenceIndexKind.GRAPH,
        EvidenceIndexKind.TEMPORAL,
    )
    assert IntelligenceRetrievalTechnique.RAG in fabric.retrieval_techniques
    assert IntelligenceRetrievalTechnique.AGENTIC_RAG in fabric.retrieval_techniques
    assert fabric.rag_is_evidence_fabric is False
    assert fabric.produces == "EVIDENCE_PACK"


def test_external_intelligence_evidence_fabric_rejects_rag_as_fabric_shortcut() -> None:
    with pytest.raises(ValueError, match="RAG is a tool"):
        ExternalIntelligenceEvidenceFabric(
            fabric_id="fabric-1",
            version="2.0.0",
            rag_is_evidence_fabric=True,
        )

    with pytest.raises(ValueError, match="retrieval technique"):
        ExternalIntelligenceEvidenceFabric(
            fabric_id="fabric-2",
            version="2.0.0",
            retrieval_techniques=(
                IntelligenceRetrievalTechnique.AGENTIC_RAG,
                IntelligenceRetrievalTechnique.HYBRID_RETRIEVAL,
            ),
        )

    with pytest.raises(ValueError, match="pipeline"):
        ExternalIntelligenceEvidenceFabric(
            fabric_id="fabric-3",
            version="2.0.0",
            pipeline=(EvidenceFabricStage.SOURCE, EvidenceFabricStage.EVIDENCE_PACK),
        )


def test_append_only_evidence_fabric_defines_physical_canonical_objects() -> None:
    fabric = build_append_only_evidence_fabric()

    assert fabric is not AI4BINANCE_APPEND_ONLY_EVIDENCE_FABRIC
    assert fabric.domain is CanonicalDomainId.EVIDENCE
    assert fabric.objects == (
        EvidenceObjectKind.SOURCE,
        EvidenceObjectKind.OBSERVATION,
        EvidenceObjectKind.CLAIM,
        EvidenceObjectKind.EVIDENCE,
        EvidenceObjectKind.CONTRADICTION,
        EvidenceObjectKind.EVIDENCE_PACK,
        EvidenceObjectKind.PROVENANCE,
    )
    assert fabric.append_only is True
    assert fabric.update_policy == "NEW_EVIDENCE_EVENT"

    with pytest.raises(ValueError, match="14_EVIDENCE"):
        AppendOnlyEvidenceFabric(domain=CanonicalDomainId.INTELLIGENCE)
    with pytest.raises(ValueError, match="append-only"):
        AppendOnlyEvidenceFabric(append_only=False)
    with pytest.raises(ValueError, match="new evidence/event"):
        AppendOnlyEvidenceFabric(update_policy="MUTATE_EXISTING_EVIDENCE")


def test_evidence_records_are_immutable_utc_quality_scored_and_packable() -> None:
    source = EvidenceSource(
        source_id="source-1",
        source_type="ExchangeAnnouncements",
        source_reference="https://www.binance.com/en/support/announcement/example",
    )
    observation = EvidenceObservation(
        observation_id="observation-1",
        source_id=source.source_id,
        observed_at=NOW,
        retrieved_at=NOW,
    )
    claim = EvidenceClaim(
        claim_id="claim-1",
        entity_ids=("HOTUSDT",),
        statement="Binance source published a HOTUSDT-related notice.",
    )
    evidence = Evidence(
        evidence_id="evidence-1",
        source_id=source.source_id,
        source_type=source.source_type,
        entity_ids=claim.entity_ids,
        claim_id=claim.claim_id,
        observed_at=observation.observed_at,
        retrieved_at=observation.retrieved_at,
        provenance=EvidenceProvenance(
            source_reference=source.source_reference,
            content_hash=HASH,
            parser_version="parser-v1",
        ),
        quality=EvidenceQuality(
            source_reliability=0.95,
            freshness_score=1.0,
            confirmation_score=0.5,
            manipulation_risk=0.1,
        ),
        status=EvidenceVerificationStatus.VERIFIED,
    )
    contradiction = EvidenceContradiction(
        contradiction_id="contradiction-1",
        evidence_ids=("evidence-1", "evidence-2"),
        reason="Two sources disagree on the extracted event time.",
    )
    pack = EvidencePack(
        evidence_pack_id="pack-1",
        evidence_ids=(evidence.evidence_id,),
        contradiction_ids=(contradiction.contradiction_id,),
    )

    assert evidence.domain is CanonicalDomainId.EVIDENCE
    assert evidence.immutable is True
    assert evidence.status is EvidenceVerificationStatus.VERIFIED
    assert pack.immutable is True

    with pytest.raises(ValueError, match="immutable"):
        Evidence(
            evidence_id="evidence-mutable",
            source_id=source.source_id,
            source_type=source.source_type,
            observed_at=NOW,
            retrieved_at=NOW,
            provenance=EvidenceProvenance(source_reference=source.source_reference),
            quality=EvidenceQuality(source_reliability=0.9, freshness_score=0.9),
            status=EvidenceVerificationStatus.UNVERIFIED,
            immutable=False,
        )
    with pytest.raises(ValueError, match="between zero and one"):
        EvidenceQuality(source_reliability=1.2, freshness_score=0.9)
    with pytest.raises(ValueError, match="at least two evidence_ids"):
        EvidenceContradiction(
            contradiction_id="contradiction-bad",
            evidence_ids=("evidence-1",),
            reason="Single record cannot contradict itself.",
        )
    with pytest.raises(ValueError, match="requires evidence_ids"):
        EvidencePack(evidence_pack_id="pack-empty", evidence_ids=())


def test_evidence_completeness_gate_keeps_missing_domains_unknown() -> None:
    incomplete = EvidenceCompleteness(
        required_domains=("market_data", "risk", "news"),
        received_domains=("market_data", "risk"),
        missing_domains=("news",),
        conflicts=(),
        completeness_score=0.66,
        minimum_met=False,
    )
    complete = EvidenceCompleteness(
        required_domains=("market_data", "risk"),
        received_domains=("market_data", "risk"),
        missing_domains=(),
        conflicts=(),
        completeness_score=1.0,
        minimum_met=True,
    )

    assert incomplete.domain is CanonicalDomainId.EVIDENCE
    assert incomplete.missing_evidence_state == "UNKNOWN"
    assert incomplete.minimum_met is False
    assert complete.minimum_met is True

    with pytest.raises(ValueError, match="explicit"):
        EvidenceCompleteness(
            required_domains=("market_data", "risk", "news"),
            received_domains=("market_data", "risk"),
            missing_domains=(),
            conflicts=(),
            completeness_score=0.66,
        )
    with pytest.raises(ValueError, match="UNKNOWN"):
        EvidenceCompleteness(
            required_domains=("market_data", "risk", "news"),
            received_domains=("market_data", "risk"),
            missing_domains=("news",),
            conflicts=(),
            completeness_score=0.66,
            missing_evidence_state="ASSUMED_PASS",
        )
    with pytest.raises(ValueError, match="gaps/conflicts"):
        EvidenceCompleteness(
            required_domains=("market_data", "risk", "news"),
            received_domains=("market_data", "risk"),
            missing_domains=("news",),
            conflicts=(),
            completeness_score=0.66,
            minimum_met=True,
        )
    with pytest.raises(ValueError, match="gaps/conflicts"):
        EvidenceCompleteness(
            required_domains=("market_data", "risk"),
            received_domains=("market_data", "risk"),
            missing_domains=(),
            conflicts=("conflict-1",),
            completeness_score=1.0,
            minimum_met=True,
        )


def test_audit_observability_catalog_is_not_logs_only() -> None:
    catalog = build_audit_observability_catalog()

    assert catalog is not AI4BINANCE_AUDIT_OBSERVABILITY_CATALOG
    assert catalog.domain is CanonicalDomainId.AUDIT_OBSERVABILITY
    assert catalog.channels == (
        AuditObservabilityChannel.LOGS,
        AuditObservabilityChannel.METRICS,
        AuditObservabilityChannel.TRACES,
        AuditObservabilityChannel.EVENTS,
        AuditObservabilityChannel.DECISION_LOGS,
        AuditObservabilityChannel.MODEL_CALLS,
        AuditObservabilityChannel.AGENT_CALLS,
        AuditObservabilityChannel.TOOL_CALLS,
        AuditObservabilityChannel.GATE_RESULTS,
        AuditObservabilityChannel.ERRORS,
        AuditObservabilityChannel.INCIDENTS,
        AuditObservabilityChannel.VALIDATION_RECORDS,
        AuditObservabilityChannel.PROMOTION_RECORDS,
    )
    assert catalog.minimum_record_fields == (
        AuditRecordField.WHAT,
        AuditRecordField.WHEN,
        AuditRecordField.WHO_COMPONENT,
        AuditRecordField.INPUT,
        AuditRecordField.OUTPUT,
        AuditRecordField.VERSION,
        AuditRecordField.EVIDENCE,
        AuditRecordField.RESULT,
    )
    assert catalog.logs_only is False

    with pytest.raises(ValueError, match="15_AUDIT_OBSERVABILITY"):
        AuditObservabilityCatalog(domain=CanonicalDomainId.EVIDENCE)
    with pytest.raises(ValueError, match="logs-only"):
        AuditObservabilityCatalog(logs_only=True)
    with pytest.raises(ValueError, match="channels"):
        AuditObservabilityCatalog(
            channels=tuple(AuditObservabilityChannel)[:-1],
        )


def test_audit_record_requires_minimum_lineage_fields_and_evidence() -> None:
    record = AuditRecord(
        record_id="audit-1",
        channel=AuditObservabilityChannel.DECISION_LOGS,
        what="Decision gate evaluated evidence completeness.",
        when=NOW,
        who_component="DeterministicCore",
        input_ref="snapshot-1",
        output_ref="decision-1",
        version="2.0.0",
        evidence_ids=("evidence-1",),
        result="NO_TRADE",
    )

    assert record.domain is CanonicalDomainId.AUDIT_OBSERVABILITY
    assert record.channel is AuditObservabilityChannel.DECISION_LOGS
    assert record.evidence_ids == ("evidence-1",)

    with pytest.raises(ValueError, match="EVIDENCE"):
        AuditRecord(
            record_id="audit-no-evidence",
            channel=AuditObservabilityChannel.GATE_RESULTS,
            what="Gate result.",
            when=NOW,
            who_component="GovernanceEngine",
            input_ref="decision-1",
            output_ref="gate-1",
            version="2.0.0",
            evidence_ids=(),
            result="BLOCK",
        )
    with pytest.raises(ValueError, match="WHO/COMPONENT"):
        AuditRecord(
            record_id="audit-no-component",
            channel=AuditObservabilityChannel.ERRORS,
            what="Error observed.",
            when=NOW,
            who_component=" ",
            input_ref="input-1",
            output_ref="error-1",
            version="2.0.0",
            evidence_ids=("evidence-1",),
            result="ERROR",
        )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        AuditRecord(
            record_id="audit-naive-time",
            channel=AuditObservabilityChannel.EVENTS,
            what="Event observed.",
            when=datetime(2026, 8, 14, 9, 0),
            who_component="EventFabric",
            input_ref="event-input-1",
            output_ref="event-output-1",
            version="2.0.0",
            evidence_ids=("evidence-1",),
            result="RECORDED",
        )
    with pytest.raises(ValueError, match="15_AUDIT_OBSERVABILITY"):
        AuditRecord(
            record_id="audit-wrong-domain",
            channel=AuditObservabilityChannel.EVENTS,
            what="Event observed.",
            when=NOW,
            who_component="EventFabric",
            input_ref="event-input-1",
            output_ref="event-output-1",
            version="2.0.0",
            evidence_ids=("evidence-1",),
            result="RECORDED",
            domain=CanonicalDomainId.EVIDENCE,
        )


def test_decision_lineage_chain_is_canonical_and_unbroken() -> None:
    lineage = build_decision_lineage("lineage-1", "cycle-1")

    assert lineage.domain is CanonicalDomainId.AUDIT_OBSERVABILITY
    assert lineage.unbroken is True
    assert tuple(step for step, _ref in lineage.step_refs) == (
        DecisionLineageStep.RAW_DATA,
        DecisionLineageStep.MARKET_SNAPSHOT,
        DecisionLineageStep.FEATURE_SNAPSHOT,
        DecisionLineageStep.OBSERVATION,
        DecisionLineageStep.EVIDENCE,
        DecisionLineageStep.SETUP_CANDIDATE,
        DecisionLineageStep.DECISION,
        DecisionLineageStep.RISK_ASSESSMENT,
        DecisionLineageStep.GOVERNANCE_RESULT,
        DecisionLineageStep.TRADE_PLAN,
        DecisionLineageStep.EXECUTION,
        DecisionLineageStep.POSITION_LIFECYCLE,
        DecisionLineageStep.CLOSURE_REVIEW,
        DecisionLineageStep.LESSON,
    )
    assert lineage.refs_by_step[DecisionLineageStep.RAW_DATA] == "cycle-1:RawData"
    assert lineage.refs_by_step[DecisionLineageStep.LESSON] == "cycle-1:Lesson"

    with pytest.raises(ValueError, match="cannot be cut or reordered"):
        DecisionLineage(
            lineage_id="lineage-cut",
            cycle_id="cycle-1",
            step_refs=tuple(
                (step, f"cycle-1:{step.value}")
                for step in tuple(DecisionLineageStep)[:-1]
            ),
        )
    with pytest.raises(ValueError, match="cannot be cut or reordered"):
        DecisionLineage(
            lineage_id="lineage-reordered",
            cycle_id="cycle-1",
            step_refs=tuple(
                (step, f"cycle-1:{step.value}")
                for step in reversed(tuple(DecisionLineageStep))
            ),
        )
    with pytest.raises(ValueError, match="MarketSnapshot"):
        DecisionLineage(
            lineage_id="lineage-empty-ref",
            cycle_id="cycle-1",
            step_refs=tuple(
                (step, " ")
                if step is DecisionLineageStep.MARKET_SNAPSHOT
                else (step, f"cycle-1:{step.value}")
                for step in DecisionLineageStep
            ),
        )
    with pytest.raises(ValueError, match="marked broken"):
        DecisionLineage(
            lineage_id="lineage-broken",
            cycle_id="cycle-1",
            step_refs=tuple(
                (step, f"cycle-1:{step.value}") for step in DecisionLineageStep
            ),
            unbroken=False,
        )


def test_security_contract_keeps_api_keys_env_only_and_secret_safe() -> None:
    security = build_security_domain_contract()

    assert security is not AI4BINANCE_SECURITY_CONTRACT
    assert security.domain is CanonicalDomainId.SECURITY
    assert security.controls == (
        SecurityControlDomain.IDENTITY,
        SecurityControlDomain.RBAC,
        SecurityControlDomain.SECRETS,
        SecurityControlDomain.API_PERMISSIONS,
        SecurityControlDomain.DATA_CLASSIFICATION,
        SecurityControlDomain.INTEGRITY,
        SecurityControlDomain.DEPENDENCY_SECURITY,
        SecurityControlDomain.SUPPLY_CHAIN_SECURITY,
        SecurityControlDomain.INCIDENT_MANAGEMENT,
        SecurityControlDomain.SECURITY_AUDIT,
    )
    assert security.api_key_policy.allowed_locations == (
        ApiKeyStorageLocation.ENV_FILE,
    )
    assert security.api_key_policy.prohibited_sinks == (
        SecretProhibitedSink.SOURCE_CODE,
        SecretProhibitedSink.LOGS,
        SecretProhibitedSink.REPORTS,
        SecretProhibitedSink.PROMPTS,
        SecretProhibitedSink.AUDIT_ARTIFACTS,
    )
    assert security.fail_policy == "DENY"
    assert security.execution_allowed is False
    assert security.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match=r"\.env only"):
        ApiKeySecretPolicy(allowed_locations=())
    with pytest.raises(ValueError, match="prohibited sinks"):
        ApiKeySecretPolicy(
            prohibited_sinks=tuple(SecretProhibitedSink)[:-1],
        )
    with pytest.raises(ValueError, match=r"outside \.env"):
        ApiKeySecretPolicy(raw_secret_storage_allowed=True)
    with pytest.raises(ValueError, match="redaction"):
        ApiKeySecretPolicy(redaction_required=False)
    with pytest.raises(ValueError, match="16_SECURITY"):
        SecurityDomainContract(domain=CanonicalDomainId.GOVERNANCE)
    with pytest.raises(ValueError, match="controls"):
        SecurityDomainContract(controls=tuple(SecurityControlDomain)[:-1])
    with pytest.raises(ValueError, match="must DENY"):
        SecurityDomainContract(fail_policy="ALLOW")
    with pytest.raises(ValueError, match="cannot authorize execution"):
        SecurityDomainContract(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot unblock live execution"):
        SecurityDomainContract(live_eligibility_status="READY")


def test_event_fabric_contract_uses_canonical_event_envelope_and_types() -> None:
    fabric = build_event_fabric_contract()

    assert fabric is not AI4BINANCE_EVENT_FABRIC_CONTRACT
    assert fabric.domain is CanonicalDomainId.EVENT_FABRIC
    assert fabric.envelope_schema == "EventEnvelope"
    assert fabric.event_types == (
        CanonicalEventType.MARKET_DATA_READY,
        CanonicalEventType.MARKET_SNAPSHOT_READY,
        CanonicalEventType.FEATURE_SET_READY,
        CanonicalEventType.AGENT_ANALYSIS_REQUESTED,
        CanonicalEventType.AGENT_OBSERVATIONS_READY,
        CanonicalEventType.EVIDENCE_PACK_READY,
        CanonicalEventType.DECISION_REQUESTED,
        CanonicalEventType.DECISION_COMPLETED,
        CanonicalEventType.RISK_ASSESSMENT_COMPLETED,
        CanonicalEventType.TRADE_PLAN_CREATED,
        CanonicalEventType.EXECUTION_GATE_EVALUATED,
        CanonicalEventType.PAPER_ORDER_ACCEPTED,
        CanonicalEventType.PAPER_ORDER_FILLED,
        CanonicalEventType.ORDER_REJECTED,
        CanonicalEventType.POSITION_OPENED,
        CanonicalEventType.POSITION_UPDATED,
        CanonicalEventType.POSITION_CLOSED,
        CanonicalEventType.TRAILING_STOP_UPDATED,
        CanonicalEventType.TRAILING_STOP_EXIT,
        CanonicalEventType.TRADE_REVIEW_COMPLETED,
        CanonicalEventType.INCIDENT_CREATED,
        CanonicalEventType.LEARNING_CANDIDATE_CREATED,
        CanonicalEventType.VALIDATION_COMPLETED,
        CanonicalEventType.PROMOTION_REQUESTED,
        CanonicalEventType.PROMOTION_APPROVED,
        CanonicalEventType.PROMOTION_REJECTED,
    )

    with pytest.raises(ValueError, match="17_EVENT_FABRIC"):
        EventFabricContract(domain=CanonicalDomainId.GOVERNANCE)
    with pytest.raises(ValueError, match="canonical"):
        EventFabricContract(event_types=tuple(CanonicalEventType)[:-1])
    with pytest.raises(ValueError, match="EventEnvelope"):
        EventFabricContract(envelope_schema="AdHocEvent")


def test_event_envelope_requires_common_lineage_and_utc_payload_reference() -> None:
    event = EventEnvelope(
        event_id="event-1",
        event_type=CanonicalEventType.DECISION_COMPLETED,
        schema_version="2.0.0",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        decision_id="decision-1",
        producer="DeterministicCore",
        occurred_at=NOW,
        recorded_at=NOW,
        payload_ref="audit:decision-1",
        correlation_id="corr-1",
        causation_id="event-0",
    )

    assert event.domain is CanonicalDomainId.EVENT_FABRIC
    assert event.event_type is CanonicalEventType.DECISION_COMPLETED
    assert event.payload_ref == "audit:decision-1"
    assert event.trade_id is None

    with pytest.raises(ValueError, match="producer"):
        EventEnvelope(
            event_id="event-no-producer",
            event_type=CanonicalEventType.MARKET_DATA_READY,
            schema_version="2.0.0",
            producer=" ",
            occurred_at=NOW,
            recorded_at=NOW,
            payload_ref="payload-1",
            correlation_id="corr-1",
        )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        EventEnvelope(
            event_id="event-naive-time",
            event_type=CanonicalEventType.MARKET_DATA_READY,
            schema_version="2.0.0",
            producer="MarketDataService",
            occurred_at=datetime(2026, 8, 14, 9, 0),
            recorded_at=NOW,
            payload_ref="payload-1",
            correlation_id="corr-1",
        )
    with pytest.raises(ValueError, match="cannot precede"):
        EventEnvelope(
            event_id="event-time-order",
            event_type=CanonicalEventType.MARKET_DATA_READY,
            schema_version="2.0.0",
            producer="MarketDataService",
            occurred_at=datetime(2026, 8, 14, 9, 1, tzinfo=UTC),
            recorded_at=NOW,
            payload_ref="payload-1",
            correlation_id="corr-1",
        )
    with pytest.raises(ValueError, match="payload_ref"):
        EventEnvelope(
            event_id="event-no-payload",
            event_type=CanonicalEventType.MARKET_DATA_READY,
            schema_version="2.0.0",
            producer="MarketDataService",
            occurred_at=NOW,
            recorded_at=NOW,
            payload_ref=" ",
            correlation_id="corr-1",
        )
    with pytest.raises(ValueError, match="correlation_id"):
        EventEnvelope(
            event_id="event-no-correlation",
            event_type=CanonicalEventType.MARKET_DATA_READY,
            schema_version="2.0.0",
            producer="MarketDataService",
            occurred_at=NOW,
            recorded_at=NOW,
            payload_ref="payload-1",
            correlation_id=" ",
        )
    with pytest.raises(ValueError, match="17_EVENT_FABRIC"):
        EventEnvelope(
            event_id="event-wrong-domain",
            event_type=CanonicalEventType.MARKET_DATA_READY,
            schema_version="2.0.0",
            producer="MarketDataService",
            occurred_at=NOW,
            recorded_at=NOW,
            payload_ref="payload-1",
            correlation_id="corr-1",
            domain=CanonicalDomainId.AUDIT_OBSERVABILITY,
        )


def test_research_capability_contract_preserves_research_to_registry_flow() -> None:
    contract = build_research_capability_domain_contract()

    assert contract is not AI4BINANCE_RESEARCH_CAPABILITY_CONTRACT
    assert contract.domain is CanonicalDomainId.RESEARCH_CAPABILITY
    assert contract.flow == (
        ResearchCapabilityStep.RADAR_FINDING,
        ResearchCapabilityStep.RESEARCH_UNIT,
        ResearchCapabilityStep.CAPABILITY_CANDIDATE,
        ResearchCapabilityStep.POC,
        ResearchCapabilityStep.VALIDATION,
        ResearchCapabilityStep.PROMOTION_GOVERNANCE,
        ResearchCapabilityStep.REGISTRY,
    )
    assert contract.score_target == "ResearchUnit"
    assert contract.evaluation_pipeline.stages == (
        ResearchEvaluationStage.HARD_GATES,
        ResearchEvaluationStage.EVIDENCE_COMPLETENESS,
        ResearchEvaluationStage.RESEARCH_100_POINT_SCORE,
        ResearchEvaluationStage.ACTION_CEILING,
    )
    assert contract.evaluation_pipeline.weights_embedded is False
    assert contract.github_stars_secondary_only is True
    assert contract.production_promotion_allowed is False

    with pytest.raises(ValueError, match="18_RESEARCH_CAPABILITY"):
        ResearchCapabilityDomainContract(domain=CanonicalDomainId.GOVERNANCE)
    with pytest.raises(ValueError, match="flow"):
        ResearchCapabilityDomainContract(flow=tuple(ResearchCapabilityStep)[:-1])
    with pytest.raises(ValueError, match="evaluation order"):
        ResearchCapabilityDomainContract(
            evaluation_pipeline=ResearchEvaluationPipeline(
                stages=tuple(reversed(tuple(ResearchEvaluationStage))),
            ),
        )
    with pytest.raises(ValueError, match="ResearchUnit"):
        ResearchCapabilityDomainContract(score_target="Repository")
    with pytest.raises(ValueError, match="GitHub stars"):
        ResearchCapabilityDomainContract(github_stars_secondary_only=False)
    with pytest.raises(ValueError, match="auto-promote"):
        ResearchCapabilityDomainContract(production_promotion_allowed=True)


def test_research_evaluation_pipeline_uses_versioned_scorecard_contract() -> None:
    pipeline = ResearchEvaluationPipeline()
    evaluation = ResearchEvaluationResult(
        research_unit_id="ru-1",
        research_scorecard_id="research-scorecard:structure-shift:v1",
        hard_gates_passed=True,
        evidence_completeness=EvidenceCompleteness(
            required_domains=("license", "integrity", "evidence"),
            received_domains=("license", "integrity", "evidence"),
            missing_domains=(),
            conflicts=(),
            completeness_score=1.0,
            minimum_met=True,
        ),
        research_score=72.5,
        action_ceiling=ActionCeiling.RESEARCH,
        result=ResearchUnitResult.POC_CANDIDATE,
    )

    assert pipeline.stages == (
        ResearchEvaluationStage.HARD_GATES,
        ResearchEvaluationStage.EVIDENCE_COMPLETENESS,
        ResearchEvaluationStage.RESEARCH_100_POINT_SCORE,
        ResearchEvaluationStage.ACTION_CEILING,
    )
    assert pipeline.weights_embedded is False
    assert evaluation.research_scorecard_id == "research-scorecard:structure-shift:v1"
    assert evaluation.action_ceiling is ActionCeiling.RESEARCH

    with pytest.raises(ValueError, match="must not be invented"):
        ResearchEvaluationPipeline(weights_embedded=True)
    with pytest.raises(ValueError, match="research_scorecard_id"):
        ResearchEvaluationResult(
            research_unit_id="ru-1",
            research_scorecard_id=" ",
            hard_gates_passed=True,
            evidence_completeness=evaluation.evidence_completeness,
            research_score=72.5,
            action_ceiling=ActionCeiling.RESEARCH,
            result=ResearchUnitResult.POC_CANDIDATE,
        )
    with pytest.raises(ValueError, match="cannot advance"):
        ResearchEvaluationResult(
            research_unit_id="ru-1",
            research_scorecard_id="research-scorecard:structure-shift:v1",
            hard_gates_passed=False,
            evidence_completeness=evaluation.evidence_completeness,
            research_score=90.0,
            action_ceiling=ActionCeiling.RESEARCH,
            result=ResearchUnitResult.POC_CANDIDATE,
        )
    with pytest.raises(ValueError, match="incomplete research evidence"):
        ResearchEvaluationResult(
            research_unit_id="ru-1",
            research_scorecard_id="research-scorecard:structure-shift:v1",
            hard_gates_passed=True,
            evidence_completeness=EvidenceCompleteness(
                required_domains=("license", "integrity", "evidence"),
                received_domains=("license", "integrity"),
                missing_domains=("evidence",),
                conflicts=(),
                completeness_score=0.66,
                minimum_met=False,
            ),
            research_score=90.0,
            action_ceiling=ActionCeiling.RESEARCH,
            result=ResearchUnitResult.POC_CANDIDATE,
        )
    with pytest.raises(ValueError, match="cannot raise action ceiling"):
        ResearchEvaluationResult(
            research_unit_id="ru-1",
            research_scorecard_id="research-scorecard:structure-shift:v1",
            hard_gates_passed=True,
            evidence_completeness=evaluation.evidence_completeness,
            research_score=100.0,
            action_ceiling=ActionCeiling.PAPER,
            result=ResearchUnitResult.POC_CANDIDATE,
        )
    with pytest.raises(ValueError, match="between zero and one"):
        ResearchEvaluationResult(
            research_unit_id="ru-1",
            research_scorecard_id="research-scorecard:structure-shift:v1",
            hard_gates_passed=True,
            evidence_completeness=evaluation.evidence_completeness,
            research_score=101.0,
            action_ceiling=ActionCeiling.RESEARCH,
            result=ResearchUnitResult.POC_CANDIDATE,
        )


def test_research_unit_enforces_license_integrity_and_promotion_boundaries() -> None:
    research_unit = ResearchUnit(
        research_unit_id="ru-1",
        source=ResearchUnitSource(
            source_id="radar-1",
            repository_ref="https://github.com/example/research-only",
        ),
        capability_candidate_id="capability-candidate-1",
        hypothesis="A structure-shift detector may reduce late entries.",
        expected_value="Improve setup qualification diagnostics after validation.",
        duplicate_capability_check=DuplicateCapabilityCheck(
            DuplicateCapabilityCheckStatus.CLEAR
        ),
        license=ResearchLicense(
            ResearchLicenseStatus.UNKNOWN,
            ResearchReuseMode.NO_CODE_REUSE,
        ),
        integrity=ResearchIntegrity(),
        evidence=("evidence-1",),
        score=ResearchScore(scorecard_id="scorecard-1"),
        result=ResearchUnitResult.POC_CANDIDATE,
    )

    assert research_unit.domain is CanonicalDomainId.RESEARCH_CAPABILITY
    assert research_unit.license.reuse_mode is ResearchReuseMode.NO_CODE_REUSE
    assert (
        research_unit.score.effective_research_scorecard_id
        == research_unit.score.scorecard_id
    )
    assert research_unit.score.score_target == "ResearchUnit"
    assert research_unit.production_promotion is False

    with pytest.raises(ValueError, match="NO_CODE_REUSE"):
        ResearchLicense(
            ResearchLicenseStatus.UNKNOWN,
            ResearchReuseMode.ADOPT_IDEA,
        )
    with pytest.raises(ValueError, match="COPY_CODE"):
        ResearchUnit(
            research_unit_id="ru-copy",
            source=ResearchUnitSource(source_id="radar-1"),
            capability_candidate_id="capability-candidate-1",
            hypothesis="Adopt the algorithmic idea only.",
            expected_value="Research review.",
            duplicate_capability_check=DuplicateCapabilityCheck(
                DuplicateCapabilityCheckStatus.CLEAR
            ),
            license=ResearchLicense(
                ResearchLicenseStatus.KNOWN,
                ResearchReuseMode.ADOPT_IDEA,
            ),
            integrity=ResearchIntegrity(),
            score=ResearchScore(scorecard_id="scorecard-1"),
            result=ResearchUnitResult.RESEARCH_ONLY,
            copied_code=True,
        )
    with pytest.raises(ValueError, match="auto-promote"):
        ResearchUnit(
            research_unit_id="ru-promotion",
            source=ResearchUnitSource(source_id="radar-1"),
            capability_candidate_id="capability-candidate-1",
            hypothesis="POC may work.",
            expected_value="Candidate for validation.",
            duplicate_capability_check=DuplicateCapabilityCheck(
                DuplicateCapabilityCheckStatus.CLEAR
            ),
            license=ResearchLicense(
                ResearchLicenseStatus.KNOWN,
                ResearchReuseMode.REVIEW_ONLY,
            ),
            integrity=ResearchIntegrity(),
            score=ResearchScore(scorecard_id="scorecard-1"),
            result=ResearchUnitResult.POC_CANDIDATE,
            production_promotion=True,
        )
    with pytest.raises(ValueError, match="NOT_TRADING_ELIGIBLE"):
        ResearchUnit(
            research_unit_id="ru-lookahead",
            source=ResearchUnitSource(source_id="radar-1"),
            capability_candidate_id="capability-candidate-1",
            hypothesis="Detector uses future bars.",
            expected_value="Negative evidence for trading use.",
            duplicate_capability_check=DuplicateCapabilityCheck(
                DuplicateCapabilityCheckStatus.CLEAR
            ),
            license=ResearchLicense(
                ResearchLicenseStatus.KNOWN,
                ResearchReuseMode.REVIEW_ONLY,
            ),
            integrity=ResearchIntegrity(lookahead_detected=True),
            evidence=("negative-evidence-1",),
            score=ResearchScore(scorecard_id="scorecard-1"),
            result=ResearchUnitResult.REJECTED,
        )
    blocked = ResearchUnit(
        research_unit_id="ru-repaint",
        source=ResearchUnitSource(source_id="radar-1"),
        capability_candidate_id="capability-candidate-1",
        hypothesis="Detector repaints after candle close.",
        expected_value="Store as negative evidence only.",
        duplicate_capability_check=DuplicateCapabilityCheck(
            DuplicateCapabilityCheckStatus.CLEAR
        ),
        license=ResearchLicense(
            ResearchLicenseStatus.KNOWN,
            ResearchReuseMode.REVIEW_ONLY,
        ),
        integrity=ResearchIntegrity(repainting_detected=True),
        evidence=("negative-evidence-1",),
        score=ResearchScore(scorecard_id="scorecard-1"),
        result=ResearchUnitResult.REJECTED,
        not_trading_eligible_reason="NOT_TRADING_ELIGIBLE",
    )
    assert blocked.integrity.trading_eligible is False


def test_canonical_entity_ontology_defines_families_and_core_entities() -> None:
    ontology = build_canonical_entity_ontology()

    assert ontology is not AI4BINANCE_CANONICAL_ENTITY_ONTOLOGY
    assert ontology.domain is CanonicalDomainId.DETERMINISTIC_ANALYTICS
    assert ontology.families == (
        EntityFamily.IDENTITY,
        EntityFamily.MARKET,
        EntityFamily.DATA,
        EntityFamily.ANALYTICS,
        EntityFamily.INTELLIGENCE,
        EntityFamily.EVIDENCE,
        EntityFamily.DECISION,
        EntityFamily.RISK,
        EntityFamily.PORTFOLIO,
        EntityFamily.EXECUTION,
        EntityFamily.VALIDATION,
        EntityFamily.RESEARCH,
        EntityFamily.LEARNING,
        EntityFamily.GOVERNANCE,
        EntityFamily.SECURITY,
        EntityFamily.OPERATIONS,
        EntityFamily.AUDIT,
    )
    assert ontology.entities == (
        CoreEntity.ACTOR,
        CoreEntity.HUMAN,
        CoreEntity.AGENT,
        CoreEntity.SERVICE,
        CoreEntity.EXCHANGE,
        CoreEntity.ASSET,
        CoreEntity.SYMBOL,
        CoreEntity.MARKET,
        CoreEntity.TIMEFRAME,
        CoreEntity.DATA_SOURCE,
        CoreEntity.DATASET,
        CoreEntity.MARKET_DATA,
        CoreEntity.MARKET_SNAPSHOT,
        CoreEntity.FEATURE_SNAPSHOT,
        CoreEntity.CONTEXT_SNAPSHOT,
        CoreEntity.FORMULA_DEFINITION,
        CoreEntity.ORACLE_DEFINITION,
        CoreEntity.FEATURE,
        CoreEntity.INDICATOR,
        CoreEntity.CAPABILITY,
        CoreEntity.OBSERVATION,
        CoreEntity.AGENT_OBSERVATION,
        CoreEntity.SOURCE,
        CoreEntity.CLAIM,
        CoreEntity.EVIDENCE,
        CoreEntity.EVIDENCE_PACK,
        CoreEntity.EXTERNAL_EVENT,
        CoreEntity.SIGNAL,
        CoreEntity.SETUP,
        CoreEntity.STRATEGY,
        CoreEntity.REGIME,
        CoreEntity.DECISION_CANDIDATE,
        CoreEntity.TRADE_DECISION,
        CoreEntity.RISK,
        CoreEntity.RISK_ASSESSMENT,
        CoreEntity.RISK_RULE,
        CoreEntity.CONTROL,
        CoreEntity.PORTFOLIO_STATE,
        CoreEntity.WALLET,
        CoreEntity.BALANCE,
        CoreEntity.INVENTORY,
        CoreEntity.POSITION,
        CoreEntity.EXPOSURE,
        CoreEntity.TRADE_PLAN,
        CoreEntity.EXECUTION_GATE_RESULT,
        CoreEntity.ORDER,
        CoreEntity.EXECUTION_RECORD,
        CoreEntity.POSITION_LIFECYCLE,
        CoreEntity.EXIT_EVENT,
        CoreEntity.VALIDATION,
        CoreEntity.VALIDATION_PROFILE,
        CoreEntity.VALIDATION_ARTIFACT,
        CoreEntity.BACKTEST_RUN,
        CoreEntity.WALK_FORWARD_RUN,
        CoreEntity.OOS_RUN,
        CoreEntity.RESEARCH_UNIT,
        CoreEntity.RADAR_FINDING,
        CoreEntity.CAPABILITY_CANDIDATE,
        CoreEntity.LESSON,
        CoreEntity.HYPOTHESIS,
        CoreEntity.LEARNING_CANDIDATE,
        CoreEntity.REQUIREMENT,
        CoreEntity.POLICY,
        CoreEntity.AUTHORITY_POLICY,
        CoreEntity.APPROVAL,
        CoreEntity.EXCEPTION,
        CoreEntity.FINDING,
        CoreEntity.TREATMENT,
        CoreEntity.GOVERNANCE_OBJECT,
        CoreEntity.GOVERNANCE_RELEASE_RECORD,
        CoreEntity.APPROVED_OPERATING_ENVELOPE,
        CoreEntity.INCIDENT,
        CoreEntity.PROBLEM,
        CoreEntity.ESCALATION_EVENT,
        CoreEntity.AUDIT_EVENT,
    )

    with pytest.raises(ValueError, match="05_DETERMINISTIC_ANALYTICS"):
        CanonicalEntityOntology(domain=CanonicalDomainId.GOVERNANCE)
    with pytest.raises(ValueError, match="families"):
        CanonicalEntityOntology(families=tuple(EntityFamily)[:-1])
    with pytest.raises(ValueError, match="entities"):
        CanonicalEntityOntology(entities=tuple(CoreEntity)[:-1])


def test_entity_rule_catalog_enforces_identity_lifecycle_and_separation() -> None:
    catalog = build_entity_rule_catalog()

    assert catalog is not AI4BINANCE_ENTITY_RULE_CATALOG
    assert catalog.domain is CanonicalDomainId.DETERMINISTIC_ANALYTICS
    assert catalog.rules == (
        EntityRuleId.ER_001_IDENTITY,
        EntityRuleId.ER_002_VERSIONING,
        EntityRuleId.ER_003_OWNERSHIP,
        EntityRuleId.ER_004_LIFECYCLE,
        EntityRuleId.ER_005_PROVENANCE,
        EntityRuleId.ER_006_SNAPSHOT_CONSISTENCY,
        EntityRuleId.ER_007_CYCLE_IDENTITY,
        EntityRuleId.ER_008_IMMUTABILITY,
        EntityRuleId.ER_009_EVIDENCE_STATUS,
        EntityRuleId.ER_010_UNKNOWN,
        EntityRuleId.ER_011_CAPABILITY_FIRST_VALIDATION,
        EntityRuleId.ER_012_LICENSE_GOVERNANCE,
        EntityRuleId.ER_013_REPAINTING_LOOKAHEAD,
        EntityRuleId.ER_014_STATE_SEPARATION,
        EntityRuleId.ER_015_RISK_SEPARATION,
    )
    assert catalog.lifecycle == (
        EntityLifecycleStatus.DRAFT,
        EntityLifecycleStatus.RESEARCH,
        EntityLifecycleStatus.POC_CANDIDATE,
        EntityLifecycleStatus.BACKTESTED,
        EntityLifecycleStatus.WF_VALIDATED,
        EntityLifecycleStatus.OOS_VALIDATED,
        EntityLifecycleStatus.PAPER_CANDIDATE,
        EntityLifecycleStatus.PAPER_APPROVED,
        EntityLifecycleStatus.LIVE_CANDIDATE,
        EntityLifecycleStatus.LIVE_APPROVED,
        EntityLifecycleStatus.RESTRICTED,
        EntityLifecycleStatus.QUARANTINED,
        EntityLifecycleStatus.SUSPENDED,
        EntityLifecycleStatus.REJECTED,
        EntityLifecycleStatus.DEPRECATED,
        EntityLifecycleStatus.RETIRED,
        EntityLifecycleStatus.WITHDRAWN,
    )
    assert catalog.versioned_trading_components == (
        VersionedTradingComponent.AGENT,
        VersionedTradingComponent.CAPABILITY,
        VersionedTradingComponent.FORMULA,
        VersionedTradingComponent.ORACLE,
        VersionedTradingComponent.INDICATOR,
        VersionedTradingComponent.MODEL,
        VersionedTradingComponent.PROMPT,
        VersionedTradingComponent.STRATEGY,
        VersionedTradingComponent.PARAMETER_SET,
        VersionedTradingComponent.POLICY,
        VersionedTradingComponent.RISK_RULE,
        VersionedTradingComponent.WORKFLOW,
        VersionedTradingComponent.TOOL_CONTRACT,
    )
    assert catalog.immutable_entities == (
        ImmutableEntityKind.RAW_MARKET_DATA,
        ImmutableEntityKind.EVIDENCE,
        ImmutableEntityKind.DECISION_RECORDS,
        ImmutableEntityKind.EXECUTION_RECORDS,
        ImmutableEntityKind.AUDIT_EVENTS,
        ImmutableEntityKind.VALIDATION_ARTIFACTS,
    )
    assert catalog.evidence_statuses == (
        EvidenceVerificationStatus.VERIFIED,
        EvidenceVerificationStatus.PARTIALLY_VERIFIED,
        EvidenceVerificationStatus.UNVERIFIED,
        EvidenceVerificationStatus.CONFLICTED,
    )
    assert catalog.unknown_representations == (
        UnknownRepresentation.UNKNOWN,
        UnknownRepresentation.NULL,
        UnknownRepresentation.DATA_UNAVAILABLE,
    )
    assert catalog.state_separation == (
        StateSeparationKind.RUNTIME_STATE,
        StateSeparationKind.HISTORICAL_MEMORY,
        StateSeparationKind.KNOWLEDGE,
        StateSeparationKind.EVIDENCE,
        StateSeparationKind.LEARNING,
    )

    identity = PersistentEntityIdentity("entity-1", CoreEntity.EVIDENCE)
    ownership = EntityOwnership(
        technical_owner="technical-owner",
        logical_owner="logical-owner",
        validation_owner="validation-owner",
        risk_owner="risk-owner",
        approval_owner="approval-owner",
        production_component=True,
        validation_owner_required=True,
        risk_owner_required=True,
        approval_owner_required=True,
    )

    assert identity.entity_id == "entity-1"
    assert ownership.production_component is True

    with pytest.raises(ValueError, match="entity_id"):
        PersistentEntityIdentity(" ", CoreEntity.EVIDENCE)
    with pytest.raises(ValueError, match="technical_owner"):
        EntityOwnership(technical_owner=" ", logical_owner="logical-owner")
    with pytest.raises(ValueError, match="validation_owner"):
        EntityOwnership(
            technical_owner="technical-owner",
            logical_owner="logical-owner",
            validation_owner_required=True,
        )
    with pytest.raises(ValueError, match="rules"):
        EntityRuleCatalog(rules=tuple(EntityRuleId)[:-1])
    with pytest.raises(ValueError, match="lifecycle"):
        EntityRuleCatalog(lifecycle=tuple(EntityLifecycleStatus)[:-1])
    with pytest.raises(ValueError, match="versioned trading"):
        EntityRuleCatalog(
            versioned_trading_components=tuple(VersionedTradingComponent)[:-1]
        )
    with pytest.raises(ValueError, match="immutable"):
        EntityRuleCatalog(immutable_entities=tuple(ImmutableEntityKind)[:-1])
    with pytest.raises(ValueError, match="evidence statuses"):
        EntityRuleCatalog(evidence_statuses=tuple(EvidenceVerificationStatus)[:-1])
    with pytest.raises(ValueError, match="unknown"):
        EntityRuleCatalog(unknown_representations=tuple(UnknownRepresentation)[:-1])
    with pytest.raises(ValueError, match="state separation"):
        EntityRuleCatalog(state_separation=tuple(StateSeparationKind)[:-1])


def test_relationship_rule_catalog_defines_lineage_and_forbidden_shortcuts() -> None:
    catalog = build_relationship_rule_catalog()

    assert catalog is not AI4BINANCE_RELATIONSHIP_RULE_CATALOG
    assert catalog.domain is CanonicalDomainId.DETERMINISTIC_ANALYTICS
    assert catalog.canonical_relationships == tuple(RelationshipType)
    assert tuple(rule.rule_id for rule in catalog.rules) == (
        RelationshipRuleId.RR_001_MARKET_LINEAGE,
        RelationshipRuleId.RR_002_FEATURE_LINEAGE,
        RelationshipRuleId.RR_003_ORACLE,
        RelationshipRuleId.RR_004_AGENT_OBSERVATION,
        RelationshipRuleId.RR_005_EVIDENCE,
        RelationshipRuleId.RR_006_SETUP,
        RelationshipRuleId.RR_007_DECISION,
        RelationshipRuleId.RR_008_RISK,
        RelationshipRuleId.RR_009_CONTROL,
        RelationshipRuleId.RR_010_REQUIREMENT,
        RelationshipRuleId.RR_011_EVIDENCE_OF_CONTROL,
        RelationshipRuleId.RR_012_GOVERNANCE,
        RelationshipRuleId.RR_013_EXECUTION,
        RelationshipRuleId.RR_014_NO_SHORTCUT,
        RelationshipRuleId.RR_015_POSITION_LIFECYCLE,
        RelationshipRuleId.RR_016_REVIEW,
        RelationshipRuleId.RR_017_LESSON,
        RelationshipRuleId.RR_018_LEARNING,
        RelationshipRuleId.RR_019_NO_SELF_PROMOTION,
        RelationshipRuleId.RR_020_RESEARCH_PROMOTION,
        RelationshipRuleId.RR_021_VALIDATION,
        RelationshipRuleId.RR_022_DECISION_GOVERNANCE,
    )

    by_rule_id = {rule.rule_id: rule for rule in catalog.rules}

    assert by_rule_id[RelationshipRuleId.RR_001_MARKET_LINEAGE].required == (
        RelationshipTriple("DataSource", RelationshipType.PRODUCES, "MarketData"),
        RelationshipTriple(
            "MarketSnapshot", RelationshipType.DERIVED_FROM, "MarketData"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_002_FEATURE_LINEAGE].required == (
        RelationshipTriple("Feature", RelationshipType.DERIVED_FROM, "MarketSnapshot"),
        RelationshipTriple(
            "Feature", RelationshipType.IMPLEMENTED_BY, "FormulaDefinition"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_003_ORACLE].required == (
        RelationshipTriple(
            "Capability", RelationshipType.VERIFIED_BY, "OracleDefinition"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_004_AGENT_OBSERVATION].required == (
        RelationshipTriple("Agent", RelationshipType.PRODUCES, "AgentObservation"),
    )
    assert by_rule_id[RelationshipRuleId.RR_004_AGENT_OBSERVATION].prohibited == (
        RelationshipTriple("Agent", RelationshipType.PRODUCES, "TradeDecision"),
    )
    assert by_rule_id[RelationshipRuleId.RR_005_EVIDENCE].required == (
        RelationshipTriple(
            "AgentObservation", RelationshipType.SUPPORTED_BY, "Evidence"
        ),
        RelationshipTriple(
            "AgentObservation", RelationshipType.CONTRADICTED_BY, "Evidence"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_007_DECISION].required == (
        RelationshipTriple("Setup", RelationshipType.EVALUATED_BY, "DeterministicCore"),
        RelationshipTriple(
            "DeterministicCore", RelationshipType.PRODUCES, "DecisionCandidate"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_008_RISK].required == (
        RelationshipTriple(
            "DecisionCandidate", RelationshipType.CONSTRAINED_BY, "RiskAssessment"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_021_VALIDATION].required == (
        RelationshipTriple(
            "DecisionCandidate", RelationshipType.VALIDATED_BY, "Validation"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_022_DECISION_GOVERNANCE].required == (
        RelationshipTriple(
            "DecisionGovernance", RelationshipType.PRODUCES, "TradeDecision"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_011_EVIDENCE_OF_CONTROL].required == (
        RelationshipTriple("Control", RelationshipType.VERIFIED_BY, "Evidence"),
        RelationshipTriple("Evidence", RelationshipType.VERIFIED_BY, "Test"),
        RelationshipTriple("Test", RelationshipType.PRODUCES, "Finding"),
        RelationshipTriple("Finding", RelationshipType.RESULTS_IN, "Remediation"),
    )
    assert by_rule_id[RelationshipRuleId.RR_014_NO_SHORTCUT].prohibited == (
        RelationshipTriple("Agent", RelationshipType.EXECUTES, "Order"),
    )
    assert by_rule_id[RelationshipRuleId.RR_019_NO_SELF_PROMOTION].prohibited == (
        RelationshipTriple(
            "LearningCandidate", RelationshipType.PROMOTES, "ProductionComponent"
        ),
    )
    assert by_rule_id[RelationshipRuleId.RR_020_RESEARCH_PROMOTION].required == (
        RelationshipTriple("RadarFinding", RelationshipType.RESULTS_IN, "ResearchUnit"),
        RelationshipTriple(
            "ResearchUnit", RelationshipType.RESULTS_IN, "CapabilityCandidate"
        ),
        RelationshipTriple(
            "CapabilityCandidate", RelationshipType.VALIDATED_BY, "Validation"
        ),
        RelationshipTriple(
            "CapabilityCandidate", RelationshipType.SUBJECT_TO, "PromotionGovernance"
        ),
        RelationshipTriple(
            "PromotionGovernance", RelationshipType.PROMOTED_TO, "RegistryComponent"
        ),
    )

    with pytest.raises(ValueError, match="relationship source"):
        RelationshipTriple(" ", RelationshipType.PRODUCES, "MarketData")
    with pytest.raises(ValueError, match="relationship target"):
        RelationshipTriple("DataSource", RelationshipType.PRODUCES, " ")
    with pytest.raises(ValueError, match="required or prohibited"):
        RelationshipRule(RelationshipRuleId.RR_001_MARKET_LINEAGE)
    with pytest.raises(ValueError, match="canonical relationships"):
        RelationshipRuleCatalog(
            canonical_relationships=tuple(RelationshipType)[:-1],
            rules=catalog.rules,
        )
    with pytest.raises(ValueError, match="complete and ordered"):
        RelationshipRuleCatalog(rules=catalog.rules[:-1])
    with pytest.raises(ValueError, match="05_DETERMINISTIC_ANALYTICS"):
        RelationshipRuleCatalog(
            domain=CanonicalDomainId.GOVERNANCE,
            rules=catalog.rules,
        )


def test_external_standards_mapping_uses_shared_ontology_and_legal_metadata() -> None:
    contract = build_external_standards_mapping_contract()

    assert contract is not AI4BINANCE_EXTERNAL_STANDARDS_MAPPING
    assert contract.domain is CanonicalDomainId.GOVERNANCE
    assert contract.frameworks == (
        ExternalFrameworkId.ISO_42001,
        ExternalFrameworkId.ISO_23894,
        ExternalFrameworkId.ISO_27001,
        ExternalFrameworkId.ISO_31000,
        ExternalFrameworkId.NIST_AI_RMF,
        ExternalFrameworkId.COSO,
        ExternalFrameworkId.COBIT,
    )
    assert contract.ontology_chain == (
        "ExternalFramework",
        "Requirement",
        "Risk",
        "Control",
        "Implementation",
        "Evidence",
        "Test",
        "Finding",
        "Remediation",
    )
    assert contract.relationship_chain == (
        RelationshipTriple(
            "ExternalFramework", RelationshipType.CONTAINS, "Requirement"
        ),
        RelationshipTriple("Requirement", RelationshipType.SUBJECT_TO, "Risk"),
        RelationshipTriple("Risk", RelationshipType.MITIGATED_BY, "Control"),
        RelationshipTriple(
            "Control", RelationshipType.IMPLEMENTED_BY, "Implementation"
        ),
        RelationshipTriple("Implementation", RelationshipType.PRODUCES, "Evidence"),
        RelationshipTriple("Evidence", RelationshipType.VERIFIED_BY, "Test"),
        RelationshipTriple("Test", RelationshipType.PRODUCES, "Finding"),
        RelationshipTriple("Finding", RelationshipType.RESULTS_IN, "Remediation"),
    )
    assert contract.shared_control_reuse_allowed is True
    assert contract.separate_compliance_subsystems_allowed is False
    assert contract.legal_source_metadata_required is True

    legal_source = LegalSourceMetadata(
        jurisdiction="EU",
        status=LegalSourceStatus.ACTIVE,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        last_verified_at=NOW,
        source_reference="https://example.invalid/legal/source",
    )

    assert legal_source.jurisdiction == "EU"
    assert legal_source.status is LegalSourceStatus.ACTIVE
    assert legal_source.last_verified_at.tzinfo is not None

    with pytest.raises(ValueError, match="13_GOVERNANCE"):
        ExternalStandardsMappingContract(domain=CanonicalDomainId.DECISION)
    with pytest.raises(ValueError, match="external frameworks"):
        ExternalStandardsMappingContract(frameworks=tuple(ExternalFrameworkId)[:-1])
    with pytest.raises(ValueError, match="ontology chain"):
        ExternalStandardsMappingContract(ontology_chain=("ExternalFramework",))
    with pytest.raises(ValueError, match="relationship chain"):
        ExternalStandardsMappingContract(
            relationship_chain=contract.relationship_chain[:-1]
        )
    with pytest.raises(ValueError, match="shared control reuse"):
        ExternalStandardsMappingContract(shared_control_reuse_allowed=False)
    with pytest.raises(ValueError, match="separate compliance subsystems"):
        ExternalStandardsMappingContract(separate_compliance_subsystems_allowed=True)
    with pytest.raises(ValueError, match="legal source metadata"):
        ExternalStandardsMappingContract(legal_source_metadata_required=False)
    with pytest.raises(ValueError, match="jurisdiction"):
        LegalSourceMetadata(
            jurisdiction=" ",
            status=LegalSourceStatus.ACTIVE,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            last_verified_at=NOW,
            source_reference="https://example.invalid/legal/source",
        )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        LegalSourceMetadata(
            jurisdiction="EU",
            status=LegalSourceStatus.ACTIVE,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            last_verified_at=datetime(2026, 1, 2),
            source_reference="https://example.invalid/legal/source",
        )
    with pytest.raises(ValueError, match="effective_to"):
        LegalSourceMetadata(
            jurisdiction="EU",
            status=LegalSourceStatus.ACTIVE,
            effective_from=date(2026, 2, 1),
            effective_to=date(2026, 1, 1),
            last_verified_at=NOW,
            source_reference="https://example.invalid/legal/source",
        )
    with pytest.raises(ValueError, match="source_reference"):
        LegalSourceMetadata(
            jurisdiction="EU",
            status=LegalSourceStatus.ACTIVE,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            last_verified_at=NOW,
            source_reference=" ",
        )


def test_deterministic_analytics_catalog_defines_feature_and_technical_families() -> (
    None
):
    catalog = build_deterministic_analytics_catalog()
    families = {item.family_id: item for item in catalog.technical_families}

    assert catalog is not AI4BINANCE_DETERMINISTIC_ANALYTICS_CATALOG
    assert catalog.domain is CanonicalDomainId.DETERMINISTIC_ANALYTICS
    assert catalog.feature_families == (
        DeterministicFeatureFamily.TREND,
        DeterministicFeatureFamily.VOLATILITY,
        DeterministicFeatureFamily.MOMENTUM,
        DeterministicFeatureFamily.VOLUME,
        DeterministicFeatureFamily.PRICE_ACTION,
        DeterministicFeatureFamily.STRUCTURE,
        DeterministicFeatureFamily.SUPPORT_RESISTANCE,
        DeterministicFeatureFamily.FIBONACCI,
        DeterministicFeatureFamily.PATTERN,
        DeterministicFeatureFamily.WYCKOFF,
        DeterministicFeatureFamily.SMC,
        DeterministicFeatureFamily.ORDER_FLOW,
        DeterministicFeatureFamily.DERIVATIVES,
        DeterministicFeatureFamily.REGIME,
        DeterministicFeatureFamily.CYCLE,
    )
    assert tuple(families) == tuple(TechnicalFamilyId)

    trend = families[TechnicalFamilyId.TREND]
    assert trend.role is CapabilityRole.PRIMARY
    assert trend.allowed_timeframes == ("1h", "4h", "1d", "15m")
    assert trend.score_contribution is ScoreContributionLevel.HIGH
    assert trend.hard_gate_description == "OOS-eligible"
    assert trend.false_positive_risks == ("chop", "late reversal")

    volatility = families[TechnicalFamilyId.VOLATILITY]
    assert volatility.role is CapabilityRole.PRIMARY_RISK_FILTER
    assert volatility.allowed_timeframes == ("15m", "1h", "4h")
    assert volatility.hard_gate_description == "blocker eligible"

    assert families[TechnicalFamilyId.MOMENTUM].role is CapabilityRole.SECONDARY
    assert (
        families[TechnicalFamilyId.MOMENTUM].hard_gate_description
        == "soft unless independently proven"
    )
    assert families[TechnicalFamilyId.VOLUME].role is CapabilityRole.DIAGNOSTIC
    assert (
        families[TechnicalFamilyId.VOLUME].hard_gate_description
        == "breakout-quality only if validated"
    )

    price_action = families[TechnicalFamilyId.PRICE_ACTION]
    assert price_action.role is CapabilityRole.PRIMARY_TRIGGER
    assert price_action.allowed_timeframes == ("5m", "15m", "1h")
    assert price_action.hard_gate_description == "HTF-aligned eligible"

    structural = families[TechnicalFamilyId.STRUCTURAL_LEVELS]
    assert structural.role is CapabilityRole.PRIMARY
    assert structural.hard_gate_description == "invalidation / TP eligible"

    for family_id in (
        TechnicalFamilyId.FIBONACCI,
        TechnicalFamilyId.PATTERN_RECOGNITION,
        TechnicalFamilyId.MACRO_CYCLE,
    ):
        assert families[family_id].hard_gate_eligibility is HardGateEligibility.FALSE


def test_deterministic_analytics_catalog_rejects_family_drift() -> None:
    with pytest.raises(ValueError, match="05_DETERMINISTIC_ANALYTICS"):
        DeterministicAnalyticsCatalog(
            catalog_id="analytics-1",
            version="2.0.0",
            domain=CanonicalDomainId.INTELLIGENCE,
            technical_families=build_deterministic_analytics_catalog().technical_families,
        )

    with pytest.raises(ValueError, match="A-I"):
        DeterministicAnalyticsCatalog(
            catalog_id="analytics-2",
            version="2.0.0",
            technical_families=(
                build_deterministic_analytics_catalog().technical_families[0],
            ),
        )

    with pytest.raises(ValueError, match="canonical"):
        TechnicalFamilyGovernance(
            family_id=TechnicalFamilyId.TREND,
            feature_family=DeterministicFeatureFamily.TREND,
            role=CapabilityRole.PRIMARY,
            allowed_timeframes=("3m",),
            score_contribution=ScoreContributionLevel.HIGH,
            hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
            hard_gate_description="OOS-eligible",
        )


def test_core_constitution_defines_mission_authority_cycle_and_rules() -> None:
    constitution = build_core_constitution()

    assert constitution is not AI4BINANCE_CORE_CONSTITUTION
    assert constitution.constitution_id == "AI4BINANCE-CORE-CONSTITUTION"
    assert constitution.final_decision_authority is (
        CoreAuthorityOwner.DETERMINISTIC_CORE
    )
    assert constitution.risk_authority is CoreAuthorityOwner.RISK
    assert constitution.execution_authority is CoreAuthorityOwner.EXECUTION
    assert constitution.live_authority is CoreAuthorityOwner.HUMAN
    assert constitution.default_trading_mode == "paper"
    assert constitution.default_order_mode == "manual"
    assert constitution.allow_auto_live_orders is False
    assert constitution.fail_policy == "NO_TRADE"
    assert constitution.change_control.code_runs_within_constitution is True
    assert constitution.change_control.quality_gate_role == "TECHNICAL_TRUTH"
    assert constitution.change_control.governance_gate_role == "POLICY_ELIGIBILITY"
    assert constitution.change_control.human_governance_role == (
        "CONSEQUENTIAL_AUTHORITY"
    )
    assert constitution.change_control.risk_tiered_human_governance is True
    assert constitution.change_control.change_classes == tuple(ChangeApprovalClass)
    assert constitution.change_control.change_classes_without_human_governance == (
        ChangeApprovalClass.C0_NON_BEHAVIORAL,
        ChangeApprovalClass.C1_LOW_RISK,
    )
    assert constitution.change_control.approval_packet_required_change_classes == (
        ChangeApprovalClass.C2_BEHAVIORAL,
        ChangeApprovalClass.C3_GOVERNED,
        ChangeApprovalClass.C4_CONSEQUENTIAL,
    )
    assert constitution.change_control.double_approval_change_classes == (
        ChangeApprovalClass.C3_GOVERNED,
    )
    assert constitution.change_control.high_assurance_change_classes == (
        ChangeApprovalClass.C4_CONSEQUENTIAL,
    )
    assert constitution.change_control.constitution_sync_change_classes == (
        ChangeApprovalClass.C3_GOVERNED,
        ChangeApprovalClass.C4_CONSEQUENTIAL,
    )
    assert constitution.change_control.constitution_sync_required is True
    assert constitution.change_control.code_constitution_divergence_allowed is False
    assert "policy" in constitution.change_control.auto_revision_targets
    assert "instructions" in constitution.change_control.auto_revision_targets
    assert "system_effect" in constitution.change_control.required_eli10_sections
    assert constitution.change_control.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert tuple(item.owner for item in constitution.authority_principles) == tuple(
        CoreAuthorityOwner
    )
    assert constitution.cycle == tuple(CanonicalCycleStep)
    assert tuple(rule.rule_id for rule in constitution.rules) == tuple(
        CoreConstitutionRuleId
    )
    assert constitution.rules[0].statement == "CAPITAL_PROTECTION > TRADE_FREQUENCY"
    assert constitution.rules[6].statement == "AGENT != FINAL_DECISION_AUTHORITY"
    assert "NON-CODE CONTENT LANGUAGE en-US" in constitution.rules[17].statement
    assert constitution.rules[24].statement == "LIVE IS OPT-IN; PAPER/MANUAL IS DEFAULT"


def test_core_constitution_rejects_authority_and_cycle_drift() -> None:
    baseline = build_core_constitution()

    with pytest.raises(ValueError, match="deterministic core"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            final_decision_authority=CoreAuthorityOwner.AGENTS,
        )
    with pytest.raises(ValueError, match="canonical cycle"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=tuple(reversed(baseline.cycle)),
            rules=baseline.rules,
        )
    with pytest.raises(ValueError, match="C01-C25"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules[:-1],
        )
    with pytest.raises(ValueError, match="auto live"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            allow_auto_live_orders=True,
        )
    with pytest.raises(ValueError, match="TECHNICAL_TRUTH"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            change_control=ConstitutionalChangeControl(
                quality_gate_role="NOT_TECHNICAL_TRUTH",
            ),
        )
    with pytest.raises(ValueError, match="statement"):
        CoreConstitutionRule(CoreConstitutionRuleId.C01, " ")


def test_constitutional_change_control_locks_code_and_docs_together() -> None:
    control = ConstitutionalChangeControl()

    assert control.code_runs_within_constitution is True
    assert control.quality_gate_role == "TECHNICAL_TRUTH"
    assert control.governance_gate_role == "POLICY_ELIGIBILITY"
    assert control.human_governance_role == "CONSEQUENTIAL_AUTHORITY"
    assert control.risk_tiered_human_governance is True
    assert control.change_classes == tuple(ChangeApprovalClass)
    assert control.constitution_sync_required is True
    assert control.code_constitution_divergence_allowed is False
    assert control.execution_allowed is False
    assert control.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert control.required_eli10_sections == (
        "system_effect",
        "benefits",
        "risks",
        "affected_contracts",
        "validation_plan",
        "rollback_or_stop_condition",
        "live_eligibility_status",
    )

    with pytest.raises(ValueError, match="within the constitution"):
        ConstitutionalChangeControl(code_runs_within_constitution=False)
    with pytest.raises(ValueError, match="risk-tiered"):
        ConstitutionalChangeControl(
            risk_tiered_human_governance=False,
        )
    with pytest.raises(ValueError, match="include policy"):
        ConstitutionalChangeControl(
            auto_revision_targets=("instructions",),
        )
    with pytest.raises(ValueError, match="include instructions"):
        ConstitutionalChangeControl(
            auto_revision_targets=("policy",),
        )
    with pytest.raises(ValueError, match="divergence"):
        ConstitutionalChangeControl(code_constitution_divergence_allowed=True)


def test_constitutional_change_control_rejects_duplicate_and_execution_drift() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        ConstitutionalChangeControl(
            auto_revision_targets=("policy", "policy", "instructions"),
        )
    with pytest.raises(ValueError, match="must be unique"):
        ConstitutionalChangeControl(
            required_eli10_sections=("system_effect", "system_effect"),
        )
    with pytest.raises(ValueError, match="C0-C4"):
        ConstitutionalChangeControl(
            change_classes=(ChangeApprovalClass.C0_NON_BEHAVIORAL,),
        )
    with pytest.raises(ValueError, match="constitution sync is required"):
        ConstitutionalChangeControl(constitution_sync_required=False)
    with pytest.raises(ValueError, match="cannot authorize trading"):
        ConstitutionalChangeControl(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot authorize trading"):
        ConstitutionalChangeControl(live_eligibility_status="PAPER_ONLY")


def test_authority_principle_and_core_constitution_reject_change_control_drift() -> (
    None
):
    baseline = build_core_constitution()

    with pytest.raises(ValueError, match="statement cannot be empty"):
        AuthorityPrinciple(CoreAuthorityOwner.DATA, " ")

    def mutated_change_control(**updates: object) -> ConstitutionalChangeControl:
        control = ConstitutionalChangeControl()
        for field_name, value in updates.items():
            object.__setattr__(control, field_name, value)
        return control

    with pytest.raises(ValueError, match="constitutional change control"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            change_control=mutated_change_control(code_runs_within_constitution=False),
        )
    with pytest.raises(ValueError, match="POLICY_ELIGIBILITY"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            change_control=mutated_change_control(
                governance_gate_role="NOT_POLICY_ELIGIBILITY"
            ),
        )
    with pytest.raises(ValueError, match="document sync"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            change_control=mutated_change_control(constitution_sync_required=False),
        )


def test_core_constitution_rejects_additional_authority_and_default_drift() -> None:
    baseline = build_core_constitution()

    with pytest.raises(ValueError, match="identity"):
        CoreConstitution(
            constitution_id="",
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
        )
    with pytest.raises(ValueError, match="mission"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=" ",
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
        )
    with pytest.raises(ValueError, match="every authority principle"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles[:-1],
            cycle=baseline.cycle,
            rules=baseline.rules,
        )
    with pytest.raises(ValueError, match="Risk Engine"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            risk_authority=CoreAuthorityOwner.GOVERNANCE,
        )
    with pytest.raises(ValueError, match="live authority"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            live_authority=CoreAuthorityOwner.EXECUTION,
        )
    with pytest.raises(ValueError, match="execution gates"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            execution_authority=CoreAuthorityOwner.HUMAN,
        )
    with pytest.raises(ValueError, match="paper/manual defaults"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            default_order_mode="auto",
        )
    with pytest.raises(ValueError, match="core fail policy"):
        CoreConstitution(
            constitution_id=baseline.constitution_id,
            version=baseline.version,
            mission=baseline.mission,
            authority_principles=baseline.authority_principles,
            cycle=baseline.cycle,
            rules=baseline.rules,
            fail_policy="WAIT",
        )


def test_core_architecture_defines_00_to_18_domains_and_planes() -> None:
    architecture = build_core_architecture()

    assert architecture is not AI4BINANCE_CORE_ARCHITECTURE
    assert architecture.architecture_id == "AI4BINANCE-CORE-ARCHITECTURE"
    assert architecture.planes == tuple(ArchitecturePlane)
    assert tuple(item.domain_id for item in architecture.domains) == tuple(
        CanonicalDomainId
    )
    assert len(architecture.domains) == 19
    assert architecture.domains[0].domain_id is CanonicalDomainId.META
    assert architecture.domains[-1].domain_id is (CanonicalDomainId.RESEARCH_CAPABILITY)
    assert architecture.research_capability_chain == (
        CanonicalDomainId.RESEARCH_CAPABILITY,
        CanonicalDomainId.DETERMINISTIC_ANALYTICS,
        CanonicalDomainId.VALIDATION,
        CanonicalDomainId.GOVERNANCE,
    )

    grouped = architecture.domains_by_plane
    data_evidence_domains = tuple(
        item.domain_id for item in grouped[ArchitecturePlane.DATA_EVIDENCE]
    )
    assert data_evidence_domains == (
        CanonicalDomainId.MARKET_DATA,
        CanonicalDomainId.SHARED_MARKET_STATE,
        CanonicalDomainId.EVIDENCE,
    )
    intelligence_domains = tuple(
        item.domain_id for item in grouped[ArchitecturePlane.INTELLIGENCE]
    )
    assert intelligence_domains == (
        CanonicalDomainId.INTELLIGENCE,
        CanonicalDomainId.DETERMINISTIC_ANALYTICS,
        CanonicalDomainId.AGENT_OBSERVATIONS,
    )
    assert tuple(
        item.domain_id for item in grouped[ArchitecturePlane.DECISION_EXECUTION]
    ) == (
        CanonicalDomainId.DECISION,
        CanonicalDomainId.RISK,
        CanonicalDomainId.PORTFOLIO,
        CanonicalDomainId.EXECUTION,
    )
    assert tuple(
        item.domain_id for item in grouped[ArchitecturePlane.ORCHESTRATION_EVENT_FABRIC]
    ) == (CanonicalDomainId.EVENT_FABRIC,)


def test_core_architecture_rejects_domain_plane_and_backbone_drift() -> None:
    baseline = build_core_architecture()

    with pytest.raises(ValueError, match="00_META through 18"):
        CoreArchitecture(
            architecture_id=baseline.architecture_id,
            version=baseline.version,
            domains=baseline.domains[:-1],
        )
    with pytest.raises(ValueError, match="planes are immutable"):
        CoreArchitecture(
            architecture_id=baseline.architecture_id,
            version=baseline.version,
            domains=baseline.domains,
            planes=tuple(reversed(baseline.planes)),
        )
    with pytest.raises(ValueError, match="ResearchUnit"):
        CoreArchitecture(
            architecture_id=baseline.architecture_id,
            version=baseline.version,
            domains=baseline.domains,
            research_capability_chain=(
                CanonicalDomainId.RESEARCH_CAPABILITY,
                CanonicalDomainId.GOVERNANCE,
            ),
        )
    with pytest.raises(ValueError, match="backbone"):
        CanonicalDomainDefinition(
            CanonicalDomainId.EVENT_FABRIC,
            ArchitecturePlane.CONTROL_ASSURANCE,
            "AgenticOrchestration",
            "Invalid backbone plane.",
            backbone=True,
        )


def test_governance_registry_catalog_contains_requested_registry_families() -> None:
    catalog = build_ai4binance_governance_registry_catalog()

    assert tuple(catalog.definitions_by_kind) == MANDATORY_REGISTRY_KINDS
    assert set(catalog.definitions_by_kind) == set(RegistryKind)
    assert len(catalog.definitions_by_kind) == 22
    assert catalog.definitions_by_kind[RegistryKind.AGENT].concept is (
        EngineeringConcept.AGENTIC_ORCHESTRATION_ENGINEERING
    )
    assert catalog.definitions_by_kind[RegistryKind.CAPABILITY].concept is (
        EngineeringConcept.FEATURE_ENGINEERING
    )
    assert catalog.definitions_by_kind[RegistryKind.ORACLE].concept is (
        EngineeringConcept.BACKTEST_VALIDATION_ENGINEERING
    )
    assert catalog.definitions_by_kind[RegistryKind.FORMULA].concept is (
        EngineeringConcept.FEATURE_ENGINEERING
    )
    assert catalog.definitions_by_kind[RegistryKind.VALIDATION_PROFILE].concept is (
        EngineeringConcept.BACKTEST_VALIDATION_ENGINEERING
    )
    assert catalog.definitions_by_kind[RegistryKind.POLICY].concept is (
        EngineeringConcept.DECISION_GOVERNANCE_ENGINEERING
    )
    assert catalog.entries_for(RegistryKind.TOOL) == ()


def test_governance_registry_entries_are_fail_closed_and_unique() -> None:
    catalog = build_ai4binance_governance_registry_catalog()
    entry = GovernedRegistryEntry(
        entry_id="indicator:supertrend:1",
        registry=RegistryKind.INDICATOR,
        name="Supertrend",
        version="1",
        owner="FeatureEngineering",
        concept=EngineeringConcept.FEATURE_ENGINEERING,
        evidence_ids=("ev-1",),
        policy_ids=("policy-1",),
    )
    enriched = GovernanceRegistryCatalog(
        catalog_id=catalog.catalog_id,
        version=catalog.version,
        definitions=catalog.definitions,
        entries=(entry,),
    )

    assert enriched.entries_by_id[entry.entry_id] is entry
    assert enriched.entries_for(RegistryKind.INDICATOR) == (entry,)
    assert entry.execution_allowed is False
    assert entry.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="trading authority"):
        GovernedRegistryEntry(
            entry_id="risk:live:1",
            registry=RegistryKind.RISK_RULE,
            name="bad",
            version="1",
            owner="Risk",
            concept=EngineeringConcept.RISK_PORTFOLIO_ENGINEERING,
            execution_allowed=True,
        )


def test_governance_registry_rejects_missing_mandatory_family() -> None:
    catalog = build_ai4binance_governance_registry_catalog()
    definitions = tuple(
        item for item in catalog.definitions if item.registry is not RegistryKind.TOOL
    )

    with pytest.raises(ValueError, match="mandatory registry"):
        GovernanceRegistryCatalog(
            catalog_id="missing-tool",
            version="1",
            definitions=definitions,
        )
    with pytest.raises(ValueError, match="cannot be empty"):
        RegistryDefinition(
            RegistryKind.TOOL,
            "",
            EngineeringConcept.SECURITY_RELIABILITY_ENGINEERING,
            "Tool contracts",
        )


def test_structure_capability_chains_are_explicit_and_fail_closed() -> None:
    chains = build_structure_capability_chains()

    assert tuple(item.capability_id for item in chains) == tuple(StructuralCapabilityId)
    assert {item.capability_id.value for item in chains} == {
        "SWING_HIGH_LOW",
        "BOS",
        "CHoCH",
        "BREAKOUT",
        "FAILED_BREAKOUT",
        "STRUCTURE_SHIFT",
    }
    for chain in chains:
        assert chain.formula_id.startswith("formula:structure:")
        assert chain.oracle_id.startswith("oracle:structure:")
        assert chain.test_ids
        assert chain.evidence_complete is False
        assert chain.blockers == (
            "CAPABILITY_OOS_ARTIFACTS_MISSING",
            "CAPABILITY_REGIME_EVIDENCE_MISSING",
            "CAPABILITY_NOT_OOS_VALIDATED",
        )
        assert chain.execution_allowed is False
        assert chain.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_capability_chain_requires_formula_oracle_tests_oos_and_regime_evidence() -> (
    None
):
    validated = CapabilityValidationChain(
        capability_id=StructuralCapabilityId.BOS,
        formula_id="formula:structure:BOS:1",
        oracle_id="oracle:structure:BOS:1",
        test_ids=("test:bos:oracle",),
        oos_artifact_ids=("oos:bos:20260813",),
        regime_evidence_ids=("regime:bos:trend-range",),
        owner="FeatureEngineering",
        status=CapabilityStatus.OOS_VALIDATED,
        hard_gate_eligible=True,
    )

    assert validated.evidence_complete is True
    assert validated.blockers == ()
    with pytest.raises(ValueError, match="requires tests"):
        CapabilityValidationChain(
            capability_id=StructuralCapabilityId.BREAKOUT,
            formula_id="formula:structure:BREAKOUT:1",
            oracle_id="oracle:structure:BREAKOUT:1",
            test_ids=(),
            oos_artifact_ids=("oos:breakout",),
            regime_evidence_ids=("regime:breakout",),
            owner="FeatureEngineering",
        )
    with pytest.raises(ValueError, match="OOS_VALIDATED"):
        CapabilityValidationChain(
            capability_id=StructuralCapabilityId.FAILED_BREAKOUT,
            formula_id="formula:structure:FAILED_BREAKOUT:1",
            oracle_id="oracle:structure:FAILED_BREAKOUT:1",
            test_ids=("test:failed-breakout",),
            oos_artifact_ids=("oos:failed-breakout",),
            regime_evidence_ids=("regime:failed-breakout",),
            owner="FeatureEngineering",
            hard_gate_eligible=True,
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        CapabilityValidationChain(
            capability_id=StructuralCapabilityId.STRUCTURE_SHIFT,
            formula_id="formula:structure:STRUCTURE_SHIFT:1",
            oracle_id="oracle:structure:STRUCTURE_SHIFT:1",
            test_ids=("test:structure-shift",),
            oos_artifact_ids=("oos:structure-shift",),
            regime_evidence_ids=("regime:structure-shift",),
            owner="FeatureEngineering",
            execution_allowed=True,
        )


def test_canonical_capability_contracts_require_formula_oracle_and_validation() -> None:
    contracts = build_structure_capability_contracts()

    assert tuple(item.capability_id for item in contracts) == (
        "SWING_HIGH_LOW",
        "BOS",
        "CHoCH",
        "BREAKOUT",
        "FAILED_BREAKOUT",
        "STRUCTURE_SHIFT",
    )
    first = contracts[0]
    assert first.family is CapabilityFamily.STRUCTURE
    assert first.role is CapabilityRole.PRIMARY
    assert first.implementation.formula_id.startswith("formula:structure:")
    assert first.implementation.oracle_id.startswith("oracle:structure:")
    assert first.score_contribution.level is ScoreContributionLevel.HIGH
    assert first.score_contribution.weight_ref == "weight:structure_score:baseline-v1"
    assert first.hard_gate.eligible is HardGateEligibility.CONDITIONAL
    assert first.hard_gate.promoted is False
    assert first.repainting.allowed is False
    assert first.lookahead.allowed is False
    assert first.repainting_allowed is False
    assert first.lookahead_allowed is False
    assert first.validation.oos_status is ValidationEvidenceStatus.UNKNOWN
    assert first.lifecycle_status is CapabilityStatus.RESEARCH_ONLY
    assert first.execution_allowed is False
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_capability_contract_rejects_unsafe_or_incomplete_shapes() -> None:
    implementation = CapabilityImplementation(
        "formula:structure:BOS:1",
        "oracle:structure:BOS:1",
    )
    validation = CapabilityValidationContract("validation:structure:BOS:1")

    def contract(
        *,
        repainting_allowed: bool = False,
        lookahead_allowed: bool = False,
        repainting: CapabilitySafetyGuard | None = None,
        lookahead: CapabilitySafetyGuard | None = None,
        allowed_timeframes: tuple[str, ...] = ("1h",),
        hard_gate: HardGateContract | None = None,
    ) -> CapabilityContract:
        return CapabilityContract(
            capability_id="BOS",
            version="1",
            family=CapabilityFamily.STRUCTURE,
            role=CapabilityRole.PRIMARY,
            implementation=implementation,
            allowed_timeframes=allowed_timeframes,
            supported_markets=("SPOT",),
            inputs=("MarketSnapshot",),
            outputs=("Feature:BOS",),
            score_contribution=ScoreContribution(
                ScoreContributionLevel.HIGH,
                "weight:structure_score:baseline-v1",
            ),
            hard_gate=hard_gate
            if hard_gate is not None
            else HardGateContract(HardGateEligibility.CONDITIONAL),
            known_failure_modes=("CHOP_FALSE_BREAK",),
            validation=validation,
            lifecycle_status=CapabilityStatus.RESEARCH_ONLY,
            repainting=repainting or CapabilitySafetyGuard(),
            lookahead=lookahead or CapabilitySafetyGuard(),
            repainting_allowed=repainting_allowed,
            lookahead_allowed=lookahead_allowed,
        )

    contract()
    with pytest.raises(ValueError, match="repainting/lookahead"):
        CapabilitySafetyGuard(allowed=True)
    with pytest.raises(ValueError, match="repainting"):
        contract(repainting_allowed=True)
    with pytest.raises(ValueError, match="lookahead"):
        contract(lookahead_allowed=True)
    with pytest.raises(ValueError, match="requires allowed_timeframes"):
        contract(allowed_timeframes=())
    with pytest.raises(ValueError, match="PASS OOS"):
        contract(
            hard_gate=HardGateContract(
                HardGateEligibility.CONDITIONAL,
                promoted=True,
            ),
        )


def test_capability_coverage_matrix_keeps_missing_from_becoming_pass() -> None:
    matrix = build_capability_coverage_matrix(build_structure_capability_contracts())
    row = matrix[0]

    assert row.formula is ValidationEvidenceStatus.PASS
    assert row.oracle is ValidationEvidenceStatus.PASS
    assert row.unit_tests is ValidationEvidenceStatus.UNKNOWN
    assert row.regression is ValidationEvidenceStatus.UNKNOWN
    assert row.walk_forward is ValidationEvidenceStatus.UNKNOWN
    assert row.oos is ValidationEvidenceStatus.UNKNOWN
    assert row.regime_validation is ValidationEvidenceStatus.UNKNOWN
    assert row.evidence_complete is False
    assert row.promotion_eligible is False
    assert "CAPABILITY_COVERAGE_OOS_UNKNOWN" in row.blockers

    with pytest.raises(ValueError, match="evidence_complete"):
        CapabilityCoverage(
            capability_id="BOS",
            formula=ValidationEvidenceStatus.PASS,
            oracle=ValidationEvidenceStatus.PASS,
            unit_tests=ValidationEvidenceStatus.PASS,
            regression=ValidationEvidenceStatus.PASS,
            walk_forward=ValidationEvidenceStatus.PASS,
            oos=ValidationEvidenceStatus.MISSING,
            regime_validation=ValidationEvidenceStatus.PASS,
            evidence_complete=True,
        )
    with pytest.raises(ValueError, match="promotion eligibility"):
        CapabilityCoverage(capability_id="BOS", promotion_eligible=True)


def test_complete_capability_coverage_can_be_promotion_eligible_but_not_live() -> None:
    coverage = CapabilityCoverage(
        capability_id="BOS",
        formula=ValidationEvidenceStatus.PASS,
        oracle=ValidationEvidenceStatus.PASS,
        unit_tests=ValidationEvidenceStatus.PASS,
        regression=ValidationEvidenceStatus.PASS,
        walk_forward=ValidationEvidenceStatus.PASS,
        oos=ValidationEvidenceStatus.PASS,
        regime_validation=ValidationEvidenceStatus.PASS,
        evidence_complete=True,
        promotion_eligible=True,
    )

    assert coverage.blockers == ()
    assert coverage.evidence_complete is True
    assert coverage.promotion_eligible is True


def test_capability_gap_registry_keeps_visible_gaps_from_promotion() -> None:
    registry = build_capability_gap_registry()

    assert registry is not AI4BINANCE_CAPABILITY_GAP_REGISTRY
    assert registry.domain is CanonicalDomainId.DETERMINISTIC_ANALYTICS
    assert registry.priority_flow == (
        CapabilityGapPriorityStep.CAPABILITY_INVENTORY,
        CapabilityGapPriorityStep.CAPABILITY_COVERAGE_MATRIX,
        CapabilityGapPriorityStep.FORMULA_ORACLE_CONTRACTS,
        CapabilityGapPriorityStep.OOS_EVIDENCE,
        CapabilityGapPriorityStep.REGISTRY_MAPPING,
        CapabilityGapPriorityStep.DECISION_CONTRIBUTION,
    )
    assert registry.default_missing_status is ValidationEvidenceStatus.MISSING
    assert tuple(gap.area for gap in registry.gaps) == tuple(CapabilityGapArea)

    gaps = {gap.area: gap for gap in registry.gaps}
    assert gaps[CapabilityGapArea.TREND].present_capabilities == (
        "EMA",
        "Supertrend",
        "trend channel",
    )
    assert gaps[CapabilityGapArea.TREND].missing_capabilities == (
        "capability coverage",
    )
    assert gaps[CapabilityGapArea.VOLATILITY].missing_capabilities == (
        "Bollinger",
        "Keltner",
        "squeeze",
        "realized-volatility catalog",
    )
    assert gaps[CapabilityGapArea.MOMENTUM].missing_capabilities == (
        "MACD",
        "Stochastic",
        "ROC",
        "CCI",
    )
    assert gaps[CapabilityGapArea.STRUCTURE].missing_capabilities == (
        "BOS evidence",
        "CHoCH evidence",
    )
    assert gaps[CapabilityGapArea.SUPPORT_RESISTANCE].missing_capabilities == (
        "pivot",
        "cluster",
        "zone decay",
        "reaction statistics",
    )
    assert gaps[CapabilityGapArea.DERIVATIVES].present_capabilities == (
        "funding",
        "OI",
        "long-short surfaces",
    )
    assert gaps[CapabilityGapArea.VALIDATION].missing_capabilities == (
        "capability-specific OOS artifacts",
    )
    assert gaps[CapabilityGapArea.OBSERVABILITY].missing_capabilities == (
        "capability health",
        "decision health",
    )
    assert gaps[CapabilityGapArea.DATA_QUALITY].missing_capabilities == (
        "expectation catalog",
        "capability catalog",
    )
    assert gaps[CapabilityGapArea.RESEARCH].missing_capabilities == (
        "Radar to ResearchUnit",
        "ResearchUnit to Capability",
        "Capability to Validation",
        "Validation to Promotion",
    )
    assert gaps[CapabilityGapArea.DGE].missing_capabilities == (
        "Radar capability-gap mapping",
    )

    for gap in registry.gaps:
        assert gap.coverage.evidence_complete is False
        assert gap.decision_contribution_allowed is False
        assert gap.promotion_eligible is False
        assert gap.coverage.oos is ValidationEvidenceStatus.MISSING
        assert gap.blockers

    assert "CAPABILITY_GAP_VALIDATION_EVIDENCE_GAP" in registry.blockers

    with pytest.raises(ValueError, match="every gap area"):
        CapabilityGapRegistry(gaps=registry.gaps[:-1])
    with pytest.raises(ValueError, match="priority flow"):
        CapabilityGapRegistry(
            priority_flow=tuple(reversed(tuple(CapabilityGapPriorityStep))),
            gaps=registry.gaps,
        )
    with pytest.raises(ValueError, match="MISSING"):
        CapabilityGapRegistry(
            gaps=registry.gaps,
            default_missing_status=ValidationEvidenceStatus.UNKNOWN,
        )
    with pytest.raises(ValueError, match="gap coverage"):
        CapabilityGap(
            area=CapabilityGapArea.TREND,
            present_capabilities=("EMA",),
            missing_capabilities=("coverage",),
            status=CapabilityGapStatus.EVIDENCE_GAP,
            required_next_step="Fix coverage mapping.",
            coverage=CapabilityCoverage(capability_id="Other"),
        )
    with pytest.raises(ValueError, match="decision"):
        CapabilityGap(
            area=CapabilityGapArea.TREND,
            present_capabilities=("EMA",),
            missing_capabilities=("coverage",),
            status=CapabilityGapStatus.EVIDENCE_GAP,
            required_next_step="Do not score until covered.",
            coverage=CapabilityCoverage(capability_id=CapabilityGapArea.TREND.value),
            decision_contribution_allowed=True,
        )
    with pytest.raises(ValueError, match="promotion eligible"):
        CapabilityGap(
            area=CapabilityGapArea.TREND,
            present_capabilities=("EMA",),
            missing_capabilities=("coverage",),
            status=CapabilityGapStatus.EVIDENCE_GAP,
            required_next_step="Do not promote until OOS exists.",
            coverage=CapabilityCoverage(capability_id=CapabilityGapArea.TREND.value),
            promotion_eligible=True,
        )


def test_agent_capability_governance_requires_capability_coverage() -> None:
    incomplete = CapabilityCoverage(
        capability_id="BOS",
        formula=ValidationEvidenceStatus.PASS,
        oracle=ValidationEvidenceStatus.PASS,
        unit_tests=ValidationEvidenceStatus.PASS,
        regression=ValidationEvidenceStatus.PASS,
        walk_forward=ValidationEvidenceStatus.PASS,
        oos=ValidationEvidenceStatus.MISSING,
        regime_validation=ValidationEvidenceStatus.PARTIAL,
        evidence_complete=False,
        promotion_eligible=False,
    )

    with pytest.raises(ValueError, match="complete capability coverage"):
        AgentCapabilityGovernance(
            agent_id="StructureAgent",
            capability_ids=("BOS",),
            capability_coverage=(incomplete,),
            agent_oos_status=ValidationEvidenceStatus.PASS,
            promotion_eligible=True,
        )

    with pytest.raises(ValueError, match="coverage for every capability"):
        AgentCapabilityGovernance(
            agent_id="StructureAgent",
            capability_ids=("BOS", "CHoCH"),
            capability_coverage=(incomplete,),
            agent_oos_status=ValidationEvidenceStatus.PASS,
        )

    complete = CapabilityCoverage(
        capability_id="BOS",
        formula=ValidationEvidenceStatus.PASS,
        oracle=ValidationEvidenceStatus.PASS,
        unit_tests=ValidationEvidenceStatus.PASS,
        regression=ValidationEvidenceStatus.PASS,
        walk_forward=ValidationEvidenceStatus.PASS,
        oos=ValidationEvidenceStatus.PASS,
        regime_validation=ValidationEvidenceStatus.PASS,
        evidence_complete=True,
        promotion_eligible=True,
    )

    governance = AgentCapabilityGovernance(
        agent_id="StructureAgent",
        capability_ids=("BOS",),
        capability_coverage=(complete,),
        agent_oos_status=ValidationEvidenceStatus.PASS,
        promotion_eligible=True,
    )

    assert governance.promotion_eligible is True


def test_market_data_contracts_separate_spot_authority_from_advisory_futures() -> None:
    contracts = {item.kind: item for item in build_market_data_contracts()}

    assert set(contracts) == set(MarketDataKind)
    for kind in (
        MarketDataKind.OHLCV,
        MarketDataKind.TICKER,
        MarketDataKind.SPREAD,
        MarketDataKind.LIQUIDITY,
        MarketDataKind.EXCHANGE_INFO,
        MarketDataKind.SYMBOL_FILTERS,
        MarketDataKind.MARKET_STATUS,
        MarketDataKind.SERVER_TIME,
    ):
        assert contracts[kind].spot_authority is (
            SpotDecisionAuthority.DECISION_AUTHORITY
        )
        assert contracts[kind].required_for_spot_decision is True

    for kind in (
        MarketDataKind.FUNDING,
        MarketDataKind.OPEN_INTEREST,
        MarketDataKind.LONG_SHORT_RATIO,
        MarketDataKind.TOP_TRADER_RATIO,
        MarketDataKind.TAKER_FLOW,
    ):
        assert contracts[kind].spot_authority is (
            SpotDecisionAuthority.SUPPLEMENTARY_ADVISORY
        )
        assert contracts[kind].required_for_spot_decision is False

    with pytest.raises(ValueError, match="required Spot data"):
        MarketDataContract(
            MarketDataKind.FUNDING,
            SpotDecisionAuthority.SUPPLEMENTARY_ADVISORY,
            True,
            "Invalid Spot authority classification.",
        )


def test_agent_observation_is_bounded_assessment_without_execution_authority() -> None:
    observation = AgentObservation(
        observation_id="obs-structure-1",
        agent_id="StructureAgent",
        agent_version="1",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        symbol="HOTUSDT",
        timeframe="1h",
        capability_ids=("BOS", "CHoCH"),
        assessment="Structure shifted but OOS evidence is incomplete.",
        confidence=0.62,
        uncertainty=0.38,
        evidence_ids=("evidence-1",),
        conflicting_evidence_ids=("evidence-2",),
        blockers=("CAPABILITY_OOS_ARTIFACTS_MISSING",),
        data_quality_score=0.91,
    )

    assert observation.execution_authority == "NONE"
    assert not hasattr(observation, "action")
    assert not hasattr(observation, "entry")
    assert not hasattr(observation, "position_size")

    with pytest.raises(ValueError, match="execution authority"):
        AgentObservation(
            observation_id="obs-live",
            agent_id="StructureAgent",
            agent_version="1",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            symbol="HOTUSDT",
            timeframe="1h",
            capability_ids=("BOS",),
            assessment="Bad authority.",
            confidence=0.5,
            uncertainty=0.5,
            data_quality_score=0.5,
            execution_authority="LIVE",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="confidence"):
        AgentObservation(
            observation_id="obs-confidence",
            agent_id="StructureAgent",
            agent_version="1",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            symbol="HOTUSDT",
            timeframe="1h",
            capability_ids=("BOS",),
            assessment="Bad confidence.",
            confidence=1.5,
            uncertainty=0.5,
            data_quality_score=0.5,
        )


def test_canonical_agent_contract_preserves_anatomy_and_authority_boundaries() -> None:
    contract = AgentContract(
        identity=AgentIdentityContract(
            agent_id="StructureAgent",
            version="1",
            role="bounded market-structure assessment",
        ),
        capabilities=AgentCapabilitiesContract(("BOS", "CHoCH")),
        intelligence_type=AgentIntelligenceType.DETERMINISTIC,
    )

    assert contract.anatomy == tuple(AgentAnatomyPart)
    assert contract.inputs.canonical_only is True
    assert contract.outputs.schema == "AgentObservation"
    assert contract.authority.analyze is True
    assert contract.authority.generate_evidence is True
    assert contract.authority.recommend is True
    assert contract.authority.final_trade_decision is False
    assert contract.authority.risk_override is False
    assert contract.authority.policy_override is False
    assert contract.authority.parameter_promotion is False
    assert contract.authority.live_execution is False
    assert contract.validation.required is True
    assert contract.failure.default == "AGENT_UNAVAILABLE"

    with pytest.raises(ValueError, match="AgentObservation"):
        AgentOutputsContract(schema="TradeSignal")

    with pytest.raises(ValueError, match="final/risk/policy/live authority"):
        AgentAuthorityContract(final_trade_decision=True)

    with pytest.raises(ValueError, match="canonical 10 parts"):
        AgentContract(
            identity=contract.identity,
            capabilities=contract.capabilities,
            intelligence_type=AgentIntelligenceType.LLM_ADVISORY,
            anatomy=tuple(reversed(tuple(AgentAnatomyPart))),
        )

    with pytest.raises(ValueError, match="canonical_only"):
        AgentInputsContract(canonical_only=False)

    with pytest.raises(ValueError, match="AGENT_UNAVAILABLE"):
        AgentFailureContract(default="NO_TRADE")

    with pytest.raises(ValueError, match="validation"):
        AgentValidationContract(required=False)


def test_agent_registry_definitions_expose_evidence_and_verification_layers() -> None:
    definition = build_default_registry().get("trend")

    assert definition.evidence_layer_schema == "AgentEvidenceLayer/v1"
    assert definition.verification_layer_schema == "VerificationLayer/v1"
    assert definition.required_evidence_domains == ()
    assert definition.required_verification_checks == ()


def test_agent_evidence_layer_blocks_incomplete_or_conflicted_evidence() -> None:
    verified = AgentEvidenceReference(
        evidence_id="ev-1",
        source_id="snapshot-1",
        claim="Trend structure supports continuation.",
        status=AgentEvidenceStatus.VERIFIED,
        observed_at=NOW,
        content_hash="a" * 64,
    )
    unavailable = AgentEvidenceReference(
        evidence_id="ev-2",
        source_id="provider",
        claim="Order book feed missing.",
        status=AgentEvidenceStatus.DATA_UNAVAILABLE,
        observed_at=NOW,
    )

    complete = AgentEvidenceLayer(
        layer_id="layer-1",
        agent_id="trend",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        evidence=(verified,),
    )
    blocked = AgentEvidenceLayer(
        layer_id="layer-2",
        agent_id="trend",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        evidence=(verified, unavailable),
        conflicting_evidence_ids=("ev-2",),
        minimum_required=2,
    )

    assert complete.evidence_complete is True
    assert complete.blockers == ()
    assert blocked.evidence_complete is False
    assert blocked.blockers == (
        "AGENT_EVIDENCE_INCOMPLETE",
        "AGENT_EVIDENCE_CONFLICTED",
        "AGENT_EVIDENCE_DATA_UNAVAILABLE",
    )


def test_agent_evidence_rejects_invalid_reference_and_layer_contracts() -> None:
    with pytest.raises(ValueError, match="evidence_id cannot be empty"):
        AgentEvidenceReference(
            evidence_id=" ",
            source_id="snapshot-1",
            claim="Trend claim.",
            status=AgentEvidenceStatus.VERIFIED,
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        AgentEvidenceReference(
            evidence_id="ev-naive",
            source_id="snapshot-1",
            claim="Trend claim.",
            status=AgentEvidenceStatus.VERIFIED,
            observed_at=datetime(2026, 8, 13, 17, 0),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        AgentEvidenceReference(
            evidence_id="ev-hash",
            source_id="snapshot-1",
            claim="Trend claim.",
            status=AgentEvidenceStatus.VERIFIED,
            observed_at=NOW,
            content_hash="short",
        )

    verified = AgentEvidenceReference(
        evidence_id="ev-1",
        source_id="snapshot-1",
        claim="Trend structure supports continuation.",
        status=AgentEvidenceStatus.VERIFIED,
        observed_at=NOW,
    )
    with pytest.raises(ValueError, match="minimum_required"):
        AgentEvidenceLayer(
            layer_id="layer-bad",
            agent_id="trend",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            evidence=(verified,),
            minimum_required=0,
        )
    with pytest.raises(ValueError, match="must be unique"):
        AgentEvidenceLayer(
            layer_id="layer-duplicate",
            agent_id="trend",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            evidence=(verified, verified),
        )
    with pytest.raises(ValueError, match="local evidence"):
        AgentEvidenceLayer(
            layer_id="layer-unknown-conflict",
            agent_id="trend",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            evidence=(verified,),
            conflicting_evidence_ids=("missing-ev",),
        )


def test_verification_layer_is_fail_closed_and_never_live_authoritative() -> None:
    layer = VerificationLayer(
        layer_id="verification-1",
        agent_id="trend",
        validation_profile_id="profile-1",
        checks=(
            VerificationCheck(
                check_id="oracle",
                description="Formula oracle passes.",
                result=VerificationResult.PASS,
                evidence_ids=("ev-1",),
                reason_codes=("ORACLE_PASS",),
            ),
            VerificationCheck(
                check_id="oos",
                description="OOS artifact is missing.",
                result=VerificationResult.UNKNOWN,
                reason_codes=("OOS_MISSING",),
            ),
        ),
    )

    assert layer.result is VerificationResult.UNKNOWN
    assert layer.blockers == ("AGENT_VERIFICATION_UNKNOWN",)
    assert layer.execution_allowed is False
    assert layer.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="cannot authorize trading"):
        VerificationLayer(
            layer_id="verification-2",
            agent_id="trend",
            validation_profile_id="profile-1",
            checks=(
                VerificationCheck(
                    check_id="oracle",
                    description="Formula oracle passes.",
                    result=VerificationResult.PASS,
                ),
            ),
            execution_allowed=True,
        )


def test_verification_layer_covers_fail_partial_and_invalid_contracts() -> None:
    passed = VerificationCheck(
        check_id="oracle",
        description="Formula oracle passes.",
        result=VerificationResult.PASS,
    )
    failed = VerificationCheck(
        check_id="risk",
        description="Risk invariant failed.",
        result=VerificationResult.FAIL,
    )

    failing_layer = VerificationLayer(
        layer_id="verification-fail",
        agent_id="risk",
        validation_profile_id="profile-1",
        checks=(passed, failed),
    )
    assert failing_layer.result is VerificationResult.FAIL
    assert failing_layer.blockers == ("AGENT_VERIFICATION_FAILED",)

    partial_layer = VerificationLayer(
        layer_id="verification-partial",
        agent_id="risk",
        validation_profile_id="profile-1",
        checks=(passed, failed),
        minimum_pass_ratio=0.75,
    )
    assert partial_layer.pass_ratio == 0.5
    assert partial_layer.result is VerificationResult.FAIL

    partial_without_fail = VerificationLayer(
        layer_id="verification-partial-no-fail",
        agent_id="risk",
        validation_profile_id="profile-1",
        checks=(
            passed,
            VerificationCheck(
                check_id="soft",
                description="Soft evidence only.",
                result=VerificationResult.PARTIAL,
            ),
        ),
        minimum_pass_ratio=0.75,
    )
    assert partial_without_fail.result is VerificationResult.PARTIAL
    assert partial_without_fail.blockers == ("AGENT_VERIFICATION_PARTIAL",)

    with pytest.raises(ValueError, match="requires checks"):
        VerificationLayer(
            layer_id="verification-empty",
            agent_id="risk",
            validation_profile_id="profile-1",
            checks=(),
        )
    with pytest.raises(ValueError, match="between zero and one"):
        VerificationLayer(
            layer_id="verification-nan",
            agent_id="risk",
            validation_profile_id="profile-1",
            checks=(passed,),
            minimum_pass_ratio=nan,
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        VerificationLayer(
            layer_id="verification-live",
            agent_id="risk",
            validation_profile_id="profile-1",
            checks=(passed,),
            live_eligibility_status="READY",
        )
    with pytest.raises(ValueError, match="cannot contain empty"):
        VerificationCheck(
            check_id="blank-reason",
            description="Blank reason rejected.",
            result=VerificationResult.PARTIAL,
            reason_codes=(" ",),
        )


def test_policy_as_code_engine_defaults_deny_and_requires_approval() -> None:
    engine = PolicyAsCodeEngine(deny_all_policy_as_code())
    denied = engine.evaluate(
        PolicyRequest(
            resource_type="Strategy",
            action="READ",
            facts={"environment": "paper"},
        )
    )

    assert denied.effect is PolicyEffect.DENY
    assert denied.reason_codes == ("POLICY_AS_CODE_DEFAULT_DENY",)
    document = PolicyAsCodeDocument(
        policy_id="AI4BINANCE-FRAMEWORK-POLICY",
        version="1",
        rules=(
            PolicyAsCodeRule(
                rule_id="paper-strategy-read",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                resource_types=("Strategy",),
                actions=("READ",),
                conditions=(
                    PolicyCondition(
                        "environment",
                        PolicyConditionOperator.EQUALS,
                        ("paper",),
                    ),
                ),
                reason_code="STRATEGY_READ_APPROVAL_REQUIRED",
            ),
        ),
    )
    engine = PolicyAsCodeEngine(document)

    needs_approval = engine.evaluate(
        PolicyRequest("Strategy", "READ", {"environment": "paper"})
    )
    approved = engine.evaluate(
        PolicyRequest("Strategy", "READ", {"environment": "paper"}, approved=True)
    )

    assert needs_approval.effect is PolicyEffect.REQUIRE_APPROVAL
    assert approved.effect is PolicyEffect.ALLOW
    assert approved.execution_allowed is False
    assert approved.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_policy_conditions_cover_matching_and_validation_edges() -> None:
    facts = {"environment": "paper", "owner": "governance"}

    assert PolicyCondition("owner", PolicyConditionOperator.PRESENT).matches(facts)
    assert not PolicyCondition("missing", PolicyConditionOperator.PRESENT).matches(
        facts
    )
    assert PolicyCondition("missing", PolicyConditionOperator.ABSENT).matches(facts)
    assert PolicyCondition(
        "environment",
        PolicyConditionOperator.EQUALS,
        ("paper",),
    ).matches(facts)
    assert PolicyCondition(
        "environment",
        PolicyConditionOperator.NOT_EQUALS,
        ("live",),
    ).matches(facts)
    assert not PolicyCondition(
        "missing",
        PolicyConditionOperator.NOT_EQUALS,
        ("live",),
    ).matches(facts)
    assert PolicyCondition(
        "environment",
        PolicyConditionOperator.IN,
        ("paper", "dry_run"),
    ).matches(facts)

    with pytest.raises(ValueError, match="condition key"):
        PolicyCondition(" ", PolicyConditionOperator.PRESENT)
    with pytest.raises(ValueError, match="values are required"):
        PolicyCondition("environment", PolicyConditionOperator.EQUALS)
    with pytest.raises(ValueError, match="presence policy"):
        PolicyCondition("owner", PolicyConditionOperator.PRESENT, ("governance",))
    with pytest.raises(ValueError, match="must be unique"):
        PolicyCondition("environment", PolicyConditionOperator.IN, ("paper", "paper"))
    with pytest.raises(ValueError, match="cannot contain empty"):
        PolicyCondition("environment", PolicyConditionOperator.IN, ("paper", " "))


def test_policy_as_code_rule_document_request_and_evaluation_guards() -> None:
    condition = PolicyCondition(
        "environment",
        PolicyConditionOperator.EQUALS,
        ("paper",),
    )

    with pytest.raises(ValueError, match="rule identity"):
        PolicyAsCodeRule("", PolicyEffect.DENY, ("Strategy",), ("READ",))
    with pytest.raises(ValueError, match="selectors"):
        PolicyAsCodeRule("missing-resource", PolicyEffect.DENY, (), ("READ",))
    with pytest.raises(ValueError, match="resource types must be unique"):
        PolicyAsCodeRule(
            "duplicate-resource",
            PolicyEffect.DENY,
            ("Strategy", "Strategy"),
            ("READ",),
        )
    with pytest.raises(ValueError, match="actions must be unique"):
        PolicyAsCodeRule(
            "duplicate-action",
            PolicyEffect.DENY,
            ("Strategy",),
            ("READ", "READ"),
        )
    with pytest.raises(ValueError, match="condition keys must be unique"):
        PolicyAsCodeRule(
            "duplicate-condition",
            PolicyEffect.DENY,
            ("Strategy",),
            ("READ",),
            conditions=(condition, condition),
        )
    with pytest.raises(ValueError, match="priority cannot be negative"):
        PolicyAsCodeRule(
            "negative-priority",
            PolicyEffect.DENY,
            ("Strategy",),
            ("READ",),
            priority=-1,
        )
    with pytest.raises(ValueError, match="document identity"):
        PolicyAsCodeDocument("", "1")
    with pytest.raises(ValueError, match="default must deny"):
        PolicyAsCodeDocument("policy", "1", default_effect=PolicyEffect.ALLOW)
    duplicate_rule = PolicyAsCodeRule("deny-read", PolicyEffect.DENY, ("A",), ("B",))
    with pytest.raises(ValueError, match="rule IDs must be unique"):
        PolicyAsCodeDocument("policy", "1", rules=(duplicate_rule, duplicate_rule))
    with pytest.raises(ValueError, match="request identity"):
        PolicyRequest(" ", "READ")
    with pytest.raises(ValueError, match="facts must be non-empty"):
        PolicyRequest("Strategy", "READ", {"environment": " "})
    with pytest.raises(ValueError, match="cannot grant execution authority"):
        PolicyEvaluation(
            PolicyEffect.ALLOW,
            ("APPROVED",),
            "policy",
            "1",
            HASH,
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot grant execution authority"):
        PolicyEvaluation(
            PolicyEffect.ALLOW,
            ("APPROVED",),
            "policy",
            "1",
            HASH,
            live_eligibility_status="READY",
        )


def test_policy_as_code_engine_orders_rules_and_returns_fail_closed_effects() -> None:
    document = PolicyAsCodeDocument(
        policy_id="AI4BINANCE-FRAMEWORK-POLICY",
        version="2",
        rules=(
            PolicyAsCodeRule(
                rule_id="late-deny",
                effect=PolicyEffect.DENY,
                resource_types=("Strategy",),
                actions=("READ",),
                reason_code="LATE_DENY",
                priority=50,
            ),
            PolicyAsCodeRule(
                rule_id="early-restrict",
                effect=PolicyEffect.RESTRICT,
                resource_types=("Strategy",),
                actions=("READ",),
                reason_code="READ_RESTRICTED",
                priority=10,
            ),
            PolicyAsCodeRule(
                rule_id="write-approval",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                resource_types=("Strategy",),
                actions=("WRITE",),
                conditions=(
                    PolicyCondition(
                        "environment",
                        PolicyConditionOperator.EQUALS,
                        ("paper",),
                    ),
                ),
                reason_code="WRITE_APPROVAL_REQUIRED",
            ),
        ),
    )
    engine = PolicyAsCodeEngine(document)

    restricted = engine.evaluate(PolicyRequest("Strategy", "READ"))
    condition_miss = engine.evaluate(
        PolicyRequest("Strategy", "WRITE", {"environment": "live"})
    )
    resource_miss = engine.evaluate(PolicyRequest("Dataset", "READ"))
    approved = engine.evaluate(
        PolicyRequest("Strategy", "WRITE", {"environment": "paper"}, approved=True)
    )

    assert restricted.effect is PolicyEffect.RESTRICT
    assert restricted.rule_id == "early-restrict"
    assert condition_miss.effect is PolicyEffect.DENY
    assert resource_miss.reason_codes == ("POLICY_AS_CODE_DEFAULT_DENY",)
    assert approved.effect is PolicyEffect.ALLOW
    assert approved.reason_codes == (
        "POLICY_RULE:write-approval",
        "APPROVAL_RECORDED",
    )


def test_canonical_hard_blockers_fail_closed_and_live_candidates_block() -> None:
    assert tuple(blocker.value for blocker in HardBlockerCode) == (
        "DATA_UNAVAILABLE",
        "DATA_STALE",
        "DATA_INCONSISTENT",
        "DATA_QUALITY_FAILED",
        "CRITICAL_SECURITY_EVENT",
        "CRITICAL_NEWS_RISK",
        "CAPABILITY_UNVALIDATED",
        "OOS_NOT_VALIDATED",
        "STRATEGY_NOT_APPROVED",
        "GOVERNANCE_NOT_APPROVED",
        "LOOKAHEAD_DETECTED",
        "REPAINTING_DETECTED",
        "LIQUIDITY_INSUFFICIENT",
        "SPREAD_LIMIT_EXCEEDED",
        "SLIPPAGE_LIMIT_EXCEEDED",
        "EXCHANGE_INFO_UNAVAILABLE",
        "PRICE_FILTER_INVALID",
        "LOT_SIZE_INVALID",
        "NOTIONAL_INVALID",
        "BALANCE_UNKNOWN",
        "INSUFFICIENT_BALANCE",
        "INVENTORY_UNKNOWN",
        "DAILY_LOSS_LIMIT",
        "LOSS_CIRCUIT_BREAKER",
        "COOLDOWN_ACTIVE",
        "PORTFOLIO_LIMIT_EXCEEDED",
        "CONFLICTING_OPEN_ORDER",
        "UNAUTHORIZED_EXECUTION",
        "CRITICAL_POLICY_VIOLATION",
    )

    blocked = decision_result_for_hard_blockers(
        (HardBlockerCode.DATA_UNAVAILABLE,),
        live_candidate=False,
    )
    live_blocked = decision_result_for_hard_blockers(
        (HardBlockerCode.DATA_UNAVAILABLE,),
        live_candidate=True,
    )

    assert blocked.result == "NO_TRADE"
    assert live_blocked.result == "LIVE_ORDER_BLOCKED"
    assert live_blocked.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="fail-closed"):
        HardBlockerDecisionResult(
            blockers=(HardBlockerCode.DATA_UNAVAILABLE,),
            result="WAIT",
        )


def test_risk_control_set_is_canonical_and_separate_08_risk_domain() -> None:
    controls = build_risk_control_set()

    assert controls is not AI4BINANCE_RISK_CONTROL_SET
    assert controls.domain is CanonicalDomainId.RISK
    assert controls.controls == (
        RiskControlId.MAX_RISK_PER_TRADE,
        RiskControlId.MAX_TRADE_USDT,
        RiskControlId.DAILY_LOSS_LIMIT,
        RiskControlId.MAX_OPEN_POSITION_SIZE,
        RiskControlId.SPREAD_CAP,
        RiskControlId.SLIPPAGE_CAP,
        RiskControlId.MINIMUM_RR,
        RiskControlId.COOLDOWN,
        RiskControlId.REPEATED_LOSS_CIRCUIT_BREAKER,
        RiskControlId.INVENTORY_LIMIT,
        RiskControlId.CORRELATION_LIMIT,
    )
    assert controls.prohibited_practices == (
        ProhibitedRiskPractice.MARTINGALE,
        ProhibitedRiskPractice.UNCONTROLLED_AVERAGING_DOWN,
        ProhibitedRiskPractice.AUTOMATIC_RISK_INCREASE,
        ProhibitedRiskPractice.RISK_LIMIT_SELF_MODIFICATION,
    )
    with pytest.raises(ValueError, match="08_RISK"):
        RiskControlSet(domain=CanonicalDomainId.DECISION)


def test_risk_assessment_contract_enforces_fail_closed_result_semantics() -> None:
    assessment = RiskAssessmentContract(
        risk_assessment_id="risk-1",
        cycle_id="cycle-1",
        decision_id="decision-1",
        market_risk=RiskState.LOW,
        liquidity_risk=RiskState.LOW,
        volatility_risk=RiskState.MEDIUM,
        execution_risk=RiskState.LOW,
        strategy_risk=RiskState.LOW,
        evidence_risk=RiskState.LOW,
        portfolio_risk=RiskState.MEDIUM,
        governance_risk=RiskState.LOW,
        result=RiskAssessmentResult.RESTRICT,
        model_risk=RiskState.UNKNOWN,
        risk_budget_usdt=Decimal("10"),
        max_loss_usdt=Decimal("5"),
        risk_reward=Decimal("2"),
        blockers=("PORTFOLIO_RISK_RESTRICTED",),
    )

    assert assessment.domain is CanonicalDomainId.RISK
    assert assessment.result is RiskAssessmentResult.RESTRICT
    assert assessment.decision_id == "decision-1"
    with pytest.raises(ValueError, match="PASS risk assessment"):
        RiskAssessmentContract(
            risk_assessment_id="risk-pass-blocked",
            cycle_id="cycle-1",
            decision_id="decision-1",
            market_risk=RiskState.LOW,
            liquidity_risk=RiskState.LOW,
            volatility_risk=RiskState.LOW,
            execution_risk=RiskState.LOW,
            strategy_risk=RiskState.LOW,
            evidence_risk=RiskState.LOW,
            portfolio_risk=RiskState.LOW,
            governance_risk=RiskState.LOW,
            result=RiskAssessmentResult.PASS,
            blockers=("BLOCKER",),
        )
    with pytest.raises(ValueError, match="unknown or critical"):
        RiskAssessmentContract(
            risk_assessment_id="risk-pass-unknown",
            cycle_id="cycle-1",
            decision_id="decision-1",
            market_risk=RiskState.UNKNOWN,
            liquidity_risk=RiskState.LOW,
            volatility_risk=RiskState.LOW,
            execution_risk=RiskState.LOW,
            strategy_risk=RiskState.LOW,
            evidence_risk=RiskState.LOW,
            portfolio_risk=RiskState.LOW,
            governance_risk=RiskState.LOW,
            result=RiskAssessmentResult.PASS,
        )
    with pytest.raises(ValueError, match="requires blockers"):
        RiskAssessmentContract(
            risk_assessment_id="risk-block-empty",
            cycle_id="cycle-1",
            decision_id="decision-1",
            market_risk=RiskState.LOW,
            liquidity_risk=RiskState.LOW,
            volatility_risk=RiskState.LOW,
            execution_risk=RiskState.LOW,
            strategy_risk=RiskState.LOW,
            evidence_risk=RiskState.LOW,
            portfolio_risk=RiskState.LOW,
            governance_risk=RiskState.LOW,
            result=RiskAssessmentResult.BLOCK,
        )


def test_portfolio_state_is_separate_and_not_backtest_consumable() -> None:
    portfolio = PortfolioStateContract(
        portfolio_state_id="portfolio-1",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        observed_at=NOW,
    )

    assert portfolio.domain is CanonicalDomainId.PORTFOLIO
    assert portfolio.components == (
        PortfolioStateComponent.SPOT_BALANCES,
        PortfolioStateComponent.FUTURES_BALANCES,
        PortfolioStateComponent.INVENTORY,
        PortfolioStateComponent.POSITIONS,
        PortfolioStateComponent.OPEN_ORDERS,
        PortfolioStateComponent.EXPOSURE,
        PortfolioStateComponent.CORRELATION,
        PortfolioStateComponent.RISK_BUDGET,
    )
    assert portfolio.historical_backtest_consumable is False
    with pytest.raises(ValueError, match="Historical Backtest"):
        PortfolioStateContract(
            portfolio_state_id="portfolio-live",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            observed_at=NOW,
            historical_backtest_consumable=True,
        )
    with pytest.raises(ValueError, match="09_PORTFOLIO"):
        PortfolioStateContract(
            portfolio_state_id="portfolio-wrong-domain",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            observed_at=NOW,
            domain=CanonicalDomainId.DECISION,
        )


def test_execution_gate_contract_blocks_single_live_gate_failure() -> None:
    checks = MappingProxyType(
        dict.fromkeys(ExecutionGateCheckId, True) | {ExecutionGateCheckId.OOS: False}
    )
    result = build_execution_gate_result(
        "gate-1",
        "decision-1",
        ExecutionMode.LIVE,
        checks,
    )

    assert tuple(mode.value for mode in ExecutionMode) == (
        "manual",
        "dry_run",
        "paper",
        "auto",
        "live",
    )
    assert result.accepted is False
    assert result.execution_allowed is False
    assert result.blockers == ("OOS == PASS",)
    assert result.mode is ExecutionMode.LIVE
    with pytest.raises(ValueError, match="block execution"):
        ExecutionGateResult(
            gate_result_id="bad-gate",
            decision_id="decision-1",
            mode=ExecutionMode.LIVE,
            checks=checks,
            accepted=False,
            blockers=("OOS == PASS",),
            execution_allowed=True,
        )


def test_execution_route_forbids_direct_agent_to_live_order_path() -> None:
    assert CANONICAL_EXECUTION_ROUTE == (
        ExecutionRouteStep.AGENT_OBSERVATION,
        ExecutionRouteStep.DETERMINISTIC_CORE,
        ExecutionRouteStep.RISK_ASSESSMENT,
        ExecutionRouteStep.VALIDATION,
        ExecutionRouteStep.DECISION_GOVERNANCE,
        ExecutionRouteStep.EXECUTION_GATE,
        ExecutionRouteStep.EXECUTION,
    )
    assert "Agent" not in tuple(step.value for step in CANONICAL_EXECUTION_ROUTE)
    assert "LiveOrder" not in tuple(step.value for step in CANONICAL_EXECUTION_ROUTE)


def test_trailing_stop_rule_is_monotonic_1_5_atr_and_reviews_closure_context() -> None:
    rule = build_trailing_stop_rule_contract()

    assert rule is not AI4BINANCE_TRAILING_STOP_RULE
    assert rule.domain is CanonicalDomainId.EXECUTION
    assert rule.direction is TrailingStopDirection.LONG
    assert rule.trailing_multiplier == Decimal("1.5")
    assert rule.monotonic is True
    assert rule.trigger is TrailingStopTrigger.TRAILING_STOP_EXIT
    assert rule.closure_review_dimensions == (
        ClosureReviewDimension.TIGHTNESS,
        ClosureReviewDimension.VOLATILITY_EXPANSION,
        ClosureReviewDimension.HTF_WEAKNESS,
        ClosureReviewDimension.IGNORED_STRUCTURE_BREAK,
        ClosureReviewDimension.STAGED_EXIT_ALTERNATIVE,
    )
    with pytest.raises(ValueError, match=r"1\.5 ATR"):
        TrailingStopRuleContract(trailing_multiplier=Decimal("2"))
    with pytest.raises(ValueError, match="never move down"):
        TrailingStopRuleContract(monotonic=False)


def test_validation_domain_is_capability_first_and_canonical() -> None:
    validation = build_validation_domain_contract()

    assert validation is not AI4BINANCE_VALIDATION_DOMAIN
    assert validation.domain is CanonicalDomainId.VALIDATION
    assert validation.capability_first is True
    assert validation.stages == (
        ValidationStage.UNIT_TESTS,
        ValidationStage.FORMULA_ORACLE_TEST,
        ValidationStage.REGRESSION_TESTS,
        ValidationStage.BACKTEST,
        ValidationStage.TRAIN_TEST,
        ValidationStage.WALK_FORWARD,
        ValidationStage.OOS,
        ValidationStage.MONTE_CARLO,
        ValidationStage.SENSITIVITY,
        ValidationStage.REGIME_TESTS,
        ValidationStage.SLIPPAGE_ROBUSTNESS,
        ValidationStage.FEE_ROBUSTNESS,
        ValidationStage.MULTIPLE_TESTING_CONTROL,
        ValidationStage.PROMOTION_REVIEW,
    )
    with pytest.raises(ValueError, match="capability-first"):
        ValidationDomainContract(capability_first=False)


def test_oracle_definition_links_expected_behavior_to_capability() -> None:
    oracle = OracleDefinition(
        oracle_id="oracle:structure:BOS:1",
        capability_id="BOS",
        expected_behavior="Detect break of prior swing high after confirmed structure.",
        version="1",
        reference_cases=("bullish_break_after_swing_confirmation",),
        edge_cases=("equal_high_no_break",),
        invalid_cases=("future_candle_required",),
    )

    assert oracle.domain is CanonicalDomainId.VALIDATION
    assert oracle.expected_behavior.startswith("Detect break")
    with pytest.raises(ValueError, match="expected_behavior"):
        OracleDefinition(
            oracle_id="oracle:structure:BOS:bad",
            capability_id="BOS",
            expected_behavior=" ",
            version="1",
        )
    with pytest.raises(ValueError, match="unique"):
        OracleDefinition(
            oracle_id="oracle:structure:BOS:dup",
            capability_id="BOS",
            expected_behavior="Expected behavior.",
            version="1",
            reference_cases=("same", "same"),
        )


def test_capability_validation_matrix_requires_full_chain_before_promotion() -> None:
    incomplete = CapabilityValidationMatrix(
        capability_id="BOS",
        formula_id="formula:structure:BOS:1",
        oracle_id="oracle:structure:BOS:1",
        validation_profile_id="validation:structure:BOS:1",
        stage_status=tuple(
            (stage, ValidationEvidenceStatus.PASS)
            if stage is not ValidationStage.OOS
            else (stage, ValidationEvidenceStatus.MISSING)
            for stage in ValidationStage
        ),
        regime_evidence_ids=("regime:trend",),
    )
    complete = CapabilityValidationMatrix(
        capability_id="BOS",
        formula_id="formula:structure:BOS:1",
        oracle_id="oracle:structure:BOS:1",
        validation_profile_id="validation:structure:BOS:1",
        stage_status=tuple(
            (stage, ValidationEvidenceStatus.PASS) for stage in ValidationStage
        ),
        regime_evidence_ids=("regime:trend", "regime:range"),
        promotion_eligible=True,
    )

    assert incomplete.evidence_complete is False
    assert "CAPABILITY_VALIDATION_OOS_MISSING" in incomplete.blockers
    assert complete.evidence_complete is True
    with pytest.raises(ValueError, match="complete capability validation"):
        CapabilityValidationMatrix(
            capability_id="BOS",
            formula_id="formula:structure:BOS:1",
            oracle_id="oracle:structure:BOS:1",
            validation_profile_id="validation:structure:BOS:1",
            stage_status=incomplete.stage_status,
            regime_evidence_ids=("regime:trend",),
            promotion_eligible=True,
        )
    with pytest.raises(ValueError, match="11_VALIDATION"):
        CapabilityValidationMatrix(
            capability_id="BOS",
            formula_id="formula:structure:BOS:1",
            oracle_id="oracle:structure:BOS:1",
            validation_profile_id="validation:structure:BOS:1",
            stage_status=incomplete.stage_status[:-1],
        )


def test_controlled_learning_contract_is_research_only_and_lifecycle_bound() -> None:
    learning = build_controlled_learning_contract()

    assert learning is not AI4BINANCE_CONTROLLED_LEARNING
    assert learning.domain is CanonicalDomainId.LEARNING
    assert learning.allowed_actions == (
        ControlledLearningAllowedAction.OBSERVE,
        ControlledLearningAllowedAction.DETECT_RECURRING_FAILURE,
        ControlledLearningAllowedAction.CLASSIFY,
        ControlledLearningAllowedAction.GENERATE_HYPOTHESIS,
        ControlledLearningAllowedAction.PROPOSE_CANDIDATE,
        ControlledLearningAllowedAction.RANK_CANDIDATE,
        ControlledLearningAllowedAction.STAGE_RESEARCH,
    )
    assert learning.prohibited_actions == (
        ControlledLearningProhibitedAction.DEPLOY,
        ControlledLearningProhibitedAction.PROMOTE,
        ControlledLearningProhibitedAction.MODIFY_LIVE_PARAMETER,
        ControlledLearningProhibitedAction.MODIFY_RISK_LIMIT,
        ControlledLearningProhibitedAction.DISABLE_GATE,
        ControlledLearningProhibitedAction.ENABLE_LIVE,
        ControlledLearningProhibitedAction.CHANGE_AUTHORITY,
    )
    assert learning.lifecycle == (
        ControlledLearningLifecycleStep.OUTCOME,
        ControlledLearningLifecycleStep.CLOSURE_REVIEW,
        ControlledLearningLifecycleStep.LESSON,
        ControlledLearningLifecycleStep.HYPOTHESIS,
        ControlledLearningLifecycleStep.LEARNING_CANDIDATE,
        ControlledLearningLifecycleStep.GOVERNANCE_INTAKE,
        ControlledLearningLifecycleStep.RESEARCH_UNIT,
        ControlledLearningLifecycleStep.VALIDATION,
        ControlledLearningLifecycleStep.PROMOTION_REVIEW,
    )
    assert learning.execution_allowed is False
    assert learning.promotion_allowed is False
    assert learning.authority_change_allowed is False
    assert learning.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="12_LEARNING"):
        ControlledLearningContract(domain=CanonicalDomainId.EXECUTION)
    with pytest.raises(ValueError, match="cannot execute"):
        ControlledLearningContract(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot enable live"):
        ControlledLearningContract(live_eligibility_status="LIVE_ELIGIBLE")


def test_governance_primitive_catalog_is_canonical_13_governance() -> None:
    catalog = build_governance_primitive_catalog()

    assert catalog is not AI4BINANCE_GOVERNANCE_PRIMITIVES
    assert catalog.domain is CanonicalDomainId.GOVERNANCE
    assert catalog.primitives == (
        GovernancePrimitive.GOVERNANCE_REGISTRY,
        GovernancePrimitive.GOVERNANCE_INTAKE,
        GovernancePrimitive.GOVERNANCE_DEFINITION_OF_READY,
        GovernancePrimitive.RISK_CRITICALITY_TIER,
        GovernancePrimitive.COMPONENT_CONTRACT,
        GovernancePrimitive.AUTHORITY_MODEL,
        GovernancePrimitive.POLICY_AS_CODE,
        GovernancePrimitive.RUNTIME_POLICY_ENFORCEMENT,
        GovernancePrimitive.INDEPENDENT_VALIDATION,
        GovernancePrimitive.GOVERNANCE_DEFINITION_OF_DONE,
        GovernancePrimitive.GOVERNANCE_RELEASE_RECORD,
        GovernancePrimitive.APPROVED_OPERATING_ENVELOPE,
        GovernancePrimitive.CONTINUOUS_ASSURANCE,
        GovernancePrimitive.GOVERNANCE_REVALIDATION,
        GovernancePrimitive.DECISION_LINEAGE,
        GovernancePrimitive.RISK_BASED_ESCALATION,
        GovernancePrimitive.INCIDENT_MANAGEMENT,
        GovernancePrimitive.PROBLEM_MANAGEMENT,
        GovernancePrimitive.KILL_SWITCH,
        GovernancePrimitive.SAFE_STATE,
        GovernancePrimitive.COMPONENT_RETIREMENT,
    )
    assert tuple(tier.value for tier in RiskCriticalityTier) == (
        "LOW",
        "MEDIUM",
        "HIGH",
        "TRADING_IMPACTING",
        "LIVE_CRITICAL",
    )

    with pytest.raises(ValueError, match="13_GOVERNANCE"):
        GovernancePrimitiveCatalog(domain=CanonicalDomainId.LEARNING)
    with pytest.raises(ValueError, match="canonical"):
        GovernancePrimitiveCatalog(
            primitives=tuple(GovernancePrimitive)[:-1],
        )


def test_governance_definition_of_ready_requires_all_pre_development_inputs() -> None:
    ready = GovernanceDefinitionOfReady(component_id="component-1")

    assert ready.domain is CanonicalDomainId.GOVERNANCE
    assert ready.criteria == tuple(GovernanceReadyCriterion)
    assert ready.ready is True

    with pytest.raises(ValueError, match="ready"):
        GovernanceDefinitionOfReady(component_id="component-1", ready=False)
    with pytest.raises(ValueError, match="every criterion"):
        GovernanceDefinitionOfReady(
            component_id="component-1",
            criteria=tuple(GovernanceReadyCriterion)[:-1],
        )
    with pytest.raises(ValueError, match="13_GOVERNANCE"):
        GovernanceDefinitionOfReady(
            component_id="component-1",
            domain=CanonicalDomainId.VALIDATION,
        )


def test_governance_definition_of_done_enforces_extra_trading_validation() -> None:
    done = GovernanceDefinitionOfDone(component_id="component-1")
    trading_done = GovernanceDefinitionOfDone(
        component_id="component-2",
        trading_impacting=True,
        trading_impacting_criteria=tuple(TradingImpactingDoneCriterion),
    )

    assert done.criteria == tuple(GovernanceDoneCriterion)
    assert done.trading_impacting_criteria == ()
    assert trading_done.trading_impacting_criteria == tuple(
        TradingImpactingDoneCriterion
    )

    with pytest.raises(ValueError, match="validation PASS"):
        GovernanceDefinitionOfDone(
            component_id="component-2",
            trading_impacting=True,
        )
    with pytest.raises(ValueError, match="cannot claim trading gates"):
        GovernanceDefinitionOfDone(
            component_id="component-2",
            trading_impacting_criteria=tuple(TradingImpactingDoneCriterion),
        )
    with pytest.raises(ValueError, match="minimum criteria"):
        GovernanceDefinitionOfDone(
            component_id="component-2",
            criteria=tuple(GovernanceDoneCriterion)[:-1],
        )


def test_approved_operating_envelope_bounds_default_spot_paper_authority() -> None:
    envelope = build_approved_operating_envelope()

    assert envelope is not AI4BINANCE_APPROVED_OPERATING_ENVELOPE
    assert envelope.domain is CanonicalDomainId.GOVERNANCE
    assert envelope.exchange == ("Binance",)
    assert envelope.markets == ("Spot",)
    assert envelope.universe_policy_id == "policy:universe:binance-spot-default:1"
    assert envelope.timeframes == ("5m", "15m", "1h", "4h", "1d")
    assert envelope.risk_policy_id == "policy:risk:spot-paper-default:1"
    assert (
        envelope.minimum_data_quality_profile_id == "dq:binance-spot-ohlcv-standard:1"
    )
    assert envelope.execution.default is ExecutionMode.PAPER
    assert envelope.execution.auto_live is False
    assert envelope.grants_authority_outside_envelope is False
    assert envelope.restrictions == (
        "paper_default",
        "manual_execution",
        "no_auto_live",
    )

    with pytest.raises(ValueError, match="Binance"):
        ApprovedOperatingEnvelope(
            envelope_id="envelope-1",
            universe_policy_id="universe-1",
            risk_policy_id="risk-1",
            minimum_data_quality_profile_id="dq-1",
            exchange=("OtherExchange",),
        )
    with pytest.raises(ValueError, match="Spot"):
        ApprovedOperatingEnvelope(
            envelope_id="envelope-1",
            universe_policy_id="universe-1",
            risk_policy_id="risk-1",
            minimum_data_quality_profile_id="dq-1",
            markets=("Futures",),
        )
    with pytest.raises(ValueError, match="timeframes"):
        ApprovedOperatingEnvelope(
            envelope_id="envelope-1",
            universe_policy_id="universe-1",
            risk_policy_id="risk-1",
            minimum_data_quality_profile_id="dq-1",
            timeframes=("1h",),
        )
    with pytest.raises(ValueError, match="auto live"):
        ApprovedOperatingEnvelopeExecution(auto_live=True)
    with pytest.raises(ValueError, match="default execution is paper"):
        ApprovedOperatingEnvelopeExecution(default=ExecutionMode.LIVE)
    with pytest.raises(ValueError, match="outside approved envelope"):
        ApprovedOperatingEnvelope(
            envelope_id="envelope-1",
            universe_policy_id="universe-1",
            risk_policy_id="risk-1",
            minimum_data_quality_profile_id="dq-1",
            grants_authority_outside_envelope=True,
        )


def test_safe_state_is_deny_no_execution_and_requires_revalidation() -> None:
    safe_state = build_safe_state()

    assert safe_state is not AI4BINANCE_SAFE_STATE
    assert safe_state.domain is CanonicalDomainId.GOVERNANCE
    assert safe_state.actions == (
        SafeStateAction.NO_NEW_TRADE,
        SafeStateAction.NO_LIVE_EXECUTION,
        SafeStateAction.PRESERVE_STATE,
        SafeStateAction.CONTINUE_MONITORING,
        SafeStateAction.WRITE_INCIDENT,
        SafeStateAction.REQUIRE_REVALIDATION,
    )
    assert safe_state.decision_result == "DENY"
    assert safe_state.execution_allowed is False
    assert safe_state.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="every required action"):
        SafeState(actions=tuple(SafeStateAction)[:-1])
    with pytest.raises(ValueError, match="must DENY"):
        SafeState(decision_result="RESTRICT")
    with pytest.raises(ValueError, match="cannot allow execution"):
        SafeState(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot unblock live execution"):
        SafeState(live_eligibility_status="READY")


def test_continuous_assurance_engine_covers_all_domains_and_denies_unknown() -> None:
    engine = build_continuous_assurance_engine()

    assert engine is not AI4BINANCE_CONTINUOUS_ASSURANCE_ENGINE
    assert engine.domain is CanonicalDomainId.GOVERNANCE
    assert engine.domains == (
        ContinuousAssuranceDomain.DATA_ASSURANCE,
        ContinuousAssuranceDomain.CAPABILITY_ASSURANCE,
        ContinuousAssuranceDomain.STRATEGY_ASSURANCE,
        ContinuousAssuranceDomain.PERFORMANCE_ASSURANCE,
        ContinuousAssuranceDomain.RISK_ASSURANCE,
        ContinuousAssuranceDomain.OPERATIONAL_ASSURANCE,
        ContinuousAssuranceDomain.EVIDENCE_ASSURANCE,
        ContinuousAssuranceDomain.SECURITY_ASSURANCE,
        ContinuousAssuranceDomain.GOVERNANCE_REVALIDATION,
    )
    assert engine.possible_states == (
        ContinuousAssuranceState.CONTINUE,
        ContinuousAssuranceState.RESTRICT,
        ContinuousAssuranceState.QUARANTINE,
        ContinuousAssuranceState.SUSPEND,
        ContinuousAssuranceState.WITHDRAW,
        ContinuousAssuranceState.DENY,
    )
    assert engine.unknown_critical_state is ContinuousAssuranceState.DENY
    assert engine.safe_state.actions == tuple(SafeStateAction)
    assert engine.execution_allowed is False
    assert engine.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="domains must be canonical"):
        ContinuousAssuranceEngine(
            domains=tuple(ContinuousAssuranceDomain)[:-1],
        )
    with pytest.raises(ValueError, match="states must be canonical"):
        ContinuousAssuranceEngine(
            possible_states=tuple(ContinuousAssuranceState)[:-1],
        )
    with pytest.raises(ValueError, match="must DENY"):
        ContinuousAssuranceEngine(
            unknown_critical_state=ContinuousAssuranceState.SUSPEND,
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        ContinuousAssuranceEngine(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot unblock live execution"):
        ContinuousAssuranceEngine(live_eligibility_status="READY")


def test_web_intelligence_radar_is_research_only_and_evidence_first() -> None:
    radar = build_web_intelligence_radar_contract()

    assert radar is not AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT
    assert radar.domain is CanonicalDomainId.INTELLIGENCE
    assert ExternalIntelligenceSource.GITHUB in radar.source_types
    assert ExternalIntelligenceSource.NEWS in radar.source_types
    assert ExternalIntelligenceSource.SECURITY in radar.source_types
    assert ExternalIntelligenceSource.RESEARCH in radar.source_types
    assert radar.evidence_pipeline == tuple(EvidenceFabricStage)
    assert "EvidencePack" in radar.required_outputs
    assert "MAP_TO_CAPABILITY_GAP" in radar.allowed_actions
    assert "EXECUTE_ORDER" in radar.prohibited_actions
    assert radar.credentialless_default is True
    assert radar.decision_authority == "ADVISORY_ONLY"
    assert radar.execution_allowed is False
    assert radar.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="news, GitHub, security, research"):
        WebIntelligenceRadarContract(
            source_types=(ExternalIntelligenceSource.GITHUB,),
        )
    with pytest.raises(ValueError, match="EvidencePack"):
        WebIntelligenceRadarContract(
            required_outputs=("RadarFinding",),
        )
    with pytest.raises(ValueError, match="advisory-only"):
        WebIntelligenceRadarContract(decision_authority="FINAL_DECISION")
    with pytest.raises(ValueError, match="cannot authorize execution"):
        WebIntelligenceRadarContract(execution_allowed=True)


def test_loops_self_improvement_contract_uses_web_radar_without_self_promotion() -> (
    None
):
    contract = build_loops_self_improvement_contract()

    assert contract is not AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT
    assert contract.domain is CanonicalDomainId.LEARNING
    assert tuple(step.stage for step in contract.steps) == (
        LoopsStage.LISTEN,
        LoopsStage.OBSERVE,
        LoopsStage.ORIENT,
        LoopsStage.PROVE,
        LoopsStage.STAGE,
    )
    assert "WebIntelligenceRadar" in contract.lifecycle_chain
    assert contract.web_intelligence_radar.decision_authority == "ADVISORY_ONLY"
    assert "REQUEST_VALIDATION" in contract.allowed_actions
    assert "SELF_PROMOTE" in contract.prohibited_actions
    assert contract.execution_allowed is False
    assert contract.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="canonical and ordered"):
        LoopsSelfImprovementContract(steps=contract.steps[:-1])
    with pytest.raises(ValueError, match="RESEARCH_ONLY"):
        LoopsStep(
            LoopsStage.LISTEN,
            "Bad step.",
            ("Outcome",),
            ("Lesson",),
            ("Evidence",),
            authority_boundary="DEPLOY",
        )
    with pytest.raises(ValueError, match="WebIntelligenceRadar"):
        LoopsSelfImprovementContract(
            lifecycle_chain=("Outcome", "Lesson"),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        LoopsSelfImprovementContract(execution_allowed=True)


def test_digital_company_operating_model_has_pyramid_and_fail_closed_loops() -> None:
    model = build_digital_company_operating_model()

    assert model is not AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL
    assert model.domain is CanonicalDomainId.GOVERNANCE
    assert tuple(layer.level for layer in model.pyramid) == tuple(
        GovernancePyramidLevel
    )
    assert model.pyramid[0].authority_holder == "Human Owner / Board"
    assert model.pyramid[-1].authority_holder == "Audit, Assurance and Learning"
    assert "no profit guarantee" in model.profitability_statement.lower()
    assert any("NO_TRADE" in item for item in model.operating_principles)
    assert model.loops_contract.web_intelligence_radar.credentialless_default is True
    assert model.loops_contract.execution_allowed is False
    assert model.execution_allowed is False
    assert model.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="no profit guarantee"):
        DigitalCompanyOperatingModel(
            pyramid=model.pyramid,
            profitability_statement="Targets continuous profit.",
        )
    with pytest.raises(ValueError, match="pyramid"):
        DigitalCompanyOperatingModel(pyramid=model.pyramid[:-1])
    with pytest.raises(ValueError, match="NO_TRADE"):
        DigitalCompanyOperatingModel(
            pyramid=model.pyramid,
            operating_principles=("Transparent lineage.",),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        DigitalCompanyOperatingModel(
            pyramid=model.pyramid,
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="responsibilities"):
        GovernancePyramidLayer(
            GovernancePyramidLevel.HUMAN_BOARD,
            "Human",
            (),
            ("EXECUTE_WITHOUT_APPROVAL",),
            ("approval_record",),
        )


def test_governance_release_record_is_audit_only_and_fail_closed() -> None:
    release = GovernanceReleaseRecord(
        grr_id="grr-1",
        component_id="component-1",
        component_version="1",
        environment=GovernanceReleaseEnvironment.PAPER,
        operating_envelope_id="envelope-1",
        approval=GovernanceApproval(GovernanceApprovalStatus.RESTRICTED, "RiskOwner"),
        approved_at=NOW,
        capability_ids=("BOS",),
        validation_artifact_ids=("validation:BOS:1",),
        restrictions=("paper_only",),
    )

    assert tuple(environment.value for environment in GovernanceReleaseEnvironment) == (
        "research",
        "backtest",
        "paper",
        "live",
    )
    assert release.domain is CanonicalDomainId.GOVERNANCE
    assert release.rollback_ready is True
    assert release.execution_allowed is False
    assert release.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    with pytest.raises(ValueError, match="rollback"):
        GovernanceReleaseRecord(
            grr_id="grr-rollback",
            component_id="component-1",
            component_version="1",
            environment=GovernanceReleaseEnvironment.PAPER,
            operating_envelope_id="envelope-1",
            approval=GovernanceApproval(GovernanceApprovalStatus.APPROVED, "Owner"),
            approved_at=NOW,
            rollback_ready=False,
        )
    with pytest.raises(ValueError, match="RESTRICTED"):
        GovernanceReleaseRecord(
            grr_id="grr-restricted",
            component_id="component-1",
            component_version="1",
            environment=GovernanceReleaseEnvironment.PAPER,
            operating_envelope_id="envelope-1",
            approval=GovernanceApproval(GovernanceApprovalStatus.RESTRICTED, "Owner"),
            approved_at=NOW,
        )
    with pytest.raises(ValueError, match="APPROVED"):
        GovernanceReleaseRecord(
            grr_id="grr-approved-restricted",
            component_id="component-1",
            component_version="1",
            environment=GovernanceReleaseEnvironment.PAPER,
            operating_envelope_id="envelope-1",
            approval=GovernanceApproval(GovernanceApprovalStatus.APPROVED, "Owner"),
            approved_at=NOW,
            restrictions=("paper_only",),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        GovernanceReleaseRecord(
            grr_id="grr-execution",
            component_id="component-1",
            component_version="1",
            environment=GovernanceReleaseEnvironment.PAPER,
            operating_envelope_id="envelope-1",
            approval=GovernanceApproval(GovernanceApprovalStatus.APPROVED, "Owner"),
            approved_at=NOW,
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot unblock live execution"):
        GovernanceReleaseRecord(
            grr_id="grr-live",
            component_id="component-1",
            component_version="1",
            environment=GovernanceReleaseEnvironment.LIVE,
            operating_envelope_id="envelope-1",
            approval=GovernanceApproval(GovernanceApprovalStatus.APPROVED, "Owner"),
            approved_at=NOW,
            live_eligibility_status="READY",
        )


def test_policy_as_code_rejects_live_trading_authority_allow_rules() -> None:
    with pytest.raises(ValueError, match="trading authority"):
        PolicyAsCodeRule(
            rule_id="bad-live",
            effect=PolicyEffect.ALLOW,
            resource_types=("Execution",),
            actions=("EXECUTE_ORDER",),
        )
    with pytest.raises(ValueError, match="default must deny"):
        PolicyAsCodeDocument(
            policy_id="bad",
            version="1",
            default_effect=PolicyEffect.ALLOW,
        )

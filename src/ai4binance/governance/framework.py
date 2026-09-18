"""Canonical governance registry and engineering concept contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

CANONICAL_DEFAULT_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
ZERO_DECIMAL = Decimal("0")
DEFAULT_TRAILING_MULTIPLIER = Decimal("1.5")


@dataclass(frozen=True, slots=True)
class CoreMeta:
    schema_version: str = "2.0.0"
    platform: str = "AI4Binance EnterpriseAI vNext"
    environment: str = "paper"
    exchange: str = "Binance"
    default_market: str = "spot"
    default_symbol: str = "HOTUSDT"
    default_timeframes: tuple[str, ...] = CANONICAL_DEFAULT_TIMEFRAMES
    trading_mode: str = "paper"
    execution_order_mode: str = "manual"
    allow_auto_live_orders: bool = False
    fail_policy: str = "NO_TRADE"
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        if self.schema_version != "2.0.0":
            raise ValueError("core meta schema_version must remain 2.0.0")
        if self.platform != "AI4Binance EnterpriseAI vNext":
            raise ValueError("core meta platform drift is not allowed")
        if self.environment != "paper" or self.trading_mode != "paper":
            raise ValueError("core meta defaults must keep paper environment")
        if self.exchange != "Binance":
            raise ValueError("core meta exchange must be Binance")
        if self.default_market != "spot":
            raise ValueError("core meta default_market must be spot")
        if self.default_symbol != "HOTUSDT":
            raise ValueError("core meta default_symbol must be HOTUSDT")
        if self.default_timeframes != CANONICAL_DEFAULT_TIMEFRAMES:
            raise ValueError("core meta default_timeframes must be canonical")
        if self.execution_order_mode != "manual":
            raise ValueError("core meta execution_order_mode must be manual")
        if self.allow_auto_live_orders:
            raise ValueError("core meta must not allow automatic live orders")
        if self.fail_policy != "NO_TRADE":
            raise ValueError("core meta fail_policy must be NO_TRADE")
        if self.timezone != "UTC":
            raise ValueError("core meta timestamps must use UTC timezone")


class CoreConstitutionRuleId(StrEnum):
    C01 = "C01"
    C02 = "C02"
    C03 = "C03"
    C04 = "C04"
    C05 = "C05"
    C06 = "C06"
    C07 = "C07"
    C08 = "C08"
    C09 = "C09"
    C10 = "C10"
    C11 = "C11"
    C12 = "C12"
    C13 = "C13"
    C14 = "C14"
    C15 = "C15"
    C16 = "C16"
    C17 = "C17"
    C18 = "C18"
    C19 = "C19"
    C20 = "C20"
    C21 = "C21"
    C22 = "C22"
    C23 = "C23"
    C24 = "C24"
    C25 = "C25"


class CanonicalCycleStep(StrEnum):
    ONE_CYCLE = "ONE_CYCLE"
    ONE_CANONICAL_SNAPSHOT = "ONE_CANONICAL_SNAPSHOT"
    ONE_SHARED_STATE = "ONE_SHARED_STATE"
    MANY_BOUNDED_OBSERVATIONS = "MANY_BOUNDED_OBSERVATIONS"
    ONE_DETERMINISTIC_DECISION = "ONE_DETERMINISTIC_DECISION"
    ONE_RISK_ASSESSMENT = "ONE_RISK_ASSESSMENT"
    ONE_GOVERNANCE_RESULT = "ONE_GOVERNANCE_RESULT"
    ZERO_OR_ONE_EXECUTION_PLAN = "ZERO_OR_ONE_EXECUTION_PLAN"
    ONE_AUDIT_TRAIL = "ONE_AUDIT_TRAIL"


class CoreAuthorityOwner(StrEnum):
    DATA = "DATA"
    FEATURES = "FEATURES"
    EVIDENCE = "EVIDENCE"
    AGENTS = "AGENTS"
    STRATEGIES = "STRATEGIES"
    DETERMINISTIC_CORE = "DETERMINISTIC_CORE"
    RISK = "RISK"
    GOVERNANCE = "GOVERNANCE"
    EXECUTION = "EXECUTION"
    AUDIT = "AUDIT"
    HUMAN = "HUMAN"
    LEARNING = "LEARNING"
    VALIDATION = "VALIDATION"


@dataclass(frozen=True, slots=True)
class CoreConstitutionRule:
    rule_id: CoreConstitutionRuleId
    statement: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("constitution rule statement cannot be empty")


class ChangeApprovalClass(StrEnum):
    C0_NON_BEHAVIORAL = "C0_NON_BEHAVIORAL"
    C1_LOW_RISK = "C1_LOW_RISK"
    C2_BEHAVIORAL = "C2_BEHAVIORAL"
    C3_GOVERNED = "C3_GOVERNED"
    C4_CONSEQUENTIAL = "C4_CONSEQUENTIAL"


@dataclass(frozen=True, slots=True)
class ConstitutionalChangeControl:
    control_id: str = "AI4BINANCE-CONSTITUTIONAL-CHANGE-CONTROL"
    version: str = "3.0.0"
    code_runs_within_constitution: bool = True
    quality_gate_role: str = "TECHNICAL_TRUTH"
    governance_gate_role: str = "POLICY_ELIGIBILITY"
    human_governance_role: str = "CONSEQUENTIAL_AUTHORITY"
    risk_tiered_human_governance: bool = True
    change_classes: tuple[ChangeApprovalClass, ...] = tuple(ChangeApprovalClass)
    change_classes_without_human_governance: tuple[ChangeApprovalClass, ...] = (
        ChangeApprovalClass.C0_NON_BEHAVIORAL,
        ChangeApprovalClass.C1_LOW_RISK,
    )
    approval_packet_required_change_classes: tuple[ChangeApprovalClass, ...] = (
        ChangeApprovalClass.C2_BEHAVIORAL,
        ChangeApprovalClass.C3_GOVERNED,
        ChangeApprovalClass.C4_CONSEQUENTIAL,
    )
    constitution_sync_change_classes: tuple[ChangeApprovalClass, ...] = (
        ChangeApprovalClass.C3_GOVERNED,
        ChangeApprovalClass.C4_CONSEQUENTIAL,
    )
    double_approval_change_classes: tuple[ChangeApprovalClass, ...] = (
        ChangeApprovalClass.C3_GOVERNED,
    )
    high_assurance_change_classes: tuple[ChangeApprovalClass, ...] = (
        ChangeApprovalClass.C4_CONSEQUENTIAL,
    )
    auto_revision_targets: tuple[str, ...] = (
        "policy",
        "instructions",
        "schema",
        "entity_rules",
        "relationship_rules",
        "output_format",
        "framework_docs",
    )
    required_eli10_sections: tuple[str, ...] = (
        "system_effect",
        "benefits",
        "risks",
        "affected_contracts",
        "validation_plan",
        "rollback_or_stop_condition",
        "live_eligibility_status",
    )
    constitution_sync_required: bool = True
    code_constitution_divergence_allowed: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("constitutional change control_id", self.control_id)
        _require_non_empty("constitutional change control version", self.version)
        _require_unique(
            "constitutional change classes",
            tuple(change_class.value for change_class in self.change_classes),
        )
        _require_unique(
            "change classes without human governance",
            tuple(
                change_class.value
                for change_class in self.change_classes_without_human_governance
            ),
        )
        _require_unique(
            "approval packet change classes",
            tuple(
                change_class.value
                for change_class in self.approval_packet_required_change_classes
            ),
        )
        _require_unique(
            "constitution sync change classes",
            tuple(
                change_class.value
                for change_class in self.constitution_sync_change_classes
            ),
        )
        _require_unique(
            "double approval change classes",
            tuple(
                change_class.value
                for change_class in self.double_approval_change_classes
            ),
        )
        _require_unique(
            "high assurance change classes",
            tuple(
                change_class.value
                for change_class in self.high_assurance_change_classes
            ),
        )
        _require_unique(
            "constitutional auto revision targets",
            self.auto_revision_targets,
        )
        _require_unique(
            "constitutional required ELI10 sections",
            self.required_eli10_sections,
        )
        if not self.code_runs_within_constitution:
            raise ValueError("code must run within the constitution")
        if self.quality_gate_role != "TECHNICAL_TRUTH":
            raise ValueError("deterministic quality gate must remain TECHNICAL_TRUTH")
        if self.governance_gate_role != "POLICY_ELIGIBILITY":
            raise ValueError(
                "deterministic governance gate must remain POLICY_ELIGIBILITY"
            )
        if self.human_governance_role != "CONSEQUENTIAL_AUTHORITY":
            raise ValueError("human governance must remain CONSEQUENTIAL_AUTHORITY")
        if not self.risk_tiered_human_governance:
            raise ValueError("human governance must remain risk-tiered")
        if self.change_classes != tuple(ChangeApprovalClass):
            raise ValueError("constitutional change classes must define C0-C4 in order")
        if self.change_classes_without_human_governance != (
            ChangeApprovalClass.C0_NON_BEHAVIORAL,
            ChangeApprovalClass.C1_LOW_RISK,
        ):
            raise ValueError("only C0/C1 changes may proceed without human governance")
        if self.approval_packet_required_change_classes != (
            ChangeApprovalClass.C2_BEHAVIORAL,
            ChangeApprovalClass.C3_GOVERNED,
            ChangeApprovalClass.C4_CONSEQUENTIAL,
        ):
            raise ValueError(
                "approval packet must remain required for C2/C3/C4 changes"
            )
        if self.constitution_sync_change_classes != (
            ChangeApprovalClass.C3_GOVERNED,
            ChangeApprovalClass.C4_CONSEQUENTIAL,
        ):
            raise ValueError("constitution sync must remain required for C3/C4 changes")
        if self.double_approval_change_classes != (ChangeApprovalClass.C3_GOVERNED,):
            raise ValueError("only C3 changes may require double approval")
        if self.high_assurance_change_classes != (
            ChangeApprovalClass.C4_CONSEQUENTIAL,
        ):
            raise ValueError("only C4 changes may require high assurance approval")
        if "policy" not in self.auto_revision_targets:
            raise ValueError("constitutional auto revision must include policy")
        if "instructions" not in self.auto_revision_targets:
            raise ValueError("constitutional auto revision must include instructions")
        if not self.constitution_sync_required:
            raise ValueError("constitution sync is required")
        if self.code_constitution_divergence_allowed:
            raise ValueError("code and constitution divergence is prohibited")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("constitutional change control cannot authorize trading")


@dataclass(frozen=True, slots=True)
class AuthorityPrinciple:
    owner: CoreAuthorityOwner
    statement: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("authority principle statement cannot be empty")


@dataclass(frozen=True, slots=True)
class CoreConstitution:
    constitution_id: str
    version: str
    mission: str
    authority_principles: tuple[AuthorityPrinciple, ...]
    cycle: tuple[CanonicalCycleStep, ...]
    rules: tuple[CoreConstitutionRule, ...]
    final_decision_authority: CoreAuthorityOwner = CoreAuthorityOwner.DETERMINISTIC_CORE
    risk_authority: CoreAuthorityOwner = CoreAuthorityOwner.RISK
    execution_authority: CoreAuthorityOwner = CoreAuthorityOwner.EXECUTION
    live_authority: CoreAuthorityOwner = CoreAuthorityOwner.HUMAN
    change_control: ConstitutionalChangeControl = field(
        default_factory=ConstitutionalChangeControl
    )
    default_trading_mode: str = "paper"
    default_order_mode: str = "manual"
    allow_auto_live_orders: bool = False
    fail_policy: str = "NO_TRADE"

    def __post_init__(self) -> None:
        if not self.constitution_id.strip() or not self.version.strip():
            raise ValueError("constitution identity is required")
        if not self.mission.strip():
            raise ValueError("constitution mission cannot be empty")
        owner_ids = tuple(item.owner.value for item in self.authority_principles)
        _require_unique("authority principles", owner_ids)
        if tuple(item.owner for item in self.authority_principles) != tuple(
            CoreAuthorityOwner
        ):
            raise ValueError("constitution must define every authority principle")
        if self.cycle != tuple(CanonicalCycleStep):
            raise ValueError("canonical cycle order is immutable")
        rule_ids = tuple(rule.rule_id for rule in self.rules)
        if rule_ids != tuple(CoreConstitutionRuleId):
            raise ValueError("constitution must define C01-C25 in order")
        if self.final_decision_authority is not CoreAuthorityOwner.DETERMINISTIC_CORE:
            raise ValueError("final decision authority must remain deterministic core")
        if self.risk_authority is not CoreAuthorityOwner.RISK:
            raise ValueError("risk authority must remain Risk Engine")
        if self.live_authority is not CoreAuthorityOwner.HUMAN:
            raise ValueError("human must retain live authority")
        if self.execution_authority is not CoreAuthorityOwner.EXECUTION:
            raise ValueError("execution authority must remain execution gates")
        if not self.change_control.code_runs_within_constitution:
            raise ValueError("code must run within constitutional change control")
        if self.change_control.quality_gate_role != "TECHNICAL_TRUTH":
            raise ValueError("constitutional quality gate must remain TECHNICAL_TRUTH")
        if self.change_control.governance_gate_role != "POLICY_ELIGIBILITY":
            raise ValueError(
                "constitutional governance gate must remain POLICY_ELIGIBILITY"
            )
        if self.change_control.human_governance_role != "CONSEQUENTIAL_AUTHORITY":
            raise ValueError(
                "constitutional human governance must remain CONSEQUENTIAL_AUTHORITY"
            )
        if not self.change_control.risk_tiered_human_governance:
            raise ValueError("constitutional human governance must remain risk-tiered")
        if not self.change_control.constitution_sync_required:
            raise ValueError("constitutional document sync is required")
        if self.default_trading_mode != "paper" or self.default_order_mode != "manual":
            raise ValueError("paper/manual defaults are immutable")
        if self.allow_auto_live_orders:
            raise ValueError("auto live orders must default disabled")
        if self.fail_policy != "NO_TRADE":
            raise ValueError("core fail policy must be NO_TRADE")


class EngineeringConcept(StrEnum):
    MARKET_DATA_ENGINEERING = "01_MARKET_DATA_ENGINEERING"
    DATA_QUALITY_ENGINEERING = "02_DATA_QUALITY_ENGINEERING"
    FEATURE_ENGINEERING = "03_FEATURE_ENGINEERING"
    CONTEXT_STATE_ENGINEERING = "04_CONTEXT_STATE_ENGINEERING"
    ONTOLOGY_SCHEMA_ENGINEERING = "05_ONTOLOGY_SCHEMA_ENGINEERING"
    EVIDENCE_KNOWLEDGE_ENGINEERING = "06_EVIDENCE_KNOWLEDGE_ENGINEERING"
    AGENTIC_ORCHESTRATION_ENGINEERING = "07_AGENTIC_ORCHESTRATION_ENGINEERING"
    MARKET_INTELLIGENCE_ENGINEERING = "08_MARKET_INTELLIGENCE_ENGINEERING"
    DECISION_GOVERNANCE_ENGINEERING = "09_DECISION_GOVERNANCE_ENGINEERING"
    RISK_PORTFOLIO_ENGINEERING = "10_RISK_PORTFOLIO_ENGINEERING"
    BACKTEST_VALIDATION_ENGINEERING = "11_BACKTEST_VALIDATION_ENGINEERING"
    EVALUATION_OBSERVABILITY = "12_EVALUATION_OBSERVABILITY"
    SECURITY_RELIABILITY_ENGINEERING = "13_SECURITY_RELIABILITY_ENGINEERING"
    MODEL_INFERENCE_ENGINEERING = "14_MODEL_INFERENCE_ENGINEERING"


class ArchitecturePlane(StrEnum):
    CONTROL_ASSURANCE = "CONTROL & ASSURANCE PLANE"
    DATA_EVIDENCE = "DATA & EVIDENCE PLANE"
    INTELLIGENCE = "INTELLIGENCE PLANE"
    DECISION_EXECUTION = "DECISION & EXECUTION PLANE"
    ORCHESTRATION_EVENT_FABRIC = "ORCHESTRATION + EVENT FABRIC"


class CanonicalDomainId(StrEnum):
    META = "00_META"
    REGISTRIES = "01_REGISTRIES"
    MARKET_DATA = "02_MARKET_DATA"
    SHARED_MARKET_STATE = "03_SHARED_MARKET_STATE"
    INTELLIGENCE = "04_INTELLIGENCE"
    DETERMINISTIC_ANALYTICS = "05_DETERMINISTIC_ANALYTICS"
    AGENT_OBSERVATIONS = "06_AGENT_OBSERVATIONS"
    DECISION = "07_DECISION"
    RISK = "08_RISK"
    PORTFOLIO = "09_PORTFOLIO"
    EXECUTION = "10_EXECUTION"
    VALIDATION = "11_VALIDATION"
    LEARNING = "12_LEARNING"
    GOVERNANCE = "13_GOVERNANCE"
    EVIDENCE = "14_EVIDENCE"
    AUDIT_OBSERVABILITY = "15_AUDIT_OBSERVABILITY"
    SECURITY = "16_SECURITY"
    EVENT_FABRIC = "17_EVENT_FABRIC"
    RESEARCH_CAPABILITY = "18_RESEARCH_CAPABILITY"


@dataclass(frozen=True, slots=True)
class CanonicalDomainDefinition:
    domain_id: CanonicalDomainId
    plane: ArchitecturePlane
    owner: str
    description: str
    backbone: bool = False

    def __post_init__(self) -> None:
        if not self.owner.strip() or not self.description.strip():
            raise ValueError("canonical domain owner and description are required")
        invalid_backbone_plane = (
            self.backbone
            and self.plane is not ArchitecturePlane.ORCHESTRATION_EVENT_FABRIC
        )
        if invalid_backbone_plane:
            raise ValueError("backbone domains must use orchestration event fabric")


@dataclass(frozen=True, slots=True)
class CoreArchitecture:
    architecture_id: str
    version: str
    domains: tuple[CanonicalDomainDefinition, ...]
    planes: tuple[ArchitecturePlane, ...] = tuple(ArchitecturePlane)
    research_capability_chain: tuple[CanonicalDomainId, ...] = (
        CanonicalDomainId.RESEARCH_CAPABILITY,
        CanonicalDomainId.DETERMINISTIC_ANALYTICS,
        CanonicalDomainId.VALIDATION,
        CanonicalDomainId.GOVERNANCE,
    )

    def __post_init__(self) -> None:
        if not self.architecture_id.strip() or not self.version.strip():
            raise ValueError("core architecture identity is required")
        if self.planes != tuple(ArchitecturePlane):
            raise ValueError("core architecture planes are immutable")
        domain_ids = tuple(item.domain_id for item in self.domains)
        if domain_ids != tuple(CanonicalDomainId):
            raise ValueError("canonical domains must define 00_META through 18")
        if self.research_capability_chain != (
            CanonicalDomainId.RESEARCH_CAPABILITY,
            CanonicalDomainId.DETERMINISTIC_ANALYTICS,
            CanonicalDomainId.VALIDATION,
            CanonicalDomainId.GOVERNANCE,
        ):
            raise ValueError("ResearchUnit-Capability-Validation-Promotion chain drift")
        backbone = tuple(item for item in self.domains if item.backbone)
        if tuple(item.domain_id for item in backbone) != (
            CanonicalDomainId.EVENT_FABRIC,
        ):
            raise ValueError("event fabric must be the single orchestration backbone")
        domain_owner_keys = tuple(
            f"{item.domain_id}:{item.owner}" for item in self.domains
        )
        _require_unique("canonical domain owners", domain_owner_keys)

    @property
    def domains_by_plane(
        self,
    ) -> MappingProxyType[ArchitecturePlane, tuple[CanonicalDomainDefinition, ...]]:
        grouped: dict[ArchitecturePlane, list[CanonicalDomainDefinition]] = {
            plane: [] for plane in self.planes
        }
        for domain in self.domains:
            grouped[domain.plane].append(domain)
        return MappingProxyType(
            {plane: tuple(items) for plane, items in grouped.items()}
        )


class RegistryKind(StrEnum):
    AGENT = "Agent Registry"
    CAPABILITY = "Capability Registry"
    SKILL = "Skill Registry"
    TOOL = "Tool Registry"
    MODEL = "Model Registry"
    PROMPT = "Prompt Registry"
    STRATEGY = "Strategy Registry"
    INDICATOR = "Indicator Registry"
    PATTERN = "Pattern Registry"
    PARAMETER = "Parameter Registry"
    WORKFLOW = "Workflow Registry"
    DATA_SOURCE = "DataSource Registry"
    DATASET = "Dataset Registry"
    FEATURE = "Feature Registry"
    RISK_RULE = "RiskRule Registry"
    CONTROL = "Control Registry"
    POLICY = "Policy Registry"
    REQUIREMENT = "Requirement Registry"
    RESEARCH_UNIT = "ResearchUnit Registry"
    ORACLE = "Oracle Registry"
    FORMULA = "Formula Registry"
    VALIDATION_PROFILE = "ValidationProfile Registry"


MANDATORY_REGISTRY_KINDS: tuple[RegistryKind, ...] = tuple(RegistryKind)


class EntityFamily(StrEnum):
    IDENTITY = "IDENTITY"
    MARKET = "MARKET"
    DATA = "DATA"
    ANALYTICS = "ANALYTICS"
    INTELLIGENCE = "INTELLIGENCE"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    RISK = "RISK"
    PORTFOLIO = "PORTFOLIO"
    EXECUTION = "EXECUTION"
    VALIDATION = "VALIDATION"
    RESEARCH = "RESEARCH"
    LEARNING = "LEARNING"
    GOVERNANCE = "GOVERNANCE"
    SECURITY = "SECURITY"
    OPERATIONS = "OPERATIONS"
    AUDIT = "AUDIT"


class CoreEntity(StrEnum):
    ACTOR = "Actor"
    HUMAN = "Human"
    AGENT = "Agent"
    SERVICE = "Service"
    EXCHANGE = "Exchange"
    ASSET = "Asset"
    SYMBOL = "Symbol"
    MARKET = "Market"
    TIMEFRAME = "Timeframe"
    DATA_SOURCE = "DataSource"
    DATASET = "Dataset"
    MARKET_DATA = "MarketData"
    MARKET_SNAPSHOT = "MarketSnapshot"
    FEATURE_SNAPSHOT = "FeatureSnapshot"
    CONTEXT_SNAPSHOT = "ContextSnapshot"
    FORMULA_DEFINITION = "FormulaDefinition"
    ORACLE_DEFINITION = "OracleDefinition"
    FEATURE = "Feature"
    INDICATOR = "Indicator"
    CAPABILITY = "Capability"
    OBSERVATION = "Observation"
    AGENT_OBSERVATION = "AgentObservation"
    SOURCE = "Source"
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    EVIDENCE_PACK = "EvidencePack"
    EXTERNAL_EVENT = "ExternalEvent"
    SIGNAL = "Signal"
    SETUP = "Setup"
    STRATEGY = "Strategy"
    REGIME = "Regime"
    DECISION_CANDIDATE = "DecisionCandidate"
    TRADE_DECISION = "TradeDecision"
    RISK = "Risk"
    RISK_ASSESSMENT = "RiskAssessment"
    RISK_RULE = "RiskRule"
    CONTROL = "Control"
    PORTFOLIO_STATE = "PortfolioState"
    WALLET = "Wallet"
    BALANCE = "Balance"
    INVENTORY = "Inventory"
    POSITION = "Position"
    EXPOSURE = "Exposure"
    TRADE_PLAN = "TradePlan"
    EXECUTION_GATE_RESULT = "ExecutionGateResult"
    ORDER = "Order"
    EXECUTION_RECORD = "ExecutionRecord"
    POSITION_LIFECYCLE = "PositionLifecycle"
    EXIT_EVENT = "ExitEvent"
    VALIDATION = "Validation"
    VALIDATION_PROFILE = "ValidationProfile"
    VALIDATION_ARTIFACT = "ValidationArtifact"
    BACKTEST_RUN = "BacktestRun"
    WALK_FORWARD_RUN = "WalkForwardRun"
    OOS_RUN = "OOSRun"
    RESEARCH_UNIT = "ResearchUnit"
    RADAR_FINDING = "RadarFinding"
    CAPABILITY_CANDIDATE = "CapabilityCandidate"
    LESSON = "Lesson"
    HYPOTHESIS = "Hypothesis"
    LEARNING_CANDIDATE = "LearningCandidate"
    REQUIREMENT = "Requirement"
    POLICY = "Policy"
    AUTHORITY_POLICY = "AuthorityPolicy"
    APPROVAL = "Approval"
    EXCEPTION = "Exception"
    FINDING = "Finding"
    TREATMENT = "Treatment"
    GOVERNANCE_OBJECT = "GovernanceObject"
    GOVERNANCE_RELEASE_RECORD = "GovernanceReleaseRecord"
    APPROVED_OPERATING_ENVELOPE = "ApprovedOperatingEnvelope"
    INCIDENT = "Incident"
    PROBLEM = "Problem"
    ESCALATION_EVENT = "EscalationEvent"
    AUDIT_EVENT = "AuditEvent"


@dataclass(frozen=True, slots=True)
class CanonicalEntityOntology:
    ontology_id: str = "AI4BINANCE-CANONICAL-ENTITY-ONTOLOGY"
    version: str = "2.0.0"
    families: tuple[EntityFamily, ...] = tuple(EntityFamily)
    entities: tuple[CoreEntity, ...] = tuple(CoreEntity)
    domain: CanonicalDomainId = CanonicalDomainId.DETERMINISTIC_ANALYTICS

    def __post_init__(self) -> None:
        _require_non_empty("canonical entity ontology_id", self.ontology_id)
        _require_non_empty("canonical entity ontology version", self.version)
        if self.domain is not CanonicalDomainId.DETERMINISTIC_ANALYTICS:
            raise ValueError(
                "canonical entity ontology belongs to 05_DETERMINISTIC_ANALYTICS"
            )
        if self.families != tuple(EntityFamily):
            raise ValueError("canonical entity families must be complete")
        if self.entities != tuple(CoreEntity):
            raise ValueError("canonical core entities must be complete")


class EntityRuleId(StrEnum):
    ER_001_IDENTITY = "ER-001"
    ER_002_VERSIONING = "ER-002"
    ER_003_OWNERSHIP = "ER-003"
    ER_004_LIFECYCLE = "ER-004"
    ER_005_PROVENANCE = "ER-005"
    ER_006_SNAPSHOT_CONSISTENCY = "ER-006"
    ER_007_CYCLE_IDENTITY = "ER-007"
    ER_008_IMMUTABILITY = "ER-008"
    ER_009_EVIDENCE_STATUS = "ER-009"
    ER_010_UNKNOWN = "ER-010"
    ER_011_CAPABILITY_FIRST_VALIDATION = "ER-011"
    ER_012_LICENSE_GOVERNANCE = "ER-012"
    ER_013_REPAINTING_LOOKAHEAD = "ER-013"
    ER_014_STATE_SEPARATION = "ER-014"
    ER_015_RISK_SEPARATION = "ER-015"


class EntityLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    RESEARCH = "RESEARCH"
    POC_CANDIDATE = "POC_CANDIDATE"
    BACKTESTED = "BACKTESTED"
    WF_VALIDATED = "WF_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    PAPER_CANDIDATE = "PAPER_CANDIDATE"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_CANDIDATE = "LIVE_CANDIDATE"
    LIVE_APPROVED = "LIVE_APPROVED"
    RESTRICTED = "RESTRICTED"
    QUARANTINED = "QUARANTINED"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"
    WITHDRAWN = "WITHDRAWN"


class VersionedTradingComponent(StrEnum):
    AGENT = "Agent"
    CAPABILITY = "Capability"
    FORMULA = "Formula"
    ORACLE = "Oracle"
    INDICATOR = "Indicator"
    MODEL = "Model"
    PROMPT = "Prompt"
    STRATEGY = "Strategy"
    PARAMETER_SET = "ParameterSet"
    POLICY = "Policy"
    RISK_RULE = "RiskRule"
    WORKFLOW = "Workflow"
    TOOL_CONTRACT = "Tool contract"


class ImmutableEntityKind(StrEnum):
    RAW_MARKET_DATA = "raw market data"
    EVIDENCE = "evidence"
    DECISION_RECORDS = "decision records"
    EXECUTION_RECORDS = "execution records"
    AUDIT_EVENTS = "audit events"
    VALIDATION_ARTIFACTS = "validation artifacts"


class UnknownRepresentation(StrEnum):
    UNKNOWN = "UNKNOWN"
    NULL = "null"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class StateSeparationKind(StrEnum):
    RUNTIME_STATE = "RuntimeState"
    HISTORICAL_MEMORY = "HistoricalMemory"
    KNOWLEDGE = "Knowledge"
    EVIDENCE = "Evidence"
    LEARNING = "Learning"


@dataclass(frozen=True, slots=True)
class EntityOwnership:
    technical_owner: str
    logical_owner: str
    validation_owner: str | None = None
    risk_owner: str | None = None
    approval_owner: str | None = None
    production_component: bool = False
    validation_owner_required: bool = False
    risk_owner_required: bool = False
    approval_owner_required: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("technical_owner", self.technical_owner)
        _require_non_empty("logical_owner", self.logical_owner)
        for field_name in ("validation_owner", "risk_owner", "approval_owner"):
            value = getattr(self, field_name)
            if value is not None:
                _require_non_empty(field_name, value)
        if self.production_component:
            if not self.technical_owner.strip() or not self.logical_owner.strip():
                raise ValueError("ownerless production component is prohibited")
        if self.validation_owner_required and self.validation_owner is None:
            raise ValueError("validation_owner is required")
        if self.risk_owner_required and self.risk_owner is None:
            raise ValueError("risk_owner is required")
        if self.approval_owner_required and self.approval_owner is None:
            raise ValueError("approval_owner is required")


@dataclass(frozen=True, slots=True)
class PersistentEntityIdentity:
    entity_id: str
    entity: CoreEntity

    def __post_init__(self) -> None:
        _require_non_empty("entity_id", self.entity_id)


@dataclass(frozen=True, slots=True)
class EntityRuleCatalog:
    catalog_id: str = "AI4BINANCE-ENTITY-RULES"
    version: str = "2.0.0"
    rules: tuple[EntityRuleId, ...] = tuple(EntityRuleId)
    lifecycle: tuple[EntityLifecycleStatus, ...] = tuple(EntityLifecycleStatus)
    versioned_trading_components: tuple[VersionedTradingComponent, ...] = tuple(
        VersionedTradingComponent
    )
    immutable_entities: tuple[ImmutableEntityKind, ...] = tuple(ImmutableEntityKind)
    evidence_statuses: tuple[EvidenceVerificationStatus, ...] = field(
        default_factory=lambda: tuple(EvidenceVerificationStatus)
    )
    unknown_representations: tuple[UnknownRepresentation, ...] = tuple(
        UnknownRepresentation
    )
    state_separation: tuple[StateSeparationKind, ...] = tuple(StateSeparationKind)
    domain: CanonicalDomainId = CanonicalDomainId.DETERMINISTIC_ANALYTICS

    def __post_init__(self) -> None:
        _require_non_empty("entity rule catalog_id", self.catalog_id)
        _require_non_empty("entity rule version", self.version)
        if self.domain is not CanonicalDomainId.DETERMINISTIC_ANALYTICS:
            raise ValueError("entity rules belong to 05_DETERMINISTIC_ANALYTICS")
        if self.rules != tuple(EntityRuleId):
            raise ValueError("entity rules must be complete")
        if self.lifecycle != tuple(EntityLifecycleStatus):
            raise ValueError("entity lifecycle statuses must be complete")
        if self.versioned_trading_components != tuple(VersionedTradingComponent):
            raise ValueError("versioned trading components must be complete")
        if self.immutable_entities != tuple(ImmutableEntityKind):
            raise ValueError("immutable entity kinds must be complete")
        if self.evidence_statuses != tuple(EvidenceVerificationStatus):
            raise ValueError("evidence statuses must be explicit")
        if self.unknown_representations != tuple(UnknownRepresentation):
            raise ValueError("unknown representations must be explicit")
        if self.state_separation != tuple(StateSeparationKind):
            raise ValueError("state separation classes must be complete")


class RelationshipType(StrEnum):
    OWNS = "OWNS"
    CONSUMES = "CONSUMES"
    PRODUCES = "PRODUCES"
    DERIVED_FROM = "DERIVED_FROM"
    OBSERVES = "OBSERVES"
    CONTAINS = "CONTAINS"
    USES = "USES"
    DEPENDS_ON = "DEPENDS_ON"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    VERIFIES = "VERIFIES"
    CONTRIBUTES_TO = "CONTRIBUTES_TO"
    QUALIFIES = "QUALIFIES"
    EVALUATED_BY = "EVALUATED_BY"
    CONSTRAINED_BY = "CONSTRAINED_BY"
    MITIGATED_BY = "MITIGATED_BY"
    GOVERNED_BY = "GOVERNED_BY"
    CONTROLLED_BY = "CONTROLLED_BY"
    ALLOWED_BY = "ALLOWED_BY"
    BLOCKED_BY = "BLOCKED_BY"
    SUBJECT_TO = "SUBJECT_TO"
    VALIDATED_BY = "VALIDATED_BY"
    APPROVED_BY = "APPROVED_BY"
    PROMOTED_TO = "PROMOTED_TO"
    RESTRICTS = "RESTRICTS"
    SUPERSEDES = "SUPERSEDES"
    CREATES = "CREATES"
    EXECUTES = "EXECUTES"
    RESULTS_IN = "RESULTS_IN"
    RECORDED_AS = "RECORDED_AS"
    PRODUCES_LESSON = "PRODUCES_LESSON"
    PROPOSES = "PROPOSES"
    ESCALATES_TO = "ESCALATES_TO"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    VERIFIED_BY = "VERIFIED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    PROMOTES = "PROMOTES"


class RelationshipRuleId(StrEnum):
    RR_001_MARKET_LINEAGE = "RR-001"
    RR_002_FEATURE_LINEAGE = "RR-002"
    RR_003_ORACLE = "RR-003"
    RR_004_AGENT_OBSERVATION = "RR-004"
    RR_005_EVIDENCE = "RR-005"
    RR_006_SETUP = "RR-006"
    RR_007_DECISION = "RR-007"
    RR_008_RISK = "RR-008"
    RR_009_CONTROL = "RR-009"
    RR_010_REQUIREMENT = "RR-010"
    RR_011_EVIDENCE_OF_CONTROL = "RR-011"
    RR_012_GOVERNANCE = "RR-012"
    RR_013_EXECUTION = "RR-013"
    RR_014_NO_SHORTCUT = "RR-014"
    RR_015_POSITION_LIFECYCLE = "RR-015"
    RR_016_REVIEW = "RR-016"
    RR_017_LESSON = "RR-017"
    RR_018_LEARNING = "RR-018"
    RR_019_NO_SELF_PROMOTION = "RR-019"
    RR_020_RESEARCH_PROMOTION = "RR-020"
    RR_021_VALIDATION = "RR-021"
    RR_022_DECISION_GOVERNANCE = "RR-022"


@dataclass(frozen=True, slots=True)
class RelationshipTriple:
    source: str
    relationship: RelationshipType
    target: str

    def __post_init__(self) -> None:
        _require_non_empty("relationship source", self.source)
        _require_non_empty("relationship target", self.target)


@dataclass(frozen=True, slots=True)
class RelationshipRule:
    rule_id: RelationshipRuleId
    required: tuple[RelationshipTriple, ...] = ()
    prohibited: tuple[RelationshipTriple, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.required and not self.prohibited:
            raise ValueError(
                "relationship rule must define required or prohibited triples"
            )
        if self.rationale:
            _require_non_empty("relationship rule rationale", self.rationale)


def _relationship(
    source: str,
    relationship: RelationshipType,
    target: str,
) -> RelationshipTriple:
    return RelationshipTriple(source, relationship, target)


@dataclass(frozen=True, slots=True)
class RelationshipRuleCatalog:
    catalog_id: str = "AI4BINANCE-RELATIONSHIP-RULES"
    version: str = "2.0.0"
    canonical_relationships: tuple[RelationshipType, ...] = tuple(RelationshipType)
    rules: tuple[RelationshipRule, ...] = field(default_factory=tuple)
    domain: CanonicalDomainId = CanonicalDomainId.DETERMINISTIC_ANALYTICS

    def __post_init__(self) -> None:
        _require_non_empty("relationship rule catalog_id", self.catalog_id)
        _require_non_empty("relationship rule version", self.version)
        if self.domain is not CanonicalDomainId.DETERMINISTIC_ANALYTICS:
            raise ValueError("relationship rules belong to 05_DETERMINISTIC_ANALYTICS")
        if self.canonical_relationships != tuple(RelationshipType):
            raise ValueError("canonical relationships must be complete")
        expected_rule_ids = tuple(RelationshipRuleId)
        actual_rule_ids = tuple(rule.rule_id for rule in self.rules)
        if actual_rule_ids != expected_rule_ids:
            raise ValueError("relationship rules must be complete and ordered")


def build_relationship_rule_catalog() -> RelationshipRuleCatalog:
    rules = (
        RelationshipRule(
            RelationshipRuleId.RR_001_MARKET_LINEAGE,
            required=(
                _relationship("DataSource", RelationshipType.PRODUCES, "MarketData"),
                _relationship(
                    "MarketSnapshot", RelationshipType.DERIVED_FROM, "MarketData"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_002_FEATURE_LINEAGE,
            required=(
                _relationship(
                    "Feature", RelationshipType.DERIVED_FROM, "MarketSnapshot"
                ),
                _relationship(
                    "Feature", RelationshipType.IMPLEMENTED_BY, "FormulaDefinition"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_003_ORACLE,
            required=(
                _relationship(
                    "Capability", RelationshipType.VERIFIED_BY, "OracleDefinition"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_004_AGENT_OBSERVATION,
            required=(
                _relationship("Agent", RelationshipType.PRODUCES, "AgentObservation"),
            ),
            prohibited=(
                _relationship("Agent", RelationshipType.PRODUCES, "TradeDecision"),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_005_EVIDENCE,
            required=(
                _relationship(
                    "AgentObservation", RelationshipType.SUPPORTED_BY, "Evidence"
                ),
                _relationship(
                    "AgentObservation", RelationshipType.CONTRADICTED_BY, "Evidence"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_006_SETUP,
            required=(
                _relationship("Feature", RelationshipType.CONTRIBUTES_TO, "Setup"),
                _relationship(
                    "AgentObservation", RelationshipType.CONTRIBUTES_TO, "Setup"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_007_DECISION,
            required=(
                _relationship(
                    "Setup", RelationshipType.EVALUATED_BY, "DeterministicCore"
                ),
                _relationship(
                    "DeterministicCore", RelationshipType.PRODUCES, "DecisionCandidate"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_008_RISK,
            required=(
                _relationship(
                    "DecisionCandidate",
                    RelationshipType.CONSTRAINED_BY,
                    "RiskAssessment",
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_009_CONTROL,
            required=(_relationship("Risk", RelationshipType.MITIGATED_BY, "Control"),),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_010_REQUIREMENT,
            required=(
                _relationship(
                    "Requirement", RelationshipType.IMPLEMENTED_BY, "Control"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_011_EVIDENCE_OF_CONTROL,
            required=(
                _relationship("Control", RelationshipType.VERIFIED_BY, "Evidence"),
                _relationship("Evidence", RelationshipType.VERIFIED_BY, "Test"),
                _relationship("Test", RelationshipType.PRODUCES, "Finding"),
                _relationship("Finding", RelationshipType.RESULTS_IN, "Remediation"),
            ),
            rationale=(
                "Requirement -> Control -> Evidence -> Test -> Finding -> Remediation"
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_012_GOVERNANCE,
            required=(
                _relationship("TradeDecision", RelationshipType.GOVERNED_BY, "Policy"),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_013_EXECUTION,
            required=(
                _relationship(
                    "TradePlan", RelationshipType.SUBJECT_TO, "ExecutionGateResult"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_014_NO_SHORTCUT,
            prohibited=(_relationship("Agent", RelationshipType.EXECUTES, "Order"),),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_015_POSITION_LIFECYCLE,
            required=(
                _relationship(
                    "ExecutionRecord", RelationshipType.CREATES, "PositionLifecycle"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_016_REVIEW,
            required=(
                _relationship(
                    "PositionLifecycle", RelationshipType.EVALUATED_BY, "ClosureReview"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_017_LESSON,
            required=(
                _relationship(
                    "ClosureReview", RelationshipType.PRODUCES_LESSON, "Lesson"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_018_LEARNING,
            required=(
                _relationship("Lesson", RelationshipType.PROPOSES, "LearningCandidate"),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_019_NO_SELF_PROMOTION,
            prohibited=(
                _relationship(
                    "LearningCandidate",
                    RelationshipType.PROMOTES,
                    "ProductionComponent",
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_020_RESEARCH_PROMOTION,
            required=(
                _relationship(
                    "RadarFinding", RelationshipType.RESULTS_IN, "ResearchUnit"
                ),
                _relationship(
                    "ResearchUnit", RelationshipType.RESULTS_IN, "CapabilityCandidate"
                ),
                _relationship(
                    "CapabilityCandidate", RelationshipType.VALIDATED_BY, "Validation"
                ),
                _relationship(
                    "CapabilityCandidate",
                    RelationshipType.SUBJECT_TO,
                    "PromotionGovernance",
                ),
                _relationship(
                    "PromotionGovernance",
                    RelationshipType.PROMOTED_TO,
                    "RegistryComponent",
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_021_VALIDATION,
            required=(
                _relationship(
                    "DecisionCandidate", RelationshipType.VALIDATED_BY, "Validation"
                ),
            ),
        ),
        RelationshipRule(
            RelationshipRuleId.RR_022_DECISION_GOVERNANCE,
            required=(
                _relationship(
                    "DecisionGovernance", RelationshipType.PRODUCES, "TradeDecision"
                ),
            ),
        ),
    )
    return RelationshipRuleCatalog(rules=rules)


class ExternalFrameworkId(StrEnum):
    ISO_42001 = "ISO 42001"
    ISO_23894 = "ISO 23894"
    ISO_27001 = "ISO 27001"
    ISO_31000 = "ISO 31000"
    NIST_AI_RMF = "NIST AI RMF"
    COSO = "COSO"
    COBIT = "COBIT"


class LegalSourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REPEALED = "REPEALED"
    DRAFT = "DRAFT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class LegalSourceMetadata:
    jurisdiction: str
    status: LegalSourceStatus
    effective_from: date
    effective_to: date | None
    last_verified_at: datetime
    source_reference: str

    def __post_init__(self) -> None:
        _require_non_empty("legal source jurisdiction", self.jurisdiction)
        _require_non_empty("legal source_reference", self.source_reference)
        _require_utc_timestamp("legal source last_verified_at", self.last_verified_at)
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("legal source effective_to cannot precede effective_from")


@dataclass(frozen=True, slots=True)
class ExternalStandardsMappingContract:
    contract_id: str = "AI4BINANCE-EXTERNAL-STANDARDS-MAPPING"
    version: str = "2.0.0"
    frameworks: tuple[ExternalFrameworkId, ...] = tuple(ExternalFrameworkId)
    ontology_chain: tuple[str, ...] = (
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
    relationship_chain: tuple[RelationshipTriple, ...] = field(
        default_factory=lambda: (
            _relationship(
                "ExternalFramework", RelationshipType.CONTAINS, "Requirement"
            ),
            _relationship("Requirement", RelationshipType.SUBJECT_TO, "Risk"),
            _relationship("Risk", RelationshipType.MITIGATED_BY, "Control"),
            _relationship("Control", RelationshipType.IMPLEMENTED_BY, "Implementation"),
            _relationship("Implementation", RelationshipType.PRODUCES, "Evidence"),
            _relationship("Evidence", RelationshipType.VERIFIED_BY, "Test"),
            _relationship("Test", RelationshipType.PRODUCES, "Finding"),
            _relationship("Finding", RelationshipType.RESULTS_IN, "Remediation"),
        )
    )
    shared_control_reuse_allowed: bool = True
    separate_compliance_subsystems_allowed: bool = False
    legal_source_metadata_required: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE

    def __post_init__(self) -> None:
        _require_non_empty("external standards mapping contract_id", self.contract_id)
        _require_non_empty("external standards mapping version", self.version)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("external standards mapping belongs to 13_GOVERNANCE")
        if self.frameworks != tuple(ExternalFrameworkId):
            raise ValueError("external frameworks must be complete")
        expected_chain = (
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
        if self.ontology_chain != expected_chain:
            raise ValueError("external standards ontology chain must be canonical")
        expected_relationship_chain = (
            _relationship(
                "ExternalFramework", RelationshipType.CONTAINS, "Requirement"
            ),
            _relationship("Requirement", RelationshipType.SUBJECT_TO, "Risk"),
            _relationship("Risk", RelationshipType.MITIGATED_BY, "Control"),
            _relationship("Control", RelationshipType.IMPLEMENTED_BY, "Implementation"),
            _relationship("Implementation", RelationshipType.PRODUCES, "Evidence"),
            _relationship("Evidence", RelationshipType.VERIFIED_BY, "Test"),
            _relationship("Test", RelationshipType.PRODUCES, "Finding"),
            _relationship("Finding", RelationshipType.RESULTS_IN, "Remediation"),
        )
        if self.relationship_chain != expected_relationship_chain:
            raise ValueError("external standards relationship chain must be canonical")
        if not self.shared_control_reuse_allowed:
            raise ValueError("shared control reuse must remain allowed")
        if self.separate_compliance_subsystems_allowed:
            raise ValueError("separate compliance subsystems are prohibited")
        if not self.legal_source_metadata_required:
            raise ValueError("legal source metadata must remain required")


def build_external_standards_mapping_contract() -> ExternalStandardsMappingContract:
    return ExternalStandardsMappingContract()


class StructuralCapabilityId(StrEnum):
    SWING_HIGH_LOW = "SWING_HIGH_LOW"
    BOS = "BOS"
    CHOCH = "CHoCH"
    BREAKOUT = "BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    STRUCTURE_SHIFT = "STRUCTURE_SHIFT"


class CapabilityStatus(StrEnum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    POC_CANDIDATE = "POC_CANDIDATE"
    VALIDATION_CANDIDATE = "VALIDATION_CANDIDATE"
    BACKTESTED = "BACKTESTED"
    WF_VALIDATED = "WF_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_BLOCKED = "LIVE_BLOCKED"
    REJECTED = "REJECTED"


class CapabilityFamily(StrEnum):
    STRUCTURE = "STRUCTURE"
    TREND = "TREND"
    VOLATILITY = "VOLATILITY"
    MOMENTUM = "MOMENTUM"
    VOLUME = "VOLUME"
    PRICE_ACTION = "PRICE_ACTION"
    SUPPORT_RESISTANCE = "SUPPORT_RESISTANCE"
    FIBONACCI = "FIBONACCI"
    PATTERN = "PATTERN"
    WYCKOFF = "WYCKOFF"
    SMC = "SMC"
    ORDER_FLOW = "ORDER_FLOW"
    DERIVATIVES = "DERIVATIVES"
    REGIME = "REGIME"
    CYCLE = "CYCLE"


class DeterministicFeatureFamily(StrEnum):
    TREND = "Trend"
    VOLATILITY = "Volatility"
    MOMENTUM = "Momentum"
    VOLUME = "Volume"
    PRICE_ACTION = "PriceAction"
    STRUCTURE = "Structure"
    SUPPORT_RESISTANCE = "SupportResistance"
    FIBONACCI = "Fibonacci"
    PATTERN = "Pattern"
    WYCKOFF = "Wyckoff"
    SMC = "SMC"
    ORDER_FLOW = "OrderFlow"
    DERIVATIVES = "Derivatives"
    REGIME = "Regime"
    CYCLE = "Cycle"


class TechnicalFamilyId(StrEnum):
    TREND = "A_TREND"
    VOLATILITY = "B_VOLATILITY"
    MOMENTUM = "C_MOMENTUM"
    VOLUME = "D_VOLUME"
    PRICE_ACTION = "E_PRICE_ACTION"
    STRUCTURAL_LEVELS = "F_STRUCTURAL_LEVELS"
    FIBONACCI = "G_FIBONACCI"
    PATTERN_RECOGNITION = "H_PATTERN_RECOGNITION"
    MACRO_CYCLE = "I_MACRO_CYCLE"


class CapabilityRole(StrEnum):
    PRIMARY = "PRIMARY"
    PRIMARY_TRIGGER = "PRIMARY_TRIGGER"
    PRIMARY_RISK_FILTER = "PRIMARY_RISK_FILTER"
    SECONDARY = "SECONDARY"
    DIAGNOSTIC = "DIAGNOSTIC"
    ADVISORY = "ADVISORY"


class ScoreContributionLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HardGateEligibility(StrEnum):
    TRUE = "true"
    FALSE = "false"
    CONDITIONAL = "conditional"


@dataclass(frozen=True, slots=True)
class TechnicalFamilyGovernance:
    family_id: TechnicalFamilyId
    feature_family: DeterministicFeatureFamily
    role: CapabilityRole
    allowed_timeframes: tuple[str, ...]
    score_contribution: ScoreContributionLevel
    hard_gate_eligibility: HardGateEligibility
    hard_gate_description: str
    false_positive_risks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.allowed_timeframes:
            raise ValueError("technical family allowed_timeframes cannot be empty")
        _require_unique("technical family allowed_timeframes", self.allowed_timeframes)
        for timeframe in self.allowed_timeframes:
            if timeframe not in CANONICAL_DEFAULT_TIMEFRAMES:
                raise ValueError("technical family timeframe must be canonical")
        _require_non_empty(
            "technical family hard_gate_description", self.hard_gate_description
        )
        _require_unique(
            "technical family false_positive_risks", self.false_positive_risks
        )


@dataclass(frozen=True, slots=True)
class DeterministicAnalyticsCatalog:
    catalog_id: str
    version: str
    domain: CanonicalDomainId = CanonicalDomainId.DETERMINISTIC_ANALYTICS
    feature_families: tuple[DeterministicFeatureFamily, ...] = tuple(
        DeterministicFeatureFamily
    )
    technical_families: tuple[TechnicalFamilyGovernance, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("deterministic analytics catalog_id", self.catalog_id)
        _require_non_empty("deterministic analytics version", self.version)
        if self.domain is not CanonicalDomainId.DETERMINISTIC_ANALYTICS:
            raise ValueError(
                "deterministic analytics catalog must belong to "
                "05_DETERMINISTIC_ANALYTICS"
            )
        if self.feature_families != tuple(DeterministicFeatureFamily):
            raise ValueError("deterministic feature families must be canonical")
        ids = tuple(item.family_id.value for item in self.technical_families)
        _require_unique("technical family IDs", ids)
        if tuple(item.family_id for item in self.technical_families) != tuple(
            TechnicalFamilyId
        ):
            raise ValueError("technical family governance must cover A-I families")


class ValidationEvidenceStatus(StrEnum):
    PASS = "PASS"  # noqa: S105  # nosec B105
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class ValidationStage(StrEnum):
    UNIT_TESTS = "UnitTests"
    FORMULA_ORACLE_TEST = "FormulaOracleTest"
    REGRESSION_TESTS = "RegressionTests"
    BACKTEST = "Backtest"
    TRAIN_TEST = "TrainTest"
    WALK_FORWARD = "WalkForward"
    OOS = "OOS"
    MONTE_CARLO = "MonteCarlo"
    SENSITIVITY = "Sensitivity"
    REGIME_TESTS = "RegimeTests"
    SLIPPAGE_ROBUSTNESS = "SlippageRobustness"
    FEE_ROBUSTNESS = "FeeRobustness"
    MULTIPLE_TESTING_CONTROL = "MultipleTestingControl"
    PROMOTION_REVIEW = "PromotionReview"


@dataclass(frozen=True, slots=True)
class ValidationDomainContract:
    validation_domain_id: str = "AI4BINANCE-VALIDATION-DOMAIN"
    version: str = "2.0.0"
    domain: CanonicalDomainId = CanonicalDomainId.VALIDATION
    stages: tuple[ValidationStage, ...] = tuple(ValidationStage)
    capability_first: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("validation_domain_id", self.validation_domain_id)
        _require_non_empty("validation domain version", self.version)
        if self.domain is not CanonicalDomainId.VALIDATION:
            raise ValueError("validation domain must remain in 11_VALIDATION")
        if self.stages != tuple(ValidationStage):
            raise ValueError("validation stages must remain canonical")
        if not self.capability_first:
            raise ValueError("validation must be capability-first")


class MarketDataKind(StrEnum):
    OHLCV = "OHLCV"
    TICKER = "Ticker"
    TRADES = "Trades"
    AGG_TRADES = "AggTrades"
    ORDER_BOOK_SNAPSHOT = "OrderBookSnapshot"
    ORDER_BOOK_DELTA = "OrderBookDelta"
    SPREAD = "Spread"
    LIQUIDITY = "Liquidity"
    EXCHANGE_INFO = "ExchangeInfo"
    SYMBOL_FILTERS = "SymbolFilters"
    MARKET_STATUS = "MarketStatus"
    FUNDING = "Funding"
    OPEN_INTEREST = "OpenInterest"
    LONG_SHORT_RATIO = "LongShortRatio"
    TOP_TRADER_RATIO = "TopTraderRatio"
    TAKER_FLOW = "TakerFlow"
    SERVER_TIME = "ServerTime"


class SpotDecisionAuthority(StrEnum):
    DECISION_AUTHORITY = "DECISION_AUTHORITY"
    SUPPLEMENTARY_ADVISORY = "SUPPLEMENTARY_ADVISORY"


class DecisionPipelineStage(StrEnum):
    DATA_READINESS = "DATA_READINESS"
    HARD_BLOCKER_CHECK = "HARD_BLOCKER_CHECK"
    EVIDENCE_COMPLETENESS = "EVIDENCE_COMPLETENESS"
    CAPABILITY_ELIGIBILITY = "CAPABILITY_ELIGIBILITY"
    SETUP_QUALIFICATION = "SETUP_QUALIFICATION"
    DETERMINISTIC_100_POINT_SCORE = "DETERMINISTIC_100_POINT_SCORE"
    ACTION_CEILING = "ACTION_CEILING"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    GOVERNANCE_ELIGIBILITY = "GOVERNANCE_ELIGIBILITY"
    TRADE_PLAN = "TRADE_PLAN"
    EXECUTION_GATE = "EXECUTION_GATE"


class GovernanceMaturity(StrEnum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    STAGED_CANDIDATE = "STAGED_CANDIDATE"
    BACKTESTED = "BACKTESTED"
    WF_VALIDATED = "WF_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


class ActionCeiling(StrEnum):
    NONE = "NONE"
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    LIVE_BLOCKED = "LIVE_BLOCKED"


@dataclass(frozen=True, slots=True)
class DecisionCorePipeline:
    pipeline_id: str = "AI4BINANCE-DECISION-CORE-PIPELINE"
    version: str = "2.0.0"
    domain: CanonicalDomainId = CanonicalDomainId.DECISION
    stages: tuple[DecisionPipelineStage, ...] = tuple(DecisionPipelineStage)

    def __post_init__(self) -> None:
        _require_non_empty("decision pipeline_id", self.pipeline_id)
        _require_non_empty("decision pipeline version", self.version)
        if self.domain is not CanonicalDomainId.DECISION:
            raise ValueError("decision pipeline must belong to 07_DECISION")
        if self.stages != tuple(DecisionPipelineStage):
            raise ValueError("decision pipeline stage order is immutable")


@dataclass(frozen=True, slots=True)
class DecisionScoreGovernanceResult:
    deterministic_score: float
    governance_maturity: GovernanceMaturity
    action_ceiling: ActionCeiling

    def __post_init__(self) -> None:
        if not 0.0 <= self.deterministic_score <= 100.0:
            raise ValueError("deterministic score must be between 0 and 100")
        expected = action_ceiling_for_maturity(self.governance_maturity)
        if self.action_ceiling is not expected:
            raise ValueError("score cannot raise governance maturity action ceiling")


class HardBlockerCode(StrEnum):
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_STALE = "DATA_STALE"
    DATA_INCONSISTENT = "DATA_INCONSISTENT"
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"
    CRITICAL_SECURITY_EVENT = "CRITICAL_SECURITY_EVENT"
    CRITICAL_NEWS_RISK = "CRITICAL_NEWS_RISK"
    CAPABILITY_UNVALIDATED = "CAPABILITY_UNVALIDATED"
    OOS_NOT_VALIDATED = "OOS_NOT_VALIDATED"
    STRATEGY_NOT_APPROVED = "STRATEGY_NOT_APPROVED"
    GOVERNANCE_NOT_APPROVED = "GOVERNANCE_NOT_APPROVED"
    LOOKAHEAD_DETECTED = "LOOKAHEAD_DETECTED"
    REPAINTING_DETECTED = "REPAINTING_DETECTED"
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"
    SPREAD_LIMIT_EXCEEDED = "SPREAD_LIMIT_EXCEEDED"
    SLIPPAGE_LIMIT_EXCEEDED = "SLIPPAGE_LIMIT_EXCEEDED"
    EXCHANGE_INFO_UNAVAILABLE = "EXCHANGE_INFO_UNAVAILABLE"
    PRICE_FILTER_INVALID = "PRICE_FILTER_INVALID"
    LOT_SIZE_INVALID = "LOT_SIZE_INVALID"
    NOTIONAL_INVALID = "NOTIONAL_INVALID"
    BALANCE_UNKNOWN = "BALANCE_UNKNOWN"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    INVENTORY_UNKNOWN = "INVENTORY_UNKNOWN"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    LOSS_CIRCUIT_BREAKER = "LOSS_CIRCUIT_BREAKER"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    PORTFOLIO_LIMIT_EXCEEDED = "PORTFOLIO_LIMIT_EXCEEDED"
    CONFLICTING_OPEN_ORDER = "CONFLICTING_OPEN_ORDER"
    UNAUTHORIZED_EXECUTION = "UNAUTHORIZED_EXECUTION"
    CRITICAL_POLICY_VIOLATION = "CRITICAL_POLICY_VIOLATION"


@dataclass(frozen=True, slots=True)
class HardBlockerDecisionResult:
    blockers: tuple[HardBlockerCode, ...]
    result: str
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_unique(
            "hard blocker codes",
            tuple(blocker.value for blocker in self.blockers),
        )
        expected_result = "CONTINUE"
        if self.blockers:
            expected_result = (
                "LIVE_ORDER_BLOCKED"
                if self.result == "LIVE_ORDER_BLOCKED"
                else "NO_TRADE"
            )
        if self.result != expected_result:
            raise ValueError("hard blocker result must be fail-closed")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("hard blockers must keep live eligibility blocked")


def decision_result_for_hard_blockers(
    blockers: tuple[HardBlockerCode, ...],
    *,
    live_candidate: bool = False,
) -> HardBlockerDecisionResult:
    """Return the canonical fail-closed decision result for hard blockers."""
    if not blockers:
        return HardBlockerDecisionResult(blockers=(), result="CONTINUE")
    result = "LIVE_ORDER_BLOCKED" if live_candidate else "NO_TRADE"
    return HardBlockerDecisionResult(blockers=blockers, result=result)


class RiskState(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class RiskAssessmentResult(StrEnum):
    PASS = "PASS"  # noqa: S105  # nosec B105
    RESTRICT = "RESTRICT"
    BLOCK = "BLOCK"


class RiskControlId(StrEnum):
    MAX_RISK_PER_TRADE = "max_risk_per_trade"
    MAX_TRADE_USDT = "max_trade_usdt"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_OPEN_POSITION_SIZE = "max_open_position_size"
    SPREAD_CAP = "spread_cap"
    SLIPPAGE_CAP = "slippage_cap"
    MINIMUM_RR = "minimum_rr"
    COOLDOWN = "cooldown"
    REPEATED_LOSS_CIRCUIT_BREAKER = "repeated_loss_circuit_breaker"
    INVENTORY_LIMIT = "inventory_limit"
    CORRELATION_LIMIT = "correlation_limit"


class ProhibitedRiskPractice(StrEnum):
    MARTINGALE = "martingale"
    UNCONTROLLED_AVERAGING_DOWN = "uncontrolled_averaging_down"
    AUTOMATIC_RISK_INCREASE = "automatic_risk_increase"
    RISK_LIMIT_SELF_MODIFICATION = "risk_limit_self_modification"


@dataclass(frozen=True, slots=True)
class RiskControlSet:
    control_set_id: str = "AI4BINANCE-RISK-CONTROLS"
    version: str = "2.0.0"
    domain: CanonicalDomainId = CanonicalDomainId.RISK
    controls: tuple[RiskControlId, ...] = tuple(RiskControlId)
    prohibited_practices: tuple[ProhibitedRiskPractice, ...] = tuple(
        ProhibitedRiskPractice
    )

    def __post_init__(self) -> None:
        _require_non_empty("risk control_set_id", self.control_set_id)
        _require_non_empty("risk control version", self.version)
        if self.domain is not CanonicalDomainId.RISK:
            raise ValueError("risk controls must belong to 08_RISK")
        if self.controls != tuple(RiskControlId):
            raise ValueError("risk controls must cover the canonical control set")
        if self.prohibited_practices != tuple(ProhibitedRiskPractice):
            raise ValueError("risk controls must preserve prohibited practices")


@dataclass(frozen=True, slots=True)
class RiskAssessmentContract:
    risk_assessment_id: str
    cycle_id: str
    decision_id: str
    market_risk: RiskState
    liquidity_risk: RiskState
    volatility_risk: RiskState
    execution_risk: RiskState
    strategy_risk: RiskState
    evidence_risk: RiskState
    portfolio_risk: RiskState
    governance_risk: RiskState
    result: RiskAssessmentResult
    model_risk: RiskState | None = None
    risk_budget_usdt: Decimal | None = None
    max_loss_usdt: Decimal | None = None
    risk_reward: Decimal | None = None
    blockers: tuple[str, ...] = ()
    domain: CanonicalDomainId = CanonicalDomainId.RISK

    def __post_init__(self) -> None:
        for field_name in ("risk_assessment_id", "cycle_id", "decision_id"):
            _require_non_empty(field_name, getattr(self, field_name))
        if self.domain is not CanonicalDomainId.RISK:
            raise ValueError("risk assessment must remain in 08_RISK")
        _require_unique("risk assessment blockers", self.blockers)
        for field_name in ("risk_budget_usdt", "max_loss_usdt"):
            value = getattr(self, field_name)
            if value is not None and value < ZERO_DECIMAL:
                raise ValueError(f"{field_name} cannot be negative")
        if self.risk_reward is not None and self.risk_reward <= ZERO_DECIMAL:
            raise ValueError("risk_reward must be positive when present")
        required_states = (
            self.market_risk,
            self.liquidity_risk,
            self.volatility_risk,
            self.execution_risk,
            self.strategy_risk,
            self.evidence_risk,
            self.portfolio_risk,
            self.governance_risk,
        )
        if self.result is RiskAssessmentResult.PASS and self.blockers:
            raise ValueError("PASS risk assessment cannot contain blockers")
        if self.result is RiskAssessmentResult.PASS and any(
            state in {RiskState.UNKNOWN, RiskState.CRITICAL}
            for state in required_states
        ):
            raise ValueError(
                "PASS risk assessment cannot contain unknown or critical risk"
            )
        if self.result is RiskAssessmentResult.BLOCK and not self.blockers:
            raise ValueError("BLOCK risk assessment requires blockers")


class PortfolioStateComponent(StrEnum):
    SPOT_BALANCES = "SpotBalances"
    FUTURES_BALANCES = "FuturesBalances"
    INVENTORY = "Inventory"
    POSITIONS = "Positions"
    OPEN_ORDERS = "OpenOrders"
    EXPOSURE = "Exposure"
    CORRELATION = "Correlation"
    RISK_BUDGET = "RiskBudget"


@dataclass(frozen=True, slots=True)
class PortfolioStateContract:
    portfolio_state_id: str
    cycle_id: str
    snapshot_id: str
    observed_at: datetime
    components: tuple[PortfolioStateComponent, ...] = tuple(PortfolioStateComponent)
    historical_backtest_consumable: bool = False
    domain: CanonicalDomainId = CanonicalDomainId.PORTFOLIO

    def __post_init__(self) -> None:
        for field_name in ("portfolio_state_id", "cycle_id", "snapshot_id"):
            _require_non_empty(field_name, getattr(self, field_name))
        _require_utc_timestamp("portfolio observed_at", self.observed_at)
        if self.domain is not CanonicalDomainId.PORTFOLIO:
            raise ValueError("portfolio state must remain in 09_PORTFOLIO")
        if self.components != tuple(PortfolioStateComponent):
            raise ValueError("portfolio state must cover every canonical component")
        if self.historical_backtest_consumable:
            raise ValueError(
                "Historical Backtest MUST NOT consume current PortfolioState"
            )


class ExecutionMode(StrEnum):
    MANUAL = "manual"
    DRY_RUN = "dry_run"
    PAPER = "paper"
    AUTO = "auto"
    LIVE = "live"


class ExecutionGateCheckId(StrEnum):
    EXPLICIT_USER_REQUEST = "explicit_user_request"
    TRADING_MODE_LIVE = "trading.mode == live"
    EXECUTION_ORDER_MODE_AUTO = "execution.order_mode == auto"
    ALLOW_AUTO_LIVE_ORDERS = "allow_auto_live_orders == true"
    CONFIRM_LIVE = "confirm_live == true"
    API_STATUS = "API_status == PASS"
    SERVER_TIME = "server_time == PASS"
    EXCHANGE_INFO = "exchange_info == PASS"
    FILTERS = "filters == PASS"
    BALANCES_KNOWN = "balances_known == true"
    INVENTORY_KNOWN = "inventory_known == true"
    NO_CONFLICTING_ORDERS = "conflicting_orders == false"
    DECISION_CURRENT = "decision_current == true"
    VALIDATION = "validation == PASS"
    WALK_FORWARD = "WF == PASS"
    OOS = "OOS == PASS"
    RISK_APPROVAL = "risk_approval == PASS"
    GOVERNANCE_APPROVAL = "governance_approval == PASS"
    SPREAD = "spread == PASS"
    SLIPPAGE = "slippage == PASS"
    LOSS_CONTROLS = "loss_controls == PASS"
    DECISION_LOGGED = "decision_logged == true"


class ExecutionRouteStep(StrEnum):
    AGENT_OBSERVATION = "AgentObservation"
    DETERMINISTIC_CORE = "DeterministicCore"
    RISK_ASSESSMENT = "RiskAssessment"
    VALIDATION = "Validation"
    DECISION_GOVERNANCE = "DecisionGovernance"
    EXECUTION_GATE = "ExecutionGate"
    EXECUTION = "Execution"


CANONICAL_EXECUTION_ROUTE: tuple[ExecutionRouteStep, ...] = tuple(ExecutionRouteStep)


@dataclass(frozen=True, slots=True)
class ExecutionGateResult:
    gate_result_id: str
    decision_id: str
    mode: ExecutionMode
    checks: MappingProxyType[ExecutionGateCheckId, bool]
    accepted: bool = False
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    domain: CanonicalDomainId = CanonicalDomainId.EXECUTION

    def __post_init__(self) -> None:
        for field_name in ("gate_result_id", "decision_id"):
            _require_non_empty(field_name, getattr(self, field_name))
        if self.domain is not CanonicalDomainId.EXECUTION:
            raise ValueError("execution gate must remain in 10_EXECUTION")
        if tuple(self.checks.keys()) != tuple(ExecutionGateCheckId):
            raise ValueError("execution gate checks must be canonical and ordered")
        _require_unique("execution gate blockers", self.blockers)
        missing_checks = tuple(
            check.value for check, passed in self.checks.items() if not passed
        )
        if missing_checks and self.execution_allowed:
            raise ValueError("failed execution gate checks must block execution")
        if missing_checks and self.accepted:
            raise ValueError("failed execution gate checks cannot be accepted")
        if missing_checks and self.blockers != missing_checks:
            raise ValueError("execution gate blockers must match failed checks")
        if not missing_checks and self.blockers:
            raise ValueError("passing execution gate cannot contain blockers")
        if self.accepted != self.execution_allowed:
            raise ValueError("accepted and execution_allowed must match")
        if self.mode is ExecutionMode.LIVE and missing_checks:
            object.__setattr__(self, "accepted", False)
            object.__setattr__(self, "execution_allowed", False)


def build_execution_gate_result(
    gate_result_id: str,
    decision_id: str,
    mode: ExecutionMode,
    checks: MappingProxyType[ExecutionGateCheckId, bool],
) -> ExecutionGateResult:
    """Evaluate canonical execution checks with one-failure live blocking."""
    blockers = tuple(check.value for check, passed in checks.items() if not passed)
    accepted = not blockers and mode is not ExecutionMode.LIVE
    execution_allowed = accepted
    if mode is ExecutionMode.LIVE:
        accepted = not blockers
        execution_allowed = not blockers
    return ExecutionGateResult(
        gate_result_id=gate_result_id,
        decision_id=decision_id,
        mode=mode,
        checks=checks,
        accepted=accepted,
        blockers=blockers,
        execution_allowed=execution_allowed,
    )


class TrailingStopDirection(StrEnum):
    LONG = "LONG"


class TrailingStopTrigger(StrEnum):
    TRAILING_STOP_EXIT = "TRAILING_STOP_EXIT"


class ClosureReviewDimension(StrEnum):
    TIGHTNESS = "tightness"
    VOLATILITY_EXPANSION = "volatility_expansion"
    HTF_WEAKNESS = "HTF_weakness"
    IGNORED_STRUCTURE_BREAK = "ignored_structure_break"
    STAGED_EXIT_ALTERNATIVE = "staged_exit_alternative"


@dataclass(frozen=True, slots=True)
class TrailingStopRuleContract:
    rule_id: str = "AI4BINANCE-TRAILING-STOP-LONG-ATR"
    version: str = "2.0.0"
    direction: TrailingStopDirection = TrailingStopDirection.LONG
    trailing_multiplier: Decimal = DEFAULT_TRAILING_MULTIPLIER
    formula: str = (
        "new_trailing_stop = max(previous_trailing_stop, "
        "current_price - trailing_multiplier * ATR)"
    )
    monotonic: bool = True
    trigger: TrailingStopTrigger = TrailingStopTrigger.TRAILING_STOP_EXIT
    closure_review_dimensions: tuple[ClosureReviewDimension, ...] = tuple(
        ClosureReviewDimension
    )
    domain: CanonicalDomainId = CanonicalDomainId.EXECUTION

    def __post_init__(self) -> None:
        _require_non_empty("trailing stop rule_id", self.rule_id)
        _require_non_empty("trailing stop version", self.version)
        if self.domain is not CanonicalDomainId.EXECUTION:
            raise ValueError("trailing stop rule must remain in 10_EXECUTION")
        if self.trailing_multiplier != DEFAULT_TRAILING_MULTIPLIER:
            raise ValueError("default trailing_multiplier must be 1.5 ATR")
        if not self.monotonic:
            raise ValueError("long trailing stop must never move down")
        if self.trigger is not TrailingStopTrigger.TRAILING_STOP_EXIT:
            raise ValueError("trailing stop trigger must be TRAILING_STOP_EXIT")
        if self.closure_review_dimensions != tuple(ClosureReviewDimension):
            raise ValueError("closure review dimensions must be canonical")


class ControlledLearningAllowedAction(StrEnum):
    OBSERVE = "observe"
    DETECT_RECURRING_FAILURE = "detect_recurring_failure"
    CLASSIFY = "classify"
    GENERATE_HYPOTHESIS = "generate_hypothesis"
    PROPOSE_CANDIDATE = "propose_candidate"
    RANK_CANDIDATE = "rank_candidate"
    STAGE_RESEARCH = "stage_research"


class ControlledLearningProhibitedAction(StrEnum):
    DEPLOY = "deploy"
    PROMOTE = "promote"
    MODIFY_LIVE_PARAMETER = "modify_live_parameter"
    MODIFY_RISK_LIMIT = "modify_risk_limit"
    DISABLE_GATE = "disable_gate"
    ENABLE_LIVE = "enable_live"
    CHANGE_AUTHORITY = "change_authority"


class ControlledLearningLifecycleStep(StrEnum):
    OUTCOME = "Outcome"
    CLOSURE_REVIEW = "ClosureReview"
    LESSON = "Lesson"
    HYPOTHESIS = "Hypothesis"
    LEARNING_CANDIDATE = "LearningCandidate"
    GOVERNANCE_INTAKE = "GovernanceIntake"
    RESEARCH_UNIT = "ResearchUnit"
    VALIDATION = "Validation"
    PROMOTION_REVIEW = "PromotionReview"


@dataclass(frozen=True, slots=True)
class ControlledLearningContract:
    learning_contract_id: str = "AI4BINANCE-CONTROLLED-AUTO-LEARN"
    version: str = "2.0.0"
    domain: CanonicalDomainId = CanonicalDomainId.LEARNING
    allowed_actions: tuple[ControlledLearningAllowedAction, ...] = tuple(
        ControlledLearningAllowedAction
    )
    prohibited_actions: tuple[ControlledLearningProhibitedAction, ...] = tuple(
        ControlledLearningProhibitedAction
    )
    lifecycle: tuple[ControlledLearningLifecycleStep, ...] = tuple(
        ControlledLearningLifecycleStep
    )
    execution_allowed: bool = False
    promotion_allowed: bool = False
    authority_change_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("learning_contract_id", self.learning_contract_id)
        _require_non_empty("learning contract version", self.version)
        if self.domain is not CanonicalDomainId.LEARNING:
            raise ValueError("controlled learning must remain in 12_LEARNING")
        if self.allowed_actions != tuple(ControlledLearningAllowedAction):
            raise ValueError("controlled learning allowed actions must be canonical")
        if self.prohibited_actions != tuple(ControlledLearningProhibitedAction):
            raise ValueError("controlled learning prohibited actions must be canonical")
        if self.lifecycle != tuple(ControlledLearningLifecycleStep):
            raise ValueError("controlled learning lifecycle must be canonical")
        if (
            self.execution_allowed
            or self.promotion_allowed
            or self.authority_change_allowed
        ):
            raise ValueError(
                "controlled learning cannot execute, promote or change authority"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("controlled learning cannot enable live eligibility")


class GovernancePrimitive(StrEnum):
    GOVERNANCE_REGISTRY = "GovernanceRegistry"
    GOVERNANCE_INTAKE = "GovernanceIntake"
    GOVERNANCE_DEFINITION_OF_READY = "GovernanceDefinitionOfReady"
    RISK_CRITICALITY_TIER = "RiskCriticalityTier"
    COMPONENT_CONTRACT = "ComponentContract"
    AUTHORITY_MODEL = "AuthorityModel"
    POLICY_AS_CODE = "PolicyAsCode"
    RUNTIME_POLICY_ENFORCEMENT = "RuntimePolicyEnforcement"
    INDEPENDENT_VALIDATION = "IndependentValidation"
    GOVERNANCE_DEFINITION_OF_DONE = "GovernanceDefinitionOfDone"
    GOVERNANCE_RELEASE_RECORD = "GovernanceReleaseRecord"
    APPROVED_OPERATING_ENVELOPE = "ApprovedOperatingEnvelope"
    CONTINUOUS_ASSURANCE = "ContinuousAssurance"
    GOVERNANCE_REVALIDATION = "GovernanceRevalidation"
    DECISION_LINEAGE = "DecisionLineage"
    RISK_BASED_ESCALATION = "RiskBasedEscalation"
    INCIDENT_MANAGEMENT = "IncidentManagement"
    PROBLEM_MANAGEMENT = "ProblemManagement"
    KILL_SWITCH = "KillSwitch"
    SAFE_STATE = "SafeState"
    COMPONENT_RETIREMENT = "ComponentRetirement"


class RiskCriticalityTier(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    TRADING_IMPACTING = "TRADING_IMPACTING"
    LIVE_CRITICAL = "LIVE_CRITICAL"


class GovernanceReadyCriterion(StrEnum):
    PURPOSE_DEFINED = "purpose_defined"
    OWNER_ASSIGNED = "owner_assigned"
    RISK_TIER_ASSIGNED = "risk_tier_assigned"
    INPUTS_DEFINED = "inputs_defined"
    OUTPUTS_DEFINED = "outputs_defined"
    DEPENDENCIES_IDENTIFIED = "dependencies_identified"
    DUPLICATE_CAPABILITY_CHECKED = "duplicate_capability_checked"
    EXPECTED_EVIDENCE_DEFINED = "expected_evidence_defined"
    ACCEPTANCE_CRITERIA_DEFINED = "acceptance_criteria_defined"
    AUTHORITY_DEFINED = "authority_defined"
    LICENSE_STATE_KNOWN = "license_state_known"


class GovernanceDoneCriterion(StrEnum):
    CONTRACT_DEFINED = "contract_defined"
    TESTS_PASS = "tests_PASS"  # noqa: S105  # nosec B105
    SECURITY_REVIEW_PASS = "security_review_PASS"  # noqa: S105  # nosec B105
    AUDIT_ENABLED = "audit_enabled"
    EVIDENCE_AVAILABLE = "evidence_available"
    ROLLBACK_READY = "rollback_ready"
    HUMAN_OVERSIGHT_DEFINED = "human_oversight_defined"
    DOCUMENTATION_COMPLETE = "documentation_complete"


class TradingImpactingDoneCriterion(StrEnum):
    BACKTEST_PASS = "Backtest_PASS"  # noqa: S105  # nosec B105
    WF_PASS = "WF_PASS"  # noqa: S105  # nosec B105
    OOS_PASS = "OOS_PASS"  # noqa: S105  # nosec B105
    ROBUSTNESS_PASS = "Robustness_PASS"  # noqa: S105  # nosec B105
    REGIME_VALIDATION_PASS = "Regime_Validation_PASS"  # noqa: S105  # nosec B105
    PAPER_VALIDATION_PASS = "Paper_Validation_PASS"  # noqa: S105  # nosec B105


class GovernanceReleaseEnvironment(StrEnum):
    RESEARCH = "research"
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class GovernanceApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    RESTRICTED = "RESTRICTED"
    REJECTED = "REJECTED"


class ContinuousAssuranceDomain(StrEnum):
    DATA_ASSURANCE = "DataAssurance"
    CAPABILITY_ASSURANCE = "CapabilityAssurance"
    STRATEGY_ASSURANCE = "StrategyAssurance"
    PERFORMANCE_ASSURANCE = "PerformanceAssurance"
    RISK_ASSURANCE = "RiskAssurance"
    OPERATIONAL_ASSURANCE = "OperationalAssurance"
    EVIDENCE_ASSURANCE = "EvidenceAssurance"
    SECURITY_ASSURANCE = "SecurityAssurance"
    GOVERNANCE_REVALIDATION = "GovernanceRevalidation"


class ContinuousAssuranceState(StrEnum):
    CONTINUE = "CONTINUE"
    RESTRICT = "RESTRICT"
    QUARANTINE = "QUARANTINE"
    SUSPEND = "SUSPEND"
    WITHDRAW = "WITHDRAW"
    DENY = "DENY"


class SafeStateAction(StrEnum):
    NO_NEW_TRADE = "NO_NEW_TRADE"
    NO_LIVE_EXECUTION = "NO_LIVE_EXECUTION"
    PRESERVE_STATE = "PRESERVE_STATE"
    CONTINUE_MONITORING = "CONTINUE_MONITORING"
    WRITE_INCIDENT = "WRITE_INCIDENT"
    REQUIRE_REVALIDATION = "REQUIRE_REVALIDATION"


@dataclass(frozen=True, slots=True)
class ApprovedOperatingEnvelopeExecution:
    default: ExecutionMode = ExecutionMode.PAPER
    auto_live: bool = False

    def __post_init__(self) -> None:
        if self.default is not ExecutionMode.PAPER:
            raise ValueError("approved operating envelope default execution is paper")
        if self.auto_live:
            raise ValueError("approved operating envelope cannot enable auto live")


@dataclass(frozen=True, slots=True)
class SafeState:
    safe_state_id: str = "AI4BINANCE-SAFE-STATE"
    actions: tuple[SafeStateAction, ...] = tuple(SafeStateAction)
    decision_result: str = "DENY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE

    def __post_init__(self) -> None:
        _require_non_empty("safe_state_id", self.safe_state_id)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("safe state must remain in 13_GOVERNANCE")
        if self.actions != tuple(SafeStateAction):
            raise ValueError("safe state must include every required action")
        if self.decision_result != "DENY":
            raise ValueError("unknown critical state must DENY")
        if self.execution_allowed:
            raise ValueError("safe state cannot allow execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("safe state cannot unblock live execution")


class AdvisoryLlmAllowedAction(StrEnum):
    RETRIEVE = "retrieve"
    CLASSIFY = "classify"
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    IDENTIFY_CONFLICTS = "identify_conflicts"
    PROPOSE_RESEARCH = "propose_research"
    RECOMMEND_CANDIDATE_EXPERIMENTS = "recommend_candidate_experiments"


class AdvisoryLlmProhibitedAction(StrEnum):
    AUTHORIZE_TRADES = "authorize_trades"
    OVERRIDE_RISK = "override_risk"
    OVERRIDE_GOVERNANCE = "override_governance"
    BYPASS_HARD_GATES = "bypass_hard_gates"
    CHANGE_APPROVED_RISK_LIMITS = "change_approved_risk_limits"
    PROMOTE_PARAMETERS = "promote_parameters"
    PROMOTE_STRATEGIES = "promote_strategies"
    EXECUTE_LIVE_ORDERS = "execute_live_orders"


class DeterministicCoreResponsibility(StrEnum):
    FEATURE_CALCULATION = "feature_calculation"
    SETUP_QUALIFICATION = "setup_qualification"
    DETERMINISTIC_SCORING = "deterministic_scoring"
    BLOCKER_EVALUATION = "blocker_evaluation"
    ACTION_CLASSIFICATION = "action_classification"
    RISK_CALCULATIONS = "risk_calculations"
    EXECUTION_ELIGIBILITY = "execution_eligibility"


class NeverFabricateDataKind(StrEnum):
    PRICE = "price"
    CANDLES = "candles"
    INDICATORS = "indicators"
    ORDER_BOOK = "order_book"
    SPREAD = "spread"
    LIQUIDITY = "liquidity"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LONG_SHORT_RATIOS = "long_short_ratios"
    WALLET_BALANCES = "wallet_balances"
    POSITIONS = "positions"
    OPEN_ORDERS = "open_orders"
    WHALE_DATA = "whale_data"
    ON_CHAIN_DATA = "on_chain_data"
    NEWS = "news"
    EXECUTION_RESULTS = "execution_results"


class AuditTraceField(StrEnum):
    CYCLE_ID = "cycle_id"
    SNAPSHOT_ID = "snapshot_id"
    DECISION_ID = "decision_id"
    COMPONENT_VERSIONS = "component_versions"
    INPUT_REFERENCES = "input_references"
    EVIDENCE_REFERENCES = "evidence_references"
    POLICY_VERSIONS = "policy_versions"
    RISK_RESULTS = "risk_results"
    GATE_RESULTS = "gate_results"
    EXECUTION_RESULTS = "execution_results"


class CoreVNextDescriptor(StrEnum):
    AI4BINANCE = "AI4BINANCE"
    ONTOLOGY_DRIVEN = "Ontology-Driven"
    EVIDENCE_BASED = "Evidence-Based"
    RISK_CONTROLLED = "Risk-Controlled"
    DETERMINISTIC = "Deterministic"
    MULTI_AGENT = "Multi-Agent"
    CONTINUOUSLY_ASSURED = "Continuously-Assured"
    ALGORITHMIC_TRADING_DECISION_PLATFORM = "Algorithmic Trading Decision Platform"


class CoreVNextPrinciple(StrEnum):
    DATA_CREATES_OBSERVATIONS = "DATA creates observations"
    EVIDENCE_SUPPORTS_CLAIMS = "EVIDENCE supports claims"
    AGENTS_ANALYZE = "AGENTS analyze"
    STRATEGIES_IDENTIFY_SETUPS = "STRATEGIES identify setups"
    SCORING_RANKS_OPPORTUNITIES = "SCORING ranks opportunities"
    GOVERNANCE_DECIDES_ELIGIBILITY = "GOVERNANCE decides eligibility"
    RISK_CONSTRAINS_EXPOSURE = "RISK constrains exposure"
    EXECUTION_OBEYS = "EXECUTION obeys"
    AUDIT_PRESERVES_LINEAGE = "AUDIT preserves lineage"
    HUMAN_RETAINS_AUTHORITY = "HUMAN retains authority"
    LEARNING_PROPOSES = "LEARNING proposes"
    VALIDATION_PROMOTES = "VALIDATION promotes"


class UnsafeDecisionState(StrEnum):
    UNKNOWN = "UNKNOWN"
    INCONSISTENT = "INCONSISTENT"
    UNVALIDATED = "UNVALIDATED"
    UNAUTHORIZED = "UNAUTHORIZED"
    STALE = "STALE"
    UNSAFE = "UNSAFE"


@dataclass(frozen=True, slots=True)
class FailClosedDecisionRule:
    unsafe_states: tuple[UnsafeDecisionState, ...] = tuple(UnsafeDecisionState)
    result: str = "NO_TRADE"

    def __post_init__(self) -> None:
        if self.unsafe_states != tuple(UnsafeDecisionState):
            raise ValueError("fail-closed unsafe states must be complete")
        if self.result != "NO_TRADE":
            raise ValueError("unsafe states must map to NO_TRADE")


@dataclass(frozen=True, slots=True)
class CoreVNextIdentity:
    identity_id: str = "AI4BINANCE-CORE-VNEXT-IDENTITY"
    version: str = "2.0.0"
    title: str = "AI4BINANCE CORE vNext"
    descriptors: tuple[CoreVNextDescriptor, ...] = tuple(CoreVNextDescriptor)
    principles: tuple[CoreVNextPrinciple, ...] = tuple(CoreVNextPrinciple)
    fail_closed_rule: FailClosedDecisionRule = field(
        default_factory=FailClosedDecisionRule
    )
    final_live_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("core vNext identity_id", self.identity_id)
        _require_non_empty("core vNext identity version", self.version)
        if self.title != "AI4BINANCE CORE vNext":
            raise ValueError("core vNext title must remain canonical")
        if self.descriptors != tuple(CoreVNextDescriptor):
            raise ValueError("core vNext descriptors must remain canonical")
        if self.principles != tuple(CoreVNextPrinciple):
            raise ValueError("core vNext principles must remain canonical")
        if self.fail_closed_rule.result != "NO_TRADE":
            raise ValueError("core vNext unsafe states must map to NO_TRADE")
        if self.final_live_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("core vNext live status must remain LIVE_ORDER_BLOCKED")


@dataclass(frozen=True, slots=True)
class MasterCoreInstructions:
    instruction_id: str = "AI4BINANCE-MASTER-CORE-INSTRUCTIONS"
    version: str = "2.0"
    mission: str = (
        "Operate as an ontology-driven, evidence-based, deterministic, "
        "risk-controlled and continuously assured algorithmic trading research "
        "and decision-support platform for Binance Spot/Futures."
    )
    defaults: CoreMeta = field(default_factory=CoreMeta)
    canonical_cycle: tuple[CanonicalCycleStep, ...] = tuple(CanonicalCycleStep)
    decision_order: tuple[DecisionPipelineStage, ...] = tuple(DecisionPipelineStage)
    llm_allowed_actions: tuple[AdvisoryLlmAllowedAction, ...] = tuple(
        AdvisoryLlmAllowedAction
    )
    llm_prohibited_actions: tuple[AdvisoryLlmProhibitedAction, ...] = tuple(
        AdvisoryLlmProhibitedAction
    )
    deterministic_core_owns: tuple[DeterministicCoreResponsibility, ...] = tuple(
        DeterministicCoreResponsibility
    )
    never_fabricate: tuple[NeverFabricateDataKind, ...] = tuple(NeverFabricateDataKind)
    required_validation_evidence: tuple[ValidationStage, ...] = (
        ValidationStage.BACKTEST,
        ValidationStage.WALK_FORWARD,
        ValidationStage.OOS,
        ValidationStage.MONTE_CARLO,
        ValidationStage.REGIME_TESTS,
    )
    safe_state_actions: tuple[SafeStateAction, ...] = tuple(SafeStateAction)
    audit_trace_fields: tuple[AuditTraceField, ...] = tuple(AuditTraceField)
    agents_final_decision_authority: bool = False
    llm_advisory_only: bool = True
    search_first_for_reasons_not_to_trade: bool = True
    high_score_overrides_hard_blocker: bool = False
    social_claim_can_authorize_trade: bool = False
    missing_evidence_result: str = "UNKNOWN"
    data_unavailable_result: str = "DATA_UNAVAILABLE"
    weak_evidence_result: str = "LOW_CONFIDENCE"
    unknown_critical_state_result: str = "DENY / NO_TRADE"
    live_default_status: str = "LIVE_ORDER_BLOCKED"
    immutable_historical_records: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("master core instruction_id", self.instruction_id)
        if self.version != "2.0":
            raise ValueError("master core instructions version must remain 2.0")
        _require_non_empty("master core mission", self.mission)
        if self.defaults.allow_auto_live_orders:
            raise ValueError("master core defaults cannot allow auto live orders")
        if self.defaults.trading_mode != "paper":
            raise ValueError("master core trading mode must default to paper")
        if self.defaults.execution_order_mode != "manual":
            raise ValueError("master core order mode must default to manual")
        if self.canonical_cycle != tuple(CanonicalCycleStep):
            raise ValueError("master core canonical cycle order is immutable")
        if self.decision_order != tuple(DecisionPipelineStage):
            raise ValueError("master core decision order is immutable")
        if self.llm_allowed_actions != tuple(AdvisoryLlmAllowedAction):
            raise ValueError("master core LLM allowed actions must be complete")
        if self.llm_prohibited_actions != tuple(AdvisoryLlmProhibitedAction):
            raise ValueError("master core LLM prohibited actions must be complete")
        if self.deterministic_core_owns != tuple(DeterministicCoreResponsibility):
            raise ValueError("deterministic core responsibilities must be complete")
        if self.never_fabricate != tuple(NeverFabricateDataKind):
            raise ValueError("master core never-fabricate data list must be complete")
        required_validation = (
            ValidationStage.BACKTEST,
            ValidationStage.WALK_FORWARD,
            ValidationStage.OOS,
            ValidationStage.MONTE_CARLO,
            ValidationStage.REGIME_TESTS,
        )
        if self.required_validation_evidence != required_validation:
            raise ValueError("master core validation evidence requirements drifted")
        if self.safe_state_actions != tuple(SafeStateAction):
            raise ValueError("master core safe state actions must be complete")
        if self.audit_trace_fields != tuple(AuditTraceField):
            raise ValueError("master core audit trace fields must be complete")
        if self.agents_final_decision_authority:
            raise ValueError("agents cannot own final trade decisions")
        if not self.llm_advisory_only:
            raise ValueError("LLMs must remain advisory only")
        if not self.search_first_for_reasons_not_to_trade:
            raise ValueError("must search first for reasons not to trade")
        if self.high_score_overrides_hard_blocker:
            raise ValueError("high score cannot override a hard blocker")
        if self.social_claim_can_authorize_trade:
            raise ValueError("social claim alone cannot authorize a trade")
        if self.missing_evidence_result != "UNKNOWN":
            raise ValueError("missing evidence must remain UNKNOWN")
        if self.data_unavailable_result != "DATA_UNAVAILABLE":
            raise ValueError("unavailable data must return DATA_UNAVAILABLE")
        if self.weak_evidence_result != "LOW_CONFIDENCE":
            raise ValueError("weak evidence must return LOW_CONFIDENCE")
        if self.unknown_critical_state_result != "DENY / NO_TRADE":
            raise ValueError("unknown critical state must DENY / NO_TRADE")
        if self.live_default_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("live default status must remain LIVE_ORDER_BLOCKED")
        if not self.immutable_historical_records:
            raise ValueError("historical evidence and decision records are immutable")


class PlatformFlowNode(StrEnum):
    ENTERPRISE_AI = "AI4BINANCE EnterpriseAI vNext"
    GOVERNANCE_REGISTRY = "Governance Registry"
    EVENT_FABRIC = "Event Fabric"
    MARKET_DATA = "Market Data"
    DATA_QUALITY = "Data Quality"
    CANONICAL_SNAPSHOT = "Canonical Snapshot"
    FEATURE_SNAPSHOT = "Feature Snapshot"
    EXTERNAL_INTELLIGENCE = "External Intelligence"
    ANALYTIC_CAPABILITIES = "Analytic Capabilities"
    EVIDENCE_FABRIC = "Evidence Fabric"
    AGENT_OBSERVATIONS = "Agent Observations"
    EVIDENCE_COMPLETENESS = "Evidence Completeness"
    SETUP_ENGINE = "Setup Engine"
    DETERMINISTIC_CORE = "Deterministic Core"
    ACTION_CEILING = "Action Ceiling"
    RISK_ENGINE = "Risk Engine"
    DECISION_GOVERNANCE = "Decision Governance"
    EXECUTION_GATES = "Execution Gates"
    NO_TRADE = "NO_TRADE"
    PAPER_MANUAL = "PAPER/MANUAL"
    EXECUTION_RECORD = "Execution Record"
    POSITION_LIFECYCLE = "Position Lifecycle"
    CLOSURE_REVIEW = "Closure Review"
    LESSON = "Lesson"
    LEARNING_CANDIDATE = "Learning Candidate"
    RESEARCH_UNIT = "Research Unit"
    VALIDATION = "Validation"
    GOVERNED_PROMOTION = "Governed Promotion"


@dataclass(frozen=True, slots=True)
class PlatformFlowEdge:
    source: PlatformFlowNode
    target: PlatformFlowNode


class CriticalArchitectureImprovement(StrEnum):
    CAPABILITY_FIRST_GOVERNANCE = "Capability-first governance"
    FORMULA_ORACLE_LINEAGE = "Formula/Oracle lineage"
    CAPABILITY_COVERAGE_MATRIX = "Capability Coverage Matrix"
    APPEND_ONLY_EVIDENCE_FABRIC = "append-only Evidence Fabric"
    EVIDENCE_COMPLETENESS_GATE = "Evidence Completeness Gate"
    ACTION_CEILING = "Action Ceiling"
    RESEARCH_UNIT_LIFECYCLE = "ResearchUnit lifecycle"
    SINGLE_EVENT_ENVELOPE = "single EventEnvelope standard"


@dataclass(frozen=True, slots=True)
class GovernedCapabilityPlatformFlow:
    flow_id: str = "AI4BINANCE-GOVERNED-CAPABILITY-PLATFORM-FLOW"
    version: str = "2.0.0"
    nodes: tuple[PlatformFlowNode, ...] = tuple(PlatformFlowNode)
    edges: tuple[PlatformFlowEdge, ...] = ()
    critical_improvements: tuple[CriticalArchitectureImprovement, ...] = tuple(
        CriticalArchitectureImprovement
    )
    model_identity: str = "governed capability platform"
    agent_role: str = "actor executing governed capabilities"
    multi_agent_trading_system: bool = False
    agent_is_feature_proxy: bool = False
    duplicate_computation_risk_reduced: bool = True
    fake_maturity_risk_reduced: bool = True
    oos_free_hard_gate_risk_reduced: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("platform flow_id", self.flow_id)
        _require_non_empty("platform flow version", self.version)
        _require_non_empty("platform model identity", self.model_identity)
        _require_non_empty("platform agent role", self.agent_role)
        if self.nodes != tuple(PlatformFlowNode):
            raise ValueError("platform flow nodes must remain canonical")
        if self.edges != _canonical_platform_flow_edges():
            raise ValueError("platform flow edges must remain canonical")
        if self.critical_improvements != tuple(CriticalArchitectureImprovement):
            raise ValueError("critical architecture improvements must be complete")
        if self.model_identity != "governed capability platform":
            raise ValueError("AI4BINANCE must be modeled as a capability platform")
        if self.agent_role != "actor executing governed capabilities":
            raise ValueError("agents must remain actors, not feature authority")
        if self.multi_agent_trading_system:
            raise ValueError(
                "AI4BINANCE is not modeled as a multi-agent trading system"
            )
        if self.agent_is_feature_proxy:
            raise ValueError("agent presence must not imply capability maturity")
        if not self.duplicate_computation_risk_reduced:
            raise ValueError("platform flow must reduce duplicate computation risk")
        if not self.fake_maturity_risk_reduced:
            raise ValueError("platform flow must reduce fake maturity risk")
        if not self.oos_free_hard_gate_risk_reduced:
            raise ValueError("platform flow must reduce OOS-free hard-gate risk")


def _flow_edge(
    source: PlatformFlowNode,
    target: PlatformFlowNode,
) -> PlatformFlowEdge:
    return PlatformFlowEdge(source, target)


def _canonical_platform_flow_edges() -> tuple[PlatformFlowEdge, ...]:
    return (
        _flow_edge(
            PlatformFlowNode.ENTERPRISE_AI, PlatformFlowNode.GOVERNANCE_REGISTRY
        ),
        _flow_edge(PlatformFlowNode.GOVERNANCE_REGISTRY, PlatformFlowNode.EVENT_FABRIC),
        _flow_edge(PlatformFlowNode.EVENT_FABRIC, PlatformFlowNode.MARKET_DATA),
        _flow_edge(PlatformFlowNode.MARKET_DATA, PlatformFlowNode.DATA_QUALITY),
        _flow_edge(PlatformFlowNode.DATA_QUALITY, PlatformFlowNode.CANONICAL_SNAPSHOT),
        _flow_edge(
            PlatformFlowNode.CANONICAL_SNAPSHOT, PlatformFlowNode.FEATURE_SNAPSHOT
        ),
        _flow_edge(
            PlatformFlowNode.FEATURE_SNAPSHOT,
            PlatformFlowNode.EXTERNAL_INTELLIGENCE,
        ),
        _flow_edge(
            PlatformFlowNode.FEATURE_SNAPSHOT,
            PlatformFlowNode.ANALYTIC_CAPABILITIES,
        ),
        _flow_edge(
            PlatformFlowNode.EXTERNAL_INTELLIGENCE, PlatformFlowNode.EVIDENCE_FABRIC
        ),
        _flow_edge(
            PlatformFlowNode.ANALYTIC_CAPABILITIES, PlatformFlowNode.AGENT_OBSERVATIONS
        ),
        _flow_edge(
            PlatformFlowNode.EVIDENCE_FABRIC,
            PlatformFlowNode.EVIDENCE_COMPLETENESS,
        ),
        _flow_edge(
            PlatformFlowNode.AGENT_OBSERVATIONS,
            PlatformFlowNode.EVIDENCE_COMPLETENESS,
        ),
        _flow_edge(
            PlatformFlowNode.EVIDENCE_COMPLETENESS, PlatformFlowNode.SETUP_ENGINE
        ),
        _flow_edge(PlatformFlowNode.SETUP_ENGINE, PlatformFlowNode.DETERMINISTIC_CORE),
        _flow_edge(
            PlatformFlowNode.DETERMINISTIC_CORE, PlatformFlowNode.ACTION_CEILING
        ),
        _flow_edge(PlatformFlowNode.ACTION_CEILING, PlatformFlowNode.RISK_ENGINE),
        _flow_edge(PlatformFlowNode.RISK_ENGINE, PlatformFlowNode.DECISION_GOVERNANCE),
        _flow_edge(
            PlatformFlowNode.DECISION_GOVERNANCE, PlatformFlowNode.EXECUTION_GATES
        ),
        _flow_edge(PlatformFlowNode.EXECUTION_GATES, PlatformFlowNode.NO_TRADE),
        _flow_edge(PlatformFlowNode.EXECUTION_GATES, PlatformFlowNode.PAPER_MANUAL),
        _flow_edge(PlatformFlowNode.PAPER_MANUAL, PlatformFlowNode.EXECUTION_RECORD),
        _flow_edge(
            PlatformFlowNode.EXECUTION_RECORD, PlatformFlowNode.POSITION_LIFECYCLE
        ),
        _flow_edge(
            PlatformFlowNode.POSITION_LIFECYCLE, PlatformFlowNode.CLOSURE_REVIEW
        ),
        _flow_edge(PlatformFlowNode.CLOSURE_REVIEW, PlatformFlowNode.LESSON),
        _flow_edge(PlatformFlowNode.LESSON, PlatformFlowNode.LEARNING_CANDIDATE),
        _flow_edge(PlatformFlowNode.LEARNING_CANDIDATE, PlatformFlowNode.RESEARCH_UNIT),
        _flow_edge(PlatformFlowNode.RESEARCH_UNIT, PlatformFlowNode.VALIDATION),
        _flow_edge(PlatformFlowNode.VALIDATION, PlatformFlowNode.GOVERNED_PROMOTION),
    )


def build_governed_capability_platform_flow() -> GovernedCapabilityPlatformFlow:
    return GovernedCapabilityPlatformFlow(edges=_canonical_platform_flow_edges())


class HumanDecisionColumn(StrEnum):
    COIN = "Coin"
    DIRECTION = "Direction"
    QUALITY = "Quality"
    ORDER = "Order"
    ENTRY = "Entry"
    STOP_LOSS = "Stop Loss"
    TP1 = "TP1"
    TP2 = "TP2"
    TP3 = "TP3"
    LEVERAGE = "Leverage"
    BUDGET_MARGIN = "Budget/Margin"
    RISK_REWARD = "R:R"
    NEWS_RISK = "News Risk"
    DECISION = "Decision"


class StandardDecisionSection(StrEnum):
    BASIC_DECISION = "Basic Decision"
    MARKET_OUTLOOK = "Market Outlook"
    SETUP_TECHNICAL_EVIDENCE = "Setup & Technical Evidence"
    LIQUIDITY_DERIVATIVES_INTELLIGENCE = "Liquidity / Derivatives / Intelligence"
    RISK_GOVERNANCE = "Risk & Governance"
    TRADE_PLAN = "Trade Plan"
    EXECUTION_TAGGING = "Execution Tagging"
    CLOSURE_REVIEW = "Closure Review"
    LEARNING_RECORD = "Learning Record"


class DecisionLifecycleState(StrEnum):
    CREATED = "CREATED"
    DATA_PENDING = "DATA_PENDING"
    DATA_VALIDATED = "DATA_VALIDATED"
    SNAPSHOT_READY = "SNAPSHOT_READY"
    FEATURES_READY = "FEATURES_READY"
    OBSERVATIONS_READY = "OBSERVATIONS_READY"
    EVIDENCE_VALIDATED = "EVIDENCE_VALIDATED"
    SETUP_EVALUATED = "SETUP_EVALUATED"
    DECISION_EVALUATED = "DECISION_EVALUATED"
    RISK_EVALUATED = "RISK_EVALUATED"
    GOVERNANCE_EVALUATED = "GOVERNANCE_EVALUATED"
    EXECUTION_GATE_EVALUATED = "EXECUTION_GATE_EVALUATED"


class DecisionTerminalState(StrEnum):
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"
    HOLD = "HOLD"
    PAPER_READY = "PAPER_READY"
    MANUAL_READY = "MANUAL_READY"
    LIVE_BLOCKED = "LIVE_BLOCKED"
    EXECUTED = "EXECUTED"


def _canonical_decision_output_template() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "meta": {
            "timestamp": None,
            "cycle_id": None,
            "snapshot_id": None,
            "decision_id": None,
            "trade_id": None,
            "symbol": "HOTUSDT",
            "market": "SPOT",
        },
        "data_state": {
            "market_data_status": "UNKNOWN",
            "data_quality_status": "UNKNOWN",
            "freshness_status": "UNKNOWN",
            "missing_feeds": [],
        },
        "market_outlook": {
            "bias_1d": "UNKNOWN",
            "bias_4h": "UNKNOWN",
            "bias_1h": "UNKNOWN",
            "regime": "UNKNOWN",
            "volatility_state": "UNKNOWN",
            "support": [],
            "resistance": [],
            "fibonacci": {},
            "macro_cycle": "UNKNOWN",
            "setup_radar": [],
        },
        "observations": {
            "agent_observation_ids": [],
            "capability_ids": [],
            "evidence_ids": [],
            "conflicting_evidence_ids": [],
        },
        "evidence_completeness": {
            "score": None,
            "minimum_met": False,
            "missing_domains": [],
            "conflicts": [],
        },
        "setup": {
            "setup_id": None,
            "name": None,
            "timeframe": None,
            "pattern_type": None,
            "quality": "NO_TRADE",
            "trigger_status": "UNKNOWN",
        },
        "scores": {
            "weight_set_id": None,
            "trend_score": None,
            "volatility_score": None,
            "momentum_score": None,
            "volume_score": None,
            "price_action_score": None,
            "structure_score": None,
            "fib_score": None,
            "pattern_score": None,
            "cycle_score": None,
            "mtf_score": None,
            "sentiment_score": None,
            "risk_penalty_score": None,
            "final_signal_score": None,
        },
        "decision": {
            "action": "NO_TRADE",
            "confidence": None,
            "reason_codes": [],
            "reason_summary": [],
            "blockers": [],
            "action_ceiling": "PAPER",
            "execution_allowed": False,
        },
        "risk": {
            "risk_assessment_id": None,
            "risk_class": "UNKNOWN",
            "risk_budget_usdt": None,
            "max_loss_usdt": None,
            "risk_reward": None,
            "blockers": [],
            "result": "BLOCK",
        },
        "trade_plan": {
            "entry": None,
            "entry_rationale": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "trailing_stop": None,
            "size_usdt": None,
            "invalidation": None,
            "discovery_method": None,
            "markets": [],
            "timeframes": [],
            "market_conditions": {
                "trend_state": "UNKNOWN",
                "range_state": "UNKNOWN",
                "choppy_state": "UNKNOWN",
                "volatile_state": "UNKNOWN",
                "determination_method": None,
                "early_exit_conditions": [],
            },
            "risk_controls": {
                "position_size": None,
                "daily_loss_limit": None,
                "weekly_loss_limit": None,
                "monthly_loss_limit": None,
                "max_positions": None,
                "max_capital_per_position": None,
                "hold_through_major_events": None,
                "hold_overnight": None,
                "hold_weekend": None,
            },
            "review": {
                "review_cadence": None,
                "mistake_tracking": [],
                "improvement_actions": [],
            },
        },
        "governance": {
            "governance_release_record_id": None,
            "approved_operating_envelope_id": None,
            "strategy_version": None,
            "parameter_set_id": None,
            "policy_version": None,
            "risk_policy_version": None,
            "validation": {
                "backtest": "UNKNOWN",
                "walk_forward": "UNKNOWN",
                "oos": "UNKNOWN",
                "robustness": "UNKNOWN",
                "regime_validation": "UNKNOWN",
            },
            "continuous_assurance": "UNKNOWN",
            "governance_result": "BLOCK",
        },
        "execution": {
            "trading_mode": "paper",
            "order_mode": "manual",
            "gate_result_id": None,
            "status": "NOT_EXECUTED",
            "accepted": False,
            "filled": False,
            "slippage": None,
        },
        "audit": {
            "lineage_id": None,
            "event_ids": [],
            "control_results": [],
            "incident_ids": [],
        },
        "learning": {
            "closure_review_id": None,
            "lesson_ids": [],
            "learning_candidate_ids": [],
            "promotion_status": "NONE",
        },
    }


@dataclass(frozen=True, slots=True)
class HumanDecisionOutputFormat:
    format_id: str = "AI4BINANCE-HUMAN-DECISION-OUTPUT"
    version: str = "2.0.0"
    columns: tuple[HumanDecisionColumn, ...] = tuple(HumanDecisionColumn)
    spot_leverage_value: str = "N/A"
    unavailable_value: str = "DATA_UNAVAILABLE"
    low_confidence_value: str = "LOW_CONFIDENCE"
    fabricate_missing_prices_allowed: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("human output format_id", self.format_id)
        _require_non_empty("human output format version", self.version)
        if self.columns != tuple(HumanDecisionColumn):
            raise ValueError("human decision output columns must remain canonical")
        if self.spot_leverage_value != "N/A":
            raise ValueError("Spot leverage must render as N/A")
        if self.unavailable_value != "DATA_UNAVAILABLE":
            raise ValueError("missing data must render as DATA_UNAVAILABLE")
        if self.low_confidence_value != "LOW_CONFIDENCE":
            raise ValueError("low confidence must render as LOW_CONFIDENCE")
        if self.fabricate_missing_prices_allowed:
            raise ValueError("missing prices must never be fabricated")


@dataclass(frozen=True, slots=True)
class StandardDecisionOutputContract:
    contract_id: str = "AI4BINANCE-STANDARD-DECISION-OUTPUT"
    version: str = "2.0.0"
    sections: tuple[StandardDecisionSection, ...] = tuple(StandardDecisionSection)
    missing_feeds_value: str = "DATA_UNAVAILABLE"
    default_quality: str = "NO_TRADE"
    execution_allowed_default: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("standard decision output contract_id", self.contract_id)
        _require_non_empty("standard decision output version", self.version)
        if self.sections != tuple(StandardDecisionSection):
            raise ValueError("standard decision output sections must remain canonical")
        if self.missing_feeds_value != "DATA_UNAVAILABLE":
            raise ValueError("missing feeds must be explicit DATA_UNAVAILABLE")
        if self.default_quality != "NO_TRADE":
            raise ValueError("default setup quality must remain NO_TRADE")
        if self.execution_allowed_default:
            raise ValueError("decision output cannot default to execution allowed")


@dataclass(frozen=True, slots=True)
class CanonicalDecisionOutputContract:
    contract_id: str = "AI4BINANCE-CANONICAL-DECISION-OUTPUT"
    schema_version: str = "2.0.0"
    template: dict[str, Any] = field(
        default_factory=_canonical_decision_output_template
    )
    no_fabricated_prices: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("canonical decision output contract_id", self.contract_id)
        if self.schema_version != "2.0.0":
            raise ValueError("canonical decision output schema_version must be 2.0.0")
        if self.template != _canonical_decision_output_template():
            raise ValueError("canonical decision output template drifted")
        if not self.no_fabricated_prices:
            raise ValueError(
                "canonical decision output must prohibit fabricated prices"
            )


@dataclass(frozen=True, slots=True)
class CanonicalDecisionStateMachine:
    machine_id: str = "AI4BINANCE-CANONICAL-DECISION-STATE-MACHINE"
    version: str = "2.0.0"
    progression: tuple[DecisionLifecycleState, ...] = tuple(DecisionLifecycleState)
    terminal_states: tuple[DecisionTerminalState, ...] = tuple(DecisionTerminalState)

    def __post_init__(self) -> None:
        _require_non_empty("decision state machine_id", self.machine_id)
        _require_non_empty("decision state machine version", self.version)
        if self.progression != tuple(DecisionLifecycleState):
            raise ValueError("decision state machine progression must be canonical")
        if self.terminal_states != tuple(DecisionTerminalState):
            raise ValueError("decision terminal states must be canonical")


@dataclass(frozen=True, slots=True)
class ContinuousAssuranceEngine:
    engine_id: str = "AI4BINANCE-CONTINUOUS-ASSURANCE"
    version: str = "2.0.0"
    domains: tuple[ContinuousAssuranceDomain, ...] = tuple(ContinuousAssuranceDomain)
    possible_states: tuple[ContinuousAssuranceState, ...] = tuple(
        ContinuousAssuranceState
    )
    unknown_critical_state: ContinuousAssuranceState = ContinuousAssuranceState.DENY
    safe_state: SafeState = field(default_factory=SafeState)
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("continuous assurance engine_id", self.engine_id)
        _require_non_empty("continuous assurance version", self.version)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("continuous assurance must remain in 13_GOVERNANCE")
        if self.domains != tuple(ContinuousAssuranceDomain):
            raise ValueError("continuous assurance domains must be canonical")
        if self.possible_states != tuple(ContinuousAssuranceState):
            raise ValueError("continuous assurance states must be canonical")
        if self.unknown_critical_state is not ContinuousAssuranceState.DENY:
            raise ValueError("unknown critical state must DENY")
        if self.safe_state.decision_result != "DENY":
            raise ValueError("continuous assurance safe state must deny")
        if self.execution_allowed:
            raise ValueError("continuous assurance cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("continuous assurance cannot unblock live execution")


@dataclass(frozen=True, slots=True)
class GovernanceDefinitionOfReady:
    component_id: str
    criteria: tuple[GovernanceReadyCriterion, ...] = tuple(GovernanceReadyCriterion)
    ready: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE

    def __post_init__(self) -> None:
        _require_non_empty("component_id", self.component_id)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("Definition of Ready must remain in 13_GOVERNANCE")
        if self.criteria != tuple(GovernanceReadyCriterion):
            raise ValueError("Definition of Ready must cover every criterion")
        if not self.ready:
            raise ValueError("component cannot enter development until ready")


@dataclass(frozen=True, slots=True)
class GovernanceDefinitionOfDone:
    component_id: str
    criteria: tuple[GovernanceDoneCriterion, ...] = tuple(GovernanceDoneCriterion)
    trading_impacting_criteria: tuple[TradingImpactingDoneCriterion, ...] = ()
    trading_impacting: bool = False
    done: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE

    def __post_init__(self) -> None:
        _require_non_empty("component_id", self.component_id)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("Definition of Done must remain in 13_GOVERNANCE")
        if self.criteria != tuple(GovernanceDoneCriterion):
            raise ValueError("Definition of Done must cover minimum criteria")
        if self.trading_impacting:
            if self.trading_impacting_criteria != tuple(TradingImpactingDoneCriterion):
                raise ValueError(
                    "trading-impacting Definition of Done requires validation PASS"
                )
        elif self.trading_impacting_criteria:
            raise ValueError(
                "non-trading Definition of Done cannot claim trading gates"
            )
        if not self.done:
            raise ValueError("component cannot be marked done until all gates pass")


@dataclass(frozen=True, slots=True)
class GovernanceApproval:
    status: GovernanceApprovalStatus
    approver: str = "HUMAN_REVIEW_REQUIRED"

    def __post_init__(self) -> None:
        _require_non_empty("approver", self.approver)


@dataclass(frozen=True, slots=True)
class GovernancePrimitiveCatalog:
    catalog_id: str = "AI4BINANCE-GOVERNANCE-PRIMITIVES"
    version: str = "2.0.0"
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE
    primitives: tuple[GovernancePrimitive, ...] = tuple(GovernancePrimitive)

    def __post_init__(self) -> None:
        _require_non_empty("governance primitive catalog_id", self.catalog_id)
        _require_non_empty("governance primitive version", self.version)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("governance primitives must remain in 13_GOVERNANCE")
        if self.primitives != tuple(GovernancePrimitive):
            raise ValueError("governance primitive catalog must be canonical")


@dataclass(frozen=True, slots=True)
class ApprovedOperatingEnvelope:
    envelope_id: str
    universe_policy_id: str
    risk_policy_id: str
    minimum_data_quality_profile_id: str
    exchange: tuple[str, ...] = ("Binance",)
    markets: tuple[str, ...] = ("Spot",)
    timeframes: tuple[str, ...] = CANONICAL_DEFAULT_TIMEFRAMES
    validated_regimes: tuple[str, ...] = ()
    strategy_ids: tuple[str, ...] = ()
    execution: ApprovedOperatingEnvelopeExecution = field(
        default_factory=ApprovedOperatingEnvelopeExecution
    )
    restrictions: tuple[str, ...] = ()
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE
    grants_authority_outside_envelope: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("envelope_id", self.envelope_id)
        _require_non_empty("universe_policy_id", self.universe_policy_id)
        _require_non_empty("risk_policy_id", self.risk_policy_id)
        _require_non_empty(
            "minimum_data_quality_profile_id",
            self.minimum_data_quality_profile_id,
        )
        _require_unique("approved operating envelope exchange", self.exchange)
        _require_unique("approved operating envelope markets", self.markets)
        _require_unique("approved operating envelope timeframes", self.timeframes)
        _require_unique(
            "approved operating envelope validated regimes",
            self.validated_regimes,
        )
        _require_unique("approved operating envelope strategy_ids", self.strategy_ids)
        _require_unique("approved operating envelope restrictions", self.restrictions)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("approved operating envelope must remain in 13_GOVERNANCE")
        if self.exchange != ("Binance",):
            raise ValueError("approved operating envelope exchange must be Binance")
        if self.markets != ("Spot",):
            raise ValueError("approved operating envelope markets must be Spot")
        if self.timeframes != CANONICAL_DEFAULT_TIMEFRAMES:
            raise ValueError("approved operating envelope timeframes are canonical")
        if self.grants_authority_outside_envelope:
            raise ValueError(
                "component outside approved envelope cannot gain authority"
            )


@dataclass(frozen=True, slots=True)
class GovernanceReleaseRecord:
    grr_id: str
    component_id: str
    component_version: str
    environment: GovernanceReleaseEnvironment
    operating_envelope_id: str
    approval: GovernanceApproval
    approved_at: datetime
    capability_ids: tuple[str, ...] = ()
    validation_artifact_ids: tuple[str, ...] = ()
    restrictions: tuple[str, ...] = ()
    rollback_ready: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in (
            "grr_id",
            "component_id",
            "component_version",
            "operating_envelope_id",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        _require_utc_timestamp("governance release approved_at", self.approved_at)
        _require_unique("governance release capability_ids", self.capability_ids)
        _require_unique(
            "governance release validation artifacts", self.validation_artifact_ids
        )
        _require_unique("governance release restrictions", self.restrictions)
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("governance release must remain in 13_GOVERNANCE")
        if not self.rollback_ready:
            raise ValueError("governance release requires rollback readiness")
        if (
            self.approval.status is GovernanceApprovalStatus.APPROVED
            and self.restrictions
        ):
            raise ValueError("APPROVED release cannot contain restrictions")
        if (
            self.approval.status is GovernanceApprovalStatus.RESTRICTED
            and not self.restrictions
        ):
            raise ValueError("RESTRICTED release requires restrictions")
        if (
            self.environment is GovernanceReleaseEnvironment.LIVE
            and self.approval.status is GovernanceApprovalStatus.APPROVED
            and self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("release record alone cannot unblock live execution")
        if self.execution_allowed:
            raise ValueError("governance release record cannot authorize execution")


class EvidenceObjectKind(StrEnum):
    SOURCE = "Source"
    OBSERVATION = "Observation"
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    CONTRADICTION = "Contradiction"
    EVIDENCE_PACK = "EvidencePack"
    PROVENANCE = "Provenance"


class EvidenceVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    source_id: str
    source_type: str
    source_reference: str

    def __post_init__(self) -> None:
        _require_non_empty("source_id", self.source_id)
        _require_non_empty("source_type", self.source_type)
        _require_non_empty("source_reference", self.source_reference)


@dataclass(frozen=True, slots=True)
class EvidenceObservation:
    observation_id: str
    source_id: str
    observed_at: datetime
    retrieved_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty("observation_id", self.observation_id)
        _require_non_empty("source_id", self.source_id)
        _require_utc_timestamp("evidence observation observed_at", self.observed_at)
        _require_utc_timestamp("evidence observation retrieved_at", self.retrieved_at)
        if self.retrieved_at < self.observed_at:
            raise ValueError(
                "evidence observation retrieval cannot precede observation"
            )


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claim_id: str
    entity_ids: tuple[str, ...]
    statement: str

    def __post_init__(self) -> None:
        _require_non_empty("claim_id", self.claim_id)
        _require_unique("evidence claim entity_ids", self.entity_ids)
        _require_non_empty("evidence claim statement", self.statement)


@dataclass(frozen=True, slots=True)
class EvidenceContradiction:
    contradiction_id: str
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty("contradiction_id", self.contradiction_id)
        _require_unique("contradiction evidence_ids", self.evidence_ids)
        if len(self.evidence_ids) < 2:
            raise ValueError("contradiction requires at least two evidence_ids")
        _require_non_empty("contradiction reason", self.reason)


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    source_reference: str
    content_hash: str | None = None
    parser_version: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("source_reference", self.source_reference)
        if self.content_hash is not None:
            _require_payload_hash(self.content_hash)
        if self.parser_version is not None:
            _require_non_empty("parser_version", self.parser_version)


@dataclass(frozen=True, slots=True)
class EvidenceQuality:
    source_reliability: float
    freshness_score: float
    confirmation_score: float | None = None
    manipulation_risk: float | None = None

    def __post_init__(self) -> None:
        _require_unit_interval("source_reliability", self.source_reliability)
        _require_unit_interval("freshness_score", self.freshness_score)
        if self.confirmation_score is not None:
            _require_unit_interval("confirmation_score", self.confirmation_score)
        if self.manipulation_risk is not None:
            _require_unit_interval("manipulation_risk", self.manipulation_risk)


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    source_id: str
    source_type: str
    observed_at: datetime
    retrieved_at: datetime
    provenance: EvidenceProvenance
    quality: EvidenceQuality
    status: EvidenceVerificationStatus
    entity_ids: tuple[str, ...] = ()
    claim_id: str | None = None
    immutable: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.EVIDENCE

    def __post_init__(self) -> None:
        _require_non_empty("evidence_id", self.evidence_id)
        _require_non_empty("source_id", self.source_id)
        _require_non_empty("source_type", self.source_type)
        _require_unique("evidence entity_ids", self.entity_ids)
        if self.claim_id is not None:
            _require_non_empty("claim_id", self.claim_id)
        _require_utc_timestamp("evidence observed_at", self.observed_at)
        _require_utc_timestamp("evidence retrieved_at", self.retrieved_at)
        if self.retrieved_at < self.observed_at:
            raise ValueError("evidence retrieval cannot precede observation")
        if self.domain is not CanonicalDomainId.EVIDENCE:
            raise ValueError("evidence must remain in 14_EVIDENCE")
        if not self.immutable:
            raise ValueError("evidence must be immutable and append-only")


@dataclass(frozen=True, slots=True)
class EvidencePack:
    evidence_pack_id: str
    evidence_ids: tuple[str, ...]
    contradiction_ids: tuple[str, ...] = ()
    immutable: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.EVIDENCE

    def __post_init__(self) -> None:
        _require_non_empty("evidence_pack_id", self.evidence_pack_id)
        _require_unique("evidence pack evidence_ids", self.evidence_ids)
        _require_unique("evidence pack contradiction_ids", self.contradiction_ids)
        if not self.evidence_ids:
            raise ValueError("evidence pack requires evidence_ids")
        if self.domain is not CanonicalDomainId.EVIDENCE:
            raise ValueError("evidence pack must remain in 14_EVIDENCE")
        if not self.immutable:
            raise ValueError("evidence pack must be immutable and append-only")


@dataclass(frozen=True, slots=True)
class AppendOnlyEvidenceFabric:
    fabric_id: str = "AI4BINANCE-APPEND-ONLY-EVIDENCE-FABRIC"
    version: str = "2.0.0"
    objects: tuple[EvidenceObjectKind, ...] = tuple(EvidenceObjectKind)
    append_only: bool = True
    update_policy: str = "NEW_EVIDENCE_EVENT"
    domain: CanonicalDomainId = CanonicalDomainId.EVIDENCE

    def __post_init__(self) -> None:
        _require_non_empty("append-only evidence fabric_id", self.fabric_id)
        _require_non_empty("append-only evidence fabric version", self.version)
        if self.domain is not CanonicalDomainId.EVIDENCE:
            raise ValueError("append-only evidence fabric must remain in 14_EVIDENCE")
        if self.objects != tuple(EvidenceObjectKind):
            raise ValueError("append-only evidence fabric objects must be canonical")
        if not self.append_only:
            raise ValueError("evidence fabric must be append-only")
        if self.update_policy != "NEW_EVIDENCE_EVENT":
            raise ValueError("new verification must create new evidence/event")


@dataclass(frozen=True, slots=True)
class EvidenceCompleteness:
    required_domains: tuple[str, ...]
    received_domains: tuple[str, ...]
    missing_domains: tuple[str, ...]
    conflicts: tuple[str, ...]
    completeness_score: float
    minimum_met: bool = False
    missing_evidence_state: str = "UNKNOWN"
    domain: CanonicalDomainId = CanonicalDomainId.EVIDENCE

    def __post_init__(self) -> None:
        _require_unique("evidence required_domains", self.required_domains)
        _require_unique("evidence received_domains", self.received_domains)
        _require_unique("evidence missing_domains", self.missing_domains)
        _require_unique("evidence conflicts", self.conflicts)
        _require_unit_interval("completeness_score", self.completeness_score)
        if self.domain is not CanonicalDomainId.EVIDENCE:
            raise ValueError("evidence completeness must remain in 14_EVIDENCE")
        expected_missing = tuple(
            domain
            for domain in self.required_domains
            if domain not in set(self.received_domains)
        )
        if self.missing_domains != expected_missing:
            raise ValueError("missing evidence domains must be explicit")
        if self.missing_domains and self.missing_evidence_state != "UNKNOWN":
            raise ValueError("missing evidence must remain UNKNOWN")
        if self.minimum_met and (self.missing_domains or self.conflicts):
            raise ValueError("evidence completeness cannot pass with gaps/conflicts")


class AuditObservabilityChannel(StrEnum):
    LOGS = "Logs"
    METRICS = "Metrics"
    TRACES = "Traces"
    EVENTS = "Events"
    DECISION_LOGS = "DecisionLogs"
    MODEL_CALLS = "ModelCalls"
    AGENT_CALLS = "AgentCalls"
    TOOL_CALLS = "ToolCalls"
    GATE_RESULTS = "GateResults"
    ERRORS = "Errors"
    INCIDENTS = "Incidents"
    VALIDATION_RECORDS = "ValidationRecords"
    PROMOTION_RECORDS = "PromotionRecords"


class AuditRecordField(StrEnum):
    WHAT = "WHAT"
    WHEN = "WHEN"
    WHO_COMPONENT = "WHO/COMPONENT"
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    VERSION = "VERSION"
    EVIDENCE = "EVIDENCE"
    RESULT = "RESULT"


@dataclass(frozen=True, slots=True)
class AuditObservabilityCatalog:
    catalog_id: str = "AI4BINANCE-AUDIT-OBSERVABILITY"
    version: str = "2.0.0"
    channels: tuple[AuditObservabilityChannel, ...] = tuple(AuditObservabilityChannel)
    minimum_record_fields: tuple[AuditRecordField, ...] = tuple(AuditRecordField)
    logs_only: bool = False
    domain: CanonicalDomainId = CanonicalDomainId.AUDIT_OBSERVABILITY

    def __post_init__(self) -> None:
        _require_non_empty("audit observability catalog_id", self.catalog_id)
        _require_non_empty("audit observability version", self.version)
        if self.domain is not CanonicalDomainId.AUDIT_OBSERVABILITY:
            raise ValueError(
                "audit observability catalog must remain in 15_AUDIT_OBSERVABILITY"
            )
        if self.channels != tuple(AuditObservabilityChannel):
            raise ValueError("audit observability channels must be canonical")
        if self.minimum_record_fields != tuple(AuditRecordField):
            raise ValueError("audit record minimum fields must be canonical")
        if self.logs_only:
            raise ValueError("audit observability cannot be logs-only")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    record_id: str
    channel: AuditObservabilityChannel
    what: str
    when: datetime
    who_component: str
    input_ref: str
    output_ref: str
    version: str
    evidence_ids: tuple[str, ...]
    result: str
    domain: CanonicalDomainId = CanonicalDomainId.AUDIT_OBSERVABILITY

    def __post_init__(self) -> None:
        _require_non_empty("audit record_id", self.record_id)
        _require_non_empty("audit WHAT", self.what)
        _require_utc_timestamp("audit WHEN", self.when)
        _require_non_empty("audit WHO/COMPONENT", self.who_component)
        _require_non_empty("audit INPUT", self.input_ref)
        _require_non_empty("audit OUTPUT", self.output_ref)
        _require_non_empty("audit VERSION", self.version)
        _require_unique("audit EVIDENCE", self.evidence_ids)
        if not self.evidence_ids:
            raise ValueError("audit record requires EVIDENCE")
        _require_non_empty("audit RESULT", self.result)
        if self.domain is not CanonicalDomainId.AUDIT_OBSERVABILITY:
            raise ValueError("audit record must remain in 15_AUDIT_OBSERVABILITY")


class DecisionLineageStep(StrEnum):
    RAW_DATA = "RawData"
    MARKET_SNAPSHOT = "MarketSnapshot"
    FEATURE_SNAPSHOT = "FeatureSnapshot"
    OBSERVATION = "Observation"
    EVIDENCE = "Evidence"
    SETUP_CANDIDATE = "SetupCandidate"
    DECISION = "Decision"
    RISK_ASSESSMENT = "RiskAssessment"
    GOVERNANCE_RESULT = "GovernanceResult"
    TRADE_PLAN = "TradePlan"
    EXECUTION = "Execution"
    POSITION_LIFECYCLE = "PositionLifecycle"
    CLOSURE_REVIEW = "ClosureReview"
    LESSON = "Lesson"


@dataclass(frozen=True, slots=True)
class DecisionLineage:
    lineage_id: str
    cycle_id: str
    step_refs: tuple[tuple[DecisionLineageStep, str], ...]
    unbroken: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.AUDIT_OBSERVABILITY

    def __post_init__(self) -> None:
        _require_non_empty("decision lineage_id", self.lineage_id)
        _require_non_empty("decision lineage cycle_id", self.cycle_id)
        if self.domain is not CanonicalDomainId.AUDIT_OBSERVABILITY:
            raise ValueError("decision lineage must remain in 15_AUDIT_OBSERVABILITY")
        expected_steps = tuple(DecisionLineageStep)
        actual_steps = tuple(step for step, _ref in self.step_refs)
        if actual_steps != expected_steps:
            raise ValueError("decision lineage chain cannot be cut or reordered")
        for step, ref in self.step_refs:
            _require_non_empty(f"decision lineage {step.value}", ref)
        if not self.unbroken:
            raise ValueError("decision lineage chain cannot be marked broken")

    @property
    def refs_by_step(self) -> MappingProxyType[DecisionLineageStep, str]:
        return MappingProxyType(dict(self.step_refs))


class SecurityControlDomain(StrEnum):
    IDENTITY = "Identity"
    RBAC = "RBAC"
    SECRETS = "Secrets"
    API_PERMISSIONS = "APIPermissions"
    DATA_CLASSIFICATION = "DataClassification"
    INTEGRITY = "Integrity"
    DEPENDENCY_SECURITY = "DependencySecurity"
    SUPPLY_CHAIN_SECURITY = "SupplyChainSecurity"
    INCIDENT_MANAGEMENT = "IncidentManagement"
    SECURITY_AUDIT = "SecurityAudit"


class ApiKeyStorageLocation(StrEnum):
    ENV_FILE = ".env"


class SecretProhibitedSink(StrEnum):
    SOURCE_CODE = "source_code"
    LOGS = "logs"
    REPORTS = "reports"
    PROMPTS = "prompts"
    AUDIT_ARTIFACTS = "audit_artifacts"


@dataclass(frozen=True, slots=True)
class ApiKeySecretPolicy:
    allowed_locations: tuple[ApiKeyStorageLocation, ...] = (
        ApiKeyStorageLocation.ENV_FILE,
    )
    prohibited_sinks: tuple[SecretProhibitedSink, ...] = tuple(SecretProhibitedSink)
    raw_secret_storage_allowed: bool = False
    redaction_required: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.SECURITY

    def __post_init__(self) -> None:
        if self.domain is not CanonicalDomainId.SECURITY:
            raise ValueError("API key secret policy must remain in 16_SECURITY")
        if self.allowed_locations != (ApiKeyStorageLocation.ENV_FILE,):
            raise ValueError("API keys must be sourced from .env only")
        if self.prohibited_sinks != tuple(SecretProhibitedSink):
            raise ValueError("API key prohibited sinks must remain canonical")
        if self.raw_secret_storage_allowed:
            raise ValueError("raw API keys must not be stored outside .env")
        if not self.redaction_required:
            raise ValueError("API key redaction is required")


@dataclass(frozen=True, slots=True)
class SecurityDomainContract:
    security_contract_id: str = "AI4BINANCE-SECURITY-CONTRACT"
    version: str = "2.0.0"
    controls: tuple[SecurityControlDomain, ...] = tuple(SecurityControlDomain)
    api_key_policy: ApiKeySecretPolicy = field(default_factory=ApiKeySecretPolicy)
    fail_policy: str = "DENY"
    domain: CanonicalDomainId = CanonicalDomainId.SECURITY
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("security contract_id", self.security_contract_id)
        _require_non_empty("security version", self.version)
        if self.domain is not CanonicalDomainId.SECURITY:
            raise ValueError("security contract must remain in 16_SECURITY")
        if self.controls != tuple(SecurityControlDomain):
            raise ValueError("security controls must be canonical")
        if self.api_key_policy.domain is not CanonicalDomainId.SECURITY:
            raise ValueError("security API key policy must remain in 16_SECURITY")
        if self.fail_policy != "DENY":
            raise ValueError("security fail policy must DENY")
        if self.execution_allowed:
            raise ValueError("security contract cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("security contract cannot unblock live execution")


class CanonicalEventType(StrEnum):
    MARKET_DATA_READY = "MARKET_DATA_READY"
    MARKET_SNAPSHOT_READY = "MARKET_SNAPSHOT_READY"
    FEATURE_SET_READY = "FEATURE_SET_READY"
    AGENT_ANALYSIS_REQUESTED = "AGENT_ANALYSIS_REQUESTED"
    AGENT_OBSERVATIONS_READY = "AGENT_OBSERVATIONS_READY"
    EVIDENCE_PACK_READY = "EVIDENCE_PACK_READY"
    DECISION_REQUESTED = "DECISION_REQUESTED"
    DECISION_COMPLETED = "DECISION_COMPLETED"
    RISK_ASSESSMENT_COMPLETED = "RISK_ASSESSMENT_COMPLETED"
    TRADE_PLAN_CREATED = "TRADE_PLAN_CREATED"
    EXECUTION_GATE_EVALUATED = "EXECUTION_GATE_EVALUATED"
    PAPER_ORDER_ACCEPTED = "PAPER_ORDER_ACCEPTED"
    PAPER_ORDER_FILLED = "PAPER_ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    TRAILING_STOP_UPDATED = "TRAILING_STOP_UPDATED"
    TRAILING_STOP_EXIT = "TRAILING_STOP_EXIT"
    TRADE_REVIEW_COMPLETED = "TRADE_REVIEW_COMPLETED"
    INCIDENT_CREATED = "INCIDENT_CREATED"
    LEARNING_CANDIDATE_CREATED = "LEARNING_CANDIDATE_CREATED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    PROMOTION_REQUESTED = "PROMOTION_REQUESTED"
    PROMOTION_APPROVED = "PROMOTION_APPROVED"
    PROMOTION_REJECTED = "PROMOTION_REJECTED"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: CanonicalEventType
    schema_version: str
    producer: str
    occurred_at: datetime
    recorded_at: datetime
    payload_ref: str
    correlation_id: str
    cycle_id: str | None = None
    snapshot_id: str | None = None
    decision_id: str | None = None
    trade_id: str | None = None
    causation_id: str | None = None
    domain: CanonicalDomainId = CanonicalDomainId.EVENT_FABRIC

    def __post_init__(self) -> None:
        _require_non_empty("event_id", self.event_id)
        _require_non_empty("event schema_version", self.schema_version)
        _require_non_empty("event producer", self.producer)
        _require_utc_timestamp("event occurred_at", self.occurred_at)
        _require_utc_timestamp("event recorded_at", self.recorded_at)
        if self.recorded_at < self.occurred_at:
            raise ValueError("event recorded_at cannot precede occurred_at")
        _require_non_empty("event payload_ref", self.payload_ref)
        _require_non_empty("event correlation_id", self.correlation_id)
        for field_name in (
            "cycle_id",
            "snapshot_id",
            "decision_id",
            "trade_id",
            "causation_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_non_empty(f"event {field_name}", value)
        if self.domain is not CanonicalDomainId.EVENT_FABRIC:
            raise ValueError("event envelope must remain in 17_EVENT_FABRIC")


@dataclass(frozen=True, slots=True)
class EventFabricContract:
    fabric_id: str = "AI4BINANCE-EVENT-FABRIC"
    version: str = "2.0.0"
    event_types: tuple[CanonicalEventType, ...] = tuple(CanonicalEventType)
    envelope_schema: str = "EventEnvelope"
    domain: CanonicalDomainId = CanonicalDomainId.EVENT_FABRIC

    def __post_init__(self) -> None:
        _require_non_empty("event fabric_id", self.fabric_id)
        _require_non_empty("event fabric version", self.version)
        if self.domain is not CanonicalDomainId.EVENT_FABRIC:
            raise ValueError("event fabric must remain in 17_EVENT_FABRIC")
        if self.event_types != tuple(CanonicalEventType):
            raise ValueError("event fabric event types must be canonical")
        if self.envelope_schema != "EventEnvelope":
            raise ValueError("all events must use EventEnvelope")


class ResearchCapabilityStep(StrEnum):
    RADAR_FINDING = "RadarFinding"
    RESEARCH_UNIT = "ResearchUnit"
    CAPABILITY_CANDIDATE = "CapabilityCandidate"
    POC = "POC"
    VALIDATION = "Validation"
    PROMOTION_GOVERNANCE = "PromotionGovernance"
    REGISTRY = "Registry"


class DuplicateCapabilityCheckStatus(StrEnum):
    CLEAR = "CLEAR"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


class ResearchLicenseStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    RESTRICTED = "RESTRICTED"


class ResearchReuseMode(StrEnum):
    ADOPT_IDEA = "ADOPT_IDEA"
    REVIEW_ONLY = "REVIEW_ONLY"
    NO_CODE_REUSE = "NO_CODE_REUSE"


class ResearchUnitResult(StrEnum):
    REJECTED = "REJECTED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    POC_CANDIDATE = "POC_CANDIDATE"
    VALIDATION_CANDIDATE = "VALIDATION_CANDIDATE"


class ResearchEvaluationStage(StrEnum):
    HARD_GATES = "HARD_GATES"
    EVIDENCE_COMPLETENESS = "EVIDENCE_COMPLETENESS"
    RESEARCH_100_POINT_SCORE = "100_POINT_RESEARCH_SCORE"
    ACTION_CEILING = "ACTION_CEILING"


@dataclass(frozen=True, slots=True)
class ResearchUnitSource:
    source_id: str
    repository_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("research source_id", self.source_id)
        if self.repository_ref is not None:
            _require_non_empty("research repository_ref", self.repository_ref)


@dataclass(frozen=True, slots=True)
class DuplicateCapabilityCheck:
    status: DuplicateCapabilityCheckStatus


@dataclass(frozen=True, slots=True)
class ResearchLicense:
    status: ResearchLicenseStatus
    reuse_mode: ResearchReuseMode

    def __post_init__(self) -> None:
        if (
            self.status is ResearchLicenseStatus.UNKNOWN
            and self.reuse_mode is not ResearchReuseMode.NO_CODE_REUSE
        ):
            raise ValueError("unknown license requires NO_CODE_REUSE")
        if (
            self.status is ResearchLicenseStatus.RESTRICTED
            and self.reuse_mode is ResearchReuseMode.ADOPT_IDEA
        ):
            raise ValueError("restricted license cannot be adopted as implementation")


@dataclass(frozen=True, slots=True)
class ResearchIntegrity:
    lookahead_detected: bool = False
    repainting_detected: bool = False

    @property
    def trading_eligible(self) -> bool:
        return not self.lookahead_detected and not self.repainting_detected


@dataclass(frozen=True, slots=True)
class ResearchScore:
    scorecard_id: str
    research_scorecard_id: str | None = None
    score_target: str = "ResearchUnit"
    github_stars_secondary_only: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("research scorecard_id", self.scorecard_id)
        if self.research_scorecard_id is not None:
            _require_non_empty(
                "research_scorecard_id",
                self.research_scorecard_id,
            )
        if self.score_target != "ResearchUnit":
            raise ValueError("score belongs to ResearchUnit, not repository")
        if not self.github_stars_secondary_only:
            raise ValueError("GitHub stars are secondary metadata only")

    @property
    def effective_research_scorecard_id(self) -> str:
        return self.research_scorecard_id or self.scorecard_id


@dataclass(frozen=True, slots=True)
class ResearchEvaluationPipeline:
    pipeline_id: str = "AI4BINANCE-RESEARCH-EVALUATION-PIPELINE"
    version: str = "2.0.0"
    stages: tuple[ResearchEvaluationStage, ...] = tuple(ResearchEvaluationStage)
    weights_embedded: bool = False
    domain: CanonicalDomainId = CanonicalDomainId.RESEARCH_CAPABILITY

    def __post_init__(self) -> None:
        _require_non_empty("research evaluation pipeline_id", self.pipeline_id)
        _require_non_empty("research evaluation version", self.version)
        if self.domain is not CanonicalDomainId.RESEARCH_CAPABILITY:
            raise ValueError(
                "research evaluation pipeline must remain in 18_RESEARCH_CAPABILITY"
            )
        if self.stages != tuple(ResearchEvaluationStage):
            raise ValueError("research evaluation order must be canonical")
        if self.weights_embedded:
            raise ValueError("research score weights must not be invented here")


@dataclass(frozen=True, slots=True)
class ResearchEvaluationResult:
    research_unit_id: str
    research_scorecard_id: str
    hard_gates_passed: bool
    evidence_completeness: EvidenceCompleteness
    research_score: float
    action_ceiling: ActionCeiling
    result: ResearchUnitResult
    pipeline: ResearchEvaluationPipeline = field(
        default_factory=ResearchEvaluationPipeline
    )
    domain: CanonicalDomainId = CanonicalDomainId.RESEARCH_CAPABILITY

    def __post_init__(self) -> None:
        _require_non_empty("research_unit_id", self.research_unit_id)
        _require_non_empty("research_scorecard_id", self.research_scorecard_id)
        _require_unit_interval("research_score normalized", self.research_score / 100)
        if self.domain is not CanonicalDomainId.RESEARCH_CAPABILITY:
            raise ValueError(
                "research evaluation result must remain in 18_RESEARCH_CAPABILITY"
            )
        if self.pipeline.stages != tuple(ResearchEvaluationStage):
            raise ValueError("research evaluation order must be canonical")
        if self.pipeline.weights_embedded:
            raise ValueError("research score weights must be scorecard-versioned")
        if not self.hard_gates_passed and self.result not in {
            ResearchUnitResult.REJECTED,
            ResearchUnitResult.RESEARCH_ONLY,
        }:
            raise ValueError("failed research hard gates cannot advance candidates")
        if not self.evidence_completeness.minimum_met and self.result not in {
            ResearchUnitResult.REJECTED,
            ResearchUnitResult.RESEARCH_ONLY,
        }:
            raise ValueError("incomplete research evidence cannot advance candidates")
        if (
            self.result is ResearchUnitResult.POC_CANDIDATE
            and self.action_ceiling not in {ActionCeiling.RESEARCH, ActionCeiling.NONE}
        ):
            raise ValueError("research score cannot raise action ceiling")


@dataclass(frozen=True, slots=True)
class ResearchUnit:
    research_unit_id: str
    source: ResearchUnitSource
    capability_candidate_id: str
    hypothesis: str
    expected_value: str
    duplicate_capability_check: DuplicateCapabilityCheck
    license: ResearchLicense
    integrity: ResearchIntegrity
    score: ResearchScore
    result: ResearchUnitResult
    evidence: tuple[str, ...] = ()
    flow: tuple[ResearchCapabilityStep, ...] = tuple(ResearchCapabilityStep)
    copied_code: bool = False
    added_dependency: bool = False
    production_promotion: bool = False
    not_trading_eligible_reason: str | None = None
    domain: CanonicalDomainId = CanonicalDomainId.RESEARCH_CAPABILITY

    def __post_init__(self) -> None:
        _require_non_empty("research_unit_id", self.research_unit_id)
        _require_non_empty("capability_candidate_id", self.capability_candidate_id)
        _require_non_empty("hypothesis", self.hypothesis)
        _require_non_empty("expected_value", self.expected_value)
        _require_unique("research evidence", self.evidence)
        if self.domain is not CanonicalDomainId.RESEARCH_CAPABILITY:
            raise ValueError("ResearchUnit must remain in 18_RESEARCH_CAPABILITY")
        if self.flow != tuple(ResearchCapabilityStep):
            raise ValueError("research capability flow must be canonical")
        if self.license.reuse_mode is ResearchReuseMode.ADOPT_IDEA and (
            self.copied_code or self.added_dependency
        ):
            raise ValueError("ADOPT_IDEA is not COPY_CODE or ADD_DEPENDENCY")
        if (
            self.result is ResearchUnitResult.POC_CANDIDATE
            and self.production_promotion
        ):
            raise ValueError("POC success cannot auto-promote to production")
        if not self.integrity.trading_eligible:
            expected_reason = "NOT_TRADING_ELIGIBLE"
            if self.not_trading_eligible_reason != expected_reason:
                raise ValueError("lookahead/repainting requires NOT_TRADING_ELIGIBLE")
        elif self.not_trading_eligible_reason is not None:
            raise ValueError("trading eligibility reason requires integrity blocker")


@dataclass(frozen=True, slots=True)
class ResearchCapabilityDomainContract:
    contract_id: str = "AI4BINANCE-RESEARCH-CAPABILITY-CONTRACT"
    version: str = "2.0.0"
    flow: tuple[ResearchCapabilityStep, ...] = tuple(ResearchCapabilityStep)
    evaluation_pipeline: ResearchEvaluationPipeline = field(
        default_factory=ResearchEvaluationPipeline
    )
    score_target: str = "ResearchUnit"
    github_stars_secondary_only: bool = True
    domain: CanonicalDomainId = CanonicalDomainId.RESEARCH_CAPABILITY
    production_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("research capability contract_id", self.contract_id)
        _require_non_empty("research capability version", self.version)
        if self.domain is not CanonicalDomainId.RESEARCH_CAPABILITY:
            raise ValueError(
                "research capability contract must remain in 18_RESEARCH_CAPABILITY"
            )
        if self.flow != tuple(ResearchCapabilityStep):
            raise ValueError("research capability flow must be canonical")
        if self.evaluation_pipeline.stages != tuple(ResearchEvaluationStage):
            raise ValueError("research evaluation order must be canonical")
        if self.score_target != "ResearchUnit":
            raise ValueError("score must be assigned to ResearchUnit")
        if not self.github_stars_secondary_only:
            raise ValueError("GitHub stars are secondary metadata only")
        if self.production_promotion_allowed:
            raise ValueError("research capability cannot auto-promote production")


class ExternalIntelligenceSource(StrEnum):
    NEWS = "News"
    SOCIAL = "Social"
    TELEGRAM = "Telegram"
    X = "X"
    GITHUB = "GitHub"
    ARXIV = "arxiv.org"
    SEC = "sec.gov"
    CVE = "cve.org"
    MEDIUM = "medium.com"
    SUBSTACK = "substack.com"
    SECURITY = "Security"
    REGULATORY = "Regulatory"
    PROJECT_OFFICIAL_SOURCES = "ProjectOfficialSources"
    EXCHANGE_ANNOUNCEMENTS = "ExchangeAnnouncements"
    TOKENOMICS = "Tokenomics"
    ON_CHAIN = "OnChain"
    WHALE = "Whale"
    MACRO = "Macro"
    RESEARCH = "Research"


class EvidenceFabricStage(StrEnum):
    SOURCE = "SOURCE"
    INGESTION = "INGESTION"
    NORMALIZATION = "NORMALIZATION"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    CLAIM_EVENT_EXTRACTION = "CLAIM_EVENT_EXTRACTION"
    SOURCE_VALIDATION = "SOURCE_VALIDATION"
    EVIDENCE_SCORING = "EVIDENCE_SCORING"
    INDEXING = "VECTOR_LEXICAL_GRAPH_TEMPORAL_INDEX"
    HYBRID_RETRIEVAL = "HYBRID_RETRIEVAL"
    EVIDENCE_PACK = "EVIDENCE_PACK"


class EvidenceIndexKind(StrEnum):
    VECTOR = "VECTOR"
    LEXICAL = "LEXICAL"
    GRAPH = "GRAPH"
    TEMPORAL = "TEMPORAL"


class IntelligenceRetrievalTechnique(StrEnum):
    RAG = "RAG"
    AGENTIC_RAG = "Agentic RAG"
    HYBRID_RETRIEVAL = "HYBRID_RETRIEVAL"


@dataclass(frozen=True, slots=True)
class ExternalIntelligenceEvidenceFabric:
    fabric_id: str
    version: str
    domain: CanonicalDomainId = CanonicalDomainId.INTELLIGENCE
    sources: tuple[ExternalIntelligenceSource, ...] = tuple(ExternalIntelligenceSource)
    pipeline: tuple[EvidenceFabricStage, ...] = tuple(EvidenceFabricStage)
    indexes: tuple[EvidenceIndexKind, ...] = tuple(EvidenceIndexKind)
    retrieval_techniques: tuple[IntelligenceRetrievalTechnique, ...] = (
        IntelligenceRetrievalTechnique.RAG,
        IntelligenceRetrievalTechnique.AGENTIC_RAG,
        IntelligenceRetrievalTechnique.HYBRID_RETRIEVAL,
    )
    rag_is_evidence_fabric: bool = False
    produces: str = "EVIDENCE_PACK"

    def __post_init__(self) -> None:
        _require_non_empty("external intelligence fabric_id", self.fabric_id)
        _require_non_empty("external intelligence version", self.version)
        if self.domain is not CanonicalDomainId.INTELLIGENCE:
            raise ValueError(
                "external intelligence fabric must belong to 04_INTELLIGENCE"
            )
        if self.sources != tuple(ExternalIntelligenceSource):
            raise ValueError("external intelligence sources must be canonical")
        if self.pipeline != tuple(EvidenceFabricStage):
            raise ValueError("external intelligence pipeline must remain canonical")
        if self.indexes != tuple(EvidenceIndexKind):
            raise ValueError(
                "evidence fabric indexes must include vector, lexical, graph, temporal"
            )
        if IntelligenceRetrievalTechnique.RAG not in self.retrieval_techniques:
            raise ValueError("evidence fabric must model RAG as a retrieval technique")
        if self.rag_is_evidence_fabric:
            raise ValueError("RAG is a tool, not the Evidence Fabric")
        if self.produces != EvidenceFabricStage.EVIDENCE_PACK.value:
            raise ValueError("external intelligence fabric must produce EVIDENCE_PACK")


class GovernancePyramidLevel(StrEnum):
    HUMAN_BOARD = "01_HUMAN_BOARD"
    GOVERNANCE_OFFICE = "02_GOVERNANCE_OFFICE"
    POLICY_AS_CODE = "03_POLICY_AS_CODE"
    GOVERNANCE_REGISTRY = "04_GOVERNANCE_REGISTRY"
    DATA_EVIDENCE_CAPABILITY = "05_DATA_EVIDENCE_CAPABILITY"
    INTELLIGENCE_AGENTS_STRATEGIES = "06_INTELLIGENCE_AGENTS_STRATEGIES"
    DETERMINISTIC_DECISION_RISK = "07_DETERMINISTIC_DECISION_RISK"
    EXECUTION_GATES = "08_EXECUTION_GATES"
    AUDIT_ASSURANCE_LEARNING = "09_AUDIT_ASSURANCE_LEARNING"


@dataclass(frozen=True, slots=True)
class GovernancePyramidLayer:
    level: GovernancePyramidLevel
    authority_holder: str
    responsibilities: tuple[str, ...]
    prohibited_authorities: tuple[str, ...]
    required_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty("governance pyramid authority_holder", self.authority_holder)
        _require_unique("governance pyramid responsibilities", self.responsibilities)
        _require_unique(
            "governance pyramid prohibited authorities",
            self.prohibited_authorities,
        )
        _require_unique("governance pyramid required evidence", self.required_evidence)
        if not self.responsibilities:
            raise ValueError("governance pyramid layer requires responsibilities")
        if not self.required_evidence:
            raise ValueError("governance pyramid layer requires evidence")


@dataclass(frozen=True, slots=True)
class WebIntelligenceRadarContract:
    radar_id: str = "AI4BINANCE-WEB-INTELLIGENCE-RADAR"
    version: str = "2.0.0"
    source_types: tuple[ExternalIntelligenceSource, ...] = (
        ExternalIntelligenceSource.NEWS,
        ExternalIntelligenceSource.GITHUB,
        ExternalIntelligenceSource.ARXIV,
        ExternalIntelligenceSource.CVE,
        ExternalIntelligenceSource.SECURITY,
        ExternalIntelligenceSource.REGULATORY,
        ExternalIntelligenceSource.EXCHANGE_ANNOUNCEMENTS,
        ExternalIntelligenceSource.PROJECT_OFFICIAL_SOURCES,
        ExternalIntelligenceSource.RESEARCH,
    )
    evidence_pipeline: tuple[EvidenceFabricStage, ...] = tuple(EvidenceFabricStage)
    required_outputs: tuple[str, ...] = (
        "RadarFinding",
        "EvidencePack",
        "CapabilityGap",
        "ResearchUnit",
        "ValidationPlan",
        "GovernanceIntake",
        "AuditEvent",
    )
    allowed_actions: tuple[str, ...] = (
        "DISCOVER_PUBLIC_EVIDENCE",
        "CLASSIFY_TECHNOLOGY_GAP",
        "MAP_TO_CAPABILITY_GAP",
        "PROPOSE_RESEARCH_UNIT",
        "PROPOSE_VALIDATION_PLAN",
        "WRITE_AUDIT_EVENT",
    )
    prohibited_actions: tuple[str, ...] = (
        "COPY_UNKNOWN_LICENSE_CODE",
        "ADD_DEPENDENCY_WITHOUT_REVIEW",
        "PROMOTE_CAPABILITY",
        "MODIFY_RISK_LIMIT",
        "ENABLE_LIVE_TRADING",
        "EXECUTE_ORDER",
    )
    credentialless_default: bool = True
    decision_authority: str = "ADVISORY_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    domain: CanonicalDomainId = CanonicalDomainId.INTELLIGENCE

    def __post_init__(self) -> None:
        _require_non_empty("web intelligence radar_id", self.radar_id)
        _require_non_empty("web intelligence version", self.version)
        _require_unique("web intelligence source types", self.source_types)
        _require_unique("web intelligence outputs", self.required_outputs)
        _require_unique("web intelligence allowed actions", self.allowed_actions)
        _require_unique("web intelligence prohibited actions", self.prohibited_actions)
        required_sources = {
            ExternalIntelligenceSource.NEWS,
            ExternalIntelligenceSource.GITHUB,
            ExternalIntelligenceSource.SECURITY,
            ExternalIntelligenceSource.RESEARCH,
        }
        if not required_sources.issubset(set(self.source_types)):
            raise ValueError(
                "web intelligence radar requires news, GitHub, security, research"
            )
        if self.evidence_pipeline != tuple(EvidenceFabricStage):
            raise ValueError("web intelligence radar must use the evidence pipeline")
        if "EvidencePack" not in self.required_outputs:
            raise ValueError("web intelligence radar must produce EvidencePack")
        if not self.credentialless_default:
            raise ValueError("web intelligence radar must default credentialless")
        if self.decision_authority != "ADVISORY_ONLY":
            raise ValueError("web intelligence radar must remain advisory-only")
        if self.domain is not CanonicalDomainId.INTELLIGENCE:
            raise ValueError("web intelligence radar belongs to 04_INTELLIGENCE")
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("web intelligence radar cannot authorize execution")


class LoopsStage(StrEnum):
    LISTEN = "L_LISTEN_OUTCOMES"
    OBSERVE = "O_OBSERVE_WEB_INTELLIGENCE"
    ORIENT = "O_ORIENT_HYPOTHESES"
    PROVE = "P_PROVE_WITH_VALIDATION"
    STAGE = "S_STAGE_GOVERNED_CANDIDATES"


@dataclass(frozen=True, slots=True)
class LoopsStep:
    stage: LoopsStage
    objective: str
    input_entities: tuple[str, ...]
    output_entities: tuple[str, ...]
    required_evidence: tuple[str, ...]
    authority_boundary: str = "RESEARCH_ONLY"

    def __post_init__(self) -> None:
        _require_non_empty("LOOPS objective", self.objective)
        _require_unique("LOOPS input entities", self.input_entities)
        _require_unique("LOOPS output entities", self.output_entities)
        _require_unique("LOOPS required evidence", self.required_evidence)
        if not self.input_entities or not self.output_entities:
            raise ValueError("LOOPS step requires input and output entities")
        if not self.required_evidence:
            raise ValueError("LOOPS step requires evidence")
        if self.authority_boundary != "RESEARCH_ONLY":
            raise ValueError("LOOPS steps must remain RESEARCH_ONLY")


def _default_loops_steps() -> tuple[LoopsStep, ...]:
    return (
        LoopsStep(
            LoopsStage.LISTEN,
            "Listen to outcomes, closure reviews and audit findings.",
            ("Outcome", "ClosureReview", "AuditEvent"),
            ("Lesson",),
            ("decision_lineage", "closure_review", "audit_event"),
        ),
        LoopsStep(
            LoopsStage.OBSERVE,
            "Observe public technology and risk evidence with Web Intelligence Radar.",
            ("Lesson", "CapabilityGapRegistry"),
            ("RadarFinding", "EvidencePack"),
            ("source_reference", "content_hash", "freshness_score"),
        ),
        LoopsStep(
            LoopsStage.ORIENT,
            "Orient evidence into hypotheses and governed research candidates.",
            ("RadarFinding", "EvidencePack", "CapabilityGap"),
            ("Hypothesis", "LearningCandidate", "GovernanceIntake"),
            ("evidence_ids", "conflict_check", "license_status"),
        ),
        LoopsStep(
            LoopsStage.PROVE,
            "Prove candidates through formula, oracle, tests, WF, OOS and regimes.",
            ("LearningCandidate", "ResearchUnit", "CapabilityCandidate"),
            ("Validation", "ValidationArtifact", "PromotionReview"),
            ("formula_id", "oracle_id", "wf_artifact", "oos_artifact"),
        ),
        LoopsStep(
            LoopsStage.STAGE,
            "Stage validated candidates for human-governed promotion or rejection.",
            ("PromotionReview", "ValidationArtifact", "GovernanceIntake"),
            ("GovernanceReleaseRecord", "RegistryComponent", "Finding"),
            ("approval_record", "operating_envelope", "rollback_plan"),
        ),
    )


@dataclass(frozen=True, slots=True)
class LoopsSelfImprovementContract:
    contract_id: str = "AI4BINANCE-LOOPS-SELF-IMPROVEMENT"
    version: str = "2.0.0"
    steps: tuple[LoopsStep, ...] = field(default_factory=_default_loops_steps)
    web_intelligence_radar: WebIntelligenceRadarContract = field(
        default_factory=WebIntelligenceRadarContract
    )
    lifecycle_chain: tuple[str, ...] = (
        "Outcome",
        "ClosureReview",
        "Lesson",
        "Hypothesis",
        "LearningCandidate",
        "WebIntelligenceRadar",
        "GovernanceIntake",
        "ResearchUnit",
        "CapabilityCandidate",
        "Validation",
        "PromotionReview",
    )
    allowed_actions: tuple[str, ...] = (
        "OBSERVE",
        "CLASSIFY",
        "PROPOSE",
        "RANK",
        "STAGE_RESEARCH",
        "REQUEST_VALIDATION",
    )
    prohibited_actions: tuple[str, ...] = (
        "DEPLOY",
        "SELF_PROMOTE",
        "MODIFY_LIVE_PARAMETER",
        "MODIFY_RISK_LIMIT",
        "DISABLE_GATE",
        "ENABLE_LIVE",
        "EXECUTE_ORDER",
    )
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    domain: CanonicalDomainId = CanonicalDomainId.LEARNING

    def __post_init__(self) -> None:
        _require_non_empty("LOOPS contract_id", self.contract_id)
        _require_non_empty("LOOPS version", self.version)
        _require_unique("LOOPS lifecycle chain", self.lifecycle_chain)
        _require_unique("LOOPS allowed actions", self.allowed_actions)
        _require_unique("LOOPS prohibited actions", self.prohibited_actions)
        if tuple(step.stage for step in self.steps) != tuple(LoopsStage):
            raise ValueError("LOOPS steps must be canonical and ordered")
        if "WebIntelligenceRadar" not in self.lifecycle_chain:
            raise ValueError("LOOPS lifecycle requires WebIntelligenceRadar")
        if self.web_intelligence_radar.decision_authority != "ADVISORY_ONLY":
            raise ValueError("LOOPS requires advisory-only Web Intelligence Radar")
        if self.domain is not CanonicalDomainId.LEARNING:
            raise ValueError("LOOPS belongs to 12_LEARNING")
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("LOOPS cannot authorize execution")


@dataclass(frozen=True, slots=True)
class DigitalCompanyOperatingModel:
    company_id: str = "AI4BINANCE-DIGITAL-COMPANY"
    version: str = "2.0.0"
    purpose: str = (
        "Operate a transparent, evidence-based, risk-controlled and fail-closed "
        "algorithmic trading decision-support digital company."
    )
    profitability_statement: str = (
        "Targets risk-adjusted positive expectancy through validation, assurance "
        "and human authority; provides no profit guarantee."
    )
    pyramid: tuple[GovernancePyramidLayer, ...] = ()
    loops_contract: LoopsSelfImprovementContract = field(
        default_factory=LoopsSelfImprovementContract
    )
    operating_principles: tuple[str, ...] = (
        "Capital protection before trade frequency.",
        "Transparent lineage for every material action.",
        "Evidence-first improvement proposals.",
        "Capability-first validation before promotion.",
        "Fail closed to NO_TRADE on critical uncertainty.",
    )
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    domain: CanonicalDomainId = CanonicalDomainId.GOVERNANCE

    def __post_init__(self) -> None:
        _require_non_empty("digital company_id", self.company_id)
        _require_non_empty("digital company version", self.version)
        _require_non_empty("digital company purpose", self.purpose)
        _require_non_empty(
            "digital company profitability_statement",
            self.profitability_statement,
        )
        _require_unique(
            "digital company operating principles",
            self.operating_principles,
        )
        if "no profit guarantee" not in self.profitability_statement.lower():
            raise ValueError("digital company must state no profit guarantee")
        if tuple(layer.level for layer in self.pyramid) != tuple(
            GovernancePyramidLevel
        ):
            raise ValueError("digital company pyramid must be canonical and ordered")
        if not any("NO_TRADE" in item for item in self.operating_principles):
            raise ValueError("digital company must fail closed to NO_TRADE")
        if self.loops_contract.domain is not CanonicalDomainId.LEARNING:
            raise ValueError("digital company requires LOOPS learning contract")
        if self.domain is not CanonicalDomainId.GOVERNANCE:
            raise ValueError("digital company model belongs to 13_GOVERNANCE")
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError(
                "digital company operating model cannot authorize execution"
            )


@dataclass(frozen=True, slots=True)
class RawMarketDataRecord:
    record_id: str
    kind: MarketDataKind
    source_id: str
    observed_at: datetime
    payload_hash: str
    immutable: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("raw market record_id", self.record_id)
        _require_non_empty("raw market source_id", self.source_id)
        _require_utc_timestamp("raw market observed_at", self.observed_at)
        _require_payload_hash(self.payload_hash)
        if not self.immutable:
            raise ValueError("RAW MARKET DATA must be immutable")


@dataclass(frozen=True, slots=True)
class NormalizedMarketDataRecord:
    normalized_record_id: str
    raw_record_id: str
    kind: MarketDataKind
    normalizer_version: str
    created_at: datetime
    payload_hash: str
    overwrite_raw: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("normalized market record_id", self.normalized_record_id)
        _require_non_empty("normalized market raw_record_id", self.raw_record_id)
        _require_non_empty("normalizer_version", self.normalizer_version)
        _require_utc_timestamp("normalized market created_at", self.created_at)
        _require_payload_hash(self.payload_hash)
        if self.normalized_record_id == self.raw_record_id:
            raise ValueError("normalization must create a separate record")
        if self.overwrite_raw:
            raise ValueError("normalization must not overwrite raw records")


@dataclass(frozen=True, slots=True)
class CycleAgentObservationRef:
    agent_id: str
    observation_id: str
    snapshot_id: str

    def __post_init__(self) -> None:
        _require_non_empty("agent_id", self.agent_id)
        _require_non_empty("agent observation_id", self.observation_id)
        _require_non_empty("agent snapshot_id", self.snapshot_id)


@dataclass(frozen=True, slots=True)
class DecisionCycleContext:
    cycle_id: str
    snapshot_id: str
    created_at: datetime
    symbol: str
    timeframes: tuple[str, ...]
    market_snapshot: str
    feature_snapshot: str
    evidence_context: str
    risk_state: str
    workflow_state: str
    data_quality_state: str
    decision_state: str
    intelligence_context: str | None = None
    portfolio_state: str | None = None
    agent_observations: tuple[CycleAgentObservationRef, ...] = ()
    conflicts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("cycle_id", self.cycle_id)
        _require_non_empty("snapshot_id", self.snapshot_id)
        _require_utc_timestamp("cycle created_at", self.created_at)
        if self.symbol != self.symbol.upper() or not self.symbol.strip():
            raise ValueError("cycle symbol must be non-empty and uppercase")
        if self.timeframes != CANONICAL_DEFAULT_TIMEFRAMES:
            raise ValueError("cycle timeframes must match canonical shared state")
        for name, value in (
            ("market_snapshot", self.market_snapshot),
            ("feature_snapshot", self.feature_snapshot),
            ("evidence_context", self.evidence_context),
            ("risk_state", self.risk_state),
            ("workflow_state", self.workflow_state),
            ("data_quality_state", self.data_quality_state),
            ("decision_state", self.decision_state),
        ):
            _require_non_empty(name, value)
        for observation in self.agent_observations:
            if observation.snapshot_id != self.snapshot_id:
                raise ValueError("all agents in a cycle must consume same snapshot_id")
        _require_unique("cycle conflicts", self.conflicts)


@dataclass(frozen=True, slots=True)
class CapabilityImplementation:
    formula_id: str
    oracle_id: str

    def __post_init__(self) -> None:
        if not self.formula_id.strip() or not self.oracle_id.strip():
            raise ValueError("capability implementation requires formula and oracle")


@dataclass(frozen=True, slots=True)
class OracleDefinition:
    oracle_id: str
    capability_id: str
    expected_behavior: str
    version: str
    reference_cases: tuple[str, ...] = ()
    edge_cases: tuple[str, ...] = ()
    invalid_cases: tuple[str, ...] = ()
    domain: CanonicalDomainId = CanonicalDomainId.VALIDATION

    def __post_init__(self) -> None:
        for field_name in (
            "oracle_id",
            "capability_id",
            "expected_behavior",
            "version",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        if self.domain is not CanonicalDomainId.VALIDATION:
            raise ValueError("oracle definition must remain in 11_VALIDATION")
        _require_unique("oracle reference cases", self.reference_cases)
        _require_unique("oracle edge cases", self.edge_cases)
        _require_unique("oracle invalid cases", self.invalid_cases)


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    level: ScoreContributionLevel
    weight_ref: str

    def __post_init__(self) -> None:
        if not self.weight_ref.strip():
            raise ValueError("score contribution weight_ref cannot be empty")


@dataclass(frozen=True, slots=True)
class HardGateContract:
    eligible: HardGateEligibility
    promoted: bool = False

    def __post_init__(self) -> None:
        if self.promoted and self.eligible is HardGateEligibility.FALSE:
            raise ValueError("hard gate cannot be promoted when ineligible")


@dataclass(frozen=True, slots=True)
class CapabilitySafetyGuard:
    allowed: bool = False

    def __post_init__(self) -> None:
        if self.allowed:
            raise ValueError("capability repainting/lookahead must be disallowed")


@dataclass(frozen=True, slots=True)
class CapabilityValidationContract:
    validation_profile_id: str
    is_status: ValidationEvidenceStatus = ValidationEvidenceStatus.UNKNOWN
    wf_status: ValidationEvidenceStatus = ValidationEvidenceStatus.UNKNOWN
    oos_status: ValidationEvidenceStatus = ValidationEvidenceStatus.UNKNOWN
    regime_status: tuple[tuple[str, ValidationEvidenceStatus], ...] = ()
    stage_status: tuple[tuple[ValidationStage, ValidationEvidenceStatus], ...] = field(
        default_factory=lambda: tuple(
            (stage, ValidationEvidenceStatus.UNKNOWN) for stage in ValidationStage
        )
    )

    def __post_init__(self) -> None:
        if not self.validation_profile_id.strip():
            raise ValueError("validation_profile_id cannot be empty")
        keys = tuple(key for key, _status in self.regime_status)
        _require_unique("regime_status keys", keys)
        stage_keys = tuple(stage for stage, _status in self.stage_status)
        if stage_keys != tuple(ValidationStage):
            raise ValueError("validation stage_status must cover canonical stages")

    @property
    def regime_status_map(self) -> MappingProxyType[str, ValidationEvidenceStatus]:
        return MappingProxyType(dict(self.regime_status))

    @property
    def stage_status_map(
        self,
    ) -> MappingProxyType[ValidationStage, ValidationEvidenceStatus]:
        return MappingProxyType(dict(self.stage_status))


@dataclass(frozen=True, slots=True)
class CapabilityValidationMatrix:
    capability_id: str
    formula_id: str
    oracle_id: str
    validation_profile_id: str
    stage_status: tuple[tuple[ValidationStage, ValidationEvidenceStatus], ...]
    regime_evidence_ids: tuple[str, ...] = ()
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "capability_id",
            "formula_id",
            "oracle_id",
            "validation_profile_id",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        stage_keys = tuple(stage for stage, _status in self.stage_status)
        if stage_keys != tuple(ValidationStage):
            raise ValueError("capability validation matrix must cover 11_VALIDATION")
        _require_unique("regime evidence IDs", self.regime_evidence_ids)
        if self.promotion_eligible and not self.evidence_complete:
            raise ValueError("promotion requires complete capability validation chain")

    @property
    def evidence_complete(self) -> bool:
        stages_pass = all(
            status is ValidationEvidenceStatus.PASS
            for _stage, status in self.stage_status
        )
        return stages_pass and bool(self.regime_evidence_ids)

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers = [
            f"CAPABILITY_VALIDATION_{stage.name}_{status.value}"
            for stage, status in self.stage_status
            if status is not ValidationEvidenceStatus.PASS
        ]
        if not self.regime_evidence_ids:
            blockers.append("CAPABILITY_VALIDATION_REGIME_EVIDENCE_MISSING")
        return tuple(blockers)

    @classmethod
    def from_contract(cls, contract: CapabilityContract) -> CapabilityValidationMatrix:
        return cls(
            capability_id=contract.capability_id,
            formula_id=contract.implementation.formula_id,
            oracle_id=contract.implementation.oracle_id,
            validation_profile_id=contract.validation.validation_profile_id,
            stage_status=contract.validation.stage_status,
            regime_evidence_ids=tuple(
                f"regime:{name}"
                for name, status in contract.validation.regime_status
                if status is ValidationEvidenceStatus.PASS
            ),
            promotion_eligible=False,
        )


@dataclass(frozen=True, slots=True)
class CapabilityContract:
    capability_id: str
    version: str
    family: CapabilityFamily
    role: CapabilityRole
    implementation: CapabilityImplementation
    allowed_timeframes: tuple[str, ...]
    supported_markets: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    score_contribution: ScoreContribution
    hard_gate: HardGateContract
    known_failure_modes: tuple[str, ...]
    validation: CapabilityValidationContract
    lifecycle_status: CapabilityStatus
    repainting: CapabilitySafetyGuard = field(default_factory=CapabilitySafetyGuard)
    lookahead: CapabilitySafetyGuard = field(default_factory=CapabilitySafetyGuard)
    repainting_allowed: bool = False
    lookahead_allowed: bool = False
    owner: str = "FeatureEngineering"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in ("capability_id", "version", "owner"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        _require_unique("allowed_timeframes", self.allowed_timeframes)
        _require_unique("supported_markets", self.supported_markets)
        _require_unique("inputs", self.inputs)
        _require_unique("outputs", self.outputs)
        _require_unique("known_failure_modes", self.known_failure_modes)
        if not self.allowed_timeframes:
            raise ValueError("capability requires allowed_timeframes")
        if not self.supported_markets:
            raise ValueError("capability requires supported_markets")
        if not self.inputs or not self.outputs:
            raise ValueError("capability requires inputs and outputs")
        if self.repainting.allowed:
            raise ValueError("capability repainting must be disallowed")
        if self.lookahead.allowed:
            raise ValueError("capability lookahead must be disallowed")
        if self.repainting_allowed:
            raise ValueError("capability repainting must be disallowed")
        if self.lookahead_allowed:
            raise ValueError("capability lookahead must be disallowed")
        if self.hard_gate.promoted and (
            self.validation.oos_status is not ValidationEvidenceStatus.PASS
        ):
            raise ValueError("hard-gate promotion requires PASS OOS evidence")
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("capability contract cannot authorize trading")


@dataclass(frozen=True, slots=True)
class CapabilityCoverage:
    capability_id: str
    formula: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    oracle: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    unit_tests: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    regression: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    walk_forward: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    oos: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    regime_validation: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    evidence_complete: bool = False
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability coverage identity is required")
        required = (
            self.formula,
            self.oracle,
            self.unit_tests,
            self.regression,
            self.walk_forward,
            self.oos,
            self.regime_validation,
        )
        complete = all(status is ValidationEvidenceStatus.PASS for status in required)
        if self.evidence_complete != complete:
            raise ValueError("evidence_complete must reflect all PASS coverage")
        if self.promotion_eligible and not complete:
            raise ValueError("promotion eligibility requires complete PASS coverage")

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        status_by_name = (
            ("FORMULA", self.formula),
            ("ORACLE", self.oracle),
            ("UNIT_TESTS", self.unit_tests),
            ("REGRESSION", self.regression),
            ("WALK_FORWARD", self.walk_forward),
            ("OOS", self.oos),
            ("REGIME_VALIDATION", self.regime_validation),
        )
        for name, status in status_by_name:
            if status is ValidationEvidenceStatus.PASS:
                continue
            blockers.append(f"CAPABILITY_COVERAGE_{name}_{status.value}")
        return tuple(blockers)

    @classmethod
    def from_contract(cls, contract: CapabilityContract) -> CapabilityCoverage:
        formula = _present_as_pass(contract.implementation.formula_id)
        oracle = _present_as_pass(contract.implementation.oracle_id)
        return cls(
            capability_id=contract.capability_id,
            formula=formula,
            oracle=oracle,
            unit_tests=contract.validation.is_status,
            regression=ValidationEvidenceStatus.UNKNOWN,
            walk_forward=contract.validation.wf_status,
            oos=contract.validation.oos_status,
            regime_validation=_aggregate_regime_status(contract.validation),
            evidence_complete=False,
            promotion_eligible=False,
        )


class CapabilityGapArea(StrEnum):
    TREND = "Trend"
    VOLATILITY = "Volatility"
    MOMENTUM = "Momentum"
    STRUCTURE = "Structure"
    SUPPORT_RESISTANCE = "SupportResistance"
    DERIVATIVES = "Derivatives"
    VALIDATION = "Validation"
    OBSERVABILITY = "Observability"
    DATA_QUALITY = "DataQuality"
    RESEARCH = "Research"
    DGE = "DGE"


class CapabilityGapStatus(StrEnum):
    PRESENT_BUT_COVERAGE_INCOMPLETE = "PRESENT_BUT_COVERAGE_INCOMPLETE"
    CATALOG_GAP = "CATALOG_GAP"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    OPERATIONAL_GAP = "OPERATIONAL_GAP"
    MAPPING_GAP = "MAPPING_GAP"


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    area: CapabilityGapArea
    present_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    status: CapabilityGapStatus
    required_next_step: str
    coverage: CapabilityCoverage
    decision_contribution_allowed: bool = False
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        _require_unique("present capabilities", self.present_capabilities)
        _require_unique("missing capabilities", self.missing_capabilities)
        _require_non_empty("required next step", self.required_next_step)
        if self.coverage.capability_id != self.area.value:
            raise ValueError("capability gap coverage must reference the gap area")
        if self.coverage.evidence_complete:
            raise ValueError("visible capability gaps cannot claim complete evidence")
        if self.decision_contribution_allowed:
            raise ValueError("capability gaps cannot contribute to decisions")
        if self.promotion_eligible:
            raise ValueError("capability gaps cannot be promotion eligible")

    @property
    def blockers(self) -> tuple[str, ...]:
        return (
            f"CAPABILITY_GAP_{self.area.name}_{self.status.value}",
            *self.coverage.blockers,
        )


class CapabilityGapPriorityStep(StrEnum):
    CAPABILITY_INVENTORY = "Capability Inventory"
    CAPABILITY_COVERAGE_MATRIX = "Capability Coverage Matrix"
    FORMULA_ORACLE_CONTRACTS = "Formula/Oracle Contracts"
    OOS_EVIDENCE = "OOS Evidence"
    REGISTRY_MAPPING = "Registry Mapping"
    DECISION_CONTRIBUTION = "Decision Contribution"


@dataclass(frozen=True, slots=True)
class CapabilityGapRegistry:
    registry_id: str = "AI4BINANCE-CAPABILITY-GAP-REGISTRY"
    version: str = "2.0.0"
    priority_flow: tuple[CapabilityGapPriorityStep, ...] = tuple(
        CapabilityGapPriorityStep
    )
    gaps: tuple[CapabilityGap, ...] = ()
    default_missing_status: ValidationEvidenceStatus = ValidationEvidenceStatus.MISSING
    domain: CanonicalDomainId = CanonicalDomainId.DETERMINISTIC_ANALYTICS

    def __post_init__(self) -> None:
        _require_non_empty("capability gap registry_id", self.registry_id)
        _require_non_empty("capability gap registry version", self.version)
        if self.domain is not CanonicalDomainId.DETERMINISTIC_ANALYTICS:
            raise ValueError(
                "capability gap registry belongs to deterministic analytics"
            )
        if self.priority_flow != tuple(CapabilityGapPriorityStep):
            raise ValueError("capability gap priority flow must remain canonical")
        if self.default_missing_status is not ValidationEvidenceStatus.MISSING:
            raise ValueError("capability gaps must default missing evidence to MISSING")
        areas = tuple(gap.area for gap in self.gaps)
        if areas != tuple(CapabilityGapArea):
            raise ValueError("capability gap registry must cover every gap area")
        if any(gap.promotion_eligible for gap in self.gaps):
            raise ValueError("visible capability gaps cannot be promotion eligible")

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(blocker for gap in self.gaps for blocker in gap.blockers)


@dataclass(frozen=True, slots=True)
class AgentCapabilityGovernance:
    agent_id: str
    capability_ids: tuple[str, ...]
    capability_coverage: tuple[CapabilityCoverage, ...]
    agent_oos_status: ValidationEvidenceStatus = ValidationEvidenceStatus.UNKNOWN
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("agent_id", self.agent_id)
        _require_unique("agent capability_ids", self.capability_ids)
        if not self.capability_ids:
            raise ValueError("agent must contain at least one capability")
        coverage_ids = tuple(item.capability_id for item in self.capability_coverage)
        _require_unique("agent capability coverage IDs", coverage_ids)
        missing = tuple(
            capability_id
            for capability_id in self.capability_ids
            if capability_id not in coverage_ids
        )
        if missing:
            raise ValueError(
                "agent capability governance requires coverage for every capability"
            )
        complete = all(item.evidence_complete for item in self.capability_coverage)
        if self.promotion_eligible and not complete:
            raise ValueError("agent promotion requires complete capability coverage")
        if self.promotion_eligible and (
            self.agent_oos_status is not ValidationEvidenceStatus.PASS
        ):
            raise ValueError("agent promotion requires PASS agent OOS status")


@dataclass(frozen=True, slots=True)
class RegistryDefinition:
    registry: RegistryKind
    owner: str
    concept: EngineeringConcept
    description: str
    status: str = "ACTIVE"

    def __post_init__(self) -> None:
        for field_name in ("owner", "description", "status"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")


@dataclass(frozen=True, slots=True)
class GovernedRegistryEntry:
    entry_id: str
    registry: RegistryKind
    name: str
    version: str
    owner: str
    concept: EngineeringConcept
    lifecycle_status: str = "RESEARCH_ONLY"
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    policy_ids: tuple[str, ...] = field(default_factory=tuple)
    dependency_ids: tuple[str, ...] = field(default_factory=tuple)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in (
            "entry_id",
            "name",
            "version",
            "owner",
            "lifecycle_status",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        _require_unique("evidence_ids", self.evidence_ids)
        _require_unique("policy_ids", self.policy_ids)
        _require_unique("dependency_ids", self.dependency_ids)
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("registry entries cannot grant trading authority")


@dataclass(frozen=True, slots=True)
class CapabilityValidationChain:
    capability_id: StructuralCapabilityId
    formula_id: str
    oracle_id: str
    test_ids: tuple[str, ...]
    oos_artifact_ids: tuple[str, ...]
    regime_evidence_ids: tuple[str, ...]
    owner: str
    status: CapabilityStatus = CapabilityStatus.RESEARCH_ONLY
    hard_gate_eligible: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in ("formula_id", "oracle_id", "owner"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        _require_unique("test_ids", self.test_ids)
        _require_unique("oos_artifact_ids", self.oos_artifact_ids)
        _require_unique("regime_evidence_ids", self.regime_evidence_ids)
        if not self.test_ids:
            raise ValueError("capability validation chain requires tests")
        hard_gate_without_oos = (
            self.hard_gate_eligible
            and self.status is not CapabilityStatus.OOS_VALIDATED
        )
        if hard_gate_without_oos:
            raise ValueError("hard-gate capability requires OOS_VALIDATED status")
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("capability validation chain cannot authorize trading")

    @property
    def evidence_complete(self) -> bool:
        return bool(
            self.test_ids and self.oos_artifact_ids and self.regime_evidence_ids
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.test_ids:
            blockers.append("CAPABILITY_TESTS_MISSING")
        if not self.oos_artifact_ids:
            blockers.append("CAPABILITY_OOS_ARTIFACTS_MISSING")
        if not self.regime_evidence_ids:
            blockers.append("CAPABILITY_REGIME_EVIDENCE_MISSING")
        if self.status is not CapabilityStatus.OOS_VALIDATED:
            blockers.append("CAPABILITY_NOT_OOS_VALIDATED")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class MarketDataContract:
    kind: MarketDataKind
    spot_authority: SpotDecisionAuthority
    required_for_spot_decision: bool
    description: str

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("market data contract description cannot be empty")
        if (
            self.required_for_spot_decision
            and self.spot_authority is not SpotDecisionAuthority.DECISION_AUTHORITY
        ):
            raise ValueError("required Spot data must be decision-authoritative")


@dataclass(frozen=True, slots=True)
class GovernanceRegistryCatalog:
    catalog_id: str
    version: str
    definitions: tuple[RegistryDefinition, ...]
    entries: tuple[GovernedRegistryEntry, ...] = ()
    _definitions_by_kind: MappingProxyType[RegistryKind, RegistryDefinition] = field(
        init=False,
        repr=False,
    )
    _entries_by_id: MappingProxyType[str, GovernedRegistryEntry] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.catalog_id.strip() or not self.version.strip():
            raise ValueError("governance registry catalog identity is required")
        definitions_by_kind = {item.registry: item for item in self.definitions}
        if len(definitions_by_kind) != len(self.definitions):
            raise ValueError("registry definitions must be unique")
        missing = tuple(
            kind for kind in MANDATORY_REGISTRY_KINDS if kind not in definitions_by_kind
        )
        if missing:
            names = ", ".join(kind.value for kind in missing)
            raise ValueError(f"mandatory registry definitions missing: {names}")
        entries_by_id = {item.entry_id: item for item in self.entries}
        if len(entries_by_id) != len(self.entries):
            raise ValueError("registry entry IDs must be unique")
        for entry in self.entries:
            if entry.registry not in definitions_by_kind:
                raise ValueError("registry entry references an unknown registry")
        object.__setattr__(
            self,
            "_definitions_by_kind",
            MappingProxyType(definitions_by_kind),
        )
        object.__setattr__(self, "_entries_by_id", MappingProxyType(entries_by_id))

    @property
    def definitions_by_kind(self) -> MappingProxyType[RegistryKind, RegistryDefinition]:
        return self._definitions_by_kind

    @property
    def entries_by_id(self) -> MappingProxyType[str, GovernedRegistryEntry]:
        return self._entries_by_id

    def entries_for(self, registry: RegistryKind) -> tuple[GovernedRegistryEntry, ...]:
        return tuple(item for item in self.entries if item.registry is registry)


def build_structure_capability_chains() -> tuple[CapabilityValidationChain, ...]:
    """Return fail-closed structure capabilities with explicit validation chain IDs."""
    return tuple(
        CapabilityValidationChain(
            capability_id=capability,
            formula_id=f"formula:structure:{capability.value}:1",
            oracle_id=f"oracle:structure:{capability.value}:1",
            test_ids=(f"test:structure:{capability.value}:contract",),
            oos_artifact_ids=(),
            regime_evidence_ids=(),
            owner="FeatureEngineering",
            status=CapabilityStatus.RESEARCH_ONLY,
        )
        for capability in StructuralCapabilityId
    )


def build_structure_capability_contracts() -> tuple[CapabilityContract, ...]:
    """Return canonical fail-closed structure capability contracts."""
    return tuple(
        CapabilityContract(
            capability_id=capability.value,
            version="1",
            family=CapabilityFamily.STRUCTURE,
            role=CapabilityRole.PRIMARY,
            implementation=CapabilityImplementation(
                formula_id=f"formula:structure:{capability.value}:1",
                oracle_id=f"oracle:structure:{capability.value}:1",
            ),
            allowed_timeframes=CANONICAL_DEFAULT_TIMEFRAMES,
            supported_markets=("SPOT",),
            inputs=("MarketSnapshot", "FeatureSnapshot"),
            outputs=(f"Feature:{capability.value}",),
            score_contribution=ScoreContribution(
                ScoreContributionLevel.HIGH,
                "weight:structure_score:baseline-v1",
            ),
            hard_gate=HardGateContract(HardGateEligibility.CONDITIONAL),
            known_failure_modes=(
                "CHOP_FALSE_BREAK",
                "LOW_LIQUIDITY_NOISE",
                "LATE_CONFIRMATION",
            ),
            validation=CapabilityValidationContract(
                validation_profile_id=f"validation:structure:{capability.value}:1",
                is_status=ValidationEvidenceStatus.UNKNOWN,
                wf_status=ValidationEvidenceStatus.UNKNOWN,
                oos_status=ValidationEvidenceStatus.UNKNOWN,
                regime_status=(("trend", ValidationEvidenceStatus.UNKNOWN),),
            ),
            lifecycle_status=CapabilityStatus.RESEARCH_ONLY,
        )
        for capability in StructuralCapabilityId
    )


def build_capability_coverage_matrix(
    contracts: tuple[CapabilityContract, ...],
) -> tuple[CapabilityCoverage, ...]:
    """Return machine-readable coverage rows without promoting missing evidence."""
    return tuple(CapabilityCoverage.from_contract(contract) for contract in contracts)


def _gap_coverage(area: CapabilityGapArea) -> CapabilityCoverage:
    return CapabilityCoverage(capability_id=area.value)


def build_capability_gap_registry() -> CapabilityGapRegistry:
    """Return visible system gaps without assuming operational or OOS evidence."""
    return CapabilityGapRegistry(
        gaps=(
            CapabilityGap(
                area=CapabilityGapArea.TREND,
                present_capabilities=("EMA", "Supertrend", "trend channel"),
                missing_capabilities=("capability coverage",),
                status=CapabilityGapStatus.PRESENT_BUT_COVERAGE_INCOMPLETE,
                required_next_step=(
                    "Build Trend capability inventory and coverage rows."
                ),
                coverage=_gap_coverage(CapabilityGapArea.TREND),
            ),
            CapabilityGap(
                area=CapabilityGapArea.VOLATILITY,
                present_capabilities=("ATR",),
                missing_capabilities=(
                    "Bollinger",
                    "Keltner",
                    "squeeze",
                    "realized-volatility catalog",
                ),
                status=CapabilityGapStatus.CATALOG_GAP,
                required_next_step="Create volatility atom catalog before scoring use.",
                coverage=_gap_coverage(CapabilityGapArea.VOLATILITY),
            ),
            CapabilityGap(
                area=CapabilityGapArea.MOMENTUM,
                present_capabilities=("RSI", "momentum"),
                missing_capabilities=("MACD", "Stochastic", "ROC", "CCI"),
                status=CapabilityGapStatus.CATALOG_GAP,
                required_next_step=(
                    "Complete momentum atoms and formula/oracle contracts."
                ),
                coverage=_gap_coverage(CapabilityGapArea.MOMENTUM),
            ),
            CapabilityGap(
                area=CapabilityGapArea.STRUCTURE,
                present_capabilities=("confirmed swing",),
                missing_capabilities=("BOS evidence", "CHoCH evidence"),
                status=CapabilityGapStatus.EVIDENCE_GAP,
                required_next_step="Separate BOS and CHoCH OOS evidence chains.",
                coverage=_gap_coverage(CapabilityGapArea.STRUCTURE),
            ),
            CapabilityGap(
                area=CapabilityGapArea.SUPPORT_RESISTANCE,
                present_capabilities=("lookback min/max",),
                missing_capabilities=(
                    "pivot",
                    "cluster",
                    "zone decay",
                    "reaction statistics",
                ),
                status=CapabilityGapStatus.CATALOG_GAP,
                required_next_step="Catalog S/R atoms and reaction-stat validation.",
                coverage=_gap_coverage(CapabilityGapArea.SUPPORT_RESISTANCE),
            ),
            CapabilityGap(
                area=CapabilityGapArea.DERIVATIVES,
                present_capabilities=("funding", "OI", "long-short surfaces"),
                missing_capabilities=(
                    "ratio evidence",
                    "parity evidence",
                    "OOS evidence",
                ),
                status=CapabilityGapStatus.EVIDENCE_GAP,
                required_next_step=(
                    "Keep derivatives advisory until ratio/parity OOS exists."
                ),
                coverage=_gap_coverage(CapabilityGapArea.DERIVATIVES),
            ),
            CapabilityGap(
                area=CapabilityGapArea.VALIDATION,
                present_capabilities=(
                    "WF",
                    "OOS",
                    "overfit",
                    "multiple-testing infrastructure",
                ),
                missing_capabilities=("capability-specific OOS artifacts",),
                status=CapabilityGapStatus.EVIDENCE_GAP,
                required_next_step="Attach real OOS artifacts to each capability.",
                coverage=_gap_coverage(CapabilityGapArea.VALIDATION),
            ),
            CapabilityGap(
                area=CapabilityGapArea.OBSERVABILITY,
                present_capabilities=("local trace", "metrics", "audit"),
                missing_capabilities=("capability health", "decision health"),
                status=CapabilityGapStatus.OPERATIONAL_GAP,
                required_next_step="Add capability and decision health observability.",
                coverage=_gap_coverage(CapabilityGapArea.OBSERVABILITY),
            ),
            CapabilityGap(
                area=CapabilityGapArea.DATA_QUALITY,
                present_capabilities=("temporal lineage", "gap controls"),
                missing_capabilities=("expectation catalog", "capability catalog"),
                status=CapabilityGapStatus.CATALOG_GAP,
                required_next_step="Map data expectations to capability coverage.",
                coverage=_gap_coverage(CapabilityGapArea.DATA_QUALITY),
            ),
            CapabilityGap(
                area=CapabilityGapArea.RESEARCH,
                present_capabilities=("license", "hash", "quarantine"),
                missing_capabilities=(
                    "Radar to ResearchUnit",
                    "ResearchUnit to Capability",
                    "Capability to Validation",
                    "Validation to Promotion",
                ),
                status=CapabilityGapStatus.MAPPING_GAP,
                required_next_step="Wire research promotion chain end to end.",
                coverage=_gap_coverage(CapabilityGapArea.RESEARCH),
            ),
            CapabilityGap(
                area=CapabilityGapArea.DGE,
                present_capabilities=("blocker-first", "rule catalog"),
                missing_capabilities=("Radar capability-gap mapping",),
                status=CapabilityGapStatus.MAPPING_GAP,
                required_next_step="Map DGE findings into Radar capability gaps.",
                coverage=_gap_coverage(CapabilityGapArea.DGE),
            ),
        )
    )


def build_market_data_contracts() -> tuple[MarketDataContract, ...]:
    """Return canonical market-data authority boundaries for Spot decisions."""
    authority = SpotDecisionAuthority.DECISION_AUTHORITY
    advisory = SpotDecisionAuthority.SUPPLEMENTARY_ADVISORY
    return (
        MarketDataContract(MarketDataKind.OHLCV, authority, True, "Spot candles."),
        MarketDataContract(
            MarketDataKind.TICKER,
            authority,
            True,
            "Latest Spot price.",
        ),
        MarketDataContract(MarketDataKind.TRADES, authority, False, "Spot trades."),
        MarketDataContract(
            MarketDataKind.AGG_TRADES,
            authority,
            False,
            "Aggregated Spot trades.",
        ),
        MarketDataContract(
            MarketDataKind.ORDER_BOOK_SNAPSHOT,
            authority,
            True,
            "Spot depth snapshot.",
        ),
        MarketDataContract(
            MarketDataKind.ORDER_BOOK_DELTA,
            authority,
            False,
            "Spot depth deltas.",
        ),
        MarketDataContract(MarketDataKind.SPREAD, authority, True, "Spot spread."),
        MarketDataContract(
            MarketDataKind.LIQUIDITY,
            authority,
            True,
            "Spot liquidity.",
        ),
        MarketDataContract(
            MarketDataKind.EXCHANGE_INFO,
            authority,
            True,
            "Binance exchange metadata.",
        ),
        MarketDataContract(
            MarketDataKind.SYMBOL_FILTERS,
            authority,
            True,
            "Tick, lot, and notional filters.",
        ),
        MarketDataContract(
            MarketDataKind.MARKET_STATUS,
            authority,
            True,
            "Exchange and symbol availability state.",
        ),
        MarketDataContract(
            MarketDataKind.FUNDING,
            advisory,
            False,
            "Futures funding is supplementary for Spot.",
        ),
        MarketDataContract(
            MarketDataKind.OPEN_INTEREST,
            advisory,
            False,
            "Futures open interest is supplementary for Spot.",
        ),
        MarketDataContract(
            MarketDataKind.LONG_SHORT_RATIO,
            advisory,
            False,
            "Futures long-short ratio is supplementary for Spot.",
        ),
        MarketDataContract(
            MarketDataKind.TOP_TRADER_RATIO,
            advisory,
            False,
            "Top trader ratio is supplementary for Spot.",
        ),
        MarketDataContract(
            MarketDataKind.TAKER_FLOW,
            advisory,
            False,
            "Futures taker flow is supplementary for Spot.",
        ),
        MarketDataContract(
            MarketDataKind.SERVER_TIME,
            authority,
            True,
            "Server-time validity for Spot gates.",
        ),
    )


def build_ai4binance_governance_registry_catalog() -> GovernanceRegistryCatalog:
    """Return the canonical registry shell requested for AI4BINANCE vNext."""
    return GovernanceRegistryCatalog(
        catalog_id="AI4BINANCE-GOVERNANCE-REGISTRY",
        version="2.0.0",
        definitions=(
            RegistryDefinition(
                RegistryKind.AGENT,
                "AgenticOrchestration",
                EngineeringConcept.AGENTIC_ORCHESTRATION_ENGINEERING,
                "Bounded agents with no final trade or execution authority.",
            ),
            RegistryDefinition(
                RegistryKind.CAPABILITY,
                "FeatureEngineering",
                EngineeringConcept.FEATURE_ENGINEERING,
                "Validated capability chains and coverage status.",
            ),
            RegistryDefinition(
                RegistryKind.SKILL,
                "AgenticOrchestration",
                EngineeringConcept.AGENTIC_ORCHESTRATION_ENGINEERING,
                "Governed skills with bounded authority and validation evidence.",
            ),
            RegistryDefinition(
                RegistryKind.TOOL,
                "SecurityReliability",
                EngineeringConcept.SECURITY_RELIABILITY_ENGINEERING,
                "Default-deny tool contracts and side-effect classifications.",
            ),
            RegistryDefinition(
                RegistryKind.MODEL,
                "ModelInference",
                EngineeringConcept.MODEL_INFERENCE_ENGINEERING,
                "Local and advisory model contracts, fingerprints, and limits.",
            ),
            RegistryDefinition(
                RegistryKind.PROMPT,
                "ModelInference",
                EngineeringConcept.MODEL_INFERENCE_ENGINEERING,
                "Advisory prompt contracts with authority stamps.",
            ),
            RegistryDefinition(
                RegistryKind.STRATEGY,
                "DecisionGovernance",
                EngineeringConcept.DECISION_GOVERNANCE_ENGINEERING,
                "Validated strategy contracts and promotion states.",
            ),
            RegistryDefinition(
                RegistryKind.INDICATOR,
                "FeatureEngineering",
                EngineeringConcept.FEATURE_ENGINEERING,
                "Indicator formulas, oracle expectations, and failure modes.",
            ),
            RegistryDefinition(
                RegistryKind.PATTERN,
                "FeatureEngineering",
                EngineeringConcept.FEATURE_ENGINEERING,
                "Pattern contracts, false-positive risks, and validation state.",
            ),
            RegistryDefinition(
                RegistryKind.PARAMETER,
                "BacktestValidation",
                EngineeringConcept.BACKTEST_VALIDATION_ENGINEERING,
                "Versioned scoring, strategy, risk, and tuning parameter sets.",
            ),
            RegistryDefinition(
                RegistryKind.WORKFLOW,
                "AgenticOrchestration",
                EngineeringConcept.AGENTIC_ORCHESTRATION_ENGINEERING,
                "Deterministic workflow manifests and audit routes.",
            ),
            RegistryDefinition(
                RegistryKind.DATA_SOURCE,
                "DataEngineering",
                EngineeringConcept.MARKET_DATA_ENGINEERING,
                "Credential-safe exchange, official, and research data sources.",
            ),
            RegistryDefinition(
                RegistryKind.DATASET,
                "DataEngineering",
                EngineeringConcept.MARKET_DATA_ENGINEERING,
                "Governed immutable datasets and validation snapshots.",
            ),
            RegistryDefinition(
                RegistryKind.FEATURE,
                "FeatureEngineering",
                EngineeringConcept.FEATURE_ENGINEERING,
                "Versioned deterministic feature and capability outputs.",
            ),
            RegistryDefinition(
                RegistryKind.RISK_RULE,
                "RiskPortfolio",
                EngineeringConcept.RISK_PORTFOLIO_ENGINEERING,
                "Risk rules, blockers, limits, and safe-state controls.",
            ),
            RegistryDefinition(
                RegistryKind.CONTROL,
                "Governance",
                EngineeringConcept.DECISION_GOVERNANCE_ENGINEERING,
                "Controls that mitigate risks and verify requirements.",
            ),
            RegistryDefinition(
                RegistryKind.POLICY,
                "Governance",
                EngineeringConcept.DECISION_GOVERNANCE_ENGINEERING,
                "Policy-as-code documents and approval rules.",
            ),
            RegistryDefinition(
                RegistryKind.REQUIREMENT,
                "Governance",
                EngineeringConcept.ONTOLOGY_SCHEMA_ENGINEERING,
                "External and internal requirements mapped to controls.",
            ),
            RegistryDefinition(
                RegistryKind.RESEARCH_UNIT,
                "ResearchGovernance",
                EngineeringConcept.EVIDENCE_KNOWLEDGE_ENGINEERING,
                "Research findings staged before capability validation.",
            ),
            RegistryDefinition(
                RegistryKind.ORACLE,
                "BacktestValidation",
                EngineeringConcept.BACKTEST_VALIDATION_ENGINEERING,
                "Expected behavior references for capability validation.",
            ),
            RegistryDefinition(
                RegistryKind.FORMULA,
                "FeatureEngineering",
                EngineeringConcept.FEATURE_ENGINEERING,
                "Versioned deterministic formulas for capabilities.",
            ),
            RegistryDefinition(
                RegistryKind.VALIDATION_PROFILE,
                "BacktestValidation",
                EngineeringConcept.BACKTEST_VALIDATION_ENGINEERING,
                "Validation profiles for tests, OOS, and regime evidence.",
            ),
        ),
    )


def build_canonical_entity_ontology() -> CanonicalEntityOntology:
    return CanonicalEntityOntology()


def build_entity_rule_catalog() -> EntityRuleCatalog:
    return EntityRuleCatalog()


def build_core_architecture() -> CoreArchitecture:
    """Return the canonical 00-18 domain architecture and physical planes."""
    return CoreArchitecture(
        architecture_id="AI4BINANCE-CORE-ARCHITECTURE",
        version="2.0.0",
        domains=(
            CanonicalDomainDefinition(
                CanonicalDomainId.META,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "Governance",
                "Common metadata, schema versioning, platform defaults and clocks.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.REGISTRIES,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "Governance",
                "Governance registries for components, policies and capabilities.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.MARKET_DATA,
                ArchitecturePlane.DATA_EVIDENCE,
                "DataEngineering",
                "Raw and normalized Binance Spot/Futures market data contracts.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.SHARED_MARKET_STATE,
                ArchitecturePlane.DATA_EVIDENCE,
                "ContextStateEngineering",
                "One canonical snapshot and shared state consumed by all agents.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.INTELLIGENCE,
                ArchitecturePlane.INTELLIGENCE,
                "MarketIntelligence",
                "External intelligence, source validation and bounded context.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.DETERMINISTIC_ANALYTICS,
                ArchitecturePlane.INTELLIGENCE,
                "FeatureEngineering",
                "Formula-backed deterministic analytics and capability outputs.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.AGENT_OBSERVATIONS,
                ArchitecturePlane.INTELLIGENCE,
                "AgenticOrchestration",
                "Bounded agent observations with no final decision authority.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.DECISION,
                ArchitecturePlane.DECISION_EXECUTION,
                "DecisionGovernance",
                "Deterministic decision evidence, setup qualification and action.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.RISK,
                ArchitecturePlane.DECISION_EXECUTION,
                "RiskPortfolio",
                "Risk assessment, blockers, constraints and exposure budgets.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.PORTFOLIO,
                ArchitecturePlane.DECISION_EXECUTION,
                "RiskPortfolio",
                "Wallet, inventory, balances, exposure and open-order context.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.EXECUTION,
                ArchitecturePlane.DECISION_EXECUTION,
                "Execution",
                "Manual, dry-run, paper and gated execution records.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.VALIDATION,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "BacktestValidation",
                "Backtest, walk-forward, OOS, robustness and promotion evidence.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.LEARNING,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "LearningGovernance",
                "Controlled learning candidates, lessons and staged hypotheses.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.GOVERNANCE,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "Governance",
                "Policy, approval, operating envelope and promotion enforcement.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.EVIDENCE,
                ArchitecturePlane.DATA_EVIDENCE,
                "EvidenceKnowledge",
                "Append-only evidence, provenance, claims and contradictions.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.AUDIT_OBSERVABILITY,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "EvaluationObservability",
                "Logs, metrics, traces, lineage, controls and incidents.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.SECURITY,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "SecurityReliability",
                "Identity, RBAC, secrets, supply-chain and incident controls.",
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.EVENT_FABRIC,
                ArchitecturePlane.ORCHESTRATION_EVENT_FABRIC,
                "AgenticOrchestration",
                "Event envelope and orchestration backbone across all planes.",
                backbone=True,
            ),
            CanonicalDomainDefinition(
                CanonicalDomainId.RESEARCH_CAPABILITY,
                ArchitecturePlane.CONTROL_ASSURANCE,
                "ResearchGovernance",
                "ResearchUnit to Capability to Validation to Promotion lifecycle.",
            ),
        ),
    )


def build_core_constitution() -> CoreConstitution:
    """Return the immutable AI4BINANCE vNext constitution contract."""
    return CoreConstitution(
        constitution_id="AI4BINANCE-CORE-CONSTITUTION",
        version="2.0.0",
        mission=(
            "AI4Binance EnterpriseAI vNext is an ontology-driven, evidence-based, "
            "event-driven, multi-agent and multi-timeframe market-intelligence "
            "platform for Binance Spot/Futures research, decision-support and "
            "paper trading. Final trading decisions are owned by the deterministic "
            "Decision Core, Risk Engine and Governance Enforcement, not by LLMs "
            "or agents."
        ),
        authority_principles=(
            AuthorityPrinciple(
                CoreAuthorityOwner.DATA,
                "DATA establishes market facts.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.FEATURES,
                "FEATURES derive deterministic measurements.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.EVIDENCE,
                "EVIDENCE supports or contradicts claims.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.AGENTS,
                "AGENTS create bounded observations.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.STRATEGIES,
                "STRATEGIES qualify setups.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.DETERMINISTIC_CORE,
                "DETERMINISTIC CORE calculates decision evidence.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.RISK,
                "RISK constrains capital exposure.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.GOVERNANCE,
                "GOVERNANCE defines what is allowed.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.EXECUTION,
                "EXECUTION obeys gates.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.AUDIT,
                "AUDIT preserves lineage.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.HUMAN,
                "HUMAN retains live authority.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.LEARNING,
                "LEARNING proposes candidates.",
            ),
            AuthorityPrinciple(
                CoreAuthorityOwner.VALIDATION,
                "VALIDATION determines promotion eligibility.",
            ),
        ),
        cycle=tuple(CanonicalCycleStep),
        rules=(
            CoreConstitutionRule(
                CoreConstitutionRuleId.C01,
                "CAPITAL_PROTECTION > TRADE_FREQUENCY",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C02,
                "NO_EVIDENCE -> NO_TRUST",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C03,
                "NO_VALIDATION -> NO_PROMOTION",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C04,
                "NO_APPROVAL -> NO_EXECUTION",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C05,
                "HARD_BLOCKER -> NO_TRADE",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C06,
                "UNKNOWN_CRITICAL_STATE -> DENY",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C07,
                "AGENT != FINAL_DECISION_AUTHORITY",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C08,
                "LLM != RISK_AUTHORITY",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C09,
                "LLM != EXECUTION_AUTHORITY",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C10,
                "LEARNING != DEPLOYMENT",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C11,
                "RAW_DATA != FEATURE != OBSERVATION != EVIDENCE != DECISION",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C12,
                "STATE != MEMORY != KNOWLEDGE != EVIDENCE != LEARNING",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C13,
                "WALLET_STATE MUST NOT contaminate historical backtests",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C14,
                "ONE AGENT MUST NOT create its own canonical market truth",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C15,
                "NO DIRECT AGENT -> LIVE_ORDER PATH",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C16,
                "EVERY DECISION MUST HAVE LINEAGE",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C17,
                "EVERY BEHAVIOR-CHANGING COMPONENT MUST BE VERSIONED",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C18,
                (
                    "EVERY GOVERNED COMPONENT MUST HAVE OWNERSHIP AND "
                    "NON-CODE CONTENT LANGUAGE en-US"
                ),
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C19,
                "HARD GATES REQUIRE STABLE OOS EVIDENCE",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C20,
                "MISSING EVIDENCE IS UNKNOWN, NEVER ASSUMED",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C21,
                "SOCIAL CLAIM ALONE CANNOT AUTHORIZE A TRADE",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C22,
                "LOOKAHEAD/REPAINTING RESEARCH CANNOT BECOME TRADING LOGIC",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C23,
                "UNKNOWN SOFTWARE LICENSE -> NO_CODE_REUSE",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C24,
                "FAIL_SAFE > FAIL_OPEN",
            ),
            CoreConstitutionRule(
                CoreConstitutionRuleId.C25,
                "LIVE IS OPT-IN; PAPER/MANUAL IS DEFAULT",
            ),
        ),
    )


def build_core_meta() -> CoreMeta:
    return CoreMeta()


def build_external_intelligence_evidence_fabric() -> ExternalIntelligenceEvidenceFabric:
    return ExternalIntelligenceEvidenceFabric(
        fabric_id="AI4BINANCE-EXTERNAL-INTELLIGENCE-EVIDENCE-FABRIC",
        version="2.0.0",
    )


def build_web_intelligence_radar_contract() -> WebIntelligenceRadarContract:
    """Return the research-only radar used by the LOOPS improvement cycle."""
    return WebIntelligenceRadarContract()


def build_loops_self_improvement_contract() -> LoopsSelfImprovementContract:
    """Return the governed self-improvement loop without deployment authority."""
    return LoopsSelfImprovementContract(
        steps=(
            LoopsStep(
                LoopsStage.LISTEN,
                "Listen to outcomes, closure reviews and audit findings.",
                ("Outcome", "ClosureReview", "AuditEvent"),
                ("Lesson",),
                ("decision_lineage", "closure_review", "audit_event"),
            ),
            LoopsStep(
                LoopsStage.OBSERVE,
                (
                    "Observe public technology and risk evidence with Web "
                    "Intelligence Radar."
                ),
                ("Lesson", "CapabilityGapRegistry"),
                ("RadarFinding", "EvidencePack"),
                ("source_reference", "content_hash", "freshness_score"),
            ),
            LoopsStep(
                LoopsStage.ORIENT,
                "Orient evidence into hypotheses and governed research candidates.",
                ("RadarFinding", "EvidencePack", "CapabilityGap"),
                ("Hypothesis", "LearningCandidate", "GovernanceIntake"),
                ("evidence_ids", "conflict_check", "license_status"),
            ),
            LoopsStep(
                LoopsStage.PROVE,
                "Prove candidates through formula, oracle, tests, WF, OOS and regimes.",
                ("LearningCandidate", "ResearchUnit", "CapabilityCandidate"),
                ("Validation", "ValidationArtifact", "PromotionReview"),
                ("formula_id", "oracle_id", "wf_artifact", "oos_artifact"),
            ),
            LoopsStep(
                LoopsStage.STAGE,
                "Stage validated candidates for human-governed promotion or rejection.",
                ("PromotionReview", "ValidationArtifact", "GovernanceIntake"),
                ("GovernanceReleaseRecord", "RegistryComponent", "Finding"),
                ("approval_record", "operating_envelope", "rollback_plan"),
            ),
        ),
        web_intelligence_radar=build_web_intelligence_radar_contract(),
    )


def build_digital_company_operating_model() -> DigitalCompanyOperatingModel:
    """Return the transparent digital-company authority model for AI4BINANCE."""
    return DigitalCompanyOperatingModel(
        pyramid=(
            GovernancePyramidLayer(
                GovernancePyramidLevel.HUMAN_BOARD,
                "Human Owner / Board",
                ("live authority", "capital mandate", "final approval"),
                ("automated live approval",),
                ("explicit_user_request", "approval_record"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.GOVERNANCE_OFFICE,
                "Governance Office",
                ("policy ownership", "exception handling", "release governance"),
                ("risk override", "execution bypass"),
                ("policy_version", "governance_release_record"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.POLICY_AS_CODE,
                "Policy-as-Code Engine",
                ("runtime deny/allow evaluation", "authority enforcement"),
                ("profit guarantee", "manual evidence fabrication"),
                ("policy_request", "policy_evaluation"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.GOVERNANCE_REGISTRY,
                "Governance Registry",
                ("registry ownership", "version lineage", "component status"),
                ("ownerless production", "unversioned behavior change"),
                ("registry_entry", "ownership_record"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.DATA_EVIDENCE_CAPABILITY,
                "Data, Evidence and Capability Owners",
                ("snapshot integrity", "evidence provenance", "capability coverage"),
                ("missing evidence as PASS", "raw data overwrite"),
                ("snapshot_id", "evidence_pack", "coverage_row"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.INTELLIGENCE_AGENTS_STRATEGIES,
                "Agents and Strategies",
                ("bounded observations", "setup qualification", "research proposals"),
                ("final trade decision", "risk override", "live execution"),
                ("agent_observation", "strategy_candidate", "evidence_ids"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.DETERMINISTIC_DECISION_RISK,
                "Deterministic Core and Risk Engine",
                ("scoring", "hard blocker evaluation", "risk assessment"),
                ("governance maturity escalation", "missing gate override"),
                ("decision_id", "risk_assessment_id", "blocker_list"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.EXECUTION_GATES,
                "Execution Gates",
                ("paper/manual routing", "live gate denial", "execution tagging"),
                ("agent direct order", "live order without all gates"),
                ("execution_gate_result", "exchange_filter_check"),
            ),
            GovernancePyramidLayer(
                GovernancePyramidLevel.AUDIT_ASSURANCE_LEARNING,
                "Audit, Assurance and Learning",
                ("lineage preservation", "continuous assurance", "LOOPS proposals"),
                ("self-promotion", "silent historical modification"),
                ("audit_event", "assurance_state", "learning_candidate"),
            ),
        ),
        loops_contract=build_loops_self_improvement_contract(),
    )


def build_deterministic_analytics_catalog() -> DeterministicAnalyticsCatalog:
    return DeterministicAnalyticsCatalog(
        catalog_id="AI4BINANCE-DETERMINISTIC-ANALYTICS-CATALOG",
        version="2.0.0",
        technical_families=(
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.TREND,
                feature_family=DeterministicFeatureFamily.TREND,
                role=CapabilityRole.PRIMARY,
                allowed_timeframes=("1h", "4h", "1d", "15m"),
                score_contribution=ScoreContributionLevel.HIGH,
                hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
                hard_gate_description="OOS-eligible",
                false_positive_risks=("chop", "late reversal"),
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.VOLATILITY,
                feature_family=DeterministicFeatureFamily.VOLATILITY,
                role=CapabilityRole.PRIMARY_RISK_FILTER,
                allowed_timeframes=("15m", "1h", "4h"),
                score_contribution=ScoreContributionLevel.MEDIUM,
                hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
                hard_gate_description="blocker eligible",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.MOMENTUM,
                feature_family=DeterministicFeatureFamily.MOMENTUM,
                role=CapabilityRole.SECONDARY,
                allowed_timeframes=CANONICAL_DEFAULT_TIMEFRAMES,
                score_contribution=ScoreContributionLevel.MEDIUM,
                hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
                hard_gate_description="soft unless independently proven",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.VOLUME,
                feature_family=DeterministicFeatureFamily.VOLUME,
                role=CapabilityRole.DIAGNOSTIC,
                allowed_timeframes=("15m", "1h", "4h"),
                score_contribution=ScoreContributionLevel.MEDIUM,
                hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
                hard_gate_description="breakout-quality only if validated",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.PRICE_ACTION,
                feature_family=DeterministicFeatureFamily.PRICE_ACTION,
                role=CapabilityRole.PRIMARY_TRIGGER,
                allowed_timeframes=("5m", "15m", "1h"),
                score_contribution=ScoreContributionLevel.HIGH,
                hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
                hard_gate_description="HTF-aligned eligible",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.STRUCTURAL_LEVELS,
                feature_family=DeterministicFeatureFamily.SUPPORT_RESISTANCE,
                role=CapabilityRole.PRIMARY,
                allowed_timeframes=CANONICAL_DEFAULT_TIMEFRAMES,
                score_contribution=ScoreContributionLevel.HIGH,
                hard_gate_eligibility=HardGateEligibility.CONDITIONAL,
                hard_gate_description="invalidation / TP eligible",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.FIBONACCI,
                feature_family=DeterministicFeatureFamily.FIBONACCI,
                role=CapabilityRole.ADVISORY,
                allowed_timeframes=("4h", "1d"),
                score_contribution=ScoreContributionLevel.MEDIUM,
                hard_gate_eligibility=HardGateEligibility.FALSE,
                hard_gate_description="advisory / strategic",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.PATTERN_RECOGNITION,
                feature_family=DeterministicFeatureFamily.PATTERN,
                role=CapabilityRole.DIAGNOSTIC,
                allowed_timeframes=("1h", "4h", "1d"),
                score_contribution=ScoreContributionLevel.MEDIUM,
                hard_gate_eligibility=HardGateEligibility.FALSE,
                hard_gate_description="diagnostic",
            ),
            TechnicalFamilyGovernance(
                family_id=TechnicalFamilyId.MACRO_CYCLE,
                feature_family=DeterministicFeatureFamily.CYCLE,
                role=CapabilityRole.DIAGNOSTIC,
                allowed_timeframes=("4h", "1d"),
                score_contribution=ScoreContributionLevel.MEDIUM,
                hard_gate_eligibility=HardGateEligibility.FALSE,
                hard_gate_description="regime modifier",
            ),
        ),
    )


def build_decision_core_pipeline() -> DecisionCorePipeline:
    return DecisionCorePipeline()


def build_risk_control_set() -> RiskControlSet:
    return RiskControlSet()


def build_trailing_stop_rule_contract() -> TrailingStopRuleContract:
    return TrailingStopRuleContract()


def build_validation_domain_contract() -> ValidationDomainContract:
    return ValidationDomainContract()


def build_controlled_learning_contract() -> ControlledLearningContract:
    return ControlledLearningContract()


def build_governance_primitive_catalog() -> GovernancePrimitiveCatalog:
    return GovernancePrimitiveCatalog()


def build_approved_operating_envelope() -> ApprovedOperatingEnvelope:
    return ApprovedOperatingEnvelope(
        envelope_id="AI4BINANCE-SPOT-PAPER-HOTUSDT-MTF",
        universe_policy_id="policy:universe:binance-spot-default:1",
        risk_policy_id="policy:risk:spot-paper-default:1",
        minimum_data_quality_profile_id="dq:binance-spot-ohlcv-standard:1",
        restrictions=("paper_default", "manual_execution", "no_auto_live"),
    )


def build_safe_state() -> SafeState:
    return SafeState()


def build_master_core_instructions() -> MasterCoreInstructions:
    return MasterCoreInstructions()


def build_core_vnext_identity() -> CoreVNextIdentity:
    return CoreVNextIdentity()


def build_human_decision_output_format() -> HumanDecisionOutputFormat:
    return HumanDecisionOutputFormat()


def build_standard_decision_output_contract() -> StandardDecisionOutputContract:
    return StandardDecisionOutputContract()


def build_canonical_decision_output_contract() -> CanonicalDecisionOutputContract:
    return CanonicalDecisionOutputContract()


def build_canonical_decision_state_machine() -> CanonicalDecisionStateMachine:
    return CanonicalDecisionStateMachine()


def build_continuous_assurance_engine() -> ContinuousAssuranceEngine:
    return ContinuousAssuranceEngine()


def build_append_only_evidence_fabric() -> AppendOnlyEvidenceFabric:
    return AppendOnlyEvidenceFabric()


def build_audit_observability_catalog() -> AuditObservabilityCatalog:
    return AuditObservabilityCatalog()


def build_decision_lineage(lineage_id: str, cycle_id: str) -> DecisionLineage:
    return DecisionLineage(
        lineage_id=lineage_id,
        cycle_id=cycle_id,
        step_refs=tuple(
            (step, f"{cycle_id}:{step.value}") for step in DecisionLineageStep
        ),
    )


def build_security_domain_contract() -> SecurityDomainContract:
    return SecurityDomainContract()


def build_event_fabric_contract() -> EventFabricContract:
    return EventFabricContract()


def build_research_capability_domain_contract() -> ResearchCapabilityDomainContract:
    return ResearchCapabilityDomainContract()


def action_ceiling_for_maturity(maturity: GovernanceMaturity) -> ActionCeiling:
    if maturity in {
        GovernanceMaturity.RESEARCH_ONLY,
        GovernanceMaturity.STAGED_CANDIDATE,
        GovernanceMaturity.BACKTESTED,
        GovernanceMaturity.WF_VALIDATED,
        GovernanceMaturity.OOS_VALIDATED,
    }:
        return ActionCeiling.RESEARCH
    if maturity is GovernanceMaturity.PAPER_APPROVED:
        return ActionCeiling.PAPER
    if maturity is GovernanceMaturity.LIVE_ELIGIBLE:
        return ActionCeiling.MANUAL_REVIEW
    return ActionCeiling.NONE


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_utc_timestamp(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must use UTC timezone")


def _require_payload_hash(value: str) -> None:
    _require_non_empty("payload_hash", value)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("payload_hash must be a lowercase sha256 hex digest")


def _require_unit_interval(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain empty values")


def _present_as_pass(value: str) -> ValidationEvidenceStatus:
    if value.strip():
        return ValidationEvidenceStatus.PASS
    return ValidationEvidenceStatus.MISSING


def _aggregate_regime_status(
    validation: CapabilityValidationContract,
) -> ValidationEvidenceStatus:
    statuses = tuple(status for _regime, status in validation.regime_status)
    if not statuses:
        return ValidationEvidenceStatus.MISSING
    if all(status is ValidationEvidenceStatus.PASS for status in statuses):
        return ValidationEvidenceStatus.PASS
    if any(status is ValidationEvidenceStatus.FAIL for status in statuses):
        return ValidationEvidenceStatus.FAIL
    if any(status is ValidationEvidenceStatus.PARTIAL for status in statuses):
        return ValidationEvidenceStatus.PARTIAL
    if any(status is ValidationEvidenceStatus.MISSING for status in statuses):
        return ValidationEvidenceStatus.MISSING
    return ValidationEvidenceStatus.UNKNOWN


AI4BINANCE_CORE_META = build_core_meta()
AI4BINANCE_EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC = (
    build_external_intelligence_evidence_fabric()
)
AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT = build_web_intelligence_radar_contract()
AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT = build_loops_self_improvement_contract()
AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL = build_digital_company_operating_model()
AI4BINANCE_DETERMINISTIC_ANALYTICS_CATALOG = build_deterministic_analytics_catalog()
AI4BINANCE_CAPABILITY_GAP_REGISTRY = build_capability_gap_registry()
AI4BINANCE_DECISION_CORE_PIPELINE = build_decision_core_pipeline()
AI4BINANCE_RISK_CONTROL_SET = build_risk_control_set()
AI4BINANCE_TRAILING_STOP_RULE = build_trailing_stop_rule_contract()
AI4BINANCE_VALIDATION_DOMAIN = build_validation_domain_contract()
AI4BINANCE_CONTROLLED_LEARNING = build_controlled_learning_contract()
AI4BINANCE_GOVERNANCE_PRIMITIVES = build_governance_primitive_catalog()
AI4BINANCE_APPROVED_OPERATING_ENVELOPE = build_approved_operating_envelope()
AI4BINANCE_SAFE_STATE = build_safe_state()
AI4BINANCE_MASTER_CORE_INSTRUCTIONS = build_master_core_instructions()
AI4BINANCE_CORE_VNEXT_IDENTITY = build_core_vnext_identity()
AI4BINANCE_GOVERNED_CAPABILITY_PLATFORM_FLOW = build_governed_capability_platform_flow()
AI4BINANCE_HUMAN_DECISION_OUTPUT_FORMAT = build_human_decision_output_format()
AI4BINANCE_STANDARD_DECISION_OUTPUT = build_standard_decision_output_contract()
AI4BINANCE_CANONICAL_DECISION_OUTPUT = build_canonical_decision_output_contract()
AI4BINANCE_DECISION_STATE_MACHINE = build_canonical_decision_state_machine()
AI4BINANCE_CONTINUOUS_ASSURANCE_ENGINE = build_continuous_assurance_engine()
AI4BINANCE_APPEND_ONLY_EVIDENCE_FABRIC = build_append_only_evidence_fabric()
AI4BINANCE_AUDIT_OBSERVABILITY_CATALOG = build_audit_observability_catalog()
AI4BINANCE_SECURITY_CONTRACT = build_security_domain_contract()
AI4BINANCE_EVENT_FABRIC_CONTRACT = build_event_fabric_contract()
AI4BINANCE_RESEARCH_CAPABILITY_CONTRACT = build_research_capability_domain_contract()
AI4BINANCE_CORE_CONSTITUTION = build_core_constitution()
AI4BINANCE_CORE_ARCHITECTURE = build_core_architecture()
AI4BINANCE_CANONICAL_ENTITY_ONTOLOGY = build_canonical_entity_ontology()
AI4BINANCE_ENTITY_RULE_CATALOG = build_entity_rule_catalog()
AI4BINANCE_RELATIONSHIP_RULE_CATALOG = build_relationship_rule_catalog()
AI4BINANCE_EXTERNAL_STANDARDS_MAPPING = build_external_standards_mapping_contract()

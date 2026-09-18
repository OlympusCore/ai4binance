"""Enterprise auto-audit trigger routing and continuous improvement planning.

Runtime conformance is governed by the EAACIE and Audit Trigger Engine
instructions under ``docs/workflows``. The engine is report-only: it can start
audit routes, blockers, and corrective-action refs, but it cannot authorize
trading, promotion, or live execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    canonical_trace_journal_path,
    canonical_trace_sha256,
)
from ai4binance.ops.decision_telemetry import (
    AcceptanceGateStatus,
    BlockerOutcome,
    EvidenceQuality,
    PerformanceEvidenceSnapshot,
)
from ai4binance.trust.plane import build_conditional_trust_plane_assessment


class AuditTriggerType(StrEnum):
    SCHEDULED_AUDIT = "SCHEDULED_AUDIT"
    MANUAL_AUDIT = "MANUAL_AUDIT"
    CODE_CHANGE = "CODE_CHANGE"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    INSTRUCTION_CHANGE = "INSTRUCTION_CHANGE"
    STATE_TRANSITION = "STATE_TRANSITION"
    DECISION_AUDIT = "DECISION_AUDIT"
    DATA_QUALITY = "DATA_QUALITY"
    PARAMETER_PROMOTION = "PARAMETER_PROMOTION"
    PERFORMANCE_DRIFT = "PERFORMANCE_DRIFT"
    MARKET_REGIME_CHANGE = "MARKET_REGIME_CHANGE"
    NEWS_SECURITY_EVENT = "NEWS_SECURITY_EVENT"
    EXECUTION_AUDIT = "EXECUTION_AUDIT"
    STOP_LOSS_AUDIT = "STOP_LOSS_AUDIT"
    TRAILING_STOP_AUDIT = "TRAILING_STOP_AUDIT"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    AUTO_LEARN_OUTCOME = "AUTO_LEARN_OUTCOME"
    PRIVACY_OR_LEAKAGE = "PRIVACY_OR_LEAKAGE"
    SYSTEM_BLOCKER = "SYSTEM_BLOCKER"
    DEPENDENCY_CHANGE = "DEPENDENCY_CHANGE"
    CREDENTIAL_SECRET_EVENT = "CREDENTIAL_SECRET_EVENT"  # noqa: S105  # nosec B105
    GIT_CLOUD_EVENT = "GIT_CLOUD_EVENT"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    SCHEDULED_DAILY_QUICK = "SCHEDULED_DAILY_QUICK"
    SCHEDULED_WEEKLY_DEEP = "SCHEDULED_WEEKLY_DEEP"


class HybridTriggerClass(StrEnum):
    EVENT = "EVENT"
    CHANGE = "CHANGE"
    DRIFT = "DRIFT"
    SCHEDULE = "SCHEDULE"
    RISK = "RISK"
    EVIDENCE = "EVIDENCE"
    MANUAL = "MANUAL"


class AuditTriggerMode(StrEnum):
    EVENT_DRIVEN = "EVENT_DRIVEN"
    RISK_DRIVEN = "RISK_DRIVEN"
    SCHEDULED = "SCHEDULED"
    ANOMALY_DRIVEN = "ANOMALY_DRIVEN"
    LIFECYCLE_DRIVEN = "LIFECYCLE_DRIVEN"


class AuditObservedEntity(StrEnum):
    STATE = "STATE"
    DECISION = "DECISION"
    DATA = "DATA"
    CONFIGURATION = "CONFIGURATION"
    MODEL = "MODEL"
    OPERATION = "OPERATION"
    SYSTEM_BEHAVIOR = "SYSTEM_BEHAVIOR"


class AuditTriggerSeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class AuditDomain(StrEnum):
    AGENT_ASSURANCE = "AGENT_ASSURANCE"
    INSTRUCTION_GOVERNANCE = "INSTRUCTION_GOVERNANCE"
    CODE_QUALITY = "CODE_QUALITY"
    ARCHITECTURE_INTELLIGENCE = "ARCHITECTURE_INTELLIGENCE"
    WORKFLOW_ASSURANCE = "WORKFLOW_ASSURANCE"
    GAP_ANALYSIS = "GAP_ANALYSIS"
    LEAN_KAIZEN = "LEAN_KAIZEN"
    DATA_GOVERNANCE = "DATA_GOVERNANCE"
    PRIVACY_KVKK = "PRIVACY_KVKK"
    CYBERSECURITY = "CYBERSECURITY"
    TRADING_ASSURANCE = "TRADING_ASSURANCE"
    BACKTEST_QA = "BACKTEST_QA"
    PARAMETER_GOVERNANCE = "PARAMETER_GOVERNANCE"
    AUTO_LEARN_GOVERNANCE = "AUTO_LEARN_GOVERNANCE"
    PERFORMANCE_ENGINEERING = "PERFORMANCE_ENGINEERING"
    COST_OPTIMIZATION = "COST_OPTIMIZATION"
    DGE_ASSURANCE = "DGE_ASSURANCE"


class SecurityDomain(StrEnum):
    """Bounded EAACIE security domains; standards remain catalog mappings."""

    PRIVACY = "PRIVACY"
    ACCESS = "ACCESS"
    SECRETS = "SECRETS"
    APPSEC = "APPSEC"
    VULNERABILITY = "VULNERABILITY"
    DLP = "DLP"
    AUDIT = "AUDIT"
    RECOVERY = "RECOVERY"


class SecurityAuditTriggerType(StrEnum):
    """Security-only trigger vocabulary governed by AuditTriggerEngine."""

    CODE_CHANGE = "CODE_CHANGE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    DEPENDENCY_CHANGE = "DEPENDENCY_CHANGE"
    CREDENTIAL_SECRET_EVENT = "CREDENTIAL_SECRET_EVENT"  # noqa: S105  # nosec B105
    GIT_CLOUD_EVENT = "GIT_CLOUD_EVENT"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    SCHEDULED_DAILY_QUICK = "SCHEDULED_DAILY_QUICK"
    SCHEDULED_WEEKLY_DEEP = "SCHEDULED_WEEKLY_DEEP"


class TrustAssuranceResult(StrEnum):
    PASSED = "PASSED"
    WARN = "WARN"
    BLOCKED = "BLOCKED"


class UncertaintyLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AuditStormStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    MERGED_SAME_ROOT_CAUSE = "MERGED_SAME_ROOT_CAUSE"
    SUPPRESSED_COOLDOWN = "SUPPRESSED_COOLDOWN"
    BLOCKED_RECURSION_DEPTH = "BLOCKED_RECURSION_DEPTH"


class AuditWorkflowPattern(StrEnum):
    ROUTING = "ROUTING"
    EVALUATOR_OPTIMIZER = "EVALUATOR_OPTIMIZER"
    HUMAN_IN_THE_LOOP = "HUMAN_IN_THE_LOOP"


_HIGH_RISK_DOMAINS = frozenset(
    {
        AuditDomain.PRIVACY_KVKK,
        AuditDomain.CYBERSECURITY,
        AuditDomain.TRADING_ASSURANCE,
        AuditDomain.PARAMETER_GOVERNANCE,
        AuditDomain.AUTO_LEARN_GOVERNANCE,
        AuditDomain.DGE_ASSURANCE,
    }
)


EAACIE_INSTRUCTION_REF = (
    "docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md"
)
AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF = (
    "docs/workflows/instruction_audit_trigger_engine.md"
)
EAACIE_INSTRUCTION_REFS = (
    EAACIE_INSTRUCTION_REF,
    AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
)


@dataclass(frozen=True, slots=True)
class SecurityAuditControlProfile:
    """Small default-on control profile from the EAACIE security instruction."""

    privacy: bool = True
    access_control: bool = True
    secrets_scan: bool = True
    dependency_scan: bool = True
    dlp_scan: bool = True
    audit_integrity: bool = True
    backup_health: bool = True
    incident_detection: bool = True

    def to_payload(self) -> dict[str, bool]:
        return {
            "privacy": self.privacy,
            "access_control": self.access_control,
            "secrets_scan": self.secrets_scan,
            "dependency_scan": self.dependency_scan,
            "dlp_scan": self.dlp_scan,
            "audit_integrity": self.audit_integrity,
            "backup_health": self.backup_health,
            "incident_detection": self.incident_detection,
        }


SECURITY_AUDIT_CONTROL_PROFILE = SecurityAuditControlProfile()


@dataclass(frozen=True, slots=True)
class PolicyEvaluationRecord:
    """One deterministic policy-as-code evaluation inside TIAF-lite."""

    evaluation_id: str
    policy_id: str
    policy_version: str
    result: TrustAssuranceResult
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    action_refs: tuple[str, ...] = ()
    review_required: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.evaluation_id.strip():
            raise ValueError("policy evaluation id is required")
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("policy evaluation policy identity is required")
        if not self.evidence_refs:
            raise ValueError("policy evaluation requires evidence")
        _require_unique("policy evaluation evidence refs", self.evidence_refs)
        _require_unique("policy evaluation blockers", self.blockers)
        _require_unique("policy evaluation action refs", self.action_refs)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("policy evaluations cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "evaluation_id": self.evaluation_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "result": self.result.value,
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "action_refs": list(self.action_refs),
            "review_required": self.review_required,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class UncertaintyAssessmentRecord:
    """Bounded abstention record; uncertainty never opens execution."""

    assessment_id: str
    level: UncertaintyLevel
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    abstention_required: bool = True
    abstention_reason: str = "ASSURANCE_REPORT_ONLY"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.assessment_id.strip():
            raise ValueError("uncertainty assessment id is required")
        if not self.reasons:
            raise ValueError("uncertainty assessment requires reasons")
        _require_unique("uncertainty assessment reasons", self.reasons)
        if not self.evidence_refs:
            raise ValueError("uncertainty assessment requires evidence")
        _require_unique("uncertainty assessment evidence refs", self.evidence_refs)
        if not self.abstention_required:
            raise ValueError("uncertainty assessment must preserve abstention")
        if not self.abstention_reason.strip():
            raise ValueError("uncertainty assessment abstention reason is required")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("uncertainty assessments cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "level": self.level.value,
            "reasons": list(self.reasons),
            "evidence_refs": list(self.evidence_refs),
            "abstention_required": self.abstention_required,
            "abstention_reason": self.abstention_reason,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class SemanticContractRecord:
    """Local semantic contract for audit artifacts and decision evidence."""

    contract_id: str
    subject: str
    required_fields: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    authority_boundary: str = "REPORT_ONLY"
    privacy_class: str = "LOCAL_ONLY"
    freshness_sla: str = "EVENT_TIME_AWARE"
    validation_status: TrustAssuranceResult = TrustAssuranceResult.PASSED

    def __post_init__(self) -> None:
        if not self.contract_id.strip() or not self.subject.strip():
            raise ValueError("semantic contract identity is required")
        if not self.required_fields:
            raise ValueError("semantic contract requires fields")
        _require_unique("semantic contract required fields", self.required_fields)
        _require_unique("semantic contract forbidden fields", self.forbidden_fields)
        if not self.authority_boundary.strip():
            raise ValueError("semantic contract authority boundary is required")
        if self.authority_boundary != "REPORT_ONLY":
            raise ValueError("semantic contracts cannot widen audit authority")

    def to_payload(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "subject": self.subject,
            "required_fields": list(self.required_fields),
            "forbidden_fields": list(self.forbidden_fields),
            "authority_boundary": self.authority_boundary,
            "privacy_class": self.privacy_class,
            "freshness_sla": self.freshness_sla,
            "validation_status": self.validation_status.value,
        }


@dataclass(frozen=True, slots=True)
class EvidenceGraphNode:
    node_id: str
    node_type: str
    ref: str

    def __post_init__(self) -> None:
        if (
            not self.node_id.strip()
            or not self.node_type.strip()
            or not self.ref.strip()
        ):
            raise ValueError("evidence graph node fields are required")

    def to_payload(self) -> dict[str, str]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "ref": self.ref,
        }


@dataclass(frozen=True, slots=True)
class EvidenceGraphEdge:
    source: str
    relation: str
    target: str

    def __post_init__(self) -> None:
        if (
            not self.source.strip()
            or not self.relation.strip()
            or not self.target.strip()
        ):
            raise ValueError("evidence graph edge fields are required")

    def to_payload(self) -> dict[str, str]:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class EvidenceGraphLiteRecord:
    """Small local evidence graph; no vector DB or external service required."""

    graph_id: str
    nodes: tuple[EvidenceGraphNode, ...]
    edges: tuple[EvidenceGraphEdge, ...]

    def __post_init__(self) -> None:
        if not self.graph_id.strip():
            raise ValueError("evidence graph id is required")
        if not self.nodes:
            raise ValueError("evidence graph requires nodes")
        node_ids = tuple(node.node_id for node in self.nodes)
        _require_unique("evidence graph nodes", node_ids)
        node_id_set = set(node_ids)
        edge_ids = tuple(
            f"{edge.source}:{edge.relation}:{edge.target}" for edge in self.edges
        )
        _require_unique("evidence graph edges", edge_ids)
        for edge in self.edges:
            if edge.source not in node_id_set or edge.target not in node_id_set:
                raise ValueError("evidence graph edge references unknown node")

    def to_payload(self) -> dict[str, object]:
        return {
            "graph_id": self.graph_id,
            "nodes": [node.to_payload() for node in self.nodes],
            "edges": [edge.to_payload() for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class DecisionProvenanceRecord:
    """Decision provenance ledger entry for EAACIE assurance plans."""

    decision_id: str
    decision_kind: str
    observed_at: datetime
    final_action: str
    evidence_refs: tuple[str, ...]
    policy_evaluation_refs: tuple[str, ...]
    uncertainty_ref: str
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.decision_kind.strip():
            raise ValueError("decision provenance identity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("decision provenance timestamp must be timezone-aware")
        if not self.final_action.strip():
            raise ValueError("decision provenance final action is required")
        if not self.evidence_refs:
            raise ValueError("decision provenance requires evidence")
        _require_unique("decision provenance evidence refs", self.evidence_refs)
        if not self.policy_evaluation_refs:
            raise ValueError("decision provenance requires policy evaluations")
        _require_unique(
            "decision provenance policy evaluation refs",
            self.policy_evaluation_refs,
        )
        if not self.uncertainty_ref.strip():
            raise ValueError("decision provenance uncertainty ref is required")
        _require_unique("decision provenance blockers", self.blockers)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("decision provenance cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "decision_id": self.decision_id,
            "decision_kind": self.decision_kind,
            "observed_at": self.observed_at.isoformat(),
            "final_action": self.final_action,
            "evidence_refs": list(self.evidence_refs),
            "policy_evaluation_refs": list(self.policy_evaluation_refs),
            "uncertainty_ref": self.uncertainty_ref,
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        payload["provenance_hash"] = _stable_digest(payload)
        return payload


@dataclass(frozen=True, slots=True)
class TrustAssuranceBundle:
    """TIAF-lite packet attached to every EAACIE plan."""

    bundle_id: str
    provenance: DecisionProvenanceRecord
    policy_evaluations: tuple[PolicyEvaluationRecord, ...]
    uncertainty: UncertaintyAssessmentRecord
    semantic_contracts: tuple[SemanticContractRecord, ...]
    evidence_graph: EvidenceGraphLiteRecord
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.bundle_id.strip():
            raise ValueError("trust assurance bundle id is required")
        if not self.policy_evaluations:
            raise ValueError("trust assurance bundle requires policy evaluations")
        _require_unique(
            "trust assurance policy evaluations",
            tuple(evaluation.evaluation_id for evaluation in self.policy_evaluations),
        )
        if not self.semantic_contracts:
            raise ValueError("trust assurance bundle requires semantic contracts")
        _require_unique(
            "trust assurance semantic contracts",
            tuple(contract.contract_id for contract in self.semantic_contracts),
        )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("trust assurance cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "bundle_id": self.bundle_id,
            "framework": "AI4BINANCE_TIAF_LITE",
            "instruction_refs": list(EAACIE_INSTRUCTION_REFS),
            "governance_plane": build_conditional_trust_plane_assessment(
                evidence_refs=(
                    self.bundle_id,
                    self.provenance.decision_id,
                    *self.provenance.evidence_refs,
                )
            ).to_payload(),
            "provenance": self.provenance.to_payload(),
            "policy_evaluations": [
                evaluation.to_payload() for evaluation in self.policy_evaluations
            ],
            "uncertainty": self.uncertainty.to_payload(),
            "semantic_contracts": [
                contract.to_payload() for contract in self.semantic_contracts
            ],
            "evidence_graph": self.evidence_graph.to_payload(),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        payload["bundle_hash"] = _stable_digest(payload)
        return payload


@dataclass(frozen=True, slots=True)
class AuditStormPolicy:
    cooldown_seconds: int = 900
    correlation_window_seconds: int = 300
    max_parallel_audits: int = 4
    max_recursion_depth: int = 3
    same_root_cause_merge: bool = True
    dedup: bool = True

    def __post_init__(self) -> None:
        if self.cooldown_seconds < 0:
            raise ValueError("audit storm cooldown must be non-negative")
        if self.correlation_window_seconds < 1:
            raise ValueError("audit storm correlation window must be positive")
        if self.max_parallel_audits < 1:
            raise ValueError("audit storm parallel limit must be positive")
        if self.max_recursion_depth < 0:
            raise ValueError("audit storm recursion depth cannot be negative")


@dataclass(frozen=True, slots=True)
class AuditStateComparison:
    field: str
    expected: str = ""
    observed: str = ""
    allowed_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("audit state comparison field is required")
        if self.allowed_values:
            _require_unique(
                "audit state comparison allowed values",
                self.allowed_values,
            )
        if any(not value.strip() for value in self.allowed_values):
            raise ValueError("audit state comparison allowed values cannot be blank")

    @property
    def deviates(self) -> bool:
        if self.allowed_values:
            return self.observed not in self.allowed_values
        return self.expected != self.observed

    def to_payload(self) -> dict[str, object]:
        return {
            "field": self.field,
            "expected": self.expected,
            "observed": self.observed,
            "allowed_values": list(self.allowed_values),
            "deviates": self.deviates,
        }


@dataclass(frozen=True, slots=True)
class AuditTriggerSignal:
    signal_id: str
    entity_kind: AuditObservedEntity
    entity_id: str
    observed_at: datetime
    trigger_modes: tuple[AuditTriggerMode, ...]
    comparisons: tuple[AuditStateComparison, ...]
    evidence_refs: tuple[str, ...]
    severity: AuditTriggerSeverity = AuditTriggerSeverity.P3
    confidence: float = 1.0
    risk_score: int = 0
    source_event_id: str = ""
    root_cause_key: str = ""
    recursion_depth: int = 0
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("audit trigger signal id is required")
        if not self.entity_id.strip():
            raise ValueError("audit trigger signal entity id is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("audit trigger signal timestamp must be timezone-aware")
        if not self.trigger_modes:
            raise ValueError("audit trigger signal requires trigger modes")
        _require_unique(
            "audit trigger signal modes",
            tuple(trigger_mode.value for trigger_mode in self.trigger_modes),
        )
        _require_unique(
            "audit trigger signal comparison fields",
            tuple(comparison.field for comparison in self.comparisons),
        )
        if not self.evidence_refs:
            raise ValueError("audit trigger signal requires evidence")
        _require_unique("audit trigger signal evidence refs", self.evidence_refs)
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("audit trigger signal evidence refs cannot be blank")
        if not 0 <= self.confidence <= 1:
            raise ValueError("audit trigger signal confidence must be between 0 and 1")
        if not 0 <= self.risk_score <= 100:
            raise ValueError(
                "audit trigger signal risk score must be between 0 and 100"
            )
        if self.recursion_depth < 0:
            raise ValueError("audit trigger signal recursion depth cannot be negative")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("audit trigger signals cannot authorize trading")

    @property
    def deviation_fields(self) -> tuple[str, ...]:
        return tuple(
            comparison.field for comparison in self.comparisons if comparison.deviates
        )

    @property
    def audit_required(self) -> bool:
        if AuditTriggerMode.SCHEDULED in self.trigger_modes:
            return True
        if self.deviation_fields:
            return True
        if self.severity in {AuditTriggerSeverity.P0, AuditTriggerSeverity.P1}:
            return True
        return self.risk_score >= 70

    def to_payload(self) -> dict[str, object]:
        return {
            "instruction_ref": AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
            "instruction_refs": list(EAACIE_INSTRUCTION_REFS),
            "signal_id": self.signal_id,
            "entity_kind": self.entity_kind.value,
            "entity_id": self.entity_id,
            "observed_at": self.observed_at.isoformat(),
            "trigger_modes": [
                trigger_mode.value for trigger_mode in self.trigger_modes
            ],
            "comparisons": [comparison.to_payload() for comparison in self.comparisons],
            "deviation_fields": list(self.deviation_fields),
            "audit_required": self.audit_required,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "source_event_id": self.source_event_id,
            "evidence_refs": list(self.evidence_refs),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class CentralAuditTriggerEngine:
    policy: AuditStormPolicy = field(default_factory=AuditStormPolicy)

    def events_from_signals(
        self,
        signals: tuple[AuditTriggerSignal, ...],
    ) -> tuple[ContinuousAuditEvent, ...]:
        events = []
        for signal in signals:
            if signal.audit_required:
                events.append(_event_from_signal(signal))
        return tuple(events)

    def build_plan(
        self,
        signals: tuple[AuditTriggerSignal, ...],
    ) -> ContinuousAssurancePlan:
        events = self.events_from_signals(signals)
        if not events:
            raise ValueError("no audit-triggering deviations detected")
        return build_continuous_assurance_plan(events, policy=self.policy)

    def security_event(
        self,
        trigger_type: SecurityAuditTriggerType,
        *,
        observed_at: datetime,
        evidence_refs: tuple[str, ...],
        entity_id: str = "AI4BINANCE",
        root_cause_key: str = "",
        recursion_depth: int = 0,
    ) -> ContinuousAuditEvent:
        """Normalize one security trigger without adding remediation authority."""

        return security_audit_event(
            trigger_type,
            observed_at=observed_at,
            evidence_refs=evidence_refs,
            entity_id=entity_id,
            root_cause_key=root_cause_key,
            recursion_depth=recursion_depth,
        )

    def build_security_plan(
        self,
        events: tuple[ContinuousAuditEvent, ...],
    ) -> ContinuousAssurancePlan:
        if not events or any(event.security_trigger_type is None for event in events):
            raise ValueError("security audit plan requires security trigger events")
        return build_continuous_assurance_plan(events, policy=self.policy)


@dataclass(frozen=True, slots=True)
class ContinuousAuditEvent:
    event_id: str
    trigger_type: AuditTriggerType
    entity_type: str
    entity_id: str
    observed_at: datetime
    evidence_refs: tuple[str, ...]
    trigger_modes: tuple[AuditTriggerMode, ...] = ()
    security_trigger_type: SecurityAuditTriggerType | None = None
    security_domains: tuple[SecurityDomain, ...] = ()
    root_cause_key: str = ""
    recursion_depth: int = 0
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("audit event id is required")
        if not self.entity_type.strip() or not self.entity_id.strip():
            raise ValueError("audit event entity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("audit event timestamp must be timezone-aware")
        if not self.evidence_refs:
            raise ValueError("audit event requires evidence")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("audit event evidence refs must be unique")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("audit event evidence refs cannot be blank")
        _require_unique(
            "audit event trigger modes",
            tuple(trigger_mode.value for trigger_mode in self.trigger_modes),
        )
        _validate_security_routing(
            "audit event",
            self.security_trigger_type,
            self.security_domains,
        )
        if self.recursion_depth < 0:
            raise ValueError("audit event recursion depth cannot be negative")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("audit events cannot authorize trading")

    @property
    def dedup_key(self) -> str:
        root = self.root_cause_key.strip() or self.event_id
        return (
            f"{self.trigger_type.value}:{self.entity_type.strip()}:"
            f"{self.entity_id.strip()}:{root}"
        )


@dataclass(frozen=True, slots=True)
class AuditRouteDecision:
    event_id: str
    trigger_type: AuditTriggerType
    hybrid_trigger_classes: tuple[HybridTriggerClass, ...]
    storm_status: AuditStormStatus
    domains: tuple[AuditDomain, ...]
    workflow_patterns: tuple[AuditWorkflowPattern, ...]
    scope_refs: tuple[str, ...]
    review_required: bool
    blockers: tuple[str, ...]
    action_refs: tuple[str, ...]
    trigger_modes: tuple[AuditTriggerMode, ...] = ()
    security_trigger_type: SecurityAuditTriggerType | None = None
    security_domains: tuple[SecurityDomain, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("audit route event id is required")
        _require_unique(
            "audit route hybrid trigger classes",
            tuple(trigger_class.value for trigger_class in self.hybrid_trigger_classes),
        )
        _require_unique(
            "audit route trigger modes",
            tuple(trigger_mode.value for trigger_mode in self.trigger_modes),
        )
        _validate_security_routing(
            "audit route",
            self.security_trigger_type,
            self.security_domains,
        )
        _require_unique(
            "audit route domains",
            tuple(domain.value for domain in self.domains),
        )
        _require_unique(
            "audit route workflow patterns",
            tuple(pattern.value for pattern in self.workflow_patterns),
        )
        _require_unique("audit route scope refs", self.scope_refs)
        _require_unique("audit route blockers", self.blockers)
        _require_unique("audit route action refs", self.action_refs)
        if not self.domains:
            raise ValueError("audit route requires at least one domain")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("audit route cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "instruction_ref": AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
            "instruction_refs": list(EAACIE_INSTRUCTION_REFS),
            "event_id": self.event_id,
            "trigger_type": self.trigger_type.value,
            "hybrid_trigger_classes": [
                trigger_class.value for trigger_class in self.hybrid_trigger_classes
            ],
            "trigger_modes": [
                trigger_mode.value for trigger_mode in self.trigger_modes
            ],
            "security_trigger_type": (
                self.security_trigger_type.value
                if self.security_trigger_type is not None
                else None
            ),
            "security_domains": [domain.value for domain in self.security_domains],
            "storm_status": self.storm_status.value,
            "domains": [domain.value for domain in self.domains],
            "workflow_patterns": [pattern.value for pattern in self.workflow_patterns],
            "scope_refs": list(self.scope_refs),
            "review_required": self.review_required,
            "blockers": list(self.blockers),
            "action_refs": list(self.action_refs),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class ContinuousAssurancePlan:
    plan_id: str
    observed_at: datetime
    workflow_pattern: str
    route_decisions: tuple[AuditRouteDecision, ...]
    accepted_count: int
    suppressed_count: int
    blockers: tuple[str, ...]
    repository_root: Path = field(default_factory=Path)
    trace_journal: CanonicalTraceJournal | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("continuous assurance plan id is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("continuous assurance timestamp must be timezone-aware")
        if not self.route_decisions:
            raise ValueError("continuous assurance plan requires route decisions")
        if self.accepted_count < 0 or self.suppressed_count < 0:
            raise ValueError("continuous assurance counts cannot be negative")
        _require_unique("continuous assurance blockers", self.blockers)
        repository_root = self.repository_root.resolve()
        object.__setattr__(self, "repository_root", repository_root)
        if self.trace_journal is None:
            object.__setattr__(
                self,
                "trace_journal",
                CanonicalTraceJournal(canonical_trace_journal_path(repository_root)),
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("continuous assurance cannot authorize trading")

    @property
    def status(self) -> str:
        return "RUNNING_WITH_BLOCKERS" if self.blockers else "READY"

    @property
    def hybrid_trigger_classes(self) -> tuple[HybridTriggerClass, ...]:
        return tuple(
            dict.fromkeys(
                trigger_class
                for decision in self.route_decisions
                for trigger_class in decision.hybrid_trigger_classes
            )
        )

    @property
    def hybrid_class_counts(self) -> dict[str, int]:
        counts = {trigger_class.value: 0 for trigger_class in HybridTriggerClass}
        for decision in self.route_decisions:
            for trigger_class in decision.hybrid_trigger_classes:
                counts[trigger_class.value] += 1
        return counts

    @property
    def trigger_modes(self) -> tuple[AuditTriggerMode, ...]:
        return tuple(
            dict.fromkeys(
                trigger_mode
                for decision in self.route_decisions
                for trigger_mode in decision.trigger_modes
            )
        )

    @property
    def trigger_mode_counts(self) -> dict[str, int]:
        counts = {trigger_mode.value: 0 for trigger_mode in AuditTriggerMode}
        for decision in self.route_decisions:
            for trigger_mode in decision.trigger_modes:
                counts[trigger_mode.value] += 1
        return counts

    @property
    def security_domains(self) -> tuple[SecurityDomain, ...]:
        return tuple(
            dict.fromkeys(
                domain
                for decision in self.route_decisions
                for domain in decision.security_domains
            )
        )

    @property
    def security_trigger_types(self) -> tuple[SecurityAuditTriggerType, ...]:
        return tuple(
            dict.fromkeys(
                decision.security_trigger_type
                for decision in self.route_decisions
                if decision.security_trigger_type is not None
            )
        )

    @property
    def security_audit_payload(self) -> dict[str, object]:
        return {
            "enabled": bool(self.security_trigger_types),
            "controls": SECURITY_AUDIT_CONTROL_PROFILE.to_payload(),
            "domains": [domain.value for domain in self.security_domains],
            "trigger_types": [
                trigger_type.value for trigger_type in self.security_trigger_types
            ],
            "review_required": any(
                decision.review_required
                for decision in self.route_decisions
                if decision.security_trigger_type is not None
            ),
            "automatic_remediation": False,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }

    @property
    def trust_assurance_bundle(self) -> TrustAssuranceBundle:
        if self.trace_journal is None:
            raise ValueError(
                "continuous assurance plan requires canonical trace journal"
            )
        return build_trust_assurance_bundle(self, trace_journal=self.trace_journal)

    @property
    def trust_assurance_payload(self) -> dict[str, object]:
        return self.trust_assurance_bundle.to_payload()

    def to_payload(self) -> dict[str, object]:
        return {
            "instruction_ref": AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
            "instruction_refs": list(EAACIE_INSTRUCTION_REFS),
            "plan_id": self.plan_id,
            "observed_at": self.observed_at.isoformat(),
            "status": self.status,
            "workflow_pattern": self.workflow_pattern,
            "hybrid_trigger_classes": [
                trigger_class.value for trigger_class in self.hybrid_trigger_classes
            ],
            "hybrid_class_counts": self.hybrid_class_counts,
            "trigger_modes": [
                trigger_mode.value for trigger_mode in self.trigger_modes
            ],
            "trigger_mode_counts": self.trigger_mode_counts,
            "security_audit": self.security_audit_payload,
            "trust_assurance": self.trust_assurance_payload,
            "accepted_count": self.accepted_count,
            "suppressed_count": self.suppressed_count,
            "blockers": list(self.blockers),
            "route_decisions": [
                decision.to_payload() for decision in self.route_decisions
            ],
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_continuous_assurance_plan(
    events: tuple[ContinuousAuditEvent, ...],
    *,
    policy: AuditStormPolicy | None = None,
    repository_root: Path | None = None,
) -> ContinuousAssurancePlan:
    """Route audit events into bounded report-only assurance loops."""
    if not events:
        raise ValueError("continuous assurance plan requires events")
    active_policy = policy or AuditStormPolicy()
    decisions: list[AuditRouteDecision] = []
    accepted = 0
    suppressed = 0
    recent: dict[str, ContinuousAuditEvent] = {}
    root_causes: set[str] = set()
    for event in sorted(events, key=lambda item: (item.observed_at, item.event_id)):
        storm_status = _storm_status(event, recent, root_causes, active_policy)
        hybrid_classes = _hybrid_classes_for_trigger(event.trigger_type)
        trigger_modes = event.trigger_modes or _trigger_modes_for_trigger(
            event.trigger_type
        )
        domains = _domains_for_trigger(event.trigger_type)
        security_domains = event.security_domains
        patterns = _patterns_for_domains(domains)
        if (
            event.security_trigger_type is not None
            and AuditWorkflowPattern.HUMAN_IN_THE_LOOP not in patterns
        ):
            patterns = (*patterns, AuditWorkflowPattern.HUMAN_IN_THE_LOOP)
        blockers = _blockers_for(event, domains, storm_status)
        decisions.append(
            AuditRouteDecision(
                event_id=event.event_id,
                trigger_type=event.trigger_type,
                hybrid_trigger_classes=hybrid_classes,
                trigger_modes=trigger_modes,
                security_trigger_type=event.security_trigger_type,
                security_domains=security_domains,
                storm_status=storm_status,
                domains=domains,
                workflow_patterns=patterns,
                scope_refs=_scope_refs(event, domains, security_domains),
                review_required=(
                    event.security_trigger_type is not None
                    or any(domain in _HIGH_RISK_DOMAINS for domain in domains)
                ),
                blockers=blockers,
                action_refs=_action_refs(event, domains, storm_status),
            )
        )
        if storm_status is AuditStormStatus.ACCEPTED:
            accepted += 1
            recent[event.dedup_key] = event
            if event.root_cause_key.strip():
                root_causes.add(event.root_cause_key.strip())
        else:
            suppressed += 1
    blockers = tuple(
        dict.fromkeys(blocker for item in decisions for blocker in item.blockers)
    )
    observed_at = max(event.observed_at for event in events)
    return ContinuousAssurancePlan(
        plan_id=f"eaacie:{int(observed_at.timestamp())}",
        observed_at=observed_at,
        workflow_pattern="ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP",
        route_decisions=tuple(decisions),
        accepted_count=accepted,
        suppressed_count=suppressed,
        blockers=blockers,
        repository_root=(repository_root or Path.cwd()).resolve(),
    )


def build_trust_assurance_bundle(
    plan: ContinuousAssurancePlan,
    *,
    trace_journal: CanonicalTraceJournal,
) -> TrustAssuranceBundle:
    """Build the local TIAF-lite packet without touching the trading hot path."""

    evidence_refs = tuple(
        dict.fromkeys(
            ref
            for decision in plan.route_decisions
            for ref in decision.scope_refs
            if not ref.startswith(("entity:", "domain:", "security-domain:"))
        )
    )
    policy_evaluations = tuple(
        PolicyEvaluationRecord(
            evaluation_id=f"policy:{decision.event_id}",
            policy_id=f"eaacie.route.{decision.trigger_type.value.lower()}",
            policy_version="EAACIE-1.3/AuditTriggerEngine-1.3",
            result=(
                TrustAssuranceResult.BLOCKED
                if decision.blockers
                else TrustAssuranceResult.PASSED
            ),
            evidence_refs=tuple(
                dict.fromkeys(
                    ref
                    for ref in decision.scope_refs
                    if not ref.startswith(("entity:", "domain:", "security-domain:"))
                )
            )
            or ("route-decision",),
            blockers=decision.blockers,
            action_refs=decision.action_refs,
            review_required=decision.review_required,
        )
        for decision in plan.route_decisions
    )
    uncertainty = UncertaintyAssessmentRecord(
        assessment_id=f"uncertainty:{plan.plan_id}",
        level=_uncertainty_level(plan.blockers),
        reasons=_uncertainty_reasons(plan),
        evidence_refs=evidence_refs or ("continuous-assurance-plan",),
        abstention_required=True,
        abstention_reason="EAACIE_REPORT_ONLY_LIVE_ORDER_BLOCKED",
    )
    contracts = _semantic_contracts_for_plan(plan)
    provenance = DecisionProvenanceRecord(
        decision_id=f"provenance:{plan.plan_id}",
        decision_kind="CONTINUOUS_ASSURANCE_PLAN",
        observed_at=plan.observed_at,
        final_action="AUDIT_ROUTE_ONLY",
        evidence_refs=evidence_refs or ("continuous-assurance-plan",),
        policy_evaluation_refs=tuple(
            evaluation.evaluation_id for evaluation in policy_evaluations
        ),
        uncertainty_ref=uncertainty.assessment_id,
        blockers=plan.blockers,
    )
    graph = _evidence_graph_for_bundle(
        plan_id=plan.plan_id,
        provenance=provenance,
        policy_evaluations=policy_evaluations,
        uncertainty=uncertainty,
        semantic_contracts=contracts,
    )
    bundle = TrustAssuranceBundle(
        bundle_id=f"tiaf-lite:{plan.plan_id}",
        provenance=provenance,
        policy_evaluations=policy_evaluations,
        uncertainty=uncertainty,
        semantic_contracts=contracts,
        evidence_graph=graph,
    )
    _record_trust_assurance_bundle(bundle, trace_journal)
    return bundle


def _record_trust_assurance_bundle(
    bundle: TrustAssuranceBundle,
    trace_journal: CanonicalTraceJournal,
) -> None:
    for record in _trust_assurance_trace_records(bundle):
        trace_journal.append_if_absent(record)


def _trust_assurance_trace_records(
    bundle: TrustAssuranceBundle,
) -> tuple[CanonicalTraceRecord, ...]:
    records = [
        _policy_evaluation_trace_record(
            evaluation,
            occurred_at=bundle.provenance.observed_at,
        )
        for evaluation in bundle.policy_evaluations
    ]
    records.append(_decision_provenance_trace_record(bundle.provenance))
    return tuple(records)


def _policy_evaluation_trace_record(
    evaluation: PolicyEvaluationRecord,
    *,
    occurred_at: datetime,
) -> CanonicalTraceRecord:
    payload = evaluation.to_payload()
    return CanonicalTraceRecord.create(
        trace_id=f"trace:policy:{evaluation.evaluation_id}",
        trace_kind=ConsequentialTraceKind.POLICY_EVALUATION,
        subject_ref=evaluation.evaluation_id,
        subject_type="POLICY_EVALUATION_RECORD",
        occurred_at=occurred_at,
        event_name="POLICY_EVALUATION_RECORDED",
        event_status=evaluation.result.value,
        evidence_refs=evaluation.evidence_refs,
        blockers=evaluation.blockers,
        related_refs=(
            evaluation.policy_id,
            evaluation.policy_version,
            *evaluation.action_refs,
        ),
        subject_sha256=canonical_trace_sha256(payload),
    )


def _decision_provenance_trace_record(
    provenance: DecisionProvenanceRecord,
) -> CanonicalTraceRecord:
    payload = provenance.to_payload()
    return CanonicalTraceRecord.create(
        trace_id=f"trace:decision:{provenance.decision_id}",
        trace_kind=ConsequentialTraceKind.DECISION,
        subject_ref=provenance.decision_id,
        subject_type="DECISION_PROVENANCE_RECORD",
        occurred_at=provenance.observed_at,
        event_name="DECISION_PROVENANCE_RECORDED",
        event_status=provenance.final_action,
        evidence_refs=provenance.evidence_refs,
        blockers=provenance.blockers,
        related_refs=(
            provenance.uncertainty_ref,
            *provenance.policy_evaluation_refs,
        ),
        subject_sha256=str(payload["provenance_hash"]),
    )


def events_from_auto_audit_cycle(
    *,
    observed_at: datetime,
    system_status: str,
    blockers: tuple[str, ...],
    new_blockers: tuple[str, ...],
    resolved_blockers: tuple[str, ...],
    privacy_leak_status: str,
) -> tuple[ContinuousAuditEvent, ...]:
    """Convert an auto-audit cycle snapshot into trigger-engine events."""
    events = [
        ContinuousAuditEvent(
            event_id=f"eaacie-scheduled:{int(observed_at.timestamp())}",
            trigger_type=AuditTriggerType.SCHEDULED_AUDIT,
            entity_type="SYSTEM",
            entity_id="AI4BINANCE",
            observed_at=observed_at,
            evidence_refs=("auto-audit-cycle",),
            root_cause_key="scheduled-baseline",
        ),
        security_audit_event(
            SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK,
            observed_at=observed_at,
            evidence_refs=(
                "auto-audit-cycle",
                "system-report",
                "privacy-leak-guard",
            ),
            root_cause_key="security-daily-quick",
        ),
    ]
    if system_status != "READY" or blockers:
        events.append(
            ContinuousAuditEvent(
                event_id=f"eaacie-system:{int(observed_at.timestamp())}",
                trigger_type=AuditTriggerType.SYSTEM_BLOCKER,
                entity_type="SYSTEM",
                entity_id=system_status or "UNKNOWN",
                observed_at=observed_at,
                evidence_refs=("system-report",),
                root_cause_key="system-blocker-trend",
            )
        )
    for blocker in new_blockers:
        events.append(_blocker_event(blocker, observed_at, "new-blocker"))
    for blocker in resolved_blockers:
        events.append(_blocker_event(blocker, observed_at, "resolved-blocker"))
    if privacy_leak_status != "CLEAR":
        events.append(
            ContinuousAuditEvent(
                event_id=f"eaacie-privacy:{int(observed_at.timestamp())}",
                trigger_type=AuditTriggerType.PRIVACY_OR_LEAKAGE,
                entity_type="PUBLIC_REPORT_SURFACE",
                entity_id="privacy-leak-guard",
                observed_at=observed_at,
                evidence_refs=("privacy-leak-guard",),
                security_trigger_type=SecurityAuditTriggerType.GIT_CLOUD_EVENT,
                security_domains=_security_domains_for_trigger(
                    SecurityAuditTriggerType.GIT_CLOUD_EVENT
                ),
                root_cause_key="privacy-leakage",
            )
        )
    return tuple(events)


def events_from_performance_evidence_snapshot(
    snapshot: PerformanceEvidenceSnapshot,
) -> tuple[ContinuousAuditEvent, ...]:
    """Convert canonical decision outcome telemetry into EAACIE audit events.

    Auto-Audit consumes these events as report-only evidence. This bridge does
    not calculate business metrics and does not mutate risk, validation, DGE, or
    execution configuration.
    """

    if not snapshot.auto_audit_consumable:
        return ()
    observed_at = snapshot.observed_at
    evidence_refs = _performance_evidence_refs(snapshot)
    events: list[ContinuousAuditEvent] = [
        ContinuousAuditEvent(
            event_id=f"eaacie-performance-decision:{snapshot.snapshot_id}",
            trigger_type=AuditTriggerType.DECISION_AUDIT,
            entity_type="DECISION_OUTCOME_GRAPH",
            entity_id=snapshot.snapshot_id,
            observed_at=observed_at,
            evidence_refs=evidence_refs,
            trigger_modes=(
                AuditTriggerMode.EVENT_DRIVEN,
                AuditTriggerMode.RISK_DRIVEN,
            ),
            root_cause_key=f"decision-outcome:{snapshot.snapshot_id}",
        )
    ]
    if not snapshot.lineage.complete:
        events.append(
            ContinuousAuditEvent(
                event_id=f"eaacie-performance-lineage:{snapshot.snapshot_id}",
                trigger_type=AuditTriggerType.DATA_QUALITY,
                entity_type="DECISION_OUTCOME_LINEAGE",
                entity_id=snapshot.snapshot_id,
                observed_at=observed_at,
                evidence_refs=_dedupe_refs(
                    *evidence_refs,
                    "lineage-completeness",
                ),
                trigger_modes=(
                    AuditTriggerMode.ANOMALY_DRIVEN,
                    AuditTriggerMode.RISK_DRIVEN,
                ),
                root_cause_key=f"lineage:{snapshot.snapshot_id}",
            )
        )
    if snapshot.telemetry_snapshot is not None:
        telemetry = snapshot.telemetry_snapshot
        if telemetry.blockers or not telemetry.gate_eligible:
            events.append(
                ContinuousAuditEvent(
                    event_id=f"eaacie-performance-telemetry:{snapshot.snapshot_id}",
                    trigger_type=AuditTriggerType.PERFORMANCE_DRIFT,
                    entity_type="CANONICAL_TELEMETRY",
                    entity_id=telemetry.telemetry_id,
                    observed_at=telemetry.observed_at,
                    evidence_refs=_dedupe_refs(
                        *evidence_refs,
                        f"telemetry:{telemetry.telemetry_id}",
                    ),
                    trigger_modes=(AuditTriggerMode.ANOMALY_DRIVEN,),
                    root_cause_key=f"telemetry:{telemetry.telemetry_id}",
                )
            )
    for acceptance in snapshot.acceptance_results:
        if acceptance.status not in {
            AcceptanceGateStatus.PASS,
            AcceptanceGateStatus.INFORMATIONAL_ONLY,
        }:
            events.append(
                ContinuousAuditEvent(
                    event_id=(
                        "eaacie-performance-acceptance:"
                        f"{_safe_event_token(acceptance.result_id)}"
                    ),
                    trigger_type=AuditTriggerType.PERFORMANCE_DRIFT,
                    entity_type="PERFORMANCE_ACCEPTANCE",
                    entity_id=acceptance.result_id,
                    observed_at=observed_at,
                    evidence_refs=_dedupe_refs(
                        *evidence_refs,
                        *acceptance.evidence_refs,
                    ),
                    trigger_modes=(
                        AuditTriggerMode.ANOMALY_DRIVEN,
                        AuditTriggerMode.RISK_DRIVEN,
                    ),
                    root_cause_key=f"acceptance:{acceptance.result_id}",
                )
            )
    for blocker in snapshot.blocker_effectiveness:
        if blocker.outcome_class is BlockerOutcome.FALSE_BLOCK:
            events.append(
                ContinuousAuditEvent(
                    event_id=(
                        "eaacie-performance-false-block:"
                        f"{_safe_event_token(blocker.blocker_id)}"
                    ),
                    trigger_type=AuditTriggerType.FALSE_POSITIVE,
                    entity_type="BLOCKER_EFFECTIVENESS",
                    entity_id=blocker.blocker_id,
                    observed_at=observed_at,
                    evidence_refs=_dedupe_refs(
                        *evidence_refs,
                        f"counterfactual:{blocker.counterfactual_id}",
                    ),
                    trigger_modes=(
                        AuditTriggerMode.EVENT_DRIVEN,
                        AuditTriggerMode.ANOMALY_DRIVEN,
                    ),
                    root_cause_key=f"false-block:{blocker.blocker_id}",
                )
            )
        elif blocker.evidence_quality is EvidenceQuality.INSUFFICIENT:
            events.append(
                ContinuousAuditEvent(
                    event_id=(
                        "eaacie-performance-blocker-evidence:"
                        f"{_safe_event_token(blocker.blocker_id)}"
                    ),
                    trigger_type=AuditTriggerType.DATA_QUALITY,
                    entity_type="BLOCKER_EFFECTIVENESS",
                    entity_id=blocker.blocker_id,
                    observed_at=observed_at,
                    evidence_refs=evidence_refs,
                    trigger_modes=(AuditTriggerMode.RISK_DRIVEN,),
                    root_cause_key=f"blocker-evidence:{blocker.blocker_id}",
                )
            )
    for candidate in snapshot.improvement_candidates:
        events.append(
            ContinuousAuditEvent(
                event_id=(
                    "eaacie-performance-improvement:"
                    f"{_safe_event_token(candidate.candidate_id)}"
                ),
                trigger_type=AuditTriggerType.AUTO_LEARN_OUTCOME,
                entity_type="IMPROVEMENT_CANDIDATE",
                entity_id=candidate.candidate_id,
                observed_at=observed_at,
                evidence_refs=_dedupe_refs(
                    *evidence_refs,
                    *candidate.originating_findings,
                ),
                trigger_modes=(
                    AuditTriggerMode.EVENT_DRIVEN,
                    AuditTriggerMode.ANOMALY_DRIVEN,
                ),
                root_cause_key=f"improvement:{candidate.candidate_id}",
            )
        )
    return tuple(events)


def security_audit_event(
    trigger_type: SecurityAuditTriggerType,
    *,
    observed_at: datetime,
    evidence_refs: tuple[str, ...],
    entity_id: str = "AI4BINANCE",
    root_cause_key: str = "",
    recursion_depth: int = 0,
) -> ContinuousAuditEvent:
    """Create one bounded EAACIE security event with deterministic routing."""

    return ContinuousAuditEvent(
        event_id=f"eaacie-security:{trigger_type.value.lower()}:{int(observed_at.timestamp())}",
        trigger_type=_audit_trigger_for_security_trigger(trigger_type),
        entity_type="SECURITY_CORE",
        entity_id=entity_id,
        observed_at=observed_at,
        evidence_refs=evidence_refs,
        trigger_modes=_trigger_modes_for_security_trigger(trigger_type),
        security_trigger_type=trigger_type,
        security_domains=_security_domains_for_trigger(trigger_type),
        root_cause_key=root_cause_key or f"security:{trigger_type.value.lower()}",
        recursion_depth=recursion_depth,
    )


def _event_from_signal(signal: AuditTriggerSignal) -> ContinuousAuditEvent:
    deviation_key = ",".join(signal.deviation_fields) or signal.severity.value
    root = signal.root_cause_key.strip() or (
        f"{signal.entity_kind.value}:{signal.entity_id}:{deviation_key}"
    )
    return ContinuousAuditEvent(
        event_id=f"central-audit:{signal.signal_id}",
        trigger_type=_trigger_type_for_signal(signal),
        entity_type=signal.entity_kind.value,
        entity_id=signal.entity_id,
        observed_at=signal.observed_at,
        evidence_refs=signal.evidence_refs,
        trigger_modes=signal.trigger_modes,
        root_cause_key=root,
        recursion_depth=signal.recursion_depth,
    )


def _trigger_type_for_signal(signal: AuditTriggerSignal) -> AuditTriggerType:
    if AuditTriggerMode.SCHEDULED in signal.trigger_modes:
        return AuditTriggerType.SCHEDULED_AUDIT
    if AuditTriggerMode.LIFECYCLE_DRIVEN in signal.trigger_modes:
        if signal.entity_kind is AuditObservedEntity.OPERATION:
            return AuditTriggerType.EXECUTION_AUDIT
        return AuditTriggerType.STATE_TRANSITION
    if AuditTriggerMode.RISK_DRIVEN in signal.trigger_modes:
        return _risk_trigger_for_entity(signal.entity_kind)
    if AuditTriggerMode.ANOMALY_DRIVEN in signal.trigger_modes:
        return _anomaly_trigger_for_entity(signal.entity_kind)
    return _event_trigger_for_entity(signal.entity_kind)


def _event_trigger_for_entity(entity_kind: AuditObservedEntity) -> AuditTriggerType:
    mapping = {
        AuditObservedEntity.STATE: AuditTriggerType.STATE_TRANSITION,
        AuditObservedEntity.DECISION: AuditTriggerType.DECISION_AUDIT,
        AuditObservedEntity.DATA: AuditTriggerType.DATA_QUALITY,
        AuditObservedEntity.CONFIGURATION: AuditTriggerType.CONFIGURATION_CHANGE,
        AuditObservedEntity.MODEL: AuditTriggerType.PARAMETER_PROMOTION,
        AuditObservedEntity.OPERATION: AuditTriggerType.EXECUTION_AUDIT,
        AuditObservedEntity.SYSTEM_BEHAVIOR: AuditTriggerType.SYSTEM_BLOCKER,
    }
    return mapping[entity_kind]


def _risk_trigger_for_entity(entity_kind: AuditObservedEntity) -> AuditTriggerType:
    mapping = {
        AuditObservedEntity.STATE: AuditTriggerType.STATE_TRANSITION,
        AuditObservedEntity.DECISION: AuditTriggerType.DECISION_AUDIT,
        AuditObservedEntity.DATA: AuditTriggerType.DATA_QUALITY,
        AuditObservedEntity.CONFIGURATION: AuditTriggerType.CONFIGURATION_CHANGE,
        AuditObservedEntity.MODEL: AuditTriggerType.PARAMETER_PROMOTION,
        AuditObservedEntity.OPERATION: AuditTriggerType.EXECUTION_AUDIT,
        AuditObservedEntity.SYSTEM_BEHAVIOR: AuditTriggerType.SYSTEM_BLOCKER,
    }
    return mapping[entity_kind]


def _anomaly_trigger_for_entity(entity_kind: AuditObservedEntity) -> AuditTriggerType:
    mapping = {
        AuditObservedEntity.STATE: AuditTriggerType.STATE_TRANSITION,
        AuditObservedEntity.DECISION: AuditTriggerType.DECISION_AUDIT,
        AuditObservedEntity.DATA: AuditTriggerType.DATA_QUALITY,
        AuditObservedEntity.CONFIGURATION: AuditTriggerType.CONFIGURATION_CHANGE,
        AuditObservedEntity.MODEL: AuditTriggerType.PERFORMANCE_DRIFT,
        AuditObservedEntity.OPERATION: AuditTriggerType.EXECUTION_AUDIT,
        AuditObservedEntity.SYSTEM_BEHAVIOR: AuditTriggerType.PERFORMANCE_DRIFT,
    }
    return mapping[entity_kind]


def _audit_trigger_for_security_trigger(
    trigger_type: SecurityAuditTriggerType,
) -> AuditTriggerType:
    mapping = {
        SecurityAuditTriggerType.CODE_CHANGE: AuditTriggerType.CODE_CHANGE,
        SecurityAuditTriggerType.CONFIG_CHANGE: AuditTriggerType.CONFIGURATION_CHANGE,
        SecurityAuditTriggerType.DEPENDENCY_CHANGE: AuditTriggerType.DEPENDENCY_CHANGE,
        SecurityAuditTriggerType.CREDENTIAL_SECRET_EVENT: (
            AuditTriggerType.CREDENTIAL_SECRET_EVENT
        ),
        SecurityAuditTriggerType.GIT_CLOUD_EVENT: AuditTriggerType.GIT_CLOUD_EVENT,
        SecurityAuditTriggerType.SECURITY_INCIDENT: AuditTriggerType.SECURITY_INCIDENT,
        SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK: (
            AuditTriggerType.SCHEDULED_DAILY_QUICK
        ),
        SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP: (
            AuditTriggerType.SCHEDULED_WEEKLY_DEEP
        ),
    }
    return mapping[trigger_type]


def _security_domains_for_trigger(
    trigger_type: SecurityAuditTriggerType,
) -> tuple[SecurityDomain, ...]:
    all_domains = tuple(SecurityDomain)
    mapping = {
        SecurityAuditTriggerType.CODE_CHANGE: (
            SecurityDomain.APPSEC,
            SecurityDomain.SECRETS,
            SecurityDomain.DLP,
            SecurityDomain.AUDIT,
        ),
        SecurityAuditTriggerType.CONFIG_CHANGE: (
            SecurityDomain.ACCESS,
            SecurityDomain.SECRETS,
            SecurityDomain.APPSEC,
            SecurityDomain.DLP,
            SecurityDomain.AUDIT,
            SecurityDomain.RECOVERY,
        ),
        SecurityAuditTriggerType.DEPENDENCY_CHANGE: (
            SecurityDomain.APPSEC,
            SecurityDomain.VULNERABILITY,
            SecurityDomain.AUDIT,
        ),
        SecurityAuditTriggerType.CREDENTIAL_SECRET_EVENT: (
            SecurityDomain.ACCESS,
            SecurityDomain.SECRETS,
            SecurityDomain.DLP,
            SecurityDomain.AUDIT,
            SecurityDomain.RECOVERY,
        ),
        SecurityAuditTriggerType.GIT_CLOUD_EVENT: (
            SecurityDomain.PRIVACY,
            SecurityDomain.SECRETS,
            SecurityDomain.DLP,
            SecurityDomain.AUDIT,
        ),
        SecurityAuditTriggerType.SECURITY_INCIDENT: all_domains,
        SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK: all_domains,
        SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP: all_domains,
    }
    return mapping[trigger_type]


def _trigger_modes_for_security_trigger(
    trigger_type: SecurityAuditTriggerType,
) -> tuple[AuditTriggerMode, ...]:
    scheduled = (
        AuditTriggerMode.SCHEDULED,
        AuditTriggerMode.RISK_DRIVEN,
    )
    mapping = {
        SecurityAuditTriggerType.CODE_CHANGE: (AuditTriggerMode.EVENT_DRIVEN,),
        SecurityAuditTriggerType.CONFIG_CHANGE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        SecurityAuditTriggerType.DEPENDENCY_CHANGE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        SecurityAuditTriggerType.CREDENTIAL_SECRET_EVENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        SecurityAuditTriggerType.GIT_CLOUD_EVENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        SecurityAuditTriggerType.SECURITY_INCIDENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
            AuditTriggerMode.ANOMALY_DRIVEN,
        ),
        SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK: scheduled,
        SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP: scheduled,
    }
    return mapping[trigger_type]


def _storm_status(
    event: ContinuousAuditEvent,
    recent: dict[str, ContinuousAuditEvent],
    root_causes: set[str],
    policy: AuditStormPolicy,
) -> AuditStormStatus:
    if event.recursion_depth > policy.max_recursion_depth:
        return AuditStormStatus.BLOCKED_RECURSION_DEPTH
    previous = recent.get(event.dedup_key)
    if policy.dedup and previous is not None:
        elapsed = (event.observed_at - previous.observed_at).total_seconds()
        if 0 <= elapsed < policy.cooldown_seconds:
            return AuditStormStatus.SUPPRESSED_COOLDOWN
    if (
        policy.same_root_cause_merge
        and event.root_cause_key.strip()
        and event.root_cause_key.strip() in root_causes
    ):
        return AuditStormStatus.MERGED_SAME_ROOT_CAUSE
    return AuditStormStatus.ACCEPTED


def _domains_for_trigger(trigger_type: AuditTriggerType) -> tuple[AuditDomain, ...]:
    mapping: dict[AuditTriggerType, tuple[AuditDomain, ...]] = {
        AuditTriggerType.SCHEDULED_AUDIT: (
            AuditDomain.AGENT_ASSURANCE,
            AuditDomain.INSTRUCTION_GOVERNANCE,
            AuditDomain.LEAN_KAIZEN,
            AuditDomain.PERFORMANCE_ENGINEERING,
        ),
        AuditTriggerType.MANUAL_AUDIT: (
            AuditDomain.GAP_ANALYSIS,
            AuditDomain.LEAN_KAIZEN,
            AuditDomain.DGE_ASSURANCE,
        ),
        AuditTriggerType.CODE_CHANGE: (
            AuditDomain.CODE_QUALITY,
            AuditDomain.ARCHITECTURE_INTELLIGENCE,
            AuditDomain.INSTRUCTION_GOVERNANCE,
        ),
        AuditTriggerType.CONFIGURATION_CHANGE: (
            AuditDomain.INSTRUCTION_GOVERNANCE,
            AuditDomain.DGE_ASSURANCE,
            AuditDomain.TRADING_ASSURANCE,
        ),
        AuditTriggerType.INSTRUCTION_CHANGE: (
            AuditDomain.INSTRUCTION_GOVERNANCE,
            AuditDomain.GAP_ANALYSIS,
            AuditDomain.DGE_ASSURANCE,
        ),
        AuditTriggerType.STATE_TRANSITION: (
            AuditDomain.WORKFLOW_ASSURANCE,
            AuditDomain.DGE_ASSURANCE,
        ),
        AuditTriggerType.DECISION_AUDIT: (
            AuditDomain.DGE_ASSURANCE,
            AuditDomain.TRADING_ASSURANCE,
        ),
        AuditTriggerType.DATA_QUALITY: (
            AuditDomain.DATA_GOVERNANCE,
            AuditDomain.BACKTEST_QA,
        ),
        AuditTriggerType.PARAMETER_PROMOTION: (
            AuditDomain.PARAMETER_GOVERNANCE,
            AuditDomain.BACKTEST_QA,
            AuditDomain.DGE_ASSURANCE,
        ),
        AuditTriggerType.PERFORMANCE_DRIFT: (
            AuditDomain.PERFORMANCE_ENGINEERING,
            AuditDomain.COST_OPTIMIZATION,
        ),
        AuditTriggerType.MARKET_REGIME_CHANGE: (
            AuditDomain.TRADING_ASSURANCE,
            AuditDomain.BACKTEST_QA,
        ),
        AuditTriggerType.NEWS_SECURITY_EVENT: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.TRADING_ASSURANCE,
        ),
        AuditTriggerType.EXECUTION_AUDIT: (
            AuditDomain.TRADING_ASSURANCE,
            AuditDomain.CYBERSECURITY,
            AuditDomain.DGE_ASSURANCE,
        ),
        AuditTriggerType.STOP_LOSS_AUDIT: (
            AuditDomain.TRADING_ASSURANCE,
            AuditDomain.AUTO_LEARN_GOVERNANCE,
        ),
        AuditTriggerType.TRAILING_STOP_AUDIT: (
            AuditDomain.TRADING_ASSURANCE,
            AuditDomain.AUTO_LEARN_GOVERNANCE,
        ),
        AuditTriggerType.FALSE_POSITIVE: (
            AuditDomain.TRADING_ASSURANCE,
            AuditDomain.AUTO_LEARN_GOVERNANCE,
        ),
        AuditTriggerType.AUTO_LEARN_OUTCOME: (
            AuditDomain.AUTO_LEARN_GOVERNANCE,
            AuditDomain.PARAMETER_GOVERNANCE,
        ),
        AuditTriggerType.PRIVACY_OR_LEAKAGE: (
            AuditDomain.PRIVACY_KVKK,
            AuditDomain.CYBERSECURITY,
            AuditDomain.DGE_ASSURANCE,
        ),
        AuditTriggerType.SYSTEM_BLOCKER: (
            AuditDomain.WORKFLOW_ASSURANCE,
            AuditDomain.LEAN_KAIZEN,
            AuditDomain.GAP_ANALYSIS,
        ),
        AuditTriggerType.DEPENDENCY_CHANGE: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.CODE_QUALITY,
        ),
        AuditTriggerType.CREDENTIAL_SECRET_EVENT: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.PRIVACY_KVKK,
        ),
        AuditTriggerType.GIT_CLOUD_EVENT: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.PRIVACY_KVKK,
            AuditDomain.CODE_QUALITY,
        ),
        AuditTriggerType.SECURITY_INCIDENT: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.PRIVACY_KVKK,
            AuditDomain.WORKFLOW_ASSURANCE,
        ),
        AuditTriggerType.SCHEDULED_DAILY_QUICK: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.PRIVACY_KVKK,
            AuditDomain.WORKFLOW_ASSURANCE,
        ),
        AuditTriggerType.SCHEDULED_WEEKLY_DEEP: (
            AuditDomain.CYBERSECURITY,
            AuditDomain.PRIVACY_KVKK,
            AuditDomain.CODE_QUALITY,
            AuditDomain.GAP_ANALYSIS,
        ),
    }
    return mapping[trigger_type]


def _hybrid_classes_for_trigger(
    trigger_type: AuditTriggerType,
) -> tuple[HybridTriggerClass, ...]:
    mapping: dict[AuditTriggerType, tuple[HybridTriggerClass, ...]] = {
        AuditTriggerType.SCHEDULED_AUDIT: (HybridTriggerClass.SCHEDULE,),
        AuditTriggerType.MANUAL_AUDIT: (HybridTriggerClass.MANUAL,),
        AuditTriggerType.CODE_CHANGE: (
            HybridTriggerClass.CHANGE,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.CONFIGURATION_CHANGE: (
            HybridTriggerClass.CHANGE,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.INSTRUCTION_CHANGE: (
            HybridTriggerClass.CHANGE,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.STATE_TRANSITION: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.DECISION_AUDIT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.DATA_QUALITY: (
            HybridTriggerClass.EVIDENCE,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.PARAMETER_PROMOTION: (
            HybridTriggerClass.CHANGE,
            HybridTriggerClass.EVIDENCE,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.PERFORMANCE_DRIFT: (HybridTriggerClass.DRIFT,),
        AuditTriggerType.MARKET_REGIME_CHANGE: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.DRIFT,
        ),
        AuditTriggerType.NEWS_SECURITY_EVENT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.EXECUTION_AUDIT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.RISK,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.STOP_LOSS_AUDIT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.TRAILING_STOP_AUDIT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.FALSE_POSITIVE: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.AUTO_LEARN_OUTCOME: (
            HybridTriggerClass.EVIDENCE,
            HybridTriggerClass.DRIFT,
        ),
        AuditTriggerType.PRIVACY_OR_LEAKAGE: (
            HybridTriggerClass.RISK,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.SYSTEM_BLOCKER: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.DRIFT,
        ),
        AuditTriggerType.DEPENDENCY_CHANGE: (
            HybridTriggerClass.CHANGE,
            HybridTriggerClass.RISK,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.CREDENTIAL_SECRET_EVENT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.RISK,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.GIT_CLOUD_EVENT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.CHANGE,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.SECURITY_INCIDENT: (
            HybridTriggerClass.EVENT,
            HybridTriggerClass.RISK,
            HybridTriggerClass.EVIDENCE,
        ),
        AuditTriggerType.SCHEDULED_DAILY_QUICK: (
            HybridTriggerClass.SCHEDULE,
            HybridTriggerClass.RISK,
        ),
        AuditTriggerType.SCHEDULED_WEEKLY_DEEP: (
            HybridTriggerClass.SCHEDULE,
            HybridTriggerClass.RISK,
            HybridTriggerClass.EVIDENCE,
        ),
    }
    return mapping[trigger_type]


def _trigger_modes_for_trigger(
    trigger_type: AuditTriggerType,
) -> tuple[AuditTriggerMode, ...]:
    mapping: dict[AuditTriggerType, tuple[AuditTriggerMode, ...]] = {
        AuditTriggerType.SCHEDULED_AUDIT: (AuditTriggerMode.SCHEDULED,),
        AuditTriggerType.MANUAL_AUDIT: (AuditTriggerMode.EVENT_DRIVEN,),
        AuditTriggerType.CODE_CHANGE: (AuditTriggerMode.EVENT_DRIVEN,),
        AuditTriggerType.CONFIGURATION_CHANGE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.INSTRUCTION_CHANGE: (AuditTriggerMode.EVENT_DRIVEN,),
        AuditTriggerType.STATE_TRANSITION: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.LIFECYCLE_DRIVEN,
        ),
        AuditTriggerType.DECISION_AUDIT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.DATA_QUALITY: (
            AuditTriggerMode.ANOMALY_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.PARAMETER_PROMOTION: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.PERFORMANCE_DRIFT: (AuditTriggerMode.ANOMALY_DRIVEN,),
        AuditTriggerType.MARKET_REGIME_CHANGE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.ANOMALY_DRIVEN,
        ),
        AuditTriggerType.NEWS_SECURITY_EVENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.EXECUTION_AUDIT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
            AuditTriggerMode.LIFECYCLE_DRIVEN,
        ),
        AuditTriggerType.STOP_LOSS_AUDIT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.LIFECYCLE_DRIVEN,
        ),
        AuditTriggerType.TRAILING_STOP_AUDIT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.LIFECYCLE_DRIVEN,
        ),
        AuditTriggerType.FALSE_POSITIVE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.ANOMALY_DRIVEN,
        ),
        AuditTriggerType.AUTO_LEARN_OUTCOME: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.ANOMALY_DRIVEN,
        ),
        AuditTriggerType.PRIVACY_OR_LEAKAGE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.SYSTEM_BLOCKER: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.ANOMALY_DRIVEN,
        ),
        AuditTriggerType.DEPENDENCY_CHANGE: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.CREDENTIAL_SECRET_EVENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.GIT_CLOUD_EVENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.SECURITY_INCIDENT: (
            AuditTriggerMode.EVENT_DRIVEN,
            AuditTriggerMode.RISK_DRIVEN,
            AuditTriggerMode.ANOMALY_DRIVEN,
        ),
        AuditTriggerType.SCHEDULED_DAILY_QUICK: (
            AuditTriggerMode.SCHEDULED,
            AuditTriggerMode.RISK_DRIVEN,
        ),
        AuditTriggerType.SCHEDULED_WEEKLY_DEEP: (
            AuditTriggerMode.SCHEDULED,
            AuditTriggerMode.RISK_DRIVEN,
        ),
    }
    return mapping[trigger_type]


def _patterns_for_domains(
    domains: tuple[AuditDomain, ...],
) -> tuple[AuditWorkflowPattern, ...]:
    patterns = [AuditWorkflowPattern.ROUTING, AuditWorkflowPattern.EVALUATOR_OPTIMIZER]
    if any(domain in _HIGH_RISK_DOMAINS for domain in domains):
        patterns.append(AuditWorkflowPattern.HUMAN_IN_THE_LOOP)
    return tuple(patterns)


def _blockers_for(
    event: ContinuousAuditEvent,
    domains: tuple[AuditDomain, ...],
    storm_status: AuditStormStatus,
) -> tuple[str, ...]:
    blockers = ["LIVE_ORDER_BLOCKED"]
    if event.security_trigger_type is not None or any(
        domain in _HIGH_RISK_DOMAINS for domain in domains
    ):
        blockers.append("HUMAN_REVIEW_REQUIRED")
    if storm_status is AuditStormStatus.SUPPRESSED_COOLDOWN:
        blockers.append("AUDIT_COOLDOWN_ACTIVE")
    if storm_status is AuditStormStatus.MERGED_SAME_ROOT_CAUSE:
        blockers.append("AUDIT_SAME_ROOT_CAUSE_MERGED")
    if storm_status is AuditStormStatus.BLOCKED_RECURSION_DEPTH:
        blockers.append("AUDIT_RECURSION_DEPTH_EXCEEDED")
    if event.trigger_type in {
        AuditTriggerType.PARAMETER_PROMOTION,
        AuditTriggerType.AUTO_LEARN_OUTCOME,
    }:
        blockers.append("VALIDATION_EVIDENCE_REQUIRED")
    if event.trigger_type in {
        AuditTriggerType.CODE_CHANGE,
        AuditTriggerType.CONFIGURATION_CHANGE,
        AuditTriggerType.INSTRUCTION_CHANGE,
    }:
        blockers.append("OEK_GAP_ANALYSIS_REQUIRED")
    if event.security_trigger_type is not None:
        blockers.append("SECURITY_AUDIT_REPORT_ONLY")
    if event.security_trigger_type in {
        SecurityAuditTriggerType.CREDENTIAL_SECRET_EVENT,
        SecurityAuditTriggerType.SECURITY_INCIDENT,
    }:
        blockers.append("SECURITY_INCIDENT_RESPONSE_REQUIRED")
    if event.security_trigger_type is SecurityAuditTriggerType.DEPENDENCY_CHANGE:
        blockers.append("DEPENDENCY_SECURITY_REVIEW_REQUIRED")
    if event.security_trigger_type is SecurityAuditTriggerType.GIT_CLOUD_EVENT:
        blockers.append("DLP_REVIEW_REQUIRED")
    return tuple(dict.fromkeys(blockers))


def _action_refs(
    event: ContinuousAuditEvent,
    domains: tuple[AuditDomain, ...],
    storm_status: AuditStormStatus,
) -> tuple[str, ...]:
    if storm_status is not AuditStormStatus.ACCEPTED:
        return (f"observe:{storm_status.value.lower()}:{event.event_id}",)
    refs = [f"route:{event.trigger_type.value.lower()}"]
    if AuditDomain.DGE_ASSURANCE in domains:
        refs.append("run:dge-review")
    if AuditDomain.PRIVACY_KVKK in domains:
        refs.append("run:privacy-boundary")
    if AuditDomain.CODE_QUALITY in domains:
        refs.append("run:repository-cleanup-audit")
    if AuditDomain.LEAN_KAIZEN in domains:
        refs.append("run:lean-governance")
    if AuditDomain.PARAMETER_GOVERNANCE in domains:
        refs.append("run:validate-research")
    if event.security_trigger_type is not None:
        refs.append("run:security-core-audit")
        refs.extend(
            f"check:security:{domain.value.lower()}"
            for domain in event.security_domains
        )
    if event.security_trigger_type is SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK:
        refs.append("run:security-daily-quick")
    if event.security_trigger_type is SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP:
        refs.append("run:security-weekly-deep")
    return tuple(dict.fromkeys(refs))


def _scope_refs(
    event: ContinuousAuditEvent,
    domains: tuple[AuditDomain, ...],
    security_domains: tuple[SecurityDomain, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                f"entity:{event.entity_type}:{event.entity_id}",
                *(f"domain:{domain.value}" for domain in domains),
                *(f"security-domain:{domain.value}" for domain in security_domains),
                *event.evidence_refs,
            )
        )
    )


def _blocker_event(
    blocker: str,
    observed_at: datetime,
    evidence_ref: str,
) -> ContinuousAuditEvent:
    trigger = AuditTriggerType.SYSTEM_BLOCKER
    if blocker.startswith("privacy:"):
        trigger = AuditTriggerType.PRIVACY_OR_LEAKAGE
    elif blocker.startswith("validation:") or "OOS" in blocker:
        trigger = AuditTriggerType.PARAMETER_PROMOTION
    elif blocker.startswith("runtime:"):
        trigger = AuditTriggerType.PERFORMANCE_DRIFT
    elif blocker.startswith("opportunities:"):
        trigger = AuditTriggerType.DECISION_AUDIT
    elif "DATA" in blocker:
        trigger = AuditTriggerType.DATA_QUALITY
    safe_id = blocker.replace(":", "-").replace("/", "-").replace("\\", "-")
    return ContinuousAuditEvent(
        event_id=f"eaacie-blocker:{safe_id}:{int(observed_at.timestamp())}",
        trigger_type=trigger,
        entity_type="BLOCKER",
        entity_id=blocker,
        observed_at=observed_at,
        evidence_refs=(evidence_ref,),
        root_cause_key=blocker,
    )


def _performance_evidence_refs(
    snapshot: PerformanceEvidenceSnapshot,
) -> tuple[str, ...]:
    refs = [
        f"decision-telemetry:{snapshot.snapshot_id}",
        f"decision:{snapshot.decision_process.decision_id}",
        f"outcome:{snapshot.decision_outcome.outcome_id}",
        f"dge:{snapshot.snapshot_id}",
    ]
    if snapshot.telemetry_snapshot is not None:
        refs.append(f"telemetry:{snapshot.telemetry_snapshot.telemetry_id}")
    refs.extend(
        f"counterfactual:{item.counterfactual_id}" for item in snapshot.counterfactuals
    )
    refs.extend(f"attribution:{item.attribution_id}" for item in snapshot.attributions)
    refs.extend(f"acceptance:{item.result_id}" for item in snapshot.acceptance_results)
    refs.extend(
        f"improvement:{item.candidate_id}" for item in snapshot.improvement_candidates
    )
    return tuple(dict.fromkeys(refs))


def _safe_event_token(value: str) -> str:
    safe = "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "-"
        for char in value.strip()
    )
    return safe or "unknown"


def _dedupe_refs(*refs: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(refs))


def _uncertainty_level(blockers: tuple[str, ...]) -> UncertaintyLevel:
    if any(
        blocker
        in {
            "LIVE_ORDER_BLOCKED",
            "HUMAN_REVIEW_REQUIRED",
            "SECURITY_INCIDENT_RESPONSE_REQUIRED",
            "VALIDATION_EVIDENCE_REQUIRED",
        }
        for blocker in blockers
    ):
        return UncertaintyLevel.HIGH
    if blockers:
        return UncertaintyLevel.MEDIUM
    return UncertaintyLevel.LOW


def _uncertainty_reasons(plan: ContinuousAssurancePlan) -> tuple[str, ...]:
    reasons = [
        "ASSURANCE_REPORT_ONLY",
        "DETERMINISTIC_CORE_RETAINS_EXECUTION_AUTHORITY",
    ]
    reasons.extend(plan.blockers)
    if plan.suppressed_count:
        reasons.append("AUDIT_STORM_SUPPRESSION_PRESENT")
    if any(decision.review_required for decision in plan.route_decisions):
        reasons.append("HUMAN_REVIEW_REQUIRED")
    return tuple(dict.fromkeys(reasons))


def _semantic_contracts_for_plan(
    plan: ContinuousAssurancePlan,
) -> tuple[SemanticContractRecord, ...]:
    contracts = [
        SemanticContractRecord(
            contract_id="contract:continuous-assurance-plan",
            subject="ContinuousAssurancePlan",
            required_fields=(
                "plan_id",
                "observed_at",
                "route_decisions",
                "blockers",
                "instruction_refs",
                "execution_allowed",
                "promotion_status",
                "live_eligibility_status",
            ),
            forbidden_fields=_forbidden_sensitive_fields(),
        ),
        SemanticContractRecord(
            contract_id="contract:audit-route-decision",
            subject="AuditRouteDecision",
            required_fields=(
                "event_id",
                "trigger_type",
                "domains",
                "scope_refs",
                "blockers",
                "action_refs",
            ),
            forbidden_fields=_forbidden_sensitive_fields(),
        ),
    ]
    if plan.security_trigger_types:
        contracts.append(
            SemanticContractRecord(
                contract_id="contract:security-assurance-evidence",
                subject="EAACIE Security Core Evidence",
                required_fields=(
                    "security_domains",
                    "trigger_types",
                    "review_required",
                    "automatic_remediation",
                    "live_eligibility_status",
                ),
                forbidden_fields=_forbidden_sensitive_fields(),
            )
        )
    return tuple(contracts)


def _forbidden_sensitive_fields() -> tuple[str, ...]:
    return (
        "api_key",
        "secret",
        "token",
        "password",
        "private_key",
        "seed",
        "wallet_balance_raw",
        "account_snapshot_raw",
    )


def _evidence_graph_for_bundle(
    *,
    plan_id: str,
    provenance: DecisionProvenanceRecord,
    policy_evaluations: tuple[PolicyEvaluationRecord, ...],
    uncertainty: UncertaintyAssessmentRecord,
    semantic_contracts: tuple[SemanticContractRecord, ...],
) -> EvidenceGraphLiteRecord:
    nodes: list[EvidenceGraphNode] = [
        EvidenceGraphNode(
            node_id="decision",
            node_type="DECISION",
            ref=provenance.decision_id,
        ),
        EvidenceGraphNode(
            node_id="uncertainty",
            node_type="UNCERTAINTY",
            ref=uncertainty.assessment_id,
        ),
    ]
    node_ids = {"decision", "uncertainty"}
    edges = [
        EvidenceGraphEdge(
            source="decision",
            relation="HAS_UNCERTAINTY",
            target="uncertainty",
        )
    ]
    for evaluation in policy_evaluations:
        policy_node = _node_id("policy", evaluation.evaluation_id)
        nodes.append(
            EvidenceGraphNode(
                node_id=policy_node,
                node_type="POLICY_EVALUATION",
                ref=evaluation.evaluation_id,
            )
        )
        node_ids.add(policy_node)
        edges.append(
            EvidenceGraphEdge(
                source="decision",
                relation="EVALUATED_BY",
                target=policy_node,
            )
        )
        for evidence_ref in evaluation.evidence_refs:
            evidence_node = _node_id("evidence", evidence_ref)
            if evidence_node not in node_ids:
                nodes.append(
                    EvidenceGraphNode(
                        node_id=evidence_node,
                        node_type="EVIDENCE_REF",
                        ref=evidence_ref,
                    )
                )
                node_ids.add(evidence_node)
            edges.append(
                EvidenceGraphEdge(
                    source=policy_node,
                    relation="EVIDENCED_BY",
                    target=evidence_node,
                )
            )
        for blocker in evaluation.blockers:
            blocker_node = _node_id("blocker", blocker)
            if blocker_node not in node_ids:
                nodes.append(
                    EvidenceGraphNode(
                        node_id=blocker_node,
                        node_type="BLOCKER",
                        ref=blocker,
                    )
                )
                node_ids.add(blocker_node)
            edges.append(
                EvidenceGraphEdge(
                    source=policy_node,
                    relation="BLOCKED_BY",
                    target=blocker_node,
                )
            )
    for contract in semantic_contracts:
        contract_node = _node_id("contract", contract.contract_id)
        nodes.append(
            EvidenceGraphNode(
                node_id=contract_node,
                node_type="SEMANTIC_CONTRACT",
                ref=contract.contract_id,
            )
        )
        node_ids.add(contract_node)
        edges.append(
            EvidenceGraphEdge(
                source="decision",
                relation="GOVERNED_BY",
                target=contract_node,
            )
        )
    return EvidenceGraphLiteRecord(
        graph_id=f"evidence-graph-lite:{plan_id}",
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def _node_id(prefix: str, value: str) -> str:
    return f"{prefix}:{_stable_digest(value)[:16]}"


def _stable_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _validate_security_routing(
    name: str,
    trigger_type: SecurityAuditTriggerType | None,
    domains: tuple[SecurityDomain, ...],
) -> None:
    _require_unique(
        f"{name} security domains",
        tuple(domain.value for domain in domains),
    )
    if trigger_type is None:
        if domains:
            raise ValueError(f"{name} security domains require a security trigger")
        return
    expected = _security_domains_for_trigger(trigger_type)
    if domains != expected:
        raise ValueError(f"{name} security domains do not match trigger policy")

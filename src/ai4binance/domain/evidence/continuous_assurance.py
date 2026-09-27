"""Pure, immutable continuous-assurance evidence contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from ai4binance.domain.evidence.trust_plane import (
    build_conditional_trust_plane_assessment,
)


class TrustAssuranceResult(StrEnum):
    PASSED = "PASSED"
    WARN = "WARN"
    BLOCKED = "BLOCKED"


class UncertaintyLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


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


def _stable_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

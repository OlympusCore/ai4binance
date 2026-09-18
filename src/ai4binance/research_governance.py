"""Research run cards, hypothesis lifecycle and demotion-only decay governance."""

# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import cast

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified


def _require_identity(**values: str) -> None:
    missing = tuple(name for name, value in values.items() if not value.strip())
    if missing:
        raise ValueError(
            f"research identity fields cannot be empty: {', '.join(missing)}"
        )


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _tuple_of_text(
    payload: Mapping[str, object],
    key: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    raw = payload.get(key)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError(f"{key} must be a sequence of text values")
    values = tuple(str(item).strip() for item in raw)
    if not allow_empty and not values:
        raise ValueError(f"{key} must not be empty")
    if any(not item for item in values):
        raise ValueError(f"{key} must not contain blank values")
    if len(set(values)) != len(values):
        raise ValueError(f"{key} must contain unique values")
    return values


class HypothesisStatus(StrEnum):
    """Human-governed research and strategy lifecycle states."""

    PROPOSED = "PROPOSED"
    RESEARCH = "RESEARCH"
    OOS_VALIDATED = "OOS_VALIDATED"
    PAPER_APPROVED = "PAPER_APPROVED"
    MONITORING = "MONITORING"
    DECAYED = "DECAYED"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"


class VirtualImprovementReviewOutcome(StrEnum):
    """Research-only review outcomes for virtual improvement follow-up artifacts."""

    EXPERIMENT_PROPOSAL = "EXPERIMENT_PROPOSAL"
    INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED"
    CONTINUE_RESEARCH = "CONTINUE_RESEARCH"


class VirtualImprovementExperimentTaskStatus(StrEnum):
    """Lifecycle states for bounded virtual improvement research tasks."""

    QUEUED = "QUEUED"
    EVIDENCE_PENDING = "EVIDENCE_PENDING"
    READY_FOR_RESEARCH = "READY_FOR_RESEARCH"
    COMPLETED = "COMPLETED"


_ALLOWED_TRANSITIONS: Mapping[HypothesisStatus, frozenset[HypothesisStatus]] = (
    MappingProxyType(
        {
            HypothesisStatus.PROPOSED: frozenset(
                {HypothesisStatus.RESEARCH, HypothesisStatus.REJECTED}
            ),
            HypothesisStatus.RESEARCH: frozenset(
                {HypothesisStatus.OOS_VALIDATED, HypothesisStatus.REJECTED}
            ),
            HypothesisStatus.OOS_VALIDATED: frozenset(
                {HypothesisStatus.PAPER_APPROVED, HypothesisStatus.REJECTED}
            ),
            HypothesisStatus.PAPER_APPROVED: frozenset(
                {HypothesisStatus.MONITORING, HypothesisStatus.DISABLED}
            ),
            HypothesisStatus.MONITORING: frozenset(
                {HypothesisStatus.DECAYED, HypothesisStatus.DISABLED}
            ),
            HypothesisStatus.DECAYED: frozenset({HypothesisStatus.DISABLED}),
            HypothesisStatus.DISABLED: frozenset(),
            HypothesisStatus.REJECTED: frozenset(),
        }
    )
)


@dataclass(frozen=True, slots=True)
class ResearchHypothesis:
    """Falsifiable research hypothesis linked to immutable artifacts."""

    hypothesis_id: str
    title: str
    thesis: str
    symbol: str
    timeframe: str
    invalidation_conditions: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    artifact_ids: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            hypothesis_id=self.hypothesis_id,
            title=self.title,
            thesis=self.thesis,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )
        _require_aware("hypothesis created_at", self.created_at)
        _require_aware("hypothesis updated_at", self.updated_at)
        if not self.invalidation_conditions or any(
            not item.strip() for item in self.invalidation_conditions
        ):
            raise ValueError("hypothesis requires explicit invalidation conditions")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("hypothesis artifact IDs must be unique")
        if self.execution_allowed:
            raise ValueError("research hypothesis cannot grant execution authority")

    def transition(
        self,
        status: HypothesisStatus,
        *,
        updated_at: datetime,
        artifact_ids: tuple[str, ...] = (),
    ) -> ResearchHypothesis:
        """Apply an explicit forward or demotion transition."""
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid hypothesis transition: {self.status}->{status}")
        _require_aware("hypothesis updated_at", updated_at)
        merged = tuple(dict.fromkeys((*self.artifact_ids, *artifact_ids)))
        return replace(self, status=status, updated_at=updated_at, artifact_ids=merged)


@dataclass(frozen=True, slots=True)
class VirtualImprovementReviewInput:
    """Governed consumer contract for a virtual improvement review handoff."""

    handoff_id: str
    snapshot_id: str
    surface_kind: str
    objective: str
    assurance_artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    governance_refs: tuple[str, ...]
    required_output_fields: tuple[str, ...]
    blocker_refs: tuple[str, ...] = ()
    priority: str = "P1"
    status: str = "QUEUED_RESEARCH_ONLY"
    review_required: bool = True
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            handoff_id=self.handoff_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            objective=self.objective,
            priority=self.priority,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError("virtual improvement review surface kind is invalid")
        if self.priority not in {"P0", "P1"}:
            raise ValueError("virtual improvement review priority is invalid")
        if self.status != "QUEUED_RESEARCH_ONLY":
            raise ValueError("virtual improvement review status is invalid")
        if not self.review_required:
            raise ValueError("virtual improvement review requires explicit review")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("virtual improvement review cannot authorize trading")
        if "VirtualImprovementResearchQueue" not in self.governance_refs:
            raise ValueError("virtual improvement review requires queue governance ref")
        if not set(self.assurance_artifact_refs).issubset(set(self.evidence_refs)):
            raise ValueError(
                "virtual improvement review assurance refs must be part of evidence refs"
            )
        expected_outputs = (
            "review_outcome",
            "recommended_experiment",
            "evidence_gap_assessment",
        )
        if self.required_output_fields != expected_outputs:
            raise ValueError("virtual improvement review output contract is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "handoff_id": self.handoff_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "objective": self.objective,
            "assurance_artifact_refs": self.assurance_artifact_refs,
            "evidence_refs": self.evidence_refs,
            "governance_refs": self.governance_refs,
            "required_output_fields": self.required_output_fields,
            "blocker_refs": self.blocker_refs,
            "priority": self.priority,
            "status": self.status,
            "review_required": True,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "execution_allowed": False,
        }


def consume_virtual_improvement_review_handoff(
    handoff: Mapping[str, object],
) -> VirtualImprovementReviewInput:
    """Validate and normalize a virtual improvement review handoff."""
    schema_version = str(handoff.get("schema_version", "")).strip()
    task_type = str(handoff.get("task_type", "")).strip()
    if schema_version != "VirtualImprovementResearchHandoff/v1":
        raise ValueError("virtual improvement handoff schema version is invalid")
    if task_type != "VIRTUAL_IMPROVEMENT_REVIEW":
        raise ValueError("virtual improvement handoff task type is invalid")

    evidence_refs = _tuple_of_text(handoff, "evidence_refs")
    assurance_artifact_refs = tuple(
        ref for ref in evidence_refs if "virtual_improvement_queue_assurance" in ref
    )
    if not assurance_artifact_refs:
        raise ValueError("virtual improvement handoff requires assurance artifact refs")

    return VirtualImprovementReviewInput(
        handoff_id=str(handoff.get("handoff_id", "")).strip(),
        snapshot_id=str(handoff.get("snapshot_id", "")).strip(),
        surface_kind=str(handoff.get("surface_kind", "")).strip(),
        objective=str(handoff.get("objective", "")).strip(),
        assurance_artifact_refs=assurance_artifact_refs,
        evidence_refs=evidence_refs,
        governance_refs=_tuple_of_text(handoff, "governance_refs"),
        required_output_fields=_tuple_of_text(handoff, "required_output_fields"),
        blocker_refs=_tuple_of_text(handoff, "blocker_refs", allow_empty=True),
        priority=str(handoff.get("priority", "")).strip(),
        status=str(handoff.get("status", "")).strip(),
        review_required=bool(handoff.get("execution_allowed", False) is False),
        promotion_status=str(handoff.get("promotion_status", "")).strip(),
        live_eligibility_status=str(handoff.get("live_eligibility_status", "")).strip(),
        execution_allowed=bool(handoff.get("execution_allowed", False)),
    )


@dataclass(frozen=True, slots=True)
class VirtualImprovementReviewResult:
    """Deterministic research-only follow-up artifact for a virtual improvement review."""

    review_id: str
    handoff_id: str
    snapshot_id: str
    surface_kind: str
    outcome: VirtualImprovementReviewOutcome
    recommended_experiment: str
    evidence_gap_assessment: str
    assurance_artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    follow_up_artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            review_id=self.review_id,
            handoff_id=self.handoff_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            recommended_experiment=self.recommended_experiment,
            evidence_gap_assessment=self.evidence_gap_assessment,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement review result surface kind is invalid"
            )
        if self.outcome not in {
            VirtualImprovementReviewOutcome.EXPERIMENT_PROPOSAL,
            VirtualImprovementReviewOutcome.INVESTIGATION_REQUIRED,
            VirtualImprovementReviewOutcome.CONTINUE_RESEARCH,
        }:
            raise ValueError("virtual improvement review result outcome is invalid")
        if len(set(self.assurance_artifact_refs)) != len(self.assurance_artifact_refs):
            raise ValueError(
                "virtual improvement review result assurance refs must be unique"
            )
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError(
                "virtual improvement review result evidence refs must be unique"
            )
        if len(set(self.follow_up_artifact_refs)) != len(self.follow_up_artifact_refs):
            raise ValueError(
                "virtual improvement review result follow-up refs must be unique"
            )
        if not set(self.assurance_artifact_refs).issubset(set(self.evidence_refs)):
            raise ValueError(
                "virtual improvement review result assurance refs must be part of evidence refs"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement review result cannot authorize trading"
            )
        if (
            self.outcome is VirtualImprovementReviewOutcome.INVESTIGATION_REQUIRED
            and not self.blockers
        ):
            raise ValueError(
                "investigation-required review result must include blockers"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "handoff_id": self.handoff_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "outcome": self.outcome.value,
            "recommended_experiment": self.recommended_experiment,
            "evidence_gap_assessment": self.evidence_gap_assessment,
            "assurance_artifact_refs": self.assurance_artifact_refs,
            "evidence_refs": self.evidence_refs,
            "follow_up_artifact_refs": self.follow_up_artifact_refs,
            "blockers": self.blockers,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementReviewResultWriter:
    """Atomically persist a virtual improvement review result and append an audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, result: VirtualImprovementReviewResult) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(result)),
            blocker="VIRTUAL_IMPROVEMENT_REVIEW_RESULT_DESTINATION_VERIFY_FAILED",
            subject_id=result.review_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="VIRTUAL_IMPROVEMENT_REVIEW_RESULT_WRITTEN",
                    timestamp=datetime.now().astimezone(),
                    payload={"review_result": result},
                )
            )


def build_virtual_improvement_review_result(
    review_input: VirtualImprovementReviewInput,
) -> VirtualImprovementReviewResult:
    """Build a deterministic research-only follow-up action from a validated handoff."""
    has_blockers = bool(review_input.blocker_refs)
    outcome = (
        VirtualImprovementReviewOutcome.INVESTIGATION_REQUIRED
        if has_blockers
        else VirtualImprovementReviewOutcome.EXPERIMENT_PROPOSAL
    )
    recommended_experiment = (
        "Inspect blocker-linked evidence gaps, reconcile assurance findings, and keep "
        "the candidate research-only until the missing evidence is closed."
        if has_blockers
        else "Run the next bounded experiment using the queue assurance packet, "
        "cost-aware virtual evidence, and explicit regime notes before any promotion request."
    )
    evidence_gap_assessment = (
        "ASSURANCE_AND_INPUT_BLOCKERS_PRESENT"
        if has_blockers
        else "ASSURANCE_BASELINE_READY_FOR_BOUNDED_EXPERIMENT"
    )
    follow_up_artifact_refs = (
        (
            "runtime/artifacts/user_reports/virtual_improvement_reviews/"
            f"{review_input.surface_kind.lower()}_virtual_improvement_review_latest.json"
        ),
        (
            "runtime/reports/virtual_improvement_reviews/"
            f"{review_input.surface_kind.lower()}_virtual_improvement_review_latest.md"
        ),
    )
    return VirtualImprovementReviewResult(
        review_id=f"virtual-improvement-review:{review_input.handoff_id}",
        handoff_id=review_input.handoff_id,
        snapshot_id=review_input.snapshot_id,
        surface_kind=review_input.surface_kind,
        outcome=outcome,
        recommended_experiment=recommended_experiment,
        evidence_gap_assessment=evidence_gap_assessment,
        assurance_artifact_refs=review_input.assurance_artifact_refs,
        evidence_refs=tuple(
            dict.fromkeys(
                (
                    *review_input.evidence_refs,
                    *review_input.assurance_artifact_refs,
                    *follow_up_artifact_refs,
                )
            )
        ),
        follow_up_artifact_refs=follow_up_artifact_refs,
        blockers=review_input.blocker_refs,
    )


@dataclass(frozen=True, slots=True)
class HypothesisRegistry:
    """Immutable registry; persistence is append-only through an optional ledger."""

    hypotheses: tuple[ResearchHypothesis, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(self, hypothesis: ResearchHypothesis) -> HypothesisRegistry:
        if any(
            item.hypothesis_id == hypothesis.hypothesis_id for item in self.hypotheses
        ):
            raise ValueError("hypothesis ID already exists")
        self._record("HYPOTHESIS_CREATED", hypothesis)
        return HypothesisRegistry((*self.hypotheses, hypothesis), self.ledger)

    def update(self, hypothesis: ResearchHypothesis) -> HypothesisRegistry:
        matches = tuple(
            index
            for index, item in enumerate(self.hypotheses)
            if item.hypothesis_id == hypothesis.hypothesis_id
        )
        if len(matches) != 1:
            raise KeyError(hypothesis.hypothesis_id)
        items = list(self.hypotheses)
        items[matches[0]] = hypothesis
        self._record("HYPOTHESIS_TRANSITIONED", hypothesis)
        return HypothesisRegistry(tuple(items), self.ledger)

    def get(self, hypothesis_id: str) -> ResearchHypothesis:
        matches = tuple(
            item for item in self.hypotheses if item.hypothesis_id == hypothesis_id
        )
        if len(matches) != 1:
            raise KeyError(hypothesis_id)
        return matches[0]

    def _record(self, event_type: str, hypothesis: ResearchHypothesis) -> None:
        if self.ledger is None:
            return
        self.ledger.append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=hypothesis.updated_at,
                payload={"hypothesis": hypothesis},
            )
        )


@dataclass(frozen=True, slots=True)
class VirtualImprovementExperimentProposal:
    """Research-only next-step dossier derived from a virtual improvement review."""

    proposal_id: str
    review_id: str
    snapshot_id: str
    surface_kind: str
    objective: str
    recommended_experiment: str
    required_data: tuple[str, ...]
    evidence_gap_assessment: str
    source_artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    priority: str = "P1"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            proposal_id=self.proposal_id,
            review_id=self.review_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            objective=self.objective,
            recommended_experiment=self.recommended_experiment,
            evidence_gap_assessment=self.evidence_gap_assessment,
            priority=self.priority,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement experiment proposal surface kind is invalid"
            )
        if self.priority not in {"P0", "P1"}:
            raise ValueError(
                "virtual improvement experiment proposal priority is invalid"
            )
        if not self.required_data:
            raise ValueError("virtual improvement experiment proposal requires data")
        if len(set(self.required_data)) != len(self.required_data):
            raise ValueError(
                "virtual improvement experiment proposal required data must be unique"
            )
        if len(set(self.source_artifact_refs)) != len(self.source_artifact_refs):
            raise ValueError(
                "virtual improvement experiment proposal source refs must be unique"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement experiment proposal cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "review_id": self.review_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "objective": self.objective,
            "recommended_experiment": self.recommended_experiment,
            "required_data": self.required_data,
            "evidence_gap_assessment": self.evidence_gap_assessment,
            "source_artifact_refs": self.source_artifact_refs,
            "blockers": self.blockers,
            "priority": self.priority,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


def build_virtual_improvement_experiment_proposal(
    review_result: VirtualImprovementReviewResult,
) -> VirtualImprovementExperimentProposal:
    """Turn a review result into a bounded experiment dossier."""
    required_data: tuple[str, ...] = (
        (
            "Queue assurance JSON/Markdown artifacts linked from the virtual "
            "improvement handoff."
        ),
        "Virtual evidence report with cost-aware telemetry and DGE observations.",
        "Regime-specific notes explaining where the candidate wins, loses, or remains uncertain.",
    )
    if review_result.blockers:
        required_data = (
            *required_data,
            "Missing or insufficient evidence required to close the active blockers.",
        )
    return VirtualImprovementExperimentProposal(
        proposal_id=f"virtual-improvement-experiment:{review_result.review_id}",
        review_id=review_result.review_id,
        snapshot_id=review_result.snapshot_id,
        surface_kind=review_result.surface_kind,
        objective=(
            "Run the next bounded research experiment without granting paper or live "
            "authority."
        ),
        recommended_experiment=review_result.recommended_experiment,
        required_data=required_data,
        evidence_gap_assessment=review_result.evidence_gap_assessment,
        source_artifact_refs=tuple(
            dict.fromkeys(
                (
                    *review_result.assurance_artifact_refs,
                    *review_result.follow_up_artifact_refs,
                )
            )
        ),
        blockers=review_result.blockers,
        priority="P1" if review_result.blockers else "P0",
    )


@dataclass(frozen=True, slots=True)
class VirtualImprovementExperimentTaskRecord:
    """Deterministic registry-ready task record for one bounded research experiment."""

    task_id: str
    proposal_id: str
    snapshot_id: str
    surface_kind: str
    objective: str
    required_data: tuple[str, ...]
    source_artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    priority: str = "P1"
    status: VirtualImprovementExperimentTaskStatus = (
        VirtualImprovementExperimentTaskStatus.QUEUED
    )
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            task_id=self.task_id,
            proposal_id=self.proposal_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            objective=self.objective,
            priority=self.priority,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement experiment task surface kind is invalid"
            )
        if self.priority not in {"P0", "P1"}:
            raise ValueError("virtual improvement experiment task priority is invalid")
        if not self.required_data:
            raise ValueError("virtual improvement experiment task requires data")
        if len(set(self.required_data)) != len(self.required_data):
            raise ValueError("virtual improvement experiment task data must be unique")
        if len(set(self.source_artifact_refs)) != len(self.source_artifact_refs):
            raise ValueError(
                "virtual improvement experiment task source refs must be unique"
            )
        expected_status = (
            VirtualImprovementExperimentTaskStatus.EVIDENCE_PENDING
            if self.blockers
            else VirtualImprovementExperimentTaskStatus.READY_FOR_RESEARCH
        )
        if self.status is not expected_status:
            raise ValueError(
                "virtual improvement experiment task status is inconsistent"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement experiment task cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "proposal_id": self.proposal_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "objective": self.objective,
            "required_data": self.required_data,
            "source_artifact_refs": self.source_artifact_refs,
            "blockers": self.blockers,
            "priority": self.priority,
            "status": self.status.value,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementExperimentTaskRegistry:
    """Immutable append/update registry for bounded virtual improvement tasks."""

    tasks: tuple[VirtualImprovementExperimentTaskRecord, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(
        self,
        task: VirtualImprovementExperimentTaskRecord,
    ) -> VirtualImprovementExperimentTaskRegistry:
        if any(item.task_id == task.task_id for item in self.tasks):
            raise ValueError("virtual improvement experiment task ID already exists")
        self._record("VIRTUAL_IMPROVEMENT_EXPERIMENT_TASK_CREATED", task)
        return VirtualImprovementExperimentTaskRegistry(
            (*self.tasks, task), self.ledger
        )

    def get(self, task_id: str) -> VirtualImprovementExperimentTaskRecord:
        matches = tuple(item for item in self.tasks if item.task_id == task_id)
        if len(matches) != 1:
            raise KeyError(task_id)
        return matches[0]

    def _record(
        self,
        event_type: str,
        task: VirtualImprovementExperimentTaskRecord,
    ) -> None:
        if self.ledger is None:
            return
        self.ledger.append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=datetime.now().astimezone(),
                payload={"task": task},
            )
        )


def build_virtual_improvement_experiment_task(
    proposal: VirtualImprovementExperimentProposal,
) -> VirtualImprovementExperimentTaskRecord:
    """Create a deterministic research task record from a bounded proposal."""
    return VirtualImprovementExperimentTaskRecord(
        task_id=f"virtual-improvement-task:{proposal.proposal_id}",
        proposal_id=proposal.proposal_id,
        snapshot_id=proposal.snapshot_id,
        surface_kind=proposal.surface_kind,
        objective=proposal.objective,
        required_data=proposal.required_data,
        source_artifact_refs=proposal.source_artifact_refs,
        blockers=proposal.blockers,
        priority=proposal.priority,
        status=(
            VirtualImprovementExperimentTaskStatus.EVIDENCE_PENDING
            if proposal.blockers
            else VirtualImprovementExperimentTaskStatus.READY_FOR_RESEARCH
        ),
    )


@dataclass(frozen=True, slots=True)
class VirtualImprovementExperimentTaskQueue:
    """Queue-level rollup for bounded virtual improvement research tasks."""

    queue_id: str
    snapshot_id: str
    surface_kind: str
    tasks: tuple[VirtualImprovementExperimentTaskRecord, ...]
    ready_task_count: int
    evidence_pending_task_count: int
    status: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement experiment task queue surface kind is invalid"
            )
        if not self.tasks:
            raise ValueError("virtual improvement experiment task queue requires tasks")
        if self.ready_task_count < 0 or self.evidence_pending_task_count < 0:
            raise ValueError(
                "virtual improvement experiment task queue counts cannot be negative"
            )
        if self.ready_task_count + self.evidence_pending_task_count != len(self.tasks):
            raise ValueError(
                "virtual improvement experiment task queue counts are inconsistent"
            )
        expected_status = (
            "READY_FOR_RESEARCH"
            if self.evidence_pending_task_count == 0
            else "EVIDENCE_PENDING"
        )
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement experiment task queue status is inconsistent"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement experiment task queue cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "ready_task_count": self.ready_task_count,
            "evidence_pending_task_count": self.evidence_pending_task_count,
            "task_count": len(self.tasks),
            "tasks": [task.to_payload() for task in self.tasks],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchWorkPlanner:
    """Operator-facing ordered plan built from one bounded task queue snapshot."""

    planner_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    selected_ready_task_ids: tuple[str, ...]
    escalated_task_ids: tuple[str, ...]
    next_safe_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            planner_id=self.planner_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError("virtual improvement planner surface kind is invalid")
        if self.status not in {"READY_PLAN", "EVIDENCE_ESCALATION_REQUIRED"}:
            raise ValueError("virtual improvement planner status is invalid")
        if len(set(self.selected_ready_task_ids)) != len(self.selected_ready_task_ids):
            raise ValueError(
                "virtual improvement planner ready task ids must be unique"
            )
        if len(set(self.escalated_task_ids)) != len(self.escalated_task_ids):
            raise ValueError(
                "virtual improvement planner escalated task ids must be unique"
            )
        if len(set(self.next_safe_actions)) != len(self.next_safe_actions):
            raise ValueError("virtual improvement planner actions must be unique")
        if not self.next_safe_actions:
            raise ValueError("virtual improvement planner requires next safe actions")
        expected_status = (
            "EVIDENCE_ESCALATION_REQUIRED" if self.escalated_task_ids else "READY_PLAN"
        )
        if self.status != expected_status:
            raise ValueError("virtual improvement planner status is inconsistent")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("virtual improvement planner cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "planner_id": self.planner_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "selected_ready_task_ids": self.selected_ready_task_ids,
            "escalated_task_ids": self.escalated_task_ids,
            "next_safe_actions": self.next_safe_actions,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementOperatorHandoffSummary:
    """Single-page operator/research handoff artifact derived from queue and planner."""

    summary_id: str
    planner_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    selected_task_briefs: tuple[str, ...]
    escalated_blocker_briefs: tuple[str, ...]
    next_safe_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            summary_id=self.summary_id,
            planner_id=self.planner_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement operator handoff surface kind is invalid"
            )
        if self.status not in {"READY_HANDOFF", "ESCALATION_HANDOFF"}:
            raise ValueError("virtual improvement operator handoff status is invalid")
        if len(set(self.selected_task_briefs)) != len(self.selected_task_briefs):
            raise ValueError(
                "virtual improvement operator handoff selected briefs must be unique"
            )
        if len(set(self.escalated_blocker_briefs)) != len(
            self.escalated_blocker_briefs
        ):
            raise ValueError(
                "virtual improvement operator handoff escalated briefs must be unique"
            )
        if len(set(self.next_safe_actions)) != len(self.next_safe_actions):
            raise ValueError(
                "virtual improvement operator handoff actions must be unique"
            )
        expected_status = (
            "ESCALATION_HANDOFF" if self.escalated_blocker_briefs else "READY_HANDOFF"
        )
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement operator handoff status is inconsistent"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement operator handoff cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "summary_id": self.summary_id,
            "planner_id": self.planner_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "selected_task_briefs": self.selected_task_briefs,
            "escalated_blocker_briefs": self.escalated_blocker_briefs,
            "next_safe_actions": self.next_safe_actions,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchExecutionInbox:
    """Single artifact answering what to do next for bounded research execution."""

    inbox_id: str
    summary_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    ready_work_items: tuple[str, ...]
    escalation_items: tuple[str, ...]
    next_safe_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            inbox_id=self.inbox_id,
            summary_id=self.summary_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement execution inbox surface kind is invalid"
            )
        if self.status not in {"READY_INBOX", "ESCALATION_INBOX"}:
            raise ValueError("virtual improvement execution inbox status is invalid")
        if len(set(self.ready_work_items)) != len(self.ready_work_items):
            raise ValueError(
                "virtual improvement execution inbox ready items must be unique"
            )
        if len(set(self.escalation_items)) != len(self.escalation_items):
            raise ValueError(
                "virtual improvement execution inbox escalation items must be unique"
            )
        if len(set(self.next_safe_actions)) != len(self.next_safe_actions):
            raise ValueError(
                "virtual improvement execution inbox actions must be unique"
            )
        if not self.next_safe_actions:
            raise ValueError(
                "virtual improvement execution inbox requires next safe actions"
            )
        expected_status = "ESCALATION_INBOX" if self.escalation_items else "READY_INBOX"
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement execution inbox status is inconsistent"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement execution inbox cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "inbox_id": self.inbox_id,
            "summary_id": self.summary_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "ready_work_items": self.ready_work_items,
            "escalation_items": self.escalation_items,
            "next_safe_actions": self.next_safe_actions,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchExecutionSessionManifest:
    """Single-session bounded execution plan derived from the research inbox."""

    manifest_id: str
    inbox_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    chosen_ready_item: str | None
    escalation_items: tuple[str, ...]
    action_order: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            manifest_id=self.manifest_id,
            inbox_id=self.inbox_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement session manifest surface kind is invalid"
            )
        if self.status not in {"READY_SESSION", "ESCALATION_SESSION"}:
            raise ValueError("virtual improvement session manifest status is invalid")
        if self.chosen_ready_item is not None and not self.chosen_ready_item.strip():
            raise ValueError(
                "virtual improvement session manifest ready item is invalid"
            )
        if len(set(self.escalation_items)) != len(self.escalation_items):
            raise ValueError(
                "virtual improvement session manifest escalation items must be unique"
            )
        if len(set(self.action_order)) != len(self.action_order):
            raise ValueError(
                "virtual improvement session manifest actions must be unique"
            )
        if len(set(self.artifact_refs)) != len(self.artifact_refs):
            raise ValueError(
                "virtual improvement session manifest artifact refs must be unique"
            )
        if not self.action_order or not self.artifact_refs:
            raise ValueError(
                "virtual improvement session manifest requires actions and artifacts"
            )
        expected_status = (
            "ESCALATION_SESSION" if self.escalation_items else "READY_SESSION"
        )
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement session manifest status is inconsistent"
            )
        if expected_status == "READY_SESSION" and self.chosen_ready_item is None:
            raise ValueError("ready session manifest requires a chosen ready item")
        if (
            expected_status == "ESCALATION_SESSION"
            and self.chosen_ready_item is not None
        ):
            raise ValueError("escalation session manifest cannot select a ready item")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement session manifest cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "inbox_id": self.inbox_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "chosen_ready_item": self.chosen_ready_item,
            "escalation_items": self.escalation_items,
            "action_order": self.action_order,
            "artifact_refs": self.artifact_refs,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchSessionJournal:
    """Single-session research audit trail derived from the session manifest."""

    journal_id: str
    manifest_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    chosen_ready_item: str | None
    escalation_items: tuple[str, ...]
    consumed_action_order: tuple[str, ...]
    closure_result: str
    artifact_refs: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            journal_id=self.journal_id,
            manifest_id=self.manifest_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            closure_result=self.closure_result,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement session journal surface kind is invalid"
            )
        if self.status not in {"READY_JOURNAL", "ESCALATION_JOURNAL"}:
            raise ValueError("virtual improvement session journal status is invalid")
        if self.chosen_ready_item is not None and not self.chosen_ready_item.strip():
            raise ValueError(
                "virtual improvement session journal ready item is invalid"
            )
        if len(set(self.escalation_items)) != len(self.escalation_items):
            raise ValueError(
                "virtual improvement session journal escalation items must be unique"
            )
        if len(set(self.consumed_action_order)) != len(self.consumed_action_order):
            raise ValueError(
                "virtual improvement session journal actions must be unique"
            )
        if len(set(self.artifact_refs)) != len(self.artifact_refs):
            raise ValueError(
                "virtual improvement session journal artifact refs must be unique"
            )
        if not self.consumed_action_order or not self.artifact_refs:
            raise ValueError(
                "virtual improvement session journal requires actions and artifacts"
            )
        expected_status = (
            "ESCALATION_JOURNAL" if self.escalation_items else "READY_JOURNAL"
        )
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement session journal status is inconsistent"
            )
        if expected_status == "READY_JOURNAL":
            if self.chosen_ready_item is None:
                raise ValueError("ready session journal requires a chosen ready item")
            if self.closure_result != "READY_ITEM_SELECTED_FOR_RESEARCH":
                raise ValueError("ready session journal closure result is invalid")
        elif self.closure_result != "ESCALATION_REQUIRED_BEFORE_RESEARCH":
            raise ValueError("escalation session journal closure result is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement session journal cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "journal_id": self.journal_id,
            "manifest_id": self.manifest_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "chosen_ready_item": self.chosen_ready_item,
            "escalation_items": self.escalation_items,
            "consumed_action_order": self.consumed_action_order,
            "closure_result": self.closure_result,
            "artifact_refs": self.artifact_refs,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchSessionClosureRecord:
    """Final research-only closure record derived from one session journal."""

    closure_id: str
    journal_id: str
    manifest_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    chosen_ready_item: str | None
    escalation_items: tuple[str, ...]
    completed_actions: tuple[str, ...]
    produced_artifact_refs: tuple[str, ...]
    closure_reason: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            closure_id=self.closure_id,
            journal_id=self.journal_id,
            manifest_id=self.manifest_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            closure_reason=self.closure_reason,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement session closure surface kind is invalid"
            )
        if self.status not in {
            "COMPLETED_RESEARCH_ONLY",
            "ESCALATED_RESEARCH_ONLY",
        }:
            raise ValueError("virtual improvement session closure status is invalid")
        if self.chosen_ready_item is not None and not self.chosen_ready_item.strip():
            raise ValueError(
                "virtual improvement session closure ready item is invalid"
            )
        if len(set(self.escalation_items)) != len(self.escalation_items):
            raise ValueError(
                "virtual improvement session closure escalation items must be unique"
            )
        if len(set(self.completed_actions)) != len(self.completed_actions):
            raise ValueError(
                "virtual improvement session closure actions must be unique"
            )
        if len(set(self.produced_artifact_refs)) != len(self.produced_artifact_refs):
            raise ValueError(
                "virtual improvement session closure artifacts must be unique"
            )
        if not self.completed_actions or not self.produced_artifact_refs:
            raise ValueError(
                "virtual improvement session closure requires actions and artifacts"
            )
        expected_status = (
            "ESCALATED_RESEARCH_ONLY"
            if self.escalation_items
            else "COMPLETED_RESEARCH_ONLY"
        )
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement session closure status is inconsistent"
            )
        if expected_status == "COMPLETED_RESEARCH_ONLY":
            if self.chosen_ready_item is None:
                raise ValueError(
                    "completed research closure requires a chosen ready item"
                )
            if self.closure_reason != "BOUNDED_RESEARCH_SESSION_RECORDED":
                raise ValueError("completed research closure reason is invalid")
        elif self.closure_reason != "EVIDENCE_ESCALATION_RECORDED":
            raise ValueError("escalated research closure reason is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement session closure cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "closure_id": self.closure_id,
            "journal_id": self.journal_id,
            "manifest_id": self.manifest_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "chosen_ready_item": self.chosen_ready_item,
            "escalation_items": self.escalation_items,
            "completed_actions": self.completed_actions,
            "produced_artifact_refs": self.produced_artifact_refs,
            "closure_reason": self.closure_reason,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchSessionArtifactBundle:
    """Single publish surface combining manifest, journal and closure evidence."""

    bundle_id: str
    manifest_id: str
    journal_id: str
    closure_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    required_artifact_refs: tuple[str, ...]
    produced_artifact_refs: tuple[str, ...]
    missing_artifact_refs: tuple[str, ...]
    escalation_items: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            bundle_id=self.bundle_id,
            manifest_id=self.manifest_id,
            journal_id=self.journal_id,
            closure_id=self.closure_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement artifact bundle surface kind is invalid"
            )
        if self.status not in {
            "COMPLETE_BUNDLE",
            "ESCALATED_BUNDLE",
            "INCOMPLETE_BUNDLE",
        }:
            raise ValueError("virtual improvement artifact bundle status is invalid")
        if len(set(self.required_artifact_refs)) != len(self.required_artifact_refs):
            raise ValueError(
                "virtual improvement artifact bundle required refs must be unique"
            )
        if len(set(self.produced_artifact_refs)) != len(self.produced_artifact_refs):
            raise ValueError(
                "virtual improvement artifact bundle produced refs must be unique"
            )
        if len(set(self.missing_artifact_refs)) != len(self.missing_artifact_refs):
            raise ValueError(
                "virtual improvement artifact bundle missing refs must be unique"
            )
        if len(set(self.escalation_items)) != len(self.escalation_items):
            raise ValueError(
                "virtual improvement artifact bundle escalation items must be unique"
            )
        if not self.required_artifact_refs or not self.produced_artifact_refs:
            raise ValueError(
                "virtual improvement artifact bundle requires required and produced refs"
            )
        if not set(self.missing_artifact_refs).issubset(
            set(self.required_artifact_refs)
        ):
            raise ValueError(
                "virtual improvement artifact bundle missing refs must be a subset"
            )
        expected_status = (
            "INCOMPLETE_BUNDLE"
            if self.missing_artifact_refs
            else "ESCALATED_BUNDLE"
            if self.escalation_items
            else "COMPLETE_BUNDLE"
        )
        if self.status != expected_status:
            raise ValueError(
                "virtual improvement artifact bundle status is inconsistent"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement artifact bundle cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "manifest_id": self.manifest_id,
            "journal_id": self.journal_id,
            "closure_id": self.closure_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "required_artifact_refs": self.required_artifact_refs,
            "produced_artifact_refs": self.produced_artifact_refs,
            "missing_artifact_refs": self.missing_artifact_refs,
            "escalation_items": self.escalation_items,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchSessionReadinessSummary:
    """Operator-facing readiness verdict derived from one session bundle."""

    summary_id: str
    bundle_id: str
    closure_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    verdict: str
    status: str
    blocker_codes: tuple[str, ...]
    next_safe_handoff: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            summary_id=self.summary_id,
            bundle_id=self.bundle_id,
            closure_id=self.closure_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            verdict=self.verdict,
            status=self.status,
            next_safe_handoff=self.next_safe_handoff,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement readiness summary surface kind is invalid"
            )
        if self.verdict not in {
            "READY_FOR_NEXT_CANDIDATE",
            "EVIDENCE_GAP_REMAINING",
            "ESCALATION_REVIEW_REQUIRED",
        }:
            raise ValueError("virtual improvement readiness summary verdict is invalid")
        if self.status not in {
            "READY_SUMMARY",
            "BLOCKED_SUMMARY",
            "ESCALATION_SUMMARY",
        }:
            raise ValueError("virtual improvement readiness summary status is invalid")
        if len(set(self.blocker_codes)) != len(self.blocker_codes):
            raise ValueError(
                "virtual improvement readiness summary blocker codes must be unique"
            )
        expected_verdict = (
            "EVIDENCE_GAP_REMAINING"
            if "SESSION_ARTIFACT_GAP_REMAINING" in self.blocker_codes
            else "ESCALATION_REVIEW_REQUIRED"
            if "EVIDENCE_ESCALATION_REQUIRED" in self.blocker_codes
            else "READY_FOR_NEXT_CANDIDATE"
        )
        expected_status = (
            "BLOCKED_SUMMARY"
            if expected_verdict == "EVIDENCE_GAP_REMAINING"
            else "ESCALATION_SUMMARY"
            if expected_verdict == "ESCALATION_REVIEW_REQUIRED"
            else "READY_SUMMARY"
        )
        if self.verdict != expected_verdict or self.status != expected_status:
            raise ValueError(
                "virtual improvement readiness summary state is inconsistent"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement readiness summary cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "summary_id": self.summary_id,
            "bundle_id": self.bundle_id,
            "closure_id": self.closure_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "verdict": self.verdict,
            "status": self.status,
            "blocker_codes": self.blocker_codes,
            "next_safe_handoff": self.next_safe_handoff,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementNextCandidateIntakeHandoff:
    """Governed intake handoff for the next virtual improvement candidate."""

    handoff_id: str
    summary_id: str
    bundle_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    intake_decision: str
    blocker_codes: tuple[str, ...]
    required_follow_up: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            handoff_id=self.handoff_id,
            summary_id=self.summary_id,
            bundle_id=self.bundle_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            intake_decision=self.intake_decision,
            required_follow_up=self.required_follow_up,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement next candidate intake surface kind is invalid"
            )
        if self.status not in {"READY_INTAKE", "BLOCKED_INTAKE"}:
            raise ValueError(
                "virtual improvement next candidate intake status is invalid"
            )
        if self.intake_decision not in {"OPEN_NEXT_CANDIDATE", "HOLD_CURRENT_CYCLE"}:
            raise ValueError(
                "virtual improvement next candidate intake decision is invalid"
            )
        if len(set(self.blocker_codes)) != len(self.blocker_codes):
            raise ValueError(
                "virtual improvement next candidate intake blocker codes must be unique"
            )
        expected_ready = self.intake_decision == "OPEN_NEXT_CANDIDATE"
        if expected_ready:
            if self.status != "READY_INTAKE":
                raise ValueError("ready next candidate intake status is invalid")
            if self.blocker_codes:
                raise ValueError("ready next candidate intake cannot contain blockers")
            if self.required_follow_up != "REGISTER_NEXT_VIRTUAL_CANDIDATE":
                raise ValueError("ready next candidate intake follow-up is invalid")
        else:
            if self.status != "BLOCKED_INTAKE":
                raise ValueError("blocked next candidate intake status is invalid")
            if not self.blocker_codes:
                raise ValueError("blocked next candidate intake requires blockers")
            if self.required_follow_up not in {
                "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
                "REVIEW_ESCALATIONS_BEFORE_NEXT_CANDIDATE",
            }:
                raise ValueError("blocked next candidate intake follow-up is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement next candidate intake cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "handoff_id": self.handoff_id,
            "summary_id": self.summary_id,
            "bundle_id": self.bundle_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "intake_decision": self.intake_decision,
            "blocker_codes": self.blocker_codes,
            "required_follow_up": self.required_follow_up,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementNextCandidateRegistrationPacket:
    """Ready-only registration packet for the next virtual improvement candidate."""

    packet_id: str
    handoff_id: str
    summary_id: str
    bundle_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    candidate_reference: str
    provenance_refs: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            packet_id=self.packet_id,
            handoff_id=self.handoff_id,
            summary_id=self.summary_id,
            bundle_id=self.bundle_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            candidate_reference=self.candidate_reference,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement registration packet surface kind is invalid"
            )
        if self.status != "REGISTER_NEXT_CANDIDATE":
            raise ValueError(
                "virtual improvement registration packet status is invalid"
            )
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise ValueError(
                "virtual improvement registration packet provenance refs must be unique"
            )
        if not self.provenance_refs:
            raise ValueError(
                "virtual improvement registration packet requires provenance refs"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement registration packet cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "packet_id": self.packet_id,
            "handoff_id": self.handoff_id,
            "summary_id": self.summary_id,
            "bundle_id": self.bundle_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "candidate_reference": self.candidate_reference,
            "provenance_refs": self.provenance_refs,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementNextCandidateRefusalArtifact:
    """Blocked-only refusal artifact for the next virtual improvement candidate."""

    artifact_id: str
    handoff_id: str
    summary_id: str
    bundle_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    blocker_codes: tuple[str, ...]
    refusal_reason: str
    required_follow_up: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            artifact_id=self.artifact_id,
            handoff_id=self.handoff_id,
            summary_id=self.summary_id,
            bundle_id=self.bundle_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            refusal_reason=self.refusal_reason,
            required_follow_up=self.required_follow_up,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement refusal artifact surface kind is invalid"
            )
        if self.status != "REFUSE_NEXT_CANDIDATE":
            raise ValueError("virtual improvement refusal artifact status is invalid")
        if len(set(self.blocker_codes)) != len(self.blocker_codes):
            raise ValueError(
                "virtual improvement refusal artifact blocker codes must be unique"
            )
        if not self.blocker_codes:
            raise ValueError("virtual improvement refusal artifact requires blockers")
        if self.required_follow_up not in {
            "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
            "REVIEW_ESCALATIONS_BEFORE_NEXT_CANDIDATE",
        }:
            raise ValueError(
                "virtual improvement refusal artifact follow-up is invalid"
            )
        if self.refusal_reason != "NEXT_CANDIDATE_NOT_READY":
            raise ValueError("virtual improvement refusal artifact reason is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement refusal artifact cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "handoff_id": self.handoff_id,
            "summary_id": self.summary_id,
            "bundle_id": self.bundle_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "blocker_codes": self.blocker_codes,
            "refusal_reason": self.refusal_reason,
            "required_follow_up": self.required_follow_up,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementCandidateRegistryEntry:
    """Append-only registry entry created from a ready registration packet."""

    entry_id: str
    packet_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    candidate_reference: str
    provenance_refs: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            entry_id=self.entry_id,
            packet_id=self.packet_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            candidate_reference=self.candidate_reference,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement candidate registry surface kind is invalid"
            )
        if self.status != "CANDIDATE_REGISTERED":
            raise ValueError("virtual improvement candidate registry status is invalid")
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise ValueError(
                "virtual improvement candidate registry provenance refs must be unique"
            )
        if not self.provenance_refs:
            raise ValueError(
                "virtual improvement candidate registry requires provenance refs"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement candidate registry cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "packet_id": self.packet_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "candidate_reference": self.candidate_reference,
            "provenance_refs": self.provenance_refs,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementRefusalLedgerEntry:
    """Append-only refusal ledger entry created from a blocked refusal artifact."""

    entry_id: str
    artifact_id: str
    queue_id: str
    snapshot_id: str
    surface_kind: str
    status: str
    blocker_codes: tuple[str, ...]
    refusal_reason: str
    required_follow_up: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            entry_id=self.entry_id,
            artifact_id=self.artifact_id,
            queue_id=self.queue_id,
            snapshot_id=self.snapshot_id,
            surface_kind=self.surface_kind,
            status=self.status,
            refusal_reason=self.refusal_reason,
            required_follow_up=self.required_follow_up,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement refusal ledger surface kind is invalid"
            )
        if self.status != "REFUSAL_RECORDED":
            raise ValueError("virtual improvement refusal ledger status is invalid")
        if len(set(self.blocker_codes)) != len(self.blocker_codes):
            raise ValueError(
                "virtual improvement refusal ledger blocker codes must be unique"
            )
        if not self.blocker_codes:
            raise ValueError("virtual improvement refusal ledger requires blockers")
        if self.refusal_reason != "NEXT_CANDIDATE_NOT_READY":
            raise ValueError("virtual improvement refusal ledger reason is invalid")
        if self.required_follow_up not in {
            "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
            "REVIEW_ESCALATIONS_BEFORE_NEXT_CANDIDATE",
        }:
            raise ValueError("virtual improvement refusal ledger follow-up is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement refusal ledger cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "artifact_id": self.artifact_id,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "status": self.status,
            "blocker_codes": self.blocker_codes,
            "refusal_reason": self.refusal_reason,
            "required_follow_up": self.required_follow_up,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementCandidateLifecycleSnapshot:
    """Single operator-facing snapshot of the latest candidate registration outcome."""

    snapshot_id: str
    queue_id: str
    source_kind: str
    surface_kind: str
    lifecycle_state: str
    subject_reference: str
    provenance_refs: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    required_follow_up: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            snapshot_id=self.snapshot_id,
            queue_id=self.queue_id,
            source_kind=self.source_kind,
            surface_kind=self.surface_kind,
            lifecycle_state=self.lifecycle_state,
            subject_reference=self.subject_reference,
            required_follow_up=self.required_follow_up,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement lifecycle snapshot surface kind is invalid"
            )
        if self.source_kind not in {"REGISTRY", "REFUSAL_LEDGER"}:
            raise ValueError(
                "virtual improvement lifecycle snapshot source kind is invalid"
            )
        if self.lifecycle_state not in {"REGISTERED", "REFUSED"}:
            raise ValueError("virtual improvement lifecycle snapshot state is invalid")
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise ValueError(
                "virtual improvement lifecycle snapshot provenance refs must be unique"
            )
        if len(set(self.blocker_codes)) != len(self.blocker_codes):
            raise ValueError(
                "virtual improvement lifecycle snapshot blocker codes must be unique"
            )
        if not self.provenance_refs:
            raise ValueError(
                "virtual improvement lifecycle snapshot requires provenance refs"
            )
        if self.source_kind == "REGISTRY":
            if self.lifecycle_state != "REGISTERED":
                raise ValueError("registry lifecycle snapshot state is invalid")
            if self.blocker_codes:
                raise ValueError(
                    "registered lifecycle snapshot cannot contain blockers"
                )
            if self.required_follow_up != "MONITOR_REGISTERED_CANDIDATE":
                raise ValueError("registered lifecycle snapshot follow-up is invalid")
        else:
            if self.lifecycle_state != "REFUSED":
                raise ValueError("refusal lifecycle snapshot state is invalid")
            if not self.blocker_codes:
                raise ValueError("refused lifecycle snapshot requires blockers")
            if self.required_follow_up not in {
                "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
                "REVIEW_ESCALATIONS_BEFORE_NEXT_CANDIDATE",
            }:
                raise ValueError("refused lifecycle snapshot follow-up is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement lifecycle snapshot cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "queue_id": self.queue_id,
            "source_kind": self.source_kind,
            "surface_kind": self.surface_kind,
            "lifecycle_state": self.lifecycle_state,
            "subject_reference": self.subject_reference,
            "provenance_refs": self.provenance_refs,
            "blocker_codes": self.blocker_codes,
            "required_follow_up": self.required_follow_up,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementCandidateOutcomeDashboardPayload:
    """Compact operator dashboard payload derived from one lifecycle snapshot."""

    dashboard_id: str
    lifecycle_snapshot_id: str
    queue_id: str
    surface_kind: str
    outcome_state: str
    blocker_count: int
    provenance_count: int
    follow_up_category: str
    subject_reference: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            dashboard_id=self.dashboard_id,
            lifecycle_snapshot_id=self.lifecycle_snapshot_id,
            queue_id=self.queue_id,
            surface_kind=self.surface_kind,
            outcome_state=self.outcome_state,
            follow_up_category=self.follow_up_category,
            subject_reference=self.subject_reference,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement outcome dashboard surface kind is invalid"
            )
        if self.outcome_state not in {"REGISTERED", "REFUSED"}:
            raise ValueError("virtual improvement outcome dashboard state is invalid")
        if self.follow_up_category not in {
            "MONITORING",
            "ARTIFACT_GAP_CLOSURE",
            "ESCALATION_REVIEW",
        }:
            raise ValueError(
                "virtual improvement outcome dashboard follow-up category is invalid"
            )
        if self.blocker_count < 0 or self.provenance_count <= 0:
            raise ValueError("virtual improvement outcome dashboard counts are invalid")
        expected_category = (
            "MONITORING"
            if self.outcome_state == "REGISTERED"
            else "ARTIFACT_GAP_CLOSURE"
            if self.blocker_count > 0 and self.follow_up_category != "ESCALATION_REVIEW"
            else "ESCALATION_REVIEW"
        )
        if self.follow_up_category != expected_category:
            raise ValueError(
                "virtual improvement outcome dashboard category is inconsistent"
            )
        if self.outcome_state == "REGISTERED" and self.blocker_count != 0:
            raise ValueError("registered outcome dashboard cannot report blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement outcome dashboard cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "dashboard_id": self.dashboard_id,
            "lifecycle_snapshot_id": self.lifecycle_snapshot_id,
            "queue_id": self.queue_id,
            "surface_kind": self.surface_kind,
            "outcome_state": self.outcome_state,
            "blocker_count": self.blocker_count,
            "provenance_count": self.provenance_count,
            "follow_up_category": self.follow_up_category,
            "subject_reference": self.subject_reference,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementCandidateCycleExecutiveSummary:
    """Compact executive summary derived from one candidate outcome dashboard."""

    summary_id: str
    dashboard_id: str
    queue_id: str
    surface_kind: str
    outcome_state: str
    summary_line: str
    next_action: str
    blocker_count: int
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            summary_id=self.summary_id,
            dashboard_id=self.dashboard_id,
            queue_id=self.queue_id,
            surface_kind=self.surface_kind,
            outcome_state=self.outcome_state,
            summary_line=self.summary_line,
            next_action=self.next_action,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement executive summary surface kind is invalid"
            )
        if self.outcome_state not in {"REGISTERED", "REFUSED"}:
            raise ValueError(
                "virtual improvement executive summary outcome state is invalid"
            )
        if self.blocker_count < 0:
            raise ValueError(
                "virtual improvement executive summary blocker count is invalid"
            )
        expected_next_action = (
            "MONITOR_REGISTERED_CANDIDATE"
            if self.outcome_state == "REGISTERED"
            else "CLOSE_ARTIFACT_GAPS_OR_REVIEW_ESCALATIONS"
        )
        if self.next_action != expected_next_action:
            raise ValueError(
                "virtual improvement executive summary next action is inconsistent"
            )
        if self.outcome_state == "REGISTERED" and self.blocker_count != 0:
            raise ValueError("registered executive summary cannot report blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement executive summary cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "summary_id": self.summary_id,
            "dashboard_id": self.dashboard_id,
            "queue_id": self.queue_id,
            "surface_kind": self.surface_kind,
            "outcome_state": self.outcome_state,
            "summary_line": self.summary_line,
            "next_action": self.next_action,
            "blocker_count": self.blocker_count,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


def build_virtual_improvement_experiment_task_queue(
    *,
    queue_id: str,
    snapshot_id: str,
    surface_kind: str,
    tasks: tuple[VirtualImprovementExperimentTaskRecord, ...],
) -> VirtualImprovementExperimentTaskQueue:
    """Aggregate bounded experiment tasks into one queue snapshot."""
    ready_task_count = sum(
        1
        for task in tasks
        if task.status is VirtualImprovementExperimentTaskStatus.READY_FOR_RESEARCH
    )
    evidence_pending_task_count = sum(
        1
        for task in tasks
        if task.status is VirtualImprovementExperimentTaskStatus.EVIDENCE_PENDING
    )
    return VirtualImprovementExperimentTaskQueue(
        queue_id=queue_id,
        snapshot_id=snapshot_id,
        surface_kind=surface_kind,
        tasks=tasks,
        ready_task_count=ready_task_count,
        evidence_pending_task_count=evidence_pending_task_count,
        status=(
            "READY_FOR_RESEARCH"
            if evidence_pending_task_count == 0
            else "EVIDENCE_PENDING"
        ),
    )


def build_virtual_improvement_research_work_planner(
    queue: VirtualImprovementExperimentTaskQueue,
) -> VirtualImprovementResearchWorkPlanner:
    """Build an ordered operator/research handoff plan from one queue snapshot."""
    selected_ready_task_ids = tuple(
        task.task_id
        for task in queue.tasks
        if task.status is VirtualImprovementExperimentTaskStatus.READY_FOR_RESEARCH
    )
    escalated_task_ids = tuple(
        task.task_id
        for task in queue.tasks
        if task.status is VirtualImprovementExperimentTaskStatus.EVIDENCE_PENDING
    )
    next_safe_actions = []
    if selected_ready_task_ids:
        next_safe_actions.append("START_BOUNDED_RESEARCH_EXPERIMENT")
        next_safe_actions.append("REVIEW_QUEUE_ASSURANCE_AND_REVIEW_ARTIFACTS")
    if escalated_task_ids:
        next_safe_actions.append("ESCALATE_MISSING_EVIDENCE")
        next_safe_actions.append("CLOSE_BLOCKERS_BEFORE_EXPERIMENT")
    if not next_safe_actions:
        next_safe_actions.append("KEEP_RESEARCH_QUEUE_VISIBLE")
    return VirtualImprovementResearchWorkPlanner(
        planner_id=f"virtual-improvement-planner:{queue.queue_id}",
        queue_id=queue.queue_id,
        snapshot_id=queue.snapshot_id,
        surface_kind=queue.surface_kind,
        status=("EVIDENCE_ESCALATION_REQUIRED" if escalated_task_ids else "READY_PLAN"),
        selected_ready_task_ids=selected_ready_task_ids,
        escalated_task_ids=escalated_task_ids,
        next_safe_actions=tuple(next_safe_actions),
    )


def build_virtual_improvement_operator_handoff_summary(
    *,
    queue: VirtualImprovementExperimentTaskQueue,
    planner: VirtualImprovementResearchWorkPlanner,
) -> VirtualImprovementOperatorHandoffSummary:
    """Build a compact human-facing handoff from the queue and planner."""
    task_index = {task.task_id: task for task in queue.tasks}
    selected_task_briefs = tuple(
        (
            f"{task_id}: {task_index[task_id].status.value} / "
            f"{task_index[task_id].priority}"
        )
        for task_id in planner.selected_ready_task_ids
    )
    escalated_blocker_briefs = tuple(
        (
            f"{task_id}: "
            f"{', '.join(task_index[task_id].blockers) or 'NO_BLOCKER_METADATA'}"
        )
        for task_id in planner.escalated_task_ids
    )
    return VirtualImprovementOperatorHandoffSummary(
        summary_id=f"virtual-improvement-handoff:{planner.planner_id}",
        planner_id=planner.planner_id,
        queue_id=queue.queue_id,
        snapshot_id=queue.snapshot_id,
        surface_kind=queue.surface_kind,
        status=("ESCALATION_HANDOFF" if escalated_blocker_briefs else "READY_HANDOFF"),
        selected_task_briefs=selected_task_briefs,
        escalated_blocker_briefs=escalated_blocker_briefs,
        next_safe_actions=planner.next_safe_actions,
    )


def build_virtual_improvement_research_execution_inbox(
    summary: VirtualImprovementOperatorHandoffSummary,
) -> VirtualImprovementResearchExecutionInbox:
    """Build a single execution inbox from the operator handoff summary."""
    return VirtualImprovementResearchExecutionInbox(
        inbox_id=f"virtual-improvement-inbox:{summary.summary_id}",
        summary_id=summary.summary_id,
        queue_id=summary.queue_id,
        snapshot_id=summary.snapshot_id,
        surface_kind=summary.surface_kind,
        status=(
            "ESCALATION_INBOX" if summary.escalated_blocker_briefs else "READY_INBOX"
        ),
        ready_work_items=summary.selected_task_briefs,
        escalation_items=summary.escalated_blocker_briefs,
        next_safe_actions=summary.next_safe_actions,
    )


def build_virtual_improvement_research_execution_session_manifest(
    inbox: VirtualImprovementResearchExecutionInbox,
) -> VirtualImprovementResearchExecutionSessionManifest:
    """Build a one-session bounded execution plan from the research inbox."""
    chosen_ready_item = (
        None
        if inbox.escalation_items
        else inbox.ready_work_items[0]
        if inbox.ready_work_items
        else None
    )
    if not inbox.escalation_items and chosen_ready_item is None:
        raise ValueError("ready session manifest requires at least one ready item")
    artifact_refs = (
        f"research-inbox:{inbox.inbox_id}",
        f"research-queue:{inbox.queue_id}",
        *(f"ready-item:{item}" for item in inbox.ready_work_items),
        *(f"escalation-item:{item}" for item in inbox.escalation_items),
    )
    return VirtualImprovementResearchExecutionSessionManifest(
        manifest_id=f"virtual-improvement-session:{inbox.inbox_id}",
        inbox_id=inbox.inbox_id,
        queue_id=inbox.queue_id,
        snapshot_id=inbox.snapshot_id,
        surface_kind=inbox.surface_kind,
        status=("ESCALATION_SESSION" if inbox.escalation_items else "READY_SESSION"),
        chosen_ready_item=chosen_ready_item,
        escalation_items=inbox.escalation_items,
        action_order=inbox.next_safe_actions,
        artifact_refs=artifact_refs,
    )


def build_virtual_improvement_research_session_journal(
    manifest: VirtualImprovementResearchExecutionSessionManifest,
) -> VirtualImprovementResearchSessionJournal:
    """Build a deterministic single-session research journal from the manifest."""
    closure_result = (
        "ESCALATION_REQUIRED_BEFORE_RESEARCH"
        if manifest.escalation_items
        else "READY_ITEM_SELECTED_FOR_RESEARCH"
    )
    artifact_refs = (
        f"research-session-manifest:{manifest.manifest_id}",
        f"research-queue:{manifest.queue_id}",
        *(f"consumed-action:{item}" for item in manifest.action_order),
        *(
            f"ready-item:{item}"
            for item in (
                ()
                if manifest.chosen_ready_item is None
                else (manifest.chosen_ready_item,)
            )
        ),
        *(f"escalation-item:{item}" for item in manifest.escalation_items),
    )
    return VirtualImprovementResearchSessionJournal(
        journal_id=f"virtual-improvement-session-journal:{manifest.manifest_id}",
        manifest_id=manifest.manifest_id,
        queue_id=manifest.queue_id,
        snapshot_id=manifest.snapshot_id,
        surface_kind=manifest.surface_kind,
        status=("ESCALATION_JOURNAL" if manifest.escalation_items else "READY_JOURNAL"),
        chosen_ready_item=manifest.chosen_ready_item,
        escalation_items=manifest.escalation_items,
        consumed_action_order=manifest.action_order,
        closure_result=closure_result,
        artifact_refs=artifact_refs,
    )


def build_virtual_improvement_research_session_closure_record(
    journal: VirtualImprovementResearchSessionJournal,
) -> VirtualImprovementResearchSessionClosureRecord:
    """Build a final fail-closed session closure record from one journal."""
    closure_reason = (
        "EVIDENCE_ESCALATION_RECORDED"
        if journal.escalation_items
        else "BOUNDED_RESEARCH_SESSION_RECORDED"
    )
    produced_artifact_refs = (
        f"research-session-journal:{journal.journal_id}",
        f"research-session-manifest:{journal.manifest_id}",
        f"research-queue:{journal.queue_id}",
        *(f"completed-action:{item}" for item in journal.consumed_action_order),
        *(
            f"ready-item:{item}"
            for item in (
                ()
                if journal.chosen_ready_item is None
                else (journal.chosen_ready_item,)
            )
        ),
        *(f"escalation-item:{item}" for item in journal.escalation_items),
    )
    return VirtualImprovementResearchSessionClosureRecord(
        closure_id=f"virtual-improvement-session-closure:{journal.journal_id}",
        journal_id=journal.journal_id,
        manifest_id=journal.manifest_id,
        queue_id=journal.queue_id,
        snapshot_id=journal.snapshot_id,
        surface_kind=journal.surface_kind,
        status=(
            "ESCALATED_RESEARCH_ONLY"
            if journal.escalation_items
            else "COMPLETED_RESEARCH_ONLY"
        ),
        chosen_ready_item=journal.chosen_ready_item,
        escalation_items=journal.escalation_items,
        completed_actions=journal.consumed_action_order,
        produced_artifact_refs=produced_artifact_refs,
        closure_reason=closure_reason,
    )


def build_virtual_improvement_research_session_artifact_bundle(
    *,
    manifest: VirtualImprovementResearchExecutionSessionManifest,
    journal: VirtualImprovementResearchSessionJournal,
    closure: VirtualImprovementResearchSessionClosureRecord,
) -> VirtualImprovementResearchSessionArtifactBundle:
    """Aggregate the bounded session evidence into one publishable bundle."""
    required_artifact_refs = tuple(
        dict.fromkeys(
            (
                *manifest.artifact_refs,
                *journal.artifact_refs,
                *closure.produced_artifact_refs,
            )
        )
    )
    produced_artifact_refs = tuple(
        dict.fromkeys(
            (
                f"research-session-manifest:{manifest.manifest_id}",
                f"research-session-journal:{journal.journal_id}",
                f"research-session-closure:{closure.closure_id}",
                *closure.produced_artifact_refs,
            )
        )
    )
    missing_artifact_refs = tuple(
        ref for ref in required_artifact_refs if ref not in set(produced_artifact_refs)
    )
    return VirtualImprovementResearchSessionArtifactBundle(
        bundle_id=f"virtual-improvement-session-bundle:{closure.closure_id}",
        manifest_id=manifest.manifest_id,
        journal_id=journal.journal_id,
        closure_id=closure.closure_id,
        queue_id=closure.queue_id,
        snapshot_id=closure.snapshot_id,
        surface_kind=closure.surface_kind,
        status=(
            "INCOMPLETE_BUNDLE"
            if missing_artifact_refs
            else "ESCALATED_BUNDLE"
            if closure.escalation_items
            else "COMPLETE_BUNDLE"
        ),
        required_artifact_refs=required_artifact_refs,
        produced_artifact_refs=produced_artifact_refs,
        missing_artifact_refs=missing_artifact_refs,
        escalation_items=closure.escalation_items,
    )


def build_virtual_improvement_research_session_readiness_summary(
    bundle: VirtualImprovementResearchSessionArtifactBundle,
) -> VirtualImprovementResearchSessionReadinessSummary:
    """Build a single operator-facing readiness verdict from one artifact bundle."""
    blocker_codes = tuple(
        dict.fromkeys(
            (
                *(
                    ()
                    if not bundle.missing_artifact_refs
                    else ("SESSION_ARTIFACT_GAP_REMAINING",)
                ),
                *(
                    ()
                    if not bundle.escalation_items
                    else ("EVIDENCE_ESCALATION_REQUIRED",)
                ),
            )
        )
    )
    verdict = (
        "EVIDENCE_GAP_REMAINING"
        if "SESSION_ARTIFACT_GAP_REMAINING" in blocker_codes
        else "ESCALATION_REVIEW_REQUIRED"
        if "EVIDENCE_ESCALATION_REQUIRED" in blocker_codes
        else "READY_FOR_NEXT_CANDIDATE"
    )
    status = (
        "BLOCKED_SUMMARY"
        if verdict == "EVIDENCE_GAP_REMAINING"
        else "ESCALATION_SUMMARY"
        if verdict == "ESCALATION_REVIEW_REQUIRED"
        else "READY_SUMMARY"
    )
    next_safe_handoff = (
        "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE"
        if verdict == "EVIDENCE_GAP_REMAINING"
        else "REVIEW_ESCALATIONS_BEFORE_NEXT_CANDIDATE"
        if verdict == "ESCALATION_REVIEW_REQUIRED"
        else "STAGE_NEXT_VIRTUAL_IMPROVEMENT_CANDIDATE"
    )
    return VirtualImprovementResearchSessionReadinessSummary(
        summary_id=f"virtual-improvement-session-readiness:{bundle.bundle_id}",
        bundle_id=bundle.bundle_id,
        closure_id=bundle.closure_id,
        queue_id=bundle.queue_id,
        snapshot_id=bundle.snapshot_id,
        surface_kind=bundle.surface_kind,
        verdict=verdict,
        status=status,
        blocker_codes=blocker_codes,
        next_safe_handoff=next_safe_handoff,
    )


def build_virtual_improvement_next_candidate_intake_handoff(
    summary: VirtualImprovementResearchSessionReadinessSummary,
) -> VirtualImprovementNextCandidateIntakeHandoff:
    """Build a fail-closed intake handoff for the next virtual candidate cycle."""
    ready = summary.verdict == "READY_FOR_NEXT_CANDIDATE"
    return VirtualImprovementNextCandidateIntakeHandoff(
        handoff_id=f"virtual-improvement-next-candidate:{summary.summary_id}",
        summary_id=summary.summary_id,
        bundle_id=summary.bundle_id,
        queue_id=summary.queue_id,
        snapshot_id=summary.snapshot_id,
        surface_kind=summary.surface_kind,
        status="READY_INTAKE" if ready else "BLOCKED_INTAKE",
        intake_decision="OPEN_NEXT_CANDIDATE" if ready else "HOLD_CURRENT_CYCLE",
        blocker_codes=() if ready else summary.blocker_codes,
        required_follow_up=(
            "REGISTER_NEXT_VIRTUAL_CANDIDATE" if ready else summary.next_safe_handoff
        ),
    )


def build_virtual_improvement_next_candidate_registration_packet(
    handoff: VirtualImprovementNextCandidateIntakeHandoff,
) -> VirtualImprovementNextCandidateRegistrationPacket:
    """Build the ready-only registration packet for the next candidate."""
    if handoff.status != "READY_INTAKE":
        raise ValueError(
            "next candidate registration packet requires READY_INTAKE handoff"
        )
    provenance_refs = (
        f"next-candidate-intake:{handoff.handoff_id}",
        f"session-readiness:{handoff.summary_id}",
        f"session-bundle:{handoff.bundle_id}",
        f"research-queue:{handoff.queue_id}",
    )
    return VirtualImprovementNextCandidateRegistrationPacket(
        packet_id=f"virtual-improvement-registration:{handoff.handoff_id}",
        handoff_id=handoff.handoff_id,
        summary_id=handoff.summary_id,
        bundle_id=handoff.bundle_id,
        queue_id=handoff.queue_id,
        snapshot_id=handoff.snapshot_id,
        surface_kind=handoff.surface_kind,
        status="REGISTER_NEXT_CANDIDATE",
        candidate_reference=f"next-candidate:{handoff.snapshot_id}",
        provenance_refs=provenance_refs,
    )


def build_virtual_improvement_next_candidate_refusal_artifact(
    handoff: VirtualImprovementNextCandidateIntakeHandoff,
) -> VirtualImprovementNextCandidateRefusalArtifact:
    """Build the blocked-only refusal artifact for the next candidate."""
    if handoff.status != "BLOCKED_INTAKE":
        raise ValueError(
            "next candidate refusal artifact requires BLOCKED_INTAKE handoff"
        )
    return VirtualImprovementNextCandidateRefusalArtifact(
        artifact_id=f"virtual-improvement-refusal:{handoff.handoff_id}",
        handoff_id=handoff.handoff_id,
        summary_id=handoff.summary_id,
        bundle_id=handoff.bundle_id,
        queue_id=handoff.queue_id,
        snapshot_id=handoff.snapshot_id,
        surface_kind=handoff.surface_kind,
        status="REFUSE_NEXT_CANDIDATE",
        blocker_codes=handoff.blocker_codes,
        refusal_reason="NEXT_CANDIDATE_NOT_READY",
        required_follow_up=handoff.required_follow_up,
    )


def build_virtual_improvement_candidate_registry_entry(
    packet: VirtualImprovementNextCandidateRegistrationPacket,
) -> VirtualImprovementCandidateRegistryEntry:
    """Build the append-only candidate registry entry from a ready packet."""
    return VirtualImprovementCandidateRegistryEntry(
        entry_id=f"virtual-improvement-candidate-registry:{packet.packet_id}",
        packet_id=packet.packet_id,
        queue_id=packet.queue_id,
        snapshot_id=packet.snapshot_id,
        surface_kind=packet.surface_kind,
        status="CANDIDATE_REGISTERED",
        candidate_reference=packet.candidate_reference,
        provenance_refs=packet.provenance_refs,
    )


def build_virtual_improvement_refusal_ledger_entry(
    artifact: VirtualImprovementNextCandidateRefusalArtifact,
) -> VirtualImprovementRefusalLedgerEntry:
    """Build the append-only refusal ledger entry from a refusal artifact."""
    return VirtualImprovementRefusalLedgerEntry(
        entry_id=f"virtual-improvement-refusal-ledger:{artifact.artifact_id}",
        artifact_id=artifact.artifact_id,
        queue_id=artifact.queue_id,
        snapshot_id=artifact.snapshot_id,
        surface_kind=artifact.surface_kind,
        status="REFUSAL_RECORDED",
        blocker_codes=artifact.blocker_codes,
        refusal_reason=artifact.refusal_reason,
        required_follow_up=artifact.required_follow_up,
    )


def build_virtual_improvement_candidate_lifecycle_snapshot_from_registry(
    entry: VirtualImprovementCandidateRegistryEntry,
) -> VirtualImprovementCandidateLifecycleSnapshot:
    """Build the latest lifecycle snapshot from a registered candidate entry."""
    return VirtualImprovementCandidateLifecycleSnapshot(
        snapshot_id=f"virtual-improvement-lifecycle:{entry.entry_id}",
        queue_id=entry.queue_id,
        source_kind="REGISTRY",
        surface_kind=entry.surface_kind,
        lifecycle_state="REGISTERED",
        subject_reference=entry.candidate_reference,
        provenance_refs=entry.provenance_refs,
        blocker_codes=(),
        required_follow_up="MONITOR_REGISTERED_CANDIDATE",
    )


def build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal(
    entry: VirtualImprovementRefusalLedgerEntry,
) -> VirtualImprovementCandidateLifecycleSnapshot:
    """Build the latest lifecycle snapshot from a refusal ledger entry."""
    return VirtualImprovementCandidateLifecycleSnapshot(
        snapshot_id=f"virtual-improvement-lifecycle:{entry.entry_id}",
        queue_id=entry.queue_id,
        source_kind="REFUSAL_LEDGER",
        surface_kind=entry.surface_kind,
        lifecycle_state="REFUSED",
        subject_reference=entry.artifact_id,
        provenance_refs=(f"refusal-ledger:{entry.entry_id}",),
        blocker_codes=entry.blocker_codes,
        required_follow_up=entry.required_follow_up,
    )


def build_virtual_improvement_candidate_outcome_dashboard_payload(
    snapshot: VirtualImprovementCandidateLifecycleSnapshot,
) -> VirtualImprovementCandidateOutcomeDashboardPayload:
    """Build a compact operator dashboard payload from one lifecycle snapshot."""
    follow_up_category = (
        "MONITORING"
        if snapshot.lifecycle_state == "REGISTERED"
        else "ARTIFACT_GAP_CLOSURE"
        if snapshot.required_follow_up
        == "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE"
        else "ESCALATION_REVIEW"
    )
    return VirtualImprovementCandidateOutcomeDashboardPayload(
        dashboard_id=f"virtual-improvement-outcome-dashboard:{snapshot.snapshot_id}",
        lifecycle_snapshot_id=snapshot.snapshot_id,
        queue_id=snapshot.queue_id,
        surface_kind=snapshot.surface_kind,
        outcome_state=snapshot.lifecycle_state,
        blocker_count=len(snapshot.blocker_codes),
        provenance_count=len(snapshot.provenance_refs),
        follow_up_category=follow_up_category,
        subject_reference=snapshot.subject_reference,
    )


def build_virtual_improvement_candidate_cycle_executive_summary(
    dashboard: VirtualImprovementCandidateOutcomeDashboardPayload,
) -> VirtualImprovementCandidateCycleExecutiveSummary:
    """Build a compact executive summary from one candidate outcome dashboard."""
    summary_line = (
        "The latest virtual improvement candidate cycle was registered for continued research monitoring."
        if dashboard.outcome_state == "REGISTERED"
        else "The latest virtual improvement candidate cycle was refused pending blocker closure or escalation review."
    )
    next_action = (
        "MONITOR_REGISTERED_CANDIDATE"
        if dashboard.outcome_state == "REGISTERED"
        else "CLOSE_ARTIFACT_GAPS_OR_REVIEW_ESCALATIONS"
    )
    return VirtualImprovementCandidateCycleExecutiveSummary(
        summary_id=f"virtual-improvement-executive-summary:{dashboard.dashboard_id}",
        dashboard_id=dashboard.dashboard_id,
        queue_id=dashboard.queue_id,
        surface_kind=dashboard.surface_kind,
        outcome_state=dashboard.outcome_state,
        summary_line=summary_line,
        next_action=next_action,
        blocker_count=dashboard.blocker_count,
    )


@dataclass(frozen=True, slots=True)
class ResearchRunCard:
    """Hash-linked evidence manifest for one reproducible research run."""

    run_id: str
    created_at: datetime
    symbol: str
    timeframe: str
    hypothesis_id: str
    dataset_sha256: str
    config_sha256: str
    strategy_sha256: str
    code_revision: str
    random_seed: int
    fee_rate: float
    slippage_rate: float
    metrics: tuple[tuple[str, float], ...]
    artifact_sha256: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            run_id=self.run_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            hypothesis_id=self.hypothesis_id,
            code_revision=self.code_revision,
        )
        _require_aware("run card created_at", self.created_at)
        hashes = (
            self.dataset_sha256,
            self.config_sha256,
            self.strategy_sha256,
            *(digest for _path, digest in self.artifact_sha256),
        )
        if any(
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in hashes
        ):
            raise ValueError("run-card hashes must be lowercase SHA-256")
        if self.random_seed < 0:
            raise ValueError("run-card random seed cannot be negative")
        numeric = (
            self.fee_rate,
            self.slippage_rate,
            *(value for _key, value in self.metrics),
        )
        if any(not isfinite(value) for value in numeric):
            raise ValueError("run-card numeric values must be finite")
        if min(self.fee_rate, self.slippage_rate) < 0.0:
            raise ValueError("run-card costs cannot be negative")
        metric_keys = tuple(key for key, _value in self.metrics)
        artifact_paths = tuple(path for path, _digest in self.artifact_sha256)
        if len(set(metric_keys)) != len(metric_keys):
            raise ValueError("run-card metric keys must be unique")
        if len(set(artifact_paths)) != len(artifact_paths):
            raise ValueError("run-card artifact paths must be unique")
        if self.promotion_status not in {"RESEARCH_ONLY", "STAGED_CANDIDATE"}:
            raise ValueError("run card cannot approve paper or live execution")
        if self.promotion_status == "STAGED_CANDIDATE" and self.blockers:
            raise ValueError("staged run card cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("run card cannot grant execution authority")

    @staticmethod
    def hash_json(value: Mapping[str, object]) -> str:
        """Return a stable hash for JSON-compatible configuration."""
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchRunCardWriter:
    """Atomically persist a run card and optionally append its audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, card: ResearchRunCard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(card)),
            blocker="RESEARCH_RUN_CARD_DESTINATION_VERIFY_FAILED",
            subject_id=card.run_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="RESEARCH_RUN_CARD_WRITTEN",
                    timestamp=card.created_at,
                    payload={"run_card": card},
                )
            )


_BLOCKER_GUIDANCE: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "WEAK_OOS_FOLD_CONSISTENCY": (
            "Rerun fold-level OOS diagnostics with regime split and checkpointed "
            "progress; do not lower promotion thresholds.",
            "Sealed HOTUSDT candles, fold metrics, regime labels, and cost "
            "assumptions.",
        ),
        "OOS_RETURN_INSUFFICIENT": (
            "Inspect setup quality and cost-adjusted expectancy before testing a "
            "narrower playbook variant.",
            "Walk-forward returns, buy-and-hold benchmark, and fee/slippage model.",
        ),
        "UNSTABLE_PARAMETER_SENSITIVITY": (
            "Expand local-neighborhood sensitivity checks around the selected "
            "candidate and reject brittle optima.",
            "Tuning grid, selected parameters, neighbor scores, and OOS folds.",
        ),
        "INSUFFICIENT_SENSITIVITY_NEIGHBORS": (
            "Add bounded neighboring parameter candidates before staging the setup.",
            "Approved tuning domains and adjacent parameter evaluations.",
        ),
        "COST_STRESS_RETURN_NOT_POSITIVE": (
            "Review spread, slippage, volume participation, and entry timing; keep "
            "the strategy research-only until stressed returns are positive.",
            "Backtest result, cost stress scenarios, spread and liquidity evidence.",
        ),
        "BOOTSTRAP_LOSS_PROBABILITY_HIGH": (
            "Run path-dependent trade-order diagnostics and look for edge "
            "concentration before changing parameters.",
            "Trade PnL sequence, bootstrap seed, and path Monte Carlo report.",
        ),
        "BOOTSTRAP_DRAWDOWN_EXCESSIVE": (
            "Stress protective exits and staged-exit rules; reject if tail "
            "drawdown remains excessive.",
            "Trade lifecycle records, drawdown path, stop and trailing review.",
        ),
        "LOW_STRESS_TRADE_COUNT": (
            "Collect more closed-candle history or narrow the setup definition "
            "only after preserving sample-size gates.",
            "Longer sealed dataset and stress-scenario trade counts.",
        ),
        "LOW_OOS_TRADE_COUNT": (
            "Increase validation horizon before interpreting expectancy.",
            "Longer OOS folds and trade-count distribution.",
        ),
        "INSUFFICIENT_REGIME_COVERAGE": (
            "Add explicit trend, range, and high-volatility regime coverage before "
            "promotion.",
            "Regime labels and per-regime OOS metrics.",
        ),
        "LEVEL_REACTION_EVIDENCE_INSUFFICIENT": (
            "Build reaction-statistics evidence for the zone using closed candles "
            "and ATR-buffered outcomes.",
            "Support/resistance zones, touch counts, reaction outcomes, and "
            "false-breakout records.",
        ),
        "INSUFFICIENT_VALIDATION_CANDLES": (
            "Archive more verified public Spot history before running promotion "
            "evidence.",
            "Checksum-verified OHLCV archive for the requested timeframe.",
        ),
        "HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED": (
            "Keep historical Spot SELL validation separate from naked-short logic; "
            "add inventory-aware replay before testing SELL playbooks.",
            "Historical inventory ledger, cost basis, and sell-only reduction rules.",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ResearchBlockerObservation:
    """One observed validation blocker with bounded occurrence count."""

    symbol: str
    timeframe: str
    playbook: str
    blocker: str
    count: int = 1

    def __post_init__(self) -> None:
        _require_identity(
            symbol=self.symbol,
            timeframe=self.timeframe,
            playbook=self.playbook,
            blocker=self.blocker,
        )
        if self.count < 1:
            raise ValueError("blocker observation count must be positive")


@dataclass(frozen=True, slots=True)
class ResearchBlockerAction:
    """Actionable research-only next step for one blocker class."""

    blocker: str
    occurrences: int
    affected_playbooks: tuple[str, ...]
    affected_timeframes: tuple[str, ...]
    recommended_experiment: str
    required_data: str
    status: str = "RESEARCH_ONLY"

    def __post_init__(self) -> None:
        _require_identity(
            blocker=self.blocker,
            recommended_experiment=self.recommended_experiment,
            required_data=self.required_data,
            status=self.status,
        )
        if self.occurrences < 1:
            raise ValueError("blocker occurrences must be positive")
        if not self.affected_playbooks or not self.affected_timeframes:
            raise ValueError("blocker action requires affected scope")
        if self.status != "RESEARCH_ONLY":
            raise ValueError("blocker actions cannot promote execution")


@dataclass(frozen=True, slots=True)
class ResearchBlockerDashboard:
    """Read-only OOS blocker dashboard with no trading authority."""

    dashboard_id: str
    created_at: datetime
    symbol: str
    actions: tuple[ResearchBlockerAction, ...]
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(dashboard_id=self.dashboard_id, symbol=self.symbol)
        _require_aware("blocker dashboard created_at", self.created_at)
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("blocker dashboard cannot promote research")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("blocker dashboard must remain live blocked")
        if self.execution_allowed:
            raise ValueError("blocker dashboard cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ResearchBlockerDashboardWriter:
    """Atomically persist a blocker dashboard and append an audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, dashboard: ResearchBlockerDashboard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(dashboard)),
            blocker="RESEARCH_BLOCKER_DASHBOARD_DESTINATION_VERIFY_FAILED",
            subject_id=dashboard.dashboard_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="RESEARCH_BLOCKER_DASHBOARD_WRITTEN",
                    timestamp=dashboard.created_at,
                    payload={"dashboard": dashboard},
                )
            )


def build_research_blocker_dashboard(
    *,
    dashboard_id: str,
    created_at: datetime,
    symbol: str,
    observations: tuple[ResearchBlockerObservation, ...],
) -> ResearchBlockerDashboard:
    """Convert validation blockers into deterministic research-only actions."""
    _require_aware("blocker dashboard created_at", created_at)
    grouped: dict[str, list[ResearchBlockerObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.blocker, []).append(observation)
    actions = tuple(
        _build_blocker_action(blocker, tuple(items))
        for blocker, items in sorted(grouped.items())
    )
    return ResearchBlockerDashboard(
        dashboard_id=dashboard_id,
        created_at=created_at,
        symbol=symbol.strip().upper(),
        actions=actions,
    )


def _build_blocker_action(
    blocker: str,
    observations: tuple[ResearchBlockerObservation, ...],
) -> ResearchBlockerAction:
    experiment, required_data = _BLOCKER_GUIDANCE.get(
        blocker,
        (
            "Inspect the blocker source, add a falsifiable regression fixture, "
            "and keep the candidate research-only.",
            "Source artifact, deterministic reproduction case, and validation log.",
        ),
    )
    return ResearchBlockerAction(
        blocker=blocker,
        occurrences=sum(item.count for item in observations),
        affected_playbooks=tuple(sorted({item.playbook for item in observations})),
        affected_timeframes=tuple(sorted({item.timeframe for item in observations})),
        recommended_experiment=experiment,
        required_data=required_data,
    )


@dataclass(frozen=True, slots=True)
class StrategyHealthSnapshot:
    """Point-in-time paper/OOS strategy health evidence."""

    strategy_id: str
    observed_at: datetime
    oos_trade_count: int
    expectancy: float
    profit_factor: float
    max_drawdown: float
    turnover: float
    regime_count: int

    def __post_init__(self) -> None:
        if (
            not self.strategy_id.strip()
            or self.oos_trade_count < 0
            or self.regime_count < 0
        ):
            raise ValueError("strategy health identity or counts are invalid")
        _require_aware("strategy health observed_at", self.observed_at)
        values = (self.expectancy, self.profit_factor, self.max_drawdown, self.turnover)
        if any(not isfinite(value) for value in values):
            raise ValueError("strategy health values must be finite")
        if min(self.max_drawdown, self.turnover) < 0.0:
            raise ValueError("strategy health risk values cannot be negative")


@dataclass(frozen=True, slots=True)
class DecayPolicy:
    """Conservative thresholds; automation may demote but never promote."""

    min_oos_trades: int = 20
    min_expectancy: float = 0.0
    min_profit_factor: float = 1.0
    max_drawdown: float = 0.25
    max_turnover: float = 0.25
    min_regime_count: int = 2
    warnings_for_monitoring: int = 2
    critical_for_decay: int = 2
    critical_for_disable: int = 3

    def __post_init__(self) -> None:
        counts = (
            self.min_oos_trades,
            self.min_regime_count,
            self.warnings_for_monitoring,
            self.critical_for_decay,
            self.critical_for_disable,
        )
        if any(value < 1 for value in counts):
            raise ValueError("decay policy counts must be positive")


@dataclass(frozen=True, slots=True)
class DecayDecision:
    """Demotion recommendation with no automatic recovery or promotion."""

    current_status: HypothesisStatus
    recommended_status: HypothesisStatus
    reason_codes: tuple[str, ...]
    human_reapproval_required: bool = True
    auto_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        if self.auto_promotion_allowed or not self.human_reapproval_required:
            raise ValueError("decay decisions cannot auto-promote")


@dataclass(frozen=True, slots=True)
class StrategyDecayEvaluator:
    """Evaluate consecutive weak evidence and recommend demotion only."""

    policy: DecayPolicy = DecayPolicy()

    def evaluate(
        self,
        current_status: HypothesisStatus,
        snapshots: tuple[StrategyHealthSnapshot, ...],
    ) -> DecayDecision:
        if not snapshots:
            return DecayDecision(
                current_status,
                current_status,
                ("STRATEGY_HEALTH_EVIDENCE_MISSING",),
            )
        reason_sets = tuple(self._reasons(item) for item in snapshots)
        weak = tuple(bool(reasons) for reasons in reason_sets)
        critical = tuple(self._critical(reasons) for reasons in reason_sets)
        recommended = current_status
        if current_status is HypothesisStatus.PAPER_APPROVED and self._tail_all(
            weak, self.policy.warnings_for_monitoring
        ):
            recommended = HypothesisStatus.MONITORING
        elif current_status is HypothesisStatus.MONITORING and self._tail_all(
            critical, self.policy.critical_for_decay
        ):
            recommended = HypothesisStatus.DECAYED
        elif current_status is HypothesisStatus.DECAYED and self._tail_all(
            critical, self.policy.critical_for_disable
        ):
            recommended = HypothesisStatus.DISABLED
        reasons = tuple(dict.fromkeys(code for items in reason_sets for code in items))
        return DecayDecision(current_status, recommended, reasons)

    def _reasons(self, item: StrategyHealthSnapshot) -> tuple[str, ...]:
        checks = (
            (item.oos_trade_count < self.policy.min_oos_trades, "DECAY_LOW_SAMPLE"),
            (item.expectancy <= self.policy.min_expectancy, "DECAY_EXPECTANCY"),
            (item.profit_factor < self.policy.min_profit_factor, "DECAY_PROFIT_FACTOR"),
            (item.max_drawdown > self.policy.max_drawdown, "DECAY_DRAWDOWN"),
            (item.turnover > self.policy.max_turnover, "DECAY_TURNOVER"),
            (item.regime_count < self.policy.min_regime_count, "DECAY_REGIME_COVERAGE"),
        )
        return tuple(code for failed, code in checks if failed)

    @staticmethod
    def _critical(reasons: tuple[str, ...]) -> bool:
        return any(
            code in {"DECAY_EXPECTANCY", "DECAY_DRAWDOWN", "DECAY_PROFIT_FACTOR"}
            for code in reasons
        )

    @staticmethod
    def _tail_all(values: tuple[bool, ...], count: int) -> bool:
        return len(values) >= count and all(values[-count:])

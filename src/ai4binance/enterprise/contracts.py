"""Typed, fail-closed enterprise work-management contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai4binance.governance.framework import ChangeApprovalClass


class DepartmentId(StrEnum):
    EXECUTIVE_OFFICE = "EXECUTIVE_OFFICE"
    BUSINESS_DEVELOPMENT = "BUSINESS_DEVELOPMENT"
    RESEARCH_DEVELOPMENT = "RESEARCH_DEVELOPMENT"
    SOFTWARE_ENGINEERING = "SOFTWARE_ENGINEERING"
    DATA_SUPPLY = "DATA_SUPPLY"
    MARKET_INTELLIGENCE = "MARKET_INTELLIGENCE"
    AGENT_FACTORY = "AGENT_FACTORY"
    QUALITY_AUDIT = "QUALITY_AUDIT"
    RISK_VALIDATION = "RISK_VALIDATION"
    TRADER = "TRADER"
    EDUCATION = "EDUCATION"
    FINANCE_PORTFOLIO = "FINANCE_PORTFOLIO"
    MULTI_OPS = "MULTI_OPS"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class WorkOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    READY_FOR_DEPARTMENT_REVIEW = "READY_FOR_DEPARTMENT_REVIEW"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class MeetingState(StrEnum):
    PREPARE = "PREPARE"
    COLLECT_DEPARTMENT_BRIEFS = "COLLECT_DEPARTMENT_BRIEFS"
    IDENTIFY_CONFLICTS = "IDENTIFY_CONFLICTS"
    CHALLENGE_ROUND = "CHALLENGE_ROUND"
    RISK_AND_QUALITY_REVIEW = "RISK_AND_QUALITY_REVIEW"
    DECIDE = "DECIDE"
    ASSIGN_ACTIONS = "ASSIGN_ACTIONS"
    MONITOR = "MONITOR"
    CLOSE_AND_REVIEW = "CLOSE_AND_REVIEW"


class OpinionVerdict(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED_FOR_RESEARCH = "APPROVED_FOR_RESEARCH"
    APPROVED_FOR_IMPLEMENTATION = "APPROVED_FOR_IMPLEMENTATION"
    REJECTED = "REJECTED"


OEK_AUTHORITY_SOURCE = (
    "OEK_AUTHORITY_SOURCE:docs/governance/policy_organization_constitution_handbook.md"
)
OEK_CONSTITUTION_CONTROL = "OEK_CONSTITUTION_COMPLIANCE"


def _require_identity(**values: str) -> None:
    missing = tuple(name for name, value in values.items() if not value.strip())
    if missing:
        raise ValueError(f"enterprise identity cannot be empty: {missing[0]}")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_fail_closed(
    *,
    execution_allowed: bool,
    live_eligibility_status: str,
    label: str,
) -> None:
    if execution_allowed or live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError(f"{label} cannot authorize live execution")


def _require_research_only(promotion_status: str, label: str) -> None:
    if promotion_status != "RESEARCH_ONLY":
        raise ValueError(f"{label} cannot promote production state")


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase sha256 hex digest")


@dataclass(frozen=True, slots=True)
class WorkflowIdentity:
    work_order_id: str
    run_id: str
    trace_id: str
    created_at: datetime
    snapshot_id: str = "SNAPSHOT_NOT_BOUND"
    code_commit: str = "WORKTREE_UNCOMMITTED"
    config_hash: str = "CONFIG_HASH_NOT_BOUND"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _require_identity(
            work_order_id=self.work_order_id,
            run_id=self.run_id,
            trace_id=self.trace_id,
            snapshot_id=self.snapshot_id,
            code_commit=self.code_commit,
            config_hash=self.config_hash,
            schema_version=self.schema_version,
        )
        _require_aware("workflow identity created_at", self.created_at)


@dataclass(frozen=True, slots=True)
class BoardDirective:
    identity: WorkflowIdentity
    directive_id: str
    requested_by: str
    objective: str
    constraints: tuple[str, ...]
    authority_scope: tuple[str, ...]
    resource_budget: str
    time_budget_seconds: int
    evidence_required: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            directive_id=self.directive_id,
            requested_by=self.requested_by,
            objective=self.objective,
            resource_budget=self.resource_budget,
        )
        _require_unique_text("directive constraints", self.constraints)
        _require_unique_text("directive authority scope", self.authority_scope)
        if OEK_AUTHORITY_SOURCE not in self.authority_scope:
            raise ValueError("board directive requires OEK authority source")
        if OEK_CONSTITUTION_CONTROL not in self.authority_scope:
            raise ValueError("board directive requires OEK constitution control")
        if self.time_budget_seconds < 1:
            raise ValueError("directive time budget must be positive")
        if not self.evidence_required:
            raise ValueError("board directive must require evidence")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="board directive",
        )


@dataclass(frozen=True, slots=True)
class ExecutiveWorkOrder:
    identity: WorkflowIdentity
    directive_id: str
    objective: str
    assigned_departments: tuple[DepartmentId, ...]
    priority: Priority
    status: WorkOrderStatus
    blockers: tuple[str, ...] = ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(directive_id=self.directive_id, objective=self.objective)
        if not self.assigned_departments:
            raise ValueError("work order requires assigned departments")
        if len(set(self.assigned_departments)) != len(self.assigned_departments):
            raise ValueError("work order departments must be unique")
        _require_unique_text("work order blockers", self.blockers)
        if (
            self.status
            in {
                WorkOrderStatus.HUMAN_REVIEW_REQUIRED,
                WorkOrderStatus.BLOCKED,
            }
            and not self.blockers
        ):
            raise ValueError("blocked work order requires blockers")
        _require_research_only(self.promotion_status, "work order")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="work order",
        )


@dataclass(frozen=True, slots=True)
class DepartmentTask:
    identity: WorkflowIdentity
    task_id: str
    department_id: DepartmentId
    department_manager_id: str
    purpose: str
    required_inputs: tuple[str, ...]
    output_schema: str
    depends_on: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.QUEUED
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            task_id=self.task_id,
            department_manager_id=self.department_manager_id,
            purpose=self.purpose,
            output_schema=self.output_schema,
        )
        _require_unique_text("department task inputs", self.required_inputs)
        _require_unique_text("department task dependencies", self.depends_on)
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="department task",
        )


@dataclass(frozen=True, slots=True)
class AgentTask:
    identity: WorkflowIdentity
    task_id: str
    department_id: DepartmentId
    department_manager_id: str
    agent_id: str
    tool_allowlist: tuple[str, ...]
    output_schema: str
    token_budget: int
    time_budget_seconds: int
    status: TaskStatus = TaskStatus.QUEUED
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            task_id=self.task_id,
            department_manager_id=self.department_manager_id,
            agent_id=self.agent_id,
            output_schema=self.output_schema,
        )
        _require_unique_text("agent task tool allowlist", self.tool_allowlist)
        if self.token_budget < 1 or self.time_budget_seconds < 1:
            raise ValueError("agent task budgets must be positive")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="agent task",
        )


@dataclass(frozen=True, slots=True)
class AgentResult:
    identity: WorkflowIdentity
    task_id: str
    agent_id: str
    status: TaskStatus
    summary: str
    evidence_refs: tuple[str, ...]
    output_schema: str
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",)
    payload_hash: str = "PAYLOAD_HASH_NOT_BOUND"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            task_id=self.task_id,
            agent_id=self.agent_id,
            summary=self.summary,
            output_schema=self.output_schema,
            payload_hash=self.payload_hash,
        )
        _require_unique_text("agent result evidence refs", self.evidence_refs)
        _require_unique_text("agent result blockers", self.blockers)
        _require_research_only(self.promotion_status, "agent result")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="agent result",
        )


@dataclass(frozen=True, slots=True)
class DepartmentBrief:
    identity: WorkflowIdentity
    brief_id: str
    department_id: DepartmentId
    department_manager_id: str
    key_findings: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    status: TaskStatus
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            brief_id=self.brief_id,
            department_manager_id=self.department_manager_id,
        )
        _require_unique_text("department brief findings", self.key_findings)
        _require_unique_text("department brief evidence refs", self.evidence_refs)
        _require_unique_text("department brief blockers", self.blockers)
        _require_research_only(self.promotion_status, "department brief")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="department brief",
        )


@dataclass(frozen=True, slots=True)
class InterdepartmentalQuestion:
    identity: WorkflowIdentity
    message_id: str
    sender_department_id: DepartmentId
    sender_manager_id: str
    recipient_department_id: DepartmentId
    recipient_manager_id: str
    question: str
    evidence_refs: tuple[str, ...]
    priority: Priority
    deadline: datetime
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            message_id=self.message_id,
            sender_manager_id=self.sender_manager_id,
            recipient_manager_id=self.recipient_manager_id,
            question=self.question,
        )
        _require_unique_text(
            "interdepartmental question evidence refs",
            self.evidence_refs,
        )
        _require_aware("interdepartmental question deadline", self.deadline)
        if self.sender_department_id is self.recipient_department_id:
            raise ValueError("interdepartmental question requires distinct departments")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="interdepartmental question",
        )


@dataclass(frozen=True, slots=True)
class InterdepartmentalResponse:
    identity: WorkflowIdentity
    message_id: str
    question_id: str
    sender_department_id: DepartmentId
    sender_manager_id: str
    recipient_department_id: DepartmentId
    recipient_manager_id: str
    response: str
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            message_id=self.message_id,
            question_id=self.question_id,
            sender_manager_id=self.sender_manager_id,
            recipient_manager_id=self.recipient_manager_id,
            response=self.response,
        )
        _require_unique_text(
            "interdepartmental response evidence refs",
            self.evidence_refs,
        )
        _require_unique_text("interdepartmental response blockers", self.blockers)
        if self.sender_department_id is self.recipient_department_id:
            raise ValueError("interdepartmental response requires distinct departments")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="interdepartmental response",
        )


@dataclass(frozen=True, slots=True)
class MeetingAgenda:
    identity: WorkflowIdentity
    meeting_id: str
    committee_id: str
    state: MeetingState
    participant_department_ids: tuple[DepartmentId, ...]
    agenda_items: tuple[str, ...]
    required_outputs: tuple[str, ...]
    max_rounds: int = 2
    max_department_statements: int = 1
    max_challenge_rounds: int = 1
    max_llm_calls: int = 4
    max_total_tokens: int = 8_000
    max_duration_seconds: int = 90
    local_llm_only: bool = True
    repeated_content_rejected: bool = True
    evidence_required: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(meeting_id=self.meeting_id, committee_id=self.committee_id)
        if len(set(self.participant_department_ids)) != len(
            self.participant_department_ids
        ):
            raise ValueError("meeting participants must be unique")
        if len(self.participant_department_ids) < 2:
            raise ValueError("meeting requires at least two departments")
        _require_unique_text("meeting agenda items", self.agenda_items)
        _require_unique_text("meeting required outputs", self.required_outputs)
        if not 1 <= self.max_rounds <= 2:
            raise ValueError("meeting max_rounds is outside budget")
        if not 1 <= self.max_department_statements <= 1:
            raise ValueError("meeting department statement budget is invalid")
        if not 0 <= self.max_challenge_rounds <= 1:
            raise ValueError("meeting challenge budget is invalid")
        if not 1 <= self.max_llm_calls <= 4:
            raise ValueError("meeting LLM call budget is invalid")
        if not 1 <= self.max_total_tokens <= 8_000:
            raise ValueError("meeting token budget is invalid")
        if not 1 <= self.max_duration_seconds <= 90:
            raise ValueError("meeting duration budget is invalid")
        if not (
            self.local_llm_only
            and self.repeated_content_rejected
            and self.evidence_required
        ):
            raise ValueError("meeting must remain local, bounded and evidence-backed")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="meeting agenda",
        )


@dataclass(frozen=True, slots=True)
class ChallengeRequest:
    identity: WorkflowIdentity
    challenge_id: str
    challenger_department_id: DepartmentId
    challenged_department_id: DepartmentId
    claim_ref: str
    challenge_reason: str
    evidence_refs: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            challenge_id=self.challenge_id,
            claim_ref=self.claim_ref,
            challenge_reason=self.challenge_reason,
        )
        _require_unique_text("challenge evidence refs", self.evidence_refs)
        if self.challenger_department_id is self.challenged_department_id:
            raise ValueError("challenge requires distinct departments")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="challenge request",
        )


@dataclass(frozen=True, slots=True)
class QualityOpinion:
    identity: WorkflowIdentity
    opinion_id: str
    reviewer_id: str
    subject_ref: str
    verdict: OpinionVerdict
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    finding_closed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            opinion_id=self.opinion_id,
            reviewer_id=self.reviewer_id,
            subject_ref=self.subject_ref,
        )
        _require_unique_text("quality evidence refs", self.evidence_refs)
        _require_unique_text("quality blockers", self.blockers)
        if self.finding_closed:
            raise ValueError("quality cannot close its own finding")
        _require_research_only(self.promotion_status, "quality opinion")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="quality opinion",
        )


@dataclass(frozen=True, slots=True)
class RiskOpinion:
    identity: WorkflowIdentity
    opinion_id: str
    reviewer_id: str
    subject_ref: str
    verdict: OpinionVerdict
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    vetoed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            opinion_id=self.opinion_id,
            reviewer_id=self.reviewer_id,
            subject_ref=self.subject_ref,
        )
        _require_unique_text("risk evidence refs", self.evidence_refs)
        _require_unique_text("risk blockers", self.blockers)
        if self.verdict is OpinionVerdict.REJECTED and not self.vetoed:
            raise ValueError("risk rejection must be represented as a veto")
        _require_research_only(self.promotion_status, "risk opinion")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="risk opinion",
        )


@dataclass(frozen=True, slots=True)
class OpsReadiness:
    identity: WorkflowIdentity
    readiness_id: str
    reviewer_id: str
    subject_ref: str
    verdict: OpinionVerdict
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            readiness_id=self.readiness_id,
            reviewer_id=self.reviewer_id,
            subject_ref=self.subject_ref,
        )
        _require_unique_text("ops evidence refs", self.evidence_refs)
        _require_unique_text("ops blockers", self.blockers)
        _require_research_only(self.promotion_status, "ops readiness")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="ops readiness",
        )


@dataclass(frozen=True, slots=True)
class ActionItem:
    identity: WorkflowIdentity
    action_id: str
    owner_department_id: DepartmentId
    owner_manager_id: str
    description: str
    due_at: datetime
    status: TaskStatus = TaskStatus.QUEUED
    evidence_refs: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            action_id=self.action_id,
            owner_manager_id=self.owner_manager_id,
            description=self.description,
        )
        _require_aware("action due_at", self.due_at)
        _require_unique_text("action evidence refs", self.evidence_refs)
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="action item",
        )


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    identity: WorkflowIdentity
    approval_id: str
    approver_id: str
    subject_ref: str
    status: ApprovalStatus
    evidence_refs: tuple[str, ...]
    approver_role: str = ""
    change_class: ChangeApprovalClass | None = None
    subject_sha256: str = ""
    scope_hash: str = ""
    quality_gate_evidence_sha256: str = ""
    governance_gate_evidence_sha256: str = ""
    evidence_hash: str = ""
    authority_family_sha256: str = ""
    lifecycle_definition_sha256: str = ""
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    principal_id: str = ""
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            approval_id=self.approval_id,
            approver_id=self.approver_id,
            subject_ref=self.subject_ref,
        )
        if self.principal_id and not self.principal_id.strip():
            raise ValueError("approval record principal_id cannot be blank")
        _require_unique_text("approval evidence refs", self.evidence_refs)
        if self.status is not ApprovalStatus.PENDING and not self.evidence_refs:
            raise ValueError("non-pending approval requires evidence")
        bound_approval = any(
            (
                self.approver_role.strip(),
                self.change_class is not None,
                self.subject_sha256,
                self.scope_hash,
                self.quality_gate_evidence_sha256,
                self.governance_gate_evidence_sha256,
                self.evidence_hash,
                self.authority_family_sha256,
                self.lifecycle_definition_sha256,
                self.approved_at is not None,
                self.expires_at is not None,
                self.revoked_at is not None,
            )
        )
        if bound_approval:
            if self.status not in {
                ApprovalStatus.APPROVED_FOR_RESEARCH,
                ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
            }:
                raise ValueError("bound approval record requires approved status")
            if not self.approver_role.strip():
                raise ValueError("bound approval record requires approver_role")
            if self.change_class is None:
                raise ValueError("bound approval record requires change_class")
            for name, value in (
                ("approval record subject_sha256", self.subject_sha256),
                ("approval record scope_hash", self.scope_hash),
                (
                    "approval record quality_gate_evidence_sha256",
                    self.quality_gate_evidence_sha256,
                ),
                (
                    "approval record governance_gate_evidence_sha256",
                    self.governance_gate_evidence_sha256,
                ),
            ):
                _require_sha256(name, value)
            for name, value in (
                ("approval record evidence_hash", self.evidence_hash),
                (
                    "approval record authority_family_sha256",
                    self.authority_family_sha256,
                ),
                (
                    "approval record lifecycle_definition_sha256",
                    self.lifecycle_definition_sha256,
                ),
            ):
                if value:
                    _require_sha256(name, value)
            if self.approved_at is None:
                raise ValueError("bound approval record requires approved_at")
            _require_aware("approval record approved_at", self.approved_at)
            if self.expires_at is not None:
                _require_aware("approval record expires_at", self.expires_at)
                if self.expires_at <= self.approved_at:
                    raise ValueError("approval record expiry must be after approval")
            if self.revoked_at is not None:
                _require_aware("approval record revoked_at", self.revoked_at)
                if self.revoked_at <= self.approved_at:
                    raise ValueError(
                        "approval record revocation must be after approval"
                    )
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="approval record",
        )


@dataclass(frozen=True, slots=True)
class ChangeProposal:
    identity: WorkflowIdentity
    proposal_id: str
    proposer_department_id: DepartmentId
    objective: str
    files_to_modify: tuple[str, ...]
    tests_required: tuple[str, ...]
    risk_notes: tuple[str, ...]
    status: ApprovalStatus = ApprovalStatus.PENDING
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(proposal_id=self.proposal_id, objective=self.objective)
        _require_unique_text("change proposal files", self.files_to_modify)
        _require_unique_text("change proposal tests", self.tests_required)
        _require_unique_text("change proposal risk notes", self.risk_notes)
        _require_research_only(self.promotion_status, "change proposal")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="change proposal",
        )


@dataclass(frozen=True, slots=True)
class LearningCandidate:
    identity: WorkflowIdentity
    candidate_id: str
    source_event_ref: str
    hypothesis: str
    required_validation: tuple[str, ...]
    status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            candidate_id=self.candidate_id,
            source_event_ref=self.source_event_ref,
            hypothesis=self.hypothesis,
        )
        _require_unique_text(
            "learning validation requirements",
            self.required_validation,
        )
        if self.status != "RESEARCH_ONLY":
            raise ValueError("learning candidate must remain research-only")
        _require_research_only(self.promotion_status, "learning candidate")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="learning candidate",
        )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    identity: WorkflowIdentity
    decision_id: str
    subject_ref: str
    verdict: str
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    user_approval_required: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            decision_id=self.decision_id,
            subject_ref=self.subject_ref,
            verdict=self.verdict,
        )
        _require_unique_text("promotion evidence refs", self.evidence_refs)
        _require_unique_text("promotion blockers", self.blockers)
        if not self.user_approval_required:
            raise ValueError("promotion decision requires user approval")
        if self.verdict not in {
            "RESEARCH_ONLY",
            "CHALLENGER",
            "SHADOW_APPROVED",
            "PAPER_SOAK_APPROVED",
            "PROMOTION_REJECTED",
            "READY_FOR_USER_APPROVAL",
        }:
            raise ValueError("promotion verdict is not governed")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="promotion decision",
        )


@dataclass(frozen=True, slots=True)
class AuditEvent:
    identity: WorkflowIdentity
    event_id: str
    event_type: str
    actor_id: str
    subject_ref: str
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",)
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_identity(
            event_id=self.event_id,
            event_type=self.event_type,
            actor_id=self.actor_id,
            subject_ref=self.subject_ref,
        )
        if self.event_type.upper() != self.event_type or " " in self.event_type:
            raise ValueError("audit event type must be uppercase snake case")
        _require_unique_text("audit evidence refs", self.evidence_refs)
        _require_unique_text("audit blockers", self.blockers)
        _require_research_only(self.promotion_status, "audit event")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            live_eligibility_status=self.live_eligibility_status,
            label="audit event",
        )

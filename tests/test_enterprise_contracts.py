from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.enterprise.contracts import (
    OEK_AUTHORITY_SOURCE,
    OEK_CONSTITUTION_CONTROL,
    ActionItem,
    AgentResult,
    AgentTask,
    ApprovalRecord,
    ApprovalStatus,
    AuditEvent,
    BoardDirective,
    ChallengeRequest,
    ChangeProposal,
    DepartmentBrief,
    DepartmentId,
    DepartmentTask,
    ExecutiveWorkOrder,
    InterdepartmentalQuestion,
    InterdepartmentalResponse,
    LearningCandidate,
    MeetingAgenda,
    MeetingState,
    OpinionVerdict,
    OpsReadiness,
    Priority,
    PromotionDecision,
    QualityOpinion,
    RiskOpinion,
    TaskStatus,
    WorkflowIdentity,
    WorkOrderStatus,
)
from ai4binance.governance.framework import ChangeApprovalClass

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def test_board_directive_and_work_order_are_safe_by_default() -> None:
    directive = BoardDirective(
        identity(),
        "directive-1",
        "board-chair",
        "Add enterprise contracts",
        ("NO_LIVE_AUTHORITY",),
        (OEK_AUTHORITY_SOURCE, OEK_CONSTITUTION_CONTROL, "RESEARCH_ONLY"),
        "cpu-light",
        600,
    )
    order = ExecutiveWorkOrder(
        identity(),
        directive.directive_id,
        directive.objective,
        (DepartmentId.SOFTWARE_ENGINEERING, DepartmentId.QUALITY_AUDIT),
        Priority.P2,
        WorkOrderStatus.HUMAN_REVIEW_REQUIRED,
    )

    assert directive.execution_allowed is False
    assert order.promotion_status == "RESEARCH_ONLY"
    assert order.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="evidence"):
        replace(directive, evidence_required=False)
    with pytest.raises(ValueError, match="time budget"):
        replace(directive, time_budget_seconds=0)
    with pytest.raises(ValueError, match="blanks"):
        replace(directive, constraints=("",))
    with pytest.raises(ValueError, match="authorize"):
        replace(order, execution_allowed=True)
    with pytest.raises(ValueError, match="assigned departments"):
        replace(order, assigned_departments=())
    with pytest.raises(ValueError, match="blocked work order"):
        replace(order, blockers=())
    with pytest.raises(ValueError, match="unique"):
        replace(
            order,
            assigned_departments=(
                DepartmentId.SOFTWARE_ENGINEERING,
                DepartmentId.SOFTWARE_ENGINEERING,
            ),
        )


def test_workflow_identity_rejects_blank_and_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="work_order_id"):
        WorkflowIdentity("", "run", "trace", NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        WorkflowIdentity("wo", "run", "trace", datetime(2026, 7, 29))


def test_agent_result_and_department_brief_cannot_promote_or_execute() -> None:
    result = AgentResult(
        identity(),
        "task-1",
        "architecture-agent",
        TaskStatus.COMPLETED,
        "Contracts reviewed.",
        ("artifact:contract-review",),
        "AgentResult/v1",
    )
    brief = DepartmentBrief(
        identity(),
        "brief-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        ("Implement typed contracts only.",),
        ("artifact:contract-review",),
        ("LIVE_ORDER_BLOCKED",),
        TaskStatus.COMPLETED,
    )

    assert result.promotion_status == "RESEARCH_ONLY"
    assert brief.execution_allowed is False
    with pytest.raises(ValueError, match="promote"):
        replace(result, promotion_status="PAPER_APPROVED")
    with pytest.raises(ValueError, match="authorize"):
        replace(brief, live_eligibility_status="LIVE_ELIGIBLE")


def test_department_and_agent_tasks_validate_budgets_and_authority() -> None:
    department_task = DepartmentTask(
        identity(),
        "dept-task-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        "Prepare implementation plan.",
        ("BoardDirective/v1",),
        "DepartmentBrief/v1",
    )
    agent_task = AgentTask(
        identity(),
        "agent-task-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        "ImplementationAgent",
        ("READ_LOCAL",),
        "AgentResult/v1",
        1_000,
        60,
    )

    assert department_task.execution_allowed is False
    assert agent_task.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="unique"):
        replace(department_task, depends_on=("a", "a"))
    with pytest.raises(ValueError, match="budgets"):
        replace(agent_task, token_budget=0)
    with pytest.raises(ValueError, match="authorize"):
        replace(agent_task, execution_allowed=True)


def test_interdepartmental_messages_require_manager_route_and_deadline() -> None:
    message = InterdepartmentalQuestion(
        identity(),
        "msg-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        DepartmentId.QUALITY_AUDIT,
        "QualityDepartmentManager",
        "Please review the contract slice.",
        ("artifact:diff-plan",),
        Priority.P2,
        NOW + timedelta(hours=1),
    )

    assert message.sender_department_id is DepartmentId.SOFTWARE_ENGINEERING
    with pytest.raises(ValueError, match="distinct departments"):
        replace(message, recipient_department_id=DepartmentId.SOFTWARE_ENGINEERING)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(message, deadline=datetime(2026, 7, 29))
    with pytest.raises(ValueError, match="recipient_manager_id"):
        replace(message, recipient_manager_id="")


def test_interdepartmental_response_and_challenge_are_manager_bounded() -> None:
    response = InterdepartmentalResponse(
        identity(),
        "msg-2",
        "msg-1",
        DepartmentId.QUALITY_AUDIT,
        "QualityDepartmentManager",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        "Review requires one more negative-path test.",
        ("artifact:quality-review",),
        ("REVISION_REQUIRED",),
    )
    challenge = ChallengeRequest(
        identity(),
        "challenge-1",
        DepartmentId.RISK_VALIDATION,
        DepartmentId.TRADER,
        "claim:trade-ready",
        "OOS evidence is insufficient.",
        ("artifact:oos-review",),
    )

    assert response.execution_allowed is False
    assert challenge.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="distinct departments"):
        replace(response, recipient_department_id=DepartmentId.QUALITY_AUDIT)
    with pytest.raises(ValueError, match="distinct departments"):
        replace(challenge, challenged_department_id=DepartmentId.RISK_VALIDATION)


def test_meeting_agenda_is_bounded_local_and_evidence_backed() -> None:
    agenda = MeetingAgenda(
        identity(),
        "meeting-1",
        "technology-change-advisory-board",
        MeetingState.PREPARE,
        (
            DepartmentId.SOFTWARE_ENGINEERING,
            DepartmentId.QUALITY_AUDIT,
            DepartmentId.MULTI_OPS,
        ),
        ("Review P1 contract slice.",),
        ("DecisionRecord", "ActionItem"),
    )

    assert agenda.max_llm_calls == 4
    assert agenda.local_llm_only is True
    with pytest.raises(ValueError, match="LLM call budget"):
        replace(agenda, max_llm_calls=5)
    with pytest.raises(ValueError, match="local"):
        replace(agenda, local_llm_only=False)
    with pytest.raises(ValueError, match="at least two"):
        replace(agenda, participant_department_ids=(DepartmentId.QUALITY_AUDIT,))
    with pytest.raises(ValueError, match="unique"):
        replace(
            agenda,
            participant_department_ids=(
                DepartmentId.QUALITY_AUDIT,
                DepartmentId.QUALITY_AUDIT,
            ),
        )
    with pytest.raises(ValueError, match="token budget"):
        replace(agenda, max_total_tokens=8_001)
    with pytest.raises(ValueError, match="duration budget"):
        replace(agenda, max_duration_seconds=91)


def test_quality_risk_approval_and_promotion_stay_fail_closed() -> None:
    quality = QualityOpinion(
        identity(),
        "q-1",
        "qaqc-agent",
        "proposal-1",
        OpinionVerdict.REVISION_REQUIRED,
        ("artifact:test-report",),
        ("QUALITY_REVIEW_REQUIRED",),
    )
    risk = RiskOpinion(
        identity(),
        "r-1",
        "risk-agent",
        "trade-plan-1",
        OpinionVerdict.REJECTED,
        ("artifact:risk-report",),
        ("RISK_REJECTED",),
        vetoed=True,
    )
    approval = ApprovalRecord(
        identity(),
        "approval-1",
        "user",
        "proposal-1",
        ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        ("artifact:diff-plan",),
    )
    promotion = PromotionDecision(
        identity(),
        "promotion-1",
        "model-candidate-1",
        "READY_FOR_USER_APPROVAL",
        ("artifact:oos-report",),
        ("LIVE_ORDER_BLOCKED",),
    )

    assert quality.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert risk.vetoed is True
    assert approval.execution_allowed is False
    assert promotion.user_approval_required is True
    with pytest.raises(ValueError, match="own finding"):
        replace(quality, finding_closed=True)
    with pytest.raises(ValueError, match="veto"):
        replace(risk, vetoed=False)
    with pytest.raises(ValueError, match="requires evidence"):
        replace(approval, evidence_refs=())
    with pytest.raises(ValueError, match="user approval"):
        replace(promotion, user_approval_required=False)
    with pytest.raises(ValueError, match="governed"):
        replace(promotion, verdict="LIVE_PROMOTED")


def test_bound_approval_record_requires_scope_hashes_and_ordered_expiry() -> None:
    approved_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    approval = ApprovalRecord(
        identity(),
        "approval-2",
        "approver-1",
        "proposal-2",
        ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        ("artifact:diff-plan",),
        approver_role="GovernanceOwner",
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256="a" * 64,
        scope_hash="b" * 64,
        quality_gate_evidence_sha256="c" * 64,
        governance_gate_evidence_sha256="d" * 64,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(days=1),
    )

    assert approval.change_class is ChangeApprovalClass.C3_GOVERNED
    assert approval.scope_hash == "b" * 64
    assert approval.principal_id == ""

    with pytest.raises(ValueError, match="approver_role"):
        replace(approval, approver_role="")
    with pytest.raises(ValueError, match="change_class"):
        replace(approval, change_class=None)
    with pytest.raises(ValueError, match="approved_at"):
        replace(approval, approved_at=None)
    with pytest.raises(ValueError, match="sha256"):
        replace(approval, scope_hash="bad")
    with pytest.raises(ValueError, match="after approval"):
        replace(approval, expires_at=approved_at)


def test_bound_approval_record_accepts_nonblank_principal_id() -> None:
    approved_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    approval = ApprovalRecord(
        identity(),
        "approval-3",
        "approver-1:GovernanceOwner",
        "proposal-3",
        ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        ("artifact:diff-plan",),
        approver_role="GovernanceOwner",
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256="a" * 64,
        scope_hash="b" * 64,
        quality_gate_evidence_sha256="c" * 64,
        governance_gate_evidence_sha256="d" * 64,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(days=1),
        principal_id="approver-1",
    )

    assert approval.principal_id == "approver-1"


def test_bound_approval_record_validates_optional_binding_hashes_and_revocation() -> (
    None
):
    approved_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    approval = ApprovalRecord(
        identity(),
        "approval-4",
        "approver-1",
        "subject",
        ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        ("artifact:governance-report",),
        approver_role="GovernanceOwner",
        change_class=ChangeApprovalClass.C3_GOVERNED,
        subject_sha256="a" * 64,
        scope_hash="b" * 64,
        quality_gate_evidence_sha256="c" * 64,
        governance_gate_evidence_sha256="d" * 64,
        evidence_hash="e" * 64,
        authority_family_sha256="f" * 64,
        lifecycle_definition_sha256="1" * 64,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(days=1),
        revoked_at=approved_at + timedelta(days=2),
    )

    assert approval.evidence_hash == "e" * 64
    assert approval.revoked_at == approved_at + timedelta(days=2)

    with pytest.raises(ValueError, match="sha256"):
        replace(approval, evidence_hash="bad")
    with pytest.raises(ValueError, match="sha256"):
        replace(approval, authority_family_sha256="bad")
    with pytest.raises(ValueError, match="sha256"):
        replace(approval, lifecycle_definition_sha256="bad")
    with pytest.raises(ValueError, match="after approval"):
        replace(approval, revoked_at=approved_at)


def test_ops_actions_change_learning_and_audit_records_are_fail_closed() -> None:
    ops = OpsReadiness(
        identity(),
        "ops-1",
        "multiops-agent",
        "proposal-1",
        OpinionVerdict.ACCEPTED,
        ("artifact:ops-review",),
        (),
    )
    action = ActionItem(
        identity(),
        "action-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        "Add contract tests.",
        NOW + timedelta(days=1),
        evidence_refs=("artifact:plan",),
    )
    change = ChangeProposal(
        identity(),
        "proposal-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "Add enterprise contracts.",
        ("src/ai4binance/enterprise/contracts.py",),
        ("tests/test_enterprise_contracts.py",),
        ("LIVE_ORDER_BLOCKED_UNCHANGED",),
    )
    learning = LearningCandidate(
        identity(),
        "lesson-1",
        "audit:event-1",
        "A blocker should become a validation test.",
        ("BACKTEST", "OOS"),
    )
    audit = AuditEvent(
        identity(),
        "audit-1",
        "ENTERPRISE_CONTRACT_ADDED",
        "codex",
        "proposal-1",
        ("artifact:test-report",),
    )

    assert ops.promotion_status == "RESEARCH_ONLY"
    assert action.execution_allowed is False
    assert change.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert learning.status == "RESEARCH_ONLY"
    assert audit.promotion_status == "RESEARCH_ONLY"
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(action, due_at=datetime(2026, 7, 30))
    with pytest.raises(ValueError, match="promote"):
        replace(change, promotion_status="PAPER_APPROVED")
    with pytest.raises(ValueError, match="research-only"):
        replace(learning, status="STAGED_CANDIDATE")
    with pytest.raises(ValueError, match="uppercase snake case"):
        replace(audit, event_type="not snake")

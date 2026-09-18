from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.enterprise.communication import (
    CommunicationDecision,
    CommunicationDecisionStatus,
    DepartmentCommunicationGate,
)
from ai4binance.enterprise.contracts import (
    DepartmentId,
    InterdepartmentalQuestion,
    InterdepartmentalResponse,
    Priority,
    WorkflowIdentity,
)
from ai4binance.enterprise.departments import build_default_department_registry

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def question() -> InterdepartmentalQuestion:
    return InterdepartmentalQuestion(
        identity(),
        "msg-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        DepartmentId.QUALITY_AUDIT,
        "QualityDepartmentManager",
        "Review the proposed enterprise contract slice.",
        ("artifact:diff-plan",),
        Priority.P2,
        NOW + timedelta(hours=1),
    )


def test_communication_gate_allows_only_manager_routed_questions() -> None:
    gate = DepartmentCommunicationGate(build_default_department_registry())
    decision = gate.validate_question(question())

    assert decision.status is CommunicationDecisionStatus.ALLOWED
    assert decision.reason_codes == ("MANAGER_ROUTE_VALIDATED",)
    assert decision.execution_allowed is False
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_communication_gate_blocks_sender_or_recipient_manager_mismatch() -> None:
    gate = DepartmentCommunicationGate(build_default_department_registry())

    sender = gate.validate_question(
        replace(question(), sender_manager_id="ImplementationAgent")
    )
    recipient = gate.validate_question(
        replace(question(), recipient_manager_id="SoftwareQualityReviewAgent")
    )

    assert sender.status is CommunicationDecisionStatus.BLOCKED
    assert sender.reason_codes == (
        "SENDER_MANAGER_MISMATCH",
        "LIVE_ORDER_BLOCKED",
    )
    assert recipient.reason_codes == (
        "RECIPIENT_MANAGER_MISMATCH",
        "LIVE_ORDER_BLOCKED",
    )


def test_communication_gate_requires_evidence_for_cross_department_messages() -> None:
    gate = DepartmentCommunicationGate(build_default_department_registry())
    decision = gate.validate_question(replace(question(), evidence_refs=()))

    assert decision.status is CommunicationDecisionStatus.BLOCKED
    assert decision.reason_codes == (
        "INTERDEPARTMENTAL_EVIDENCE_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )


def test_communication_gate_validates_responses_with_same_manager_route() -> None:
    gate = DepartmentCommunicationGate(build_default_department_registry())
    response = InterdepartmentalResponse(
        identity(),
        "msg-2",
        "msg-1",
        DepartmentId.QUALITY_AUDIT,
        "QualityDepartmentManager",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        "Add one negative-path test before approval.",
        ("artifact:quality-review",),
        ("REVISION_REQUIRED",),
    )

    decision = gate.validate_response(response)

    assert decision.status is CommunicationDecisionStatus.ALLOWED
    assert decision.sender_manager_id == "QualityDepartmentManager"
    assert decision.recipient_manager_id == "SoftwareDepartmentManager"


def test_communication_decision_cannot_claim_execution_authority() -> None:
    with pytest.raises(ValueError, match="authorize execution"):
        CommunicationDecision(
            CommunicationDecisionStatus.BLOCKED,
            ("LIVE_ORDER_BLOCKED",),
            "SoftwareDepartmentManager",
            "QualityDepartmentManager",
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="manager route"):
        CommunicationDecision(
            CommunicationDecisionStatus.ALLOWED,
            ("MANUAL_OVERRIDE",),
            "SoftwareDepartmentManager",
            "QualityDepartmentManager",
        )

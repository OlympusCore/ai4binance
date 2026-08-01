"""Manager-routed interdepartmental communication gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise.contracts import (
    DepartmentId,
    InterdepartmentalQuestion,
    InterdepartmentalResponse,
)
from ai4binance.enterprise.departments import DepartmentRegistry
from ai4binance.enterprise.prompt_intake import contains_restricted_prompt_content


class CommunicationDecisionStatus(StrEnum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CommunicationDecision:
    status: CommunicationDecisionStatus
    reason_codes: tuple[str, ...]
    sender_manager_id: str
    recipient_manager_id: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.reason_codes:
            raise ValueError("communication decision requires reasons")
        if not self.sender_manager_id.strip() or not self.recipient_manager_id.strip():
            raise ValueError("communication decision requires manager identities")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("communication decision cannot authorize execution")
        if self.status is CommunicationDecisionStatus.ALLOWED and self.reason_codes != (
            "MANAGER_ROUTE_VALIDATED",
        ):
            raise ValueError("allowed communication must use the manager route")


@dataclass(frozen=True, slots=True)
class DepartmentCommunicationGate:
    """Validate that departments communicate through their managers."""

    registry: DepartmentRegistry

    def validate_question(
        self, message: InterdepartmentalQuestion
    ) -> CommunicationDecision:
        return self._validate_route(
            sender_department=message.sender_department_id,
            sender_manager=message.sender_manager_id,
            recipient_department=message.recipient_department_id,
            recipient_manager=message.recipient_manager_id,
            content=(message.question, *message.evidence_refs),
            evidence_refs=message.evidence_refs,
        )

    def validate_response(
        self, message: InterdepartmentalResponse
    ) -> CommunicationDecision:
        return self._validate_route(
            sender_department=message.sender_department_id,
            sender_manager=message.sender_manager_id,
            recipient_department=message.recipient_department_id,
            recipient_manager=message.recipient_manager_id,
            content=(message.response, *message.evidence_refs),
            evidence_refs=message.evidence_refs,
        )

    def _validate_route(
        self,
        *,
        sender_department: DepartmentId,
        sender_manager: str,
        recipient_department: DepartmentId,
        recipient_manager: str,
        content: tuple[str, ...],
        evidence_refs: tuple[str, ...],
    ) -> CommunicationDecision:
        if sender_department == recipient_department:
            return _blocked(
                "DIRECT_SAME_DEPARTMENT_ROUTE_REJECTED",
                sender_manager,
                recipient_manager,
            )
        expected_sender = self.registry.get(sender_department).manager_role
        expected_recipient = self.registry.get(recipient_department).manager_role
        if sender_manager != expected_sender:
            return _blocked(
                "SENDER_MANAGER_MISMATCH",
                sender_manager,
                recipient_manager,
            )
        if recipient_manager != expected_recipient:
            return _blocked(
                "RECIPIENT_MANAGER_MISMATCH",
                sender_manager,
                recipient_manager,
            )
        if not evidence_refs:
            return _blocked(
                "INTERDEPARTMENTAL_EVIDENCE_REQUIRED",
                sender_manager,
                recipient_manager,
            )
        if any(contains_restricted_prompt_content(item) for item in content):
            return _blocked(
                "PROMPT_ACCESS_BLOCKED",
                sender_manager,
                recipient_manager,
            )
        return CommunicationDecision(
            CommunicationDecisionStatus.ALLOWED,
            ("MANAGER_ROUTE_VALIDATED",),
            sender_manager,
            recipient_manager,
        )


def _blocked(
    reason: str,
    sender_manager: str,
    recipient_manager: str,
) -> CommunicationDecision:
    return CommunicationDecision(
        CommunicationDecisionStatus.BLOCKED,
        (reason, "LIVE_ORDER_BLOCKED"),
        sender_manager,
        recipient_manager,
    )

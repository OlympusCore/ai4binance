"""Verified persistence adapters for enterprise governance records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai4binance.enterprise.contracts import AuditEvent as EnterpriseAuditEvent
from ai4binance.enterprise.contracts import ExecutiveWorkOrder, WorkflowIdentity
from ai4binance.enterprise.prompt_intake import (
    ExecutivePromptIntake,
    PromptAccessDecision,
    PromptAccessStatus,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.storage.destination_verification import VerifiedWriteResult


@dataclass(frozen=True, slots=True)
class EnterpriseAuditJournal:
    """Append enterprise audit events with destination read-back proof."""

    path: Path
    durable: bool = False

    def append_verified(
        self,
        event: EnterpriseAuditEvent,
    ) -> VerifiedWriteResult:
        payload = to_primitive(event)
        if not isinstance(payload, dict):
            raise RuntimeError("ENTERPRISE_AUDIT_PAYLOAD_INVALID")
        store = JsonlAuditStore(self.path, durable=self.durable)
        return store.append_verified(
            AuditEvent(
                event_type=event.event_type,
                timestamp=event.identity.created_at,
                payload=payload,
                snapshot_id=event.identity.snapshot_id,
            )
        )

    def append_prompt_intake_verified(
        self,
        intake: ExecutivePromptIntake,
    ) -> VerifiedWriteResult:
        return self.append_verified(
            EnterpriseAuditEvent(
                identity=intake.identity,
                event_id=f"audit:{intake.prompt_id}:intake",
                event_type="EXECUTIVE_PROMPT_INTAKE",
                actor_id="GeneralManagerController",
                subject_ref=intake.raw_prompt_ref,
                evidence_refs=intake.evidence_refs,
                blockers=intake.blockers,
            )
        )

    def append_prompt_access_decision_verified(
        self,
        decision: PromptAccessDecision,
        *,
        identity: WorkflowIdentity,
    ) -> VerifiedWriteResult:
        blockers = (
            ("LIVE_ORDER_BLOCKED",)
            if decision.status is PromptAccessStatus.ALLOWED
            else decision.reason_codes
        )
        return self.append_verified(
            EnterpriseAuditEvent(
                identity=identity,
                event_id=f"audit:{decision.prompt_id}:access:{decision.actor_role}",
                event_type="PROMPT_ACCESS_DECISION",
                actor_id=decision.actor_role,
                subject_ref=f"prompt:{decision.prompt_id}",
                evidence_refs=(f"prompt-visibility:{decision.visibility.value}",),
                blockers=blockers,
            )
        )

    def append_work_order_created_verified(
        self,
        work_order: ExecutiveWorkOrder,
    ) -> VerifiedWriteResult:
        return self.append_verified(
            EnterpriseAuditEvent(
                identity=work_order.identity,
                event_id=f"audit:{work_order.directive_id}:work-order-created",
                event_type="WORK_ORDER_CREATED",
                actor_id="GeneralManagerController",
                subject_ref=work_order.directive_id,
                evidence_refs=(f"work-order:{work_order.identity.work_order_id}",),
                blockers=work_order.blockers,
            )
        )

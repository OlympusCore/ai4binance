"""Bridge enterprise governance records into the hash-linked event journal."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from ai4binance.enterprise.contracts import (
    AuditEvent as EnterpriseAuditEvent,
)
from ai4binance.enterprise.contracts import BoardDirective, ExecutiveWorkOrder
from ai4binance.events import DiskEventJournal, DomainEvent
from ai4binance.reporting import to_primitive


class EnterpriseDomainEventType(StrEnum):
    BOARD_DIRECTIVE_RECORDED = "BOARD_DIRECTIVE_RECORDED"
    WORK_ORDER_CREATED = "WORK_ORDER_CREATED"
    ENTERPRISE_AUDIT_RECORDED = "ENTERPRISE_AUDIT_RECORDED"


EnterpriseGovernanceRecord = BoardDirective | ExecutiveWorkOrder | EnterpriseAuditEvent


def board_directive_domain_event(
    directive: BoardDirective,
    *,
    sequence: int,
    previous_hash: str = "GENESIS",
) -> DomainEvent:
    """Convert a board directive into a redacted domain event."""

    return _governance_domain_event(
        record=directive,
        event_id=f"enterprise:{directive.directive_id}:board-directive-recorded",
        event_type=EnterpriseDomainEventType.BOARD_DIRECTIVE_RECORDED,
        sequence=sequence,
        previous_hash=previous_hash,
        subject_ref=f"directive:{directive.directive_id}",
        payload_refs=(
            ("authority_scope_count", str(len(directive.authority_scope))),
            ("constraint_count", str(len(directive.constraints))),
            ("evidence_required", str(directive.evidence_required)),
            ("time_budget_seconds", str(directive.time_budget_seconds)),
        ),
    )


def work_order_domain_event(
    work_order: ExecutiveWorkOrder,
    *,
    sequence: int,
    previous_hash: str = "GENESIS",
) -> DomainEvent:
    """Convert a work order into a redacted domain event."""

    return _governance_domain_event(
        record=work_order,
        event_id=f"enterprise:{work_order.directive_id}:work-order-created",
        event_type=EnterpriseDomainEventType.WORK_ORDER_CREATED,
        sequence=sequence,
        previous_hash=previous_hash,
        subject_ref=f"work-order:{work_order.identity.work_order_id}",
        payload_refs=(
            ("assigned_department_count", str(len(work_order.assigned_departments))),
            ("blocker_count", str(len(work_order.blockers))),
            ("priority", work_order.priority.value),
            ("status", work_order.status.value),
        ),
    )


def enterprise_audit_domain_event(
    event: EnterpriseAuditEvent,
    *,
    sequence: int,
    previous_hash: str = "GENESIS",
) -> DomainEvent:
    """Convert an enterprise audit record into a redacted domain event."""

    return _governance_domain_event(
        record=event,
        event_id=f"enterprise:{event.event_id}:audit-recorded",
        event_type=EnterpriseDomainEventType.ENTERPRISE_AUDIT_RECORDED,
        sequence=sequence,
        previous_hash=previous_hash,
        subject_ref=f"audit:{event.event_id}",
        payload_refs=(
            ("blocker_count", str(len(event.blockers))),
            ("evidence_count", str(len(event.evidence_refs))),
            ("source_event_type", event.event_type),
        ),
    )


@dataclass(frozen=True, slots=True)
class EnterpriseDomainEventJournal:
    """Append enterprise records as hash-linked domain events."""

    journal: DiskEventJournal

    def append_board_directive(self, directive: BoardDirective) -> DomainEvent:
        return self._append(board_directive_domain_event, directive)

    def append_work_order(self, work_order: ExecutiveWorkOrder) -> DomainEvent:
        return self._append(work_order_domain_event, work_order)

    def append_audit_event(self, event: EnterpriseAuditEvent) -> DomainEvent:
        return self._append(enterprise_audit_domain_event, event)

    def _append(
        self,
        builder: _EnterpriseEventBuilder,
        record: EnterpriseGovernanceRecord,
    ) -> DomainEvent:
        events = self.journal.load()
        previous_hash = events[-1].event_hash if events else "GENESIS"
        event = builder(
            record,
            sequence=len(events) + 1,
            previous_hash=previous_hash,
        )
        self.journal.append(event)
        return event


_EnterpriseEventBuilder = Callable[..., DomainEvent]


def _governance_domain_event(
    *,
    record: EnterpriseGovernanceRecord,
    event_id: str,
    event_type: EnterpriseDomainEventType,
    sequence: int,
    previous_hash: str,
    subject_ref: str,
    payload_refs: tuple[tuple[str, str], ...],
) -> DomainEvent:
    identity = record.identity
    payload = (
        ("code_commit", identity.code_commit),
        ("config_hash", identity.config_hash),
        ("content_sha256", _contract_hash(record)),
        ("contract_type", type(record).__name__),
        ("execution_allowed", str(record.execution_allowed)),
        ("live_eligibility_status", record.live_eligibility_status),
        ("run_id", identity.run_id),
        ("schema_version", identity.schema_version),
        ("snapshot_id", identity.snapshot_id),
        ("subject_ref", subject_ref),
        ("trace_id", identity.trace_id),
        ("work_order_id", identity.work_order_id),
        *payload_refs,
    )
    if hasattr(record, "promotion_status"):
        payload = (
            *payload,
            ("promotion_status", str(record.promotion_status)),
        )
    return DomainEvent.create(
        event_id=event_id,
        aggregate_id=identity.work_order_id,
        event_type=event_type.value,
        sequence=sequence,
        occurred_at=identity.created_at,
        payload=payload,
        previous_hash=previous_hash,
    )


def _contract_hash(record: EnterpriseGovernanceRecord) -> str:
    payload = to_primitive(record)
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()

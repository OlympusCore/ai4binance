from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai4binance.enterprise import (
    AuditEvent,
    BoardDirective,
    DepartmentId,
    EnterpriseDomainEventJournal,
    EnterpriseDomainEventType,
    ExecutiveWorkOrder,
    Priority,
    WorkflowIdentity,
    WorkOrderStatus,
    board_directive_domain_event,
    work_order_domain_event,
)
from ai4binance.events import DiskEventJournal

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity(
        "wo-holding-1",
        "run-holding-1",
        "trace-holding-1",
        NOW,
        snapshot_id="snapshot-holding-1",
        code_commit="WORKTREE_UNCOMMITTED",
        config_hash="CONFIG_HASH_NOT_BOUND",
    )


def directive() -> BoardDirective:
    return BoardDirective(
        identity(),
        "directive-holding-1",
        "board-chair",
        "Apply a private holding governance operating system.",
        ("NO_LIVE_AUTHORITY", "NO_RAW_PRIVATE_PROFILE_OUTSIDE_COMPUTER_MD"),
        ("RESEARCH_ONLY", "GENERAL_MANAGER_ORCHESTRATION"),
        "local-only",
        600,
    )


def work_order() -> ExecutiveWorkOrder:
    return ExecutiveWorkOrder(
        identity(),
        "directive-holding-1",
        "Create the governance event bridge.",
        (DepartmentId.SOFTWARE_ENGINEERING, DepartmentId.QUALITY_AUDIT),
        Priority.P2,
        WorkOrderStatus.HUMAN_REVIEW_REQUIRED,
    )


def audit_event() -> AuditEvent:
    return AuditEvent(
        identity(),
        "audit-holding-1",
        "ENTERPRISE_EVENT_BRIDGE_ADDED",
        "codex",
        "work-order:wo-holding-1",
        ("tests:test_enterprise_event_bridge",),
    )


def test_board_directive_event_is_redacted_and_hash_bound() -> None:
    event = board_directive_domain_event(directive(), sequence=1)
    payload = event.payload_dict()

    assert event.event_type == EnterpriseDomainEventType.BOARD_DIRECTIVE_RECORDED
    assert event.aggregate_id == "wo-holding-1"
    assert payload["contract_type"] == "BoardDirective"
    assert payload["subject_ref"] == "directive:directive-holding-1"
    assert len(payload["content_sha256"]) == 64
    assert payload["execution_allowed"] == "False"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert "Apply a private holding governance operating system." not in tuple(
        payload.values()
    )


def test_work_order_event_chains_after_directive_event() -> None:
    first = board_directive_domain_event(directive(), sequence=1)
    second = work_order_domain_event(
        work_order(),
        sequence=2,
        previous_hash=first.event_hash,
    )
    payload = second.payload_dict()

    assert second.previous_hash == first.event_hash
    assert second.event_type == EnterpriseDomainEventType.WORK_ORDER_CREATED
    assert payload["assigned_department_count"] == "2"
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert "Create the governance event bridge." not in tuple(payload.values())


def test_enterprise_domain_event_journal_appends_and_recovers(
    tmp_path: Path,
) -> None:
    journal = DiskEventJournal(tmp_path / "enterprise-events.jsonl", durable=False)
    bridge = EnterpriseDomainEventJournal(journal)

    first = bridge.append_board_directive(directive())
    second = bridge.append_work_order(work_order())
    third = bridge.append_audit_event(audit_event())
    recovered = journal.recover()

    assert (first.sequence, second.sequence, third.sequence) == (1, 2, 3)
    assert second.previous_hash == first.event_hash
    assert third.previous_hash == second.event_hash
    assert [event.event_type for event in recovered.events] == [
        "BOARD_DIRECTIVE_RECORDED",
        "WORK_ORDER_CREATED",
        "ENTERPRISE_AUDIT_RECORDED",
    ]
    assert recovered.execution_allowed is False
    assert recovered.live_eligibility_status == "LIVE_ORDER_BLOCKED"

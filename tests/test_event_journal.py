"""Durable event journal corruption, checkpoint, and restart tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.events import (
    DiskEventJournal,
    DomainEvent,
    EventJournalCorruptionError,
    JournalCheckpoint,
    JournaledEventRuntime,
)
from ai4binance.execution.order_state import OrderStateMachine, OrderStatus

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def build_events() -> tuple[DomainEvent, ...]:
    submitted = DomainEvent.create(
        event_id="event-1",
        aggregate_id="paper-order-1",
        event_type="ORDER_SUBMITTED",
        sequence=1,
        occurred_at=NOW,
        payload=(("action", "BUY"), ("quantity", "2"), ("symbol", "HOTUSDT")),
    )
    accepted = DomainEvent.create(
        event_id="event-2",
        aggregate_id="paper-order-1",
        event_type="ORDER_ACCEPTED",
        sequence=2,
        occurred_at=NOW + timedelta(seconds=1),
        previous_hash=submitted.event_hash,
    )
    return submitted, accepted


def test_journal_recovers_runtime_and_order_state_after_restart(tmp_path: Path) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl")
    runtime = JournaledEventRuntime.open(journal)
    for event in build_events():
        runtime.publish(event)
    checkpoint = journal.checkpoint(created_at=NOW + timedelta(seconds=2))

    restarted = JournaledEventRuntime.open(DiskEventJournal(journal.path))
    recovery = journal.recover()

    assert restarted.snapshot() == build_events()
    assert OrderStateMachine.replay(restarted.snapshot()).status is OrderStatus.ACCEPTED
    assert checkpoint.sequence == 2
    assert recovery.checkpoint == checkpoint
    assert recovery.events_after_checkpoint == ()
    assert recovery.execution_allowed is False
    assert recovery.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_journal_rejects_partial_tampered_and_noncontiguous_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    journal = DiskEventJournal(path)
    journal.append(build_events()[0])
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(EventJournalCorruptionError, match="partial"):
        journal.load()

    path.unlink()
    journal.append(build_events()[0])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["event_hash"] = "0" * 64
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(EventJournalCorruptionError, match="invalid"):
        journal.load()

    path.unlink()
    with pytest.raises(ValueError, match="sequence"):
        journal.append(build_events()[1])


def test_journal_rejects_duplicate_and_bad_checkpoint(tmp_path: Path) -> None:
    journal = DiskEventJournal(tmp_path / "events.jsonl")
    first = build_events()[0]
    journal.append(first)
    with pytest.raises(ValueError, match="duplicate"):
        journal.append(first)
    journal.checkpoint(created_at=NOW)
    target = journal.checkpoint_path
    assert target is not None
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["event_hash"] = "f" * 64
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EventJournalCorruptionError, match="does not match"):
        journal.recover()


def test_journal_enforces_record_and_total_byte_limits(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="size limits"):
        DiskEventJournal(tmp_path / "events.jsonl", maximum_event_bytes=128)
    journal = DiskEventJournal(
        tmp_path / "events.jsonl",
        maximum_event_bytes=256,
        maximum_journal_bytes=256,
    )
    with pytest.raises(OverflowError, match="record exceeds"):
        journal.append(
            DomainEvent.create(
                event_id="large",
                aggregate_id="paper-order-1",
                event_type="ORDER_SUBMITTED",
                sequence=1,
                occurred_at=NOW,
                payload=(("blob", "x" * 500),),
            )
        )


def test_checkpoint_and_recovery_fail_closed_on_invalid_evidence(
    tmp_path: Path,
) -> None:
    journal = DiskEventJournal(
        tmp_path / "events.jsonl",
        checkpoint_path=tmp_path / "cursor.json",
        durable=False,
    )
    assert journal.recover().events_after_checkpoint == ()
    with pytest.raises(ValueError, match="empty journal"):
        journal.checkpoint(created_at=NOW)
    with pytest.raises(ValueError, match="sequence"):
        JournalCheckpoint(0, "a" * 64, NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        JournalCheckpoint(1, "a" * 64, NOW.replace(tzinfo=None))

    journal.append(build_events()[0])
    observed: list[str] = []
    runtime = JournaledEventRuntime.open(journal)
    runtime.subscribe(lambda event: observed.append(event.event_id))
    runtime.publish(build_events()[1])
    assert observed == ["event-2"]

    target = journal.checkpoint_path
    assert target is not None
    target.write_text("not-json", encoding="utf-8")
    with pytest.raises(EventJournalCorruptionError, match="checkpoint is invalid"):
        journal.recover()
    target.write_text(
        json.dumps(
            {
                "created_at": NOW.isoformat(),
                "event_hash": "a" * 64,
                "schema_version": "1.0",
                "sequence": 3,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EventJournalCorruptionError, match="exceeds journal"):
        journal.recover()

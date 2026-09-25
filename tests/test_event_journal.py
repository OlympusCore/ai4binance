"""Durable event journal corruption, checkpoint, and restart tests."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

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


def test_append_next_serializes_distinct_journal_instances(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    def append_event(index: int) -> DomainEvent:
        journal = DiskEventJournal(path, durable=False)
        return journal.append_next(
            lambda sequence, previous_hash: DomainEvent.create(
                event_id=f"concurrent-{index}",
                aggregate_id="paper-order-concurrent",
                event_type="ORDER_OBSERVED",
                sequence=sequence,
                occurred_at=NOW,
                previous_hash=previous_hash,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        appended = tuple(executor.map(append_event, range(20)))

    loaded = DiskEventJournal(path, durable=False).load()

    assert len(appended) == len(loaded) == 20
    assert tuple(event.sequence for event in loaded) == tuple(range(1, 21))
    assert {event.event_id for event in loaded} == {
        f"concurrent-{index}" for index in range(20)
    }
    assert all(
        event.previous_hash == previous.event_hash
        for previous, event in pairwise(loaded)
    )


def test_sequential_append_reuses_validated_tail_without_replaying_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    decoded_records = 0
    original_decode = DiskEventJournal._decode_event

    def counting_decode(payload: object) -> DomainEvent:
        nonlocal decoded_records
        decoded_records += 1
        return original_decode(payload)

    monkeypatch.setattr(
        DiskEventJournal,
        "_decode_event",
        staticmethod(counting_decode),
    )
    journal = DiskEventJournal(path, durable=False)
    for _index in range(10):

        def build_sequential_event(
            sequence: int,
            previous_hash: str,
        ) -> DomainEvent:
            event_index = sequence - 1
            return DomainEvent.create(
                event_id=f"sequential-{event_index}",
                aggregate_id="paper-order-sequential",
                event_type="ORDER_OBSERVED",
                sequence=sequence,
                occurred_at=NOW + timedelta(seconds=event_index),
                previous_hash=previous_hash,
            )

        journal.append_next(build_sequential_event)

    assert decoded_records == 0
    assert len(journal.load()) == 10
    assert decoded_records == 10


def test_append_cache_resynchronizes_after_another_journal_writes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = DiskEventJournal(path, durable=False)
    second = DiskEventJournal(path, durable=False)

    first_event = first.append_next(
        lambda sequence, previous_hash: DomainEvent.create(
            event_id="cross-instance-1",
            aggregate_id="paper-order-cross-instance",
            event_type="ORDER_OBSERVED",
            sequence=sequence,
            occurred_at=NOW,
            previous_hash=previous_hash,
        )
    )
    second_event = second.append_next(
        lambda sequence, previous_hash: DomainEvent.create(
            event_id="cross-instance-2",
            aggregate_id="paper-order-cross-instance",
            event_type="ORDER_OBSERVED",
            sequence=sequence,
            occurred_at=NOW + timedelta(seconds=1),
            previous_hash=previous_hash,
        )
    )
    third_event = first.append_next(
        lambda sequence, previous_hash: DomainEvent.create(
            event_id="cross-instance-3",
            aggregate_id="paper-order-cross-instance",
            event_type="ORDER_OBSERVED",
            sequence=sequence,
            occurred_at=NOW + timedelta(seconds=2),
            previous_hash=previous_hash,
        )
    )

    assert (first_event.sequence, second_event.sequence, third_event.sequence) == (
        1,
        2,
        3,
    )
    assert third_event.previous_hash == second_event.event_hash
    assert first.load() == (first_event, second_event, third_event)


def test_append_cache_revalidates_and_rejects_same_size_tampering(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    journal = DiskEventJournal(path, durable=False)
    first = build_events()[0]
    journal.append(first)
    original_stat = path.stat()
    original_data = path.read_bytes()
    tampered_data = original_data.replace(
        first.event_hash.encode("ascii"),
        b"0" * 64,
        1,
    )
    assert len(tampered_data) == len(original_data)
    path.write_bytes(tampered_data)
    os.utime(
        path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    restored_stat = path.stat()
    assert restored_stat.st_size == original_stat.st_size
    assert restored_stat.st_mtime_ns == original_stat.st_mtime_ns

    with pytest.raises(EventJournalCorruptionError, match="record 1 is invalid"):
        journal.append_next(
            lambda sequence, previous_hash: DomainEvent.create(
                event_id="tamper-follow-up",
                aggregate_id="paper-order-1",
                event_type="ORDER_ACCEPTED",
                sequence=sequence,
                occurred_at=NOW + timedelta(seconds=1),
                previous_hash=previous_hash,
            )
        )

    assert path.read_bytes() == tampered_data


def test_append_cache_falls_back_to_replay_without_change_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    decoded_records = 0
    original_decode = DiskEventJournal._decode_event

    def counting_decode(payload: object) -> DomainEvent:
        nonlocal decoded_records
        decoded_records += 1
        return original_decode(payload)

    monkeypatch.setattr(
        DiskEventJournal,
        "_decode_event",
        staticmethod(counting_decode),
    )
    monkeypatch.setattr(
        "ai4binance.events.journal._file_change_token",
        lambda _stream, _stat: None,
    )
    journal = DiskEventJournal(path, durable=False)
    for index in range(4):

        def build_fallback_event(
            sequence: int,
            previous_hash: str,
            event_index: int = index,
        ) -> DomainEvent:
            return DomainEvent.create(
                event_id=f"fallback-{event_index}",
                aggregate_id="paper-order-fallback",
                event_type="ORDER_OBSERVED",
                sequence=sequence,
                occurred_at=NOW + timedelta(seconds=event_index),
                previous_hash=previous_hash,
            )

        journal.append_next(build_fallback_event)

    assert decoded_records == 6
    assert len(journal.load()) == 4
    assert decoded_records == 10


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


@pytest.mark.parametrize("missing_name", ["flock", "LOCK_EX"])
def test_posix_file_lock_acquire_requires_platform_primitives(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
) -> None:
    import sys
    from types import SimpleNamespace

    import ai4binance.events.file_lock as file_lock

    primitives = {"flock": lambda *_args: None, "LOCK_EX": 2}
    primitives[missing_name] = None
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(**primitives))

    with pytest.raises(RuntimeError, match="POSIX file locking is unavailable"):
        file_lock._acquire_file_lock(cast(Any, SimpleNamespace(fileno=lambda: 7)))


@pytest.mark.parametrize("missing_name", ["flock", "LOCK_UN"])
def test_posix_file_lock_release_requires_platform_primitives(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
) -> None:
    import sys
    from types import SimpleNamespace

    import ai4binance.events.file_lock as file_lock

    primitives = {"flock": lambda *_args: None, "LOCK_UN": 8}
    primitives[missing_name] = None
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(**primitives))

    with pytest.raises(RuntimeError, match="POSIX file locking is unavailable"):
        file_lock._release_file_lock(cast(Any, SimpleNamespace(fileno=lambda: 7)))


def test_posix_file_lock_calls_platform_primitives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import ai4binance.events.file_lock as file_lock

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setitem(
        sys.modules,
        "fcntl",
        SimpleNamespace(
            flock=lambda descriptor, operation: calls.append((descriptor, operation)),
            LOCK_EX=2,
            LOCK_UN=8,
        ),
    )
    stream = cast(Any, SimpleNamespace(fileno=lambda: 7))

    file_lock._acquire_file_lock(stream)
    file_lock._release_file_lock(stream)

    assert calls == [(7, 2), (7, 8)]


def test_windows_file_lock_retries_transient_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import errno
    import sys
    from types import SimpleNamespace

    import ai4binance.events.file_lock as file_lock

    calls: list[tuple[int, int, int]] = []

    def locking(descriptor: int, operation: int, size: int) -> None:
        calls.append((descriptor, operation, size))
        if len(calls) < 3:
            raise OSError(errno.EDEADLK, "fixture contention")

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("ai4binance.events.file_lock.time.sleep", lambda _seconds: None)
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(locking=locking, LK_NBLCK=1),
    )
    stream = cast(
        Any,
        SimpleNamespace(seek=lambda *_args: None, fileno=lambda: 7),
    )

    file_lock._acquire_file_lock(stream)

    assert calls == [(7, 1, 1), (7, 1, 1), (7, 1, 1)]


def test_windows_file_lock_times_out_on_persistent_contention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import errno
    import sys
    from types import SimpleNamespace

    import ai4binance.events.file_lock as file_lock

    def locking(_descriptor: int, _operation: int, _size: int) -> None:
        raise OSError(errno.EDEADLK, "fixture contention")

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(file_lock, "_WINDOWS_LOCK_TIMEOUT_SECONDS", 0.0)
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(locking=locking, LK_NBLCK=1),
    )
    stream = cast(
        Any,
        SimpleNamespace(seek=lambda *_args: None, fileno=lambda: 7),
    )

    with pytest.raises(TimeoutError, match="file lock acquisition timed out"):
        file_lock._acquire_file_lock(stream)


def test_windows_file_lock_preserves_non_retryable_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import errno
    import sys
    from types import SimpleNamespace

    import ai4binance.events.file_lock as file_lock

    expected = OSError(errno.EBADF, "fixture invalid handle")

    def locking(_descriptor: int, _operation: int, _size: int) -> None:
        raise expected

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(locking=locking, LK_NBLCK=1),
    )
    stream = cast(
        Any,
        SimpleNamespace(seek=lambda *_args: None, fileno=lambda: 7),
    )

    with pytest.raises(OSError, match="fixture invalid handle") as raised:
        file_lock._acquire_file_lock(stream)

    assert raised.value is expected

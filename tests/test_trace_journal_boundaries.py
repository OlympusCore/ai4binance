"""Canonical traces reject corrupt identity, hashes and duplicate journal entries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ai4binance.events.journal import DiskEventJournal, EventJournalCorruptionError
from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    TraceabilityAuditReport,
    TraceabilityStatus,
    _json_text_tuple,
)


def _record(trace_id: str = "trace:test") -> CanonicalTraceRecord:
    return CanonicalTraceRecord.create(
        trace_id=trace_id,
        trace_kind=ConsequentialTraceKind.DECISION,
        subject_ref="decision:test",
        subject_type="DECISION",
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        event_name="DECISION_RECORDED",
        event_status="NO_TRADE",
        evidence_refs=("evidence:test",),
        subject_sha256="a" * 64,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"trace_id": ""}, "required"),
        ({"event_name": "lowercase"}, "uppercase snake"),
        ({"occurred_at": datetime(2026, 9, 1)}, "timezone-aware"),
        ({"evidence_refs": (" ",)}, "non-empty"),
        ({"blockers": ("same", "same")}, "unique"),
        ({"subject_sha256": "bad"}, "sha256"),
        ({"execution_allowed": True}, "authorize"),
        ({"promotion_status": "LIVE"}, "authorize"),
        ({"record_sha256": "0" * 64}, "hash is invalid"),
        ({"trace_kind": ConsequentialTraceKind.APPROVAL}, "approval_ref"),
    ],
)
def test_trace_contract_rejects_invalid_evidence(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_record(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"journal_path": Path("relative.jsonl")}, "absolute"),
        ({"record_count": -1}, "non-negative"),
        ({"blockers": ("MISSING",)}, "passing.*blockers"),
        ({"status": TraceabilityStatus.RUNNING_WITH_BLOCKERS}, "requires blockers"),
    ],
)
def test_trace_audit_rejects_inconsistent_status(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    report = TraceabilityAuditReport(
        tmp_path / "trace.jsonl", TraceabilityStatus.PASS, 0, 0
    )
    with pytest.raises(ValueError, match=message):
        replace(report, **changes)


def test_trace_journal_duplicate_is_idempotent_only_through_explicit_api(
    tmp_path: Path,
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "trace.jsonl")
    record = _record()
    assert journal.append_if_absent(record) is True
    assert journal.append_if_absent(record) is False
    with pytest.raises(ValueError, match="already exists"):
        journal.append(record)
    assert journal.records() == (record,)


@pytest.mark.parametrize("value", [None, "{}"])
def test_trace_wire_lists_reject_wrong_shape(value: object) -> None:
    with pytest.raises(ValueError, match=r"JSON text|decode to a list"):
        _json_text_tuple(value, "evidence")


def test_trace_batch_preserves_records_with_two_history_validations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only-batch.jsonl", durable=True)
    journal.append(_record())
    records = tuple(_record(f"trace:batch:{index}") for index in range(11))
    scans = 0
    original = DiskEventJournal._load_unlocked

    def load(instance: DiskEventJournal) -> tuple[Any, ...]:
        nonlocal scans
        scans += 1
        return original(instance)

    monkeypatch.setattr(DiskEventJournal, "_load_unlocked", load)
    events = journal.append_batch(records)
    assert scans == 2
    assert tuple(event.sequence for event in events) == tuple(range(2, 13))
    assert journal.records() == (_record(), *records)
    assert all(record.execution_allowed is False for record in journal.records())


@pytest.mark.parametrize("duplicate_existing", [True, False])
def test_trace_batch_rejects_duplicates_without_partial_append(
    tmp_path: Path, duplicate_existing: bool
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only-duplicates.jsonl")
    journal.append(_record())
    before = journal.path.read_bytes()
    new = _record("trace:new")
    duplicate = _record() if duplicate_existing else new
    with pytest.raises(ValueError, match="already exists"):
        journal.append_batch((new, duplicate))
    assert journal.path.read_bytes() == before


def test_trace_batch_rejects_corrupt_history_without_writing(tmp_path: Path) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only-corrupt.jsonl")
    journal.append(_record())
    corrupt = journal.path.read_bytes().replace(b"NO_TRADE", b"UNKNOWN!")
    journal.path.write_bytes(corrupt)
    with pytest.raises(EventJournalCorruptionError):
        journal.append_batch((_record("trace:new"),))
    assert journal.path.read_bytes() == corrupt


def test_trace_factory_uses_validated_history_and_preserves_duplicate_veto(
    tmp_path: Path,
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only-factory.jsonl")
    record = _record()
    journal.append(record)
    before = journal.path.read_bytes()

    def duplicate(
        history: tuple[CanonicalTraceRecord, ...],
    ) -> tuple[CanonicalTraceRecord, ...]:
        assert history == (record,)
        return (_record("trace:new"), record)

    with pytest.raises(ValueError, match="already exists"):
        journal.append_batch_factory(duplicate)
    assert journal.path.read_bytes() == before

    corrupt = before.replace(b"NO_TRADE", b"UNKNOWN!")
    journal.path.write_bytes(corrupt)

    def must_not_run(
        _history: tuple[CanonicalTraceRecord, ...],
    ) -> tuple[CanonicalTraceRecord, ...]:
        pytest.fail("factory must not run against corrupt history")

    with pytest.raises(EventJournalCorruptionError):
        journal.append_batch_factory(must_not_run)
    assert journal.path.read_bytes() == corrupt


def test_trace_batches_serialize_distinct_instances(tmp_path: Path) -> None:
    path = tmp_path / "test-only-concurrent.jsonl"

    def append(index: int) -> None:
        CanonicalTraceJournal(path).append_batch(
            tuple(_record(f"trace:{index}:{item}") for item in range(3))
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(append, range(8)))
    assert len(CanonicalTraceJournal(path).records()) == 24

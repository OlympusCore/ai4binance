"""Canonical traces reject corrupt identity, hashes and duplicate journal entries."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    TraceabilityAuditReport,
    TraceabilityStatus,
    _json_text_tuple,
)


def _record() -> CanonicalTraceRecord:
    return CanonicalTraceRecord.create(
        trace_id="trace:test",
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

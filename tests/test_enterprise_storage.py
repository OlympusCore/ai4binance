from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.enterprise.contracts import (
    AuditEvent,
    WorkflowIdentity,
)
from ai4binance.enterprise.storage import EnterpriseAuditJournal
from ai4binance.storage import VerificationStatus

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity(
        "wo-1",
        "run-1",
        "trace-1",
        NOW,
        snapshot_id="snapshot-1",
    )


def test_enterprise_audit_journal_appends_with_destination_verification(
    tmp_path: Path,
) -> None:
    journal = EnterpriseAuditJournal(tmp_path / "enterprise-audit.jsonl")
    event = AuditEvent(
        identity(),
        "audit-1",
        "ENTERPRISE_CONTRACT_ADDED",
        "codex",
        "proposal-1",
        ("artifact:test-report",),
    )

    result = journal.append_verified(event)
    line = json.loads((tmp_path / "enterprise-audit.jsonl").read_text("utf-8"))

    assert result.status is VerificationStatus.VERIFIED
    assert result.operation == "jsonl_append"
    assert result.expected_sha256 == result.observed_sha256
    assert line["event_type"] == "ENTERPRISE_CONTRACT_ADDED"
    assert line["snapshot_id"] == "snapshot-1"
    assert line["payload"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert line["payload"]["promotion_status"] == "RESEARCH_ONLY"

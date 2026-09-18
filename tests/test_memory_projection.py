from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.core.contracts.memory import (
    MemoryAuthorityCeiling,
    MemoryClassification,
    MemoryLifecycleStatus,
    MemoryProducerRole,
    MemoryRecord,
    MemoryTrustClass,
    MemoryType,
    memory_canonical_sha256,
)
from ai4binance.infrastructure.persistence.memory import JsonlMemoryStore
from ai4binance.infrastructure.persistence.memory_projection import (
    MemoryProjectionDriftError,
    SqliteMemoryProjection,
)

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)
HASH = "a" * 64


def _active_memory(memory_id: str, body: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.SEMANTIC_MEMORY,
        subject_key="strategy:pullback_continuation_v4",
        body=body,
        event_time=NOW,
        observed_at=NOW + timedelta(seconds=3),
        recorded_at=NOW + timedelta(seconds=4),
        valid_from=NOW,
        valid_until=None,
        source_refs=("runtime/artifacts/learning/closure.json",),
        evidence_refs=("decision:btc-no-trade",),
        source_hashes=(HASH,),
        content_hash=memory_canonical_sha256(
            {
                "body": body,
                "memory_type": MemoryType.SEMANTIC_MEMORY.value,
                "subject_key": "strategy:pullback_continuation_v4",
            }
        ),
        producer_role=MemoryProducerRole.OBSERVER,
        trust_class=MemoryTrustClass.VERIFIED_SYSTEM_EVIDENCE,
        authority_ceiling=MemoryAuthorityCeiling.ADVISORY,
        status=MemoryLifecycleStatus.ACTIVE,
        classification=MemoryClassification.VERIFIED_MARKET_EVIDENCE,
        approval_record_id="approval-1",
        verification_record_id="verification-1",
    )


def test_projection_rebuild_is_deterministic_and_preserves_journal_records(
    tmp_path: Path,
) -> None:
    records = (
        _active_memory("mem:two", "Spread percentile raised false-positive risk."),
        _active_memory("mem:one", "Liquidity deterioration requires a no-trade hint."),
    )
    journal = JsonlMemoryStore(tmp_path / "memory.jsonl")
    for record in records:
        journal.append(record)
    projection = SqliteMemoryProjection(tmp_path / "memory.sqlite3")

    first = projection.rebuild_from_journal(journal)
    second = projection.rebuild_from_journal(journal)

    assert first.projection_hash == second.projection_hash
    assert first.record_count == 2
    assert projection.load_verified_records(journal) == tuple(
        sorted(records, key=lambda record: record.memory_id)
    )
    assert projection.search_body("Spread") == (records[0],)
    assert projection.audit_against_journal(journal).blockers == ()


def test_projection_drift_blocks_verified_reads_until_rebuilt(
    tmp_path: Path,
) -> None:
    record = _active_memory("mem:drift", "A validated failure mode remains advisory.")
    journal = JsonlMemoryStore(tmp_path / "memory.jsonl")
    journal.append(record)
    projection = SqliteMemoryProjection(tmp_path / "memory.sqlite3")
    projection.rebuild_from_journal(journal)
    connection = sqlite3.connect(projection.path)
    try:
        connection.execute(
            "UPDATE projection_metadata SET value = ? WHERE key = 'projection_hash'",
            ("b" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    audit = projection.audit_against_journal(journal)

    assert audit.status == "RUNNING_WITH_BLOCKERS"
    assert audit.blockers == ("MEMORY_PROJECTION_DRIFT",)
    with pytest.raises(MemoryProjectionDriftError, match="MEMORY_PROJECTION_DRIFT"):
        projection.load_verified_records(journal)

    rebuilt = projection.rebuild_from_journal(journal)

    assert projection.load_verified_records(journal) == (record,)
    assert rebuilt.projection_hash == audit.expected_hash


def test_projection_corruption_is_rebuilt_from_authoritative_journal(
    tmp_path: Path,
) -> None:
    record = _active_memory("mem:corruption", "Projection corruption must fail closed.")
    journal = JsonlMemoryStore(tmp_path / "memory.jsonl")
    journal.append(record)
    projection = SqliteMemoryProjection(tmp_path / "memory.sqlite3")
    projection.path.write_text("not a SQLite database", encoding="utf-8")

    audit = projection.audit_against_journal(journal)

    assert audit.status == "RUNNING_WITH_BLOCKERS"
    assert audit.blockers == ("MEMORY_PROJECTION_UNAVAILABLE",)
    with pytest.raises(MemoryProjectionDriftError, match="UNAVAILABLE"):
        projection.load_verified_records(journal)

    projection.rebuild_from_journal(journal)

    assert projection.load_verified_records(journal) == (record,)


def test_projection_rejects_duplicate_memory_ids(tmp_path: Path) -> None:
    record = _active_memory("mem:duplicate", "Duplicate identity must remain blocked.")
    projection = SqliteMemoryProjection(tmp_path / "memory.sqlite3")

    with pytest.raises(ValueError, match="unique ids"):
        projection.rebuild((record, replace(record)))

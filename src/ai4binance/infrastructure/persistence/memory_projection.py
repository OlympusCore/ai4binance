"""Rebuildable SQLite read projection for the authoritative memory journal."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from ai4binance.core.contracts.memory import MemoryRecord, memory_canonical_sha256
from ai4binance.infrastructure.persistence.memory import (
    JsonlMemoryStore,
    memory_record_from_payload,
)
from ai4binance.infrastructure.persistence.safe_json import to_primitive


class MemoryProjectionDriftError(RuntimeError):
    """Raised when a read projection diverges from its authoritative journal."""


@dataclass(frozen=True, slots=True)
class MemoryProjectionRebuildResult:
    projection_hash: str
    record_count: int
    status: str = "READY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if len(self.projection_hash) != 64:
            raise ValueError("memory projection hash is invalid")
        if self.record_count < 0:
            raise ValueError("memory projection record count is invalid")
        if self.status != "READY":
            raise ValueError("memory projection rebuild status is invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory projection cannot authorize trading")


@dataclass(frozen=True, slots=True)
class MemoryProjectionAudit:
    expected_hash: str
    actual_hash: str | None
    record_count: int
    blockers: tuple[str, ...] = ()
    status: str = "READY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if len(self.expected_hash) != 64:
            raise ValueError("memory projection expected hash is invalid")
        if self.actual_hash is not None and len(self.actual_hash) != 64:
            raise ValueError("memory projection actual hash is invalid")
        if self.record_count < 0:
            raise ValueError("memory projection record count is invalid")
        if bool(self.blockers) != (self.status == "RUNNING_WITH_BLOCKERS"):
            raise ValueError("memory projection audit status must reflect blockers")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory projection audit cannot authorize trading")


@dataclass(frozen=True, slots=True)
class SqliteMemoryProjection:
    """A disposable SQLite read model derived only from JSONL memory records."""

    path: Path

    def rebuild_from_journal(
        self,
        journal: JsonlMemoryStore,
    ) -> MemoryProjectionRebuildResult:
        return self.rebuild(journal.load_recent())

    def rebuild(
        self,
        records: tuple[MemoryRecord, ...],
    ) -> MemoryProjectionRebuildResult:
        _require_unique_record_ids(records)
        ordered_records = tuple(sorted(records, key=lambda record: record.memory_id))
        projection_hash = _projection_hash(ordered_records)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(
            f".{self.path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            connection = sqlite3.connect(temporary_path)
            try:
                _create_schema(connection)
                for record in ordered_records:
                    payload = _payload(record)
                    connection.execute(
                        """
                        INSERT INTO memory_records (
                            memory_id, content_hash, status, subject_key, memory_type,
                            classification, market_type, symbol, strategy_id,
                            setup_type,
                            recorded_at, valid_from, valid_until, payload
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.memory_id,
                            record.content_hash,
                            record.status.value,
                            record.subject_key,
                            record.memory_type.value,
                            record.classification.value,
                            record.market_type,
                            record.symbol,
                            record.strategy_id,
                            record.setup_type,
                            record.effective_recorded_at.isoformat(),
                            record.valid_from.isoformat(),
                            (
                                record.valid_until.isoformat()
                                if record.valid_until is not None
                                else None
                            ),
                            payload,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO memory_fts (memory_id, body) VALUES (?, ?)",
                        (record.memory_id, record.body),
                    )
                connection.executemany(
                    "INSERT INTO projection_metadata (key, value) VALUES (?, ?)",
                    (
                        ("projection_hash", projection_hash),
                        ("record_count", str(len(ordered_records))),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        return MemoryProjectionRebuildResult(
            projection_hash=projection_hash,
            record_count=len(ordered_records),
        )

    def load_records(self) -> tuple[MemoryRecord, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT payload FROM memory_records ORDER BY memory_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(memory_record_from_payload(json.loads(row[0])) for row in rows)

    def search_body(self, query: str, *, limit: int = 20) -> tuple[MemoryRecord, ...]:
        if not query.strip():
            raise ValueError("memory projection search query is required")
        if limit < 1:
            raise ValueError("memory projection search limit must be positive")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT records.payload
                FROM memory_fts
                INNER JOIN memory_records AS records
                    ON records.memory_id = memory_fts.memory_id
                WHERE memory_fts MATCH ?
                ORDER BY bm25(memory_fts), records.memory_id
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(memory_record_from_payload(json.loads(row[0])) for row in rows)

    def audit_against_journal(self, journal: JsonlMemoryStore) -> MemoryProjectionAudit:
        records = journal.load_recent()
        expected_hash = _projection_hash(records)
        try:
            connection = self._connect()
            try:
                metadata = dict(
                    connection.execute(
                        "SELECT key, value FROM projection_metadata"
                    ).fetchall()
                )
                record_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM memory_records"
                    ).fetchone()[0]
                )
            finally:
                connection.close()
        except (OSError, sqlite3.DatabaseError, ValueError):
            return MemoryProjectionAudit(
                expected_hash=expected_hash,
                actual_hash=None,
                record_count=0,
                blockers=("MEMORY_PROJECTION_UNAVAILABLE",),
                status="RUNNING_WITH_BLOCKERS",
            )
        actual_hash = metadata.get("projection_hash")
        expected_count = len(records)
        if actual_hash != expected_hash or record_count != expected_count:
            return MemoryProjectionAudit(
                expected_hash=expected_hash,
                actual_hash=actual_hash,
                record_count=record_count,
                blockers=("MEMORY_PROJECTION_DRIFT",),
                status="RUNNING_WITH_BLOCKERS",
            )
        return MemoryProjectionAudit(
            expected_hash=expected_hash,
            actual_hash=actual_hash,
            record_count=record_count,
        )

    def load_verified_records(
        self,
        journal: JsonlMemoryStore,
    ) -> tuple[MemoryRecord, ...]:
        audit = self.audit_against_journal(journal)
        if audit.blockers:
            raise MemoryProjectionDriftError(
                "memory projection cannot serve verified retrieval: "
                + ", ".join(audit.blockers)
            )
        return self.load_records()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(f"memory projection does not exist: {self.path}")
        return sqlite3.connect(self.path)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE projection_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE memory_records (
            memory_id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            classification TEXT NOT NULL,
            market_type TEXT,
            symbol TEXT,
            strategy_id TEXT,
            setup_type TEXT,
            recorded_at TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            payload TEXT NOT NULL
        );
        CREATE INDEX memory_records_temporal_idx
            ON memory_records (recorded_at, valid_from, valid_until);
        CREATE INDEX memory_records_entity_idx
            ON memory_records (subject_key, market_type, symbol, strategy_id);
        CREATE VIRTUAL TABLE memory_fts USING fts5(memory_id UNINDEXED, body);
        """
    )


def _payload(record: MemoryRecord) -> str:
    return json.dumps(
        to_primitive(record),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _projection_hash(records: tuple[MemoryRecord, ...]) -> str:
    _require_unique_record_ids(records)
    return memory_canonical_sha256(
        {
            "records": tuple(
                json.loads(_payload(record))
                for record in sorted(records, key=lambda record: record.memory_id)
            )
        }
    )


def _require_unique_record_ids(records: tuple[MemoryRecord, ...]) -> None:
    if len({record.memory_id for record in records}) != len(records):
        raise ValueError("memory projection records must have unique ids")

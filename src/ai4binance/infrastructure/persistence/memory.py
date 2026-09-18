"""JSONL persistence adapter for governed memory records."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from ai4binance.core.contracts.memory import (
    MemoryAdvisoryEffect,
    MemoryApplicabilityScope,
    MemoryAuthorityCeiling,
    MemoryClassification,
    MemoryConflict,
    MemoryConflictRecord,
    MemoryConflictReviewStatus,
    MemoryConflictType,
    MemoryLifecycleStatus,
    MemoryProducerRole,
    MemoryRecord,
    MemoryRetrievalPolicy,
    MemoryTrustClass,
    MemoryType,
)
from ai4binance.domain.memory_metrics import (
    MemoryRuntimeMetricEvent,
    MemoryRuntimeMetricsRecorder,
    MemoryRuntimeOperation,
)
from ai4binance.infrastructure.persistence.safe_json import (
    JsonlAuditStore,
    SecretRedactor,
    read_bounded_jsonl_tail,
    to_primitive,
)


@dataclass(frozen=True, slots=True)
class JsonlMemoryStore:
    path: Path
    max_lines: int = 2_000
    max_bytes: int = 2_000_000
    metrics_recorder: MemoryRuntimeMetricsRecorder | None = None

    def append(self, record: MemoryRecord) -> None:
        with JsonlAuditStore(self.path)._synchronized():
            self._append_unlocked(record)

    def _append_unlocked(self, record: MemoryRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        latest = self._latest_identity_unlocked(record.memory_id)
        for existing in () if latest is None else (latest,):
            if existing == record:
                self._record_duplicate_rejection()
                return
            if existing.content_hash != record.content_hash:
                raise ValueError(
                    "memory JSONL duplicate identity has conflicting content"
                )
            if record.effective_recorded_at <= existing.effective_recorded_at:
                raise ValueError("memory JSONL revision must advance recorded time")
            if existing.status in {
                MemoryLifecycleStatus.REVOKED,
                MemoryLifecycleStatus.REJECTED,
                MemoryLifecycleStatus.EXPIRED,
                MemoryLifecycleStatus.SUPERSEDED,
            }:
                raise ValueError("terminal memory requires a new candidate identity")
            if (
                replace(
                    existing,
                    status=record.status,
                    recorded_at=record.recorded_at,
                    approval_record_id=record.approval_record_id,
                    verification_record_id=record.verification_record_id,
                    revoked_at=record.revoked_at,
                    expired_at=record.expired_at,
                    superseded_at=record.superseded_at,
                    blockers=record.blockers,
                )
                != record
            ):
                raise ValueError("memory JSONL revision changed immutable evidence")
        payload = SecretRedactor().redact(to_primitive(record))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            stream.write("\n")
        self._record_store_append()

    def _latest_identity_unlocked(self, memory_id: str) -> MemoryRecord | None:
        """Check identity across the authoritative journal, beyond retrieval limits.

        Stream bounded individual records so a revoked identity cannot become
        writable again merely because its last revision aged out of the tail.
        """
        if not self.path.exists():
            return None
        latest: MemoryRecord | None = None
        with self.path.open("rb") as stream:
            while raw_line := stream.readline(self.max_bytes + 1):
                if len(raw_line) > self.max_bytes:
                    raise ValueError("memory JSONL record exceeds bounded read limit")
                payload = json.loads(raw_line)
                if not isinstance(payload, dict):
                    raise ValueError("memory JSONL record must be an object")
                if payload.get("memory_id") != memory_id:
                    continue
                record = memory_record_from_payload(payload)
                if latest is not None and (
                    latest.content_hash != record.content_hash
                    or record.effective_recorded_at <= latest.effective_recorded_at
                ):
                    raise ValueError("memory JSONL revision lineage is invalid")
                latest = record
        return latest

    def load_recent(
        self, *, as_of_system_time: datetime | None = None
    ) -> tuple[MemoryRecord, ...]:
        with JsonlAuditStore(self.path)._synchronized():
            return self._load_recent_unlocked(as_of_system_time=as_of_system_time)

    def _load_recent_unlocked(
        self, *, as_of_system_time: datetime | None = None
    ) -> tuple[MemoryRecord, ...]:
        if not self.path.exists():
            return ()
        rows = read_bounded_jsonl_tail(
            self.path,
            max_lines=self.max_lines,
            max_bytes=self.max_bytes,
        )
        records: dict[str, MemoryRecord] = {}
        for row in rows:
            payload = json.loads(row.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("memory JSONL record must be an object")
            record = memory_record_from_payload(payload)
            if (
                as_of_system_time is not None
                and record.effective_recorded_at > as_of_system_time
            ):
                continue
            previous = records.get(record.memory_id)
            if previous is not None and (
                previous.content_hash != record.content_hash
                or record.effective_recorded_at <= previous.effective_recorded_at
            ):
                raise ValueError("memory JSONL revision lineage is invalid")
            records[record.memory_id] = record
        return tuple(records.values())

    def _record_store_append(self) -> None:
        if self.metrics_recorder is not None:
            self.metrics_recorder.record(
                MemoryRuntimeMetricEvent(
                    operation=MemoryRuntimeOperation.STORE_APPEND,
                )
            )

    def _record_duplicate_rejection(self) -> None:
        if self.metrics_recorder is not None:
            self.metrics_recorder.record(
                MemoryRuntimeMetricEvent(
                    operation=MemoryRuntimeOperation.STORE_APPEND,
                    duplicate_rejection_count=1,
                )
            )


@dataclass(frozen=True, slots=True)
class JsonlMemoryConflictStore:
    path: Path
    max_lines: int = 2_000
    max_bytes: int = 2_000_000

    def append(self, record: MemoryConflictRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = SecretRedactor().redact(to_primitive(record))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            stream.write("\n")

    def load_recent(self) -> tuple[MemoryConflictRecord, ...]:
        if not self.path.exists():
            return ()
        rows = read_bounded_jsonl_tail(
            self.path,
            max_lines=self.max_lines,
            max_bytes=self.max_bytes,
        )
        records: list[MemoryConflictRecord] = []
        for row in rows:
            payload = json.loads(row.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("memory conflict JSONL record must be an object")
            records.append(_conflict_record_from_payload(payload))
        return tuple(records)


def memory_record_from_payload(payload: dict[str, Any]) -> MemoryRecord:
    """Deserialize one canonical memory journal payload."""
    return MemoryRecord(
        memory_id=_text(payload, "memory_id"),
        memory_type=MemoryType(_text(payload, "memory_type")),
        subject_key=_text(payload, "subject_key"),
        body=_text(payload, "body"),
        event_time=_dt(payload, "event_time"),
        observed_at=_dt(payload, "observed_at"),
        valid_from=_dt(payload, "valid_from"),
        valid_until=_optional_dt(payload, "valid_until"),
        source_refs=_texts(payload, "source_refs"),
        evidence_refs=_texts(payload, "evidence_refs"),
        source_hashes=_texts(payload, "source_hashes"),
        content_hash=_text(payload, "content_hash"),
        producer_role=MemoryProducerRole(_text(payload, "producer_role")),
        trust_class=MemoryTrustClass(_text(payload, "trust_class")),
        authority_ceiling=MemoryAuthorityCeiling(_text(payload, "authority_ceiling")),
        status=MemoryLifecycleStatus(_text(payload, "status")),
        recorded_at=_optional_dt(payload, "recorded_at"),
        superseded_at=_optional_dt(payload, "superseded_at"),
        revoked_at=_optional_dt(payload, "revoked_at"),
        expired_at=_optional_dt(payload, "expired_at"),
        applicability_scope=MemoryApplicabilityScope(
            payload.get("applicability_scope", MemoryApplicabilityScope.GLOBAL.value)
        ),
        classification=MemoryClassification(
            payload.get("classification", MemoryClassification.PUBLIC_RESEARCH.value)
        ),
        market_type=_optional_text(payload, "market_type"),
        symbol=_optional_text(payload, "symbol"),
        strategy_id=_optional_text(payload, "strategy_id"),
        setup_type=_optional_text(payload, "setup_type"),
        regime_tags=_texts(payload, "regime_tags"),
        timeframe_tags=_texts(payload, "timeframe_tags"),
        supersedes=_texts(payload, "supersedes"),
        contradicts=_texts(payload, "contradicts"),
        retention_policy=_text(payload, "retention_policy"),
        retrieval_policy=MemoryRetrievalPolicy(_text(payload, "retrieval_policy")),
        advisory_effect=MemoryAdvisoryEffect(
            payload.get("advisory_effect", MemoryAdvisoryEffect.WARN.value)
        ),
        failure_mode_code=_optional_text(payload, "failure_mode_code"),
        reason_codes=_texts(payload, "reason_codes"),
        confidence=_float(payload, "confidence"),
        cycle_id=_optional_text(payload, "cycle_id"),
        snapshot_id=_optional_text(payload, "snapshot_id"),
        decision_id=_optional_text(payload, "decision_id"),
        approval_record_id=_optional_text(payload, "approval_record_id"),
        verification_record_id=_optional_text(payload, "verification_record_id"),
        blockers=_texts(payload, "blockers"),
        execution_allowed=bool(payload.get("execution_allowed", False)),
        signal_authority=bool(payload.get("signal_authority", False)),
        live_eligibility_status=_text(payload, "live_eligibility_status"),
    )


def _conflict_record_from_payload(payload: dict[str, Any]) -> MemoryConflictRecord:
    conflict_payload = payload.get("conflict")
    if not isinstance(conflict_payload, dict):
        raise ValueError("memory conflict JSONL field conflict must be an object")
    return MemoryConflictRecord(
        conflict=MemoryConflict(
            conflict_id=_text(conflict_payload, "conflict_id"),
            conflict_type=MemoryConflictType(_text(conflict_payload, "conflict_type")),
            subject_key=_text(conflict_payload, "subject_key"),
            memory_ids=_texts(conflict_payload, "memory_ids"),
            reason_codes=_texts(conflict_payload, "reason_codes"),
        ),
        detected_at=_dt(payload, "detected_at"),
        review_status=MemoryConflictReviewStatus(_text(payload, "review_status")),
        reviewer_ref=_optional_text(payload, "reviewer_ref"),
        resolution_ref=_optional_text(payload, "resolution_ref"),
        blockers=_texts(payload, "blockers"),
        execution_allowed=bool(payload.get("execution_allowed", False)),
        live_eligibility_status=_text(payload, "live_eligibility_status"),
    )


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"memory JSONL field {key} must be text")
    return value


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"memory JSONL field {key} must be text")
    return value


def _texts(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"memory JSONL field {key} must be a text list")
    return tuple(value)


def _dt(payload: dict[str, Any], key: str) -> datetime:
    return datetime.fromisoformat(_text(payload, key))


def _optional_dt(payload: dict[str, Any], key: str) -> datetime | None:
    value = _optional_text(payload, key)
    return None if value is None else datetime.fromisoformat(value)


def _float(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (float, int)):
        raise ValueError(f"memory JSONL field {key} must be numeric")
    return float(value)

"""DGE audit, decision, and replay-ready persistence helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.governance.adapters import DgeEvaluationRecord
from ai4binance.governance.dge_models import GovernedDecision
from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import VerifiedWriteResult, verified
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class DgePersistenceResult:
    """Verified append result for one DGE artifact."""

    decision_id: str
    event_result: VerifiedWriteResult
    replay_result: VerifiedWriteResult | None = None


def persist_dge_decision_event(
    root: Path,
    decision: GovernedDecision,
    *,
    source: str,
    timestamp: datetime | None = None,
    idempotent: bool = False,
) -> VerifiedWriteResult:
    """Append one secret-redacted DGE decision event."""

    store = _audit_store(_event_path(root))
    return _append_record(
        store,
        AuditEvent(
            "DGE_DECISION_RECORDED",
            timestamp if timestamp is not None else datetime.now(UTC),
            {
                "source": source,
                "decision": _mapping(to_primitive(decision)),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            snapshot_id=decision.decision_id,
        ),
        idempotent=idempotent,
    )


def persist_dge_evaluation_record(
    root: Path,
    record: DgeEvaluationRecord,
    *,
    idempotent: bool = False,
) -> DgePersistenceResult:
    """Persist one DGE event plus replay-ready candidate/context snapshot."""

    timestamp = (
        datetime.fromisoformat(record.decision.timestamp_utc)
        if idempotent
        else datetime.now(UTC)
    )
    event_result = persist_dge_decision_event(
        root,
        record.decision,
        source=record.source,
        timestamp=timestamp,
        idempotent=idempotent,
    )
    store = _audit_store(_decision_path(root))
    replay_result = _append_record(
        store,
        AuditEvent(
            "DGE_DECISION_REPLAY_RECORD",
            timestamp,
            {
                "source": record.source,
                "candidate": _mapping(to_primitive(record.candidate)),
                "context": _mapping(to_primitive(record.context)),
                "decision": _mapping(to_primitive(record.decision)),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            snapshot_id=record.decision.decision_id,
        ),
        idempotent=idempotent,
    )
    return DgePersistenceResult(
        decision_id=record.decision.decision_id,
        event_result=event_result,
        replay_result=replay_result,
    )


def _append_record(
    store: JsonlAuditStore,
    event: AuditEvent,
    *,
    idempotent: bool,
) -> VerifiedWriteResult:
    if not idempotent:
        return store.append_verified(event)
    result = store.append_verified_idempotent(event)
    # An exact duplicate has already been compared under the journal lock.
    return (
        result
        if result is not None
        else verified(
            store.path,
            event.snapshot_id or event.event_type,
            operation="jsonl_existing_verified",
        )
    )


def dge_decision_log_path(root: Path) -> Path:
    return _active_audit_log_path(_decision_path(root))


def dge_event_log_path(root: Path) -> Path:
    return _active_audit_log_path(_event_path(root))


def _decision_path(root: Path) -> Path:
    return (
        root / "runtime" / "data" / "governance" / "decisions" / "dge_decisions.jsonl"
    )


def _event_path(root: Path) -> Path:
    return root / "runtime" / "data" / "governance" / "events" / "dge_events.jsonl"


def _audit_store(path: Path) -> JsonlAuditStore:
    """Open the immutable successor for legacy or new DGE audit journals."""

    store = JsonlAuditStore.chained_successor(path)
    store.durable = True
    return store


def _active_audit_log_path(path: Path) -> Path:
    """Return the sealed journal that contains current DGE audit records.

    Calling ``chained_successor`` only after a journal exists keeps read-only
    replay from creating an empty audit artifact, while writes use the same
    resolver through ``_audit_store``.
    """

    successor_path = path.with_suffix(".chained.jsonl")
    if not path.exists() and not successor_path.exists():
        return path
    return JsonlAuditStore.chained_successor(path).path


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise TypeError("DGE persistence payload must be a mapping")

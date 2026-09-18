"""DGE audit, decision, and replay-ready persistence helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.governance.adapters import DgeEvaluationRecord
from ai4binance.governance.dge_models import GovernedDecision
from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import VerifiedWriteResult
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
) -> VerifiedWriteResult:
    """Append one secret-redacted DGE decision event."""

    return _audit_store(_event_path(root)).append_verified(
        AuditEvent(
            "DGE_DECISION_RECORDED",
            datetime.now(UTC),
            {
                "source": source,
                "decision": _mapping(to_primitive(decision)),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            snapshot_id=decision.decision_id,
        )
    )


def persist_dge_evaluation_record(
    root: Path,
    record: DgeEvaluationRecord,
) -> DgePersistenceResult:
    """Persist one DGE event plus replay-ready candidate/context snapshot."""

    event_result = persist_dge_decision_event(
        root,
        record.decision,
        source=record.source,
    )
    replay_result = _audit_store(_decision_path(root)).append_verified(
        AuditEvent(
            "DGE_DECISION_REPLAY_RECORD",
            datetime.now(UTC),
            {
                "source": record.source,
                "candidate": _mapping(to_primitive(record.candidate)),
                "context": _mapping(to_primitive(record.context)),
                "decision": _mapping(to_primitive(record.decision)),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            snapshot_id=record.decision.decision_id,
        )
    )
    return DgePersistenceResult(
        decision_id=record.decision.decision_id,
        event_result=event_result,
        replay_result=replay_result,
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

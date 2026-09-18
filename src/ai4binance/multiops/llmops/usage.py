"""Append-only local model_usage ledger with destination verification."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.multiops.llmops.contracts import (
    ModelUsageRecord,
    TaskClass,
    TaskCriticality,
    TokenAccountingSource,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, read_bounded_jsonl_tail
from ai4binance.storage.destination_verification import VerifiedWriteResult


def default_model_usage_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or Path.cwd()).resolve()
    return root / "logs" / "model_governance" / "model_usage.jsonl"


@dataclass(frozen=True, slots=True)
class ModelUsageLedger:
    """Local-only ledger; records observations without changing routing."""

    path: Path

    @classmethod
    def at_repository(cls, repository_root: Path | None = None) -> ModelUsageLedger:
        return cls(default_model_usage_path(repository_root))

    def append(self, record: ModelUsageRecord) -> VerifiedWriteResult:
        payload = to_primitive(record)
        if not isinstance(payload, Mapping):
            raise TypeError("model usage payload must be a mapping")
        return JsonlAuditStore(self.path).append_verified(
            AuditEvent(
                event_type="MODEL_USAGE_RECORDED",
                timestamp=record.timestamp,
                snapshot_id=record.task_id,
                payload=cast(Mapping[str, object], payload),
            )
        )

    def read_recent(
        self, *, max_records: int = 200
    ) -> tuple[Mapping[str, object], ...]:
        if not self.path.exists():
            return ()
        records: list[Mapping[str, object]] = []
        for line in read_bounded_jsonl_tail(self.path, max_lines=max_records):
            parsed = json.loads(line)
            if not isinstance(parsed, Mapping):
                raise ValueError("model usage ledger record must be a mapping")
            if parsed.get("event_type") != "MODEL_USAGE_RECORDED":
                raise ValueError("model usage ledger event type is invalid")
            payload = parsed.get("payload")
            if not isinstance(payload, Mapping):
                raise ValueError("model usage ledger payload must be a mapping")
            records.append(cast(Mapping[str, object], payload))
        return tuple(records)


def unavailable_usage_record(
    *,
    task_id: str,
    task_type: str,
    task_class: TaskClass,
    criticality: TaskCriticality,
    sanitized_summary: str,
) -> ModelUsageRecord:
    """Build an explicit no-provider-data record without inventing counters."""

    return ModelUsageRecord(
        task_id=task_id,
        timestamp=datetime.now(UTC),
        task_type=task_type,
        task_class=task_class,
        criticality=criticality,
        token_accounting_source=TokenAccountingSource.UNAVAILABLE,
        sanitized_summary=sanitized_summary,
    )

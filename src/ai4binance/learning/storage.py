"""Atomic learning summary plus append-only audit persistence."""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.learning.models import LearningSummary
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class LearningStore:
    summary_path: Path
    audit_path: Path

    def save(self, summary: LearningSummary) -> None:
        primitive = cast(dict[str, object], to_primitive(summary))
        write_json_object_verified(
            self.summary_path,
            primitive,
            blocker="LEARNING_SUMMARY_DESTINATION_VERIFY_FAILED",
            subject_id=summary.summary_id,
            indent=2,
        )
        JsonlAuditStore(self.audit_path, durable=True).append_verified(
            AuditEvent(
                event_type="LEARNING_SUMMARY_CREATED",
                timestamp=summary.created_at,
                payload={"summary": primitive},
            )
        )

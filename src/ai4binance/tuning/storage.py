"""Append-only tuning experiment persistence."""

from dataclasses import dataclass

from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.tuning.models import TuningReport


@dataclass(frozen=True, slots=True)
class TuningAuditWriter:
    store: JsonlAuditStore

    def append(self, report: TuningReport) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="TUNING_REPORT",
                timestamp=report.created_at,
                payload={"report": to_primitive(report)},
            )
        )

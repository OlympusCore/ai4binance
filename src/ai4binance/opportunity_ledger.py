"""Secret-redacted persistence adapter for opportunity lifecycle evidence."""

from dataclasses import dataclass
from pathlib import Path

from ai4binance.opportunity_intelligence import OpportunityLifecycleEvent
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.storage.destination_verification import VerifiedWriteResult


@dataclass(frozen=True, slots=True)
class OpportunityLedgerWriter:
    """Append exact lifecycle events to the existing verified JSONL store."""

    path: Path
    durable: bool = True

    def append(self, event: OpportunityLifecycleEvent) -> VerifiedWriteResult | None:
        return JsonlAuditStore(
            self.path,
            durable=self.durable,
            tamper_evident=self.durable,
        ).append_verified_idempotent(
            AuditEvent(
                event_type=event.event_type.value,
                timestamp=event.event_time,
                payload=event.to_payload(),
                snapshot_id=event.event_id,
                schema_version=event.schema_version,
            )
        )


__all__ = ("OpportunityLedgerWriter",)

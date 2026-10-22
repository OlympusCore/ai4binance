"""Secret-redacted persistence adapter for opportunity lifecycle evidence."""

from dataclasses import dataclass
from pathlib import Path

from ai4binance.core.contracts.core_observation import consume_core_output
from ai4binance.opportunity_intelligence import OpportunityLifecycleEvent
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.storage.destination_verification import VerifiedWriteResult


@dataclass(frozen=True, slots=True)
class OpportunityLedgerWriter:
    """Append exact lifecycle events to the existing verified JSONL store."""

    path: Path
    durable: bool = True

    def append(self, event: OpportunityLifecycleEvent) -> VerifiedWriteResult | None:
        store = JsonlAuditStore(
            self.path,
            durable=self.durable,
            tamper_evident=self.durable,
        )
        return consume_core_output(
            "trade-opportunity-ledger",
            inputs=event,
            produce=event.to_payload,
            consume=lambda payload: store.append_verified_idempotent(
                AuditEvent(
                    event_type=event.event_type.value,
                    timestamp=event.event_time,
                    payload=payload,
                    snapshot_id=event.event_id,
                    schema_version=event.schema_version,
                )
            ),
        )


__all__ = ("OpportunityLedgerWriter",)

"""Append-only persistence for walk-forward validation evidence."""

from dataclasses import dataclass

from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.validation.models import WalkForwardReport


@dataclass(frozen=True, slots=True)
class WalkForwardAuditWriter:
    """Persist a complete validation report through the redacting audit store."""

    store: JsonlAuditStore

    def append(self, report: WalkForwardReport) -> None:
        self.store.append_verified(
            AuditEvent(
                event_type="WALK_FORWARD_REPORT",
                timestamp=report.created_at,
                payload={"report": to_primitive(report)},
            )
        )

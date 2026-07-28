"""Idempotent append-only audit persistence for snapshot-bound fusion results."""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import Lock

from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore
from ai4binance.whale_fusion.integration import WhaleFusionEnvelope


@dataclass(slots=True)
class FusionAuditWriter:
    path: Path
    durable: bool = False
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def append(self, envelope: WhaleFusionEnvelope) -> bool:
        """Append once across process restarts; return False for an existing record."""
        record_id = self.record_id(envelope)
        with self._lock:
            if record_id in self._existing_record_ids():
                return False
            store = JsonlAuditStore(self.path, durable=self.durable)
            store.append(
                AuditEvent(
                    event_type="WHALE_FUSION_RESULT",
                    timestamp=envelope.result.as_of,
                    snapshot_id=envelope.snapshot_id,
                    payload={
                        "record_id": record_id,
                        "symbol": envelope.symbol,
                        "result": envelope.result,
                    },
                )
            )
        return True

    @staticmethod
    def record_id(envelope: WhaleFusionEnvelope) -> str:
        payload = (
            f"{envelope.snapshot_id}|{envelope.symbol}|"
            f"{envelope.result.as_of.isoformat()}"
        )
        return "fusion:" + sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _existing_record_ids(self) -> frozenset[str]:
        if not self.path.exists():
            return frozenset()
        identifiers: set[str] = set()
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"fusion audit contains invalid JSON at line {line_number}"
                    ) from None
                if not isinstance(item, dict):
                    raise ValueError("fusion audit line must be an object")
                payload = item.get("payload")
                if isinstance(payload, dict):
                    record_id = payload.get("record_id")
                    if isinstance(record_id, str):
                        identifiers.add(record_id)
        return frozenset(identifiers)

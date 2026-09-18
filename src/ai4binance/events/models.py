"""Canonical immutable domain events with deterministic content hashes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """One ordered aggregate event suitable for deterministic replay."""

    event_id: str
    aggregate_id: str
    event_type: str
    sequence: int
    occurred_at: datetime
    payload: tuple[tuple[str, str], ...]
    previous_hash: str
    event_hash: str

    def __post_init__(self) -> None:
        identities = (self.event_id, self.aggregate_id, self.event_type)
        if any(not value.strip() for value in identities) or self.sequence < 1:
            raise ValueError("event identity and positive sequence are required")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("event timestamp must be timezone-aware")
        keys = tuple(key for key, _value in self.payload)
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("event payload keys must be non-empty and unique")
        if tuple(sorted(self.payload)) != self.payload:
            raise ValueError("event payload must be sorted")
        if self.event_hash != self.compute_hash(
            self.event_id,
            self.aggregate_id,
            self.event_type,
            self.sequence,
            self.occurred_at,
            self.payload,
            self.previous_hash,
        ):
            raise ValueError("event content hash is invalid")

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        aggregate_id: str,
        event_type: str,
        sequence: int,
        occurred_at: datetime,
        payload: tuple[tuple[str, str], ...] = (),
        previous_hash: str = "GENESIS",
    ) -> DomainEvent:
        ordered_payload = tuple(sorted(payload))
        digest = cls.compute_hash(
            event_id,
            aggregate_id,
            event_type,
            sequence,
            occurred_at,
            ordered_payload,
            previous_hash,
        )
        return cls(
            event_id=event_id,
            aggregate_id=aggregate_id,
            event_type=event_type,
            sequence=sequence,
            occurred_at=occurred_at,
            payload=ordered_payload,
            previous_hash=previous_hash,
            event_hash=digest,
        )

    @staticmethod
    def compute_hash(
        event_id: str,
        aggregate_id: str,
        event_type: str,
        sequence: int,
        occurred_at: datetime,
        payload: tuple[tuple[str, str], ...],
        previous_hash: str,
    ) -> str:
        canonical = json.dumps(
            {
                "aggregate_id": aggregate_id,
                "event_id": event_id,
                "event_type": event_type,
                "occurred_at": occurred_at.isoformat(),
                "payload": payload,
                "previous_hash": previous_hash,
                "sequence": sequence,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def payload_dict(self) -> dict[str, str]:
        return dict(self.payload)

"""Durable hash-linked event journal and deterministic restart recovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from ai4binance.events.bus import DeterministicEventBus, EventSubscriber
from ai4binance.events.models import DomainEvent


class EventJournalCorruptionError(RuntimeError):
    """Raised when persisted event evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class JournalCheckpoint:
    """Verified replay cursor; it never contains trading authority."""

    sequence: int
    event_hash: str
    created_at: datetime
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.sequence < 1 or len(self.event_hash) != 64:
            raise ValueError("checkpoint sequence and event hash are invalid")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("checkpoint timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class JournalRecovery:
    """Validated restart evidence and optional replay cursor."""

    events: tuple[DomainEvent, ...]
    checkpoint: JournalCheckpoint | None
    replay_from_sequence: int
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def events_after_checkpoint(self) -> tuple[DomainEvent, ...]:
        return tuple(
            event
            for event in self.events
            if event.sequence >= self.replay_from_sequence
        )


@dataclass(slots=True)
class DiskEventJournal:
    """Append-only JSONL journal with bounded records and atomic checkpoints."""

    path: Path
    checkpoint_path: Path | None = None
    durable: bool = True
    maximum_event_bytes: int = 65_536
    maximum_journal_bytes: int = 134_217_728
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.checkpoint_path is None:
            self.checkpoint_path = self.path.with_suffix(".checkpoint.json")
        limits = (self.maximum_event_bytes, self.maximum_journal_bytes)
        if min(limits) < 256 or self.maximum_event_bytes > self.maximum_journal_bytes:
            raise ValueError("journal size limits are invalid")

    def append(self, event: DomainEvent) -> None:
        """Validate against durable history before committing one complete line."""
        with self._lock:
            events = self._load_unlocked()
            validator = DeterministicEventBus(capacity=self._capacity())
            validator.replay(events)
            validator.publish(event)
            encoded = self._encode_event(event)
            current_size = self.path.stat().st_size if self.path.exists() else 0
            if current_size + len(encoded) > self.maximum_journal_bytes:
                raise OverflowError("event journal byte capacity exceeded")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                if self.durable:
                    os.fsync(stream.fileno())

    def load(self) -> tuple[DomainEvent, ...]:
        """Load and validate the complete journal; never skip corrupt records."""
        with self._lock:
            return self._load_unlocked()

    def recover(self) -> JournalRecovery:
        """Return validated events plus a verified checkpoint replay cursor."""
        with self._lock:
            events = self._load_unlocked()
            checkpoint = self._read_checkpoint_unlocked()
            replay_from = 1
            if checkpoint is not None:
                if checkpoint.sequence > len(events):
                    raise EventJournalCorruptionError(
                        "checkpoint sequence exceeds journal"
                    )
                matched = events[checkpoint.sequence - 1]
                if matched.event_hash != checkpoint.event_hash:
                    raise EventJournalCorruptionError(
                        "checkpoint hash does not match journal"
                    )
                replay_from = checkpoint.sequence + 1
            return JournalRecovery(events, checkpoint, replay_from)

    def checkpoint(self, *, created_at: datetime | None = None) -> JournalCheckpoint:
        """Atomically store a cursor for the latest fully durable event."""
        with self._lock:
            events = self._load_unlocked()
            if not events:
                raise ValueError("cannot checkpoint an empty journal")
            latest = events[-1]
            checkpoint = JournalCheckpoint(
                latest.sequence,
                latest.event_hash,
                created_at or datetime.now(UTC),
            )
            target = self._checkpoint_target()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(f"{target.suffix}.tmp")
            encoded = (
                json.dumps(
                    {
                        "created_at": checkpoint.created_at.isoformat(),
                        "event_hash": checkpoint.event_hash,
                        "schema_version": checkpoint.schema_version,
                        "sequence": checkpoint.sequence,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
                stream.flush()
                if self.durable:
                    os.fsync(stream.fileno())
            os.replace(temporary, target)
            return checkpoint

    def _load_unlocked(self) -> tuple[DomainEvent, ...]:
        if not self.path.exists():
            return ()
        data = self.path.read_bytes()
        if len(data) > self.maximum_journal_bytes:
            raise EventJournalCorruptionError("event journal exceeds byte capacity")
        if data and not data.endswith(b"\n"):
            raise EventJournalCorruptionError(
                "event journal has a partial final record"
            )
        events: list[DomainEvent] = []
        for line_number, raw_line in enumerate(data.splitlines(), start=1):
            if not raw_line or len(raw_line) + 1 > self.maximum_event_bytes:
                raise EventJournalCorruptionError(
                    f"event record {line_number} is empty or oversized"
                )
            try:
                payload = json.loads(raw_line)
                events.append(self._decode_event(payload))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise EventJournalCorruptionError(
                    f"event record {line_number} is invalid"
                ) from error
        try:
            validator = DeterministicEventBus(capacity=self._capacity())
            validator.replay(events)
        except (OverflowError, ValueError) as error:
            raise EventJournalCorruptionError(
                "event journal chain is invalid"
            ) from error
        return tuple(events)

    def _read_checkpoint_unlocked(self) -> JournalCheckpoint | None:
        target = self._checkpoint_target()
        if not target.exists():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError
            return JournalCheckpoint(
                sequence=int(payload["sequence"]),
                event_hash=str(payload["event_hash"]),
                created_at=datetime.fromisoformat(str(payload["created_at"])),
                schema_version=str(payload["schema_version"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise EventJournalCorruptionError("checkpoint is invalid") from error

    def _checkpoint_target(self) -> Path:
        if self.checkpoint_path is None:
            raise RuntimeError("checkpoint path was not initialized")
        return self.checkpoint_path

    def _capacity(self) -> int:
        return min(1_000_000, max(1, self.maximum_journal_bytes // 256))

    def _encode_event(self, event: DomainEvent) -> bytes:
        encoded = (
            json.dumps(
                {
                    "aggregate_id": event.aggregate_id,
                    "event_hash": event.event_hash,
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "occurred_at": event.occurred_at.isoformat(),
                    "payload": event.payload,
                    "previous_hash": event.previous_hash,
                    "sequence": event.sequence,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > self.maximum_event_bytes:
            raise OverflowError("event record exceeds byte capacity")
        return encoded

    @staticmethod
    def _decode_event(payload: object) -> DomainEvent:
        if not isinstance(payload, dict):
            raise TypeError
        raw_payload = payload["payload"]
        if not isinstance(raw_payload, list):
            raise TypeError
        event_payload = tuple((str(item[0]), str(item[1])) for item in raw_payload)
        return DomainEvent(
            event_id=str(payload["event_id"]),
            aggregate_id=str(payload["aggregate_id"]),
            event_type=str(payload["event_type"]),
            sequence=int(payload["sequence"]),
            occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
            payload=event_payload,
            previous_hash=str(payload["previous_hash"]),
            event_hash=str(payload["event_hash"]),
        )


@dataclass(slots=True)
class JournaledEventRuntime:
    """Persist-first event runtime that reconstructs state on restart."""

    journal: DiskEventJournal
    bus: DeterministicEventBus

    @classmethod
    def open(
        cls,
        journal: DiskEventJournal,
        *,
        capacity: int = 100_000,
    ) -> JournaledEventRuntime:
        recovery = journal.recover()
        bus = DeterministicEventBus(capacity=capacity)
        bus.replay(recovery.events)
        return cls(journal, bus)

    def subscribe(self, subscriber: EventSubscriber) -> None:
        self.bus.subscribe(subscriber)

    def publish(self, event: DomainEvent) -> None:
        self.journal.append(event)
        self.bus.publish(event)

    def snapshot(self) -> tuple[DomainEvent, ...]:
        return self.bus.snapshot()

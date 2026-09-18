"""Durable at-least-once delivery for the local event journal."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from ai4binance.events.bus import DeterministicEventBus
from ai4binance.events.file_lock import exclusive_file_lock
from ai4binance.events.models import DomainEvent

_CONSUMER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_CHECKPOINT_SCHEMA_VERSION = "1.0"
_CHECKPOINT_KEYS = frozenset(
    {
        "consumer_id",
        "event_hash",
        "event_id",
        "schema_version",
        "sequence",
        "updated_at",
    }
)


class DurableEventCheckpointCorruptionError(RuntimeError):
    """Raised when durable consumer progress cannot be trusted."""


class DurableEventDeliveryError(RuntimeError):
    """Raised when a durable handler or checkpoint commit fails."""


@dataclass(frozen=True, slots=True)
class DurableEventDelivery:
    """One at-least-once invocation with a stable deduplication key."""

    consumer_id: str
    event: DomainEvent
    idempotency_key: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _validate_consumer_id(self.consumer_id)
        expected = durable_event_idempotency_key(self.consumer_id, self.event)
        if self.idempotency_key != expected:
            raise ValueError("durable delivery idempotency key is invalid")
        if self.execution_allowed:
            raise ValueError("durable delivery cannot grant execution authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("durable delivery cannot grant live eligibility")


DurableEventConsumer = Callable[[DurableEventDelivery], None]


@dataclass(frozen=True, slots=True)
class DurableConsumerCheckpoint:
    """Verified progress for one durable consumer and one event chain."""

    consumer_id: str
    sequence: int
    event_id: str
    event_hash: str
    updated_at: datetime
    schema_version: str = _CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_consumer_id(self.consumer_id)
        if self.sequence < 1:
            raise ValueError("durable consumer checkpoint sequence is invalid")
        if not self.event_id.strip():
            raise ValueError("durable consumer checkpoint event identity is invalid")
        if not _is_sha256(self.event_hash):
            raise ValueError("durable consumer checkpoint event hash is invalid")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError(
                "durable consumer checkpoint timestamp must be timezone-aware"
            )
        if self.schema_version != _CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("durable consumer checkpoint schema is unsupported")


@dataclass(slots=True)
class DiskConsumerCheckpointStore:
    """Bounded, locked, atomic checkpoint persistence for durable consumers."""

    root: Path
    durable: bool = True
    maximum_checkpoint_bytes: int = 65_536

    def __post_init__(self) -> None:
        if not 256 <= self.maximum_checkpoint_bytes <= 1_048_576:
            raise ValueError("durable checkpoint size limit is invalid")

    def deliver_pending(
        self,
        consumer_id: str,
        consumer: DurableEventConsumer,
        events: Sequence[DomainEvent],
    ) -> DurableConsumerCheckpoint | None:
        """Deliver all events after the verified consumer checkpoint."""
        _validate_consumer_id(consumer_id)
        event_snapshot = _validated_event_snapshot(events)
        with self._consumer_lock(consumer_id):
            checkpoint = self._read_unlocked(consumer_id)
            next_index = self._next_index(checkpoint, consumer_id, event_snapshot)
            for event in event_snapshot[next_index:]:
                checkpoint = self._deliver_event_unlocked(
                    consumer_id,
                    consumer,
                    event,
                )
            return checkpoint

    def deliver_next(
        self,
        consumer_id: str,
        consumer: DurableEventConsumer,
        event: DomainEvent,
        previous_event: DomainEvent | None,
    ) -> bool:
        """Deliver one contiguous event or request a complete verified catch-up."""
        _validate_consumer_id(consumer_id)
        with self._consumer_lock(consumer_id):
            checkpoint = self._read_unlocked(consumer_id)
            if checkpoint is None:
                if event.sequence != 1:
                    return False
            elif checkpoint.sequence == event.sequence:
                if (
                    checkpoint.event_id != event.event_id
                    or checkpoint.event_hash != event.event_hash
                ):
                    raise DurableEventCheckpointCorruptionError(
                        "durable consumer checkpoint does not match delivered event"
                    )
                return True
            elif not _checkpoint_matches_previous_event(
                checkpoint,
                event,
                previous_event,
            ):
                return False
            self._deliver_event_unlocked(consumer_id, consumer, event)
            return True

    def load_verified(
        self,
        consumer_id: str,
        events: Sequence[DomainEvent],
    ) -> DurableConsumerCheckpoint | None:
        """Return progress only after matching it to the current event chain."""
        _validate_consumer_id(consumer_id)
        event_snapshot = _validated_event_snapshot(events)
        with self._consumer_lock(consumer_id):
            checkpoint = self._read_unlocked(consumer_id)
            self._next_index(checkpoint, consumer_id, event_snapshot)
            return checkpoint

    @contextmanager
    def _consumer_lock(self, consumer_id: str) -> Iterator[None]:
        lock_path = self._consumer_path(consumer_id, suffix=".lock")
        with exclusive_file_lock(lock_path):
            yield

    def _read_unlocked(self, consumer_id: str) -> DurableConsumerCheckpoint | None:
        target = self._consumer_path(consumer_id, suffix=".checkpoint.json")
        if not target.exists():
            return None
        try:
            with target.open("rb") as stream:
                encoded = stream.read(self.maximum_checkpoint_bytes + 1)
            if len(encoded) > self.maximum_checkpoint_bytes:
                raise DurableEventCheckpointCorruptionError(
                    "durable consumer checkpoint exceeds byte capacity"
                )
            payload = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
            )
            if not isinstance(payload, dict) or set(payload) != _CHECKPOINT_KEYS:
                raise TypeError
            sequence = payload["sequence"]
            string_fields = (
                "consumer_id",
                "event_hash",
                "event_id",
                "schema_version",
                "updated_at",
            )
            if type(sequence) is not int or any(
                type(payload[field]) is not str for field in string_fields
            ):
                raise TypeError
            checkpoint = DurableConsumerCheckpoint(
                consumer_id=payload["consumer_id"],
                sequence=sequence,
                event_id=payload["event_id"],
                event_hash=payload["event_hash"],
                updated_at=datetime.fromisoformat(payload["updated_at"]),
                schema_version=payload["schema_version"],
            )
        except DurableEventCheckpointCorruptionError:
            raise
        except (
            KeyError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint is invalid"
            ) from error
        if checkpoint.consumer_id != consumer_id:
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint identity does not match consumer"
            )
        return checkpoint

    def _write_unlocked(
        self,
        consumer_id: str,
        event: DomainEvent,
    ) -> DurableConsumerCheckpoint:
        checkpoint = DurableConsumerCheckpoint(
            consumer_id=consumer_id,
            sequence=event.sequence,
            event_id=event.event_id,
            event_hash=event.event_hash,
            updated_at=datetime.now(UTC),
        )
        target = self._consumer_path(consumer_id, suffix=".checkpoint.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        encoded = (
            json.dumps(
                {
                    "consumer_id": checkpoint.consumer_id,
                    "event_hash": checkpoint.event_hash,
                    "event_id": checkpoint.event_id,
                    "schema_version": checkpoint.schema_version,
                    "sequence": checkpoint.sequence,
                    "updated_at": checkpoint.updated_at.isoformat(),
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > self.maximum_checkpoint_bytes:
            raise OverflowError("durable consumer checkpoint exceeds byte capacity")
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                if self.durable:
                    os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return checkpoint

    def _deliver_event_unlocked(
        self,
        consumer_id: str,
        consumer: DurableEventConsumer,
        event: DomainEvent,
    ) -> DurableConsumerCheckpoint:
        delivery = DurableEventDelivery(
            consumer_id=consumer_id,
            event=event,
            idempotency_key=durable_event_idempotency_key(consumer_id, event),
        )
        try:
            consumer(delivery)
            return self._write_unlocked(consumer_id, event)
        except Exception as error:
            raise DurableEventDeliveryError(
                f"durable consumer delivery failed at sequence {event.sequence}"
            ) from error

    def _consumer_path(self, consumer_id: str, *, suffix: str) -> Path:
        _validate_consumer_id(consumer_id)
        digest = sha256(consumer_id.encode("ascii")).hexdigest()
        return self.root / f"{digest}{suffix}"

    @staticmethod
    def _next_index(
        checkpoint: DurableConsumerCheckpoint | None,
        consumer_id: str,
        events: Sequence[DomainEvent],
    ) -> int:
        if checkpoint is None:
            return 0
        if checkpoint.consumer_id != consumer_id:
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint identity does not match consumer"
            )
        if checkpoint.sequence > len(events):
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint sequence exceeds journal"
            )
        matched = events[checkpoint.sequence - 1]
        if matched.sequence != checkpoint.sequence:
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint sequence does not match journal"
            )
        if matched.event_id != checkpoint.event_id:
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint event identity does not match journal"
            )
        if matched.event_hash != checkpoint.event_hash:
            raise DurableEventCheckpointCorruptionError(
                "durable consumer checkpoint event hash does not match journal"
            )
        return checkpoint.sequence


def durable_event_idempotency_key(consumer_id: str, event: DomainEvent) -> str:
    """Return one stable key for each consumer and canonical event identity."""
    _validate_consumer_id(consumer_id)
    canonical = json.dumps(
        {
            "consumer_id": consumer_id,
            "event_hash": event.event_hash,
            "event_id": event.event_id,
            "sequence": event.sequence,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _validate_consumer_id(consumer_id: str) -> None:
    if (
        not isinstance(consumer_id, str)
        or _CONSUMER_ID_PATTERN.fullmatch(consumer_id) is None
    ):
        raise ValueError("durable consumer identity is invalid")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("checkpoint JSON contains a duplicate object key")
        payload[key] = value
    return payload


def _checkpoint_matches_previous_event(
    checkpoint: DurableConsumerCheckpoint,
    event: DomainEvent,
    previous_event: DomainEvent | None,
) -> bool:
    return (
        previous_event is not None
        and checkpoint.sequence == event.sequence - 1
        and previous_event.sequence == checkpoint.sequence
        and previous_event.event_id == checkpoint.event_id
        and previous_event.event_hash == checkpoint.event_hash
        and event.previous_hash == previous_event.event_hash
    )


def _validated_event_snapshot(
    events: Sequence[DomainEvent],
) -> tuple[DomainEvent, ...]:
    snapshot = tuple(events)
    if len(snapshot) > 1_000_000:
        raise DurableEventDeliveryError("durable delivery history exceeds capacity")
    try:
        validator = DeterministicEventBus(capacity=max(1, len(snapshot)))
        validator.replay(snapshot)
    except (OverflowError, ValueError) as error:
        raise DurableEventDeliveryError(
            "durable delivery event history is invalid"
        ) from error
    return snapshot

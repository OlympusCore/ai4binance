"""Durable hash-linked event journal and deterministic restart recovery."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, RLock
from typing import Any, BinaryIO, cast

from ai4binance.events.bus import (
    DeterministicEventBus,
    EventSubscriber,
    _validate_next_event,
)
from ai4binance.events.delivery import (
    DiskConsumerCheckpointStore,
    DurableEventConsumer,
)
from ai4binance.events.file_lock import exclusive_file_lock
from ai4binance.events.models import DomainEvent


class EventJournalCorruptionError(RuntimeError):
    """Raised when persisted event evidence is incomplete or inconsistent."""


EventFactory = Callable[[int, str], DomainEvent]
JournalFileSignature = tuple[int, int, int, int, int, int | None]

_WINDOWS_FSCTL_READ_FILE_USN_DATA = 0x000900EB
_WINDOWS_USN_RECORD_V2_MAJOR_VERSION = 2
_WINDOWS_USN_RECORD_V2_MINIMUM_BYTES = 32
_WINDOWS_USN_RECORD_V2_USN_OFFSET = 24


@dataclass(slots=True)
class _JournalAppendState:
    """Minimal validated state for constant-time sequential append checks."""

    event_count: int
    event_ids: set[str]
    latest_event: DomainEvent | None
    file_signature: JournalFileSignature | None

    def validate(self, event: DomainEvent, *, capacity: int) -> None:
        _validate_next_event(
            event,
            capacity=capacity,
            event_count=self.event_count,
            event_ids=self.event_ids,
            latest_event=self.latest_event,
        )

    def record(
        self,
        event: DomainEvent,
        *,
        file_signature: JournalFileSignature,
    ) -> None:
        self.event_count += 1
        self.event_ids.add(event.event_id)
        self.latest_event = event
        self.file_signature = file_signature


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
    _append_state: _JournalAppendState | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.checkpoint_path is None:
            self.checkpoint_path = self.path.with_suffix(".checkpoint.json")
        limits = (self.maximum_event_bytes, self.maximum_journal_bytes)
        if min(limits) < 256 or self.maximum_event_bytes > self.maximum_journal_bytes:
            raise ValueError("journal size limits are invalid")

    def append(self, event: DomainEvent) -> None:
        """Validate against durable history before committing one complete line."""
        with self._synchronized():
            self._append_unlocked(event)

    def append_next(self, event_factory: EventFactory) -> DomainEvent:
        """Build and append one event against the locked durable tail."""
        with self._synchronized():
            state = self._append_state_for_current_file_unlocked()
            event = event_factory(
                state.event_count + 1,
                (
                    state.latest_event.event_hash
                    if state.latest_event is not None
                    else "GENESIS"
                ),
            )
            self._append_validated_unlocked(event, state)
            return event

    def load(self) -> tuple[DomainEvent, ...]:
        """Load and validate the complete journal; never skip corrupt records."""
        with self._synchronized():
            return self._load_unlocked()

    def recover(self) -> JournalRecovery:
        """Return validated events plus a verified checkpoint replay cursor."""
        with self._synchronized():
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
        with self._synchronized():
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

    def _append_unlocked(self, event: DomainEvent) -> None:
        state = self._append_state_for_current_file_unlocked()
        self._append_validated_unlocked(event, state)

    def _append_validated_unlocked(
        self,
        event: DomainEvent,
        state: _JournalAppendState,
    ) -> None:
        state.validate(event, capacity=self._capacity())
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
        file_signature = self._file_signature_unlocked()
        if file_signature is None:
            raise RuntimeError("event journal append destination is unavailable")
        state.record(event, file_signature=file_signature)

    @contextmanager
    def _synchronized(self) -> Iterator[None]:
        with self._lock:
            with self._file_lock():
                yield

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        with exclusive_file_lock(lock_path):
            yield

    def _load_unlocked(self) -> tuple[DomainEvent, ...]:
        self._append_state = None
        initial_signature = self._file_signature_unlocked()
        if initial_signature is None:
            self._append_state = _JournalAppendState(0, set(), None, None)
            return ()
        data = self.path.read_bytes()
        final_signature = self._file_signature_unlocked()
        if final_signature != initial_signature:
            raise EventJournalCorruptionError("event journal changed during validation")
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
        loaded = tuple(events)
        self._append_state = _JournalAppendState(
            event_count=len(loaded),
            event_ids={event.event_id for event in loaded},
            latest_event=loaded[-1] if loaded else None,
            file_signature=final_signature,
        )
        return loaded

    def _append_state_for_current_file_unlocked(self) -> _JournalAppendState:
        current_signature = self._file_signature_unlocked()
        if self._append_state is not None and _file_signatures_allow_cache_reuse(
            self._append_state.file_signature,
            current_signature,
        ):
            return self._append_state
        self._load_unlocked()
        if self._append_state is None:
            raise RuntimeError("event journal append state was not initialized")
        return self._append_state

    def _file_signature_unlocked(self) -> JournalFileSignature | None:
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                change_token = _file_change_token(stream, stat)
        except FileNotFoundError:
            return None
        return (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            change_token,
        )

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
    checkpoint_store: DiskConsumerCheckpointStore | None = None
    _durable_consumers: dict[str, DurableEventConsumer] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _runtime_lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _latest_event: DomainEvent | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.checkpoint_store is None:
            root = self.journal.path.with_suffix(
                f"{self.journal.path.suffix}.consumers"
            )
            self.checkpoint_store = DiskConsumerCheckpointStore(
                root,
                durable=self.journal.durable,
            )
        events = self.bus.snapshot()
        self._latest_event = events[-1] if events else None

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
        """Register an ephemeral subscriber without replaying durable history."""
        self.bus.subscribe(subscriber)

    def subscribe_durable(
        self,
        consumer_id: str,
        consumer: DurableEventConsumer,
    ) -> None:
        """Catch up and register one explicit at-least-once consumer."""
        with self._runtime_lock:
            if not isinstance(consumer_id, str):
                raise ValueError("durable consumer identity is invalid")
            if not callable(consumer):
                raise TypeError("durable event consumer must be callable")
            if consumer_id in self._durable_consumers:
                raise ValueError("durable event consumer is already registered")
            store = self._checkpoint_store()
            store.deliver_pending(consumer_id, consumer, self.journal.load())
            self._durable_consumers[consumer_id] = consumer

    def publish(self, event: DomainEvent) -> None:
        with self._runtime_lock:
            self.journal.append(event)
            failures: list[Exception] = []
            previous_event = self._latest_event
            bus_committed = False
            try:
                self.bus.publish(event)
                bus_committed = True
            except Exception as error:
                failures.append(error)
                events = self.bus.snapshot()
                bus_committed = bool(events and events[-1] == event)
            if bus_committed:
                self._latest_event = event
            full_history: tuple[DomainEvent, ...] | None = None
            if self._durable_consumers and not bus_committed:
                try:
                    full_history = self.journal.load()
                except (OSError, RuntimeError, ValueError) as error:
                    failures.append(error)
            for consumer_id in sorted(self._durable_consumers):
                consumer = self._durable_consumers[consumer_id]
                if full_history is None and bus_committed:
                    try:
                        delivered = self._checkpoint_store().deliver_next(
                            consumer_id,
                            consumer,
                            event,
                            previous_event,
                        )
                    except (OSError, RuntimeError, ValueError) as error:
                        failures.append(error)
                        continue
                    if delivered:
                        continue
                    try:
                        full_history = self.journal.load()
                    except (OSError, RuntimeError, ValueError) as error:
                        failures.append(error)
                        continue
                if full_history is not None:
                    try:
                        self._checkpoint_store().deliver_pending(
                            consumer_id,
                            consumer,
                            full_history,
                        )
                    except (OSError, RuntimeError, ValueError) as error:
                        failures.append(error)
            _raise_delivery_failures(failures)

    def snapshot(self) -> tuple[DomainEvent, ...]:
        return self.bus.snapshot()

    def _checkpoint_store(self) -> DiskConsumerCheckpointStore:
        if self.checkpoint_store is None:
            raise RuntimeError("durable consumer checkpoint store is unavailable")
        return self.checkpoint_store


def _raise_delivery_failures(failures: list[Exception]) -> None:
    if not failures:
        return
    if len(failures) == 1:
        raise failures[0]
    raise ExceptionGroup("event dispatch produced multiple failures", failures)


def _file_signatures_allow_cache_reuse(
    cached: JournalFileSignature | None,
    current: JournalFileSignature | None,
) -> bool:
    """Trust a cached tail only when an OS-backed change token is available."""
    return (
        cached is not None
        and current is not None
        and cached[-1] is not None
        and current[-1] is not None
        and cached == current
    )


def _file_change_token(stream: BinaryIO, stat: os.stat_result) -> int | None:
    """Return an O(1) file-change token or deny append-cache reuse."""
    if os.name == "nt":
        return _read_windows_file_usn(stream)
    return stat.st_ctime_ns


def _read_windows_file_usn(stream: BinaryIO) -> int | None:
    """Read the NTFS per-file USN; unsupported evidence disables caching."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    win_dll = cast(Any, getattr(ctypes, "WinDLL", None))
    if win_dll is None:
        return None
    try:
        kernel32 = win_dll("kernel32", use_last_error=True)
        device_io_control = cast(Any, kernel32.DeviceIoControl)
        device_io_control.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        device_io_control.restype = wintypes.BOOL
        buffer = ctypes.create_string_buffer(4096)
        returned = wintypes.DWORD()
        succeeded = device_io_control(
            wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno())),
            _WINDOWS_FSCTL_READ_FILE_USN_DATA,
            None,
            0,
            buffer,
            len(buffer),
            ctypes.byref(returned),
            None,
        )
    except (AttributeError, OSError):
        return None
    if not succeeded or returned.value < _WINDOWS_USN_RECORD_V2_MINIMUM_BYTES:
        return None
    raw = buffer.raw[: returned.value]
    record_length = int.from_bytes(raw[0:4], "little")
    major_version = int.from_bytes(raw[4:6], "little")
    if (
        major_version != _WINDOWS_USN_RECORD_V2_MAJOR_VERSION
        or record_length < _WINDOWS_USN_RECORD_V2_MINIMUM_BYTES
        or record_length > returned.value
    ):
        return None
    return int.from_bytes(
        raw[
            _WINDOWS_USN_RECORD_V2_USN_OFFSET : (_WINDOWS_USN_RECORD_V2_USN_OFFSET + 8)
        ],
        "little",
        signed=True,
    )

"""Canonical infrastructure JSON and JSONL persistence helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, cast
from uuid import uuid4

from ai4binance.core import (
    read_bounded_jsonl_tail as _read_bounded_jsonl_tail,
)

_EVENT_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_TAIL_READ_CHUNK_BYTES = 64 * 1024
_DEFAULT_MAX_EVENT_BYTES = 8 * 1024 * 1024
_GENESIS_RECORD_HASH = "GENESIS"
_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "signature",
    "authorization",
    "password",
    "private_key",
    "token",
)
_SAFE_TOKEN_METRIC_KEYS = frozenset(
    {
        "cached_input_tokens",
        "cached_prompt_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "reasoning_tokens",
        "token_accounting_source",
        "token_source_required",
        "total_tokens",
    }
)


@dataclass(frozen=True, slots=True)
class VerifiedWriteResult:
    destination: str
    subject_id: str
    status: str
    blockers: tuple[str, ...] = ()
    verified_at: datetime | None = None
    operation: str = "write"
    expected_sha256: str | None = None
    observed_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.destination.strip() or not self.subject_id.strip():
            raise ValueError("verified write identity is required")
        if not self.operation.strip():
            raise ValueError("verified write operation is required")
        if self.status == "VERIFIED" and self.blockers:
            raise ValueError("verified write cannot contain blockers")
        if self.status == "VERIFICATION_FAILED" and not self.blockers:
            raise ValueError("failed verification requires blockers")


class DestinationVerificationError(ValueError):
    """Raised when a write cannot be proven from the changed destination."""


class SecretRedactor:
    """Recursively redact values whose keys may contain credentials."""

    REDACTED = "[REDACTED]"

    def redact(self, value: object) -> object:
        if isinstance(value, Mapping):
            return {
                str(key): (
                    self.REDACTED if self._is_sensitive(str(key)) else self.redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self.redact(item) for item in value]
        return value

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        normalized = key.strip().lower().replace("-", "_")
        if normalized in _SAFE_TOKEN_METRIC_KEYS:
            return False
        return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One versioned append-only audit event."""

    event_type: str
    timestamp: datetime
    payload: Mapping[str, object]
    snapshot_id: str | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not _EVENT_TYPE_PATTERN.fullmatch(self.event_type):
            raise ValueError("event_type must be uppercase snake case")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("audit timestamp must be timezone-aware")
        if self.snapshot_id is not None and not self.snapshot_id.strip():
            raise ValueError("snapshot_id cannot be blank")


@dataclass(slots=True)
class JsonlAuditStore:
    """Append-only JSONL writer with bounded read-back verification."""

    path: Path
    durable: bool = False
    tamper_evident: bool = False
    max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES
    redactor: SecretRedactor = field(default_factory=SecretRedactor)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_event_bytes < 1:
            raise ValueError("maximum JSONL event size must be positive")
        if self.tamper_evident and not self.durable:
            self.durable = True

    def append_verified(self, event: AuditEvent) -> VerifiedWriteResult:
        subject_id = event.snapshot_id or event.event_type
        with self._synchronized():
            previous_record_hash, chain_position = self._chain_state_or_fail(
                subject_id=subject_id
            )
            line = self._render(
                event,
                previous_record_hash=previous_record_hash,
                chain_position=chain_position,
            )
            expected = json.loads(line)
            self._append_line(line)
            observed = self._last_event_unlocked()
        if observed != expected:
            raise fail_verification(
                "JSONL_AUDIT_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=subject_id,
            )
        return verified(
            self.path,
            subject_id,
            operation="jsonl_append",
            expected_sha256=_canonical_json_sha256(expected),
            observed_sha256=_canonical_json_sha256(observed),
        )

    def _render(
        self,
        event: AuditEvent,
        *,
        previous_record_hash: str,
        chain_position: int,
    ) -> str:
        primitive = to_primitive(event)
        redacted = self.redactor.redact(primitive)
        if self.tamper_evident:
            redacted = self._seal_tamper_evident_record(
                redacted,
                previous_record_hash=previous_record_hash,
                chain_position=chain_position,
            )
        return json.dumps(
            redacted,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _seal_tamper_evident_record(
        self,
        event: object,
        *,
        previous_record_hash: str,
        chain_position: int,
    ) -> dict[str, object]:
        if not isinstance(event, Mapping):
            raise TypeError("tamper-evident JSONL events must be objects")
        payload = dict(event)
        event_sha256 = _canonical_json_sha256(payload)
        record_sha256 = _canonical_json_sha256(
            {
                "chain_position": chain_position,
                "event_sha256": event_sha256,
                "previous_record_sha256": previous_record_hash,
            }
        )
        payload["chain_position"] = chain_position
        payload["tamper_evident"] = True
        payload["previous_record_sha256"] = previous_record_hash
        payload["event_sha256"] = event_sha256
        payload["record_sha256"] = record_sha256
        return payload

    def _append_line(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.write("\n")
            stream.flush()
            if self.durable:
                os.fsync(stream.fileno())

    def _last_event_unlocked(self) -> object:
        line = self._read_last_nonempty_line()
        return json.loads(line.decode("utf-8"))

    def _chain_state_or_fail(self, *, subject_id: str) -> tuple[str, int]:
        try:
            if not self.tamper_evident:
                return _GENESIS_RECORD_HASH, 1
            return self._verify_chain_state_unlocked()
        except (
            OSError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            raise fail_verification(
                "JSONL_AUDIT_TAMPER_EVIDENT_CHAIN_INVALID",
                destination=self.path,
                subject_id=subject_id,
            ) from error

    @contextmanager
    def _synchronized(self) -> Iterator[None]:
        with self._lock:
            with self._file_lock():
                yield

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.touch(exist_ok=True)
        with lock_path.open("r+b") as stream:
            _acquire_file_lock(stream)
            try:
                yield
            finally:
                _release_file_lock(stream)

    def _read_last_nonempty_line(self) -> bytes:
        with self.path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = _trim_trailing_whitespace(stream, stream.tell())
            if end == 0:
                raise OSError("JSONL destination contains no event")
            cursor = end
            parts: list[bytes] = []
            event_size = 0
            while cursor > 0:
                start = max(0, cursor - _TAIL_READ_CHUNK_BYTES)
                stream.seek(start)
                block = stream.read(cursor - start)
                newline = block.rfind(b"\n")
                part = block[newline + 1 :] if newline >= 0 else block
                event_size += len(part)
                if event_size > self.max_event_bytes:
                    raise OSError("JSONL destination event exceeds bounded read limit")
                parts.append(part)
                if newline >= 0:
                    break
                cursor = start
            return b"".join(reversed(parts))

    def _verify_chain_state_unlocked(self) -> tuple[str, int]:
        if not self.path.exists():
            return _GENESIS_RECORD_HASH, 1
        expected_previous = _GENESIS_RECORD_HASH
        expected_position = 1
        with self.path.open("rb") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                if not raw_line.strip():
                    raise ValueError(
                        f"tamper-evident JSONL line {line_number} cannot be blank"
                    )
                event = _load_event_line(
                    raw_line,
                    label=f"tamper-evident JSONL line {line_number}",
                )
                if event.get("tamper_evident") is not True:
                    raise ValueError(
                        f"tamper-evident JSONL line {line_number} is missing sealing"
                    )
                chain_position = event.get("chain_position")
                if chain_position != expected_position:
                    raise ValueError(
                        f"tamper-evident JSONL line {line_number} position is invalid"
                    )
                previous_record_hash = _text_field(
                    event,
                    "previous_record_sha256",
                    label=f"tamper-evident JSONL line {line_number}",
                )
                if previous_record_hash != expected_previous:
                    raise ValueError(
                        f"tamper-evident JSONL line {line_number} hash chain is broken"
                    )
                event_sha256 = _text_field(
                    event,
                    "event_sha256",
                    label=f"tamper-evident JSONL line {line_number}",
                )
                record_sha256 = _text_field(
                    event,
                    "record_sha256",
                    label=f"tamper-evident JSONL line {line_number}",
                )
                unsealed_event = {
                    key: value
                    for key, value in event.items()
                    if key
                    not in {
                        "chain_position",
                        "tamper_evident",
                        "previous_record_sha256",
                        "event_sha256",
                        "record_sha256",
                    }
                }
                expected_event_sha256 = _canonical_json_sha256(unsealed_event)
                if event_sha256 != expected_event_sha256:
                    raise ValueError(
                        f"tamper-evident JSONL line {line_number} event hash invalid"
                    )
                expected_record_sha256 = _canonical_json_sha256(
                    {
                        "chain_position": expected_position,
                        "event_sha256": expected_event_sha256,
                        "previous_record_sha256": expected_previous,
                    }
                )
                if record_sha256 != expected_record_sha256:
                    raise ValueError(
                        f"tamper-evident JSONL line {line_number} record hash invalid"
                    )
                expected_previous = record_sha256
                expected_position += 1
        return expected_previous, expected_position


def write_json_object_verified(
    path: Path,
    payload: Mapping[str, object],
    *,
    blocker: str,
    subject_id: str | None = None,
    indent: int | None = None,
    durable: bool = False,
) -> VerifiedWriteResult:
    expected = dict(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        encoded = _json_dumps(expected, indent=indent) + "\n"
        normalized_expected = json.loads(encoded)
        if not isinstance(normalized_expected, dict):
            raise TypeError("verified JSON state must encode an object")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            if durable:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
        observed = _read_json_object(path, blocker=blocker)
    finally:
        temporary.unlink(missing_ok=True)
    if dict(observed) != normalized_expected:
        raise fail_verification(
            blocker,
            destination=path,
            subject_id=subject_id or str(path),
        )
    expected_hash = _canonical_json_sha256(normalized_expected)
    observed_hash = _canonical_json_sha256(dict(observed))
    return verified(
        path,
        subject_id or str(path),
        operation="json_state_write",
        expected_sha256=expected_hash,
        observed_sha256=observed_hash,
    )


def to_primitive(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_primitive(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [to_primitive(item) for item in sorted(value, key=repr)]
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def read_bounded_jsonl_tail(
    path: Path,
    *,
    max_lines: int = 200,
    max_bytes: int = 16 * 1024 * 1024,
) -> tuple[bytes, ...]:
    """Compatibility export for the canonical bounded JSONL reader."""
    return _read_bounded_jsonl_tail(
        path,
        max_lines=max_lines,
        max_bytes=max_bytes,
    )


def verified(
    destination: Path,
    subject_id: str,
    *,
    operation: str = "write",
    expected_sha256: str | None = None,
    observed_sha256: str | None = None,
) -> VerifiedWriteResult:
    return VerifiedWriteResult(
        str(destination),
        subject_id,
        "VERIFIED",
        (),
        datetime.now(UTC),
        operation,
        expected_sha256,
        observed_sha256,
    )


def fail_verification(
    blocker: str,
    *,
    destination: Path,
    subject_id: str,
) -> DestinationVerificationError:
    result = VerifiedWriteResult(
        str(destination),
        subject_id,
        "VERIFICATION_FAILED",
        (blocker,),
    )
    return DestinationVerificationError(result.blockers[0])


def _read_json_object(path: Path, *, blocker: str) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise fail_verification(
            blocker, destination=path, subject_id=str(path)
        ) from error
    if not isinstance(payload, Mapping):
        raise fail_verification(blocker, destination=path, subject_id=str(path))
    return payload


def _json_dumps(payload: Mapping[str, object], *, indent: int | None) -> str:
    if indent is None:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=True)


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trim_trailing_whitespace(stream: BinaryIO, end: int) -> int:
    while end > 0:
        start = max(0, end - _TAIL_READ_CHUNK_BYTES)
        stream.seek(start)
        block = stream.read(end - start)
        stripped = block.rstrip(b" \t\r\n")
        if stripped:
            return start + len(stripped)
        end = start
    return 0


def _load_event_line(raw_line: bytes, *, label: str) -> dict[str, object]:
    payload = json.loads(raw_line.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _text_field(payload: Mapping[str, object], name: str, *, label: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} {name} is invalid")
    return value


def _acquire_file_lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        if stream.tell() == 0 and stream.read(1) == b"":
            stream.seek(0)
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    flock = cast(Any, getattr(fcntl, "flock", None))
    lock_ex = cast(Any, getattr(fcntl, "LOCK_EX", None))
    if flock is None or lock_ex is None:
        raise RuntimeError("POSIX file locking is unavailable on this platform.")
    flock(stream.fileno(), lock_ex)


def _release_file_lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    flock = cast(Any, getattr(fcntl, "flock", None))
    lock_un = cast(Any, getattr(fcntl, "LOCK_UN", None))
    if flock is None or lock_un is None:
        raise RuntimeError("POSIX file locking is unavailable on this platform.")
    flock(stream.fileno(), lock_un)

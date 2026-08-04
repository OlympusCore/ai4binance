"""Secret-redacted append-only JSONL audit storage."""

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import BinaryIO

from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import (
    VerifiedWriteResult,
    fail_verification,
    verified,
)

_EVENT_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_TAIL_READ_CHUNK_BYTES = 64 * 1024
_DEFAULT_MAX_EVENT_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_TAIL_BYTES = 16 * 1024 * 1024
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
    """Process-local atomic line writer with optional durable fsync."""

    path: Path
    durable: bool = False
    max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES
    redactor: SecretRedactor = field(default_factory=SecretRedactor)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_event_bytes < 1:
            raise ValueError("maximum JSONL event size must be positive")

    def append(self, event: AuditEvent) -> None:
        line = self._render(event)
        with self._lock:
            self._append_line(line)

    def append_verified(self, event: AuditEvent) -> VerifiedWriteResult:
        line = self._render(event)
        expected = json.loads(line)
        subject_id = event.snapshot_id or event.event_type
        with self._lock:
            self._append_line(line)
            observed = self._last_event()
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

    def _render(self, event: AuditEvent) -> str:
        primitive = to_primitive(event)
        redacted = self.redactor.redact(primitive)
        return json.dumps(
            redacted,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _append_line(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.write("\n")
            stream.flush()
            if self.durable:
                os.fsync(stream.fileno())

    def _last_event(self) -> object:
        try:
            line = self._read_last_nonempty_line()
            return json.loads(line.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise fail_verification(
                "JSONL_AUDIT_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            ) from error

    def _read_last_nonempty_line(self) -> bytes:
        with self.path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            end = self._trim_trailing_whitespace(stream, end)
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

    @staticmethod
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


def read_bounded_jsonl_tail(
    path: Path,
    *,
    max_lines: int = 200,
    max_bytes: int = _DEFAULT_MAX_TAIL_BYTES,
) -> tuple[bytes, ...]:
    """Read recent non-empty records without loading an entire JSONL file."""
    if max_lines < 1 or max_bytes < 1:
        raise ValueError("JSONL tail limits must be positive")
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        end = JsonlAuditStore._trim_trailing_whitespace(stream, stream.tell())
        cursor = end
        buffer = b""
        while cursor > 0:
            start = max(0, cursor - _TAIL_READ_CHUNK_BYTES)
            stream.seek(start)
            buffer = stream.read(cursor - start) + buffer
            if len(buffer) > max_bytes:
                raise OSError("JSONL tail exceeds bounded read limit")
            lines = tuple(line for line in buffer.splitlines() if line.strip())
            if len(lines) >= max_lines or start == 0:
                return lines[-max_lines:]
            cursor = start
    return ()


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

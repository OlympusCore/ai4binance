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

from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import (
    VerifiedWriteResult,
    fail_verification,
    verified,
)

_EVENT_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
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
    redactor: SecretRedactor = field(default_factory=SecretRedactor)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

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
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise fail_verification(
                "JSONL_AUDIT_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            ) from error
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError as error:
                raise fail_verification(
                    "JSONL_AUDIT_DESTINATION_VERIFY_FAILED",
                    destination=self.path,
                    subject_id=str(self.path),
                ) from error
        raise fail_verification(
            "JSONL_AUDIT_DESTINATION_VERIFY_FAILED",
            destination=self.path,
            subject_id=str(self.path),
        )


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

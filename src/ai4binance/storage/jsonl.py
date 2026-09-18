"""Secret-redacted append-only and tamper-evident JSONL audit storage."""

import hashlib
import json
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, cast

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

# Token usage counters are operational measurements, not bearer credentials.
# Keep this allowlist exact so names such as ``access_token`` remain redacted.
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
    """Atomic JSONL writer with cross-process file serialization."""

    path: Path
    durable: bool = False
    tamper_evident: bool = False
    max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES
    redactor: SecretRedactor = field(default_factory=SecretRedactor)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _legacy_path: Path | None = field(default=None, init=False, repr=False)
    _legacy_sha256: str | None = field(default=None, init=False, repr=False)

    @classmethod
    def chained_successor(cls, legacy_path: Path) -> "JsonlAuditStore":
        """Preserve legacy bytes and bind new events to a sealed successor journal.

        The anchor attests only to the bytes present at migration, not to the
        historical authenticity of unsealed records. Later legacy changes block
        new writes and verification. Reopening does not append another anchor.
        """
        legacy_sha256 = _file_sha256_or_none(legacy_path)
        primary_path = legacy_path.with_suffix(".chained.jsonl")
        try:
            return cls._anchored_successor(legacy_path, primary_path, legacy_sha256)
        except ValueError as error:
            if str(error) != "JSONL_AUDIT_LEGACY_ANCHOR_MISMATCH":
                raise
        recovery = cls._read_recovery_receipt(legacy_path)
        if recovery is None or not cls._recovery_receipt_matches(
            recovery, legacy_path, primary_path, legacy_sha256
        ):
            raise ValueError("JSONL_AUDIT_LEGACY_ANCHOR_MISMATCH")
        successor = legacy_path.with_name(str(recovery["successor_filename"]))
        return cls._anchored_successor(legacy_path, successor, legacy_sha256)

    @classmethod
    def recover_chained_successor(cls, legacy_path: Path) -> "JsonlAuditStore":
        """Create a separately sealed successor after an approved legacy change.

        The legacy journal and its original successor remain immutable.  The
        receipt binds their exact hashes to a new successor whose anchor binds
        the current legacy bytes.  Calling this method is an explicit local
        recovery action, never an automatic fallback.
        """

        legacy_sha256 = _file_sha256_or_none(legacy_path)
        primary_path = legacy_path.with_suffix(".chained.jsonl")
        primary = cls(primary_path, tamper_evident=True)
        with primary._synchronized():
            _, position = primary._chain_state_or_fail(
                subject_id="legacy-audit-recovery"
            )
            if position == 1:
                raise ValueError("JSONL_AUDIT_RECOVERY_PRIMARY_ANCHOR_MISSING")
            with primary.path.open("rb") as stream:
                anchor = primary._load_event_line(
                    stream.readline(primary.max_event_bytes + 1),
                    label="audit anchor",
                )
            if anchor.get("event_type") != "LEGACY_AUDIT_ANCHOR":
                raise ValueError("JSONL_AUDIT_RECOVERY_PRIMARY_ANCHOR_INVALID")
            payload = anchor.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("JSONL_AUDIT_RECOVERY_PRIMARY_ANCHOR_INVALID")
            previous_legacy_sha256 = payload.get("legacy_sha256")
            if not isinstance(previous_legacy_sha256, str):
                raise ValueError("JSONL_AUDIT_RECOVERY_PRIMARY_ANCHOR_INVALID")
            if previous_legacy_sha256 == legacy_sha256:
                raise ValueError("JSONL_AUDIT_RECOVERY_NOT_REQUIRED")
            primary_sha256 = _file_sha256_or_none(primary_path)
            if primary_sha256 is None:
                raise ValueError("JSONL_AUDIT_RECOVERY_PRIMARY_MISSING")
            successor = legacy_path.with_name(
                f"{legacy_path.stem}.recovery-"
                f"{legacy_sha256[:16] if legacy_sha256 else 'absent'}.chained.jsonl"
            )
            existing = cls._read_recovery_receipt(legacy_path)
            if existing is not None and cls._recovery_receipt_matches(
                existing, legacy_path, primary_path, legacy_sha256
            ):
                return cls._anchored_successor(legacy_path, successor, legacy_sha256)
            receipt = {
                "schema_version": 1,
                "status": "LEGACY_AUDIT_RECOVERY_APPROVED",
                "legacy_filename": legacy_path.name,
                "previous_legacy_sha256": previous_legacy_sha256,
                "current_legacy_sha256": legacy_sha256,
                "primary_successor_filename": primary_path.name,
                "primary_successor_sha256": primary_sha256,
                "successor_filename": successor.name,
                "recovered_at": datetime.now(UTC).isoformat(),
                "historical_authenticity_verified": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
            cls._write_recovery_receipt(legacy_path, receipt)
        return cls._anchored_successor(legacy_path, successor, legacy_sha256)

    @classmethod
    def _anchored_successor(
        cls, legacy_path: Path, successor_path: Path, legacy_sha256: str | None
    ) -> "JsonlAuditStore":
        store = cls(successor_path, tamper_evident=True)
        with store._synchronized():
            store._legacy_path = legacy_path
            store._legacy_sha256 = legacy_sha256
            anchor_payload = {
                "legacy_filename": legacy_path.name,
                "legacy_sha256": store._legacy_sha256,
                "historical_authenticity_verified": False,
            }
            _, position = store._chain_state_or_fail(subject_id="legacy-audit-anchor")
            if position == 1:
                event = AuditEvent(
                    event_type="LEGACY_AUDIT_ANCHOR",
                    timestamp=datetime.now(UTC),
                    snapshot_id="legacy-audit-anchor",
                    payload=anchor_payload,
                )
                store._append_line(
                    store._render(
                        event,
                        previous_record_hash=_GENESIS_RECORD_HASH,
                        chain_position=1,
                    )
                )
            else:
                with store.path.open("rb") as stream:
                    anchor = store._load_event_line(
                        stream.readline(store.max_event_bytes + 1), label="audit anchor"
                    )
                if (
                    anchor.get("event_type") != "LEGACY_AUDIT_ANCHOR"
                    or anchor.get("payload") != anchor_payload
                ):
                    raise ValueError("JSONL_AUDIT_LEGACY_ANCHOR_MISMATCH")
        return store

    @staticmethod
    def _recovery_receipt_path(legacy_path: Path) -> Path:
        return legacy_path.with_name(f"{legacy_path.stem}.audit-recovery.json")

    @classmethod
    def _read_recovery_receipt(cls, legacy_path: Path) -> dict[str, object] | None:
        path = cls._recovery_receipt_path(legacy_path)
        try:
            if path.stat().st_size > 16_384:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _recovery_receipt_matches(
        cls,
        receipt: dict[str, object],
        legacy_path: Path,
        primary_path: Path,
        legacy_sha256: str | None,
    ) -> bool:
        successor = receipt.get("successor_filename")
        if (
            not isinstance(successor, str)
            or Path(successor).name != successor
            or Path(successor).is_absolute()
        ):
            return False
        expected_successor = legacy_path.with_name(str(successor))
        return (
            receipt.get("schema_version") == 1
            and receipt.get("status") == "LEGACY_AUDIT_RECOVERY_APPROVED"
            and receipt.get("legacy_filename") == legacy_path.name
            and receipt.get("current_legacy_sha256") == legacy_sha256
            and receipt.get("primary_successor_filename") == primary_path.name
            and receipt.get("primary_successor_sha256")
            == _file_sha256_or_none(primary_path)
            and expected_successor.parent == legacy_path.parent
            and expected_successor.name == successor
            and receipt.get("historical_authenticity_verified") is False
            and receipt.get("execution_allowed") is False
            and receipt.get("live_eligibility_status") == "LIVE_ORDER_BLOCKED"
        )

    @classmethod
    def _write_recovery_receipt(
        cls, legacy_path: Path, receipt: dict[str, object]
    ) -> None:
        path = cls._recovery_receipt_path(legacy_path)
        expected = (
            json.dumps(receipt, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
        )
        if path.exists():
            current = cls._read_recovery_receipt(legacy_path)
            if current is None or current != receipt:
                raise ValueError("JSONL_AUDIT_RECOVERY_RECEIPT_CONFLICT")
            return
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(expected, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def __post_init__(self) -> None:
        if self.max_event_bytes < 1:
            raise ValueError("maximum JSONL event size must be positive")
        if self.tamper_evident and not self.durable:
            self.durable = True

    def append(self, event: AuditEvent) -> None:
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
            self._append_line(line)

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

    def append_verified_idempotent(
        self,
        event: AuditEvent,
    ) -> VerifiedWriteResult | None:
        """Append once per event identity under the cross-process file lock.

        An exact replay returns ``None``. Reusing an event identity with different
        content fails closed instead of creating ambiguous financial evidence.
        """

        subject_id = event.snapshot_id or event.event_type
        expected_event = self.redactor.redact(to_primitive(event))
        with self._synchronized():
            previous_record_hash, chain_position = self._chain_state_or_fail(
                subject_id=subject_id
            )
            existing = self._event_by_identity_unlocked(
                event_type=event.event_type,
                snapshot_id=event.snapshot_id,
            )
            if existing is not None:
                existing_event = {
                    key: existing.get(key)
                    for key in (
                        "event_type",
                        "timestamp",
                        "payload",
                        "snapshot_id",
                        "schema_version",
                    )
                }
                if existing_event != expected_event:
                    raise ValueError("JSONL_AUDIT_IDEMPOTENCY_CONFLICT")
                return None
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
            operation="jsonl_append_idempotent",
            expected_sha256=_canonical_json_sha256(expected),
            observed_sha256=_canonical_json_sha256(observed),
        )

    def verify_chain(self) -> str:
        with self._synchronized():
            last_record_hash, _ = self._chain_state_or_fail(subject_id=str(self.path))
        return last_record_hash

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
        if len(line.encode("utf-8")) > self.max_event_bytes:
            raise OSError("JSONL event exceeds bounded write limit")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.write("\n")
            stream.flush()
            if self.durable:
                os.fsync(stream.fileno())

    def _last_event(self) -> object:
        try:
            with self._synchronized():
                line = self._read_last_nonempty_line()
            return json.loads(line.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise fail_verification(
                "JSONL_AUDIT_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            ) from error

    def _last_event_unlocked(self) -> object:
        line = self._read_last_nonempty_line()
        return json.loads(line.decode("utf-8"))

    def _event_by_identity_unlocked(
        self,
        *,
        event_type: str,
        snapshot_id: str | None,
    ) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        with self.path.open("rb") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                if not raw_line.strip():
                    raise ValueError(f"JSONL audit line {line_number} cannot be blank")
                record = self._load_event_line(
                    raw_line,
                    label=f"JSONL audit line {line_number}",
                )
                if (
                    record.get("event_type") == event_type
                    and record.get("snapshot_id") == snapshot_id
                ):
                    return record
        return None

    def _chain_state_or_fail(self, *, subject_id: str) -> tuple[str, int]:
        try:
            if (
                self._legacy_path is not None
                and _file_sha256_or_none(self._legacy_path) != self._legacy_sha256
            ):
                raise ValueError("JSONL_AUDIT_LEGACY_ANCHOR_MISMATCH")
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
                event = self._load_event_line(
                    raw_line,
                    label=f"tamper-evident JSONL line {line_number}",
                )
                tamper_evident = event.get("tamper_evident")
                if tamper_evident is not True:
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
                        f"tamper-evident JSONL line {line_number} event hash is invalid"
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
                        "tamper-evident JSONL line "
                        f"{line_number} record hash is invalid"
                    )
                expected_previous = record_sha256
                expected_position += 1
        return expected_previous, expected_position

    @staticmethod
    def _load_event_line(raw_line: bytes, *, label: str) -> dict[str, object]:
        payload = json.loads(raw_line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{label} must be a JSON object")
        return payload


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


def _file_sha256_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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

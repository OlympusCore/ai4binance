"""Shared write-destination verification contracts."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "VERIFICATION_FAILED"


class DestinationVerificationError(ValueError):
    """Raised when a write cannot be proven from the changed destination."""


@dataclass(frozen=True, slots=True)
class VerifiedWriteResult:
    destination: str
    subject_id: str
    status: VerificationStatus
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
        if self.status is VerificationStatus.VERIFIED and self.blockers:
            raise ValueError("verified write cannot contain blockers")
        if self.status is VerificationStatus.FAILED and not self.blockers:
            raise ValueError("failed verification requires blockers")
        for digest in (self.expected_sha256, self.observed_sha256):
            if digest is not None and (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError("verified write hash is invalid")


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
        VerificationStatus.VERIFIED,
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
        VerificationStatus.FAILED,
        (blocker,),
    )
    return DestinationVerificationError(result.blockers[0])


def read_json_object(path: Path, *, blocker: str) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise fail_verification(
            blocker, destination=path, subject_id=str(path)
        ) from error
    if not isinstance(payload, Mapping):
        raise fail_verification(blocker, destination=path, subject_id=str(path))
    return payload


def write_json_object_verified(
    path: Path,
    payload: Mapping[str, object],
    *,
    blocker: str,
    subject_id: str | None = None,
    indent: int | None = None,
    durable: bool = False,
) -> VerifiedWriteResult:
    """Atomically write one JSON object, then prove it from the destination."""
    expected = dict(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        encoded = _json_dumps(expected, indent=indent) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            if durable:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
        observed = read_json_object(path, blocker=blocker)
    finally:
        temporary.unlink(missing_ok=True)
    if dict(observed) != expected:
        raise fail_verification(
            blocker,
            destination=path,
            subject_id=subject_id or str(path),
        )
    expected_hash = _canonical_json_sha256(expected)
    observed_hash = _canonical_json_sha256(dict(observed))
    return verified(
        path,
        subject_id or str(path),
        operation="json_state_write",
        expected_sha256=expected_hash,
        observed_sha256=observed_hash,
    )


def _json_dumps(payload: Mapping[str, object], *, indent: int | None) -> str:
    if indent is None:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=True)


def _canonical_json_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

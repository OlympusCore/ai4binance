"""Append-only persistence and audit utilities."""

from ai4binance.storage.destination_verification import (
    DestinationVerificationError,
    VerificationStatus,
    VerifiedWriteResult,
    write_json_object_verified,
)
from ai4binance.storage.jsonl import (
    AuditEvent,
    JsonlAuditStore,
    SecretRedactor,
    read_bounded_jsonl_tail,
)

__all__ = (
    "AuditEvent",
    "DestinationVerificationError",
    "JsonlAuditStore",
    "SecretRedactor",
    "VerificationStatus",
    "VerifiedWriteResult",
    "read_bounded_jsonl_tail",
    "write_json_object_verified",
)

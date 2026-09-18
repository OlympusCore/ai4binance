"""Externally anchorable checkpoint for a local tamper-evident JSONL journal."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from ai4binance.storage.jsonl import JsonlAuditStore, read_bounded_jsonl_tail


class AuditAnchorStatus(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    EXTERNAL_ANCHOR_RECORDED = "EXTERNAL_ANCHOR_RECORDED"


@dataclass(frozen=True, slots=True)
class AuditRetentionDirective:
    retention_class: str
    retain_until: date | None
    legal_hold: bool
    disposition_authority: str

    def __post_init__(self) -> None:
        if not self.retention_class.strip() or not self.disposition_authority.strip():
            raise ValueError("audit retention class and authority are required")
        if self.legal_hold and self.retain_until is not None:
            raise ValueError("legal hold cannot carry an automatic retain_until")

    def to_payload(self) -> dict[str, object]:
        return {
            "retention_class": self.retention_class,
            "retain_until": (
                None if self.retain_until is None else self.retain_until.isoformat()
            ),
            "legal_hold": self.legal_hold,
            "disposition_authority": self.disposition_authority,
        }


@dataclass(frozen=True, slots=True)
class AuditChainCheckpoint:
    checkpoint_id: str
    journal_ref: str
    journal_path_sha256: str
    chain_position: int
    record_sha256: str
    created_at: datetime
    retention: AuditRetentionDirective
    anchor_status: AuditAnchorStatus = AuditAnchorStatus.LOCAL_ONLY
    external_anchor_ref: str | None = None
    external_anchor_sha256: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not isinstance(self.anchor_status, AuditAnchorStatus):
            raise ValueError("audit checkpoint anchor status is invalid")
        if not self.checkpoint_id.strip() or not self.journal_ref.strip():
            raise ValueError("audit checkpoint identity is required")
        if self.chain_position < 1:
            raise ValueError("audit checkpoint chain_position must be positive")
        _require_sha256("record_sha256", self.record_sha256)
        _require_sha256("journal_path_sha256", self.journal_path_sha256)
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise ValueError("audit checkpoint created_at must be UTC")
        external = (self.external_anchor_ref, self.external_anchor_sha256)
        if any(value is None for value in external) != all(
            value is None for value in external
        ):
            raise ValueError("external audit anchor binding must be complete")
        if self.external_anchor_sha256 is not None:
            _require_sha256("external_anchor_sha256", self.external_anchor_sha256)
            if self.external_anchor_ref is None or not self.external_anchor_ref.strip():
                raise ValueError("external audit anchor reference is required")
        if (
            self.anchor_status is AuditAnchorStatus.EXTERNAL_ANCHOR_RECORDED
            and self.external_anchor_ref is None
        ):
            raise ValueError("recorded external anchor requires reference and hash")
        if (
            self.anchor_status is AuditAnchorStatus.LOCAL_ONLY
            and self.external_anchor_ref is not None
        ):
            raise ValueError("local-only checkpoint cannot claim an external anchor")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("audit checkpoint cannot grant execution authority")

    @property
    def semantic_sha256(self) -> str:
        canonical = json.dumps(
            self.to_payload(include_semantic_hash=False),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_payload(self, *, include_semantic_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "checkpoint_id": self.checkpoint_id,
            "journal_ref": self.journal_ref,
            "journal_path_sha256": self.journal_path_sha256,
            "chain_position": self.chain_position,
            "record_sha256": self.record_sha256,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "retention": self.retention.to_payload(),
            "anchor_status": self.anchor_status.value,
            "external_anchor_ref": self.external_anchor_ref,
            "external_anchor_sha256": self.external_anchor_sha256,
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }
        if include_semantic_hash:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload


def checkpoint_audit_chain(
    store: JsonlAuditStore,
    *,
    checkpoint_id: str,
    journal_ref: str,
    created_at: datetime,
    retention: AuditRetentionDirective,
    external_anchor_ref: str | None = None,
    external_anchor_sha256: str | None = None,
) -> AuditChainCheckpoint:
    """Verify the chain and bind its current head; no external write is performed."""
    head = store.verify_chain()
    tail = read_bounded_jsonl_tail(store.path, max_lines=1)
    if not tail:
        raise ValueError("audit checkpoint requires at least one journal record")
    try:
        record = json.loads(tail[0].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("audit checkpoint journal tail is invalid") from error
    if not isinstance(record, dict):
        raise ValueError("audit checkpoint journal tail must be an object")
    position = record.get("chain_position")
    record_hash = record.get("record_sha256")
    if not isinstance(position, int) or not isinstance(record_hash, str):
        raise ValueError("audit checkpoint requires a tamper-evident journal")
    if record_hash != head:
        raise ValueError("audit checkpoint head mismatch")
    if store.verify_chain() != head:
        raise ValueError("audit checkpoint journal changed during checkpoint")
    status = (
        AuditAnchorStatus.EXTERNAL_ANCHOR_RECORDED
        if external_anchor_ref is not None
        else AuditAnchorStatus.LOCAL_ONLY
    )
    return AuditChainCheckpoint(
        checkpoint_id=checkpoint_id,
        journal_ref=journal_ref,
        journal_path_sha256=_journal_path_sha256(store),
        chain_position=position,
        record_sha256=record_hash,
        created_at=created_at,
        retention=retention,
        anchor_status=status,
        external_anchor_ref=external_anchor_ref,
        external_anchor_sha256=external_anchor_sha256,
    )


def verify_audit_checkpoint(
    store: JsonlAuditStore, checkpoint: AuditChainCheckpoint
) -> bool:
    """Return whether the local chain still contains the checkpointed head."""
    if checkpoint.journal_path_sha256 != _journal_path_sha256(store):
        return False
    store.verify_chain()
    with store.path.open("rb") as stream:
        for raw_line in stream:
            if not raw_line.strip():
                return False
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
            if not isinstance(record, dict):
                return False
            position = record.get("chain_position")
            if position == checkpoint.chain_position:
                return record.get("record_sha256") == checkpoint.record_sha256
            if isinstance(position, int) and position > checkpoint.chain_position:
                return False
    return False


def _journal_path_sha256(store: JsonlAuditStore) -> str:
    return hashlib.sha256(str(store.path.resolve()).encode("utf-8")).hexdigest()


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


__all__ = (
    "AuditAnchorStatus",
    "AuditChainCheckpoint",
    "AuditRetentionDirective",
    "checkpoint_audit_chain",
    "verify_audit_checkpoint",
)

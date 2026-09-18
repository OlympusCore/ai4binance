"""Append-only persistence for portfolio bucket-state evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from ai4binance.portfolio.rebalancing import InventoryBuckets


@dataclass(frozen=True, slots=True)
class PortfolioBucketPersistenceEvidence:
    """Bounded evidence that one bucket-state snapshot was persisted."""

    bucket_state_id: str
    observed_at: datetime
    path: Path
    persisted: bool
    snapshot_hash: str
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.bucket_state_id.strip():
            raise ValueError("portfolio bucket-state identity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("portfolio bucket-state timestamp must be timezone-aware")
        if not str(self.path).strip():
            raise ValueError("portfolio bucket-state path is required")
        if self.persisted and self.blockers:
            raise ValueError("persisted portfolio bucket-state cannot contain blockers")
        if not self.persisted and not self.blockers:
            raise ValueError("failed portfolio bucket-state must declare blockers")
        if len(self.snapshot_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.snapshot_hash
        ):
            raise ValueError("portfolio bucket-state hash must be lowercase SHA-256")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("portfolio bucket-state cannot authorize execution")


@dataclass(frozen=True, slots=True)
class PortfolioBucketStateStore:
    """Persist immutable bucket snapshots with deterministic read-back."""

    path: Path

    def save(
        self,
        *,
        bucket_state_id: str,
        observed_at: datetime,
        buckets: InventoryBuckets,
    ) -> PortfolioBucketPersistenceEvidence:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("portfolio bucket-state timestamp must be timezone-aware")
        normalized_state_id = bucket_state_id.strip()
        if not normalized_state_id:
            raise ValueError("portfolio bucket-state identity is required")
        payload = {
            "bucket_state_id": normalized_state_id,
            "observed_at": observed_at.isoformat(),
            "state_version": 1,
            "buckets": {
                "core_units": str(buckets.core_units),
                "strategic_units": str(buckets.strategic_units),
                "tactical_units": str(buckets.tactical_units),
                "cash_quote": str(buckets.cash_quote),
                "reserved_cash_quote": str(buckets.reserved_cash_quote),
                "pending_rebuy_cash_quote": str(buckets.pending_rebuy_cash_quote),
                "last_stage": buckets.last_stage,
                "last_side": buckets.last_side,
                "last_stage_clock": buckets.last_stage_clock,
            },
        }
        snapshot_hash = sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        payload["snapshot_hash"] = snapshot_hash
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)
        observed = json.loads(self.path.read_text(encoding="utf-8"))
        if observed != payload:
            raise ValueError("portfolio bucket-state persistence verification failed")
        return PortfolioBucketPersistenceEvidence(
            bucket_state_id=normalized_state_id,
            observed_at=observed_at,
            path=self.path,
            persisted=True,
            snapshot_hash=snapshot_hash,
        )


def snapshot_hash(
    bucket_state_id: str,
    observed_at: datetime,
    buckets: InventoryBuckets,
) -> str:
    """Compute the canonical persistence hash without writing a file."""
    normalized_state_id = bucket_state_id.strip()
    if not normalized_state_id:
        raise ValueError("portfolio bucket-state identity is required")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("portfolio bucket-state timestamp must be timezone-aware")
    payload = {
        "bucket_state_id": normalized_state_id,
        "observed_at": observed_at.isoformat(),
        "state_version": 1,
        "buckets": {
            "core_units": str(buckets.core_units),
            "cash_quote": str(buckets.cash_quote),
            "last_side": buckets.last_side,
            "last_stage": buckets.last_stage,
            "last_stage_clock": buckets.last_stage_clock,
            "pending_rebuy_cash_quote": str(buckets.pending_rebuy_cash_quote),
            "reserved_cash_quote": str(buckets.reserved_cash_quote),
            "strategic_units": str(buckets.strategic_units),
            "tactical_units": str(buckets.tactical_units),
        },
    }
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

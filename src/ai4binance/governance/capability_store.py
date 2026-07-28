"""Run-scoped, single-use capability leases for governed tools."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ai4binance.governance.tool_policy import (
    ToolDescriptor,
    ToolPermission,
    ToolSideEffect,
)

_CREATE = """
CREATE TABLE IF NOT EXISTS capability_leases (
    lease_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    permission TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    execution_id TEXT UNIQUE
)
"""

_PROHIBITED_EFFECTS = frozenset(
    {
        ToolSideEffect.EXTERNAL_WRITE,
        ToolSideEffect.FINANCIAL,
        ToolSideEffect.FORBIDDEN,
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityLease:
    run_id: str
    project: str
    tool_name: str
    permission: ToolPermission
    policy_hash: str
    issued_at: datetime
    expires_at: datetime
    lease_id: str = field(default_factory=lambda: str(uuid4()))
    consumed_at: datetime | None = None
    execution_id: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.lease_id.strip()
            or not self.run_id.strip()
            or not self.project.strip()
            or not self.tool_name.strip()
        ):
            raise ValueError("capability lease identity is required")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("capability lease timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("capability lease expiry must be after issue time")
        if len(self.policy_hash) != 64:
            raise ValueError("capability lease policy hash is invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("capability lease cannot authorize trading")


class CapabilityStore:
    """Issues authority that must be consumed once before a tool operation."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        ttl_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("capability lease ttl must be positive")
        self.path = runtime_root.resolve() / "governance.db"
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))

    def issue(
        self,
        *,
        run_id: str,
        project: str,
        descriptor: ToolDescriptor,
        permission: ToolPermission,
        policy_hash: str,
    ) -> CapabilityLease:
        if descriptor.side_effect in _PROHIBITED_EFFECTS:
            raise PermissionError("CAPABILITY_LEASE_PROHIBITED")
        if descriptor.side_effect is ToolSideEffect.WRITE_LOCAL:
            raise PermissionError("CAPABILITY_LEASE_APPROVAL_REQUIRED")
        if project not in descriptor.allowed_projects:
            raise PermissionError("CAPABILITY_PROJECT_NOT_ALLOWED")
        issued_at = self._clock()
        lease = CapabilityLease(
            run_id=run_id,
            project=project,
            tool_name=descriptor.name,
            permission=permission,
            policy_hash=policy_hash,
            issued_at=issued_at,
            expires_at=issued_at + self._ttl,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(_CREATE)
            connection.execute(
                """
                INSERT INTO capability_leases (
                    lease_id, run_id, project, tool_name, permission, policy_hash,
                    issued_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lease.lease_id,
                    lease.run_id,
                    lease.project,
                    lease.tool_name,
                    lease.permission.value,
                    lease.policy_hash,
                    lease.issued_at.isoformat(),
                    lease.expires_at.isoformat(),
                ),
            )
            connection.commit()
        return lease

    def consume(self, lease: CapabilityLease, *, execution_id: str) -> CapabilityLease:
        if not execution_id.strip():
            raise ValueError("capability execution id is required")
        now = self._clock()
        with sqlite3.connect(self.path, isolation_level="IMMEDIATE") as connection:
            connection.execute(_CREATE)
            row = connection.execute(
                """
                SELECT run_id, project, tool_name, permission, policy_hash,
                       issued_at, expires_at, consumed_at
                FROM capability_leases WHERE lease_id = ?
                """,
                (lease.lease_id,),
            ).fetchone()
            if row is None:
                raise PermissionError("CAPABILITY_NOT_REGISTERED")
            expected = (
                lease.run_id,
                lease.project,
                lease.tool_name,
                lease.permission.value,
                lease.policy_hash,
                lease.issued_at.isoformat(),
                lease.expires_at.isoformat(),
            )
            if tuple(str(item) for item in row[:7]) != expected:
                raise PermissionError("CAPABILITY_BINDING_MISMATCH")
            if row[7] is not None:
                raise PermissionError("CAPABILITY_REPLAY_BLOCKED")
            if now > lease.expires_at:
                raise PermissionError("CAPABILITY_EXPIRED")
            try:
                updated = connection.execute(
                    """
                    UPDATE capability_leases
                    SET consumed_at = ?, execution_id = ?
                    WHERE lease_id = ? AND consumed_at IS NULL
                    """,
                    (now.isoformat(), execution_id, lease.lease_id),
                ).rowcount
            except sqlite3.IntegrityError as exc:
                raise PermissionError("CAPABILITY_EXECUTION_REPLAY_BLOCKED") from exc
            if updated != 1:
                raise PermissionError("CAPABILITY_REPLAY_BLOCKED")
            connection.commit()
        return CapabilityLease(
            run_id=lease.run_id,
            project=lease.project,
            tool_name=lease.tool_name,
            permission=lease.permission,
            policy_hash=lease.policy_hash,
            issued_at=lease.issued_at,
            expires_at=lease.expires_at,
            lease_id=lease.lease_id,
            consumed_at=now,
            execution_id=execution_id,
        )

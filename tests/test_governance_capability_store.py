from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, TypedDict, Unpack

import pytest

from ai4binance.governance import (
    CapabilityLease,
    CapabilityStore,
    ToolDescriptor,
    ToolPermission,
    ToolSideEffect,
    canonical_sha256,
)


class CapabilityConnectOptions(TypedDict, total=False):
    isolation_level: Literal["DEFERRED", "EXCLUSIVE", "IMMEDIATE"] | None


def assert_connections_closed(connections: list[sqlite3.Connection]) -> None:
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def descriptor(
    side_effect: ToolSideEffect = ToolSideEffect.READ_LOCAL,
) -> ToolDescriptor:
    return ToolDescriptor(
        "quality-triage",
        "Read local quality triage artifacts",
        ("ai4binance",),
        side_effect,
    )


def test_capability_store_issues_consumes_and_blocks_replay(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = CapabilityStore(tmp_path, clock=lambda: now)
    lease = store.issue(
        run_id="run-1",
        project="ai4binance",
        descriptor=descriptor(),
        permission=ToolPermission.READ_ONLY,
        policy_hash=canonical_sha256({"policy": "allow-read"}),
    )

    consumed = store.consume(lease, execution_id="execution-1")

    assert consumed.consumed_at == now
    assert consumed.execution_id == "execution-1"
    assert consumed.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(PermissionError, match="REPLAY"):
        store.consume(lease, execution_id="execution-2")


def test_capability_store_verifies_registered_scope_bound_consumption(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = CapabilityStore(tmp_path, clock=lambda: now)
    lease = store.issue(
        run_id="run-1",
        project="ai4binance",
        descriptor=descriptor(),
        permission=ToolPermission.READ_ONLY,
        policy_hash="a" * 64,
        scope_hash="b" * 64,
    )
    consumed = store.consume(lease, execution_id="execution-1")

    store.verify_consumed(
        consumed,
        execution_id="execution-1",
        enforced_at=now + timedelta(seconds=1),
    )
    with pytest.raises(PermissionError, match="NOT_CONSUMED_FOR_ENFORCEMENT"):
        store.verify_consumed(
            consumed,
            execution_id="other-execution",
            enforced_at=now + timedelta(seconds=1),
        )
    with pytest.raises(PermissionError, match="CONSUMPTION_OUT_OF_WINDOW"):
        store.verify_consumed(
            replace(consumed, consumed_at=now + timedelta(seconds=2)),
            execution_id="execution-1",
            enforced_at=now + timedelta(seconds=3),
        )


def test_capability_store_closes_connections_after_all_transaction_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def tracked_connect(
        database: str | Path,
        **options: Unpack[CapabilityConnectOptions],
    ) -> sqlite3.Connection:
        connection = connect(database, **options)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    monkeypatch.setattr(
        "ai4binance.governance.capability_store.uuid4",
        lambda: "fixed-lease-id",
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store = CapabilityStore(tmp_path, clock=lambda: now)

    def issue_lease() -> CapabilityLease:
        return store.issue(
            run_id="run-close",
            project="ai4binance",
            descriptor=descriptor(),
            permission=ToolPermission.READ_ONLY,
            policy_hash=canonical_sha256({"policy": "close-connections"}),
        )

    lease = issue_lease()
    with pytest.raises(sqlite3.IntegrityError):
        issue_lease()
    store.consume(lease, execution_id="execution-close")
    with pytest.raises(PermissionError, match="REPLAY"):
        store.consume(lease, execution_id="execution-replay")
    with pytest.raises(PermissionError, match="NOT_REGISTERED"):
        store.consume(
            CapabilityLease(
                run_id="run-missing",
                project="ai4binance",
                tool_name="quality-triage",
                permission=ToolPermission.READ_ONLY,
                policy_hash=canonical_sha256({"policy": "missing"}),
                issued_at=now,
                expires_at=now + timedelta(minutes=1),
                lease_id="missing-lease-id",
            ),
            execution_id="execution-missing",
        )

    assert len(opened) == 5
    assert_connections_closed(opened)


def test_capability_store_rejects_prohibited_and_write_local_leases(
    tmp_path: Path,
) -> None:
    store = CapabilityStore(tmp_path)
    with pytest.raises(PermissionError, match="PROHIBITED"):
        store.issue(
            run_id="run-1",
            project="ai4binance",
            descriptor=descriptor(ToolSideEffect.FINANCIAL),
            permission=ToolPermission.WRITE_APPROVED,
            policy_hash=canonical_sha256({"policy": "bad"}),
        )
    with pytest.raises(PermissionError, match="APPROVAL_REQUIRED"):
        store.issue(
            run_id="run-1",
            project="ai4binance",
            descriptor=descriptor(ToolSideEffect.WRITE_LOCAL),
            permission=ToolPermission.WRITE_APPROVED,
            policy_hash=canonical_sha256({"policy": "write"}),
        )


def test_capability_store_rejects_expired_and_invalid_contracts(
    tmp_path: Path,
) -> None:
    current = datetime(2026, 1, 1, tzinfo=UTC)

    def clock() -> datetime:
        return current

    store = CapabilityStore(tmp_path, ttl_seconds=1, clock=clock)
    lease = store.issue(
        run_id="run-1",
        project="ai4binance",
        descriptor=descriptor(),
        permission=ToolPermission.READ_ONLY,
        policy_hash=canonical_sha256({"policy": "allow-read"}),
    )
    current = current + timedelta(seconds=2)
    with pytest.raises(PermissionError, match="EXPIRED"):
        store.consume(lease, execution_id="execution-1")
    with pytest.raises(ValueError, match="ttl"):
        CapabilityStore(tmp_path, ttl_seconds=0)
    with pytest.raises(ValueError, match="cannot authorize"):
        CapabilityLease(
            run_id="run",
            project="ai4binance",
            tool_name="tool",
            permission=ToolPermission.READ_ONLY,
            policy_hash="a" * 64,
            issued_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=datetime(2026, 1, 2, tzinfo=UTC),
            execution_allowed=True,
        )


def test_capability_store_rejects_binding_project_and_contract_edges(
    tmp_path: Path,
) -> None:
    store = CapabilityStore(tmp_path)
    with pytest.raises(PermissionError, match="PROJECT"):
        store.issue(
            run_id="run-1",
            project="other",
            descriptor=descriptor(),
            permission=ToolPermission.READ_ONLY,
            policy_hash=canonical_sha256({"policy": "allow-read"}),
        )
    with pytest.raises(PermissionError, match="NOT_REGISTERED"):
        store.consume(
            CapabilityLease(
                run_id="run",
                project="ai4binance",
                tool_name="tool",
                permission=ToolPermission.READ_ONLY,
                policy_hash="a" * 64,
                issued_at=datetime(2026, 1, 1, tzinfo=UTC),
                expires_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
            execution_id="execution",
        )
    with pytest.raises(ValueError, match="execution id"):
        store.consume(
            store.issue(
                run_id="run-1",
                project="ai4binance",
                descriptor=descriptor(),
                permission=ToolPermission.READ_ONLY,
                policy_hash=canonical_sha256({"policy": "allow-read"}),
            ),
            execution_id=" ",
        )
    with pytest.raises(ValueError, match="identity"):
        CapabilityLease(
            run_id="",
            project="ai4binance",
            tool_name="tool",
            permission=ToolPermission.READ_ONLY,
            policy_hash="a" * 64,
            issued_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="after"):
        CapabilityLease(
            run_id="run",
            project="ai4binance",
            tool_name="tool",
            permission=ToolPermission.READ_ONLY,
            policy_hash="a" * 64,
            issued_at=datetime(2026, 1, 2, tzinfo=UTC),
            expires_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

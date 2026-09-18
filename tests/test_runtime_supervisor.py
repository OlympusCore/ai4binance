"""Resident runtime persistence and single-instance tests."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.application.runtime import DualMarketAdvisoryReport
from ai4binance.ops import (
    PrivateRuntimeStatusStore,
    RuntimeManagementLedger,
    RuntimeStatusStore,
    RuntimeSupervisor,
    SingleInstanceLease,
)
from ai4binance.portfolio.orders import AccountOpenOrder
from ai4binance.storage import DestinationVerificationError
from tests.test_runtime_cycle import NOW, cycle


def test_runtime_store_excludes_private_account_payloads(tmp_path: Path) -> None:
    path = tmp_path / "state" / "runtime.json"
    report = cycle().run(NOW)

    RuntimeStatusStore(path).save(report)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["state"] == "DEGRADED"
    assert payload["execution_allowed"] is False
    assert payload["investment_management"]["execution_allowed"] is False
    assert "spot_wallet" not in payload
    assert "futures_account" not in payload
    assert "total_wallet_balance" not in path.read_text(encoding="utf-8")


def test_runtime_store_stops_when_destination_read_back_does_not_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state" / "runtime.json"
    original = Path.read_text

    def tampered_read_text(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        payload = original(self, encoding, errors)
        return (
            payload.replace("LIVE_ORDER_BLOCKED", "EXECUTION_ALLOWED", 1)
            if (self == path)
            else payload
        )

    monkeypatch.setattr(Path, "read_text", tampered_read_text)
    with pytest.raises(DestinationVerificationError, match="RUNTIME_STATE"):
        RuntimeStatusStore(path).save(cycle().run(NOW))


def test_runtime_store_retries_transient_windows_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state" / "runtime.json"
    original_replace = Path.replace
    attempts = {"count": 0}

    def flaky_replace(self: Path, target: Path) -> Path:
        if self == path.with_suffix(".json.tmp") and attempts["count"] == 0:
            attempts["count"] += 1
            raise PermissionError(5, "Access is denied")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    RuntimeStatusStore(path).save(cycle().run(NOW))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert attempts["count"] == 1


def test_private_runtime_store_contains_account_detail_but_no_credentials(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private" / "account-management.json"
    ledger_path = tmp_path / "private" / "account-management-events.jsonl"
    accounting_root = tmp_path / "private" / "binance-accounting"

    PrivateRuntimeStatusStore(path, ledger_path, accounting_root).save(cycle().run(NOW))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert {item["asset"] for item in payload["inventory"]} == {"HOT", "USDT"}
    assert payload["open_orders"] == []
    assert payload["execution_allowed"] is False
    text = path.read_text(encoding="utf-8")
    assert "BINANCE_API_KEY" not in text
    assert "BINANCE_API_SECRET" not in text
    assert payload["open_order_reconciliation"]["status"] == "NOT_AVAILABLE"
    event = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["event_type"] == "PRIVATE_ACCOUNT_MANAGEMENT_SNAPSHOT"
    assert event["payload"]["execution_allowed"] is False
    assert event["payload"]["inventory"][0]["asset"] == "HOT"
    spot_balances = (accounting_root / "spot" / "balance_snapshots.jsonl").read_text(
        encoding="utf-8"
    )
    futures_account = (
        accounting_root / "futures_usdm" / "account_snapshots.jsonl"
    ).read_text(encoding="utf-8")
    shared_sync = (accounting_root / "shared" / "api_sync_runs.jsonl").read_text(
        encoding="utf-8"
    )
    assert "SPOT_BALANCE_SNAPSHOT_RECORDED" in spot_balances
    assert "FUTURES_USDM_ACCOUNT_SNAPSHOT_RECORDED" in futures_account
    assert "API_SYNC_RUN_RECORDED" in shared_sync
    assert '"product_type":"SPOT"' in spot_balances
    assert '"product_type":"FUTURES_USDM"' in futures_account
    assert '"product_type":"MULTI_PRODUCT"' in shared_sync
    assert "HOT_INVENTORY" not in futures_account


def test_private_store_reconciles_previous_expected_open_orders(tmp_path: Path) -> None:
    path = tmp_path / "private" / "account-management.json"
    store = PrivateRuntimeStatusStore(path)
    base = cycle().run(NOW)
    assert base.spot_wallet is not None

    def order(client_id: str, remaining: str) -> AccountOpenOrder:
        quantity = Decimal(remaining)
        return AccountOpenOrder(
            "SPOT",
            f"exchange-{client_id}",
            client_id,
            "HOTUSDT",
            "BUY",
            "LIMIT",
            "NEW",
            Decimal("0.001"),
            quantity,
            Decimal("0"),
        )

    first_wallet = replace(
        base.spot_wallet,
        open_orders=(order("known", "2"), order("missing", "1")),
    )
    store.save(replace(base, spot_wallet=first_wallet))
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["open_order_reconciliation"]["status"] == "NOT_AVAILABLE"

    second_wallet = replace(
        base.spot_wallet,
        open_orders=(order("known", "1.5"), order("unknown", "1")),
    )
    store.save(replace(base, spot_wallet=second_wallet))

    reconciliation = json.loads(path.read_text(encoding="utf-8"))[
        "open_order_reconciliation"
    ]
    assert reconciliation["status"] == "COMPLETE"
    assert reconciliation["missing_on_exchange"] == ["SPOT:missing"]
    assert reconciliation["unknown_on_exchange"] == ["SPOT:unknown"]
    assert reconciliation["quantity_mismatches"] == ["SPOT:known"]
    assert reconciliation["execution_allowed"] is False


def test_supervisor_runs_bounded_cycles_without_sleeping_after_last(
    tmp_path: Path,
) -> None:
    report = cycle().run(NOW)
    sleeps: list[float] = []
    private_path = tmp_path / "private.json"
    management_ledger_path = tmp_path / "wallet-management.jsonl"
    supervisor = RuntimeSupervisor(
        cycle=lambda: report,
        store=RuntimeStatusStore(tmp_path / "runtime.json"),
        interval_seconds=5,
        private_store=PrivateRuntimeStatusStore(private_path),
        management_ledger=RuntimeManagementLedger(management_ledger_path),
        sleeper=sleeps.append,
    )

    assert supervisor.run(max_cycles=2) == 2
    assert sleeps == [5]
    assert private_path.exists()
    events = [
        json.loads(line)
        for line in management_ledger_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events] == [
        "WALLET_MANAGEMENT_REVIEW",
        "WALLET_MANAGEMENT_REVIEW",
    ]
    assert events[0]["payload"]["opportunity_count"] > 0
    assert events[0]["payload"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_single_instance_lease_rejects_duplicate_and_cleans_up(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.lock"
    first = SingleInstanceLease(path)
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already active"):
            SingleInstanceLease(path).acquire()
    finally:
        first.release()
    assert not path.exists()


def test_single_instance_lease_recovers_a_recycled_process_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.lock"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": os.getpid(),
                "process_marker": "windows-filetime:recycled",
            }
        ),
        encoding="ascii",
    )

    with SingleInstanceLease(path):
        payload = json.loads(path.read_text(encoding="ascii"))
        assert payload["pid"] == os.getpid()
        assert payload["process_marker"] != "windows-filetime:recycled"


@pytest.mark.skipif(os.name != "nt", reason="Windows process handle semantics")
@pytest.mark.parametrize("exit_code", [0, 259])
def test_single_instance_lease_recovers_terminated_process_with_retained_handle(
    tmp_path: Path, exit_code: int
) -> None:
    path = tmp_path / "runtime.lock"
    with subprocess.Popen(  # noqa: S603 - Fixed local fixture; no shell or external input.
        [sys.executable, "-c", f"raise SystemExit({exit_code})"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as process:
        process.wait(timeout=10)
        assert process.returncode == exit_code
        path.write_text(str(process.pid), encoding="ascii")
        with SingleInstanceLease(path):
            payload = json.loads(path.read_text(encoding="ascii"))
            assert payload["pid"] == os.getpid()
        assert not path.exists()


def test_single_instance_lease_recovers_stale_pid(tmp_path: Path) -> None:
    path = tmp_path / "runtime.lock"
    path.write_text("999999999", encoding="ascii")

    lease = SingleInstanceLease(path)
    lease.acquire()
    lease.release()

    assert not path.exists()


def test_runtime_supervisor_rejects_invalid_bounds_and_lock(tmp_path: Path) -> None:
    report = cycle().run(NOW)
    with pytest.raises(ValueError, match="between 5 and 3600"):
        RuntimeSupervisor(
            lambda: report, RuntimeStatusStore(tmp_path / "state.json"), 4
        )
    supervisor = RuntimeSupervisor(
        lambda: report, RuntimeStatusStore(tmp_path / "state.json"), 5
    )
    with pytest.raises(ValueError, match="positive"):
        supervisor.run(max_cycles=0)
    lock = tmp_path / "invalid.lock"
    lock.write_text("not-a-pid", encoding="ascii")
    with pytest.raises(RuntimeError, match="manual review"):
        SingleInstanceLease(lock).acquire()


def test_supervisor_isolates_cycle_failures_and_recovers(tmp_path: Path) -> None:
    report = cycle().run(NOW)
    outcomes = iter((RuntimeError("credential detail must not leak"), report))
    sleeps: list[float] = []

    def flaky_cycle() -> DualMarketAdvisoryReport:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    path = tmp_path / "runtime.json"
    supervisor = RuntimeSupervisor(
        flaky_cycle,
        RuntimeStatusStore(path),
        interval_seconds=60,
        sleeper=sleeps.append,
        failure_backoff_seconds=5,
        clock=lambda: NOW,
    )

    assert supervisor.run(max_cycles=2) == 1
    assert sleeps == [5]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["health"]["status"] == "DEGRADED"
    assert payload["health"]["consecutive_failures"] == 0
    assert "credential detail" not in path.read_text(encoding="utf-8")


def test_supervisor_persists_failure_health_and_caps_backoff(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    sleeps: list[float] = []

    def fail_cycle() -> DualMarketAdvisoryReport:
        raise OSError("secret-bearing upstream error")

    supervisor = RuntimeSupervisor(
        fail_cycle,
        RuntimeStatusStore(path),
        interval_seconds=60,
        sleeper=sleeps.append,
        failure_backoff_seconds=2,
        max_failure_backoff_seconds=3,
        clock=lambda: NOW,
    )

    assert supervisor.run(max_cycles=3) == 0
    assert sleeps == [2, 3]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["state"] == "DEGRADED"
    assert payload["blockers"] == ["RUNTIME_CYCLE_FAILED"]
    assert payload["health"]["status"] == "FAILED"
    assert payload["health"]["consecutive_failures"] == 3
    assert payload["health"]["error_category"] == "OSError"
    assert "secret-bearing" not in path.read_text(encoding="utf-8")

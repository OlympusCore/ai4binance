"""Resident runtime supervision and secret-safe status persistence."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from ai4binance.accounting import BinanceAccountLedger
from ai4binance.application.runtime import DualMarketAdvisoryReport
from ai4binance.portfolio.orders import AccountOpenOrder
from ai4binance.portfolio.reconciliation import OpenOrderView, reconcile_open_orders
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.storage.destination_verification import fail_verification


@dataclass(frozen=True, slots=True)
class RuntimeStatusStore:
    path: Path

    def save(self, report: DualMarketAdvisoryReport) -> None:
        """Persist advisory summaries without wallet balances or credentials."""
        payload: dict[str, object] = {
            "cycle_id": report.cycle_id,
            "symbol": report.symbol,
            "created_at": report.created_at,
            "state": report.state,
            "spot": report.spot,
            "futures": report.futures,
            "investment_management": report.investment_management,
            "portfolio_analytics": report.portfolio_analytics,
            "blockers": report.blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "health": {
                "status": "HEALTHY" if not report.blockers else "DEGRADED",
                "last_attempt_at": report.created_at,
                "last_success_at": report.created_at,
                "consecutive_failures": 0,
            },
        }
        self._save_payload(payload)

    def save_failure(self, error: Exception, attempted_at: datetime) -> None:
        """Persist a bounded, secret-safe cycle failure without exception text."""
        if attempted_at.tzinfo is None or attempted_at.utcoffset() is None:
            raise ValueError("runtime health timestamp must be timezone-aware")
        previous = self._read_previous_health()
        previous_failures = previous.get("consecutive_failures", 0)
        if isinstance(previous_failures, bool) or not isinstance(
            previous_failures, int
        ):
            previous_failures = 0
        payload: dict[str, object] = {
            "cycle_id": None,
            "symbol": None,
            "created_at": attempted_at,
            "state": "DEGRADED",
            "spot": None,
            "futures": None,
            "investment_management": None,
            "blockers": ("RUNTIME_CYCLE_FAILED",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "health": {
                "status": "FAILED",
                "last_attempt_at": attempted_at,
                "last_success_at": previous.get("last_success_at"),
                "consecutive_failures": previous_failures + 1,
                "error_category": type(error).__name__[:100],
            },
        }
        self._save_payload(payload)

    def _read_previous_health(self) -> dict[str, object]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        health = payload.get("health")
        return health if isinstance(health, dict) else {}

    def _save_payload(self, payload: dict[str, object]) -> None:
        expected = to_primitive(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(expected, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self._verify_payload(expected)

    def _verify_payload(self, expected: object) -> None:
        try:
            observed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise fail_verification(
                "RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            ) from error
        if observed != expected:
            raise fail_verification(
                "RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            )


@dataclass(frozen=True, slots=True)
class RuntimeManagementLedger:
    """Append-only public management ledger without raw wallet balances."""

    path: Path

    def append(self, report: DualMarketAdvisoryReport) -> None:
        payload: dict[str, object] = {
            "cycle_id": report.cycle_id,
            "symbol": report.symbol,
            "created_at": report.created_at,
            "state": report.state,
            "spot": report.spot,
            "futures": report.futures,
            "investment_management": report.investment_management,
            "portfolio_analytics": report.portfolio_analytics,
            "cost_basis": report.cost_basis,
            "blockers": report.blockers,
            "opportunity_count": (
                len(report.investment_management.recommendations)
                if report.investment_management is not None
                else 0
            ),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        JsonlAuditStore(self.path).append_verified(
            AuditEvent(
                event_type="WALLET_MANAGEMENT_REVIEW",
                timestamp=report.created_at,
                snapshot_id=report.cycle_id,
                payload=payload,
            )
        )

    def append_failure(self, error: Exception, attempted_at: datetime) -> None:
        JsonlAuditStore(self.path).append_verified(
            AuditEvent(
                event_type="WALLET_MANAGEMENT_REVIEW_FAILED",
                timestamp=attempted_at,
                payload={
                    "blockers": ("RUNTIME_CYCLE_FAILED",),
                    "error_category": type(error).__name__[:100],
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            )
        )


@dataclass(frozen=True, slots=True)
class PrivateRuntimeStatusStore:
    """Persist account detail only under an operator-protected local path."""

    path: Path
    ledger_path: Path | None = None
    accounting_root: Path | None = None

    def save(self, report: DualMarketAdvisoryReport) -> None:
        previous = self._read_previous_payload()
        wallet = report.spot_wallet
        futures = report.futures_account
        spot_orders = wallet.open_orders if wallet is not None else ()
        futures_orders = futures.open_orders if futures is not None else ()
        exchange_orders = (*spot_orders, *futures_orders)
        reconciliation = self._reconcile(previous, exchange_orders)
        payload = {
            "cycle_id": report.cycle_id,
            "symbol": report.symbol,
            "created_at": report.created_at,
            "state": report.state,
            "spot": report.spot,
            "futures": report.futures,
            "inventory": tuple(
                {
                    "asset": item.asset,
                    "free": item.free,
                    "locked": item.locked,
                    "total": item.free + item.locked,
                }
                for item in (wallet.balances if wallet is not None else ())
                if item.free + item.locked > 0
            ),
            "futures_positions": tuple(
                {
                    "symbol": item.symbol,
                    "side": "LONG" if item.quantity > 0 else "SHORT",
                    "quantity": abs(item.quantity),
                    "entry_price": item.entry_price,
                    "mark_price": item.mark_price,
                    "liquidation_price": item.liquidation_price,
                    "leverage": item.leverage,
                    "margin_type": item.margin_type,
                    "notional": item.notional,
                    "isolated_margin": item.isolated_margin,
                    "unrealized_pnl": item.unrealized_pnl,
                }
                for item in (futures.positions if futures is not None else ())
                if item.quantity != 0
            ),
            "open_orders": tuple(
                {
                    "market": item.market,
                    "client_order_id": item.client_order_id,
                    "symbol": item.symbol,
                    "side": item.side,
                    "type": item.order_type,
                    "status": item.status,
                    "price": item.price,
                    "original_quantity": item.original_quantity,
                    "executed_quantity": item.executed_quantity,
                    "remaining_quantity": item.remaining_quantity,
                }
                for item in exchange_orders
            ),
            "open_order_snapshot_version": 1,
            "open_order_reconciliation": reconciliation,
            "investment_management": report.investment_management,
            "portfolio_analytics": report.portfolio_analytics,
            "blockers": report.blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        expected = to_primitive(payload)
        temporary.write_text(
            json.dumps(expected, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self._verify_payload(expected)
        if self.ledger_path is not None:
            JsonlAuditStore(self.ledger_path).append_verified(
                AuditEvent(
                    event_type="PRIVATE_ACCOUNT_MANAGEMENT_SNAPSHOT",
                    timestamp=report.created_at,
                    snapshot_id=report.cycle_id,
                    payload=payload,
                )
            )
        if self.accounting_root is not None:
            BinanceAccountLedger(self.accounting_root).append_runtime_report(report)

    def _read_previous_payload(self) -> dict[str, object] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _verify_payload(self, expected: object) -> None:
        try:
            observed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise fail_verification(
                "PRIVATE_RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            ) from error
        if observed != expected:
            raise fail_verification(
                "PRIVATE_RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=str(self.path),
            )

    @staticmethod
    def _reconcile(
        previous: dict[str, object] | None,
        exchange_orders: tuple[AccountOpenOrder, ...],
    ) -> dict[str, object]:
        unavailable = {
            "status": "NOT_AVAILABLE",
            "local_count": 0,
            "exchange_count": len(exchange_orders),
            "missing_on_exchange": (),
            "unknown_on_exchange": (),
            "quantity_mismatches": (),
            "blockers": ("LOCAL_EXPECTED_OPEN_ORDER_SNAPSHOT_NOT_AVAILABLE",),
            "execution_allowed": False,
        }
        if previous is None or previous.get("open_order_snapshot_version") != 1:
            return unavailable
        raw_orders = previous.get("open_orders")
        if not isinstance(raw_orders, list):
            return unavailable
        try:
            local = tuple(_stored_order_view(item) for item in raw_orders)
            exchange = tuple(_account_order_view(item) for item in exchange_orders)
            report = reconcile_open_orders(local, exchange)
        except (InvalidOperation, TypeError, ValueError):
            return unavailable
        report_payload = cast(dict[str, object], to_primitive(report))
        return {
            "status": "COMPLETE",
            **report_payload,
        }


def _stored_order_view(payload: object) -> OpenOrderView:
    if not isinstance(payload, dict):
        raise ValueError("stored open order must be an object")
    market = str(payload.get("market", "")).strip()
    client_order_id = str(payload.get("client_order_id", "")).strip()
    symbol = str(payload.get("symbol", "")).strip()
    remaining = Decimal(str(payload.get("remaining_quantity", "")))
    return OpenOrderView(f"{market}:{client_order_id}", symbol, remaining)


def _account_order_view(order: AccountOpenOrder) -> OpenOrderView:
    return OpenOrderView(
        f"{order.market}:{order.client_order_id}",
        order.symbol,
        order.remaining_quantity,
    )


@dataclass(slots=True)
class SingleInstanceLease:
    path: Path
    _held: bool = field(default=False, init=False)

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_stale_lease()
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            raise RuntimeError("runtime instance is already active") from None
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
        finally:
            os.close(descriptor)
        self._held = True

    def _remove_stale_lease(self) -> None:
        if not self.path.exists():
            return
        try:
            pid = int(self.path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            raise RuntimeError(
                "runtime lock is invalid; manual review required"
            ) from None
        if not self._pid_is_alive(pid):
            self.path.unlink(missing_ok=True)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        if pid < 1:
            return False
        if os.name == "nt":
            import ctypes

            process_query_limited_information = 0x1000
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return ctypes.get_last_error() == 5
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self) -> SingleInstanceLease:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.release()


@dataclass(frozen=True, slots=True)
class RuntimeSupervisor:
    cycle: Callable[[], DualMarketAdvisoryReport]
    store: RuntimeStatusStore
    interval_seconds: float = 60.0
    private_store: PrivateRuntimeStatusStore | None = None
    management_ledger: RuntimeManagementLedger | None = None
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    failure_backoff_seconds: float = 5.0
    max_failure_backoff_seconds: float = 300.0
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)

    def __post_init__(self) -> None:
        if not 5.0 <= self.interval_seconds <= 3600.0:
            raise ValueError("runtime interval must be between 5 and 3600")
        if not 1.0 <= self.failure_backoff_seconds <= 300.0:
            raise ValueError("failure backoff must be between 1 and 300")
        if not self.failure_backoff_seconds <= self.max_failure_backoff_seconds <= 3600:
            raise ValueError("maximum failure backoff is invalid")

    def run(self, *, max_cycles: int | None = None) -> int:
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        attempts = 0
        completed = 0
        consecutive_failures = 0
        while max_cycles is None or attempts < max_cycles:
            attempts += 1
            try:
                report = self.cycle()
                self.store.save(report)
                if self.private_store is not None:
                    self.private_store.save(report)
                if self.management_ledger is not None:
                    self.management_ledger.append(report)
            except Exception as error:
                consecutive_failures += 1
                self.store.save_failure(error, self.clock())
                if self.management_ledger is not None:
                    self.management_ledger.append_failure(error, self.clock())
            else:
                completed += 1
                consecutive_failures = 0
            if max_cycles is not None and attempts >= max_cycles:
                continue
            delay = self.interval_seconds
            if consecutive_failures:
                delay = min(
                    self.failure_backoff_seconds * (2 ** (consecutive_failures - 1)),
                    self.max_failure_backoff_seconds,
                )
            self.sleeper(delay)
        return completed

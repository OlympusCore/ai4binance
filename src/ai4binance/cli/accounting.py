"""Accounting command handlers for the safe CLI dispatcher."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.accounting import (
    AccountingFileReconciler,
    AccountingRestCollector,
    AccountingUiReportBuilder,
    AccountingUserStreamCollectorService,
    BinanceAccountingRestSource,
    BinanceAccountLedger,
    BinanceUsdMListenKeyManager,
    FuturesUsdMUserDataStreamSession,
    HmacSpotUserDataStreamSession,
)
from ai4binance.config import Settings
from ai4binance.exchange import (
    BinancePrivateAccountReader,
    BinanceUsdMPrivateAccountReader,
    PrivateCredentials,
    SignedReadOnlyRequestFactory,
    SignedUsdMReadOnlyRequestFactory,
    UrllibPrivateJsonTransport,
)
from ai4binance.ops import SingleInstanceLease
from ai4binance.reporting import to_primitive
from ai4binance.storage import read_bounded_jsonl_tail


def run_accounting_command(
    command: str,
    settings: Settings,
    *,
    max_cycles: int | None,
) -> int:
    if command == "accounting-collect-once":
        payload, exit_code = accounting_collect_once(settings)
    elif command == "accounting-ws-once":
        payload, exit_code = accounting_ws_once(settings)
    elif command == "accounting-reconcile-once":
        payload, exit_code = accounting_reconcile_once(settings)
    elif command == "accounting-ui-report":
        payload = accounting_ui_report(settings)
        exit_code = 0 if payload["status"] == "CLEAN" else 2
    elif command == "accounting-status":
        payload = accounting_status_payload(settings, datetime.now(UTC))
        exit_code = 0 if payload["status"] == "CLEAN" else 2
    elif command == "accounting-collect-daemon":
        return _run_locked_accounting_daemon(
            "accounting",
            settings,
            lambda: accounting_collect_daemon(settings, max_cycles=max_cycles),
        )
    elif command == "accounting-ws-daemon":
        return _run_locked_accounting_daemon(
            "accounting-ws",
            settings,
            lambda: accounting_ws_daemon(settings, max_cycles=max_cycles),
        )
    else:
        raise ValueError(f"unsupported accounting command: {command}")
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return exit_code


def _run_locked_accounting_daemon(
    service: str,
    settings: Settings,
    runner: Callable[[], int],
) -> int:
    lock_path = settings.runtime_state_path.with_name(f"{service}.lock")
    try:
        with SingleInstanceLease(lock_path):
            return runner()
    except RuntimeError as error:
        blocker = (
            "ACCOUNTING_DAEMON_ALREADY_ACTIVE"
            if "already active" in str(error)
            else "ACCOUNTING_DAEMON_LOCK_REVIEW_REQUIRED"
        )
        print(
            json.dumps(
                {
                    "command": f"{service}-daemon",
                    "status": "BLOCKED",
                    "service": service,
                    "blockers": (blocker,),
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


def accounting_collect_once(settings: Settings) -> tuple[dict[str, object], int]:
    now = datetime.now(UTC)
    sync_run_id = f"accounting-{settings.symbol}-{int(now.timestamp() * 1000)}"
    try:
        credentials = PrivateCredentials.from_environment_or_file(
            settings.private_credentials_file
        )
    except ValueError:
        return (
            {
                "command": "accounting-collect-once",
                "status": "BLOCKED",
                "sync_run_id": sync_run_id,
                "blockers": ("BINANCE_READ_ONLY_CREDENTIALS_UNAVAILABLE",),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            2,
        )
    transport = UrllibPrivateJsonTransport(
        timeout_seconds=settings.request_timeout_seconds,
        max_attempts=settings.request_max_attempts,
        backoff_seconds=settings.request_backoff_seconds,
    )
    source = BinanceAccountingRestSource(
        spot_reader=BinancePrivateAccountReader(
            SignedReadOnlyRequestFactory(credentials), transport
        ),
        futures_reader=BinanceUsdMPrivateAccountReader(
            SignedUsdMReadOnlyRequestFactory(credentials), transport
        ),
        symbol=settings.symbol,
        limit=settings.accounting_collection_limit,
    )
    ledger = BinanceAccountLedger(settings.binance_accounting_directory)
    result = AccountingRestCollector(ledger).ingest_snapshot(
        source,
        snapshot_id=sync_run_id,
        sync_run_id=sync_run_id,
        received_at=now,
    )
    reconciliation = AccountingFileReconciler(
        ledger,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).reconcile_latest(
        snapshot_id=sync_run_id,
        sync_run_id=sync_run_id,
        observed_at=datetime.now(UTC),
    )
    ui_report = AccountingUiReportBuilder(
        settings.binance_accounting_directory,
        settings.accounting_report_directory,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).write(datetime.now(UTC))
    status = (
        "COLLECTED"
        if not result.blockers
        and result.rejected_count == 0
        and not reconciliation.blockers
        else "DEGRADED"
    )
    return (
        {
            "command": "accounting-collect-once",
            "status": status,
            "result": result,
            "reconciliation": reconciliation,
            "ui_report_path": ui_report["html_path"],
            "accounting_directory": str(settings.binance_accounting_directory),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        0 if status == "COLLECTED" else 2,
    )


def accounting_collect_daemon(
    settings: Settings,
    *,
    max_cycles: int | None,
) -> int:
    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    completed = 0
    attempts = 0
    while max_cycles is None or attempts < max_cycles:
        attempts += 1
        payload, _exit_code = accounting_collect_once(settings)
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        sys.stdout.flush()
        completed += 1
        if max_cycles is not None and attempts >= max_cycles:
            break
        time.sleep(settings.runtime_cycle_interval_seconds)
    return 0 if completed else 2


def accounting_ws_once(settings: Settings) -> tuple[dict[str, object], int]:
    now = datetime.now(UTC)
    sync_run_id = f"accounting-ws-{settings.symbol}-{int(now.timestamp() * 1000)}"
    try:
        credentials = PrivateCredentials.from_environment_or_file(
            settings.private_credentials_file
        )
    except ValueError:
        return (
            {
                "command": "accounting-ws-once",
                "status": "BLOCKED",
                "sync_run_id": sync_run_id,
                "blockers": ("BINANCE_READ_ONLY_CREDENTIALS_UNAVAILABLE",),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            2,
        )
    ledger = BinanceAccountLedger(settings.binance_accounting_directory)
    service = AccountingUserStreamCollectorService(
        ledger=ledger,
        sessions=(
            HmacSpotUserDataStreamSession(
                credentials,
                url=settings.spot_ws_api_url,
            ),
            FuturesUsdMUserDataStreamSession(
                BinanceUsdMListenKeyManager(credentials),
                base_url=settings.futures_private_ws_url,
            ),
        ),
        event_limit=settings.accounting_ws_event_limit,
        collect_seconds=settings.accounting_ws_collect_seconds,
        receive_timeout_seconds=settings.accounting_ws_receive_timeout_seconds,
    )
    result = service.collect_once(sync_run_id=sync_run_id)
    reconciliation = AccountingFileReconciler(
        ledger,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).reconcile_latest(
        snapshot_id=sync_run_id,
        sync_run_id=sync_run_id,
        observed_at=datetime.now(UTC),
    )
    ui_report = AccountingUiReportBuilder(
        settings.binance_accounting_directory,
        settings.accounting_report_directory,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).write(datetime.now(UTC))
    status = (
        "COLLECTED"
        if result.status == "COLLECTED" and not reconciliation.blockers
        else "DEGRADED"
    )
    return (
        {
            "command": "accounting-ws-once",
            "status": status,
            "sync_run_id": sync_run_id,
            "result": result,
            "reconciliation": reconciliation,
            "ui_report_path": ui_report["html_path"],
            "accounting_directory": str(settings.binance_accounting_directory),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        0 if status == "COLLECTED" else 2,
    )


def accounting_ws_daemon(
    settings: Settings,
    *,
    max_cycles: int | None,
) -> int:
    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    completed = 0
    attempts = 0
    while max_cycles is None or attempts < max_cycles:
        attempts += 1
        payload, _exit_code = accounting_ws_once(settings)
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        sys.stdout.flush()
        completed += 1
        if max_cycles is not None and attempts >= max_cycles:
            break
        time.sleep(settings.runtime_cycle_interval_seconds)
    return 0 if completed else 2


def accounting_reconcile_once(settings: Settings) -> tuple[dict[str, object], int]:
    now = datetime.now(UTC)
    sync_run_id = (
        f"accounting-reconcile-{settings.symbol}-{int(now.timestamp() * 1000)}"
    )
    ledger = BinanceAccountLedger(settings.binance_accounting_directory)
    reconciliation = AccountingFileReconciler(
        ledger,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).reconcile_latest(
        snapshot_id=sync_run_id,
        sync_run_id=sync_run_id,
        observed_at=now,
    )
    ui_report = AccountingUiReportBuilder(
        settings.binance_accounting_directory,
        settings.accounting_report_directory,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).write(datetime.now(UTC))
    payload = {
        "command": "accounting-reconcile-once",
        "status": reconciliation.status,
        "sync_run_id": sync_run_id,
        "reconciliation": reconciliation,
        "ui_report_path": ui_report["html_path"],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    return payload, 0 if reconciliation.status == "CLEAN" else 2


def accounting_ui_report(settings: Settings) -> dict[str, object]:
    return AccountingUiReportBuilder(
        settings.binance_accounting_directory,
        settings.accounting_report_directory,
        freshness_seconds=settings.accounting_freshness_minutes * 60,
    ).write(datetime.now(UTC))


def accounting_status_payload(
    settings: Settings,
    observed_at: datetime,
) -> dict[str, object]:
    required = (
        "shared/raw_api_events.jsonl",
        "shared/reconciliation_results.jsonl",
    )
    observed = (
        "spot/orders.jsonl",
        "spot/order_events.jsonl",
        "spot/trades.jsonl",
        "spot/capital_flows.jsonl",
        "futures_usdm/orders.jsonl",
        "futures_usdm/order_events.jsonl",
        "futures_usdm/trades.jsonl",
        "futures_usdm/positions_current.jsonl",
        "futures_usdm/position_events.jsonl",
        "futures_usdm/income_ledger.jsonl",
        "futures_usdm/configuration_snapshots.jsonl",
        *required,
    )
    root = settings.binance_accounting_directory
    freshness_seconds = settings.accounting_freshness_minutes * 60
    files = []
    blockers: list[str] = []
    for relative in observed:
        path = root / relative
        exists, age_seconds, file_blocker = _accounting_file_state(
            path,
            relative=relative,
            required=relative in required,
            observed_at=observed_at,
            freshness_seconds=freshness_seconds,
        )
        if file_blocker is not None:
            blockers.append(file_blocker)
        files.append(
            {
                "path": str(path),
                "required": relative in required,
                "exists": exists,
                "age_seconds": age_seconds,
            }
        )
    reconciliation_path = root / "shared" / "reconciliation_results.jsonl"
    reconciliation = latest_reconciliation_status(reconciliation_path)
    if reconciliation["status"] != "CLEAN":
        blockers.extend(cast(tuple[str, ...], reconciliation["blockers"]))
    return {
        "command": "accounting-status",
        "observed_at": observed_at,
        "status": "CLEAN" if not blockers else "DEGRADED",
        "accounting_directory": str(root),
        "files": tuple(files),
        "reconciliation": reconciliation,
        "blockers": tuple(dict.fromkeys(blockers)),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _accounting_file_state(
    path: Path,
    *,
    relative: str,
    required: bool,
    observed_at: datetime,
    freshness_seconds: int,
) -> tuple[bool, float | None, str | None]:
    try:
        exists = path.is_file()
        if not exists:
            blocker = f"ACCOUNTING_FILE_MISSING:{relative}" if required else None
            return False, None, blocker
        age_seconds = observed_at.timestamp() - path.stat().st_mtime
    except OSError:
        return False, None, f"ACCOUNTING_FILE_UNREADABLE:{relative}"
    if required and age_seconds > freshness_seconds:
        return True, age_seconds, f"ACCOUNTING_FILE_STALE:{relative}"
    return True, age_seconds, None


def latest_reconciliation_status(path: Path) -> dict[str, object]:
    try:
        exists = path.is_file()
    except OSError:
        exists = False
        unreadable = True
    else:
        unreadable = False
    if unreadable:
        return {
            "status": "BLOCKED",
            "latest_severity": None,
            "blockers": ("RECONCILIATION_RESULTS_UNREADABLE",),
        }
    if not exists:
        return {
            "status": "BLOCKED",
            "latest_severity": None,
            "blockers": ("RECONCILIATION_RESULTS_MISSING",),
        }
    malformed = False
    latest_severity: str | None = None
    latest_blockers: tuple[str, ...] = ()
    try:
        lines = read_bounded_jsonl_tail(path, max_lines=200)
    except OSError:
        return {
            "status": "BLOCKED",
            "latest_severity": None,
            "blockers": ("RECONCILIATION_RESULTS_UNREADABLE",),
        }
    for encoded_line in lines:
        try:
            line = encoded_line.decode("utf-8")
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed = True
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        if not isinstance(payload, dict):
            malformed = True
            continue
        if not _is_accounting_reconciliation_payload(payload):
            continue
        severity = payload.get("severity")
        if isinstance(severity, str):
            latest_severity = severity
            latest_blockers = (
                () if severity == "OK" else (f"RECONCILIATION_NOT_CLEAN:{severity}",)
            )
    blockers = latest_blockers or (
        ("RECONCILIATION_RESULT_MALFORMED",)
        if malformed and latest_severity is None
        else ()
    )
    return {
        "status": "CLEAN" if not blockers else "DEGRADED",
        "latest_severity": latest_severity,
        "blockers": tuple(dict.fromkeys(blockers)),
    }


def _is_accounting_reconciliation_payload(payload: dict[str, object]) -> bool:
    envelope = payload.get("envelope")
    if not isinstance(envelope, dict):
        return True
    endpoint = envelope.get("endpoint")
    return endpoint == "accounting:reconciliation"

"""Focused coverage for remaining lowest-audit fail-closed branches."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance import historical_replay_evaluation as historical_module
from ai4binance.accounting import ui_reports
from ai4binance.application import (
    ResearchApplicationService,
    ResearchStage,
    ResearchStageStatus,
)
from ai4binance.application import research as research_module
from ai4binance.application.runtime import (
    DualMarketAdvisoryReport,
    MarketAdvisory,
    RuntimeState,
)
from ai4binance.cli import accounting as accounting_cli
from ai4binance.config import Settings
from ai4binance.core.errors import ExchangeError
from ai4binance.exchange import PrivateCredentials
from ai4binance.historical_replay_evaluation import (
    HistoricalDgeCounterfactualOutcome,
    HistoricalMarketPerformanceEvaluation,
    HistoricalReplayMetric,
    HistoricalReplayPublication,
    HistoricalReplaySystemEvaluator,
)
from ai4binance.ops import runtime as runtime_ops
from ai4binance.ops import system_report as system_report_module
from ai4binance.ops.user_reports import UserReportPaths
from ai4binance.reporting import to_primitive
from ai4binance.research import VirtualMarket
from ai4binance.research_runtime import HistoricalReplayCycleResult
from ai4binance.storage.destination_verification import DestinationVerificationError
from tests.test_cli import public_snapshot
from tests.test_historical_replay_evaluation import (
    _counterfactuals,
    _dual_dge_blocked_result,
    _dual_no_trade_result,
)
from tests.test_historical_replay_runner import (
    HASH_1,
    START,
    _NoCandidateOrchestrator,
    _request,
    _runner,
    _snapshot,
)
from tests.test_research_application import (
    _RuntimeReadyOrchestrator,
    _RuntimeReadyOutlook,
)

NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)


def test_accounting_ui_report_parses_malformed_and_stale_edges(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ui_reports.AccountingUiReportBuilder(tmp_path, tmp_path / "ui", 60).build(
            datetime(2026, 9, 16, 9, 0)
        )

    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n"
        "{bad-json}\n"
        + json.dumps({"payload": {"envelope": "invalid"}})
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-09-16T08:59:00Z",
                "payload": {
                    "received_at": "2026-09-16T08:59:30Z",
                    "envelope": {
                        "product_type": "OPTIONS",
                        "source_type": "REST",
                    },
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-09-16T08:58:00Z",
                "payload": {
                    "event_type": "BALANCE",
                    "received_at": "2026-09-16T08:58:30Z",
                    "envelope": {
                        "product_type": "SPOT",
                        "source_type": "REST",
                        "endpoint": "/api/v3/account",
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert ui_reports._read_events(tmp_path / "missing.jsonl", limit=10) == ()
    events = ui_reports._read_events(events_path, limit=10)
    channels = ui_reports._channel_summary(
        events,
        observed_at=NOW,
        freshness_seconds=10,
    )

    assert len(events) == 3
    assert channels[0]["status"] == "STALE"
    assert channels[0]["endpoints"] == ({"endpoint": "/api/v3/account", "count": 1},)
    assert ui_reports._render_blockers(()) == '<p class="muted">No active blockers.</p>'
    assert "RECONCILIATION_NOT_CLEAN" in ui_reports._render_blockers(
        ("RECONCILIATION_NOT_CLEAN:BLOCKED:wallet",)
    )
    assert ui_reports._render_activity(()) == '<p class="muted">No activity yet.</p>'
    assert ui_reports._render_endpoint_list(()) == (
        '<span class="muted">no records</span>'
    )
    assert ui_reports._parse_time("not-a-time") is None
    assert ui_reports._parse_time("2026-09-16T09:00:00") is None
    assert ui_reports._age(59) == "59s"
    assert ui_reports._age(120) == "2.0min"


def test_accounting_cli_daemons_status_and_reconciliation_edges(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_RUNTIME_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(tmp_path))
    settings = Settings()

    with pytest.raises(ValueError, match="unsupported accounting command"):
        accounting_cli.run_accounting_command("unknown", settings, max_cycles=1)
    with pytest.raises(ValueError, match="max_cycles"):
        accounting_cli.accounting_collect_daemon(settings, max_cycles=0)
    with pytest.raises(ValueError, match="max_cycles"):
        accounting_cli.accounting_ws_daemon(settings, max_cycles=0)

    def _raise_locked(path: Path) -> None:
        del path
        raise RuntimeError("manual review required")

    monkeypatch.setattr(accounting_cli, "SingleInstanceLease", _raise_locked)
    assert (
        accounting_cli._run_locked_accounting_daemon(
            "accounting",
            settings,
            lambda: 0,
        )
        == 2
    )
    locked_payload = json.loads(capsys.readouterr().out)
    assert locked_payload["blockers"] == ["ACCOUNTING_DAEMON_LOCK_REVIEW_REQUIRED"]

    calls = {"count": 0}

    def _failing_collect(settings: Settings) -> tuple[dict[str, object], int]:
        del settings
        calls["count"] += 1
        raise ExchangeError("provider unavailable")

    monkeypatch.setattr(accounting_cli, "accounting_collect_once", _failing_collect)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    assert accounting_cli.accounting_collect_daemon(settings, max_cycles=3) == 2
    daemon_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert daemon_lines[-1]["status"] == "CIRCUIT_OPEN"
    assert daemon_lines[-1]["blockers"] == ["ACCOUNTING_PROVIDER_CIRCUIT_OPEN"]
    assert calls["count"] == 3

    monkeypatch.setattr(
        accounting_cli,
        "accounting_ws_once",
        lambda settings: ({"status": "COLLECTED"}, 0),
    )
    assert accounting_cli.accounting_ws_daemon(settings, max_cycles=1) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COLLECTED"

    class _UnreadablePath:
        def is_file(self) -> bool:
            raise OSError("blocked")

    assert (
        accounting_cli.latest_reconciliation_status(cast(Path, _UnreadablePath()))[
            "status"
        ]
        == "BLOCKED"
    )

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_bytes(b"\xff\n{}\n")
    assert accounting_cli.latest_reconciliation_status(malformed)["blockers"] == (
        "RECONCILIATION_RESULT_MALFORMED",
    )


def test_accounting_cli_collectors_are_wired_to_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_RUNTIME_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(tmp_path))
    settings = Settings()

    monkeypatch.setattr(
        PrivateCredentials,
        "from_environment_or_file",
        staticmethod(lambda path: object()),
    )
    for name in (
        "UrllibPrivateJsonTransport",
        "SignedReadOnlyRequestFactory",
        "SignedUsdMReadOnlyRequestFactory",
        "BinancePrivateAccountReader",
        "BinanceUsdMPrivateAccountReader",
        "BinanceAccountingRestSource",
        "BinanceAccountLedger",
        "HmacSpotUserDataStreamSession",
        "BinanceUsdMListenKeyManager",
        "FuturesUsdMUserDataStreamSession",
    ):
        monkeypatch.setattr(accounting_cli, name, lambda *args, **kwargs: object())

    class _RestCollector:
        def __init__(self, ledger: object) -> None:
            del ledger

        def ingest_snapshot(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(blockers=(), rejected_count=0)

    class _Reconciler:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def reconcile_latest(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(blockers=(), status="CLEAN")

    class _UiReport:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def write(self, observed_at: datetime) -> dict[str, object]:
            return {
                "status": "CLEAN",
                "html_path": str(tmp_path / f"{observed_at.timestamp()}.html"),
            }

    class _WsCollector:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def collect_once(self, *, sync_run_id: str) -> object:
            assert sync_run_id.startswith("accounting-ws-")
            return SimpleNamespace(status="COLLECTED")

    monkeypatch.setattr(accounting_cli, "AccountingRestCollector", _RestCollector)
    monkeypatch.setattr(accounting_cli, "AccountingFileReconciler", _Reconciler)
    monkeypatch.setattr(accounting_cli, "AccountingUiReportBuilder", _UiReport)
    monkeypatch.setattr(
        accounting_cli,
        "AccountingUserStreamCollectorService",
        _WsCollector,
    )

    payload, exit_code = accounting_cli.accounting_collect_once(settings)
    assert exit_code == 0
    assert payload["status"] == "COLLECTED"
    payload, exit_code = accounting_cli.accounting_ws_once(settings)
    assert exit_code == 0
    assert payload["status"] == "COLLECTED"
    payload, exit_code = accounting_cli.accounting_reconcile_once(settings)
    assert exit_code == 0
    assert payload["status"] == "CLEAN"

    monkeypatch.setattr(
        accounting_cli,
        "accounting_ui_report",
        lambda settings: {"status": "CLEAN"},
    )
    assert (
        accounting_cli.run_accounting_command(
            "accounting-ui-report",
            settings,
            max_cycles=1,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "CLEAN"

    class _Lease:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> "_Lease":
            return self

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setattr(accounting_cli, "SingleInstanceLease", _Lease)
    assert (
        accounting_cli._run_locked_accounting_daemon(
            "accounting",
            settings,
            lambda: 0,
        )
        == 0
    )

    monkeypatch.setattr(
        accounting_cli,
        "accounting_ws_once",
        lambda settings: ({"status": "COLLECTED"}, 0),
    )
    monkeypatch.setattr(
        accounting_cli,
        "accounting_reconcile_once",
        lambda settings: ({"status": "CLEAN"}, 0),
    )
    assert (
        accounting_cli.run_accounting_command(
            "accounting-ws-once",
            settings,
            max_cycles=1,
        )
        == 0
    )
    assert (
        accounting_cli.run_accounting_command(
            "accounting-reconcile-once",
            settings,
            max_cycles=1,
        )
        == 0
    )
    assert (
        accounting_cli.run_accounting_command(
            "accounting-ws-daemon",
            settings,
            max_cycles=1,
        )
        == 0
    )
    capsys.readouterr()


def test_accounting_cli_success_daemons_and_status_edges(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI4BINANCE_RUNTIME_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(tmp_path))
    settings = Settings()

    monkeypatch.setattr(
        accounting_cli,
        "accounting_collect_once",
        lambda settings: ({"status": "COLLECTED"}, 0),
    )
    monkeypatch.setattr(
        accounting_cli,
        "accounting_ws_once",
        lambda settings: ({"status": "COLLECTED"}, 0),
    )
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    assert accounting_cli.accounting_collect_daemon(settings, max_cycles=2) == 0
    assert accounting_cli.accounting_ws_daemon(settings, max_cycles=2) == 0
    assert slept == [settings.runtime_cycle_interval_seconds] * 2
    capsys.readouterr()

    class _UiReport:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def write(self, observed_at: datetime) -> dict[str, object]:
            return {"status": "CLEAN", "html_path": str(observed_at.timestamp())}

    monkeypatch.setattr(accounting_cli, "AccountingUiReportBuilder", _UiReport)
    assert accounting_cli.accounting_ui_report(settings)["status"] == "CLEAN"

    stale = tmp_path / "stale.jsonl"
    stale.write_text("x\n", encoding="utf-8")
    os.utime(stale, (NOW.timestamp() - 10_000, NOW.timestamp() - 10_000))
    assert (
        accounting_cli._accounting_file_state(
            stale,
            relative="shared/raw_api_events.jsonl",
            required=True,
            observed_at=NOW,
            freshness_seconds=60,
        )[2]
        == "ACCOUNTING_FILE_STALE:shared/raw_api_events.jsonl"
    )

    missing_status = accounting_cli.accounting_status_payload(settings, NOW)
    assert missing_status["status"] == "DEGRADED"

    reconciliation = tmp_path / "shared" / "reconciliation_results.jsonl"
    reconciliation.parent.mkdir(parents=True)
    reconciliation.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        accounting_cli,
        "read_bounded_jsonl_tail",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("blocked")),
    )
    assert accounting_cli.latest_reconciliation_status(reconciliation)["blockers"] == (
        "RECONCILIATION_RESULTS_UNREADABLE",
    )
    monkeypatch.setattr(
        accounting_cli,
        "read_bounded_jsonl_tail",
        lambda *args, **kwargs: (
            json.dumps({"payload": {"envelope": {"endpoint": "other"}}}).encode(),
        ),
    )
    assert (
        accounting_cli.latest_reconciliation_status(reconciliation)["status"] == "CLEAN"
    )
    assert (
        accounting_cli._is_accounting_reconciliation_payload(
            {"envelope": {"endpoint": "other"}}
        )
        is False
    )


def test_runtime_status_stores_and_lease_fail_closed_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        runtime_ops._replace_file_with_retry(
            tmp_path / "tmp",
            tmp_path / "target",
            attempts=0,
        )

    class _TemporaryPath:
        def __init__(self) -> None:
            self.calls = 0

        def replace(self, target: Path) -> None:
            del target
            self.calls += 1
            raise PermissionError("locked")

    temporary = _TemporaryPath()
    with pytest.raises(PermissionError):
        runtime_ops._replace_file_with_retry(
            cast(Path, temporary),
            tmp_path / "target",
            attempts=1,
        )
    assert temporary.calls == 1

    store = runtime_ops.RuntimeStatusStore(tmp_path / "runtime.json")
    with pytest.raises(ValueError, match="timezone-aware"):
        store.save_failure(RuntimeError("x"), datetime(2026, 9, 16, 9, 0))
    (tmp_path / "runtime.json").write_text(
        json.dumps({"health": {"consecutive_failures": True}}),
        encoding="utf-8",
    )
    store.save_failure(RuntimeError("cycle"), NOW)
    payload = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
    assert payload["health"]["consecutive_failures"] == 1

    (tmp_path / "runtime.json").write_text("{bad-json}", encoding="utf-8")
    with pytest.raises(
        DestinationVerificationError,
        match="RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
    ):
        store._verify_payload({})

    private = runtime_ops.PrivateRuntimeStatusStore(tmp_path / "private.json")
    assert private._read_previous_payload() is None
    assert private._reconcile({"open_order_snapshot_version": 1}, ())["status"] == (
        "NOT_AVAILABLE"
    )
    assert (
        private._reconcile(
            {"open_order_snapshot_version": 1, "open_orders": [object()]},
            (),
        )["status"]
        == "NOT_AVAILABLE"
    )

    lock = runtime_ops.SingleInstanceLease(tmp_path / "runtime.lock")
    lock.path.write_text(json.dumps({"schema_version": 2, "pid": 1}), encoding="ascii")
    with pytest.raises(RuntimeError, match="invalid"):
        lock._read_lock_owner(lock.path)
    lock.path.write_text(
        json.dumps({"schema_version": 1, "pid": True}),
        encoding="ascii",
    )
    with pytest.raises(RuntimeError, match="invalid"):
        lock._read_lock_owner(lock.path)
    marker = runtime_ops.SingleInstanceLease._process_marker(os.getpid())
    assert marker is None or marker.startswith("windows-filetime:")
    assert runtime_ops.SingleInstanceLease._pid_is_alive(0) is False


def test_runtime_stores_ledgers_and_supervisor_edges(tmp_path: Path) -> None:
    report = _report()
    store = runtime_ops.RuntimeStatusStore(tmp_path / "runtime.json")
    store.save(report)
    payload = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
    assert payload["controlled_learning"]["status"] == "NOT_RUN"

    private = runtime_ops.PrivateRuntimeStatusStore(
        tmp_path / "private.json",
        ledger_path=tmp_path / "private-ledger.jsonl",
    )
    private.save(report)
    assert (tmp_path / "private.json").is_file()
    assert (tmp_path / "private-ledger.jsonl").is_file()

    management = runtime_ops.RuntimeManagementLedger(tmp_path / "management.jsonl")
    management.append(report)
    management.append_failure(RuntimeError("cycle"), NOW)
    assert "WALLET_MANAGEMENT_REVIEW_FAILED" in (
        tmp_path / "management.jsonl"
    ).read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="runtime interval"):
        runtime_ops.RuntimeSupervisor(lambda: report, store, interval_seconds=1)
    with pytest.raises(ValueError, match="failure backoff"):
        runtime_ops.RuntimeSupervisor(lambda: report, store, failure_backoff_seconds=0)
    with pytest.raises(ValueError, match="maximum failure backoff"):
        runtime_ops.RuntimeSupervisor(
            lambda: report,
            store,
            failure_backoff_seconds=10,
            max_failure_backoff_seconds=5,
        )

    failures = {"count": 0}

    def _cycle() -> DualMarketAdvisoryReport:
        failures["count"] += 1
        if failures["count"] == 1:
            raise RuntimeError("first cycle fails")
        return report

    slept: list[float] = []
    supervisor = runtime_ops.RuntimeSupervisor(
        _cycle,
        store,
        private_store=private,
        management_ledger=management,
        sleeper=slept.append,
        clock=lambda: NOW,
    )
    assert supervisor.run(max_cycles=2) == 1
    assert slept == [5.0]


def test_runtime_private_verify_pid_and_learning_edges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private = runtime_ops.PrivateRuntimeStatusStore(tmp_path / "private.json")
    private.path.write_text("{bad-json}", encoding="utf-8")
    with pytest.raises(
        DestinationVerificationError,
        match="PRIVATE_RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
    ):
        private._verify_payload({})
    private.path.write_text(json.dumps({"different": True}), encoding="utf-8")
    with pytest.raises(
        DestinationVerificationError,
        match="PRIVATE_RUNTIME_STATE_DESTINATION_VERIFY_FAILED",
    ):
        private._verify_payload({})

    lock_path = tmp_path / "runtime.lock"
    lock_path.write_text(
        json.dumps({"schema_version": 1, "pid": 1, "process_marker": ""}),
        encoding="ascii",
    )
    with pytest.raises(RuntimeError, match="invalid"):
        runtime_ops.SingleInstanceLease._read_lock_owner(lock_path)

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "kill", lambda pid, signal: None)
    assert runtime_ops.SingleInstanceLease._process_marker(os.getpid()) is None
    assert runtime_ops.SingleInstanceLease._pid_is_alive(os.getpid()) is True
    monkeypatch.setattr(
        os,
        "kill",
        lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError),
    )
    assert runtime_ops.SingleInstanceLease._pid_is_alive(os.getpid()) is False
    monkeypatch.setattr(
        os,
        "kill",
        lambda pid, signal: (_ for _ in ()).throw(PermissionError),
    )
    assert runtime_ops.SingleInstanceLease._pid_is_alive(os.getpid()) is True

    learning_report = replace(
        _report(),
        spot_research=SimpleNamespace(
            learning=SimpleNamespace(
                saved=True,
                summary=SimpleNamespace(
                    summary_id="summary-1",
                    lessons=("lesson",),
                    experiments=("experiment",),
                    execution_allowed=False,
                    risk_change_allowed=False,
                    promotion_status="RESEARCH_ONLY",
                ),
            )
        ),
    )
    payload = runtime_ops._controlled_learning_payload(learning_report)
    assert payload["status"] == "READY"
    assert payload["summary_id"] == "summary-1"


def test_system_report_helpers_cover_invalid_components_and_payloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        system_report_module.build_system_report(
            _settings(monkeypatch, tmp_path),
            observed_at=datetime(2026, 9, 16, 9, 0),
            workspace_root=tmp_path,
        )

    runtime_state = tmp_path / "runtime.json"
    runtime_state.write_text(
        json.dumps(
            {
                "created_at": "not-a-time",
                "state": "READY",
                "health": {"status": "READY"},
                "controlled_learning": "invalid",
                "blockers": "RUNTIME_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    settings = _settings(monkeypatch, tmp_path)
    object.__setattr__(settings, "runtime_state_path", runtime_state)
    runtime_payload = system_report_module.runtime_state_payload(settings, NOW)
    runtime_blockers = cast(tuple[str, ...], runtime_payload["blockers"])
    assert "RUNTIME_REPORT_TIMESTAMP_INVALID" in runtime_blockers

    advisory_state = tmp_path / "qwen-prompter-health.json"
    object.__setattr__(settings, "runtime_state_path", advisory_state)
    advisory_state.write_text(
        json.dumps(
            {
                "provider": "other",
                "status": "STOPPED",
                "endpoint": "http://remote.invalid",
                "listener_pids": ["bad"],
                "auto_learn": {"engine": "invalid"},
            }
        ),
        encoding="utf-8",
    )
    health = system_report_module.local_advisory_health_payload(settings)
    assert health["status"] == "DEGRADED"
    health_blockers = cast(tuple[str, ...], health["blockers"])
    assert "QWEN_PROMPTER_LISTENER_MISSING" in health_blockers

    invalid = system_report_module._safe_component("demo", lambda: "not-dict")
    failed = system_report_module._safe_component(
        "demo",
        lambda: (_ for _ in ()).throw(ValueError("bad")),
    )
    assert invalid["blockers"] == ("DEMO_PAYLOAD_INVALID",)
    assert failed["blockers"] == ("DEMO_UNAVAILABLE",)
    assert system_report_module._component_payload({"ok": True}) == {"ok": True}
    with pytest.raises(ValueError, match="dictionary"):
        system_report_module._component_payload(("not", "dict"))
    assert system_report_module._advanced_contract_snapshot("missing")["status"] == (
        "DEGRADED"
    )
    assert system_report_module._blocker_tuple("one") == ("one",)
    assert system_report_module._blocker_tuple(42) == ()
    assert system_report_module._parse_datetime("not-a-date") is None
    assert system_report_module._parse_datetime("2026-09-16T09:00:00") == NOW
    assert system_report_module._safe_int(True) is None
    assert system_report_module._safe_int("bad") is None
    assert system_report_module._as_sequence(None) == ()
    assert system_report_module._as_sequence("x") == ("x",)

    markdown = system_report_module._render_markdown(
        {
            "observed_at": NOW.isoformat(),
            "status": "READY",
            "telemetry_assessment": {"blockers": ()},
            "components": {
                "string_blocker": {"status": "READY", "blockers": "BLOCKER"},
                "invalid_blockers": {"state": "UNKNOWN", "blockers": 7},
            },
            "advanced_agent_operating_contract": {
                "status": "READY",
                "human_approval_controls": "invalid",
            },
            "blockers": (),
        },
        json_path=tmp_path / "report.json",
    )
    assert "string_blocker" in markdown
    assert "BLOCKER" in markdown


def test_research_application_static_edges_and_fail_closed_inputs() -> None:
    with pytest.raises(ValueError, match="research stage name"):
        ResearchStage("", ResearchStageStatus.COMPLETED)
    with pytest.raises(ValueError, match="wallet capture"):
        ResearchApplicationService(
            orchestrator=object(),
            outlook_engine=object(),
            primitive_converter=lambda value: value,
            wallet_capture_enabled=True,
        )
    with pytest.raises(ValueError, match="market context providers"):
        ResearchApplicationService(
            orchestrator=object(),
            outlook_engine=object(),
            primitive_converter=lambda value: value,
            market_context_provider_ids=("web",),
        )
    with pytest.raises(ValueError, match="observer"):
        ResearchApplicationService(
            orchestrator=object(),
            outlook_engine=object(),
            primitive_converter=lambda value: value,
            observer=object(),
        )
    with pytest.raises(ValueError, match="request builder"):
        ResearchApplicationService(
            orchestrator=object(),
            outlook_engine=object(),
            primitive_converter=lambda value: value,
            market_context_registry=object(),
        )
    with pytest.raises(ValueError, match="audit persistence"):
        ResearchApplicationService(
            orchestrator=object(),
            outlook_engine=object(),
            primitive_converter=lambda value: value,
            audit_store=object(),
        )

    snapshot = public_snapshot()
    candidate = SimpleNamespace(
        candidate_id="c1",
        timeframe="1h",
        market_type="USD_M_FUTURES",
        action=SimpleNamespace(value="BUY"),
    )
    assert (
        ResearchApplicationService._candidate_candle_volume(
            replace(snapshot, ohlcv_by_timeframe=cast(Any, "invalid")),
            candidate,
        )
        is None
    )
    assert (
        ResearchApplicationService._candidate_candle_volume(
            replace(snapshot, ohlcv_by_timeframe={"1h": ()}),
            candidate,
        )
        is None
    )
    assert ResearchApplicationService._virtual_execution_inputs(
        replace(snapshot, market_metadata={"historical_virtual_execution": "invalid"}),
        candidate=candidate,
        market="USD_M_FUTURES",
    ) == ({}, ("VIRTUAL_EXECUTION_CONTEXT_INVALID",))
    assert ResearchApplicationService._virtual_execution_inputs(
        replace(
            snapshot,
            market_metadata={
                "historical_virtual_execution": {
                    "context_kind": "wrong",
                    "market": "USD_M_FUTURES",
                    "symbol": snapshot.symbol,
                    "observed_at": snapshot.created_at.isoformat().replace(
                        "+00:00",
                        "Z",
                    ),
                }
            },
        ),
        candidate=candidate,
        market="USD_M_FUTURES",
    ) == ({}, ("VIRTUAL_EXECUTION_CONTEXT_IDENTITY_MISMATCH",))
    assert (
        ResearchApplicationService._bounded_decimal(
            "NaN",
            minimum=Decimal("0"),
        )
        is None
    )
    assert (
        ResearchApplicationService._bounded_decimal(
            "-1",
            minimum=Decimal("0"),
        )
        is None
    )
    assert (
        ResearchApplicationService._bounded_decimal(
            "2",
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        is None
    )
    assert ResearchApplicationService._merge_virtual_learning_artifacts(
        {"performance_snapshots": ()},
        virtual_runtime_decision=None,
    ) == {"performance_snapshots": ()}
    with pytest.raises(ValueError, match="performance_snapshots"):
        ResearchApplicationService._merge_virtual_learning_artifacts(
            {"performance_snapshots": []},
            virtual_runtime_decision=SimpleNamespace(
                halt_review=SimpleNamespace(
                    improvement_candidates=("candidate",),
                    root_cause_tags=("risk",),
                )
            ),
        )
    assert ResearchApplicationService._futures_inputs_without_context(
        replace(snapshot, derivatives_snapshot=cast(Any, "invalid")),
        candidate=candidate,
        market="USD_M_FUTURES",
    ) == ({}, ("FUTURES_EXECUTION_CONTEXT_INVALID",))
    assert ResearchApplicationService._futures_inputs(
        {"mark_price": "100", "funding_rate": "0", "isolated_margin_usdt": "10"},
        candidate=SimpleNamespace(action=SimpleNamespace(value="HOLD")),
    ) == ({}, ("FUTURES_EXECUTION_CONTEXT_INVALID",))
    assert ResearchApplicationService._risk_blockers(
        SimpleNamespace(agent_results={})
    ) == ("RISK_NOT_EVALUATED",)
    assert ResearchApplicationService._risk_blockers(
        SimpleNamespace(
            agent_results={
                "risk": SimpleNamespace(
                    status=SimpleNamespace(value="BLOCKED"),
                    blockers=("RISK_BLOCKED",),
                )
            }
        )
    ) == ("RISK_BLOCKED",)
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(agent_results={"risk": SimpleNamespace(agent_name="other")})
        )
        is None
    )
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(agent_results={"risk": SimpleNamespace(agent_name="risk")})
        )
        is None
    )
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(
                agent_results={
                    "risk": SimpleNamespace(
                        agent_name="risk",
                        calculation_metadata="invalid",
                    )
                }
            )
        )
        is None
    )
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(
                agent_results={
                    "risk": SimpleNamespace(
                        agent_name="risk",
                        calculation_metadata={"candidate_id": " "},
                    )
                }
            )
        )
        is None
    )
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(
                agent_results={
                    "risk": SimpleNamespace(
                        agent_name="risk",
                        calculation_metadata={"candidate_id": "c1"},
                    )
                }
            )
        )
        is None
    )
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(
                agent_results={
                    "risk": SimpleNamespace(
                        agent_name="risk",
                        blockers=[],
                        calculation_metadata={
                            "candidate_id": "c1",
                            "size_usdt": "1",
                            "quantity": "1",
                            "risk_amount_usdt": "1",
                        },
                    )
                }
            )
        )
        is None
    )
    assert (
        ResearchApplicationService._risk_assessment(
            SimpleNamespace(
                agent_results={
                    "risk": SimpleNamespace(
                        agent_name="risk",
                        blockers=(),
                        calculation_metadata={
                            "candidate_id": "c1",
                            "size_usdt": "1",
                            "quantity": "bad",
                            "risk_amount_usdt": "1",
                        },
                    )
                }
            )
        )
        is None
    )
    fallback = ResearchApplicationService._candidate_for_virtual_runtime(
        (SimpleNamespace(candidate_id="fallback", market_type="OPTIONS"),),
        "missing",
    )
    assert fallback is not None
    assert fallback.candidate_id == "fallback"
    with pytest.raises(ValueError, match="SPOT or USD_M_FUTURES"):
        ResearchApplicationService._default_virtual_portfolio_builder(
            snapshot,
            SimpleNamespace(market_type="OPTIONS"),
        )
    assert ResearchApplicationService._attach_market_context(snapshot, None) is snapshot
    retrieved_at = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)
    batch = SimpleNamespace(
        events=(SimpleNamespace(retrieved_at=retrieved_at),),
        as_news_snapshot=lambda: {
            "high_impact_events": (
                {"event_id": "event-2", "scheduled_at": "2026-09-16T09:00:00Z"},
                {"event_id": "event-1", "scheduled_at": "2026-09-16T08:00:00Z"},
                "invalid",
            )
        },
    )
    merged = ResearchApplicationService._attach_market_context(
        replace(
            snapshot,
            news_snapshot={
                "high_impact_events": (
                    {"event_id": "event-0", "scheduled_at": "2026-09-16T07:00:00Z"},
                )
            },
            sentiment_snapshot={},
        ),
        batch,
    )
    assert merged.news_snapshot["source_count"] == 3
    assert merged.sentiment_snapshot["source_count"] == 3
    assert research_module._has_external_evidence({"source_count": True}) is False


def test_research_application_run_observer_and_virtual_runtime_edges() -> None:
    class _Context:
        def for_step(self, step: str) -> "_Context":
            self.step = step
            return self

    class _Observer:
        def __init__(self) -> None:
            self.events: list[str] = []

        def emit(
            self,
            context: _Context,
            event: str,
            status: str,
            **kwargs: object,
        ) -> None:
            del context, status, kwargs
            self.events.append(event)

    observer = _Observer()
    service = ResearchApplicationService(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        primitive_converter=to_primitive,
        observer=observer,
        run_context_builder=lambda snapshot_id, name: _Context(),
    )

    workflow = service.run(public_snapshot())

    assert "research_workflow_started" in observer.events
    assert "research_workflow_completed" in observer.events
    assert workflow.execution_allowed is False

    capture_service = SimpleNamespace(capture=lambda symbol, observed_at: None)
    service_with_capture = ResearchApplicationService(
        orchestrator=_RuntimeReadyOrchestrator(),
        outlook_engine=_RuntimeReadyOutlook(),
        primitive_converter=to_primitive,
        wallet_service=capture_service,
        wallet_capture_enabled=True,
    )
    with pytest.raises(ValueError, match="wallet override"):
        service_with_capture.run(public_snapshot(), wallet=object())

    object.__setattr__(service, "virtual_market_runtime", None)
    assert service._evaluate_virtual_runtime(public_snapshot(), SimpleNamespace()) == (
        None,
        None,
    )
    object.__setattr__(service, "virtual_market_runtime", object())
    assert service._evaluate_virtual_runtime(
        public_snapshot(),
        SimpleNamespace(candidate_setups=()),
    ) == (None, None)


def test_historical_replay_guard_helpers_and_publication_edges(
    tmp_path: Path,
) -> None:
    outcome = HistoricalDgeCounterfactualOutcome(
        decision_id="dge:decision:1",
        market=VirtualMarket.SPOT,
        rule_id="DGE_RULE_1",
        outcome_observed_at=NOW,
        net_pnl_usdt=Decimal("1"),
        execution_model_sha256=HASH_1,
        replay_state_sha256=HASH_1,
        evidence_refs=("evidence:1",),
    )
    assert outcome.to_payload()["market"] == "SPOT"

    evaluator = HistoricalReplaySystemEvaluator()
    result = _dual_no_trade_result()
    evaluation = evaluator.evaluate(result)
    spot = evaluation.market(VirtualMarket.SPOT)
    with pytest.raises(ValueError, match="historical market performance"):
        HistoricalMarketPerformanceEvaluation(
            market=VirtualMarket.USD_M_FUTURES,
            portfolio_performance=spot.performance.portfolio_performance,
            attribution_ledger=spot.performance.attribution_ledger,
            common_kpis=spot.performance.common_kpis,
            market_specific_kpis=spot.performance.market_specific_kpis,
            operational_kpis=spot.performance.operational_kpis,
        )
    with pytest.raises(ValueError, match="metric ids"):
        HistoricalMarketPerformanceEvaluation(
            market=spot.performance.market,
            portfolio_performance=spot.performance.portfolio_performance,
            attribution_ledger=spot.performance.attribution_ledger,
            common_kpis=(HistoricalReplayMetric("duplicate", 1, "count"),) * 2,
            market_specific_kpis=(),
            operational_kpis=(),
        )
    with pytest.raises(ValueError, match="identity"):
        replace(spot, market=VirtualMarket.USD_M_FUTURES)
    with pytest.raises(ValueError, match="blockers"):
        replace(spot, blockers=("OTHER",))
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(spot, execution_allowed=True)
    with pytest.raises(ValueError, match="exact requested markets"):
        replace(evaluation, markets=(evaluation.markets[0],))
    with pytest.raises(ValueError, match="system acceptance"):
        replace(evaluation, system_acceptance=None)
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(evaluation, execution_allowed=True)
    with pytest.raises(ValueError, match="SHA-256"):
        evaluator.evaluate(result, reproducibility_reference_sha256="bad")
    single = evaluator.evaluate(
        _runner(orchestrator=_NoCandidateOrchestrator()).run(
            _request(run_id="single-market-edge"),
            (_snapshot(START, snapshot_id="single-market-edge"),),
        )
    )
    with pytest.raises(ValueError, match="cannot fabricate system acceptance"):
        replace(single, system_acceptance=evaluation.system_acceptance)

    paths = UserReportPaths(
        report_dir=tmp_path,
        artifact_dir=tmp_path,
        json_path=tmp_path / "a.json",
        markdown_path=tmp_path / "a.md",
        latest_json_path=tmp_path / "latest.json",
        latest_markdown_path=tmp_path / "latest.md",
    )
    with pytest.raises(ValueError, match="unique supported markets"):
        HistoricalReplayPublication(
            state_path=tmp_path / "state.json",
            state_persisted=False,
            market_report_paths=(),
            system_acceptance_paths=None,
            system_evaluation_paths=paths,
        )
    with pytest.raises(ValueError, match="system acceptance"):
        HistoricalReplayPublication(
            state_path=tmp_path / "state.json",
            state_persisted=False,
            market_report_paths=((VirtualMarket.SPOT, paths),),
            system_acceptance_paths=paths,
            system_evaluation_paths=paths,
        )
    with pytest.raises(ValueError, match="cannot authorize"):
        HistoricalReplayPublication(
            state_path=tmp_path / "state.json",
            state_persisted=False,
            market_report_paths=((VirtualMarket.SPOT, paths),),
            system_acceptance_paths=None,
            system_evaluation_paths=paths,
            execution_allowed=True,
        )

    duplicate = _counterfactuals(_dual_dge_blocked_result())[0]
    with pytest.raises(ValueError, match="unique per rule"):
        evaluator.evaluate(
            _dual_dge_blocked_result(),
            dge_counterfactuals=(duplicate, duplicate),
        )
    with pytest.raises(ValueError, match="replay state mismatch"):
        evaluator.evaluate(
            _dual_dge_blocked_result(),
            dge_counterfactuals=(replace(duplicate, replay_state_sha256="a" * 64),),
            reproducibility_reference_sha256=(
                _dual_dge_blocked_result().semantic_result_sha256
            ),
        )

    class _DuplicateMarketMapping:
        def items(self) -> tuple[tuple[object, int], ...]:
            return ((VirtualMarket.SPOT, 1), ("SPOT", 2))

    with pytest.raises(ValueError, match="duplicate markets"):
        historical_module._normalize_market_mapping(
            cast(Mapping[VirtualMarket | str, int], _DuplicateMarketMapping())
        )
    assert (
        historical_module._eligible_dge_rules(_dual_no_trade_result().cycles[0]) == ()
    )

    dge_result = _dual_dge_blocked_result()
    dge_cycles = tuple(
        cycle
        for cycle in dge_result.cycles
        if cycle.replay_snapshot.market == VirtualMarket.SPOT.value
    )
    dge_curve = next(
        curve
        for curve in dge_result.equity_curves
        if curve.market is VirtualMarket.SPOT
    )
    _metrics, blockers = historical_module._dge_effectiveness(
        result=dge_result,
        market=VirtualMarket.SPOT,
        cycles=dge_cycles,
        trades=(),
        curve=dge_curve,
        outcomes=(),
        reproducibility_rate=Decimal("1"),
        runtime=evaluator.runtime,
    )
    assert "DGE_COUNTERFACTUAL_OUTCOME_EVIDENCE_INCOMPLETE" in blockers
    _metrics, blockers = historical_module._dge_effectiveness(
        result=dge_result,
        market=VirtualMarket.SPOT,
        cycles=cast(
            tuple[HistoricalReplayCycleResult, ...],
            (
                SimpleNamespace(
                    replay_snapshot=SimpleNamespace(created_at=START),
                    workflow=SimpleNamespace(
                        virtual_runtime_request=SimpleNamespace(
                            decision_id="dge:synthetic",
                            dge_blockers=("DGE_RULE", "NOT_ABLATABLE"),
                            dge_simulation_allowed=False,
                        )
                    ),
                ),
            ),
        ),
        trades=(),
        curve=dge_curve,
        outcomes=(),
        reproducibility_rate=Decimal("1"),
        runtime=evaluator.runtime,
    )
    assert "DGE_HIGHER_AUTHORITY_BLOCKER_NOT_ABLATABLE" in blockers
    with pytest.raises(ValueError, match="unknown rule activation"):
        historical_module._dge_effectiveness(
            result=dge_result,
            market=VirtualMarket.SPOT,
            cycles=dge_cycles,
            trades=(),
            curve=dge_curve,
            outcomes=(
                HistoricalDgeCounterfactualOutcome(
                    decision_id="unknown",
                    market=VirtualMarket.SPOT,
                    rule_id="DGE_UNKNOWN",
                    outcome_observed_at=START,
                    net_pnl_usdt=Decimal("-1"),
                    execution_model_sha256=HASH_1,
                    replay_state_sha256=dge_result.semantic_result_sha256,
                    evidence_refs=("evidence:unknown",),
                ),
            ),
            reproducibility_rate=Decimal("1"),
            runtime=evaluator.runtime,
        )
    with pytest.raises(ValueError, match="EQUITY_INVALID"):
        historical_module._counterfactual_equity_curve(
            dge_curve,
            (
                HistoricalDgeCounterfactualOutcome(
                    decision_id="dge:snapshot-dge-shadow-spot",
                    market=VirtualMarket.SPOT,
                    rule_id="DGE_DATA_UNAVAILABLE",
                    outcome_observed_at=START,
                    net_pnl_usdt=Decimal("-1000000"),
                    execution_model_sha256=HASH_1,
                    replay_state_sha256=dge_result.semantic_result_sha256,
                    evidence_refs=("evidence:loss",),
                ),
            ),
        )
    assert historical_module._ratio(1, 0) == Decimal("0")
    assert historical_module._bounded_ratio(Decimal("1"), Decimal("0")) == Decimal("0")


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    runtime_state_path = tmp_path / "runtime" / "state" / "runtime.json"
    monkeypatch.setenv("AI4BINANCE_RUNTIME_STATE_PATH", str(runtime_state_path))
    monkeypatch.setenv(
        "AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY",
        str(tmp_path / "Accounting"),
    )
    monkeypatch.setenv("AI4BINANCE_AUDIT_DIRECTORY", str(tmp_path / "logs"))
    monkeypatch.setenv(
        "AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY",
        str(tmp_path / "Validation"),
    )
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    return Settings()


def _report() -> DualMarketAdvisoryReport:
    advisory = MarketAdvisory(
        market="SPOT",
        action="NO_TRADE",
        bias="NEUTRAL",
        setup_radar=(),
        blockers=(),
        wallet_status="NOT_CONFIGURED",
    )
    futures = replace(advisory, market="USD_M_FUTURES")
    return DualMarketAdvisoryReport(
        cycle_id="cycle-1",
        symbol="BTCUSDT",
        created_at=NOW,
        state=RuntimeState.READY,
        spot=advisory,
        futures=futures,
        blockers=(),
    )

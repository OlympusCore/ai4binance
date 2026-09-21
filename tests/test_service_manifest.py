"""Service manifest proof contracts for resident operations health."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from ai4binance.config import Settings
from ai4binance.ops.service_health import (
    ServiceHealthSpec,
    load_service_manifest,
    service_health_from_spec,
    startup_health_from_manifest,
)

NOW = datetime(2026, 8, 8, 18, 0, tzinfo=UTC)


def test_service_manifest_is_shared_safe_and_complete() -> None:
    specs = load_service_manifest()
    required = {spec.service: spec for spec in specs if spec.required}

    assert set(required) == {
        "runtime",
        "virtual-market",
        "accounting",
        "accounting-ws",
        "skill-discovery",
        "market-history",
    }
    assert required["accounting"].task_name == "AI4BINANCE-Accounting-Collector"
    assert required["virtual-market"].task_name == "AI4BINANCE-Virtual-Market"
    assert required["virtual-market"].command == "virtual-market-daemon"
    assert required["virtual-market"].lock_file == "virtual-market.lock"
    assert required["skill-discovery"].health_file == "skill-discovery-health.json"
    assert required["skill-discovery"].lock_file == "skill_discovery.lock"
    assert required["market-history"].task_name == "AI4BINANCE-Market-History"
    assert required["market-history"].command == (
        "python -m ai4binance.cli.market_gateway"
    )
    scheduled = {spec.service: spec for spec in specs if not spec.required}
    assert scheduled["ykb-report"].health_mode == "SCHEDULED"
    assert scheduled["qwen-prompter"].enabled is False
    assert scheduled["primary-local-reasoning"].enabled is True
    assert scheduled["primary-local-reasoning"].task_name == (
        "AI4BINANCE-Primary-Local-Reasoning"
    )
    assert scheduled["auto-audit"].enabled is False
    assert scheduled["futures-multitf"].useful_state_file == (
        "futures-multitf-latest.json"
    )
    assert scheduled["futures-multitf"].enabled is False
    for spec in specs:
        assert spec.startup_trigger == "AtLogOn"
        assert spec.allow_start_if_on_batteries is True
        assert spec.stop_if_going_on_batteries is False
        assert spec.order_writing_authority is False


def test_startup_manifest_degrades_stale_useful_cycle_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "state"
    for service in (
        "runtime",
        "virtual-market",
        "accounting",
        "accounting-ws",
        "skill-discovery",
        "market-history",
        "futures-multitf",
    ):
        _write_health(state_dir, service, NOW)
    (state_dir / "virtual-market.json").write_text(
        json.dumps({"last_success_at": NOW.isoformat()}), encoding="utf-8"
    )
    (state_dir / "market-history-latest.json").write_text(
        json.dumps({"observed_at": NOW.isoformat()}), encoding="utf-8"
    )
    (state_dir / "futures-multitf-latest.json").write_text(
        json.dumps({"observed_at": NOW.isoformat()}), encoding="utf-8"
    )
    stale = datetime(2026, 8, 8, 17, 45, tzinfo=UTC)
    _write_health(state_dir, "accounting", NOW, last_success_at=stale)

    payload = startup_health_from_manifest(
        settings,
        NOW,
        pid_is_alive=lambda pid: pid == 4242,
    )

    assert payload["status"] == "DEGRADED"
    blockers = cast(tuple[str, ...], payload["blockers"])
    assert "ACCOUNTING_USEFUL_CYCLE_STALE" in blockers
    service_items = cast(tuple[dict[str, object], ...], payload["services"])
    services = {str(item["service"]): item for item in service_items}
    assert services["accounting"]["task_name"] == "AI4BINANCE-Accounting-Collector"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_startup_status_powershell_reads_the_same_service_manifest() -> None:
    status_text = (Path("scripts") / "startup_status.ps1").read_text(encoding="utf-8")
    install_text = (Path("scripts") / "install_startup_task.ps1").read_text(
        encoding="utf-8"
    )

    assert "config\\operations\\services.json" in status_text
    assert "ConvertFrom-Json" in status_text
    assert "config\\operations\\services.json" in install_text
    assert "ConvertFrom-Json" in install_text
    assert "function Test-CanonicalTaskAction" in status_text
    assert "ACTION_EXECUTABLE_DRIFT" in status_text
    assert "ACTION_WORKING_DIRECTORY_DRIFT" in status_text
    assert "ACTION_ARGUMENT_DRIFT" in status_text
    assert "AllowStartIfOnBatteries" in install_text
    assert "DontStopIfGoingOnBatteries" in install_text


def test_startup_status_supports_schema_versioned_runtime_leases() -> None:
    status_text = (Path("scripts") / "startup_status.ps1").read_text(encoding="utf-8")

    assert "ConvertFrom-Json -ErrorAction Stop" in status_text
    assert "lockDocument.schema_version" in status_text
    assert "legacy PID-only lease" in status_text


def test_startup_status_uses_version_agnostic_global_python_classification() -> None:
    status_text = (Path("scripts") / "startup_status.ps1").read_text(encoding="utf-8")

    assert "Python\\d+" in status_text
    assert '"global-python"' in status_text
    assert "global-py3" not in status_text


def test_startup_install_script_preserves_cli_module_runtime_commands() -> None:
    install_text = (Path("scripts") / "install_startup_task.ps1").read_text(
        encoding="utf-8"
    )
    status_text = (Path("scripts") / "startup_status.ps1").read_text(encoding="utf-8")
    tray_install_text = (Path("scripts") / "install_startup_tray_task.ps1").read_text(
        encoding="utf-8"
    )
    tray_host_text = (Path("scripts") / "startup_tray_host.ps1").read_text(
        encoding="utf-8"
    )

    assert '@("-m", "ai4binance.cli", $Command)' in install_text
    assert "-Arguments $pythonArguments" in install_text
    assert '$env:PYTHONDONTWRITEBYTECODE = "1"' in install_text
    assert "& $python -B @Arguments" in install_text
    assert "& $python @Arguments" not in install_text
    assert '-Arguments @("-m", "ai4binance.cli", "archive-public")' in install_text
    assert '-Arguments @("-m", "ai4binance.cli", "validate-research")' in install_text
    assert "-WindowStyle Hidden" in install_text
    assert (
        '(Get-ServiceManifestEntry -Service "accounting").required -or '
        "$EnableAccountingTask" in install_text
    )
    assert (
        '(Get-ServiceManifestEntry -Service "accounting-ws").required -or '
        "$EnableAccountingWsTask" in install_text
    )
    assert (
        '(Get-ServiceManifestEntry -Service "skill-discovery").required -or '
        "$EnableSkillDiscoveryTask" in install_text
    )
    assert '(Get-ServiceManifestEntry -Service "ykb-report").task_name' in install_text
    assert "[bool]$EnableYkbReportTask = $true" in install_text
    assert "ykb_daily_report.ps1" in install_text
    assert "AI4BINANCE-YKB-Daily-Report" in install_text
    assert "-Mode Install" in install_text
    assert "-DailyTime $YkbDailyTime" in install_text
    assert "-MaxReportAgeHours $YkbMaxReportAgeHours" in install_text
    assert "YKB report installation failed." in install_text
    assert (
        'Start-BoundedService -Service "runtime" -Command "runtime-daemon" '
        "-RestartForever" in install_text
    )
    assert '-Service "virtual-market"' in install_text
    assert '-Command "virtual-market-daemon"' in install_text
    assert 'Get-ServiceManifestEntry -Service "virtual-market"' in install_text
    assert "InstallVirtualMarket" in install_text
    assert "RunVirtualMarket" in install_text
    assert "ai4binance\\.cli\\s+virtual-market-daemon" in status_text
    assert "VIRTUAL_MARKET" in status_text
    assert 'Join-Path $stateDirectory "virtual-market.json"' in status_text
    assert 'Label "VIRTUAL_MARKET_CYCLE"' in status_text
    assert 'Start-BoundedService -Service "voice" -Command "voice-daemon"' in (
        install_text
    )
    assert '-Service "accounting"' in install_text
    assert '-Command "accounting-collect-daemon"' in install_text
    assert '-Service "accounting-ws"' in install_text
    assert '-Command "accounting-ws-daemon"' in install_text
    assert '-Service "skill-discovery"' in install_text
    assert '-Command "skill-discovery-daemon"' in install_text
    assert '-Module "ai4binance.cli.market_data"' in install_text
    assert '-Module "ai4binance.cli.futures_multitf"' in install_text
    assert "[switch]$RestartForever" in install_text
    assert 'Status "RECOVERING"' in install_text
    assert "Start-Sleep -Seconds 60" in install_text
    assert "AI4BINANCE-Market-History" in install_text
    assert "$marketRecoveryTriggers" not in install_text
    assert "$recoveryTriggers" not in install_text
    assert "AddHours($hour)" not in install_text
    assert "-RestartCount 999" in install_text
    assert "-Action $action -Trigger $logonTrigger" in install_text
    assert "-Action $marketAction -Trigger $marketLogonTrigger" in install_text
    assert "-Action $multiTfAction -Trigger $marketLogonTrigger" in install_text
    assert "ai4binance\\.cli\\.market_data" in status_text
    assert "MARKET_HISTORY" in status_text
    assert "AI4BINANCE-Startup-Tray" in tray_install_text
    assert "-WindowStyle Hidden" in tray_install_text
    assert "sync.ico" in tray_install_text
    assert "NotifyIcon" in tray_host_text
    assert "AI4BINANCE Assistant" in tray_host_text
    assert "Chat" in tray_host_text
    assert "AI4BINANCE Chat" in tray_host_text
    assert "Closing hides the window." in tray_host_text
    assert "Get-FastLocalAnswer" in tray_host_text
    assert "Get-AI4BinanceWalletAnswer" in tray_host_text
    assert "Format-AI4BinanceAssistantAnswer" in tray_host_text
    assert "assistant_wallet_context.ps1" in tray_host_text
    assert "private\\account-management.json" in tray_host_text
    assert "Get-CurrentIstanbulTimestamp" in tray_host_text
    assert "Europe/Istanbul time:" in tray_host_text
    assert "AI4BINANCE asistani hazir." in tray_host_text
    assert "Soru yaz ve Send tusuna bas." in tray_host_text
    assert "Chat history and previous assistant answers are not evidence." in (
        tray_host_text
    )
    assert "do not provide a generic or invented answer" in tray_host_text
    assert "Calisma durumu:" in tray_host_text
    assert "aktif engel sayisi:" in tray_host_text
    assert "Kisa cevap: Hayir, tam otonom degil." in tray_host_text
    assert "Get-HumanReadableRuntimeState" in tray_host_text
    assert '"READY" { return "hazir" }' in tray_host_text
    assert '"DEGRADED" { return "kisitli" }' in tray_host_text
    assert "blockers=$((@($runtime.blockers) -join ','))" not in tray_host_text
    assert "Calisma durumu: DEGRADED" not in tray_host_text
    assert "Show-AssistantChatWindow" in tray_host_text
    assert "ShowInTaskbar = $false" in tray_host_text
    assert "Asistan dusunuyor..." in tray_host_text
    assert "n_predict = $maxPredictTokens" in tray_host_text
    assert "sync.ico" in tray_host_text


def test_ykb_daily_report_task_refreshes_stale_report_on_logon() -> None:
    script_text = (Path("scripts") / "ykb_daily_report.ps1").read_text(encoding="utf-8")

    assert "AI4BINANCE-YKB-Daily-Report" in script_text
    assert (
        '[ValidateSet("RunIfStale", "RunNow", "RunLoop", "Install", "Status")]'
        in script_text
    )
    assert "[int]$MaxReportAgeHours = 4" in script_text
    assert "runtime\\artifacts\\user_reports\\ykb\\latest.json" in script_text
    assert "Get-StartupLauncherPath" in script_text
    assert "Write-StartupLauncher" in script_text
    assert "AI4BINANCE-YKB-Daily-Report.cmd" in script_text
    assert "RunLoop -Symbol" in script_text
    assert "Start-YkbLoop" in script_text
    assert "Initialize-Utf8Logs" in script_text
    assert "Invoke-PythonUtf8Command" in script_text
    assert "Start-Process" in script_text
    assert "PYTHONPATH" in script_text
    assert "src" in script_text
    assert "-Encoding UTF8" in script_text
    assert "WriteAllText" in script_text
    assert "AppendAllText" in script_text
    assert "New-ScheduledTaskTrigger -AtLogOn" in script_text
    assert (
        "$staleCheckTriggers = for ($offset = 0; $offset -lt 24; $offset++)"
        in script_text
    )
    assert (
        "New-ScheduledTaskTrigger -Daily -At ($dailyAnchor.AddHours($offset))"
        in script_text
    )
    assert "-Trigger (@($logonTrigger) + $staleCheckTriggers)" in script_text
    assert "-StartWhenAvailable" in script_text
    assert "Read-LatestReportState" in script_text
    assert "Sync-LatestHumanReport" in script_text
    assert "Get-RecentYkbReports" in script_text
    assert "RecentReportHistory" in script_text
    assert "runtime\\reports\\ykb" in script_text
    assert "runtime\\state" in script_text
    assert "runtime\\logs\\services" in script_text
    assert "AllowEmptyCollection" in script_text
    assert "ykb_report_STALE" in script_text
    assert "ykb_report_FUTURE_TIMESTAMP" in script_text
    assert "runtime-research-refresh-once" in script_text
    assert "YKB_HUMAN_REPORT_READY" in script_text
    assert "markdown_path" in script_text
    assert "latest_markdown_path" in script_text
    assert 'if ($Mode -eq "RunNow")' in script_text
    assert "execution_allowed" in script_text
    assert "live_eligibility_status" in script_text
    assert "LIVE_ORDER_BLOCKED" in script_text
    assert "Invoke-PythonUtf8Command -ArgumentList @(" in script_text


def test_ykb_daily_report_script_uses_utf8_redirect_helper() -> None:
    script_text = (Path("scripts") / "ykb_daily_report.ps1").read_text(encoding="utf-8")

    assert "Start-Process" in (script_text)
    assert '$env:PYTHONDONTWRITEBYTECODE = "1"' in script_text
    assert '$pythonArguments = @("-B") + $ArgumentList' in script_text
    assert "-ArgumentList $pythonArguments" in script_text
    assert "-ArgumentList $ArgumentList" not in script_text
    assert "RedirectStandardOutput" in script_text
    assert "RedirectStandardError" in script_text
    assert "Get-Content -LiteralPath $stdoutTemp -Raw -Encoding UTF8" in script_text
    assert "AppendAllText($stdoutPath, $stdoutContent" in script_text
    assert "AppendAllText($stderrPath, $stderrContent" in script_text
    assert '$tempDirectory = Join-Path $root "runtime\\tmp\\ykb"' in script_text
    assert '"capture-" + [guid]::NewGuid().ToString("N")' in script_text
    assert '$stdoutTemp = Join-Path $captureDirectory "stdout.tmp"' in script_text
    assert '$stderrTemp = Join-Path $captureDirectory "stderr.tmp"' in script_text
    assert "-LiteralPath $captureDirectory" in script_text
    assert "-Confirm:$false" in script_text
    assert "[System.IO.Path]::GetTempFileName()" not in script_text


def test_ykb_install_verifies_existing_task_before_removing_fallback() -> None:
    script_text = (Path("scripts") / "ykb_daily_report.ps1").read_text(encoding="utf-8")

    assert "function Test-YkbScheduledTaskConfiguration" in script_text
    assert "$actions.Count -ne 1" in script_text
    assert "$triggers.Count -ne 25" in script_text
    assert "$logonTriggers.Count -ne 1 -or $dailyTriggers.Count -ne 24" in script_text
    assert 'Task.Principal.RunLevel -ne "Limited"' in script_text
    assert 'Task.Settings.MultipleInstances -ne "IgnoreNew"' in script_text
    assert "-not [bool]$Task.Settings.StartWhenAvailable" in script_text
    assert "$existingTaskMatches" in script_text
    assert "Test-YkbScheduledTaskConfiguration" in script_text
    assert "Remove-StartupLauncher" in script_text
    assert 'Write-Output "status=EXISTING_TASK_VERIFIED"' in script_text
    assert 'Write-Output "registration_error=$registrationError"' in script_text


def test_repository_governance_monitor_disables_bytecode_writes() -> None:
    script_text = (Path("scripts") / "repository_governance_monitor.ps1").read_text(
        encoding="utf-8"
    )

    assert '$env:PYTHONDONTWRITEBYTECODE = "1"' in script_text
    assert "& $python -B -m ai4binance.governance.repository_validator" in script_text
    assert "& $python -m ai4binance.governance.repository_validator" not in script_text


def test_service_manifest_rejects_live_authority_drift(tmp_path: Path) -> None:
    path = tmp_path / "services.json"
    payload = json.loads(
        (Path("config") / "operations" / "services.json").read_text(encoding="utf-8")
    )
    payload["execution_allowed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot allow execution"):
        load_service_manifest(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update({"live_eligibility_status": "READY"}),
            "blocked",
        ),
        (lambda payload: payload.update({"services": []}), "list services"),
        (
            lambda payload: payload.update({"services": [payload["services"][0]] * 2}),
            "unique",
        ),
        (lambda payload: payload.update({"services": ["bad"]}), "entries"),
        (
            lambda payload: payload["services"][0].update({"service": " "}),
            "non-empty string",
        ),
        (
            lambda payload: payload["services"][0].update({"required": "yes"}),
            "boolean",
        ),
        (
            lambda payload: payload["services"][0].update({"enabled": False}),
            "cannot be disabled",
        ),
        (
            lambda payload: payload["services"][0].update(
                {"max_health_age_seconds": 0}
            ),
            "positive",
        ),
        (
            lambda payload: payload["services"][0].update({"health_file": "../x"}),
            "simple file name",
        ),
        (
            lambda payload: payload["services"][0].update(
                {"useful_state_file": "../outside.json"}
            ),
            "safe relative path",
        ),
        (
            lambda payload: payload["services"][-1].update(
                {"health_mode": "ON_DEMAND"}
            ),
            "health_mode",
        ),
    ],
)
def test_service_manifest_rejects_invalid_contracts(
    tmp_path: Path,
    mutation: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    path = tmp_path / "services.json"
    payload = json.loads(
        (Path("config") / "operations" / "services.json").read_text(encoding="utf-8")
    )
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_service_manifest(path)


def test_service_health_reports_invalid_and_authority_drift_states(
    tmp_path: Path,
) -> None:
    spec = ServiceHealthSpec(
        service="research-daemon",
        task_name="AI4BINANCE-Research",
        command="python -m ai4binance.cli research",
        mode="Run",
        required=True,
        health_file="research-health.json",
        lock_file="research.lock",
        max_health_age_seconds=60,
        startup_trigger="AtLogOn",
        allow_start_if_on_batteries=False,
        stop_if_going_on_batteries=True,
        order_writing_authority=True,
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / spec.health_file).write_text("[]", encoding="utf-8")

    invalid = service_health_from_spec(
        spec,
        state_dir,
        NOW,
        pid_is_alive=lambda pid: False,
    )

    blockers = cast(tuple[str, ...], invalid["blockers"])
    assert "RESEARCH_DAEMON_STATE_INVALID" in blockers
    assert "RESEARCH_DAEMON_STATE_TIMESTAMP_INVALID" in blockers
    assert "RESEARCH_DAEMON_USEFUL_CYCLE_TIMESTAMP_INVALID" in blockers
    assert "RESEARCH_DAEMON_BATTERY_START_BLOCKED" in blockers
    assert "RESEARCH_DAEMON_BATTERY_STOP_ENABLED" in blockers
    assert "RESEARCH_DAEMON_ORDER_WRITING_AUTHORITY_DRIFT" in blockers

    (state_dir / spec.health_file).write_text(
        json.dumps(
            {
                "status": "STOPPED",
                "updated_at": "2026-08-08T18:02:00+00:00",
                "last_success_at": "not-a-date",
                "pid": True,
                "child_pid": "child",
                "execution_allowed": True,
                "live_eligibility_status": "READY",
            }
        ),
        encoding="utf-8",
    )
    (state_dir / spec.lock_file).write_text("4243", encoding="ascii")
    drift = service_health_from_spec(
        spec,
        state_dir,
        NOW,
        pid_is_alive=lambda pid: pid == 9999,
    )

    blockers = cast(tuple[str, ...], drift["blockers"])
    assert "RESEARCH_DAEMON_STATE_STALE" in blockers
    assert "RESEARCH_DAEMON_USEFUL_CYCLE_STALE" in blockers
    assert "RESEARCH_DAEMON_NOT_RUNNING" in blockers
    assert "RESEARCH_DAEMON_EXECUTION_AUTHORITY_DRIFT" in blockers
    assert "RESEARCH_DAEMON_LIVE_AUTHORITY_DRIFT" in blockers
    assert "RESEARCH_DAEMON_PID_NOT_ALIVE" in blockers
    assert "RESEARCH_DAEMON_LOCK_PID_NOT_ALIVE" in blockers


def test_service_health_separates_liveness_from_useful_cycle(
    tmp_path: Path,
) -> None:
    spec = ServiceHealthSpec(
        service="research-daemon",
        task_name="AI4BINANCE-Research",
        command="python -m ai4binance.cli research",
        mode="Run",
        required=True,
        health_file="research-health.json",
        lock_file="research.lock",
        max_health_age_seconds=60,
        startup_trigger="AtLogOn",
        allow_start_if_on_batteries=True,
        stop_if_going_on_batteries=False,
        order_writing_authority=False,
        useful_state_file="research/latest.json",
        useful_timestamp_field="observed_at",
        max_useful_cycle_age_seconds=120,
    )
    state_dir = tmp_path / "state"
    useful_dir = state_dir / "research"
    useful_dir.mkdir(parents=True)
    (state_dir / spec.health_file).write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "updated_at": NOW.isoformat(),
                "pid": 4242,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    (state_dir / spec.lock_file).write_text("4242", encoding="ascii")
    (useful_dir / "latest.json").write_text(
        json.dumps({"observed_at": "2026-08-08T17:55:00+00:00"}),
        encoding="utf-8",
    )

    result = service_health_from_spec(
        spec,
        state_dir,
        NOW,
        pid_is_alive=lambda pid: pid == 4242,
    )

    assert result["updated_at"] == NOW.isoformat()
    assert result["age_seconds"] == 300.0
    blockers = cast(tuple[str, ...], result["blockers"])
    assert "RESEARCH_DAEMON_STATE_STALE" not in blockers
    assert "RESEARCH_DAEMON_USEFUL_CYCLE_STALE" in blockers


def test_disabled_optional_service_is_explicit_and_not_degraded(tmp_path: Path) -> None:
    spec = next(
        item for item in load_service_manifest() if item.service == "qwen-prompter"
    )

    result = service_health_from_spec(
        spec,
        tmp_path,
        NOW,
        pid_is_alive=lambda _: False,
    )

    assert result["status"] == "DISABLED"
    assert result["enabled"] is False
    assert result["blockers"] == ()


def test_scheduled_service_health_requires_ready_state_not_resident_process(
    tmp_path: Path,
) -> None:
    spec = next(
        item for item in load_service_manifest() if item.service == "ykb-report"
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / spec.health_file).write_text(
        json.dumps(
            {
                "service": spec.service,
                "status": "READY",
                "updated_at": NOW.isoformat(),
                "last_success_at": NOW.isoformat(),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )

    result = service_health_from_spec(
        spec,
        state_dir,
        NOW,
        pid_is_alive=lambda _: False,
    )

    assert result["status"] == "READY"
    assert result["health_mode"] == "SCHEDULED"
    assert result["blockers"] == ()


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_STATE_PATH",
        str(tmp_path / "state" / "runtime.json"),
    )
    return Settings()


def _write_health(
    state_dir: Path,
    service: str,
    updated_at: datetime,
    *,
    last_success_at: datetime | None = None,
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f"{service}.lock").write_text("4242", encoding="ascii")
    payload = {
        "service": service,
        "status": "RUNNING",
        "updated_at": updated_at.isoformat(),
        "pid": 4242,
        "child_pid": 0,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    if last_success_at is not None:
        payload["last_success_at"] = last_success_at.isoformat()
    (state_dir / f"{service}-health.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )

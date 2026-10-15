from __future__ import annotations

import hashlib
import http.client
import json
import runpy
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ai4binance" / "local_dashboard"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_dashboard_source_builds_deterministic_offline_assets(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "dashboard"
    shutil.copytree(SOURCE, stage)

    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(stage / "build.py.in"),
            str(stage / "design_source.html"),
            str(ROOT / "frontend" / "src"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "DASHBOARD_PACKAGE_BUILT"
    assert _sha256(stage / "app.js") == (
        "18ce82d045aec6cebaf87a239dd422c2451bf5a7e96b7f82e70e0ee4279162e2"
    )
    assert _sha256(stage / "app.css") == (
        "9d135f9c272b0f2ae41486b870204d7bdc8e963f0048520da2876918bd776b09"
    )
    assert _sha256(stage / "index.html") == (
        "cf00ea2f86490a6a63b8a8383edbd0ed813a4fb3b85af1775915e13ca41219ca"
    )
    document = (stage / "index.html").read_text(encoding="utf-8")
    script = (stage / "app.js").read_text(encoding="utf-8")
    assert "/lucide.js" not in document
    assert "renderDashboardIcons(root)" in script
    assert "Copyright (c) 2026 Lucide Icons and Contributors" in script
    node = shutil.which("node")
    assert node is not None
    syntax = subprocess.run(  # noqa: S603
        [node, "--check", str(stage / "app.js")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert syntax.returncode == 0, syntax.stderr
    expected = {
        name: _sha256(stage / name) for name in ("app.js", "app.css", "index.html")
    }
    repeated = subprocess.run(  # noqa: S603
        completed.args,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert expected == {name: _sha256(stage / name) for name in expected}
    public_files = runpy.run_path(str(stage / "server.py.in"))["PUBLIC_FILES"]
    assert "/lucide.js" not in public_files


def test_dashboard_deployer_preserves_machine_state_and_private_profile() -> None:
    deployer = (ROOT / "scripts" / "deploy_local_dashboard.ps1").read_text(
        encoding="utf-8"
    )

    assert "runtime/dashboard/config.json" in deployer
    assert "runtime/dashboard/browser-profile" in deployer
    assert "source-manifest.json" in deployer
    assert 'live_eligibility_status = "LIVE_ORDER_BLOCKED"' in deployer


def test_dashboard_packaging_reads_operations_from_canonical_owner(
    tmp_path: Path,
) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for the Windows packaging test")
    receipt = tmp_path / "test-only-dashboard-package.json"
    completed = subprocess.run(  # noqa: S603
        [
            shell,
            "-NoProfile",
            "-File",
            str(ROOT / "scripts/deploy_local_dashboard.ps1"),
            "-ReceiptPath",
            str(receipt),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert payload["applied"] is False
    assert payload["restart_required"] is False
    assert payload["verification_status"] == "BUILT_NOT_DEPLOYED"
    assert isinstance(payload["restart_required_if_applied"], bool)
    records = {item["path"]: item["sha256"] for item in payload["source_files"]}
    for name in ("install.ps1.in", "launch.ps1.in"):
        path = ROOT / "scripts/local_dashboard" / name
        assert records[path.relative_to(ROOT).as_posix()] == _sha256(path)
        assert not (SOURCE / name).exists()
    for name in (
        "command_center.ts",
        "command_center.css",
        "dashboard_shell.ts",
        "dashboard_icons.ts",
    ):
        path = ROOT / "frontend" / "src" / name
        assert records[path.relative_to(ROOT).as_posix()] == _sha256(path)
    assert not any("lucide.js" in path for path in records)
    assert not any("lucide.js" in item["path"] for item in payload["deployment_files"])


def test_dashboard_installer_does_not_bypass_task_registration_failure(
    tmp_path: Path,
) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for the Windows installer test")
    installer = tmp_path / "test-only-install.ps1"
    shutil.copyfile(ROOT / "scripts/local_dashboard/install.ps1.in", installer)
    (tmp_path / "config.json").write_text(
        json.dumps({"repository_root": str(tmp_path), "port": 8765}), encoding="utf-8"
    )
    harness = tmp_path / "test-only-installer-harness.ps1"
    harness.write_text(
        """
$ErrorActionPreference = 'Stop'
function New-ScheduledTaskAction {
    param($Execute, $Argument, $WorkingDirectory)
    if ($Argument -match 'ExecutionPolicy') { throw 'TEST_ONLY_POLICY_OVERRIDE' }
    [pscustomobject]@{}
}
function New-ScheduledTaskTrigger { [pscustomobject]@{} }
function New-ScheduledTaskPrincipal { [pscustomobject]@{} }
function New-ScheduledTaskSettingsSet { [pscustomobject]@{} }
function Get-ScheduledTask { $null }
function Register-ScheduledTask { throw 'TEST_ONLY_REGISTRATION_DENIED' }
function Start-ScheduledTask { throw 'TEST_ONLY_UNEXPECTED_TASK_START' }
function Start-Process { throw 'TEST_ONLY_UNEXPECTED_PROCESS_START' }
function New-Object { throw 'TEST_ONLY_UNEXPECTED_SHORTCUT_CREATION' }
try {
    & (Join-Path $PSScriptRoot 'test-only-install.ps1')
    throw 'TEST_ONLY_EXPECTED_FAILURE_MISSING'
} catch {
    [Console]::WriteLine($_.Exception.Message)
}
""",
        encoding="utf-8",
    )
    completed = subprocess.run(  # noqa: S603
        [shell, "-NoProfile", "-File", str(harness)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "TEST_ONLY_REGISTRATION_DENIED"
    assert not (tmp_path / "installation.json").exists()


def test_dashboard_exposes_useful_cycle_and_producer_health() -> None:
    server = (SOURCE / "server.py.in").read_text(encoding="utf-8")
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")

    assert '"last_success_at"' in server
    assert '"age_seconds"' in server
    assert '"producer_status"' in server
    assert "source.producer_status" in views
    assert "s.age_seconds" in views
    assert "DISABLED" in views


def test_dashboard_keeps_collection_progress_and_p3_advice_out_of_readiness() -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    findings = module["dashboard_health_findings"](
        {
            "market_history": {"completed_streams": 12, "total_streams": 301},
            "market_depth": {},
            "futures_research": {},
            "learning": {"lesson_count": 0, "experiment_count": 0},
            "services": [],
            "sources": {
                "market_history": {"status": "COLLECTING"},
                "market_depth": {"status": "COLLECTING"},
                "futures_research": {"status": "COLLECTING"},
                "auto_audit": {"status": "CURRENT"},
            },
        }
    )
    projection = module["operational_readiness_projection"](findings, [])

    assert [item["finding_id"] for item in findings] == ["LEARNING_SUMMARY_EMPTY"]
    assert projection == {
        "status": "READY",
        "finding_count": 1,
        "high_priority_finding_count": 0,
        "required_service_ready_count": 0,
        "required_service_count": 0,
    }


def test_dashboard_degrades_for_high_priority_health_findings() -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    projection = module["operational_readiness_projection"](
        [{"severity": "P2"}],
        [{"required": True, "status": "DEGRADED"}],
    )

    assert projection["status"] == "DEGRADED"
    assert projection["high_priority_finding_count"] == 1
    assert projection["required_service_ready_count"] == 0


@pytest.fixture
def kaizen_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Only disposable local inputs; no service, market network, or credentials."""
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    namespace = module["start_kaizen_action"].__globals__
    monkeypatch.setitem(namespace, "APP", tmp_path / "test-only-dashboard")
    root = tmp_path / "test-only-repository"
    (root / "config/operations").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "config/operations/services.json",
        root / "config/operations/services.json",
    )
    finding = {
        "finding_id": "MARKET_HISTORY_INCOMPLETE",
        "status": "DEGRADED",
        "evidence": "TEST_ONLY_SOURCE_FAILURE",
        "facts": {},
    }
    observed = {"health_findings": [finding]}
    monkeypatch.setitem(namespace, "snapshot", lambda _: observed)
    monkeypatch.setitem(
        sys.modules,
        "market_views",
        SimpleNamespace(selection=lambda *_: (root, ("TESTUSDT",), "TESTUSDT")),
    )
    return {
        "module": module,
        "namespace": namespace,
        "root": root,
        "config": {"repository_root": str(root)},
        "observed": observed,
    }


def test_kaizen_candle_apply_uses_canonical_queue_without_simulation(
    kaizen_host: dict[str, Any],
) -> None:
    module, config = kaizen_host["module"], kaizen_host["config"]
    actions = module["kaizen_actions"](config)
    request = {
        "token": actions["actions"][0]["token"],
        "confirmed": True,
        "market": "SPOT",
        "symbol": "TESTUSDT",
    }
    first = module["start_kaizen_action"](config, request)
    assert first["state"] == "PENDING"
    duplicate = module["start_kaizen_action"](config, request)
    assert duplicate["state"] == "BUSY"
    assert duplicate["request_id"] == first["request_id"]
    path = kaizen_host["root"] / "runtime/state/market-history-refresh-request.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "TESTUSDT"
    assert payload["execution_allowed"] is False
    assert not (path.parent / "virtual-market-refresh-request.json").exists()
    payload["status"] = "DATA_READY"
    payload["completed_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")
    status = module["kaizen_actions"](config)["job"]
    assert status["state"] == "COMPLETED"
    assert status["finding_present"] is True
    assert status["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "change",
    [
        {"confirmed": False},
        {"confirmed": 1},
        {"token": "0" * 64},
        {"symbol": "ALL"},
        {"market": "INVALID"},
        {"symbol": "../../test"},
        {"command": "TEST_ONLY_FORBIDDEN"},
    ],
)
def test_kaizen_rejects_unconfirmed_stale_and_arbitrary_targets(
    kaizen_host: dict[str, Any],
    change: dict[str, object],
) -> None:
    module, config = kaizen_host["module"], kaizen_host["config"]
    token = module["kaizen_actions"](config)["actions"][0]["token"]
    request = {
        "token": token,
        "confirmed": True,
        "market": "SPOT",
        "symbol": "TESTUSDT",
    }
    request.update(change)
    with pytest.raises(ValueError, match="KAIZEN_"):
        module["start_kaizen_action"](config, request)
    assert not (
        kaizen_host["root"] / "runtime/state/market-history-refresh-request.json"
    ).exists()


def test_kaizen_rechecks_finding_and_withholds_unsupported_service(
    kaizen_host: dict[str, Any],
) -> None:
    module, config = kaizen_host["module"], kaizen_host["config"]
    old = module["kaizen_actions"](config)["actions"][0]["token"]
    kaizen_host["observed"]["health_findings"][0]["evidence"] = "TEST_ONLY_CHANGED"
    with pytest.raises(ValueError, match="FINDING_UNAVAILABLE"):
        module["start_kaizen_action"](config, {"token": old, "confirmed": True})
    kaizen_host["observed"]["health_findings"] = [
        {"finding_id": "SERVICE_NOT_READY", "facts": {"service": "runtime"}}
    ]
    item = module["kaizen_actions"](config)["actions"][0]
    assert item["action"] is None
    with pytest.raises(ValueError, match="FINDING_UNAVAILABLE"):
        module["start_kaizen_action"](
            config, {"token": item["token"], "confirmed": True}
        )


def test_kaizen_learning_dispatch_does_not_invent_lessons(
    kaizen_host: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, config = kaizen_host["module"], kaizen_host["config"]
    kaizen_host["observed"]["health_findings"] = [
        {"finding_id": "LEARNING_SUMMARY_EMPTY"}
    ]
    calls = []

    def start(_config: dict[str, object], radar: str) -> dict[str, object]:
        calls.append(radar)
        return {"state": "RUNNING"}

    monkeypatch.setitem(kaizen_host["namespace"], "start_radar", start)
    monkeypatch.setitem(
        kaizen_host["namespace"], "radar_status", lambda *_: {"state": "COMPLETED"}
    )
    token = module["kaizen_actions"](config)["actions"][0]["token"]
    module["start_kaizen_action"](config, {"token": token, "confirmed": True})
    status = module["kaizen_actions"](config)["job"]
    assert calls == ["learning"]
    assert status["state"] == "COMPLETED"
    assert status["finding_present"] is True


def test_kaizen_http_requires_same_origin_and_explicit_confirmation(
    kaizen_host: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, config = kaizen_host["module"], kaizen_host["config"]
    config.update(port=0, installation_id="TEST_ONLY_KAIZEN")
    kaizen_host["observed"]["health_findings"] = [
        {"finding_id": "LEARNING_SUMMARY_EMPTY"}
    ]
    calls: list[str] = []

    def start(_config: dict[str, object], radar: str) -> dict[str, object]:
        calls.append(radar)
        return {"state": "RUNNING"}

    monkeypatch.setitem(kaizen_host["namespace"], "start_radar", start)
    server = module["create_server"](config)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        token = module["kaizen_actions"](config)["actions"][0]["token"]
        for origin, confirmed, expected in [
            ("https://example.invalid", True, 403),
            (None, False, 400),
            (None, True, 202),
        ]:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=5
            )
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            connection.request(
                "POST",
                "/api/kaizen/apply",
                json.dumps({"token": token, "confirmed": confirmed}),
                headers,
            )
            response = connection.getresponse()
            assert response.status == expected
            payload = json.loads(response.read())
            if expected == 202:
                assert payload["execution_allowed"] is False
                assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
            connection.close()
        assert calls == ["learning"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert not (kaizen_host["root"] / "runtime/state/learning_summary.json").exists()


def test_kaizen_restart_dispatch_is_fixed_to_canonical_market_history_owner(
    kaizen_host: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    module, config = kaizen_host["module"], kaizen_host["config"]
    namespace = kaizen_host["namespace"]
    kaizen_host["observed"]["health_findings"] = [
        {"finding_id": "SERVICE_NOT_READY", "facts": {"service": "market-history"}}
    ]
    calls = []

    def launch(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(poll=lambda: 0)

    monkeypatch.setitem(namespace, "os", SimpleNamespace(name="nt", replace=os.replace))
    monkeypatch.setattr(namespace["subprocess"], "Popen", launch)
    token = module["kaizen_actions"](config)["actions"][0]["token"]
    module["start_kaizen_action"](config, {"token": token, "confirmed": True})
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[-2:] == ["-Mode", "RestartMarketHistory"]
    assert command[command.index("-File") + 1] == str(
        kaizen_host["root"] / "scripts/install_startup_task.ps1"
    )
    assert kwargs["shell"] is False
    status = module["kaizen_actions"](config)["job"]
    assert status["state"] == "COMPLETED"
    assert status["finding_present"] is True


@pytest.mark.parametrize("observations", [None, {}, [], [None]])
def test_news_article_projection_withholds_missing_metadata(
    tmp_path: Path, observations: object
) -> None:
    result_path = tmp_path / "test-only-news.json"
    result_path.write_text(
        json.dumps({"report": {"observations": observations}}), encoding="utf-8"
    )
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    result = module["radar_result_summary"]("news", result_path)
    assert result["articles"] == []
    assert result["items"] == []


def test_news_article_projection_preserves_provenance_without_inventing_events(
    tmp_path: Path,
) -> None:
    observation = {
        "source_type": "NEWS_ARTICLE",
        "title": "Test-only public news title",
        "canonical_uri": "https://example.com/test-only-news",
        "published_at": "2026-10-12T12:00:00+00:00",
        "retrieved_at": "2026-10-12T13:00:00+00:00",
        "provider_id": "test-only-provider",
        "summary": "Test-only article text withheld from dashboard",
    }
    result_path = tmp_path / "test-only-news.json"
    result_path.write_text(
        json.dumps(
            {
                "status": "READY",
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                "report": {
                    "observations": [
                        observation,
                        {**observation, "source_type": "OFFICIAL_DOCUMENT"},
                    ],
                    "findings": [{"verification_status": "UNVERIFIED"}],
                },
            }
        ),
        encoding="utf-8",
    )
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    result = module["radar_result_summary"]("news", result_path)
    assert result["articles"] == [
        {
            key: value
            for key, value in observation.items()
            if key not in {"summary", "source_type"}
        }
    ]
    assert result["items"] == [
        {
            "asset": None,
            "symbol": None,
            "event_type": None,
            "claim": None,
            "verification_status": "UNVERIFIED",
            "confidence": None,
        }
    ]
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("count", "candidates", "expected"),
    [
        (0, [], "NO_CANDIDATES"),
        (1, [{}], "CANDIDATES_FOUND"),
        (True, [], "UNKNOWN"),
        (2, [], "UNKNOWN"),
    ],
)
def test_github_radar_projects_real_empty_results_without_invented_blockers(
    tmp_path: Path,
    count: object,
    candidates: list[dict[str, Any]],
    expected: str,
) -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    result_path = tmp_path / "test-only-github.json"
    result_path.write_text(
        json.dumps(
            {
                "mode": "GITHUB_DISCOVERY",
                "candidate_count": count,
                "candidates": candidates,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    result = module["radar_result_summary"]("github", result_path)
    assert result["result_status"] == expected
    assert result["blockers"] == (
        ["RADAR_RESULT_STATUS_UNAVAILABLE"] if expected == "UNKNOWN" else []
    )
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_radar_projection_preserves_nested_and_process_failure_blockers(
    tmp_path: Path,
) -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    module["radar_paths"].__globals__["APP"] = tmp_path
    radar = tmp_path / "radar"
    radar.mkdir()
    (radar / "web-status.json").write_text(
        json.dumps(
            {
                "state": "COMPLETED_WITH_BLOCKERS",
                "exit_code": 1,
            }
        ),
        encoding="utf-8",
    )
    (radar / "web-result.json").write_text(
        json.dumps(
            {
                "status": "DEGRADED",
                "blockers": ["LIVE_ORDER_BLOCKED"],
                "report": {
                    "blockers": ["TEST_ONLY_FETCH_FAILED", "LIVE_ORDER_BLOCKED"]
                },
            }
        ),
        encoding="utf-8",
    )
    result = module["radar_status"]({}, "web")
    assert result["state"] == "COMPLETED_WITH_BLOCKERS"
    assert result["result"]["result_status"] == "FAILED"
    assert result["result"]["items"] == []
    assert result["result"]["blockers"] == [
        "LIVE_ORDER_BLOCKED",
        "TEST_ONLY_FETCH_FAILED",
        "RADAR_PROCESS_FAILED",
    ]
    (radar / "web-status.json").write_text(
        json.dumps({"state": "RUNNING"}), encoding="utf-8"
    )
    orphaned = module["radar_status"]({}, "web")
    assert orphaned["state"] == "COMPLETED_WITH_BLOCKERS"
    assert orphaned["result"]["result_status"] == "UNVERIFIED"
    assert orphaned["result"]["blockers"] == ["RADAR_RUN_OWNERSHIP_UNVERIFIED"]


def test_dashboard_classifies_futures_research_progress_and_failures() -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    classify = module["futures_research_readiness_status"]

    assert classify({"status": "CURRENT", "blockers": []}) == "READY"
    assert classify({"status": "RUNNING", "blockers": []}) == "COLLECTING"
    assert classify({"status": "PROCESSED", "blockers": []}) == "COLLECTING"
    assert classify({"status": "WAITING_FOR_RETRY", "blockers": []}) == "COLLECTING"
    assert (
        classify({"status": "CURRENT_WITH_SOURCE_GAPS", "blockers": []}) == "DEGRADED"
    )
    assert classify({"status": "CURRENT", "blockers": ["SOURCE_GAP"]}) == "DEGRADED"


def test_virtual_market_separates_trade_records_from_potential_opportunities() -> None:
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")
    wallet = (ROOT / "src" / "ai4binance" / "virtual_wallet_journal.py").read_text(
        encoding="utf-8"
    )

    assert "if(virtual)return;" in views
    assert "potential opportunities" in views
    assert "commandOpportunitySymbolMatches(r,market)" in views
    assert "Virtual trade records" in views
    assert "payload.trade_records" in views
    assert "completeOpportunityPlan" in views
    assert "Entry / Stop / TP1 / TP2 / TP3 / R/R" in views
    assert "Opportunity generation health" in views
    assert "rejected_by_reason" in views
    assert "CANDIDATES_AVAILABLE_WITH_DATA_GAPS" in views
    assert "Published research opportunities remain visible" in views
    assert "Rejected attempts are diagnostic evidence, not opportunities" in views
    assert "has_complete_measurable_opportunity" in (
        SOURCE / "market_views.py.in"
    ).read_text(encoding="utf-8")
    assert '"generation_health"' in (SOURCE / "market_views.py.in").read_text(
        encoding="utf-8"
    )
    assert "def _dashboard_trade_records" in wallet
    assert "def _trade_record_dashboard_row" in wallet


def test_dashboard_exposes_virtual_runtime_preconditions_as_inactive() -> None:
    server = (SOURCE / "server.py.in").read_text(encoding="utf-8")
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")

    assert '"virtual_runtime_evaluated"' in server
    assert '"virtual_simulation_outcome"' in server
    assert '"risk_approved"' in server
    assert "commandVirtualSimulationView(market,daemon,projection,scope" in views
    assert "simulation.runtime_display" in views
    assert "simulation.risk_display" in views
    assert "Runtime evaluated" in views
    assert "Risk approved" in views


def test_dashboard_projects_auto_audit_movements_with_method_provenance() -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    project = module["auto_audit_observer_projection"]

    projected = project(
        {
            "status": "RUNNING_WITH_BLOCKERS",
            "loop_id": "auto-audit:42",
            "workflow_pattern": "HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER",
            "cycles": [
                {
                    "cycle_index": 1,
                    "observed_at": "2026-09-21T12:00:00+00:00",
                    "system_status": "DEGRADED",
                    "blocker_count": 1,
                    "new_blockers": ["DATA_STALE"],
                    "persistent_blockers": [],
                    "resolved_blockers": [],
                    "action_refs": ["resolve:DATA_STALE"],
                    "system_report_json_path": "runtime/reports/audit.json",
                    "continuous_assurance": {
                        "status": "RUNNING_WITH_BLOCKERS",
                        "route_decisions": [
                            {
                                "trigger_type": "SYSTEM_BLOCKER",
                                "storm_status": "ACCEPTED",
                                "event_id": "event:42",
                                "action_refs": ["run:lean-governance"],
                            }
                        ],
                    },
                }
            ],
        }
    )

    assert projected["movements"] == [
        {
            "cycle_index": 1,
            "observed_at": "2026-09-21T12:00:00+00:00",
            "system_status": "DEGRADED",
            "blocker_count": 1,
            "privacy_leak_status": None,
            "local_qwen_status": None,
            "new_blockers": ["DATA_STALE"],
            "persistent_blockers": [],
            "resolved_blockers": [],
            "action_refs": ["resolve:DATA_STALE"],
            "evidence_ref": "runtime/reports/audit.json",
        }
    ]
    assert projected["recommendations"] == [
        {
            "recommendation": "resolve:DATA_STALE",
            "method": "AUTO_AUDIT_LOOP",
            "method_result": "DEGRADED",
            "observed_at": "2026-09-21T12:00:00+00:00",
            "evidence_ref": "runtime/reports/audit.json",
        },
        {
            "recommendation": "run:lean-governance",
            "method": "CONTINUOUS_ASSURANCE:SYSTEM_BLOCKER",
            "method_result": "ACCEPTED",
            "observed_at": "2026-09-21T12:00:00+00:00",
            "evidence_ref": "event:42",
        },
    ]


def test_dashboard_rejects_auto_audit_artifact_with_execution_authority(
    tmp_path: Path,
) -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    artifact = tmp_path / "auto-audit-latest.json"
    artifact.write_text(
        json.dumps(
            {
                "execution_allowed": True,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                "cycles": [{"observed_at": datetime.now(UTC).isoformat()}],
            }
        ),
        encoding="utf-8",
    )

    meta, data = module["read_auto_audit_source"](
        artifact,
        86_400,
        now=datetime.now(UTC),
    )

    assert meta["status"] == "INVALID"
    assert data == {}


def test_market_selection_uses_current_manual_universe(tmp_path: Path) -> None:
    module = runpy.run_path(str(SOURCE / "market_views.py.in"))
    select = module["selection"]
    select.__globals__["Settings"] = lambda **_kwargs: SimpleNamespace(
        market_history_source_cache_directory=Path("runtime/data/market_sources"),
        market_history_manual_universe_path=Path(
            "config/research/manual_universe.yaml"
        ),
        symbol="BTCUSDT",
    )
    selection_path = tmp_path / "config/research/manual_universe.yaml"
    selection_path.parent.mkdir(parents=True)
    selection_path.write_text("spot_assets: [BTC]\n", encoding="utf-8")
    cache_path = tmp_path / "runtime/data/market_sources/universe-v3.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps(
            {
                "observed_at": datetime.now(UTC).isoformat(),
                "spot_symbols": ["BTCUSDT"],
                "futures_symbols": ["ETHUSDT"],
                "excluded_assets": [],
                "source": "BINANCE_WALLET_AND_MANUAL_RESEARCH_SELECTION",
                "manual_selection_sha256": _sha256(selection_path),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )

    assert select({"repository_root": str(tmp_path)}, "SPOT", "") == (
        tmp_path,
        ("BTCUSDT",),
        "BTCUSDT",
    )
    assert select({"repository_root": str(tmp_path)}, "USD_M_FUTURES", "") == (
        tmp_path,
        ("ETHUSDT",),
        "ETHUSDT",
    )
    selection_path.write_text("spot_assets: [SOL]\n", encoding="utf-8")
    assert select({"repository_root": str(tmp_path)}, "SPOT", "")[1:] == ((), "")


def test_market_quality_projection_validates_collector_age_and_counts(
    tmp_path: Path,
) -> None:
    module = runpy.run_path(str(SOURCE / "market_views.py.in"))
    project = module["universe_view"]
    now = datetime(2026, 9, 28, 12, tzinfo=UTC)
    state_path = tmp_path / "runtime/state/market-history-latest.json"
    state_path.parent.mkdir(parents=True)
    state = {
        "observed_at": now.isoformat(),
        "status": "COLLECTING",
        "collector_coverage": {
            "SPOT": [
                {
                    "timeframe": timeframe,
                    "universe_count": 2,
                    "current_count": 1,
                    "invalid_count": 0,
                    "unavailable_count": 0,
                    "refresh_required_count": 0,
                    "pending_count": 1,
                }
                for timeframe in module["MARKET_TIMEFRAMES"]["SPOT"]
            ]
        },
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    settings = SimpleNamespace(market_history_live_interval_seconds=300)

    current = project(tmp_path, settings, "SPOT", ("BTCUSDT", "ETHUSDT"), now)
    assert current["quality_status"] == "COLLECTING"
    assert current["quality"][0]["current_count"] == 1
    assert current["quality"][0]["pending_count"] == 1
    assert current["quality"][0]["stale_count"] is None
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")
    assert "Window gaps" in views
    assert "Dataset gaps" in views
    assert "Warnings" in views
    assert "collector_observed_at" in views
    assert "dataset_sha256" in views

    state["observed_at"] = (now - timedelta(minutes=16)).isoformat()
    state["status"] = "READY"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    stale = project(tmp_path, settings, "SPOT", ("BTCUSDT", "ETHUSDT"), now)
    assert stale["quality_status"] == "DATA_UNAVAILABLE"
    assert stale["collector_stale"] is True
    assert stale["quality"][0]["current_count"] is None

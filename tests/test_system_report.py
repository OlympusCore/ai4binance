"""Whole-system operator report tests."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.cli import main
from ai4binance.config import Settings
from ai4binance.enterprise import GpuResourceGovernor, GpuTelemetrySnapshot
from ai4binance.ops import system_report as system_report_module
from ai4binance.ops.system_report import (
    SystemReportResult,
    build_system_report,
    local_advisory_health_payload,
    runtime_state_payload,
    startup_health_payload,
    startup_replay_payload,
    system_report_summary_payload,
)

NOW = datetime(2026, 8, 3, 10, 30, tzinfo=UTC)


def test_startup_health_accepts_fresh_running_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "runtime" / "state"
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

    payload = startup_health_payload(settings, NOW)

    assert payload["status"] == "READY"
    assert payload["blockers"] == ()
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_startup_health_reports_missing_and_stale_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "runtime" / "state"
    _write_health(state_dir, "runtime", NOW)
    stale = datetime(2026, 8, 3, 10, 20, tzinfo=UTC)
    _write_health(state_dir, "accounting", stale)

    payload = startup_health_payload(settings, NOW)

    assert payload["status"] == "DEGRADED"
    blockers = payload["blockers"]
    assert isinstance(blockers, tuple)
    assert "ACCOUNTING_STATE_STALE" in blockers
    assert "ACCOUNTING_WS_STATE_MISSING" in blockers
    assert "SKILL_DISCOVERY_STATE_MISSING" in blockers
    assert "VIRTUAL_MARKET_STATE_MISSING" in blockers


def test_startup_replay_payload_reports_empty_journal_without_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    payload = startup_replay_payload(settings)

    assert payload["status"] == "READY"
    assert payload["blockers"] == ()
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    replay = payload["replay"]
    assert isinstance(replay, dict)
    assert replay["journal_exists"] is False
    assert replay["event_count"] == 0
    assert replay["replayed_event_count"] == 0
    assert replay["replay_from_sequence"] == 1
    assert replay["lifecycle_stage"] is None


def test_startup_replay_payload_blocks_on_corrupt_journal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    journal_path = settings.audit_directory / "live-order-lifecycle.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text("not-json", encoding="utf-8")

    payload = startup_replay_payload(settings)

    assert payload["status"] == "DEGRADED"
    assert payload["blockers"] == ("STARTUP_REPLAY_JOURNAL_INVALID",)
    assert payload["execution_allowed"] is False
    replay = payload["replay"]
    assert isinstance(replay, dict)
    assert replay["blockers"] == ("STARTUP_REPLAY_JOURNAL_INVALID",)


def test_runtime_state_payload_handles_missing_and_invalid_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    missing = runtime_state_payload(settings, NOW)
    assert missing["status"] == "DEGRADED"
    assert missing["blockers"] == ("RUNTIME_REPORT_UNAVAILABLE",)

    settings.runtime_state_path.parent.mkdir(parents=True, exist_ok=True)
    settings.runtime_state_path.write_text("[1, 2, 3]", encoding="utf-8")

    invalid = runtime_state_payload(settings, NOW)
    assert invalid["status"] == "DEGRADED"
    assert invalid["blockers"] == ("RUNTIME_REPORT_INVALID",)


def test_runtime_state_payload_reports_controlled_learning_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    settings.runtime_state_path.parent.mkdir(parents=True, exist_ok=True)
    settings.runtime_state_path.write_text(
        json.dumps(
            {
                "cycle_id": "runtime-1",
                "symbol": "HOTUSDT",
                "created_at": NOW.isoformat(),
                "state": "READY",
                "blockers": [],
                "health": {
                    "status": "HEALTHY",
                    "last_attempt_at": NOW.isoformat(),
                    "last_success_at": NOW.isoformat(),
                    "consecutive_failures": 0,
                },
                "controlled_learning": {
                    "status": "READY",
                    "summary_id": "learning:test",
                    "lesson_count": 1,
                    "experiment_count": 1,
                    "execution_allowed": False,
                    "risk_change_allowed": False,
                    "promotion_status": "RESEARCH_ONLY",
                },
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )

    payload = runtime_state_payload(settings, NOW)

    learning = payload["controlled_learning"]
    assert isinstance(learning, dict)
    assert learning["summary_id"] == "learning:test"
    assert learning["lesson_count"] == 1
    assert learning["execution_allowed"] is False


def test_local_advisory_health_requires_loopback_llama_qwen_and_prompter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "runtime" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "qwen-prompter-health.json").write_text(
        json.dumps(
            {
                "service": "qwen-prompter",
                "provider": "llama.cpp",
                "status": "RUNNING",
                "model": "qwen3:8b",
                "endpoint": "http://127.0.0.1:8080",
                "pid": os.getpid(),
                "provider_pid": os.getpid(),
                "listener_pids": [os.getpid()],
                "auto_learn": {
                    "status": "RUNNING",
                    "mode": "RESEARCH_ONLY",
                    "engine": {
                        "provider": "llama.cpp",
                        "model": "qwen3:8b",
                        "runtime": "llama.cpp",
                    },
                    "capabilities": [
                        "observe",
                        "analyze",
                        "extract_lessons",
                        "detect_patterns",
                        "generate_hypotheses",
                        "propose_experiments",
                        "propose_improvements",
                    ],
                    "authority": {
                        "modify_runtime": False,
                        "modify_strategy": False,
                        "modify_parameters": False,
                        "modify_risk_limits": False,
                        "promote_strategy": False,
                        "authorize_execution": False,
                        "deploy_code": False,
                    },
                    "promotion": {"human_approval_required": True},
                    "execution": {"live_execution": False},
                    "learning": {
                        "model_weight_update": False,
                        "external_memory": True,
                        "evidence_registry": True,
                        "lesson_registry": True,
                        "experiment_registry": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = local_advisory_health_payload(settings)

    assert payload["status"] == "READY"
    assert payload["provider"] == "llama.cpp"
    assert payload["model"] == "qwen3:8b"
    assert payload["blockers"] == ()
    auto_learn = payload["auto_learn"]
    assert isinstance(auto_learn, dict)
    assert auto_learn["status"] == "RUNNING"
    assert auto_learn["mode"] == "RESEARCH_ONLY"
    assert auto_learn["engine"]["provider"] == "llama.cpp"
    assert auto_learn["authority"]["promote_strategy"] is False
    assert auto_learn["learning"]["external_memory"] is True
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_local_advisory_health_prefers_enabled_primary_local_reasoning_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "runtime" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "primary-local-reasoning-health.json").write_text(
        json.dumps(
            {
                "service": "primary-local-reasoning",
                "provider": "llama.cpp",
                "status": "RUNNING",
                "runtime_model": "qwen3:8b",
                "endpoint": "http://127.0.0.1:8080",
                "listener_pids": [os.getpid()],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "qwen-prompter-health.json").write_text(
        json.dumps({"status": "STARTING", "endpoint": ""}), encoding="utf-8"
    )

    payload = local_advisory_health_payload(settings)

    assert payload["status"] == "READY"
    assert payload["health_source_service"] == "primary-local-reasoning"
    assert payload["prompter_pid"] == os.getpid()
    assert payload["blockers"] == ()


def test_system_report_persists_secret_safe_json_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_at = datetime.now(UTC)
    settings = _settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        GpuResourceGovernor,
        "collect_telemetry",
        lambda self: GpuTelemetrySnapshot.unavailable(source="unit-test"),
    )
    state_dir = tmp_path / "runtime" / "state"
    for service in (
        "runtime",
        "virtual-market",
        "accounting",
        "accounting-ws",
        "skill-discovery",
        "market-history",
        "futures-multitf",
    ):
        _write_health(state_dir, service, observed_at)
    (state_dir / "runtime.json").write_text(
        json.dumps(
            {
                "created_at": observed_at.isoformat(),
                "state": "DEGRADED",
                "health": {"status": "DEGRADED", "consecutive_failures": 0},
                "blockers": ["PORTFOLIO_COST_BASIS_UNAVAILABLE"],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _stub_components(monkeypatch)

    result = build_system_report(
        settings, observed_at=observed_at, workspace_root=tmp_path
    )

    assert result.payload["status"] == "RUNNING_WITH_BLOCKERS"
    telemetry_assessment = result.payload["telemetry_assessment"]
    assert isinstance(telemetry_assessment, dict)
    assert telemetry_assessment["source_label"] == "unit-test"
    assert telemetry_assessment["healthy"] is False
    assert telemetry_assessment["blockers"] == ["CUDA_UNAVAILABLE"]
    blockers = result.payload["blockers"]
    assert isinstance(blockers, tuple)
    assert "runtime:PORTFOLIO_COST_BASIS_UNAVAILABLE" in blockers
    components = result.payload["components"]
    assert isinstance(components, dict)
    assert "advanced_agent_contract" in components
    assert "startup_replay" in components
    startup_replay = components["startup_replay"]
    assert isinstance(startup_replay, dict)
    assert startup_replay["status"] == "READY"
    assert startup_replay["execution_allowed"] is False
    contract = result.payload["advanced_agent_operating_contract"]
    assert isinstance(contract, dict)
    assert contract["status"] == "READY"
    assert "FAIL_CLOSED_DEFAULTS" in contract["guardrails"]
    assert result.payload["execution_allowed"] is False
    assert result.payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert result.markdown_path.exists()
    assert result.json_path.exists()
    assert result.json_path == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "system_audit"
        / f"system-report-{observed_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    assert result.latest_json_path == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "system_audit"
        / "system-report-latest.json"
    )
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "- Healthy: `False`" in markdown
    assert "- Source: `unit-test`" in markdown
    persisted = result.json_path.read_text(encoding="utf-8")
    assert "advanced_agent_operating_contract" in persisted
    assert "telemetry_assessment" in persisted
    assert "PORTFOLIO_COST_BASIS_UNAVAILABLE" in persisted
    assert "BINANCE_API_SECRET" not in persisted
    assert "total_wallet_balance" not in persisted


def test_system_report_cli_renders_text_and_returns_blocked_status(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = SystemReportResult(
        payload={
            "command": "system-report",
            "status": "RUNNING_WITH_BLOCKERS",
            "telemetry_assessment": {
                "healthy": False,
                "source_label": "unit-test",
                "blockers": ("CUDA_UNAVAILABLE",),
            },
            "components": {
                "runtime": {
                    "status": "RUNNING_WITH_BLOCKERS",
                    "blockers": ("RUNTIME_DEGRADED",),
                },
                "local_advisory": {
                    "status": "READY",
                    "blockers": (),
                    "auto_learn": {
                        "status": "RUNNING",
                        "mode": "RESEARCH_ONLY",
                        "engine": {
                            "provider": "llama.cpp",
                            "model": "qwen3:8b",
                        },
                    },
                },
            },
            "blockers": ("runtime:RUNTIME_DEGRADED",),
            "markdown_path": str(tmp_path / "report.md"),
            "json_path": str(tmp_path / "report.json"),
            "advanced_agent_operating_contract": {
                "status": "READY",
                "orchestration": "MULTI_STEP_WORKFLOWS",
                "execution_scope": "END_TO_END_OPERATIONS",
                "guardrails": ("FAIL_CLOSED_DEFAULTS",),
                "human_approval_controls": {
                    "gates": ("TRADING_SCOPE",),
                },
            },
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        markdown_path=tmp_path / "report.md",
        json_path=tmp_path / "report.json",
        latest_json_path=tmp_path / "latest.json",
    )
    monkeypatch.setattr("ai4binance.cli.build_system_report", lambda settings: result)

    assert main(["system-report", "--format", "text"]) == 2

    output = capsys.readouterr().out
    assert "System report" in output
    assert "RUNNING_WITH_BLOCKERS" in output
    assert "advanced_agent_contract: READY" in output
    assert "FAIL_CLOSED_DEFAULTS" in output
    assert "- telemetry_assessment: False unit-test ['CUDA_UNAVAILABLE']" in output
    assert (
        "auto_learn: RUNNING mode=RESEARCH_ONLY provider=llama.cpp model=qwen3:8b"
        in output
    )
    assert "LIVE_ORDER_BLOCKED" in output


def test_system_report_summary_keeps_interactive_payload_bounded(
    tmp_path: Path,
) -> None:
    result = SystemReportResult(
        payload={
            "command": "system-report",
            "report_id": "report-1",
            "observed_at": NOW,
            "status": "RUNNING_WITH_BLOCKERS",
            "telemetry_assessment": {
                "healthy": False,
                "source_label": "unit-test",
                "blockers": ("CUDA_UNAVAILABLE",),
            },
            "components": {
                "validation": {
                    "status": "RESEARCH_ONLY",
                    "blockers": ("WEAK_OOS",),
                    "large_details": "x" * 100_000,
                }
            },
            "advanced_agent_operating_contract": {
                "status": "READY",
                "orchestration": "MULTI_STEP_WORKFLOWS",
                "automation_scope": "REPETITIVE_OPERATIONS",
                "execution_scope": "END_TO_END_OPERATIONS",
                "guardrails": ("FAIL_CLOSED_DEFAULTS",),
                "auditable_traceability": ("AUDIT_LOGS",),
                "human_approval_controls": {
                    "mode": "HUMAN_IN_THE_LOOP",
                    "required_at": "CRITICAL_DECISION_POINTS",
                    "gates": ("TRADING_SCOPE",),
                },
                "large_details": "y" * 100_000,
            },
            "blockers": ("validation:WEAK_OOS",),
        },
        markdown_path=tmp_path / "report.md",
        json_path=tmp_path / "report.json",
        latest_json_path=tmp_path / "latest.json",
    )

    summary = system_report_summary_payload(result)

    encoded = json.dumps(summary, default=str)
    assert "large_details" not in encoded
    assert len(encoded) < 2_000
    contract = summary["advanced_agent_operating_contract"]
    assert isinstance(contract, dict)
    assert contract["status"] == "READY"
    assert contract["human_approval_controls"]["gates"] == ("TRADING_SCOPE",)
    dashboard_cards = summary["dashboard_cards"]
    assert isinstance(dashboard_cards, dict)
    assert dashboard_cards["source"] == "system-report"
    assert dashboard_cards["metric_count"] == 5
    assert "contract_guardrails" in dashboard_cards["blocked_metric_ids"]
    telemetry = summary["telemetry_assessment"]
    assert isinstance(telemetry, dict)
    assert telemetry["source_label"] == "unit-test"
    assert summary["details"] == "FULL_EVIDENCE_PERSISTED_TO_JSON"


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_STATE_PATH",
        str(tmp_path / "runtime" / "state" / "runtime.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_SKILL_DISCOVERY_STATE_PATH",
        str(tmp_path / "runtime" / "state" / "skill_discovery.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(tmp_path / "Accounting")
    )
    monkeypatch.setenv("AI4BINANCE_AUDIT_DIRECTORY", str(tmp_path / "logs"))
    monkeypatch.setenv(
        "AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY", str(tmp_path / "Validation")
    )
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    return Settings()


def _write_health(state_dir: Path, service: str, observed_at: datetime) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    lock_name = {
        "skill-discovery": "skill_discovery.lock",
        "market-history": "market-history-latest.lock",
    }.get(service, f"{service}.lock")
    (state_dir / lock_name).write_text(str(pid), encoding="ascii")
    (state_dir / f"{service}-health.json").write_text(
        json.dumps(
            {
                "service": service,
                "status": "RUNNING",
                "updated_at": observed_at.isoformat(),
                "pid": pid,
                "child_pid": 0,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    useful_state = {
        "virtual-market": ("virtual-market.json", "last_success_at"),
        "market-history": ("market-history-latest.json", "observed_at"),
    }.get(service)
    if useful_state is not None:
        filename, timestamp_field = useful_state
        (state_dir / filename).write_text(
            json.dumps({timestamp_field: observed_at.isoformat()}, sort_keys=True),
            encoding="utf-8",
        )


def _stub_components(monkeypatch: pytest.MonkeyPatch) -> None:
    safe = {
        "status": "PASSED",
        "blockers": (),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    monkeypatch.setattr(
        system_report_module,
        "_load_cli_component_builders",
        lambda: (
            lambda settings, observed_at: safe,
            lambda settings: {
                **safe,
                "status": "REVIEW_REQUIRED",
                "blockers": ("SIX_SIGMA_TARGET_DPMO_NOT_MET",),
            },
            lambda settings, symbol: safe,
            lambda: safe,
            lambda: safe,
            lambda settings, symbol: {
                **safe,
                "status": "RESEARCH_ONLY",
                "blockers": ("UNSTABLE_PARAMETER_SENSITIVITY",),
            },
        ),
    )
    monkeypatch.setattr(
        system_report_module, "audit_oek_constitution", lambda root: safe
    )
    monkeypatch.setattr(
        system_report_module, "read_skill_discovery_status", lambda settings: safe
    )

"""Whole-system operator report tests."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request

import pytest

from ai4binance.cli import main
from ai4binance.config import Settings
from ai4binance.ops import system_report as system_report_module
from ai4binance.ops.system_report import (
    SystemReportResult,
    build_system_report,
    local_advisory_health_payload,
    runtime_state_payload,
    startup_health_payload,
    system_report_summary_payload,
)

NOW = datetime(2026, 8, 3, 10, 30, tzinfo=UTC)


class _ResponseStub:
    def __enter__(self) -> "_ResponseStub":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, limit: int) -> bytes:
        assert limit == 1024 * 1024
        return b'{"models":[{"name":"qwen3:8b"}]}'


def test_startup_health_accepts_fresh_running_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "State"
    for service in ("runtime", "accounting", "accounting-ws", "skill-discovery"):
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
    state_dir = tmp_path / "State"
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


def test_local_advisory_health_requires_loopback_ollama_qwen_and_prompter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "State"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "qwen-prompter-health.json").write_text(
        json.dumps(
            {
                "service": "qwen-prompter",
                "status": "RUNNING",
                "model": "qwen3:8b",
                "pid": os.getpid(),
            }
        ),
        encoding="utf-8",
    )

    def fake_urlopen(request: Request, timeout: float) -> _ResponseStub:
        assert request.full_url == "http://127.0.0.1:11434/api/tags"
        assert timeout == 3.0
        return _ResponseStub()

    monkeypatch.setattr(
        "ai4binance.ops.system_report.urllib.request.urlopen", fake_urlopen
    )

    payload = local_advisory_health_payload(settings)

    assert payload["status"] == "READY"
    assert payload["provider"] == "ollama"
    assert payload["model"] == "qwen3:8b"
    assert payload["blockers"] == ()
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_system_report_persists_secret_safe_json_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_at = datetime.now(UTC)
    settings = _settings(monkeypatch, tmp_path)
    state_dir = tmp_path / "State"
    for service in ("runtime", "accounting", "accounting-ws", "skill-discovery"):
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
    blockers = result.payload["blockers"]
    assert isinstance(blockers, tuple)
    assert "runtime:PORTFOLIO_COST_BASIS_UNAVAILABLE" in blockers
    assert result.payload["execution_allowed"] is False
    assert result.payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert result.markdown_path.exists()
    assert result.json_path.exists()
    persisted = result.json_path.read_text(encoding="utf-8")
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
            "components": {
                "runtime": {
                    "status": "RUNNING_WITH_BLOCKERS",
                    "blockers": ("RUNTIME_DEGRADED",),
                }
            },
            "blockers": ("runtime:RUNTIME_DEGRADED",),
            "markdown_path": str(tmp_path / "report.md"),
            "json_path": str(tmp_path / "report.json"),
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
            "components": {
                "validation": {
                    "status": "RESEARCH_ONLY",
                    "blockers": ("WEAK_OOS",),
                    "large_details": "x" * 100_000,
                }
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
    assert summary["details"] == "FULL_EVIDENCE_PERSISTED_TO_JSON"


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_STATE_PATH", str(tmp_path / "State" / "runtime.json")
    )
    monkeypatch.setenv(
        "AI4BINANCE_SKILL_DISCOVERY_STATE_PATH",
        str(tmp_path / "State" / "skill-discovery.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(tmp_path / "Accounting")
    )
    monkeypatch.setenv(
        "AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY", str(tmp_path / "Validation")
    )
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    return Settings()


def _write_health(state_dir: Path, service: str, observed_at: datetime) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    (state_dir / f"{service}.lock").write_text(str(pid), encoding="ascii")
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

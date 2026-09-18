from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.config import Settings
from ai4binance.ops.auto_audit_loop import AutoAuditLoop, run_auto_audit_loop
from ai4binance.ops.continuous_assurance import (
    AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
    EAACIE_INSTRUCTION_REFS,
    AuditTriggerType,
    ContinuousAuditEvent,
    SecurityAuditTriggerType,
    SecurityDomain,
)
from ai4binance.ops.system_report import SystemReportResult
from ai4binance.rag import AdvisoryProviderResult, RagSearchHit


class FakeQwenRunner:
    def __init__(self, response: str | None = None) -> None:
        self.response = response or (
            "RESEARCH_ONLY\n"
            "LIVE_ORDER_BLOCKED\n"
            "BULGU: blocker trendi izlenebilir.\n"
            "DIFF: otomatik yetki verilmedi.\n"
            "TEST: evidence raporu incelenmeli.\n"
            "BLOCKER: human review gerekli."
        )
        self.calls = 0

    def run(
        self,
        prompt: str,
        hits: tuple[RagSearchHit, ...],
    ) -> AdvisoryProviderResult:
        assert "Never authorize signals" in prompt
        assert hits == ()
        self.calls += 1
        return AdvisoryProviderResult(
            provider="ollama",
            model="qwen3:8b",
            prompt_sha256=sha256(prompt.encode("utf-8")).hexdigest(),
            response_text=self.response,
            citations=(),
            blockers=("ADVISORY_ONLY",),
        )


def test_auto_audit_loop_tracks_blocker_movement_and_persists_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    observed = _clock(datetime(2026, 8, 8, 12, 0, tzinfo=UTC))
    reports = iter(
        (
            _report(
                tmp_path,
                "one",
                "RUNNING_WITH_BLOCKERS",
                ("runtime:RUNTIME_DEGRADED", "opportunities:NO_READY_CANDIDATE"),
            ),
            _report(
                tmp_path,
                "two",
                "RUNNING_WITH_BLOCKERS",
                ("runtime:RUNTIME_DEGRADED", "validation:OOS_APPROVAL_MISSING"),
            ),
        )
    )

    result = AutoAuditLoop(
        settings=settings,
        repository_root=tmp_path,
        report_builder=lambda settings, **kwargs: next(reports),
        sleep=lambda seconds: None,
    ).run(
        max_cycles=2,
        interval_seconds=0,
        observed_at_factory=lambda: next(observed),
    )

    assert result.status == "RUNNING_WITH_BLOCKERS"
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert result.cycles[0].new_blockers == (
        "opportunities:NO_READY_CANDIDATE",
        "runtime:RUNTIME_DEGRADED",
    )
    assert result.cycles[1].persistent_blockers == ("runtime:RUNTIME_DEGRADED",)
    assert result.cycles[1].resolved_blockers == ("opportunities:NO_READY_CANDIDATE",)
    assert result.cycles[1].new_blockers == ("validation:OOS_APPROVAL_MISSING",)
    assert result.json_path.exists()
    assert result.latest_json_path.exists()
    assert result.markdown_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["workflow_pattern"] == "HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER"
    kaizen = payload["kaizen_quality_snapshot"]
    assert kaizen["status"] == "RUNNING_WITH_BLOCKERS"
    assert kaizen["execution_allowed"] is False
    assert kaizen["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert kaizen["full_gate_command"] == ".\\scripts\\quality.ps1"
    kaizen_signals = {item["blocker"]: item for item in kaizen["blocker_signals"]}
    assert kaizen_signals["runtime:RUNTIME_DEGRADED"]["state"] == "PERSISTENT"
    assert "ENFORCEMENT_INVENTORY_UNAVAILABLE" in " ".join(kaizen["blockers"])
    assert payload["cycles"][1]["execution_allowed"] is False
    continuous = payload["cycles"][1]["continuous_assurance"]
    assert continuous["instruction_ref"] == AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF
    assert continuous["instruction_refs"] == list(EAACIE_INSTRUCTION_REFS)
    assert continuous["workflow_pattern"] == (
        "ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP"
    )
    assert continuous["execution_allowed"] is False
    assert continuous["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert any(
        "PARAMETER_GOVERNANCE" in decision["domains"]
        for decision in continuous["route_decisions"]
    )
    security_audit = continuous["security_audit"]
    assert security_audit["enabled"] is True
    assert security_audit["trigger_types"] == [
        SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK.value
    ]
    assert set(security_audit["domains"]) == {domain.value for domain in SecurityDomain}
    assert security_audit["automatic_remediation"] is False
    assert security_audit["execution_allowed"] is False
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "## Kaizen Quality" in markdown
    assert "kaizen_quality" in markdown
    assert "closure_gate" in markdown
    assert "technical_quality_status" in markdown
    assert "governance_closure_status" in markdown
    assert "governance_approval" in markdown
    assert (
        "class=UNKNOWN; status=NOT_VERIFIED; approvals=0/0; hard_veto=true" in markdown
    )
    assert "acceptance_status" in markdown
    assert "instruction_baseline" in markdown
    assert "instruction_context_benchmark" in markdown
    assert "token_status=TOKEN_ESTIMATE" in markdown
    assert "blocker_evidence" in markdown
    assert "runtime:RUNTIME_DEGRADED|PERSISTENT|system-report:runtime" in markdown
    assert "tests/test_kaizen_quality.py tests/test_auto_audit_loop.py" in markdown
    assert AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF in markdown
    for instruction_ref in EAACIE_INSTRUCTION_REFS:
        assert instruction_ref in markdown
    assert "SCHEDULED_DAILY_QUICK" in markdown
    assert "PRIVACY, ACCESS, SECRETS, APPSEC" in markdown


def test_auto_audit_loop_loads_matched_current_gate_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_current_gate_artifacts(tmp_path, subject_sha256="a" * 64)
    reports = iter((_report(tmp_path, "current-gates", "READY", ()),))

    result = AutoAuditLoop(
        settings=settings,
        repository_root=tmp_path,
        report_builder=lambda settings, **kwargs: next(reports),
        sleep=lambda seconds: None,
    ).run(
        max_cycles=1,
        interval_seconds=0,
        observed_at_factory=lambda: datetime(2026, 9, 3, tzinfo=UTC),
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    closure_gate = payload["kaizen_quality_snapshot"]["closure_gate"]
    assert closure_gate["technical_quality_status"] == "TECHNICAL_QUALITY_PASS"
    assert closure_gate["governance_closure_status"] == "GOVERNANCE_CLOSURE_PASS"
    assert closure_gate["governance_approval_evidence"] == {
        "change_class": "C0_NON_BEHAVIORAL",
        "status": "NOT_REQUIRED",
        "required_approval_count": 0,
        "observed_approval_count": 0,
        "hard_veto": False,
        "blockers": [],
    }
    assert not any(
        blocker.startswith("CURRENT_GATE_EVIDENCE")
        for blocker in closure_gate["blockers"]
    )


def test_auto_audit_loop_can_use_local_qwen_without_execution_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    (tmp_path / "src" / "ai4binance" / "ops").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "ops" / "auto_audit_loop.py").write_text(
        "LIVE_ORDER_BLOCKED = True\n",
        encoding="utf-8",
    )
    qwen = FakeQwenRunner()

    result = run_auto_audit_loop(
        settings,
        repository_root=tmp_path,
        max_cycles=1,
        interval_seconds=0,
        use_local_qwen=True,
        qwen_runner=qwen,
        report_builder=lambda settings, **kwargs: _report(
            tmp_path,
            "qwen",
            "READY",
            (),
        ),
        sleep=lambda seconds: None,
    )

    assert qwen.calls == 1
    assert result.status == "READY"
    assert result.cycles[0].local_qwen_status == "READY"
    assert result.cycles[0].local_qwen_report_path is not None
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_auto_audit_loop_surfaces_privacy_leaks_through_dge_remediation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    public_report = tmp_path / "runtime" / "reports" / "ykb" / "ykb_report.md"
    public_report.parent.mkdir(parents=True)
    public_report.write_text(
        "mailadresim: owner@example.com\nBinanceWallet: spot-main\n",
        encoding="utf-8",
    )

    result = run_auto_audit_loop(
        settings,
        repository_root=tmp_path,
        max_cycles=1,
        interval_seconds=0,
        report_builder=lambda settings, **kwargs: _report(
            tmp_path,
            "privacy",
            "READY",
            (),
        ),
        sleep=lambda seconds: None,
    )

    cycle = result.cycles[0]
    assert result.status == "RUNNING_WITH_BLOCKERS"
    assert "privacy:KVKK_PUBLIC_PRIVACY_LEAK" in cycle.blockers
    assert cycle.privacy_leak_status == "BLOCKED"
    assert cycle.privacy_leak_findings == (
        "runtime/reports/ykb/ykb_report.md:EMAIL_ADDRESS_PUBLIC_LEAK",
        "runtime/reports/ykb/ykb_report.md:KVKK_PERSONAL_DATA_PUBLIC_LEAK",
        "runtime/reports/ykb/ykb_report.md:BINANCE_WALLET_IDENTIFIER_PUBLIC_LEAK",
    )
    assert cycle.privacy_dge_decision_id.startswith("dge:")
    assert "dge-privacy-remediation:" in " ".join(cycle.action_refs)
    assert "classify_control_in_blocker_registry" in (
        cycle.privacy_dge_required_changes
    )
    assert "restore_execution_feasibility_evidence" in (
        cycle.privacy_dge_required_changes
    )
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_auto_audit_loop_routes_performance_snapshots_into_continuous_assurance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    observed = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

    def performance_events(snapshot: object) -> tuple[ContinuousAuditEvent, ...]:
        del snapshot
        return (
            ContinuousAuditEvent(
                event_id="performance-drift:snapshot-1",
                trigger_type=AuditTriggerType.PERFORMANCE_DRIFT,
                entity_type="CANONICAL_TELEMETRY",
                entity_id="snapshot-1",
                observed_at=observed,
                evidence_refs=("decision-telemetry:snapshot-1",),
                root_cause_key="telemetry:snapshot-1",
            ),
        )

    monkeypatch.setattr(
        "ai4binance.ops.auto_audit_loop.events_from_performance_evidence_snapshot",
        performance_events,
    )

    result = run_auto_audit_loop(
        settings,
        repository_root=tmp_path,
        max_cycles=1,
        interval_seconds=0,
        performance_snapshots=cast(tuple[Any, ...], (object(),)),
        report_builder=lambda settings, **kwargs: _report(
            tmp_path,
            "performance",
            "READY",
            (),
        ),
        sleep=lambda seconds: None,
    )

    continuous = result.cycles[0].continuous_assurance_plan
    assert continuous is not None
    payload = continuous.to_payload()
    route_domains = {
        domain
        for decision in cast(list[dict[str, object]], payload["route_decisions"])
        for domain in cast(list[str], decision["domains"])
    }
    assert "PERFORMANCE_ENGINEERING" in route_domains
    assert continuous.execution_allowed is False
    assert continuous.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_auto_audit_loop_degrades_on_invalid_local_qwen_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    (tmp_path / "src" / "ai4binance" / "ops").mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "ops" / "auto_audit_loop.py").write_text(
        "RESEARCH_ONLY = True\n",
        encoding="utf-8",
    )

    result = run_auto_audit_loop(
        settings,
        repository_root=tmp_path,
        max_cycles=1,
        interval_seconds=0,
        use_local_qwen=True,
        qwen_runner=FakeQwenRunner(response="Eksik guvenlik damgasi."),
        report_builder=lambda settings, **kwargs: _report(
            tmp_path,
            "bad-qwen",
            "READY",
            (),
        ),
        sleep=lambda seconds: None,
    )

    assert result.status == "DEGRADED"
    assert result.cycles[0].local_qwen_status == "BLOCKED"
    assert "LOCAL_QWEN_SAFETY_STAMP_MISSING" in result.cycles[0].local_qwen_blockers
    assert result.execution_allowed is False


def test_auto_audit_cli_command_is_registered_and_report_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance import cli

    settings = _settings(monkeypatch, tmp_path)
    expected = run_auto_audit_loop(
        settings,
        repository_root=tmp_path,
        max_cycles=1,
        interval_seconds=0,
        report_builder=lambda settings, **kwargs: _report(
            tmp_path,
            "cli",
            "RUNNING_WITH_BLOCKERS",
            ("runtime:RUNTIME_DEGRADED",),
        ),
        sleep=lambda seconds: None,
    )
    monkeypatch.setattr(cli, "run_auto_audit_loop", lambda settings, **kwargs: expected)

    exit_code = cli.main(["auto-audit-once", "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["command"] == "auto-audit-loop"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_auto_audit_loop_rejects_invalid_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    loop = AutoAuditLoop(settings=settings, repository_root=tmp_path)

    with pytest.raises(ValueError, match="max_cycles"):
        loop.run(max_cycles=0)
    with pytest.raises(ValueError, match="interval"):
        loop.run(interval_seconds=-1)


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_STATE_PATH",
        str(tmp_path / "state" / "runtime.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_SKILL_DISCOVERY_STATE_PATH",
        str(tmp_path / "state" / "skill_discovery.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY",
        str(tmp_path / "Accounting"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY",
        str(tmp_path / "Validation"),
    )
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    return Settings()


def _report(
    root: Path,
    name: str,
    status: str,
    blockers: tuple[str, ...],
) -> SystemReportResult:
    report_dir = root / "reports" / "operations"
    artifact_dir = root / "runtime" / "artifacts" / "system_audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / f"SYSTEM_REPORT_{name}.md"
    json_path = artifact_dir / f"system-report-{name}.json"
    latest_json_path = artifact_dir / "system-report-latest.json"
    markdown_path.write_text("# report\n", encoding="utf-8")
    json_path.write_text("{}", encoding="utf-8")
    latest_json_path.write_text("{}", encoding="utf-8")
    payload: dict[str, object] = {
        "command": "system-report",
        "report_id": f"system-report:{name}",
        "observed_at": datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        "status": status,
        "components": {
            "runtime": {
                "status": status,
                "blockers": blockers,
            }
        },
        "advanced_agent_operating_contract": {
            "status": "READY",
            "guardrails": ("FAIL_CLOSED_DEFAULTS",),
            "human_approval_controls": {"gates": ("TRADING_SCOPE",)},
        },
        "blockers": blockers,
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "latest_json_path": str(latest_json_path),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    return SystemReportResult(payload, markdown_path, json_path, latest_json_path)


def _write_current_gate_artifacts(root: Path, *, subject_sha256: str) -> None:
    gate_directory = root / "runtime" / "artifacts" / "quality" / "gate"
    gate_directory.mkdir(parents=True, exist_ok=True)
    shared_safety = {
        "subject_digest": {"subject_sha256": subject_sha256},
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    quality_payload = {
        **shared_safety,
        "status": "PASS",
        "quality_evidence_gate": {
            "quality_gate": {
                "status": "TECHNICAL_QUALITY_PASS",
                "pytest_pass_count": 1,
            }
        },
    }
    governance_payload = {
        **shared_safety,
        "status": "PASS",
        "deterministic_gate_resolver": {"decision": "PASS"},
        "approval_verification": {
            "change_class": "C0_NON_BEHAVIORAL",
            "status": "NOT_REQUIRED",
            "required_approval_count": 0,
            "observed_approval_count": 0,
            "hard_veto": False,
            "blockers": [],
        },
        "blockers": [],
    }
    (gate_directory / "deterministic_quality_gate_latest.json").write_text(
        json.dumps(quality_payload), encoding="utf-8"
    )
    (gate_directory / "governance_gate_latest.json").write_text(
        json.dumps(governance_payload), encoding="utf-8"
    )


def _clock(start: datetime) -> Iterator[datetime]:
    current = start
    while True:
        yield current
        current += timedelta(seconds=1)

"""Enterprise reports expose input failures and cannot acquire authority."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from ai4binance.cli import enterprise as cli
from ai4binance.enterprise import quality_audit as audit
from ai4binance.reporting import to_primitive
from tests.test_enterprise_quality_audit import evidence


@pytest.mark.parametrize(
    ("mode", "blocker"),
    [("missing", "UNAVAILABLE"), ("large", "TOO_LARGE"), ("empty", "INTAKE_REJECTED")],
)
def test_intake_rejects_unusable_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str, blocker: str
) -> None:
    path = tmp_path / "prompt.txt"
    if mode != "missing":
        path.write_text("x" * 16001 if mode == "large" else "", encoding="utf-8")
    assert cli.run_enterprise_intake(prompt_file=str(path), output_format="json") == 2
    payload = json.loads(capsys.readouterr().out)
    assert any(blocker in item for item in payload["blockers"])
    assert payload["execution_allowed"] is False


@pytest.mark.parametrize(
    "kind", ["intake", "directive", "quality", "stack", "cleanup", "oek"]
)
def test_cli_rejects_non_object_report_serialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    original = to_primitive
    calls = 0

    def malformed(value: object) -> object:
        nonlocal calls
        calls += 1
        return original(value) if kind == "directive" and calls == 1 else []

    monkeypatch.setattr(cli, "to_primitive", malformed)
    monkeypatch.setattr(cli, "run_quality_system_audit", lambda *args: None)
    monkeypatch.setattr(cli, "run_agent_stack_audit", lambda *args: None)
    monkeypatch.setattr(cli, "run_repository_cleanup_audit", lambda *args: None)
    monkeypatch.setattr(cli, "analyze_oek_change_gap", lambda *args: None)
    path = tmp_path / "change.json"
    path.write_text(
        json.dumps(
            {
                "change_id": "change-1",
                "change_kind": "SKILL",
                "subject_ref": "skill:review",
                "changed_paths": ["skills/review"],
                "summary": "Review only",
                "evidence_refs": ["test"],
                "declared_controls": ["LIVE_ORDER_BLOCKED"],
            }
        )
    )

    def invoke() -> None:
        if kind in {"intake", "directive"}:
            cli.enterprise_intake_payload("Review local evidence")
        elif kind == "quality":
            cli.quality_system_audit_payload()
        elif kind == "stack":
            cli.agent_stack_audit_payload()
        elif kind == "cleanup":
            cli.repository_cleanup_audit_payload()
        else:
            cli.oek_gap_analysis_payload(str(path))

    with pytest.raises(RuntimeError, match="PAYLOAD_INVALID"):
        invoke()


@pytest.mark.parametrize("value", ["invalid", []])
def test_manifest_rejects_wrong_list_shapes(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="list of strings"):
        cli._string_tuple(value)


def test_cleanup_command_preserves_read_only_report(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "run_repository_cleanup_audit", lambda root: {"status": "READY"}
    )
    assert cli.run_repository_cleanup_audit_command(output_format="json") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "READY"
    assert report["execution_allowed"] is False


@pytest.fixture(scope="module")
def audit_subjects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    ev = evidence(tmp_path_factory.mktemp("audit"), ())
    report = audit.run_quality_system_audit(ev)
    check = audit.QualitySystemAuditCheck("check", "subject", True, ("evidence",))
    return {"evidence": ev, "report": report, "check": check}


@pytest.mark.parametrize(
    ("kind", "changes", "message"),
    [
        ("evidence", {"observed_at": datetime(2026, 9, 1)}, "timezone-aware"),
        ("evidence", {"command_names": ("",)}, "blanks"),
        ("evidence", {"command_names": ("same", "same")}, "unique"),
        ("evidence", {"execution_allowed": True}, "authorize"),
        ("evidence", {"live_eligibility_status": "LIVE"}, "authorize"),
        ("check", {"check_id": ""}, "empty"),
        ("check", {"execution_allowed": True}, "authorize"),
        ("check", {"promotion_status": "LIVE"}, "promote"),
        ("check", {"live_eligibility_status": "LIVE"}, "blocked"),
        ("report", {"checks": ()}, "requires checks"),
        ("report", {"status": audit.QualitySystemAuditStatus.PASSED}, "status"),
        ("report", {"execution_allowed": True}, "authorize"),
        ("report", {"promotion_status": "LIVE"}, "promote"),
        ("report", {"live_eligibility_status": "LIVE"}, "blocked"),
    ],
)
def test_audit_contracts_reject_invalid_authority(
    audit_subjects: dict[str, Any], kind: str, changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(audit_subjects[kind], **changes)


def test_missing_governance_surface_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audit, "lint_skill_manifest", None)
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    check = audit._audit_agentic_governance_surfaces()
    assert not check.passed
    assert "AGENTIC_GOVERNANCE_SURFACE_MISSING:model-adaptation-board" in check.blockers
    assert "AGENTIC_GOVERNANCE_SURFACE_MISSING:skill-linter" in check.blockers


def test_missing_quality_gate_is_not_green(tmp_path: Path) -> None:
    check = audit._audit_quality_gate_green(tmp_path, ())
    assert not check.passed
    assert "QUALITY_GATE_SCRIPT_MISSING" in check.blockers
    assert "QUALITY_GATE_COMMAND_UNREGISTERED" in check.blockers
    assert "QUALITY_GATE_GOVERNANCE_GATE_MISSING" in check.blockers
    assert "QUALITY_GATE_LIVE_BLOCKED_BOUNDARY_MISSING" in check.blockers

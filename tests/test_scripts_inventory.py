"""Read-only scripts inventory and kaizen baseline tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ai4binance.ops as ops
from ai4binance.ops.scripts_inventory import (
    build_scripts_inventory_report,
    main,
    persist_scripts_inventory_report,
)

NOW = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)


def test_scripts_inventory_api_is_exposed_from_ops_package() -> None:
    assert ops.build_scripts_inventory_report is build_scripts_inventory_report


def test_scripts_inventory_classifies_scripts_and_preserves_fail_closed_authority(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "quality.ps1").write_text(
        """
param([string]$Profile = "full")
function Invoke-SharedThing {
    $artifact = "runtime\\quality\\latest.json"
    Set-Content -LiteralPath $artifact -Value "{}"
    $status = "PASS"
}
function Invoke-OtherThing {
    $artifact = "runtime\\quality\\latest.json"
    Set-Content -LiteralPath $artifact -Value "{}"
}
& .\\cleanup_generated_artifacts.ps1
""",
        encoding="utf-8",
    )
    (scripts / "cleanup_generated_artifacts.ps1").write_text(
        """
param([switch]$Apply)
function Remove-GeneratedStuff {
    $artifact = "runtime\\quality\\latest.json"
    Set-Content -LiteralPath $artifact -Value "{}"
    $status = "PASS"
    Remove-Item -LiteralPath "runtime\\tmp\\x" -Recurse -Force
}
""",
        encoding="utf-8",
    )
    (scripts / "install_startup_task.ps1").write_text(
        """
function Register-Task {
    Register-ScheduledTask -TaskName "AI4B" -Action $action
}
""",
        encoding="utf-8",
    )

    report = build_scripts_inventory_report(
        tmp_path,
        duplicate_block_size=3,
        clock=NOW,
    )

    assert report.status == "INVENTORIED"
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.script_count == 3
    assert report.top_by_lines[0].path == "scripts/quality.ps1"
    assert report.risk_summary["destructive_capability_count"] == 1
    assert report.risk_summary["task_scheduler_capability_count"] == 1
    assert report.risk_summary["runtime_artifact_writer_count"] == 2
    assert report.script_call_graph["scripts/quality.ps1"] == (
        "scripts/cleanup_generated_artifacts.ps1",
    )
    assert report.duplicate_blocks
    assert any(
        "shared orchestration into Python" in action
        for action in report.recommended_next_actions
    )


def test_scripts_inventory_persists_verified_json_and_cli_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "speak.ps1").write_text('Write-Output "ok"', encoding="utf-8")
    output = tmp_path / "runtime" / "artifacts" / "scripts_kaizen" / "latest.json"
    report = build_scripts_inventory_report(tmp_path, clock=NOW)

    persist_scripts_inventory_report(report, output)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["status"] == "INVENTORIED"
    assert persisted["script_count"] == 1
    assert persisted["execution_allowed"] is False

    exit_code = main(
        (
            "--repository-root",
            str(tmp_path),
            "--output",
            str(output),
        )
    )
    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 0
    assert summary == {
        "duplicate_block_count": 0,
        "evidence_path": "runtime/artifacts/scripts_kaizen/latest.json",
        "script_count": 1,
        "status": "INVENTORIED",
        "top_script": "scripts/speak.ps1",
        "total_lines": 1,
    }


def test_inventory_includes_extensionless_git_hooks(tmp_path: Path) -> None:
    hook = tmp_path / "scripts/git-hooks/pre-commit"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    report = build_scripts_inventory_report(tmp_path)
    assert [item.path for item in report.entries] == ["scripts/git-hooks/pre-commit"]
    assert report.status == "INVENTORIED"


def test_inventory_templates_bind_exact_bytes_and_reject_invalid_text(
    tmp_path: Path,
) -> None:
    import hashlib

    script = tmp_path / "scripts/local_dashboard/launch.ps1.in"
    script.parent.mkdir(parents=True)
    raw = b'\xef\xbb\xbfWrite-Output "test-only"\r\n'
    script.write_bytes(raw)
    entry = build_scripts_inventory_report(tmp_path).entries[0]
    assert entry.path == "scripts/local_dashboard/launch.ps1.in"
    assert entry.extension == ".ps1"
    assert entry.bytes == len(raw)
    assert entry.sha256 == hashlib.sha256(raw).hexdigest()
    script.write_bytes(b"\xffinvalid")
    with pytest.raises(UnicodeDecodeError):
        build_scripts_inventory_report(tmp_path)

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is required for script hygiene tests")
    return executable


def _copy_script(root: Path, script_name: str) -> None:
    scripts = root / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copy2(Path("scripts") / script_name, scripts / script_name)


def _run_script(root: Path, *args: str) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / "optimize_windows_ai4binance.ps1"),
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def test_windows_optimization_script_reports_repo_candidates(tmp_path: Path) -> None:
    _copy_script(tmp_path, "optimize_windows_ai4binance.ps1")
    for relative_path in ("artifacts", "runtime", "state", ".venv"):
        (tmp_path / relative_path).mkdir(parents=True, exist_ok=True)

    payload = _run_script(
        tmp_path,
        "-SkipPowerPlan",
        "-SkipLongPaths",
        "-SkipDefenderExclusion",
    )

    assert payload["command"] == "optimize-windows-ai4binance"
    assert payload["applied"] is False
    assert payload["indexing_candidate_count"] == 4
    assert payload["indexing_optimization"] == "RECOMMENDED"
    assert payload["power_plan"] == "SKIPPED"
    assert payload["long_paths"] == "SKIPPED"
    assert payload["defender_exclusion"] == "SKIPPED"
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["preferred_time_zone"] == "Europe/Istanbul"
    assert payload["assistant_profile"]["provider"] == "llama.cpp"
    assert (
        payload["assistant_profile"]["endpoint"] == "http://127.0.0.1:8080/completion"
    )
    assert payload["assistant_profile"]["prompt_timezone"] == "Europe/Istanbul"
    assert payload["assistant_profile"]["timeout_seconds"] == 180
    assert payload["assistant_profile"]["history_turns"] == 4
    assert (
        payload["assistant_profile"]["response_style"]
        == "Direct, practical, recommendation-oriented"
    )
    assert (
        payload["assistant_profile"]["response_order"]
        == "Answer first, then brief rationale, then next action"
    )
    assert (
        payload["assistant_profile"]["clarifying_question_policy"]
        == "At most one concise question when necessary"
    )


def test_windows_optimization_script_applies_indexing_only_changes(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "optimize_windows_ai4binance.ps1")
    target = tmp_path / "runtime"
    target.mkdir(parents=True, exist_ok=True)
    (target / "marker.txt").write_text("runtime", encoding="utf-8")

    payload = _run_script(
        tmp_path,
        "-Apply",
        "-SkipPowerPlan",
        "-SkipLongPaths",
        "-SkipDefenderExclusion",
    )

    assert payload["applied"] is True
    assert payload["indexing_candidate_count"] == 1
    assert payload["indexing_optimization"] in {"APPLIED", "ALREADY_OPTIMAL"}
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_windows_optimization_script_is_fail_closed_and_repo_scoped() -> None:
    text = (Path("scripts") / "optimize_windows_ai4binance.ps1").read_text(
        encoding="utf-8"
    )

    assert 'command                    = "optimize-windows-ai4binance"' in text
    assert (
        '$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path'
        in text
    )
    assert '"LIVE_ORDER_BLOCKED"' in text
    assert '"RESEARCH_ONLY"' in text
    assert "execution_allowed          = $false" in text
    assert '"Turbo"' in text
    assert '"THIRD_PARTY_AV_PRESENT_MANUAL_REVIEW_REQUIRED"' in text
    assert '"BLOCKED_ADMIN_REQUIRED"' in text
    assert '"Europe/Istanbul"' in text
    assert "assistant_profile" in text
    assert 'prompt_timezone = "Europe/Istanbul"' in text
    assert "timeout_seconds = 180" in text
    assert 'response_style = "Direct, practical, recommendation-oriented"' in text
    assert (
        'response_order = "Answer first, then brief rationale, then next action"'
        in text
    )
    assert (
        'clarifying_question_policy = "At most one concise question when necessary"'
        in text
    )

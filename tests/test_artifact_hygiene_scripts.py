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


def _run_cleanup_script(root: Path, *args: str) -> dict[str, Any]:
    command = [
        _powershell(),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / "Scripts" / "cleanup_generated_artifacts.ps1"),
        *args,
    ]
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _copy_cleanup_script(root: Path) -> None:
    scripts = root / "Scripts"
    scripts.mkdir()
    source = Path("Scripts") / "cleanup_generated_artifacts.ps1"
    shutil.copy2(source, scripts / "cleanup_generated_artifacts.ps1")


def test_cleanup_generated_artifacts_coverage_mode_dry_run_and_apply(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    (tmp_path / ".coverage").write_text("stale", encoding="utf-8")
    (tmp_path / ".coverage.worker").write_text("stale", encoding="utf-8")
    (tmp_path / "coverage.xml").write_text("<coverage />", encoding="utf-8")
    htmlcov = tmp_path / "htmlcov"
    htmlcov.mkdir()
    (htmlcov / "index.html").write_text("<html></html>", encoding="utf-8")

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "Coverage")

    assert dry_run["applied"] is False
    assert dry_run["modes"] == ["Coverage"]
    assert dry_run["candidate_count"] == 4
    assert dry_run["execution_allowed"] is False
    assert dry_run["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {".coverage", ".coverage.worker", "coverage.xml", "htmlcov"}

    applied = _run_cleanup_script(tmp_path, "-Mode", "Coverage", "-Apply")

    assert applied["applied"] is True
    assert applied["applied_count"] == 4
    assert not (tmp_path / ".coverage").exists()
    assert not (tmp_path / ".coverage.worker").exists()
    assert not (tmp_path / "coverage.xml").exists()
    assert not htmlcov.exists()


def test_cleanup_generated_artifacts_cache_mode_includes_pytest_cache(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    for cache_name in (".mypy_cache", ".ruff_cache", ".pytest_cache", ".test-tmp"):
        cache = tmp_path / cache_name
        cache.mkdir()
        (cache / "marker.txt").write_text("cache", encoding="utf-8")

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "Caches")

    assert dry_run["applied"] is False
    assert dry_run["modes"] == ["Caches"]
    assert dry_run["candidate_count"] == 4
    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {".mypy_cache", ".ruff_cache", ".pytest_cache", ".test-tmp"}

    applied = _run_cleanup_script(tmp_path, "-Mode", "Caches", "-Apply")

    assert applied["applied"] is True
    assert applied["applied_count"] == 4
    for cache_name in (".mypy_cache", ".ruff_cache", ".pytest_cache", ".test-tmp"):
        assert not (tmp_path / cache_name).exists()


def test_quality_script_isolates_coverage_artifacts() -> None:
    text = (Path("Scripts") / "quality.ps1").read_text(encoding="utf-8")

    assert "Remove-GeneratedCoverageArtifacts" in text
    assert "Invoke-GeneratedArtifactCleanup" in text
    assert "cleanup_generated_artifacts.ps1" in text
    assert '-Mode @("Caches", "Coverage")' in text
    assert "$env:COVERAGE_FILE = $coverageFile" in text
    assert '".coverage"' in text
    assert "Artifacts\\TestTemp" in text


def test_cleanup_script_acl_force_is_bounded_to_test_temp() -> None:
    text = (Path("Scripts") / "cleanup_generated_artifacts.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$ForceAcl" in text
    assert "Assert-InTestTempPath" in text
    assert "Test-IsWindowsAdministrator" in text
    assert "Grant-TestTempCleanupAccess" in text
    assert "STALE_TEST_TEMP" in text
    assert "Refusing ACL-forced cleanup outside Artifacts\\TestTemp" in text
    assert "FORCE_ACL_REQUIRES_ELEVATED_POWERSHELL" in text
    assert "Remove-Item -LiteralPath $source -Recurse -Force" in text


def test_qwen_prompter_startup_task_is_visible_and_advisory_only() -> None:
    install_text = (
        Path("Scripts") / "install_qwen_prompter_startup_task.ps1"
    ).read_text(encoding="utf-8")
    prompter_text = (Path("Scripts") / "start_qwen_prompter.ps1").read_text(
        encoding="utf-8"
    )
    status_text = (Path("Scripts") / "startup_status.ps1").read_text(encoding="utf-8")

    assert 'qwen3:8b"' in install_text
    assert "AI4BINANCE-Qwen3-Prompter" in install_text
    assert "New-ScheduledTaskTrigger -AtLogOn" in install_text
    assert "-File" in install_text
    assert "-NoExit" not in install_text
    assert "-NonInteractive" not in install_text
    assert "-Hidden" not in install_text
    assert "visible_prompt = $true" in install_text
    assert 'AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"' in prompter_text
    assert 'AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"' in prompter_text
    assert 'AI4BINANCE_ORDER_AUTHORITY = "BLOCKED"' in prompter_text
    assert 'AI4BINANCE_RISK_AUTHORITY = "BLOCKED"' in prompter_text
    assert 'AI4BINANCE_LIVE_AUTHORITY = "BLOCKED"' in prompter_text
    assert "LIVE_ORDER_BLOCKED" in prompter_text
    assert "New-SystemPrompt" in prompter_text
    assert "Docs\\READ_ONLY_RUNTIME.md" in prompter_text
    assert "State\\runtime.json" in prompter_text
    assert "Artifacts\\market-outlook\\runtime-state.json" in prompter_text
    assert "http://127.0.0.1:11434/api/chat" in prompter_text
    assert "Invoke-OllamaChat" in prompter_text
    assert "Start-Job" in prompter_text
    assert "Start-Sleep -Seconds 30" in prompter_text
    assert "System.Net.Http.HttpClient" in prompter_text
    assert "System.Net.Http.StringContent" in prompter_text
    assert '"application/json"' in prompter_text
    assert "Private state and Secrets are out of scope" in prompter_text
    assert "Read-Host" in prompter_text
    assert "RequireQwenPrompterTask" in status_text
    assert "AI4BINANCE-Qwen3-Prompter" in status_text
    assert "qwen-prompter-health.json" in status_text

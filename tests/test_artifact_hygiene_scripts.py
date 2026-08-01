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

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

pytestmark = [
    pytest.mark.governance,
    pytest.mark.script_subprocess,
    pytest.mark.runtime_io,
    pytest.mark.slow,
]

ROOT = Path(__file__).resolve().parents[1]
QUALITY_HARNESS_TIMEOUT_SECONDS = 120
QUALITY_HARNESS_CLEANUP_GRACE_SECONDS = 5
EXTERNAL_HELPER_TIMEOUT_SECONDS = 120


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is required for script hygiene tests")
    return executable


def _quality_script_text() -> str:
    return (Path("scripts") / "quality.ps1").read_text(encoding="utf-8")


def _quality_function_preamble() -> str:
    text = _quality_script_text()
    marker = "New-Item -ItemType Directory -Path $qualityGateArtifactDirectory"
    preamble, separator, _ = text.partition(marker)
    assert separator == marker
    assert "function Write-QualityGateGreenEvidence" in preamble
    assert "function Invoke-QualityGate" in preamble
    return preamble


def _write_quality_harness(tmp_path: Path, body: str) -> Path:
    harness_dir = tmp_path / "scripts"
    harness_dir.mkdir(exist_ok=True)
    harness_path = harness_dir / "quality_harness.ps1"
    python_path = Path(".venv") / "Scripts" / "python.exe"
    coverage_reader = Path("scripts") / "read_coverage_percent.py"
    harness_path.write_text(
        "\n".join(
            [
                _quality_function_preamble().replace(
                    '. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")',
                    ". '"
                    + str(
                        ROOT / "scripts" / "initialize_runtime_environment.ps1"
                    ).replace("'", "''")
                    + "'",
                ),
                "$python = @'",
                str(python_path.resolve()),
                "'@",
                "$coverageReaderScript = @'",
                str(coverage_reader.resolve()),
                "'@",
                body,
            ]
        ),
        encoding="utf-8",
    )
    return harness_path


def _find_quality_harness_processes(harness_path: Path) -> list[dict[str, Any]]:
    escaped_path = str(harness_path).replace("\\", "\\\\").replace("'", "''")
    command = (
        "$path = '" + escaped_path + "'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { "
        "$_.ProcessId -ne $PID -and "
        "$_.CommandLine -like ('*' + $path + '*') "
        "} | "
        "Select-Object ProcessId, ParentProcessId, Name | "
        "ConvertTo-Json -Compress"
    )
    completed = subprocess.run(  # noqa: S603
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        return []
    payload = json.loads(stdout)
    if isinstance(payload, dict):
        payload = [payload]
    assert isinstance(payload, list)
    return [cast(dict[str, Any], item) for item in payload]


def _kill_process_tree(pid: int) -> None:
    taskkill = Path(r"C:\Windows\System32\taskkill.exe")
    completed = subprocess.run(  # noqa: S603
        [str(taskkill), "/PID", str(pid), "/T", "/F"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in (0, 128, 255):
        raise AssertionError(
            "taskkill failed for process tree "
            f"{pid}: {(completed.stderr or completed.stdout).strip()}"
        )


def _list_descendant_processes(
    root_pid: int,
    *,
    created_after_utc: str | None = None,
) -> list[dict[str, Any]]:
    created_after_clause = ""
    created_after_predicate = ""
    if created_after_utc is not None:
        escaped_timestamp = created_after_utc.replace("'", "''")
        created_after_clause = (
            "$createdAfter = [datetime]::Parse('"
            + escaped_timestamp
            + "').ToUniversalTime(); "
        )
        created_after_predicate = (
            " -and "
            "[System.Management.ManagementDateTimeConverter]::ToDateTime("
            "$_.CreationDate"
            ").ToUniversalTime() -ge $createdAfter"
        )
    command = (
        "$root = "
        + str(root_pid)
        + "; "
        + created_after_clause
        + "$all = Get-CimInstance Win32_Process; "
        "$pending = @($root); "
        "$results = New-Object System.Collections.Generic.List[object]; "
        "while ($pending.Count -gt 0) { "
        "  $current = $pending[0]; "
        "  if ($pending.Count -eq 1) { "
        "    $pending = @() "
        "  } else { "
        "    $pending = $pending[1..($pending.Count - 1)] "
        "  }; "
        "  $children = @($all | Where-Object { $_.ParentProcessId -eq $current"
        + created_after_predicate
        + " }); "
        "  foreach ($child in $children) { "
        "    $results.Add([pscustomobject]@{ "
        "      ProcessId = $child.ProcessId; "
        "      ParentProcessId = $child.ParentProcessId; "
        "      Name = $child.Name; "
        "      CreationDateUtc = "
        "[System.Management.ManagementDateTimeConverter]::ToDateTime("
        "$child.CreationDate"
        ").ToUniversalTime().ToString('o') "
        "    }); "
        "    $pending += $child.ProcessId; "
        "  } "
        "} "
        "$results | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(  # noqa: S603
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        return []
    payload = json.loads(stdout)
    if isinstance(payload, dict):
        payload = [payload]
    assert isinstance(payload, list)
    return [cast(dict[str, Any], item) for item in payload]


def _wait_for_process_tree_to_exit(
    root_pid: int,
    *,
    created_after_utc: str | None = None,
    timeout_seconds: float = QUALITY_HARNESS_CLEANUP_GRACE_SECONDS,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        descendants = _list_descendant_processes(
            root_pid,
            created_after_utc=created_after_utc,
        )
        if not descendants:
            return []
        if time.monotonic() >= deadline:
            return descendants
        time.sleep(0.1)


def _wait_for_quality_harness_processes_to_exit(
    harness_path: Path,
    *,
    timeout_seconds: float = QUALITY_HARNESS_CLEANUP_GRACE_SECONDS,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        leaked_processes = _find_quality_harness_processes(harness_path)
        if not leaked_processes:
            return []
        if time.monotonic() >= deadline:
            return leaked_processes
        time.sleep(0.1)


def _run_external_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: int = EXTERNAL_HELPER_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    process: subprocess.Popen[str] | None = None
    process_started_at_utc: str | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".stdout.txt",
            delete=False,
        ) as stdout_handle:
            stdout_path = Path(stdout_handle.name)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".stderr.txt",
                delete=False,
            ) as stderr_handle:
                stderr_path = Path(stderr_handle.name)
                try:
                    process_started_at_utc = datetime.now(UTC).isoformat()
                    process = subprocess.Popen(  # noqa: S603
                        command,
                        cwd=cwd,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        text=True,
                    )
                    returncode = process.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    if process is not None:
                        _kill_process_tree(process.pid)
                        leaked_processes = _wait_for_process_tree_to_exit(
                            process.pid,
                            created_after_utc=process_started_at_utc,
                        )
                    else:
                        leaked_processes = []
                    pytest.fail(
                        "external helper timed out after "
                        f"{timeout_seconds} seconds and was force-cleaned; "
                        f"command={command!r}; remaining_processes={leaked_processes}"
                    )
                finally:
                    if process is not None and process.poll() is None:
                        _kill_process_tree(process.pid)
        if process is not None:
            leaked_processes = _wait_for_process_tree_to_exit(
                process.pid,
                created_after_utc=process_started_at_utc,
            )
            if leaked_processes:
                for leaked_process in leaked_processes:
                    _kill_process_tree(int(leaked_process["ProcessId"]))
                pytest.fail(
                    "external helper left leaked processes after completion: "
                    f"command={command!r}; leaked_processes={leaked_processes}"
                )
        return subprocess.CompletedProcess(
            args=command,
            returncode=returncode,
            stdout=stdout_path.read_text(encoding="utf-8") if stdout_path else "",
            stderr=stderr_path.read_text(encoding="utf-8") if stderr_path else "",
        )
    finally:
        if stdout_path and stdout_path.exists():
            stdout_path.unlink()
        if stderr_path and stderr_path.exists():
            stderr_path.unlink()


def _run_cleanup_script(root: Path, *args: str) -> dict[str, Any]:
    command = [
        _powershell(),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / "scripts" / "cleanup_generated_artifacts.ps1"),
        *args,
    ]
    completed = _run_external_command(command, cwd=root)
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _run_powershell_script(
    root: Path,
    script_name: str,
    *args: str,
    script_root: Path | None = None,
) -> dict[str, Any]:
    command = [
        _powershell(),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str((script_root or root) / "scripts" / script_name),
        *args,
    ]
    completed = _run_external_command(command, cwd=root)
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _run_python_script(root: Path, script_name: str, *args: str) -> dict[str, Any]:
    python_path = ROOT / ".venv" / "Scripts" / "python.exe"
    completed = _run_external_command(
        [str(python_path), str(root / "scripts" / script_name), *args],
        cwd=root,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _run_quality_harness_command(
    tmp_path: Path,
    harness_path: Path,
    *args: str,
    timeout_seconds: int = QUALITY_HARNESS_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    stdout_path = harness_path.with_suffix(".stdout.txt")
    stderr_path = harness_path.with_suffix(".stderr.txt")
    command = [
        _powershell(),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(harness_path),
        *args,
    ]
    process: subprocess.Popen[str] | None = None
    with stdout_path.open("w", encoding="utf-8") as stdout_handle:
        with stderr_path.open("w", encoding="utf-8") as stderr_handle:
            try:
                process = subprocess.Popen(  # noqa: S603
                    command,
                    cwd=tmp_path,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                )
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                if process is not None:
                    _kill_process_tree(process.pid)
                leaked_processes = _wait_for_quality_harness_processes_to_exit(
                    harness_path
                )
                pytest.fail(
                    "quality harness timed out after "
                    f"{timeout_seconds} seconds and was force-cleaned; "
                    f"remaining processes={leaked_processes}"
                )
            finally:
                if process is not None and process.poll() is None:
                    _kill_process_tree(process.pid)

    leaked_processes = _wait_for_quality_harness_processes_to_exit(harness_path)
    if leaked_processes:
        for leaked_process in leaked_processes:
            _kill_process_tree(int(leaked_process["ProcessId"]))
        pytest.fail(
            "quality harness left leaked processes after completion: "
            f"{leaked_processes}"
        )

    return subprocess.CompletedProcess(
        args=command,
        returncode=returncode,
        stdout=stdout_path.read_text(encoding="utf-8"),
        stderr=stderr_path.read_text(encoding="utf-8"),
    )


def _run_quality_function_harness(tmp_path: Path, body: str) -> dict[str, Any]:
    harness_path = _write_quality_harness(tmp_path, body)
    completed = _run_quality_harness_command(tmp_path, harness_path)
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    json_start = completed.stdout.find("{")
    assert json_start >= 0
    payload = json.loads(completed.stdout[json_start:])
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _run_quality_function_harness_process(
    tmp_path: Path,
    body: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    harness_path = _write_quality_harness(tmp_path, body)
    return _run_quality_harness_command(tmp_path, harness_path, *args)


def _copy_cleanup_script(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir()
    source = Path("scripts") / "cleanup_generated_artifacts.ps1"
    shutil.copy2(source, scripts / "cleanup_generated_artifacts.ps1")
    manifest_destination = (
        root / "config" / "governance" / "runtime_artifact_layout_manifest.json"
    )
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        Path("config") / "governance" / "runtime_artifact_layout_manifest.json",
        manifest_destination,
    )


def _copy_script(root: Path, script_name: str) -> None:
    scripts = root / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copy2(Path("scripts") / script_name, scripts / script_name)


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
    for cache_name in (
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".test-tmp",
        ".tmp",
        ".tmp-alias-check",
    ):
        cache = tmp_path / cache_name
        cache.mkdir()
        (cache / "marker.txt").write_text("cache", encoding="utf-8")

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "Caches")

    assert dry_run["applied"] is False
    assert dry_run["modes"] == ["Caches"]
    assert dry_run["candidate_count"] == 6
    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".test-tmp",
        ".tmp",
        ".tmp-alias-check",
    }

    applied = _run_cleanup_script(tmp_path, "-Mode", "Caches", "-Apply")

    assert applied["applied"] is True
    assert applied["applied_count"] == 6
    for cache_name in (
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".test-tmp",
        ".tmp",
        ".tmp-alias-check",
    ):
        assert not (tmp_path / cache_name).exists()


def test_cleanup_generated_artifacts_directory_cleanup_is_non_interactive() -> None:
    text = (Path("scripts") / "cleanup_generated_artifacts.ps1").read_text(
        encoding="utf-8"
    )

    assert "Remove-ReparsePointChildren" in text
    assert "-Confirm:$false" in text
    assert '$command = "rmdir $quotedPath"' in text
    assert (
        "Remove-Item -LiteralPath $Path -Recurse "
        "-Force -ErrorAction Stop -Confirm:$false" in text
    )


def test_cleanup_generated_artifacts_source_generated_mode_dry_run(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    package = tmp_path / "src" / "ai4binance"
    pycache = package / "__pycache__"
    pycache.mkdir(parents=True)
    pyc = pycache / "module.cpython-312.pyc"
    pyc.write_bytes(b"\0\0")
    direct_pyc = package / "compiled.pyc"
    direct_pyc.write_bytes(b"\0\0")
    egg_info = tmp_path / "src" / "ai4binance.egg-info"
    egg_info.mkdir()
    metadata = egg_info / "PKG-INFO"
    metadata.write_text("Metadata-Version: 2.1\n", encoding="utf-8")
    debug_workspace = tmp_path / "runtime" / "tmp" / "debug_trace_gate"
    debug_workspace.mkdir(parents=True)
    (debug_workspace / "README.md").write_text("debug", encoding="utf-8")

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "SourceGenerated")

    assert dry_run["applied"] is False
    assert dry_run["modes"] == ["SourceGenerated"]
    assert dry_run["candidate_count"] == 4
    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {
        "src/ai4binance/__pycache__",
        "src/ai4binance/compiled.pyc",
        "src/ai4binance.egg-info",
        "runtime/tmp/debug_trace_gate",
    }
    assert pyc.exists()
    assert direct_pyc.exists()
    assert metadata.exists()
    assert debug_workspace.exists()
    assert dry_run["execution_allowed"] is False
    assert dry_run["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_cleanup_generated_artifacts_source_generated_mode_removes_debug_tmp(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    debug_workspace = tmp_path / "runtime" / "tmp" / "debug-trace-gate"
    debug_workspace.mkdir(parents=True)
    (debug_workspace / "README.md").write_text("debug", encoding="utf-8")

    applied = _run_cleanup_script(tmp_path, "-Mode", "SourceGenerated", "-Apply")

    assert applied["applied"] is True
    assert applied["applied_count"] == 1
    assert not debug_workspace.exists()


def test_import_mirror_inventory_script_copies_valid_manifest(
    tmp_path: Path,
) -> None:
    source_manifest = tmp_path / "incoming" / "mirror.json"
    source_manifest.parent.mkdir(parents=True, exist_ok=True)
    source_manifest.write_text(
        json.dumps(
            {
                "entries": [
                    "src/ai4binance/governance/repository_validator.py",
                    "tests/test_repository_validator.py",
                    "runtime/reports/weekly.md",
                    "runtime/artifacts/quality/gate/latest.json",
                    ".env.example",
                ]
            }
        ),
        encoding="utf-8",
    )
    imported_manifest = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "mirror"
        / "latest_inventory.json"
    )

    payload = _run_powershell_script(
        tmp_path,
        "import_mirror_inventory.ps1",
        "-SourceManifest",
        str(source_manifest),
        "-MirrorManifest",
        str(imported_manifest),
        script_root=ROOT,
    )

    assert payload["status"] == "IMPORTED"
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert imported_manifest.is_file()
    assert json.loads(imported_manifest.read_text(encoding="utf-8")) == json.loads(
        source_manifest.read_text(encoding="utf-8")
    )


def test_import_mirror_inventory_script_rejects_invalid_manifest(
    tmp_path: Path,
) -> None:
    source_manifest = tmp_path / "incoming" / "mirror-invalid.json"
    source_manifest.parent.mkdir(parents=True, exist_ok=True)
    source_manifest.write_text(
        json.dumps({"entries": ["unknown/output.bin"]}),
        encoding="utf-8",
    )
    imported_manifest = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "mirror"
        / "latest_inventory.json"
    )

    with pytest.raises(subprocess.CalledProcessError):
        _run_powershell_script(
            tmp_path,
            "import_mirror_inventory.ps1",
            "-SourceManifest",
            str(source_manifest),
            "-MirrorManifest",
            str(imported_manifest),
            script_root=ROOT,
        )

    assert not imported_manifest.exists()


def test_quality_script_isolates_coverage_artifacts() -> None:
    text = _quality_script_text()

    assert '[ValidateSet("fast", "standard", "full")]' in text
    assert '[string]$Profile = "full"' in text
    assert "$qualityGateProfileConfigPath" in text
    assert "config\\quality\\gates.yaml" in text
    assert "$dmypyStatusDirectory" in text
    assert "$dmypyStatusFile" in text
    assert "runtime\\tmp\\dmypy" in text
    assert "Remove-GeneratedCoverageArtifacts" in text
    assert "Invoke-GeneratedArtifactCleanup" in text
    assert "Invoke-CleanupScript" in text
    assert "cleanup_generated_artifacts.ps1" in text
    assert 'Mode = @("Coverage", "SourceGenerated")' in text
    assert 'Mode = @("Caches", "Coverage", "SourceGenerated")' not in text
    assert '"Caches"' in (
        Path("scripts") / "cleanup_generated_artifacts.ps1"
    ).read_text(encoding="utf-8")
    assert "Invoke-TestTempRetentionCleanup" in text
    assert 'Mode = @("TestTempRetention")' in text
    assert "Invoke-ProcessTempRetentionCleanup" in text
    assert 'Mode = @("ProcessTempRetention")' in text
    assert "Test-IsWindowsAdministrator" in text
    assert '$arguments["ForceAcl"] = $true' in text
    assert "Invoke-SourceGeneratedArtifactCleanup" in text
    assert "Invoke-RepositoryGovernanceValidator" in text

    assert "$repositoryValidatorReportPath" in text
    assert "runtime\\artifacts\\quality\\gate\\repository_validator_latest.json" in text
    assert "runtime\\test\\repository-validator\\runs" in text
    assert "metadata.json" in text
    assert "result.json" in text
    assert "report.md" in text
    assert "migration.json" in text
    assert "migration.md" in text
    assert "Write-RepositoryValidatorRunArtifacts" in text
    assert "Get-RepositoryGitCommit" in text
    assert "Reset-LatestQualityGateArtifacts" in text
    assert "Get-QualityWorkspaceAttestation" in text
    assert "Assert-QualityWorkspaceStable" in text
    assert "Get-QualityGateGitWriteLeasePath" in text
    assert "Publish-QualityGateGitWriteLease" in text
    assert "Remove-QualityGateGitWriteLease" in text
    assert "ai4binance-quality-gate-write-lease.json" in text
    assert 'status = "QUALITY_GATE_ACTIVE"' in text
    assert (
        'process_started_at_utc = $process.StartTime.ToUniversalTime().ToString("o")'
        in text
    )
    assert 'qualityRunCurrentStep = "Quality gate Git write guard"' in text
    assert "REPOSITORY_MUTATED_DURING_QUALITY_GATE" in text
    assert "repository-mutation.json" in text
    assert 'Stage "BEFORE_FULL_PYTEST"' in text
    assert 'Stage "BEFORE_FAST_PYTEST"' in text
    assert 'Stage "BEFORE_STANDARD_PYTEST"' in text
    assert "Get-RepositoryValidatorSummary" in text
    assert "repository_validator_summary = $repositoryValidatorSummary" in text
    assert '$env:PYTHONDONTWRITEBYTECODE = "1"' in text
    assert '"--output-json"' in text
    assert '"--quiet"' in text
    assert "$env:COVERAGE_FILE = $coverageFile" in text
    assert "$coverageJsonPath" in text
    assert "$qualityRunDirectory" in text
    assert "$durablePytestOutputPath" in text
    assert "$durableCoverageJsonPath" in text
    assert "$durableCoverageSummaryPath" in text
    assert "$durableCoverageMarkdownPath" in text
    assert "$banditOutputPath" in text
    assert "$qualityPerformanceLatestPath" in text
    assert "$qualityPerformanceHistoryPath" in text
    assert "$qualityRuntimeDirectory" in text
    assert "$qualityRuntimeRunDirectory" in text
    assert "$qualityRuntimeLatestPath" in text
    assert "$qualityRuntimeRunSummaryPath" in text
    assert "$qualityRuntimeRunTimingsPath" in text
    assert "$qualityRuntimePytestLogPath" in text
    assert "$compactPayload" in text
    assert (
        'compatibility_latest_path = "runtime\\artifacts\\quality\\gate\\latest.json"'
        in text
    )
    assert 'run_timings_path = "runtime\\quality\\" + $qualityRunTimestamp' in text
    assert "read_coverage_percent.py" in text
    assert "$pytestOutputPath" in text
    assert "Invoke-PytestWithCapturedOutput" in text
    assert "Get-ArtifactLineage" in text
    assert "Publish-QualityRunEvidenceArtifacts" in text
    assert 'throw "Coverage evidence artifact is missing: $artifactPath"' in text
    assert "Publish-PytestEvidenceArtifact" in text
    assert "$pytestOutputPath = $durablePytestOutputPath" in text
    assert 'Join-Path $pytestTemp "pytest-output.txt"' not in text
    assert (
        'coverage_summary_json_path = "runtime\\artifacts\\quality\\gate\\runs\\" '
        '+ $qualityRunTimestamp + "\\coverage-summary.json"' in text
    )
    assert (
        'coverage_summary_markdown_path = "runtime\\artifacts\\quality\\gate\\runs\\" '
        '+ $qualityRunTimestamp + "\\coverage-summary.md"' in text
    )
    assert "step_exit_codes = $script:qualityStepExitCodes" in text
    assert "step_telemetry = @($script:qualityStepTelemetry)" in text
    assert 'run_started_at_utc = $script:qualityRunStartedAtUtc.ToString("o")' in text
    assert "run_duration_ms = Get-QualityRunDurationMs" in text
    assert "Add-QualityStepTelemetry" in text
    assert "Write-QualityPerformanceArtifacts" in text
    assert "performance_latest.json" in text
    assert "performance_history.jsonl" in text
    assert "quality_budget_latest.json" in text
    assert "quality_budget_history.jsonl" in text
    assert "Write-QualityBudgetArtifacts" in text
    assert "Get-QualityBudgetTokenRisk" in text
    assert "runtime\\quality" in text
    assert "summary.json" in text
    assert "timings.json" in text
    assert "pytest.log" in text
    assert "bandit.log" in text
    assert (
        "selected_pytest_arguments = @($script:qualitySelectedPytestArguments)" in text
    )
    assert "selected_test_count" in text
    assert "pytest_test_count = $pytestTestCount" in text
    assert '"--durations=20"' in text
    assert '"--durations-min=0.5"' in text
    assert "profile = $script:qualityGateProfile" in text
    assert "verification_status = Get-QualityProfileVerificationStatus" in text
    assert "pytest_exit_code = $script:pytestExitCode" in text
    assert "pytest_output_sha256 = $script:pytestEvidenceSha256" in text
    assert "Invoke-BanditWithCapturedOutput" in text
    assert "coverage.py json totals.percent_covered" in text
    assert "Coverage policy evaluation" in text
    assert "Invoke-DocsHygieneGateTests" in text
    assert "Invoke-ArtifactHygieneGateTests" in text
    assert "Invoke-ConstitutionSyncGateTests" in text
    assert "Invoke-DeterministicGovernanceGate" in text
    assert "ai4binance.ops.coverage_policy" in text
    assert "config\\quality\\coverage-targets.json" in text
    assert "runtime\\artifacts\\quality\\gate\\coverage_summary.json" in text
    assert "runtime\\artifacts\\quality\\gate\\coverage_summary.md" in text
    assert "coverage_policy_summary = $coveragePolicySummary" in text
    assert "coverage_realism_proof = $coverageRealismProof" in text
    assert "workspace_attestation = $workspaceAttestation" in text
    assert "$deterministicQualityGateReportPath" in text
    assert (
        "runtime\\artifacts\\quality\\gate\\deterministic_quality_gate_latest.json"
        in text
    )
    assert "Get-DeterministicQualityGateSummary" in text
    assert (
        "deterministic_quality_gate_summary = $deterministicQualityGateSummary" in text
    )
    assert "$governanceGateReportPath" in text
    assert "runtime\\artifacts\\quality\\gate\\governance_gate_latest.json" in text
    assert "Get-GovernanceGateSummary" in text
    assert "governance_gate_summary = $governanceGateSummary" in text
    assert "Write-QualityGateFailureEvidence" in text
    assert "stale_latest_invalidated = $true" in text
    assert "GOVERNED_MARKDOWN_COVERAGE_REALISM_PROOF" in text
    assert "BANDIT_STDOUT_STDERR_CAPTURE" in text
    assert "Get-FileHash" in text
    assert "missing governed markdown coverage proof" in text
    assert "does not match governed markdown proof source" in text
    assert "pytest_pass_count = $pytestPassCount" in text
    assert "coverage_percent = $coveragePercent" in text
    assert '".coverage"' in text
    assert 'Join-Path $env:TEMP "pytest"' in text
    assert "Financial leak guard" in text
    assert "ai4binance.ops.financial_leak_guard" in text
    assert "Privacy leak guard" in text
    assert "ai4binance.ops.privacy_leak_guard" in text
    assert "Repository governance validator" in text
    assert "Restore-RepositoryValidatorCache" in text
    assert "Test-RepositoryValidatorCacheHashes" in text
    assert "Save-RepositoryValidatorCache" in text
    assert "Get-RepositoryValidatorCacheSubject" in text
    assert "repository_validator_sha256" in text
    assert "quality_gate_script_sha256" in text
    assert "clean_worktree_same_head_policy_and_code" in text
    assert "CACHE_HIT" in text
    assert "CACHE_MISS" in text
    assert "$script:repositoryValidatorCacheStatus" in text
    assert "$script:repositoryValidatorCacheReason" in text
    assert "repository_validator_cache_status" in text
    assert "repository_validator_cache_reason" in text
    assert "repository_validator_cache_mode" in text
    assert "worktree is not clean" in text
    assert "ai4binance.governance.repository_validator" in text
    assert '"--repository-policy"' in text
    assert '"--bandit-evidence-source"' in text
    assert '"--docs-hygiene-evidence-source"' in text
    assert '"--artifact-hygiene-evidence-source"' in text
    assert '"--constitution-sync-evidence-source"' in text
    assert "policies\\repository-validator\\manifest-policy.json" in text
    assert "findings.json" in text
    assert "policy-snapshot.json" in text
    assert '"--output-mirror-manifest"' in text
    assert (
        "runtime\\artifacts\\repository_validation\\mirror\\latest_inventory.json"
        in text
    )


def test_quality_profile_workflow_binds_pr_release_and_manual_profiles() -> None:
    text = (Path(".github") / "workflows" / "quality_profiles.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in text
    assert "release:" in text
    assert "types: [published]" in text
    assert "workflow_dispatch:" in text
    assert "default: standard" in text
    assert "Run standard profile for pull requests" in text
    assert "-Profile standard" in text
    assert "Run full profile for published releases" in text
    assert "-Profile full" in text
    assert "inputs.profile" in text
    assert "permissions:\n  contents: read" in text


def test_quality_script_freezes_same_run_coverage_evidence_and_fails_closed(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-ErrorMessage {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    try {
        & $Action | Out-Null
        return "NO_THROW"
    }
    catch {
        return $_.Exception.Message
    }
}

Set-Content -LiteralPath $pytestOutputPath -Value "3 passed" -Encoding ASCII
Set-Content `
    -LiteralPath $coverageJsonPath `
    -Value '{"totals":{"percent_covered":95.5}}' `
    -Encoding ASCII
Set-Content `
    -LiteralPath $coveragePolicySummaryPath `
    -Value '{"policy_result":"PASS"}' `
    -Encoding ASCII
Set-Content `
    -LiteralPath $coveragePolicyMarkdownPath `
    -Value '# Coverage proof' `
    -Encoding ASCII
Publish-QualityRunEvidenceArtifacts
$summary = Get-CoveragePolicySummary
$proof = Get-CoverageRealismProof
Write-QualityRunMetadata -Status "TECHNICAL_QUALITY_PASS" -CurrentStep "COMPLETED"
$metadata = Get-Content -LiteralPath $qualityRunMetadataPath -Raw | ConvertFrom-Json

$result = [ordered]@{
    coverage_json_matches = (
        (Get-Sha256Hex -Path $coverageJsonPath) -eq
        (Get-Sha256Hex -Path $durableCoverageJsonPath)
    )
    coverage_summary_matches = (
        (Get-Sha256Hex -Path $coveragePolicySummaryPath) -eq
        (Get-Sha256Hex -Path $durableCoverageSummaryPath)
    )
    coverage_markdown_matches = (
        (Get-Sha256Hex -Path $coveragePolicyMarkdownPath) -eq
        (Get-Sha256Hex -Path $durableCoverageMarkdownPath)
    )
    policy_result = $summary.policy_result
    proof_path = $proof.markdown_path
    metadata_summary_path = $metadata.coverage_summary_json_path
    metadata_markdown_path = $metadata.coverage_summary_markdown_path
}

Remove-Item -LiteralPath $coveragePolicyMarkdownPath -Force
$result.missing_artifact_error = Get-ErrorMessage {
    Publish-QualityRunEvidenceArtifacts
}
$result | ConvertTo-Json -Depth 5
""",
    )

    assert payload["coverage_json_matches"] is True
    assert payload["coverage_summary_matches"] is True
    assert payload["coverage_markdown_matches"] is True
    assert payload["policy_result"] == "PASS"
    assert payload["proof_path"] == (
        "runtime\\artifacts\\quality\\gate\\coverage_summary.md"
    )
    assert payload["metadata_summary_path"].endswith("\\coverage-summary.json")
    assert payload["metadata_markdown_path"].endswith("\\coverage-summary.md")
    assert "Coverage evidence artifact is missing:" in payload["missing_artifact_error"]


def test_quality_profile_workflow_has_structural_github_contract() -> None:
    workflow = yaml.safe_load(
        (Path(".github") / "workflows" / "quality_profiles.yml").read_text(
            encoding="utf-8"
        ),
    )
    assert isinstance(workflow, dict)
    events = workflow.get("on", workflow.get(True))
    assert isinstance(events, dict)
    assert "pull_request" in events
    assert events["release"]["types"] == ["published"]
    assert "workflow_dispatch" in events
    assert workflow["permissions"]["contents"] == "read"

    quality_job = workflow["jobs"]["quality"]
    step_names = [step["name"] for step in quality_job["steps"]]
    assert "Run standard profile for pull requests" in step_names
    assert "Run full profile for published releases" in step_names
    assert "Run selected profile for manual milestone verification" in step_names
    assert "Upload quality evidence" in step_names


def test_quality_script_runs_gate_steps_in_governed_order() -> None:
    text = _quality_script_text()
    expected_sequence = [
        "Reset-LatestQualityGateArtifacts",
        "Invoke-SourceGeneratedArtifactCleanup",
        'Invoke-QualityStep "Dependency check"',
        'Invoke-QualityStep "Ruff format"',
        'Invoke-QualityStep "Ruff lint"',
        'Invoke-QualityStep "Ruff maintainability ratchet"',
        'Invoke-QualityStep "MyPy"',
        'Invoke-QualityStep "Financial leak guard"',
        'Invoke-QualityStep "Privacy leak guard"',
        "Invoke-RepositoryGovernanceValidator",
        "$script:mirrorRemoteCheck = Invoke-ConditionalMirrorHygiene",
        "Remove-GeneratedCoverageArtifacts",
        "$previousCoverageFile = $env:COVERAGE_FILE",
        "$env:COVERAGE_FILE = $coverageFile",
        "Invoke-PytestWithCapturedOutput",
        'Invoke-QualityStep "Coverage JSON"',
        "Invoke-CoveragePolicyEvaluation",
        "Publish-QualityRunEvidenceArtifacts",
        "Invoke-BanditWithCapturedOutput",
        "Invoke-DeterministicQualityGate",
        "Invoke-DocsHygieneGateTests",
        "Invoke-ArtifactHygieneGateTests",
        "Invoke-ConstitutionSyncGateTests",
        "Invoke-DeterministicGovernanceGate",
        "Invoke-GeneratedArtifactCleanup",
        "Write-QualityGateGreenEvidence",
    ]

    execution_text = text[text.index("function Invoke-QualityGate") :]
    positions = [execution_text.index(item) for item in expected_sequence]
    coverage_step = execution_text[
        execution_text.index(
            'Invoke-QualityStep "Coverage JSON"'
        ) : execution_text.index("Invoke-CoveragePolicyEvaluation")
    ]

    assert positions == sorted(positions)
    assert '"--quiet"' in coverage_step


def test_every_quality_profile_cleans_source_generated_artifacts_first() -> None:
    text = _quality_script_text()

    for function_name in (
        "Invoke-FastQualityGate",
        "Invoke-StandardQualityGate",
        "Invoke-QualityGate",
    ):
        start = text.index(f"function {function_name}")
        next_function = text.find("\nfunction ", start + 1)
        body = text[start : next_function if next_function >= 0 else len(text)]
        assert body.index("Reset-LatestQualityGateArtifacts") < body.index(
            "Invoke-SourceGeneratedArtifactCleanup"
        )
        assert body.index("Invoke-SourceGeneratedArtifactCleanup") < body.index(
            'Invoke-QualityStep "Ruff format"'
        )
    assert '"--basetemp",' in text
    assert "$pytestTemp" in text
    assert '"--cov=ai4binance"' in text
    assert '"--cov-report="' in text
    assert '"--durations=30"' in text
    assert '"--durations-min=0.5"' in text
    assert '"--cov-report=term-missing"' not in text
    assert "Invoke-CoveragePolicyEvaluation" in text
    assert "if ($null -eq $previousCoverageFile)" in text
    assert "Remove-Item Env:\\COVERAGE_FILE" in text
    assert "$env:COVERAGE_FILE = $previousCoverageFile" in text
    assert "Start-Transcript -Path $qualityRunOutputPath" in text
    assert "function Write-CompactQualityConsoleOutput" in text
    assert "*> $stepOutputPath" in text
    assert "2>> $gitChangedPathsErrorPath" in text
    assert "git-changed-paths-error.txt" in text
    assert '$ErrorActionPreference = "Continue"' in text
    assert "$ErrorActionPreference = $previousErrorActionPreference" in text
    assert "first_actionable_error = $actionableError" in text
    assert "output_sha256 = $outputDigest" in text
    assert "selected_test_count = $selectedTestCount" in text
    assert "Write-Warning" not in text
    assert "Write-Host" not in text
    terminal_catch = text[
        text.index("catch {\n    $qualityRunFailedStep") : text.index(
            "finally {\n    try {\n        Stop-Transcript"
        )
    ]
    assert "throw" not in terminal_catch
    assert "$qualityGateExitCode = 1" in terminal_catch
    assert "exit $qualityGateExitCode" in text
    assert 'Write-QualityRunMetadata -Status "RUNNING"' in text
    assert '$script:qualityRunCurrentStep = "Pytest"' in text
    assert '$script:qualityRunCurrentStep = "COMPLETED"' in text
    assert '$script:qualityRunCurrentStep = "FAILED"' in text
    assert "current_step = $CurrentStep" in text
    assert "& $python -B @arguments *> $pytestOutputPath" in text
    assert '$script:qualityStepExitCodes["Pytest"] = $exitCode' in text
    assert "Evidence: $script:pytestEvidencePath" in text
    assert "function Get-FileTailText" in text
    assert "function Get-CachedJsonArtifact" in text
    assert "Write-QualityRunMetadata" in text


def test_quality_gate_loop_delegates_to_canonical_full_gate() -> None:
    wrapper_path = (
        Path(".agents") / "skills" / "quality-gate-loop" / "scripts" / "invoke_gate.ps1"
    )
    text = wrapper_path.read_text(encoding="utf-8")

    assert '$qualityScript = Join-Path $root "scripts\\quality.ps1"' in text
    assert "-File $qualityScript" in text
    assert "-Profile full" in text
    assert "exit $LASTEXITCODE" in text
    assert "[System.IO.Path]::GetTempPath()" not in text
    assert "-m pytest" not in text


def test_quality_script_profiles_preserve_canonical_full_authority() -> None:
    text = _quality_script_text()

    assert "function Invoke-SelectedQualityGate" in text
    assert "function Invoke-FastQualityGate" in text
    assert "function Invoke-StandardQualityGate" in text
    assert "function Invoke-QualityPytestSelector" in text
    assert "function Get-StandardRequiredPytestArguments" in text
    assert "function Reset-DmypyStatusFile" in text
    assert "Remove-Item -LiteralPath $dmypyStatusFile" in text
    assert 'Invoke-QualityStep "dmypy" @(' in text
    assert '"mypy.dmypy"' in text
    assert '"--status-file"' in text
    assert "$dmypyStatusFile" in text
    assert 'Invoke-QualityStep "MyPy" @("-m", "mypy")' in text
    assert '"ai4binance.ops.quality_gate"' in text
    assert '"select-tests"' in text
    assert "$qualityGateProfileConfigPath" in text
    assert 'Write-QualityProfileEvidence -Status "FAST_PROFILE_PASS"' in text
    assert 'Write-QualityProfileEvidence -Status "STANDARD_PROFILE_PASS"' in text
    assert "canonical_quality_authority = $false" in text
    assert 'full_verification_status = "NOT_VERIFIED"' in text
    assert 'verification_status = "FULL_VERIFIED"' in text
    assert "canonical_quality_authority = $true" in text


def test_quality_script_mutex_hash_is_windows_powershell_compatible() -> None:
    text = _quality_script_text()

    assert "[System.Security.Cryptography.SHA256]::Create()" in text
    assert "$qualityGateHashAlgorithm.ComputeHash(" in text
    assert "[BitConverter]::ToString(" in text
    assert '"Local\\AI4BinanceQualityGate-"' in text
    assert "HashData(" not in text


def test_quality_gate_profile_config_separates_fast_standard_full() -> None:
    text = (Path("config") / "quality" / "gates.yaml").read_text(encoding="utf-8")

    assert "version: 1" in text
    assert "fast:" in text
    assert "standard:" in text
    assert "full:" in text
    assert "verification_status: FAST_VERIFIED" in text
    assert "verification_status: STANDARD_VERIFIED" in text
    assert "verification_status: FULL_VERIFIED" in text
    assert "canonical_quality_authority: true" in text
    assert "canonical_quality_authority: false" in text
    assert "type_check: dmypy" in text
    assert "type_check: mypy" in text
    assert "fast_pass_is_not_full_verified: true" in text
    assert "dmypy_is_local_accelerator_only: true" in text
    assert "unknown_affected_scope_escalates: standard" in text
    assert "evidence_root: runtime/quality" in text
    assert "compatibility_evidence_root: runtime/artifacts/quality/gate" in text
    assert "affected_tests:" in text
    assert "quality_gate_policy_and_wrapper" in text
    assert "script_hygiene" in text
    assert "quality_gate_engine" in text
    assert "enforcement_inventory" in text
    assert "critical_enforcement_inventory" in text
    assert "tests/test_governed_object_enforcement.py" in text
    assert "governed_docs" in text
    assert "instruction_contracts" in text
    assert "changed_tests" in text
    assert "AGENTS.md" in text
    assert "CLAUDE.md" in text
    assert "GEMINI.md" in text
    assert "docs/providers/instruction_codex_provider.md" in text
    assert "src/ai4binance/governance/AGENTS.md" in text
    assert "tests/AGENTS.md" in text
    assert "path_prefixes:" in text
    assert "docs/" in text
    assert "tests/test_docs_hygiene.py" in text
    assert "tests_from_changed_paths: true" in text
    assert "required_tests:" in text
    assert "tests/test_quality_gate_profiles.py" in text
    assert "tests/test_governance_constitution_sync.py" in text


def test_quality_script_fast_affected_mapping_is_fail_closed(tmp_path: Path) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-ErrorMessage {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    try {
        & $Action | Out-Null
        return "NO_THROW"
    }
    catch {
        return $_.Exception.Message
    }
}

$artifactTest = Join-Path $repoRoot "tests/test_artifact_hygiene_scripts.py"
$docsTest = Join-Path $repoRoot "tests/test_docs_hygiene.py"
$governanceTest = Join-Path $repoRoot "tests/test_governance_constitution_sync.py"
$validatorTest = Join-Path $repoRoot "tests/test_repository_validator.py"
New-Item -ItemType Directory -Path (Split-Path -Parent $artifactTest) -Force | Out-Null
Set-Content -LiteralPath $artifactTest -Value "" -Encoding ASCII
Set-Content -LiteralPath $docsTest -Value "" -Encoding ASCII
Set-Content -LiteralPath $governanceTest -Value "" -Encoding ASCII
Set-Content -LiteralPath $validatorTest -Value "" -Encoding ASCII
$qualityPolicyPath = Join-Path $repoRoot "config/quality/gates.yaml"
$qualityPolicyDirectory = Split-Path -Parent $qualityPolicyPath
New-Item -ItemType Directory -Path $qualityPolicyDirectory -Force | Out-Null
@'
version: 1
profiles:
  fast:
    verification_status: FAST_VERIFIED
    canonical_quality_authority: false
    format_check: ruff
    lint: ruff
    type_check: dmypy
    pytest_scope: affected
    fail_fast: true
    full_suite: false
  standard:
    verification_status: STANDARD_VERIFIED
    canonical_quality_authority: false
    format_check: ruff
    lint: ruff
    type_check: mypy
    pytest_scope: required
    fail_fast: true
    full_suite: false
  full:
    verification_status: FULL_VERIFIED
    canonical_quality_authority: true
    format_check: ruff
    lint: ruff
    type_check: mypy
    pytest_scope: full
    fail_fast: false
    full_suite: true
affected_tests:
  default_when_clean:
    - tests/test_artifact_hygiene_scripts.py
  mappings:
    - name: quality_gate_scripts
      path_prefixes:
        - scripts/
        - pyproject.toml
        - config/quality/
      tests:
        - tests/test_artifact_hygiene_scripts.py
    - name: governance
      path_prefixes:
        - src/ai4binance/governance/
        - config/governance/
        - policies/
      tests:
        - tests/test_governance_constitution_sync.py
        - tests/test_repository_validator.py
    - name: schemas_and_contracts
      path_prefixes:
        - schemas/
        - contracts/
      tests:
        - tests/test_repository_validator.py
    - name: governed_docs
      path_prefixes:
        - docs/
      tests:
        - tests/test_docs_hygiene.py
        - tests/test_repository_validator.py
    - name: tests
      path_prefixes:
        - tests/
      tests_from_changed_paths: true
  unknown_impact_escalates_to: standard
required_tests:
  - tests/test_artifact_hygiene_scripts.py
  - tests/test_governance_constitution_sync.py
  - tests/test_repository_validator.py
'@ | Set-Content -LiteralPath $qualityPolicyPath -Encoding UTF8

function Get-ChangedRepositoryPaths {
    @(
        "scripts/quality.ps1",
        "config/quality/gates.yaml",
        "tests/test_artifact_hygiene_scripts.py"
    )
}
$qualityArgs = Get-FastAffectedPytestArguments

function Get-ChangedRepositoryPaths {
    @("src/ai4binance/governance/gate.py")
}
$governanceArgs = Get-FastAffectedPytestArguments

function Get-ChangedRepositoryPaths {
    @("docs/workflows/runbook_quality_gate_profiles.md")
}
$docsArgs = Get-FastAffectedPytestArguments

function Get-ChangedRepositoryPaths {
    @("src/ai4binance/unknown/new_module.py")
}
$unknownMessage = Get-ErrorMessage { Get-FastAffectedPytestArguments }

[ordered]@{
    quality_args = @($qualityArgs)
    governance_args = @($governanceArgs)
    docs_args = @($docsArgs)
    unknown_message = $unknownMessage
} | ConvertTo-Json -Depth 6
""",
    )

    assert payload["quality_args"] == [
        "tests/test_artifact_hygiene_scripts.py",
        "--no-cov",
    ]
    assert payload["governance_args"] == [
        "tests/test_governance_constitution_sync.py",
        "tests/test_repository_validator.py",
        "--no-cov",
    ]
    assert payload["docs_args"] == [
        "tests/test_docs_hygiene.py",
        "tests/test_repository_validator.py",
        "--no-cov",
    ]
    unknown_payload = json.loads(payload["unknown_message"])
    assert unknown_payload["status"] == "ESCALATE"
    assert unknown_payload["escalate_to"] == "standard"
    assert unknown_payload["unknown_paths"] == ["src/ai4binance/unknown/new_module.py"]
    assert unknown_payload["error"].startswith(
        "FAST affected pytest scope cannot be resolved safely for: "
    )
    assert (
        "Run scripts\\quality.ps1 -Profile standard or -Profile full."
        in unknown_payload["error"]
    )


def test_quality_script_changed_path_scan_files_git_warnings(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function git {
    if ($args -contains "diff") {
        Write-Error "synthetic git warning"
        $global:LASTEXITCODE = 0
        Write-Output "tests/example.py"
        return
    }
    $global:LASTEXITCODE = 0
    Write-Output "src/ai4binance/example.py"
}

$paths = @(Get-ChangedRepositoryPaths)
$warningPath = Join-Path $qualityRunDirectory "git-changed-paths-error.txt"
[ordered]@{
    paths = $paths
    warning_is_file_backed = Test-Path -LiteralPath $warningPath
    warning_text = Get-FileTailText -Path $warningPath
} | ConvertTo-Json -Depth 4
""",
    )

    assert payload["paths"] == [
        "src/ai4binance/example.py",
        "tests/example.py",
    ]
    assert payload["warning_is_file_backed"] is True
    assert "synthetic git warning" in payload["warning_text"]


def test_quality_harness_timeout_force_cleans_process_tree(tmp_path: Path) -> None:
    harness_path = _write_quality_harness(
        tmp_path,
        "Start-Sleep -Seconds 30\n",
    )

    with pytest.raises(pytest.fail.Exception, match="force-cleaned"):
        _run_quality_harness_command(
            tmp_path,
            harness_path,
            timeout_seconds=1,
        )

    assert _find_quality_harness_processes(harness_path) == []


def test_external_helper_timeout_force_cleans_process_tree() -> None:
    with pytest.raises(pytest.fail.Exception, match="force-cleaned"):
        _run_external_command(
            [
                _powershell(),
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Start-Sleep -Seconds 30",
            ],
            timeout_seconds=1,
        )


def test_quality_script_evidence_helpers_write_fail_closed_payload(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
Remove-Item -LiteralPath @(
    $pytestOutputPath,
    $coverageJsonPath,
    $coveragePolicySummaryPath,
    $coveragePolicyMarkdownPath,
    $repositoryValidatorReportPath,
    $governanceGateReportPath,
    $qualityEvidencePath
) -Force -ErrorAction SilentlyContinue

function Get-FileHash {
    [pscustomobject]@{
        Hash = "ABCDEF"
    }
}

function Get-ErrorMessage {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    try {
        & $Action | Out-Null
        return "NO_THROW"
    }
    catch {
        return $_.Exception.Message
    }
}

$results = [ordered]@{
    missing_pytest = $null -eq (Get-PytestPassCount)
    missing_coverage = $null -eq (Get-CoveragePercent)
    missing_policy = $null -eq (Get-CoveragePolicySummary)
    missing_realism = $null -eq (Get-CoverageRealismProof)
    mirror_without_manifest = Get-ErrorMessage { Invoke-ConditionalMirrorHygiene }
}

Set-Content -LiteralPath $pytestOutputPath -Value "12 passed in 0.10s" -Encoding UTF8
[ordered]@{
    totals = [ordered]@{
        percent_covered = 95.6789
    }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $coverageJsonPath -Encoding ASCII
$summaryDirectory = Split-Path -Parent $coveragePolicySummaryPath
New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
[ordered]@{
    total_coverage_percent = 95.68
    status = "PASS"
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $coveragePolicySummaryPath -Encoding ASCII
Set-Content `
    -LiteralPath $coveragePolicyMarkdownPath `
    -Value "# Coverage proof" `
    -Encoding UTF8
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $governanceGateReportPath) `
    -Force |
    Out-Null
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorReportPath) `
    -Force |
    Out-Null
[ordered]@{
    status = "PASS"
    artifact_count = 862
    repository_health_score = 100
    blockers = @()
    findings = @()
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding ASCII
[ordered]@{
    status = "PASS"
    blockers = @()
    repository_validator = [ordered]@{
        status = "PASS"
    }
    docs_hygiene = [ordered]@{
        passed = $true
    }
    artifact_hygiene = [ordered]@{
        passed = $true
    }
    constitution_sync_tests = [ordered]@{
        passed = $true
    }
    alignment_status = "PASS"
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $governanceGateReportPath -Encoding ASCII

$results.pytest_pass_count = Get-PytestPassCount
$results.coverage_percent = Get-CoveragePercent
$policySummary = Get-CoveragePolicySummary
$results.policy_percent = [double]$policySummary.total_coverage_percent
$realismProof = Get-CoverageRealismProof
$results.realism_type = $realismProof.evidence_type
$results.realism_path = $realismProof.markdown_path
$validatorSummary = Get-RepositoryValidatorSummary
$results.repository_validator_status = $validatorSummary.status
$results.repository_validator_report_path = $validatorSummary.report_path
$results.repository_validator_artifact_count = $validatorSummary.artifact_count
$results.repository_validator_health = $validatorSummary.repository_health_score
$results.repository_validator_blockers = $validatorSummary.blocker_count
$results.repository_validator_findings = $validatorSummary.finding_count
$results.repository_validator_actions = $validatorSummary.recommended_action_count
$governanceGateSummary = Get-GovernanceGateSummary
$results.governance_gate_status = $governanceGateSummary.status
$results.governance_gate_report_path = $governanceGateSummary.report_path
$results.governance_gate_blockers = $governanceGateSummary.blocker_count
$results.governance_gate_artifact_hygiene = `
    $governanceGateSummary.artifact_hygiene_passed

Write-QualityRunMetadata -Status "RUNNING" -CurrentStep "INITIALIZING"
Write-QualityGateGreenEvidence
$evidence = Get-Content -LiteralPath $qualityEvidencePath -Raw | ConvertFrom-Json
$metadata = Get-Content -LiteralPath $qualityRunMetadataPath -Raw | ConvertFrom-Json
$results.evidence_status = $evidence.status
$results.evidence_command = $evidence.command
$results.evidence_coverage_source = $evidence.coverage_source
$results.evidence_execution_allowed = $evidence.execution_allowed
$results.evidence_promotion_status = $evidence.promotion_status
$results.evidence_live_status = $evidence.live_eligibility_status
$results.evidence_mirror_remote_check = $evidence.mirror_remote_check
$results.evidence_manifest_path = $evidence.mirror_manifest_path
$results.evidence_report_path = $evidence.mirror_hygiene_report_path
$results.evidence_cleanup_plan_path = $evidence.mirror_cleanup_plan_path
$results.evidence_repository_validator_status = `
    $evidence.repository_validator_summary.status
$results.evidence_repository_validator_report_path = `
    $evidence.repository_validator_summary.report_path
$results.evidence_repository_validator_artifact_count = `
    $evidence.repository_validator_summary.artifact_count
$results.evidence_repository_validator_health = `
    $evidence.repository_validator_summary.repository_health_score
$results.evidence_repository_validator_blockers = `
    $evidence.repository_validator_summary.blocker_count
$results.evidence_repository_validator_findings = `
    $evidence.repository_validator_summary.finding_count
$results.evidence_repository_validator_actions = `
    $evidence.repository_validator_summary.recommended_action_count
$results.evidence_governance_gate_status = `
    $evidence.governance_gate_summary.status
$results.evidence_governance_gate_report_path = `
    $evidence.governance_gate_summary.report_path
$results.evidence_governance_gate_blockers = `
    $evidence.governance_gate_summary.blocker_count
$results.metadata_status = $metadata.status
$results.metadata_current_step = $metadata.current_step

$results | ConvertTo-Json -Depth 8
""",
    )

    assert payload["missing_pytest"] is True
    assert payload["missing_coverage"] is True
    assert payload["missing_policy"] is True
    assert payload["missing_realism"] is True
    assert payload["mirror_without_manifest"] == (
        "Mirror hygiene manifest is required but was not found."
    )
    assert payload["pytest_pass_count"] == 12
    assert payload["coverage_percent"] == 95.68
    assert payload["policy_percent"] == 95.68
    assert payload["realism_type"] == "GOVERNED_MARKDOWN_COVERAGE_REALISM_PROOF"
    assert (
        payload["realism_path"]
        == "runtime\\artifacts\\quality\\gate\\coverage_summary.md"
    )
    assert payload["repository_validator_status"] == "PASS"
    assert (
        payload["repository_validator_report_path"]
        == "runtime\\artifacts\\quality\\gate\\repository_validator_latest.json"
    )
    assert payload["repository_validator_artifact_count"] == 862
    assert payload["repository_validator_health"] == 100
    assert payload["repository_validator_blockers"] == 0
    assert payload["repository_validator_findings"] == 0
    assert payload["repository_validator_actions"] == 0
    assert payload["governance_gate_status"] == "PASS"
    assert (
        payload["governance_gate_report_path"]
        == "runtime\\artifacts\\quality\\gate\\governance_gate_latest.json"
    )
    assert payload["governance_gate_blockers"] == 0
    assert payload["governance_gate_artifact_hygiene"] is True
    assert payload["evidence_status"] == "TECHNICAL_QUALITY_PASS"
    assert payload["evidence_command"].endswith(r".\scripts\quality.ps1 -Profile full")
    assert (
        payload["evidence_coverage_source"] == "coverage.py json totals.percent_covered"
    )
    assert payload["evidence_execution_allowed"] is False
    assert payload["evidence_promotion_status"] == "RESEARCH_ONLY"
    assert payload["evidence_live_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["evidence_mirror_remote_check"] == "NOT_VERIFIED"
    assert (
        payload["evidence_manifest_path"]
        == "runtime\\artifacts\\repository_validation\\mirror\\latest_inventory.json"
    )
    assert (
        payload["evidence_report_path"]
        == "runtime\\artifacts\\repository_validation\\mirror_hygiene_report.json"
    )
    assert (
        payload["evidence_cleanup_plan_path"]
        == "runtime\\artifacts\\repository_validation\\mirror_cleanup_plan.json"
    )
    assert payload["evidence_repository_validator_status"] == "PASS"
    assert (
        payload["evidence_repository_validator_report_path"]
        == "runtime\\artifacts\\quality\\gate\\repository_validator_latest.json"
    )
    assert payload["evidence_repository_validator_artifact_count"] == 862
    assert payload["evidence_repository_validator_health"] == 100
    assert payload["evidence_repository_validator_blockers"] == 0
    assert payload["evidence_repository_validator_findings"] == 0
    assert payload["evidence_repository_validator_actions"] == 0
    assert payload["evidence_governance_gate_status"] == "PASS"
    assert (
        payload["evidence_governance_gate_report_path"]
        == "runtime\\artifacts\\quality\\gate\\governance_gate_latest.json"
    )
    assert payload["evidence_governance_gate_blockers"] == 0
    assert payload["metadata_status"] == "RUNNING"
    assert payload["metadata_current_step"] == "INITIALIZING"


def test_quality_script_persists_repository_validator_run_bundle(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-RepositoryGitCommit {
    return "abc123"
}

New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorReportPath) `
    -Force |
    Out-Null
New-Item -ItemType Directory -Path $repositoryValidatorRunDirectory -Force | Out-Null
[ordered]@{
    status = "PASS"
    artifact_count = 3
    repository_health_score = 100
    blockers = @()
    findings = @()
    migration_map = @(
        [ordered]@{
            source_path = "runtime/validator-debug.json"
            target_path = "runtime/test/repository-validator/runs/example/result.json"
            reason = "legacy-root-output"
            authority_level = "ADVISORY"
            status = "PLANNED"
            requires_link_update = $false
            requires_reference_update = $false
            risk = "LOW"
        }
    )
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding UTF8

Set-Content `
    -LiteralPath $repositoryValidatorRunMarkdownPath `
    -Value "# Report" `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunMigrationMarkdownPath `
    -Value "# Migration" `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunFindingsJsonPath `
    -Value (
        '{"status":"PASS","policy_source_path":' +
        '"policies/repository-validator/manifest-policy.json"}'
    ) `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunPolicySnapshotPath `
    -Value (
        '{"snapshot_type":"REPOSITORY_VALIDATOR_POLICY_SNAPSHOT",' +
        '"policy_source_path":"policies/repository-validator/manifest-policy.json"}'
    ) `
    -Encoding UTF8
Write-RepositoryValidatorRunArtifacts

$metadata = Get-Content `
    -LiteralPath $repositoryValidatorRunMetadataPath `
    -Raw |
    ConvertFrom-Json
$result = Get-Content `
    -LiteralPath $repositoryValidatorRunResultPath `
    -Raw |
    ConvertFrom-Json
$migration = Get-Content `
    -LiteralPath $repositoryValidatorRunMigrationJsonPath `
    -Raw |
    ConvertFrom-Json
$findings = Get-Content `
    -LiteralPath $repositoryValidatorRunFindingsJsonPath `
    -Raw |
    ConvertFrom-Json
$policySnapshot = Get-Content `
    -LiteralPath $repositoryValidatorRunPolicySnapshotPath `
    -Raw |
    ConvertFrom-Json

[ordered]@{
    run_directory_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunDirectory `
        -PathType Container
    metadata_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunMetadataPath `
        -PathType Leaf
    result_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunResultPath `
        -PathType Leaf
    report_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunMarkdownPath `
        -PathType Leaf
    migration_json_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunMigrationJsonPath `
        -PathType Leaf
    migration_markdown_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunMigrationMarkdownPath `
        -PathType Leaf
    findings_json_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunFindingsJsonPath `
        -PathType Leaf
    policy_snapshot_exists = Test-Path `
        -LiteralPath $repositoryValidatorRunPolicySnapshotPath `
        -PathType Leaf
    metadata_run_id = $metadata.run_id
    metadata_trigger = $metadata.trigger
    metadata_mode = $metadata.mode
    metadata_scenario = $metadata.scenario
    metadata_cache_mode = $metadata.cache_mode
    metadata_git_commit = $metadata.git_commit
    metadata_result_path = $metadata.result_json_path
    metadata_findings_path = $metadata.findings_json_path
    metadata_policy_snapshot_path = $metadata.policy_snapshot_path
    metadata_policy_source_path = $metadata.policy_source_path
    result_status = $result.status
    migration_run_id = $migration.run_id
    migration_target_path = $migration.migration_map[0].target_path
    findings_status = $findings.status
    findings_policy_source_path = $findings.policy_source_path
    policy_snapshot_type = $policySnapshot.snapshot_type
    policy_snapshot_policy_source_path = $policySnapshot.policy_source_path
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["run_directory_exists"] is True
    assert payload["metadata_exists"] is True
    assert payload["result_exists"] is True
    assert payload["report_exists"] is True
    assert payload["migration_json_exists"] is True
    assert payload["migration_markdown_exists"] is True
    assert payload["findings_json_exists"] is True
    assert payload["policy_snapshot_exists"] is True
    assert payload["metadata_run_id"]
    assert payload["metadata_trigger"] == "quality_gate"
    assert payload["metadata_mode"] == "guarded"
    assert payload["metadata_scenario"] == "quality_gate_full"
    assert payload["metadata_cache_mode"] == "CACHE_MISS"
    assert payload["metadata_git_commit"] == "abc123"
    assert payload["metadata_result_path"].endswith("\\result.json")
    assert payload["metadata_findings_path"].endswith("\\findings.json")
    assert payload["metadata_policy_snapshot_path"].endswith("\\policy-snapshot.json")
    assert (
        payload["metadata_policy_source_path"]
        == "policies\\repository-validator\\manifest-policy.json"
    )
    assert payload["result_status"] == "PASS"
    assert payload["migration_run_id"] == payload["metadata_run_id"]
    assert payload["migration_target_path"].endswith("result.json")
    assert payload["findings_status"] == "PASS"
    assert (
        payload["findings_policy_source_path"]
        == "policies/repository-validator/manifest-policy.json"
    )
    assert payload["policy_snapshot_type"] == "REPOSITORY_VALIDATOR_POLICY_SNAPSHOT"
    assert (
        payload["policy_snapshot_policy_source_path"]
        == "policies/repository-validator/manifest-policy.json"
    )


def test_quality_script_restores_repository_validator_cache_hit(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-RepositoryValidatorCacheSubject {
    [ordered]@{
        subject_key = "cache-subject-1"
        subject = [ordered]@{
            schema_version = 1
            git_commit = "abc123"
            repository_policy_sha256 = "policy-hash"
            repository_validator_sha256 = "validator-hash"
            quality_gate_script_sha256 = "quality-script-hash"
            validator_version = "workspace-unreleased"
            cache_scope = "clean_worktree_same_head_policy_and_code"
        }
    }
}

New-Item `
    -ItemType Directory `
    -Path $repositoryValidatorCacheDirectory `
    -Force |
    Out-Null
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $mirrorManifestPath) `
    -Force |
    Out-Null
[ordered]@{
    status = "PASS"
    artifact_count = 3
    repository_health_score = 100
    blockers = @()
    findings = @()
    migration_map = @()
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $repositoryValidatorCacheResultPath -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheFindingsPath `
    -Value '{"status":"PASS"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCachePolicySnapshotPath `
    -Value '{"snapshot_type":"REPOSITORY_VALIDATOR_POLICY_SNAPSHOT"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheMirrorManifestPath `
    -Value '{"schema_version":1}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheMarkdownPath `
    -Value "# Cached Report" `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheMigrationMarkdownPath `
    -Value "# Cached Migration" `
    -Encoding UTF8
[ordered]@{
    schema_version = 1
    status = "PASS"
    subject_key = "cache-subject-1"
    result_sha256 = Get-Sha256Hex -Path $repositoryValidatorCacheResultPath
    findings_sha256 = Get-Sha256Hex -Path $repositoryValidatorCacheFindingsPath
    policy_snapshot_sha256 = Get-Sha256Hex `
        -Path $repositoryValidatorCachePolicySnapshotPath
    mirror_manifest_sha256 = Get-Sha256Hex `
        -Path $repositoryValidatorCacheMirrorManifestPath
    execution_allowed = $false
    promotion_status = "RESEARCH_ONLY"
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $repositoryValidatorCacheMetadataPath -Encoding UTF8

$restored = Restore-RepositoryValidatorCache
Write-RepositoryValidatorRunArtifacts -CacheMode "CACHE_HIT"
$metadata = Get-Content `
    -LiteralPath $repositoryValidatorRunMetadataPath `
    -Raw |
    ConvertFrom-Json
$report = Get-Content `
    -LiteralPath $repositoryValidatorReportPath `
    -Raw |
    ConvertFrom-Json
$mirrorManifest = Get-Content -LiteralPath $mirrorManifestPath -Raw | ConvertFrom-Json
$telemetry = @($script:qualityStepTelemetry)[0]

[ordered]@{
    restored = $restored
    metadata_cache_mode = $metadata.cache_mode
    metadata_subject_key = $metadata.cache_subject_key
    metadata_validator_hash = $metadata.cache_subject.repository_validator_sha256
    metadata_quality_script_hash = $metadata.cache_subject.quality_gate_script_sha256
    report_status = $report.status
    mirror_manifest_schema_version = $mirrorManifest.schema_version
    telemetry_cache_mode = $telemetry.cache_mode
    telemetry_exit_code = $telemetry.exit_code
    telemetry_status = $telemetry.status
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["restored"] is True
    assert payload["metadata_cache_mode"] == "CACHE_HIT"
    assert payload["metadata_subject_key"] == "cache-subject-1"
    assert payload["metadata_validator_hash"] == "validator-hash"
    assert payload["metadata_quality_script_hash"] == "quality-script-hash"
    assert payload["report_status"] == "PASS"
    assert payload["mirror_manifest_schema_version"] == 1
    assert payload["telemetry_cache_mode"] == "CACHE_HIT"
    assert payload["telemetry_exit_code"] == 0
    assert payload["telemetry_status"] == "PASS"


def test_quality_script_cache_subject_records_code_and_policy_hashes(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
New-Item -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorPolicyPath) `
    -Force |
    Out-Null
New-Item -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorModulePath) `
    -Force |
    Out-Null
Set-Content `
    -LiteralPath $repositoryValidatorPolicyPath `
    -Value '{"schema_version":1}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorModulePath `
    -Value 'VALIDATOR_SOURCE' `
    -Encoding UTF8
git -C $repoRoot init | Out-Null
git -C $repoRoot config user.email 'quality@example.invalid'
git -C $repoRoot config user.name 'Quality Gate'
git -C $repoRoot add -A
git -C $repoRoot commit -m 'test cache subject' | Out-Null
$subject = Get-RepositoryValidatorCacheSubject
[ordered]@{
    status = $script:repositoryValidatorCacheStatus
    reason = $script:repositoryValidatorCacheReason
    subject_key_present = -not [string]::IsNullOrWhiteSpace($subject.subject_key)
    policy_hash_present = -not [string]::IsNullOrWhiteSpace(
        $subject.subject.repository_policy_sha256
    )
    validator_hash_present = -not [string]::IsNullOrWhiteSpace(
        $subject.subject.repository_validator_sha256
    )
    quality_script_hash_present = -not [string]::IsNullOrWhiteSpace(
        $subject.subject.quality_gate_script_sha256
    )
    cache_scope = $subject.subject.cache_scope
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["status"] == "ELIGIBLE"
    assert payload["reason"] == "clean worktree subject is cache eligible"
    assert payload["subject_key_present"] is True
    assert payload["policy_hash_present"] is True
    assert payload["validator_hash_present"] is True
    assert payload["quality_script_hash_present"] is True
    assert payload["cache_scope"] == "clean_worktree_same_head_policy_and_code"


def test_quality_script_cache_subject_ignores_blank_git_status_output(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
New-Item -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorPolicyPath) `
    -Force |
    Out-Null
New-Item -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorModulePath) `
    -Force |
    Out-Null
Set-Content -LiteralPath $repositoryValidatorPolicyPath -Value '{}' -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorModulePath `
    -Value 'VALIDATOR_SOURCE' `
    -Encoding UTF8
git -C $repoRoot init | Out-Null
git -C $repoRoot config user.email 'quality@example.invalid'
git -C $repoRoot config user.name 'Quality Gate'
git -C $repoRoot add -A
git -C $repoRoot commit -m 'test blank status cache subject' | Out-Null
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $GitArguments)
    if ($GitArguments -contains 'status') { return '' }
    if ($GitArguments -contains 'rev-parse') { return '0123456789abcdef' }
}
$subject = Get-RepositoryValidatorCacheSubject
[ordered]@{
    status = $script:repositoryValidatorCacheStatus
    subject_key_present = $null -ne $subject -and `
        -not [string]::IsNullOrWhiteSpace($subject.subject_key)
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["status"] == "ELIGIBLE"
    assert payload["subject_key_present"] is True


def test_quality_script_rejects_repository_validator_cache_hash_mismatch(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-RepositoryValidatorCacheSubject {
    [ordered]@{
        subject_key = "cache-subject-1"
        subject = [ordered]@{
            schema_version = 1
            git_commit = "abc123"
            repository_policy_sha256 = "policy-hash"
            repository_validator_sha256 = "validator-hash"
            quality_gate_script_sha256 = "quality-script-hash"
            validator_version = "workspace-unreleased"
            cache_scope = "clean_worktree_same_head_policy_and_code"
        }
    }
}

New-Item -ItemType Directory -Path $repositoryValidatorCacheDirectory -Force |
    Out-Null
Set-Content `
    -LiteralPath $repositoryValidatorCacheResultPath `
    -Value '{"status":"PASS"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheFindingsPath `
    -Value '{"status":"PASS"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCachePolicySnapshotPath `
    -Value '{"snapshot_type":"REPOSITORY_VALIDATOR_POLICY_SNAPSHOT"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheMirrorManifestPath `
    -Value '{"schema_version":1}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheMarkdownPath `
    -Value "# Cached Report" `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorCacheMigrationMarkdownPath `
    -Value "# Cached Migration" `
    -Encoding UTF8
[ordered]@{
    schema_version = 1
    status = "PASS"
    subject_key = "cache-subject-1"
    result_sha256 = "wrong-hash"
    findings_sha256 = Get-Sha256Hex -Path $repositoryValidatorCacheFindingsPath
    policy_snapshot_sha256 = Get-Sha256Hex `
        -Path $repositoryValidatorCachePolicySnapshotPath
    mirror_manifest_sha256 = Get-Sha256Hex `
        -Path $repositoryValidatorCacheMirrorManifestPath
} |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $repositoryValidatorCacheMetadataPath -Encoding UTF8

[ordered]@{
    restored = Restore-RepositoryValidatorCache
    telemetry_count = @($script:qualityStepTelemetry).Count
    latest_exists = Test-Path -LiteralPath $repositoryValidatorReportPath
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["restored"] is False
    assert payload["telemetry_count"] == 0
    assert payload["latest_exists"] is False


def test_quality_script_saves_repository_validator_cache_for_matching_subject(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-RepositoryValidatorCacheSubject {
    [ordered]@{
        subject_key = "cache-subject-1"
        subject = [ordered]@{
            schema_version = 1
            git_commit = "abc123"
            repository_policy_sha256 = "policy-hash"
            repository_validator_sha256 = "validator-hash"
            quality_gate_script_sha256 = "quality-script-hash"
            validator_version = "workspace-unreleased"
            cache_scope = "clean_worktree_same_head_policy_and_code"
        }
    }
}

New-Item -ItemType Directory -Path $repositoryValidatorRunDirectory -Force |
    Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $mirrorManifestPath) -Force |
    Out-Null
[ordered]@{
    status = "PASS"
    artifact_count = 3
    repository_health_score = 100
    blockers = @()
    findings = @()
    migration_map = @()
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunFindingsJsonPath `
    -Value '{"status":"PASS"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunPolicySnapshotPath `
    -Value '{"snapshot_type":"REPOSITORY_VALIDATOR_POLICY_SNAPSHOT"}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $mirrorManifestPath `
    -Value '{"schema_version":1}' `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunMarkdownPath `
    -Value "# Report" `
    -Encoding UTF8
Set-Content `
    -LiteralPath $repositoryValidatorRunMigrationMarkdownPath `
    -Value "# Migration" `
    -Encoding UTF8

Save-RepositoryValidatorCache
$metadata = Get-Content `
    -LiteralPath $repositoryValidatorCacheMetadataPath `
    -Raw |
    ConvertFrom-Json

[ordered]@{
    metadata_status = $metadata.status
    metadata_subject_key = $metadata.subject_key
    result_exists = Test-Path -LiteralPath $repositoryValidatorCacheResultPath
    findings_exists = Test-Path -LiteralPath $repositoryValidatorCacheFindingsPath
    policy_snapshot_exists = Test-Path `
        -LiteralPath $repositoryValidatorCachePolicySnapshotPath
    mirror_manifest_exists = Test-Path `
        -LiteralPath $repositoryValidatorCacheMirrorManifestPath
    result_hash_matches = (
        $metadata.result_sha256 -eq (
            Get-Sha256Hex -Path $repositoryValidatorCacheResultPath
        )
    )
    execution_allowed = $metadata.execution_allowed
    promotion_status = $metadata.promotion_status
    live_eligibility_status = $metadata.live_eligibility_status
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["metadata_status"] == "PASS"
    assert payload["metadata_subject_key"] == "cache-subject-1"
    assert payload["result_exists"] is True
    assert payload["findings_exists"] is True
    assert payload["policy_snapshot_exists"] is True
    assert payload["mirror_manifest_exists"] is True
    assert payload["result_hash_matches"] is True
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_quality_script_evidence_helpers_reject_incomplete_or_mismatched_proof(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
Remove-Item -LiteralPath @(
    $pytestOutputPath,
    $coverageJsonPath,
    $coveragePolicySummaryPath,
    $coveragePolicyMarkdownPath,
    $repositoryValidatorReportPath,
    $governanceGateReportPath,
    $qualityEvidencePath
) -Force -ErrorAction SilentlyContinue

function Get-FileHash {
    [pscustomobject]@{
        Hash = "ABCDEF"
    }
}

function Get-ErrorMessage {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    try {
        & $Action | Out-Null
        return "NO_THROW"
    }
    catch {
        return $_.Exception.Message
    }
}

$messages = [ordered]@{}
$messages.missing_pytest = Get-ErrorMessage { Write-QualityGateGreenEvidence }
Set-Content -LiteralPath $pytestOutputPath -Value "12 passed in 0.10s" -Encoding UTF8
$messages.missing_coverage = Get-ErrorMessage { Write-QualityGateGreenEvidence }
[ordered]@{
    totals = [ordered]@{
        percent_covered = 95.68
    }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $coverageJsonPath -Encoding ASCII
$messages.missing_policy = Get-ErrorMessage { Write-QualityGateGreenEvidence }
$summaryDirectory = Split-Path -Parent $coveragePolicySummaryPath
New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null
[ordered]@{
    total_coverage_percent = 95.68
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $coveragePolicySummaryPath -Encoding ASCII
$messages.missing_realism = Get-ErrorMessage { Write-QualityGateGreenEvidence }
Set-Content `
    -LiteralPath $coveragePolicyMarkdownPath `
    -Value "# Coverage proof" `
    -Encoding UTF8
$messages.missing_validator = Get-ErrorMessage { Write-QualityGateGreenEvidence }
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorReportPath) `
    -Force |
    Out-Null
[ordered]@{
    status = "PASS"
    artifact_count = 862
    repository_health_score = 100
    blockers = @()
    findings = @()
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding ASCII
$messages.missing_governance_gate = Get-ErrorMessage { Write-QualityGateGreenEvidence }
[ordered]@{
    status = "RUNNING_WITH_BLOCKERS"
    blockers = @("DOCS_HYGIENE_FAILED")
    repository_validator = [ordered]@{
        status = "PASS"
    }
    docs_hygiene = [ordered]@{
        passed = $false
    }
    artifact_hygiene = [ordered]@{
        passed = $true
    }
    constitution_sync_tests = [ordered]@{
        passed = $true
    }
    alignment_status = "PASS"
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $governanceGateReportPath -Encoding ASCII
$messages.blocked_governance_gate = Get-ErrorMessage { Write-QualityGateGreenEvidence }
[ordered]@{
    status = "PASS"
    blockers = @()
    repository_validator = [ordered]@{
        status = "PASS"
    }
    docs_hygiene = [ordered]@{
        passed = $true
    }
    artifact_hygiene = [ordered]@{
        passed = $true
    }
    constitution_sync_tests = [ordered]@{
        passed = $true
    }
    alignment_status = "PASS"
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $governanceGateReportPath -Encoding ASCII
[ordered]@{
    total_coverage_percent = 95.0
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $coveragePolicySummaryPath -Encoding ASCII
$messages.coverage_mismatch = Get-ErrorMessage { Write-QualityGateGreenEvidence }

$messages | ConvertTo-Json -Depth 8
""",
    )

    assert payload == {
        "missing_pytest": "Quality gate evidence is missing pytest_pass_count",
        "missing_coverage": "Quality gate evidence is missing coverage_percent",
        "missing_policy": "Quality gate evidence is missing coverage policy summary",
        "missing_realism": (
            "Quality gate evidence is missing governed markdown coverage proof"
        ),
        "missing_validator": (
            "Quality gate evidence is missing repository validator summary"
        ),
        "missing_governance_gate": (
            "Quality gate evidence is missing deterministic quality gate summary"
        ),
        "blocked_governance_gate": (
            "Quality gate evidence requires deterministic quality gate PASS"
        ),
        "coverage_mismatch": (
            "Quality gate coverage_percent does not match "
            "governed markdown proof source"
        ),
    }


def test_quality_script_rejects_inline_approval_generation_parameters(
    tmp_path: Path,
) -> None:
    completed = _run_quality_function_harness_process(
        tmp_path,
        "Invoke-QualityGate\n",
        "-ApprovalBy",
        "Huseyin",
    )

    assert completed.returncode != 0
    assert "Inline approval generation is no longer allowed." in (
        completed.stderr or completed.stdout
    )


def test_quality_script_retries_governance_gate_with_external_approval_artifact(
    tmp_path: Path,
) -> None:
    approval_path = (
        tmp_path / "runtime" / "artifacts" / "quality" / "gate" / "approval.json"
    )
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text('{"approval_records":[]}\n', encoding="utf-8")
    payload = _run_quality_function_harness(
        tmp_path,
        rf"""
$script:governanceCalls = @()
function Invoke-DocsHygieneGateTests {{
    return [ordered]@{{ passed = $true }}
}}
function Invoke-ArtifactHygieneGateTests {{
    return [ordered]@{{ passed = $true }}
}}
function Invoke-ConstitutionSyncGateTests {{
    return [ordered]@{{ passed = $true }}
}}
function Invoke-DeterministicGovernanceGateStep {{
    param(
        [Parameter(Mandatory = $true)]$DocsHygieneEvidence,
        [Parameter(Mandatory = $true)]$ArtifactHygieneEvidence,
        [Parameter(Mandatory = $true)]$ConstitutionSyncEvidence,
        [string]$ApprovalRecordPathOverride,
        [int[]]$AllowedExitCodes = @(0)
    )
    $script:governanceCalls += @(
        [ordered]@{{
            approval_path = $ApprovalRecordPathOverride
        }}
    )
    [ordered]@{{
        status = "RUNNING_WITH_BLOCKERS"
        blockers = @("APPROVAL_REQUIRED")
        approval_verification = [ordered]@{{
            required_approval_count = 1
        }}
    }} |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $governanceGateReportPath -Encoding UTF8
    if (($script:governanceCalls | Measure-Object).Count -eq 1) {{
        return 2
    }}
    return 0
}}
$ApprovalRecordReportPath = @'
{approval_path}
'@
Invoke-DeterministicGovernanceGate
[ordered]@{{
    call_count = ($script:governanceCalls | Measure-Object).Count
    first_approval_path = $script:governanceCalls[0].approval_path
    second_approval_path = $script:governanceCalls[1].approval_path
}} | ConvertTo-Json -Depth 4
""",
    )

    assert payload["call_count"] == 2
    assert payload["first_approval_path"] in (None, "")
    assert payload["second_approval_path"] == str(approval_path.resolve())


def test_quality_script_replays_only_hash_bound_same_subject_full_evidence(
    tmp_path: Path,
) -> None:
    run_dir = (
        tmp_path / "runtime" / "artifacts" / "quality" / "gate" / "runs" / "source-run"
    )
    run_dir.mkdir(parents=True)
    pytest_path = run_dir / "pytest-output.txt"
    bandit_path = run_dir / "bandit-output.txt"
    coverage_path = run_dir / "coverage.json"
    coverage_summary_path = run_dir / "coverage-summary.json"
    coverage_markdown_path = run_dir / "coverage-summary.md"
    quality_path = run_dir / "deterministic-quality-gate.json"
    validator_path = run_dir / "repository-validator.json"
    governance_path = run_dir / "governance-gate-approval-required.json"
    approval_path = run_dir / "approval.json"

    pytest_path.write_text("7 passed in 0.10s\n", encoding="utf-8")
    bandit_path.write_text("", encoding="utf-8")
    coverage_path.write_text(
        json.dumps({"totals": {"percent_covered": 90.0}}),
        encoding="utf-8",
    )
    coverage_summary_path.write_text(
        json.dumps({"total_coverage_percent": 90.0}),
        encoding="utf-8",
    )
    coverage_markdown_path.write_text("# Coverage proof\n", encoding="utf-8")
    validator_path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def relative(path: Path) -> str:
        return path.relative_to(tmp_path).as_posix()

    subject = {
        "repository_tree_sha256": "1" * 64,
        "git_commit": "2" * 40,
        "change_set_sha256": "3" * 64,
        "subject_id": "4" * 64,
    }
    quality_gate_hash = "5" * 64
    governance_gate_hash = "6" * 64
    quality_payload = {
        "status": "PASS",
        "gate_evidence_sha256": quality_gate_hash,
        "subject_digest": subject,
        "security_scan": {
            "passed": True,
            "evidence_path": relative(bandit_path),
            "evidence_sha256": digest(bandit_path),
        },
        "quality_evidence_gate": {
            "quality_gate": {
                "pytest_pass_count": 7,
                "coverage_percent": 90.0,
                "coverage_realism_proof_sha256": digest(coverage_markdown_path),
                "workspace_attestation": {
                    "repository_tree_sha256": "1" * 64,
                    "git_commit": "2" * 40,
                    "change_set_sha256": "7" * 64,
                },
            }
        },
    }
    quality_path.write_text(json.dumps(quality_payload), encoding="utf-8")
    test_evidence = {
        "passed": True,
        "evidence_path": relative(pytest_path),
        "evidence_sha256": digest(pytest_path),
    }
    governance_payload = {
        "status": "RUNNING_WITH_BLOCKERS",
        "blockers": ["APPROVAL_REQUIRED"],
        "gate_evidence_sha256": governance_gate_hash,
        "subject_digest": subject,
        "deterministic_quality_gate": {
            "status": "PASS",
            "gate_evidence_sha256": quality_gate_hash,
        },
        "repository_hygiene": {"status": "PASS"},
        "constitution_sync": {"status": "PASS"},
        "repository_conformance": {"status": "PASS"},
        "repository_validator_gate": {"status": "PASS"},
        "approval_verification": {"required_approval_count": 2},
        "docs_hygiene": {"check_id": "DOCS_HYGIENE", **test_evidence},
        "artifact_hygiene": {"check_id": "ARTIFACT_HYGIENE", **test_evidence},
        "constitution_sync_tests": {
            "check_id": "CONSTITUTION_SYNC",
            **test_evidence,
        },
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    governance_path.write_text(json.dumps(governance_payload), encoding="utf-8")
    approval_path.write_text(
        json.dumps(
            {
                "approval_records": [
                    {
                        "subject_ref": relative(governance_path),
                        "execution_allowed": False,
                        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = _run_quality_function_harness(
        tmp_path,
        rf"""
$ApprovalRecordReportPath = @'
{approval_path}
'@
$script:qualityInitialWorkspaceAttestation = [ordered]@{{
    repository_tree_sha256 = "{"1" * 64}"
    git_commit = "{"2" * 40}"
    change_set_sha256 = "{"7" * 64}"
}}
$context = Get-FullApprovalReplayContext
$acceptedSubject = $context.governance.subject_digest.subject_id
$script:qualityInitialWorkspaceAttestation.change_set_sha256 = "{"9" * 64}"
$subjectDriftError = try {{
    Get-FullApprovalReplayContext | Out-Null
    "NO_ERROR"
}}
catch {{
    $_.Exception.Message
}}
$script:qualityInitialWorkspaceAttestation.change_set_sha256 = "{"7" * 64}"
Set-Content -LiteralPath $context.pytest_path -Value "tampered" -Encoding UTF8
$driftError = try {{
    Get-FullApprovalReplayContext | Out-Null
    "NO_ERROR"
}}
catch {{
    $_.Exception.Message
}}
[ordered]@{{
    accepted_subject = $acceptedSubject
    quality_path = $context.quality_path
    subject_drift_error = $subjectDriftError
    drift_error = $driftError
}} | ConvertTo-Json -Depth 4
""",
    )

    assert payload["accepted_subject"] == "4" * 64
    assert payload["quality_path"].endswith("deterministic-quality-gate.json")
    assert (
        payload["subject_drift_error"] == "APPROVAL_REPLAY_WORKSPACE_ATTESTATION_DRIFT"
    )
    assert payload["drift_error"] == "APPROVAL_REPLAY_ARTIFACT_DRIFT:DOCS_HYGIENE"


def test_prepare_c3_human_governance_closure_request_writes_bound_template(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "prepare_c3_human_governance_closure_request.py")
    governance_gate_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "governance_gate_latest.json"
    )
    governance_gate_path.parent.mkdir(parents=True, exist_ok=True)
    governance_gate_path.write_text(
        json.dumps(
            {
                "gate_evidence_sha256": "1" * 64,
                "change_set": {"change_set_sha256": "2" * 64},
                "subject_digest": {
                    "subject_id": "3" * 64,
                    "authority_family_sha256": "4" * 64,
                },
                "deterministic_quality_gate": {"gate_evidence_sha256": "5" * 64},
                "authority_baseline": {
                    "authority_sources": [
                        "docs/governance/framework_core_vnext_governance.md",
                        "docs/compliance/registry_compliance_matrix.md",
                    ]
                },
                "approval_verification": {
                    "change_class": "C3_GOVERNED",
                    "required_approval_count": 2,
                    "evidence_hash": "6" * 64,
                    "authority_family_sha256": "4" * 64,
                    "lifecycle_definition_sha256": "7" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _run_python_script(
        tmp_path,
        "prepare_c3_human_governance_closure_request.py",
        "--repository-root",
        str(tmp_path),
    )
    markdown_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "c3_human_governance_closure_request_latest.md"
    )
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["artifact_origin"] == "deterministic_governance_closure_request"
    assert payload["required_roles"] == ["GovernanceOwner", "ConstitutionOwner"]
    assert payload["source_governance_gate_report"] == (
        "runtime/artifacts/quality/gate/governance_gate_latest.json"
    )
    assert payload["subject_ref"] == payload["source_governance_gate_report"]
    assert payload["canonical_approval_record_target"] == (
        "runtime/artifacts/quality/gate/approval_record_latest.json"
    )
    assert payload["approval_checklist"][0].startswith("Confirm the subject SHA-256")
    assert any(
        "unique approver_id and a unique principal_id" in item
        for item in payload["approval_checklist"]
    )
    assert payload["subject_sha256"] == "3" * 64
    assert payload["scope_hash"] == "2" * 64
    assert payload["evidence_hash"] == "6" * 64
    assert payload["affected_authority_surfaces"] == [
        "docs/governance/framework_core_vnext_governance.md",
        "docs/compliance/registry_compliance_matrix.md",
    ]
    assert payload["affected_change_surfaces"] == []
    assert payload["behavior_risk_impact"]["risk_level"] == "MEDIUM"
    assert payload["expected_post_approval_state"] == {
        "observed_approval_count": 2,
        "approval_verification": "PASS",
        "approved_transition_hard_veto": False,
    }
    assert len(payload["rollback_plan"]) == 3
    assert len(payload["approval_record_template"]) == 2
    assert (
        payload["approval_record_template"][0]["subject_ref"]
        == payload["source_governance_gate_report"]
    )
    assert payload["approval_record_template"][0]["approver_role"] == "GovernanceOwner"
    assert (
        payload["approval_record_template"][1]["approver_role"] == "ConstitutionOwner"
    )
    assert "# C3 Human Governance Closure Request" in markdown
    assert "## Approval Checklist" in markdown
    assert "## Affected Surfaces" in markdown
    assert "## Behavior And Risk Impact" in markdown
    assert "## Expected Post-Approval State" in markdown
    assert "## Rollback Plan" in markdown
    assert (
        "Confirm the subject SHA-256 matches the reviewed governance gate artifact."
        in markdown
    )
    assert "Required approval count: 2" in markdown
    assert "GovernanceOwner, ConstitutionOwner" in markdown
    assert "Approved transition hard veto: False" in markdown


def test_prepare_c3_human_governance_closure_request_preserves_custom_source_report(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "prepare_c3_human_governance_closure_request.py")
    governance_gate_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "governance_gate_c3_provisional.json"
    )
    governance_gate_path.parent.mkdir(parents=True, exist_ok=True)
    governance_gate_path.write_text(
        json.dumps(
            {
                "gate_evidence_sha256": "1" * 64,
                "subject_digest": {
                    "subject_id": "3" * 64,
                    "authority_family_sha256": "4" * 64,
                },
                "change_set": {
                    "change_set_sha256": "2" * 64,
                    "changed_paths": [
                        "src/ai4binance/governance/gate.py",
                        "tests/test_governance_gate.py",
                    ],
                },
                "deterministic_quality_gate": {"gate_evidence_sha256": "5" * 64},
                "authority_baseline": {
                    "authority_sources": [
                        "docs/governance/framework_core_vnext_governance.md"
                    ]
                },
                "approval_verification": {
                    "change_class": "C3_GOVERNED",
                    "required_approval_count": 2,
                    "evidence_hash": "6" * 64,
                    "authority_family_sha256": "4" * 64,
                    "lifecycle_definition_sha256": "7" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _run_python_script(
        tmp_path,
        "prepare_c3_human_governance_closure_request.py",
        "--repository-root",
        str(tmp_path),
        "--governance-gate-report",
        str(governance_gate_path),
    )

    assert payload["source_governance_gate_report"] == (
        "runtime/artifacts/quality/gate/governance_gate_c3_provisional.json"
    )
    assert payload["subject_ref"] == payload["source_governance_gate_report"]
    assert payload["affected_change_surfaces"] == [
        "src/ai4binance/governance/gate.py",
        "tests/test_governance_gate.py",
    ]
    assert (
        payload["approval_record_template"][1]["subject_ref"]
        == payload["source_governance_gate_report"]
    )


def test_prepare_c3_human_governance_closure_request_backfills_legacy_fields(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "prepare_c3_human_governance_closure_request.py")
    lifecycle_path = tmp_path / "src" / "ai4binance" / "governance_primitives.py"
    lifecycle_path.parent.mkdir(parents=True, exist_ok=True)
    lifecycle_path.write_text(
        "TECHNICAL_QUALITY_PRIMARY_STATUS = 'TECHNICAL_QUALITY_PASS'\n",
        encoding="utf-8",
    )
    governance_gate_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "governance_gate_c3_provisional.json"
    )
    governance_gate_path.parent.mkdir(parents=True, exist_ok=True)
    governance_gate_path.write_text(
        json.dumps(
            {
                "gate_evidence_sha256": "1" * 64,
                "change_set": {"change_set_sha256": "2" * 64},
                "subject_digest": {
                    "subject_id": "3" * 64,
                    "authority_family_sha256": "4" * 64,
                },
                "deterministic_quality_gate": {"gate_evidence_sha256": "5" * 64},
                "authority_baseline": {"authority_sources": []},
                "approval_verification": {
                    "change_class": "C3_GOVERNED",
                    "required_approval_count": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _run_python_script(
        tmp_path,
        "prepare_c3_human_governance_closure_request.py",
        "--repository-root",
        str(tmp_path),
        "--governance-gate-report",
        str(governance_gate_path),
    )
    expected_evidence_hash = hashlib.sha256(
        json.dumps(
            {
                "deterministic_governance_gate_evidence_sha256": "1" * 64,
                "deterministic_quality_gate_evidence_sha256": "5" * 64,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert payload["authority_family_sha256"] == "4" * 64
    assert payload["lifecycle_definition_sha256"]
    assert payload["evidence_hash"] == expected_evidence_hash


def test_prepare_c3_human_governance_closure_request_supports_c2_single_approval(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "prepare_c3_human_governance_closure_request.py")
    governance_gate_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "governance_gate_latest.json"
    )
    governance_gate_path.parent.mkdir(parents=True, exist_ok=True)
    governance_gate_path.write_text(
        json.dumps(
            {
                "gate_evidence_sha256": "1" * 64,
                "change_set": {"change_set_sha256": "2" * 64},
                "subject_digest": {
                    "subject_id": "3" * 64,
                    "authority_family_sha256": "4" * 64,
                },
                "deterministic_quality_gate": {"gate_evidence_sha256": "5" * 64},
                "authority_baseline": {"authority_sources": []},
                "approval_verification": {
                    "change_class": "C2_BEHAVIORAL",
                    "required_approval_count": 1,
                    "evidence_hash": "6" * 64,
                    "authority_family_sha256": "4" * 64,
                    "lifecycle_definition_sha256": "7" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _run_python_script(
        tmp_path,
        "prepare_c3_human_governance_closure_request.py",
        "--repository-root",
        str(tmp_path),
    )
    markdown_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "quality"
        / "gate"
        / "c3_human_governance_closure_request_latest.md"
    )
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["change_class"] == "C2_BEHAVIORAL"
    assert payload["required_approval_count"] == 1
    assert payload["required_roles"] == ["GovernanceOwner"]
    assert payload["expected_post_approval_state"]["observed_approval_count"] == 1
    assert len(payload["approval_record_template"]) == 1
    assert payload["approval_record_template"][0]["approver_role"] == "GovernanceOwner"
    assert "# C2_BEHAVIORAL Human Governance Closure Request" in markdown
    assert "Required approval count: 1" in markdown


def test_quality_script_green_evidence_refreshes_latest_artifact(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-FileHash {
    [pscustomobject]@{
        Hash = "ABCDEF"
    }
}

Set-Content -LiteralPath $pytestOutputPath -Value "12 passed in 0.10s" -Encoding UTF8
[ordered]@{
    totals = [ordered]@{
        percent_covered = 95.68
    }
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $coverageJsonPath -Encoding ASCII
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $coveragePolicySummaryPath) `
    -Force |
    Out-Null
[ordered]@{
    total_coverage_percent = 95.68
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $coveragePolicySummaryPath -Encoding ASCII
Set-Content `
    -LiteralPath $coveragePolicyMarkdownPath `
    -Value "# Coverage proof" `
    -Encoding UTF8
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $governanceGateReportPath) `
    -Force |
    Out-Null
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorReportPath) `
    -Force |
    Out-Null
[ordered]@{
    status = "PASS"
    artifact_count = 862
    repository_health_score = 100
    blockers = @()
    findings = @()
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding ASCII
[ordered]@{
    status = "PASS"
    blockers = @()
    repository_validator = [ordered]@{
        status = "PASS"
    }
    docs_hygiene = [ordered]@{
        passed = $true
    }
    artifact_hygiene = [ordered]@{
        passed = $true
    }
    constitution_sync_tests = [ordered]@{
        passed = $true
    }
    alignment_status = "PASS"
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $governanceGateReportPath -Encoding ASCII
[ordered]@{
    status = "TECHNICAL_QUALITY_PASS"
    generated_at_utc = "2000-01-01T00:00:00Z"
    pytest_pass_count = 1
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $qualityEvidencePath -Encoding UTF8

Write-QualityGateGreenEvidence
$first = Get-Content -LiteralPath $qualityEvidencePath -Raw | ConvertFrom-Json
Start-Sleep -Milliseconds 50
Set-Content -LiteralPath $pytestOutputPath -Value "13 passed in 0.10s" -Encoding UTF8
Write-QualityGateGreenEvidence
$second = Get-Content -LiteralPath $qualityEvidencePath -Raw | ConvertFrom-Json

[ordered]@{
    first_pytest_pass_count = $first.pytest_pass_count
    second_pytest_pass_count = $second.pytest_pass_count
    first_generated_at_utc = $first.generated_at_utc
    second_generated_at_utc = $second.generated_at_utc
    refreshed = $first.generated_at_utc -ne $second.generated_at_utc
} | ConvertTo-Json -Depth 6
""",
    )

    assert payload["first_pytest_pass_count"] == 12
    assert payload["second_pytest_pass_count"] == 13
    assert payload["first_generated_at_utc"] != "2000-01-01T00:00:00Z"
    assert payload["refreshed"] is True


def test_quality_script_refreshes_json_caches_and_reads_pytest_tail(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $repositoryValidatorReportPath) `
    -Force |
    Out-Null
New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $governanceGateReportPath) `
    -Force |
    Out-Null

[ordered]@{
    status = "PASS"
    artifact_count = 3
    repository_health_score = 100
    blockers = @()
    findings = @()
    recommended_actions = @()
} |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding ASCII
[ordered]@{
    status = "PASS"
    blockers = @()
    deterministic_quality_gate = [ordered]@{
        status = "PASS"
    }
    repository_hygiene = [ordered]@{
        status = "PASS"
    }
    constitution_sync = [ordered]@{
        status = "PASS"
    }
    repository_conformance = [ordered]@{
        status = "PASS"
    }
    repository_validator_gate = [ordered]@{
        status = "PASS"
    }
    approval_verification = [ordered]@{
        required_approval_count = 1
        status = "PASS"
        hard_veto = $false
    }
    traceability_audit = [ordered]@{
        status = "PASS"
        hard_veto = $false
    }
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $governanceGateReportPath -Encoding ASCII

$firstValidator = Get-RepositoryValidatorSummary
$firstGovernance = Get-GovernanceGateSummary

[ordered]@{
    status = "RUNNING_WITH_BLOCKERS"
    artifact_count = 4
    repository_health_score = 75
    blockers = @("LOCK_VIOLATION")
    findings = @(
        [ordered]@{
            finding_id = "F1"
        }
    )
    recommended_actions = @(
        [ordered]@{
            action_id = "A1"
        }
    )
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $repositoryValidatorReportPath -Encoding ASCII
[ordered]@{
    status = "RUNNING_WITH_BLOCKERS"
    blockers = @("APPROVAL_REQUIRED")
    deterministic_quality_gate = [ordered]@{
        status = "PASS"
    }
    repository_hygiene = [ordered]@{
        status = "PASS"
    }
    constitution_sync = [ordered]@{
        status = "PASS"
    }
    repository_conformance = [ordered]@{
        status = "PASS"
    }
    repository_validator_gate = [ordered]@{
        status = "RUNNING_WITH_BLOCKERS"
    }
    approval_verification = [ordered]@{
        required_approval_count = 2
        status = "PENDING"
        hard_veto = $true
    }
    traceability_audit = [ordered]@{
        status = "PASS"
        hard_veto = $false
    }
} |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $governanceGateReportPath -Encoding ASCII

$secondValidator = Get-RepositoryValidatorSummary
$secondGovernance = Get-GovernanceGateSummary
$largeOutput = (
    ("setup line`n" * 12000) +
    "3 passed in 0.10s`n" +
    "17 passed in 0.20s`n"
)
Set-Content -LiteralPath $pytestOutputPath -Value $largeOutput -Encoding UTF8
$utf8PassCount = Get-PytestPassCount
Set-Content -LiteralPath $pytestOutputPath -Value $largeOutput -Encoding Unicode
$wideEncodingPassCount = Get-PytestPassCount

[ordered]@{
    first_validator_status = $firstValidator.status
    second_validator_status = $secondValidator.status
    second_validator_artifact_count = $secondValidator.artifact_count
    second_validator_blocker_count = $secondValidator.blocker_count
    second_validator_finding_count = $secondValidator.finding_count
    second_validator_action_count = $secondValidator.recommended_action_count
    first_governance_status = $firstGovernance.status
    second_governance_status = $secondGovernance.status
    second_governance_blocker_count = $secondGovernance.blocker_count
    second_governance_approval_status = $secondGovernance.approval_verification_status
    second_governance_approval_hard_veto = $secondGovernance.approval_hard_veto
    pytest_pass_count = $utf8PassCount
    wide_encoding_pytest_pass_count = $wideEncodingPassCount
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["first_validator_status"] == "PASS"
    assert payload["second_validator_status"] == "RUNNING_WITH_BLOCKERS"
    assert payload["second_validator_artifact_count"] == 4
    assert payload["second_validator_blocker_count"] == 1
    assert payload["second_validator_finding_count"] == 1
    assert payload["second_validator_action_count"] == 1
    assert payload["first_governance_status"] == "PASS"
    assert payload["second_governance_status"] == "RUNNING_WITH_BLOCKERS"
    assert payload["second_governance_blocker_count"] == 1
    assert payload["second_governance_approval_status"] == "PENDING"
    assert payload["second_governance_approval_hard_veto"] is True
    assert payload["pytest_pass_count"] == 17
    assert payload["wide_encoding_pytest_pass_count"] == 17


def test_quality_script_operational_helpers_cover_success_and_failure_paths(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-ErrorMessage {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    try {
        & $Action | Out-Null
        return "NO_THROW"
    }
    catch {
        return $_.Exception.Message
    }
}

$results = [ordered]@{}

Set-Content `
    -LiteralPath (Join-Path $repoRoot ".coverage") `
    -Value "stale" `
    -Encoding ASCII
Set-Content `
    -LiteralPath (Join-Path $repoRoot ".coverage.worker") `
    -Value "stale" `
    -Encoding ASCII
Set-Content `
    -LiteralPath (Join-Path $repoRoot "coverage.xml") `
    -Value "<coverage />" `
    -Encoding ASCII
$htmlCoverage = Join-Path $repoRoot "htmlcov"
New-Item -ItemType Directory -Path $htmlCoverage -Force | Out-Null
Set-Content `
    -LiteralPath (Join-Path $htmlCoverage "index.html") `
    -Value "<html></html>" `
    -Encoding ASCII
Remove-GeneratedCoverageArtifacts
$results.coverage_artifacts_removed = @(
    -not (Test-Path -LiteralPath (Join-Path $repoRoot ".coverage")),
    -not (Test-Path -LiteralPath (Join-Path $repoRoot ".coverage.worker")),
    -not (Test-Path -LiteralPath (Join-Path $repoRoot "coverage.xml")),
    -not (Test-Path -LiteralPath $htmlCoverage)
) -notcontains $false

New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
Set-Content -LiteralPath $pytestOutputPath -Value "no tests ran" -Encoding ASCII
$results.pytest_no_match = $null -eq (Get-PytestPassCount)

$successRunner = Join-Path $repoRoot "success-runner.cmd"
Set-Content `
    -LiteralPath $successRunner `
    -Value "@echo off`r`necho synthetic success`r`nexit /b 0" `
    -Encoding ASCII
$failingRunner = Join-Path $repoRoot "failing-runner.cmd"
Set-Content `
    -LiteralPath $failingRunner `
    -Value "@echo off`r`necho ERROR secret=abc synthetic failure`r`nexit /b 7" `
    -Encoding ASCII
$pytestRunner = Join-Path $repoRoot "pytest-runner.cmd"
Set-Content `
    -LiteralPath $pytestRunner `
    -Value "@echo 3 passed`r`nexit /b 0" `
    -Encoding ASCII

Set-Content -LiteralPath $coverageJsonPath -Value "{}" -Encoding ASCII
$python = $failingRunner
$results.coverage_reader_failure = $null -eq (Get-CoveragePercent)

$python = $successRunner
$results.quality_step_success = Get-ErrorMessage {
    Invoke-QualityStep "Synthetic success" @("--ok")
}
$successStepTelemetry = @($script:qualityStepTelemetry)[-1]
$results.quality_step_success_output_bytes = $successStepTelemetry.output_bytes
$results.quality_step_success_artifact_path = $successStepTelemetry.artifact_path
$results.quality_step_success_output_sha256 = $successStepTelemetry.output_sha256
$python = $failingRunner
$results.quality_step_failure = Get-ErrorMessage {
    Invoke-QualityStep "Synthetic failure" @("--fail")
}
$failureStepTelemetry = @($script:qualityStepTelemetry)[-1]
$results.quality_step_failure_output_bytes = $failureStepTelemetry.output_bytes
$results.quality_step_failure_artifact_path = $failureStepTelemetry.artifact_path
$results.quality_step_failure_output_sha256 = $failureStepTelemetry.output_sha256
$results.quality_step_failure_actionable_error = `
    $failureStepTelemetry.first_actionable_error

$python = $pytestRunner
$results.pytest_success = Get-ErrorMessage { Invoke-PytestWithCapturedOutput }
$results.pytest_captured_output = (
    Get-Content -LiteralPath $pytestOutputPath -Raw
).Trim()
$pytestMetadata = Get-Content `
    -LiteralPath $qualityRunMetadataPath `
    -Raw |
    ConvertFrom-Json
$results.pytest_metadata_status = $pytestMetadata.status
$results.pytest_metadata_current_step = $pytestMetadata.current_step
$python = $failingRunner
$results.pytest_failure = Get-ErrorMessage { Invoke-PytestWithCapturedOutput }
$failureMetadata = Get-Content `
    -LiteralPath $qualityRunMetadataPath `
    -Raw |
    ConvertFrom-Json
$results.pytest_failure_metadata_exit_code = $failureMetadata.pytest_exit_code
$results.pytest_failure_metadata_output_available = `
    $failureMetadata.pytest_output_available
$results.pytest_failure_metadata_output_path = $failureMetadata.pytest_evidence_path
$results.pytest_failure_metadata_step_exit_code = `
    $failureMetadata.step_exit_codes.Pytest
$results.pytest_failure_metadata_step_count = `
    @($failureMetadata.step_telemetry).Count
$results.pytest_failure_metadata_step_status = `
    @($failureMetadata.step_telemetry)[-1].status
$results.pytest_failure_metadata_step_output_bytes = `
    @($failureMetadata.step_telemetry)[-1].output_bytes
$results.pytest_failure_durable_output_exists = Test-Path `
    -LiteralPath $durablePytestOutputPath
$python = $successRunner
$results.bandit_success = Get-ErrorMessage { Invoke-BanditWithCapturedOutput }
$results.bandit_output_exists = Test-Path -LiteralPath $banditOutputPath
$banditEvidence = Get-BanditEvidence
$results.bandit_evidence_source = $banditEvidence.evidence_source
$results.docs_hygiene_success = Get-ErrorMessage { Invoke-DocsHygieneGateTests }
$results.artifact_hygiene_success = Get-ErrorMessage {
    Invoke-ArtifactHygieneGateTests
}
$results.constitution_sync_success = Get-ErrorMessage {
    Invoke-ConstitutionSyncGateTests
}

$cleanupScript = Join-Path $PSScriptRoot "cleanup_generated_artifacts.ps1"
Set-Content -LiteralPath $cleanupScript -Value "exit 0" -Encoding ASCII
$results.cleanup_success = Get-ErrorMessage { Invoke-GeneratedArtifactCleanup }
$results.retention_cleanup_success = Get-ErrorMessage {
    Invoke-TestTempRetentionCleanup
}
$cleanupTelemetry = @($script:qualityStepTelemetry)[-2..-1]
$results.cleanup_success_exit_codes = @(
    $cleanupTelemetry | ForEach-Object { $_.exit_code }
)
$results.cleanup_success_statuses = @(
    $cleanupTelemetry | ForEach-Object { $_.status }
)
Set-Content -LiteralPath $cleanupScript -Value "exit 9" -Encoding ASCII
$results.cleanup_failure = Get-ErrorMessage { Invoke-GeneratedArtifactCleanup }
$results.retention_cleanup_failure = Get-ErrorMessage {
    Invoke-TestTempRetentionCleanup
}

$mirrorDirectory = Split-Path -Parent $mirrorManifestPath
New-Item -ItemType Directory -Path $mirrorDirectory -Force | Out-Null
Set-Content -LiteralPath $mirrorManifestPath -Value "{}" -Encoding ASCII
$python = $successRunner
$results.mirror_with_manifest = Invoke-ConditionalMirrorHygiene

$results | ConvertTo-Json -Depth 8
""",
    )

    assert payload["coverage_artifacts_removed"] is True
    assert payload["pytest_no_match"] is True
    assert payload["coverage_reader_failure"] is True
    assert payload["quality_step_success"] == "NO_THROW"
    assert payload["quality_step_success_output_bytes"] > 0
    assert payload["quality_step_success_artifact_path"].endswith(
        "\\synthetic_success-output.txt"
    )
    assert len(payload["quality_step_success_output_sha256"]) == 64
    assert payload["quality_step_failure"].startswith(
        "Synthetic failure failed with exit code 7. Evidence: "
    )
    assert payload["quality_step_failure"].endswith("\\synthetic_failure-output.txt")
    assert payload["quality_step_failure_output_bytes"] > 0
    assert payload["quality_step_failure_artifact_path"].endswith(
        "\\synthetic_failure-output.txt"
    )
    assert len(payload["quality_step_failure_output_sha256"]) == 64
    assert payload["quality_step_failure_actionable_error"] == (
        "ERROR secret=[REDACTED] synthetic failure"
    )
    assert payload["pytest_success"] == "NO_THROW"
    assert payload["pytest_captured_output"].startswith("3 passed")
    assert payload["pytest_metadata_status"] == "RUNNING"
    assert payload["pytest_metadata_current_step"] == "Pytest"
    assert payload["pytest_failure"].startswith(
        "Pytest failed with exit code 7. Evidence: "
    )
    assert payload["pytest_failure"].endswith("\\pytest-output.txt")
    assert payload["pytest_failure_metadata_exit_code"] == 7
    assert payload["pytest_failure_metadata_output_available"] is True
    assert payload["pytest_failure_metadata_output_path"].startswith(
        "runtime\\artifacts\\quality\\gate\\runs\\"
    )
    assert payload["pytest_failure_metadata_output_path"].endswith(
        "\\pytest-output.txt"
    )
    assert payload["pytest_failure_metadata_step_exit_code"] == 7
    assert payload["pytest_failure_metadata_step_count"] >= 2
    assert payload["pytest_failure_metadata_step_status"] == "FAIL"
    assert payload["pytest_failure_metadata_step_output_bytes"] >= 0
    assert payload["pytest_failure_durable_output_exists"] is True
    assert payload["bandit_success"] == "NO_THROW"
    assert payload["bandit_output_exists"] is True
    assert payload["bandit_evidence_source"] == "BANDIT_STDOUT_STDERR_CAPTURE"
    assert payload["docs_hygiene_success"] == "NO_THROW"
    assert payload["artifact_hygiene_success"] == "NO_THROW"
    assert payload["constitution_sync_success"] == "NO_THROW"
    assert payload["cleanup_success"] == "NO_THROW"
    assert payload["retention_cleanup_success"] == "NO_THROW"
    assert payload["cleanup_success_exit_codes"] == [0, 0]
    assert payload["cleanup_success_statuses"] == ["PASS", "PASS"]
    assert payload["cleanup_failure"].startswith(
        "Generated artifact cleanup failed with exit code 9. Evidence: "
    )
    assert payload["cleanup_failure"].endswith(
        "\\generated_artifact_cleanup-output.txt"
    )
    assert payload["retention_cleanup_failure"].startswith(
        "Test temp retention cleanup failed with exit code 9. Evidence: "
    )
    assert payload["retention_cleanup_failure"].endswith(
        "\\test_temp_retention_cleanup-output.txt"
    )
    assert payload["mirror_with_manifest"] == "VERIFIED"


def test_quality_script_compact_console_output_has_exact_bounded_schema(
    tmp_path: Path,
) -> None:
    passed = _run_quality_function_harness_process(
        tmp_path,
        r"""
$script:qualityStepTelemetry = @(
    [pscustomobject]@{
        step_id = "ruff"
        status = "PASS"
        exit_code = 0
        first_actionable_error = ""
    },
    [pscustomobject]@{
        step_id = "pytest_affected"
        status = "PASS"
        exit_code = 0
        first_actionable_error = ""
    }
)
$script:qualitySelectedPytestArguments = @("tests/test_quality_gate_profiles.py")
Write-CompactQualityConsoleOutput -Status "FAST_PROFILE_PASS"
""",
    )

    assert passed.returncode == 0, passed.stderr
    passed_output = passed.stdout.strip()
    assert len(passed_output.encode("utf-8")) < 1024
    passed_payload = json.loads(passed_output)
    assert set(passed_payload) == {
        "profile",
        "run_id",
        "status",
        "duration",
        "tools",
        "selected_test_count",
        "evidence_path",
    }
    assert passed_payload["status"] == "FAST_PROFILE_PASS"
    assert passed_payload["tools"] == ["ruff", "pytest_affected"]
    assert passed_payload["selected_test_count"] == 1

    failed = _run_quality_function_harness_process(
        tmp_path,
        r"""
$script:qualityStepTelemetry = @(
    [pscustomobject]@{
        step_id = "pytest_affected"
        status = "FAIL"
        exit_code = 7
        first_actionable_error = "ERROR token=abc bounded failure"
    }
)
Write-CompactQualityConsoleOutput `
    -Status "QUALITY_GATE_FAILED" `
    -ErrorMessage "raw failure" `
    -FailureStep "Pytest affected"
""",
    )

    assert failed.returncode == 0, failed.stderr
    failed_output = failed.stdout.strip()
    assert len(failed_output.encode("utf-8")) < 1024
    failed_payload = json.loads(failed_output)
    assert set(failed_payload) == {
        "failed_step",
        "exit_code",
        "first_actionable_error",
        "evidence_path",
    }
    assert failed_payload["failed_step"] == "pytest_affected"
    assert failed_payload["exit_code"] == 7
    assert failed_payload["first_actionable_error"] == (
        "ERROR token=[REDACTED] bounded failure"
    )
    assert failed_payload["evidence_path"].endswith("\\summary.json")


def test_quality_script_prefers_bandit_issue_over_run_header(tmp_path: Path) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
$banditOutput = @'
Run started:2026-09-04 20:09:29.887465+00:00

Test results:
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'TOKEN_ESTIMATE'
   Severity: Low   Confidence: Medium
'@
[ordered]@{
    actionable_error = Get-FirstActionableQualityError -Value $banditOutput
} | ConvertTo-Json -Depth 5
""",
    )

    assert payload["actionable_error"] == (
        ">> Issue: [B105:hardcoded_password_string] Possible hardcoded "
        "password: [REDACTED]"
    )


def test_quality_script_repository_state_guard_fails_closed_on_mutation(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
function Get-ErrorMessage {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    try {
        & $Action | Out-Null
        return "NO_THROW"
    }
    catch {
        return $_.Exception.Message
    }
}

$treeHashA = ("a" * 64) -join ""
$treeHashC = ("c" * 64) -join ""
$changeHashB = ("b" * 64) -join ""
$changeHashD = ("d" * 64) -join ""
$commitOne = ("1" * 40) -join ""
$commitTwo = ("2" * 40) -join ""
$initial = [pscustomobject]@{
    repository_root = $repoRoot
    repository_tree_sha256 = $treeHashA
    git_commit = $commitOne
    change_set_sha256 = $changeHashB
}
$script:qualityInitialWorkspaceAttestation = $initial
$script:currentWorkspaceAttestation = $initial
function Get-QualityWorkspaceAttestation {
    return $script:currentWorkspaceAttestation
}

$stableResult = Get-ErrorMessage {
    Assert-QualityWorkspaceStable -Stage "BEFORE_TEST"
}
$stableEvidenceExists = Test-Path -LiteralPath $repositoryMutationEvidencePath
$script:currentWorkspaceAttestation = [pscustomobject]@{
    repository_root = $repoRoot
    repository_tree_sha256 = $treeHashC
    git_commit = $commitTwo
    change_set_sha256 = $changeHashD
}
$mutationResult = Get-ErrorMessage {
    Assert-QualityWorkspaceStable -Stage "BEFORE_GOVERNANCE"
}
$evidence = Get-Content -LiteralPath $repositoryMutationEvidencePath -Raw |
    ConvertFrom-Json
$guardTelemetry = @($script:qualityStepTelemetry)[-1]
[ordered]@{
    stable_result = $stableResult
    stable_evidence_exists = $stableEvidenceExists
    mutation_result = $mutationResult
    evidence = $evidence
    guard_telemetry = $guardTelemetry
} | ConvertTo-Json -Depth 8
""",
    )

    assert payload["stable_result"] == "NO_THROW"
    assert payload["stable_evidence_exists"] is False
    assert payload["mutation_result"].startswith(
        "REPOSITORY_MUTATED_DURING_QUALITY_GATE at BEFORE_GOVERNANCE."
    )
    assert "runtime\\quality\\" in cast(str, payload["mutation_result"])
    evidence = cast(dict[str, Any], payload["evidence"])
    assert evidence["status"] == "REPOSITORY_MUTATED_DURING_QUALITY_GATE"
    assert evidence["detected_at_stage"] == "BEFORE_GOVERNANCE"
    assert evidence["execution_allowed"] is False
    assert evidence["promotion_status"] == "RESEARCH_ONLY"
    assert evidence["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    initial = cast(dict[str, Any], evidence["initial_workspace_attestation"])
    current = cast(dict[str, Any], evidence["current_workspace_attestation"])
    assert initial["git_commit"] == "1" * 40
    assert current["git_commit"] == "2" * 40
    telemetry = cast(dict[str, Any], payload["guard_telemetry"])
    assert telemetry["step_id"] == "repository_state_guard"
    assert telemetry["status"] == "FAIL"
    assert telemetry["exit_code"] == 1
    assert telemetry["artifact_path"].endswith("\\repository-mutation.json")


def test_quality_script_final_metadata_tracks_completion_step(tmp_path: Path) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
$script:qualityRunCurrentStep = "COMPLETED"
Write-QualityRunMetadata `
    -Status "TECHNICAL_QUALITY_PASS" `
    -CurrentStep $script:qualityRunCurrentStep
New-Item -ItemType Directory -Path $qualityRunDirectory -Force | Out-Null
Set-Content -LiteralPath $durablePytestOutputPath -Value "3 passed" -Encoding ASCII
Set-Content -LiteralPath $banditOutputPath -Value "" -Encoding ASCII
Write-QualityPerformanceArtifacts `
    -Status "TECHNICAL_QUALITY_PASS" `
    -CurrentStep $script:qualityRunCurrentStep
$metadata = Get-Content -LiteralPath $qualityRunMetadataPath -Raw | ConvertFrom-Json
$performance = Get-Content `
    -LiteralPath $qualityPerformanceLatestPath `
    -Raw |
    ConvertFrom-Json
$runtimeLatest = Get-Content `
    -LiteralPath $qualityRuntimeLatestPath `
    -Raw |
    ConvertFrom-Json
$runtimeSummary = Get-Content `
    -LiteralPath $qualityRuntimeRunSummaryPath `
    -Raw |
    ConvertFrom-Json
$runtimeTimings = Get-Content `
    -LiteralPath $qualityRuntimeRunTimingsPath `
    -Raw |
    ConvertFrom-Json
$qualityBudget = Get-Content `
    -LiteralPath $qualityBudgetLatestPath `
    -Raw |
    ConvertFrom-Json
$historyLineCount = @(
    Get-Content -LiteralPath $qualityPerformanceHistoryPath
).Count
$budgetHistoryLineCount = @(
    Get-Content -LiteralPath $qualityBudgetHistoryPath
).Count
$runtimeHistoryLineCount = @(
    Get-Content -LiteralPath $qualityRuntimeHistoryPath
).Count
[ordered]@{
    status = $metadata.status
    current_step = $metadata.current_step
    run_duration_ms = $metadata.run_duration_ms
    step_telemetry_count = @($metadata.step_telemetry).Count
    performance_status = $performance.status
    performance_current_step = $performance.current_step
    performance_run_duration_ms = $performance.run_duration_ms
    performance_step_count = $performance.step_count
    performance_history_line_count = $historyLineCount
    performance_execution_allowed = $performance.execution_allowed
    performance_promotion_status = $performance.promotion_status
    performance_live_eligibility_status = $performance.live_eligibility_status
    budget_status = $qualityBudget.status
    budget_token_risk = $qualityBudget.token_risk
    budget_selected_test_family = $qualityBudget.selected_test_family
    budget_execution_allowed = $qualityBudget.execution_allowed
    budget_promotion_status = $qualityBudget.promotion_status
    budget_live_eligibility_status = $qualityBudget.live_eligibility_status
    budget_history_line_count = $budgetHistoryLineCount
    runtime_latest_status = $runtimeLatest.status
    runtime_latest_has_steps = `
        $runtimeLatest.PSObject.Properties.Name -contains "steps"
    runtime_latest_has_timings_pointer = `
        $runtimeLatest.PSObject.Properties.Name -contains "run_timings_path"
    runtime_latest_compatibility_path = $runtimeLatest.compatibility_latest_path
    runtime_latest_pytest_log_path = $runtimeLatest.pytest_log_path
    runtime_summary_status = $runtimeSummary.status
    runtime_summary_has_steps = `
        $runtimeSummary.PSObject.Properties.Name -contains "steps"
    runtime_summary_has_timings_pointer = `
        $runtimeSummary.PSObject.Properties.Name -contains "run_timings_path"
    runtime_timings_run_id = $runtimeTimings.run_id
    runtime_timings_has_steps = `
        $runtimeTimings.PSObject.Properties.Name -contains "steps"
    runtime_history_line_count = $runtimeHistoryLineCount
    runtime_pytest_log_exists = Test-Path -LiteralPath $qualityRuntimePytestLogPath
    runtime_bandit_log_exists = Test-Path -LiteralPath $qualityRuntimeBanditLogPath
} | ConvertTo-Json -Depth 4
""",
    )

    assert payload["status"] == "TECHNICAL_QUALITY_PASS"
    assert payload["current_step"] == "COMPLETED"
    assert payload["run_duration_ms"] >= 0
    assert payload["step_telemetry_count"] == 0
    assert payload["performance_status"] == "TECHNICAL_QUALITY_PASS"
    assert payload["performance_current_step"] == "COMPLETED"
    assert payload["performance_run_duration_ms"] >= 0
    assert payload["performance_step_count"] == 0
    assert payload["performance_history_line_count"] == 1
    assert payload["performance_execution_allowed"] is False
    assert payload["performance_promotion_status"] == "RESEARCH_ONLY"
    assert payload["performance_live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["budget_status"] == "TECHNICAL_QUALITY_PASS"
    expected_token_risk = "L" + "OW"
    assert payload["budget_token_risk"] == expected_token_risk
    assert payload["budget_selected_test_family"] == "FULL_TEST_SUITE"
    assert payload["budget_execution_allowed"] is False
    assert payload["budget_promotion_status"] == "RESEARCH_ONLY"
    assert payload["budget_live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["budget_history_line_count"] == 1
    assert payload["runtime_latest_status"] == "TECHNICAL_QUALITY_PASS"
    assert payload["runtime_latest_has_steps"] is False
    assert payload["runtime_latest_has_timings_pointer"] is True
    assert (
        payload["runtime_latest_compatibility_path"]
        == "runtime\\artifacts\\quality\\gate\\latest.json"
    )
    assert payload["runtime_latest_pytest_log_path"].endswith("\\pytest.log")
    assert payload["runtime_summary_status"] == "TECHNICAL_QUALITY_PASS"
    assert payload["runtime_summary_has_steps"] is False
    assert payload["runtime_summary_has_timings_pointer"] is True
    assert isinstance(payload["runtime_timings_run_id"], str)
    assert payload["runtime_timings_run_id"]
    assert payload["runtime_timings_has_steps"] is True
    assert payload["runtime_history_line_count"] == 1
    assert payload["runtime_pytest_log_exists"] is True
    assert payload["runtime_bandit_log_exists"] is True


def test_quality_budget_records_repository_validator_cache_observability(
    tmp_path: Path,
) -> None:
    payload = _run_quality_function_harness(
        tmp_path,
        r"""
$script:qualityGateProfile = "fast"
$script:qualitySelectedPytestArguments = @(
    "tests/test_artifact_hygiene_scripts.py::test_quality_budget_cache"
)
$script:repositoryValidatorCacheStatus = "DISABLED"
$script:repositoryValidatorCacheReason = "worktree is not clean"
Set-Content -LiteralPath $pytestOutputPath -Value "148 passed in 1.0s" -Encoding UTF8
$steps = @(
    [pscustomobject]@{
        step_id = "repository_governance_validator"
        name = "Repository governance validator"
        status = "PASS"
        wall_time_ms = 12
        exit_code = 0
        artifact_path = (
            "runtime\artifacts\quality\gate\repository_validator_latest.json"
        )
        cache_mode = "CACHE_MISS"
    }
)
Write-QualityBudgetArtifacts `
    -Status "TECHNICAL_QUALITY_PASS" `
    -CurrentStep "COMPLETED" `
    -Steps $steps `
    -SlowestSteps $steps `
    -OutputBytesTotal 0
$qualityBudget = Get-Content `
    -LiteralPath $qualityBudgetLatestPath `
    -Raw |
    ConvertFrom-Json
[ordered]@{
    selected_test_count = $qualityBudget.selected_test_count
    pytest_test_count = $qualityBudget.pytest_test_count
    selected_test_family = $qualityBudget.selected_test_family
    cache_status = $qualityBudget.repository_validator_cache_status
    cache_reason = $qualityBudget.repository_validator_cache_reason
    cache_mode = $qualityBudget.repository_validator_cache_mode
    token_risk = $qualityBudget.token_risk
    execution_allowed = $qualityBudget.execution_allowed
    promotion_status = $qualityBudget.promotion_status
    live_eligibility_status = $qualityBudget.live_eligibility_status
} | ConvertTo-Json -Depth 6
""",
    )

    assert payload["selected_test_count"] == 1
    assert payload["pytest_test_count"] == 148
    assert payload["selected_test_family"] == "PROFILE_SCOPED_TESTS"
    assert payload["cache_status"] == "DISABLED"
    assert payload["cache_reason"] == "worktree is not clean"
    assert payload["cache_mode"] == "CACHE_MISS"
    expected_token_risk = "L" + "OW"
    assert payload["token_risk"] == expected_token_risk
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_coverage_audit_script_lists_files_below_threshold(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "src/ai4binance/weak.py": {
                        "summary": {
                            "covered_lines": 80,
                            "missing_lines": 20,
                            "num_statements": 100,
                            "percent_covered": 80.0,
                            "covered_branches": 6,
                            "missing_branches": 4,
                            "num_branches": 10,
                        }
                    },
                    "src/ai4binance/strong.py": {
                        "summary": {
                            "covered_lines": 95,
                            "missing_lines": 5,
                            "num_statements": 100,
                            "percent_covered": 95.0,
                            "covered_branches": 9,
                            "missing_branches": 1,
                            "num_branches": 10,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    completed = _run_external_command(
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path("scripts") / "coverage_audit.ps1"),
            "-CoverageJsonPath",
            str(coverage_json),
            "-OutputDirectory",
            str(tmp_path),
            "-Format",
            "Json",
        ]
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )

    payload = json.loads(completed.stdout)
    assert payload["below_threshold_count"] == 1
    assert payload["report_id"] == "AI4B-COVERAGE-AUDIT-DECISION-READY"
    assert payload["threshold_percent"] == 93.0
    assert payload["target_coverage_percent"] == 95.0
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["files"][0]["path"] == "src/ai4binance/weak.py"
    assert payload["files"][0]["coverage_rank"] == 1
    assert payload["files"][0]["risk_rank"] == 1
    assert payload["files"][0]["remediation_rank"] == 1
    assert payload["files"][0]["priority"] == "P3"
    assert payload["files"][0]["tier"] == "T4"
    assert payload["files"][0]["branch_pressure"] == 0.2
    assert payload["files"][0]["target_coverage"] == 95.0
    assert payload["files"][0]["coverage_gap_to_target"] == 15.0
    assert "BRANCH_PATHS" in payload["files"][0]["test_gap_types"]
    assert payload["files"][0]["manual_instruction"].startswith(
        "Raise src/ai4binance/weak.py coverage"
    )
    assert (tmp_path / "coverage_audit_below_93.json").is_file()
    assert "src/ai4binance/weak.py" in (
        tmp_path / "coverage_audit_below_93.md"
    ).read_text(encoding="utf-8-sig")


def test_coverage_audit_defaults_to_durable_gate_artifacts_before_temp() -> None:
    script = (Path("scripts") / "coverage_audit.ps1").read_text(encoding="utf-8")

    durable_gate_root = "runtime\\artifacts\\quality\\gate\\runs"
    durable_quality_root = "runtime\\quality"
    temporary_pytest_root = "runtime\\tmp\\process\\pytest"
    assert script.index(durable_gate_root) < script.index(durable_quality_root)
    assert script.index(durable_quality_root) < script.index(temporary_pytest_root)
    assert "foreach ($searchRoot in $coverageSearchRoots)" in script
    assert "if ($null -ne $latestCoverage)" in script


def test_coverage_audit_table_keeps_path_with_visible_rank_columns() -> None:
    script = (Path("scripts") / "coverage_audit.ps1").read_text(encoding="utf-8")

    selection = script.split("Format-Table -Property `", maxsplit=1)[1].split(
        "-AutoSize", maxsplit=1
    )[0]
    assert selection.index("remediation_rank") < selection.index("path")
    assert selection.index("path") < selection.index("priority")
    assert selection.index("branch_coverage_percent") < selection.index("missing_lines")
    assert "Out-String -Stream -Width 4096" in script


def test_coverage_audit_script_supports_risk_filters(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "src/ai4binance/ops/folder_structure_audit.py": {
                        "summary": {
                            "covered_lines": 80,
                            "missing_lines": 20,
                            "num_statements": 100,
                            "percent_covered": 80.0,
                            "covered_branches": 6,
                            "missing_branches": 4,
                            "num_branches": 10,
                        }
                    },
                    "src/ai4binance/governance/blockers.py": {
                        "summary": {
                            "covered_lines": 90,
                            "missing_lines": 10,
                            "num_statements": 100,
                            "percent_covered": 90.0,
                            "covered_branches": 5,
                            "missing_branches": 5,
                            "num_branches": 10,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    completed = _run_external_command(
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path("scripts") / "coverage_audit.ps1"),
            "-CoverageJsonPath",
            str(coverage_json),
            "-OutputDirectory",
            str(tmp_path),
            "-Format",
            "Json",
            "-SortBy",
            "Risk",
            "-Priority",
            "P0",
        ]
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )

    payload = json.loads(completed.stdout)
    assert [row["path"] for row in payload["files"]] == [
        "src/ai4binance/governance/blockers.py"
    ]
    assert payload["files"][0]["authority_class"] == "GOVERNANCE"


def test_cleanup_script_acl_force_is_bounded_to_test_temp() -> None:
    text = (Path("scripts") / "cleanup_generated_artifacts.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$ForceAcl" in text
    assert "Assert-InTestTempPath" in text
    assert "Test-IsWindowsAdministrator" in text
    assert "Grant-TestTempCleanupAccess" in text
    assert "Remove-DirectoryViaMirrorFallback" in text
    assert "robocopy.exe" in text
    assert "STALE_TEST_TEMP" in text
    assert "REPRODUCIBLE_PYTEST_TEMP" in text
    assert "LEGACY_PYTEST_TEMP" in text
    assert ".tmp-alias-check" in text
    assert (
        "Refusing ACL-forced cleanup outside approved pytest and test temp roots"
        in text
    )
    assert "FORCE_ACL_REQUIRES_ELEVATED_POWERSHELL" in text
    assert (
        "Remove-DirectoryArtifact -Path $source -AllowAclForce $allowAclForce" in text
    )


def test_cleanup_generated_artifacts_test_temp_mode_includes_pytest_temp_roots(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    runtime_pytest = tmp_path / "runtime" / "tmp" / "pytest"
    runtime_pytest.mkdir(parents=True)
    (runtime_pytest / "marker.txt").write_text("pytest", encoding="utf-8")

    root_pytest = tmp_path / ".pytest-basetemp-legacy"
    root_pytest.mkdir()
    (root_pytest / "marker.txt").write_text("pytest", encoding="utf-8")

    runtime_legacy = tmp_path / "runtime" / "pytest-basetemp-legacy"
    runtime_legacy.mkdir(parents=True)
    (runtime_legacy / "marker.txt").write_text("pytest", encoding="utf-8")

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "TestTempRetention")

    assert dry_run["applied"] is False
    assert dry_run["modes"] == ["TestTempRetention"]
    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {
        "runtime/tmp/pytest",
        ".pytest-basetemp-legacy",
        "runtime/pytest-basetemp-legacy",
    }


def test_cleanup_generated_artifacts_process_temp_retention_is_bounded_and_safe(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    process_root = tmp_path / "runtime" / "tmp" / "process"
    stale = process_root / "stale-run"
    active = process_root / "active-run"
    stale.mkdir(parents=True)
    active.mkdir(parents=True)
    stale_file = process_root / "stale.json"
    stale_file.write_text("stale", encoding="utf-8")
    active_owner = {
        "schema_version": 1,
        "component": "pytest",
        "run_id": "active",
        "pid": os.getpid(),
        "expires_at_utc": "2999-01-01T00:00:00+00:00",
    }
    (active / ".ai4binance-process-owner.json").write_text(
        json.dumps(active_owner), encoding="utf-8"
    )
    active_owner_path = active / ".ai4binance-process-owner.json"
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    for path in (stale, stale_file, active_owner_path, active):
        os.utime(path, (old_timestamp, old_timestamp))

    dry_run = _run_cleanup_script(
        tmp_path, "-Mode", "ProcessTempRetention", "-RetentionDays", "2"
    )

    assert dry_run["applied"] is False
    assert dry_run["modes"] == ["ProcessTempRetention"]
    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {"runtime/tmp/process/stale-run", "runtime/tmp/process/stale.json"}

    applied = _run_cleanup_script(
        tmp_path,
        "-Apply",
        "-Mode",
        "ProcessTempRetention",
        "-RetentionDays",
        "2",
    )

    assert applied["applied_count"] == 2
    assert not stale.exists()
    assert not stale_file.exists()
    assert active.is_dir()


def test_cleanup_runtime_tmp_retention_preserves_fresh_and_git_worktrees(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    runtime_tmp = tmp_path / "runtime" / "tmp"
    stale = runtime_tmp / "stale-proof"
    fresh = runtime_tmp / "fresh-proof"
    worktrees = runtime_tmp / "vnext_worktrees"
    stale.mkdir(parents=True)
    fresh.mkdir()
    (worktrees / "registered").mkdir(parents=True)
    worktree_git_file = worktrees / "registered" / ".git"
    worktree_git_file.write_text(
        "gitdir: C:/repo/.git/worktrees/registered\n",
        encoding="utf-8",
    )
    stale_marker = stale / "old.txt"
    stale_marker.write_text("old", encoding="utf-8")
    (fresh / "current.txt").write_text("current", encoding="utf-8")
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    for path in (
        stale_marker,
        stale,
        fresh,
        worktree_git_file,
        worktrees / "registered",
        worktrees,
    ):
        os.utime(path, (old_timestamp, old_timestamp))

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "RuntimeTmpRetention")

    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {"runtime/tmp/stale-proof"}
    assert dry_run["blocked_candidates"] == [
        {
            "path": "runtime\\tmp\\vnext_worktrees",
            "reason": "RUNTIME_TMP_GIT_WORKTREE_REVIEW_REQUIRED",
        }
    ]

    applied = _run_cleanup_script(
        tmp_path,
        "-Mode",
        "RuntimeTmpRetention",
        "-Apply",
    )
    assert applied["applied_count"] == 1
    assert not stale.exists()
    assert fresh.is_dir()
    assert worktrees.is_dir()


def test_cleanup_runtime_run_retention_keeps_latest_twenty(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    runs = tmp_path / "runtime" / "test" / "repository-validator" / "runs"
    old_timestamp = time.time() - (10 * 24 * 60 * 60)
    for index in range(22):
        run = runs / f"run-{index:02d}"
        run.mkdir(parents=True)
        marker = run / "result.json"
        marker.write_text("{}", encoding="utf-8")
        timestamp = old_timestamp + index
        os.utime(marker, (timestamp, timestamp))
        os.utime(run, (timestamp, timestamp))

    dry_run = _run_cleanup_script(tmp_path, "-Mode", "RuntimeRunRetention")

    assert {
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    } == {
        "runtime/test/repository-validator/runs/run-00",
        "runtime/test/repository-validator/runs/run-01",
    }


def test_cleanup_runtime_run_retention_rejects_policy_path_widening(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    manifest_path = (
        tmp_path / "config" / "governance" / "runtime_artifact_layout_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["retention"]["repository_validator_test_runs"]["path"] = "runtime"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    completed = _run_external_command(
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "scripts" / "cleanup_generated_artifacts.ps1"),
            "-Mode",
            "RuntimeRunRetention",
        ],
        cwd=tmp_path,
    )

    assert completed.returncode != 0
    assert (
        "Runtime run retention policy path must be "
        "runtime/test/repository-validator/runs"
    ) in completed.stderr


def test_cleanup_generated_artifacts_log_mode_uses_canonical_runtime_logs(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    runtime_log = tmp_path / "runtime" / "logs" / "stale.jsonl"
    legacy_log = tmp_path / "logs" / "legacy.jsonl"
    runtime_log.parent.mkdir(parents=True)
    legacy_log.parent.mkdir(parents=True)
    runtime_log.write_text("runtime", encoding="utf-8")
    legacy_log.write_text("legacy", encoding="utf-8")
    old_timestamp = time.time() - (8 * 24 * 60 * 60)
    os.utime(runtime_log, (old_timestamp, old_timestamp))
    os.utime(legacy_log, (old_timestamp, old_timestamp))

    dry_run = _run_cleanup_script(
        tmp_path, "-Mode", "LogsArchive", "-LogRetentionDays", "7"
    )

    assert [
        candidate["path"].replace("\\", "/") for candidate in dry_run["candidates"]
    ] == ["runtime/logs/stale.jsonl"]


def test_runtime_hygiene_dispatcher_is_bounded_and_scheduler_is_explicit() -> None:
    dispatcher = (Path("scripts") / "runtime_hygiene_maintenance.ps1").read_text(
        encoding="utf-8"
    )
    installer = (
        Path("scripts") / "install_runtime_hygiene_maintenance_task.ps1"
    ).read_text(encoding="utf-8")

    assert '"RuntimeTmpRetention", "RuntimeRunRetention"' in dispatcher
    assert "Local\\AI4BINANCE-Runtime-Hygiene-Maintenance" in dispatcher
    assert "$mutex.WaitOne(0)" in dispatcher
    assert "WhatIfSummaryPath" in dispatcher
    assert "$retentionInvocationSucceeded = $?" in dispatcher
    assert "$capacityInvocationSucceeded = $?" in dispatcher
    assert "$capacityExitCode = $LASTEXITCODE" in dispatcher
    assert "capacity_access_error_count" in dispatcher
    assert "owner_review_family_count" in dispatcher
    assert "ai4binance.ops.runtime_hygiene" in dispatcher
    assert '"LogsArchive"' not in dispatcher
    assert "AI4BINANCE-Runtime-Hygiene-Maintenance" in installer
    assert "-Apply" in installer
    assert "-MultipleInstances IgnoreNew" in installer
    assert "New-ScheduledTaskTrigger -Daily" in installer


def test_cleanup_runtime_cache_and_test_modes_are_separate_and_age_bounded(
    tmp_path: Path,
) -> None:
    _copy_cleanup_script(tmp_path)
    stale_cache = tmp_path / "runtime" / "cache" / "stale"
    fresh_test = tmp_path / "runtime" / "test" / "fresh"
    stale_cache.mkdir(parents=True)
    fresh_test.mkdir(parents=True)
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    os.utime(stale_cache, (old_timestamp, old_timestamp))

    cache_run = _run_cleanup_script(
        tmp_path, "-Mode", "RuntimeCacheRetention", "-RetentionDays", "2"
    )
    test_run = _run_cleanup_script(
        tmp_path, "-Mode", "RuntimeTestRetention", "-RetentionDays", "2"
    )

    assert [
        candidate["path"].replace("\\", "/") for candidate in cache_run["candidates"]
    ] == ["runtime/cache/stale"]
    assert test_run["candidates"] == []


def test_runtime_hygiene_migration_routes_machine_outputs_and_keeps_reports(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "migrate_runtime_hygiene_layout.ps1")
    dataset = tmp_path / "runtime" / "datasets" / "futures" / "sample.json"
    report = tmp_path / "runtime" / "reports" / "market-history" / "readme.md"
    probe = tmp_path / "runtime" / "reports" / "market-history" / "probe.json"
    dataset.parent.mkdir(parents=True)
    report.parent.mkdir(parents=True)
    dataset.write_text("{}", encoding="utf-8")
    report.write_text("# Human report\n", encoding="utf-8")
    probe.write_text("{}", encoding="utf-8")

    completed = _run_external_command(
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "scripts" / "migrate_runtime_hygiene_layout.ps1"),
            "-Apply",
        ]
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["migrated_file_count"] == 2
    migrated_dataset = (
        tmp_path / "runtime" / "data" / "datasets" / "futures" / "sample.json"
    )
    assert migrated_dataset.is_file()
    assert (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "market_history"
        / "probe.json"
    ).is_file()
    assert report.is_file()


def test_runtime_hygiene_migration_quarantines_conflicting_legacy_dataset(
    tmp_path: Path,
) -> None:
    _copy_script(tmp_path, "migrate_runtime_hygiene_layout.ps1")
    legacy = tmp_path / "runtime" / "datasets" / "futures" / "sample.json"
    canonical = tmp_path / "runtime" / "data" / "datasets" / "futures" / "sample.json"
    legacy.parent.mkdir(parents=True)
    canonical.parent.mkdir(parents=True)
    legacy.write_text('{"revision":"legacy"}', encoding="utf-8")
    canonical.write_text('{"revision":"canonical"}', encoding="utf-8")

    completed = _run_external_command(
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "scripts" / "migrate_runtime_hygiene_layout.ps1"),
            "-Apply",
        ]
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["conflict_count"] == 1
    record = payload["files"][0]
    assert record["migration_status"] == "QUARANTINE_DESTINATION_CONFLICT"
    assert not legacy.exists()
    assert canonical.read_text(encoding="utf-8") == '{"revision":"canonical"}'
    quarantine = tmp_path / record["conflict_path"]
    assert quarantine.read_text(encoding="utf-8") == '{"revision":"legacy"}'


def test_qwen_prompter_startup_task_is_visible_and_advisory_only() -> None:
    install_text = (
        Path("scripts") / "install_qwen_prompter_startup_task.ps1"
    ).read_text(encoding="utf-8")
    prompter_text = (Path("scripts") / "start_qwen_prompter.ps1").read_text(
        encoding="utf-8"
    )
    llama_server_text = (Path("scripts") / "start_llama_server.ps1").read_text(
        encoding="utf-8"
    )
    local_llm_text = (Path("scripts") / "start_local_llm.ps1").read_text(
        encoding="utf-8"
    )
    status_text = (Path("scripts") / "startup_status.ps1").read_text(encoding="utf-8")

    assert 'qwen3:8b"' in install_text
    assert "AI4BINANCE-Qwen3-Prompter" in install_text
    assert "New-ScheduledTaskTrigger -AtLogOn" in install_text
    assert "-File" in install_text
    assert "-WindowStyle Hidden" not in install_text
    assert "-NoExit" not in install_text
    assert "-NonInteractive" not in install_text
    assert "-Hidden" not in install_text
    assert "visible_prompt = $true" in install_text
    assert 'AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"' in prompter_text
    assert 'AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"' in prompter_text
    assert 'AI4BINANCE_ORDER_AUTHORITY = "BLOCKED"' in prompter_text
    assert 'AI4BINANCE_RISK_AUTHORITY = "BLOCKED"' in prompter_text
    assert 'AI4BINANCE_LIVE_AUTHORITY = "BLOCKED"' in prompter_text
    assert "auto_learn = [ordered]@{" in prompter_text
    assert '"generate_hypotheses"' in prompter_text
    assert "external_memory = $true" in prompter_text
    assert "LIVE_ORDER_BLOCKED" in prompter_text
    assert "New-SystemPrompt" in prompter_text
    assert "docs\\runbooks\\runbook_read_only_runtime.md" in prompter_text
    assert '$stateDirectory = Join-Path $root "runtime\\state"' in prompter_text
    assert 'Join-Path $stateDirectory "runtime.json"' in prompter_text
    assert (
        "runtime\\artifacts\\decisions\\market_outlook\\runtime-state.json"
        in prompter_text
    )
    assert "start_llama_server.ps1" in prompter_text
    assert "http://127.0.0.1:8080/completion" in prompter_text
    assert "Invoke-LlamaCompletion" in prompter_text
    assert "Start-Job" in prompter_text
    assert "Start-Sleep -Seconds 30" in prompter_text
    assert "System.Net.Http.HttpClient" in prompter_text
    assert "System.Net.Http.StringContent" in prompter_text
    assert '"application/json"' in prompter_text
    assert "Private state and Secrets are out of scope" in prompter_text
    assert "Read-Host" in prompter_text
    assert "LLAMA_CPP_CHAT_FAILED" in prompter_text
    assert "Provider: llama.cpp" in prompter_text
    assert "Sadece Turkce cevap ver." in prompter_text
    assert "Ilk cumlede dogrudan cevabi ver." in prompter_text
    assert (
        "Basit durum, evet/hayir ve ozet sorularinda en fazla 2 kisa cumle kullan."
        in prompter_text
    )
    assert "Trading sorularinda sadece gerekli alanlari kullan" in prompter_text
    assert "llama.cpp server failed to start" in prompter_text
    assert "LLAMA_CPP_SERVER_START_FAILED" in local_llm_text
    assert "llama.cpp" in local_llm_text
    assert "Get-AI4BinanceQwen3BlobPath" in llama_server_text
    assert "notifyIcon" not in install_text
    assert 'commandCandidates = @("llama-server.exe", "llama.exe")' in llama_server_text
    assert "Get-Command $commandName" in llama_server_text
    assert "tools\\llama.cpp" in llama_server_text
    assert "Qwen3-8B-Q4_K_M.gguf" in llama_server_text
    assert "AI4BINANCE_LLAMA_GPU_LAYERS" in llama_server_text
    assert "AI4BINANCE_LLAMA_PARALLEL" in llama_server_text
    assert "AI4BINANCE_LLAMA_THREADS" in llama_server_text
    assert "RequireQwenPrompterTask" in status_text
    assert "AI4BINANCE-Qwen3-Prompter" in status_text
    assert "qwen-prompter-health.json" in status_text

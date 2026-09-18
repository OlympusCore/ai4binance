"""Failure-path coverage for the Python runtime removal evidence gate."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.ops import python_runtime_removal_gate as gate


@pytest.mark.parametrize(
    "factory",
    [
        lambda: gate.RemovalGateCheck("UNKNOWN", "PASS", (), {}),
        lambda: gate.RemovalGateCheck("RUFF", "UNKNOWN", (), {}),
        lambda: gate.RemovalGateCheck("RUFF", "PASS", ("BLOCKER",), {}),
        lambda: gate.RemovalGateCheck("RUFF", "BLOCKED", (), {}),
    ],
)
def test_removal_gate_check_rejects_invalid_shapes(
    factory: Callable[[], gate.RemovalGateCheck],
) -> None:
    with pytest.raises(ValueError, match=r"UNKNOWN|INVALID|BLOCKER"):
        factory()


def test_check_helper_rejects_blocked_pass_and_supplies_default_blocker() -> None:
    with pytest.raises(ValueError, match="CANNOT_HAVE_BLOCKERS"):
        gate._check("RUFF", passed=True, blockers=("INVALID",))
    check = gate._check("RUFF", passed=False)
    assert check.blockers == ("RUFF_NOT_PROVEN",)
    assert check.evidence == {}


def test_load_json_rejects_missing_invalid_and_non_object_evidence(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="EVIDENCE_FILE_MISSING"):
        gate._load_json(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="EVIDENCE_FILE_INVALID"):
        gate._load_json(invalid)
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="EVIDENCE_OBJECT_REQUIRED"):
        gate._load_json(invalid)

    utf16 = tmp_path / "utf16.json"
    utf16.write_text('{"status":"PASS"}', encoding="utf-16")
    assert gate._load_json(utf16) == {"status": "PASS"}


def test_load_json_rejects_oversized_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "large.json"
    path.write_text("{}", encoding="utf-8")
    original_stat = Path.stat

    def stat(candidate: Path) -> object:
        if candidate == path:
            return SimpleNamespace(st_size=gate._MAX_EVIDENCE_BYTES + 1)
        return original_stat(candidate)

    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(ValueError, match="EVIDENCE_FILE_TOO_LARGE"):
        gate._load_json(path)


def test_repository_path_and_git_helpers_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    with pytest.raises(ValueError, match="OUTSIDE_REPOSITORY"):
        gate._resolve_repository_path(root, root.parent / "outside.json")

    monkeypatch.setattr(gate, "shutil_which_required", lambda _command: "git")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "error"),
    )
    with pytest.raises(ValueError, match="GIT_COMMAND_FAILED"):
        gate._git(root, "status")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, "x" * (gate._MAX_CAPTURE_BYTES + 1), ""
        ),
    )
    with pytest.raises(ValueError, match="GIT_OUTPUT_TOO_LARGE"):
        gate._git(root, "status")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "ok\n", ""),
    )
    assert gate._git(root, "status") == "ok\n"


def test_required_command_and_repository_state_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda _command: None)
    with pytest.raises(ValueError, match="COMMAND_NOT_FOUND"):
        gate.shutil_which_required("missing")
    monkeypatch.setattr("shutil.which", lambda _command: "tool.exe")
    assert gate.shutil_which_required("tool") == "tool.exe"

    monkeypatch.setattr(
        gate,
        "_git",
        lambda _root, *arguments: (
            "revision\n" if arguments[0] == "rev-parse" else " M changed.py\n\n"
        ),
    )
    assert gate._repository_state(tmp_path) == ("revision", (" M changed.py",), ())
    monkeypatch.setattr(
        gate,
        "_git",
        lambda *_args: (_ for _ in ()).throw(ValueError("GIT_FAILED")),
    )
    assert gate._repository_state(tmp_path) == ("UNKNOWN", (), ("GIT_FAILED",))


@pytest.mark.parametrize(
    ("process", "expected"),
    [
        (OSError("cannot start"), "CANONICAL_PYTHON_PROBE_FAILED"),
        (
            subprocess.CompletedProcess([], 0, "x" * (gate._MAX_CAPTURE_BYTES + 1), ""),
            "CANONICAL_PYTHON_PROBE_OUTPUT_TOO_LARGE",
        ),
        (
            subprocess.CompletedProcess([], 1, "{}", "failed"),
            "CANONICAL_PYTHON_PROBE_FAILED",
        ),
        (
            subprocess.CompletedProcess([], 0, "{", ""),
            "CANONICAL_PYTHON_PROBE_INVALID",
        ),
        (
            subprocess.CompletedProcess([], 0, "[]", ""),
            "CANONICAL_PYTHON_PROBE_INVALID",
        ),
    ],
)
def test_python_json_probe_maps_process_and_payload_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    process: object,
    expected: str,
) -> None:
    executable = tmp_path / "python.exe"
    executable.write_bytes(b"")

    def run(*_args: object, **_kwargs: object) -> object:
        if isinstance(process, BaseException):
            raise process
        return process

    monkeypatch.setattr(subprocess, "run", run)
    payload, blockers = gate._run_python_json(executable, tmp_path, "print('{}')")
    assert payload is None
    assert blockers == (expected,)


def test_python_json_probe_accepts_object_and_runtime_probe_normalizes_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path.parent / "python.exe"
    outside.write_bytes(b"")
    assert gate._run_python_json(outside, tmp_path, "") == (
        None,
        ("CANONICAL_PYTHON_INVALID",),
    )
    executable = tmp_path / "python.exe"
    executable.write_bytes(b"")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, '{"status":"PASS"}', ""
        ),
    )
    assert gate._run_python_json(executable, tmp_path, "")[0] == {"status": "PASS"}

    monkeypatch.setattr(
        gate, "_run_python_json", lambda *_args, **_kwargs: (None, ("X",))
    )
    assert gate._runtime_probe(executable, tmp_path) == ({}, ("X",))
    monkeypatch.setattr(
        gate, "_run_python_json", lambda *_args, **_kwargs: ({"version": "3.14.7"}, ())
    )
    assert gate._runtime_probe(executable, tmp_path)[0]["version"] == "3.14.7"


def test_dependency_check_maps_subprocess_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("pip unavailable")),
    )
    assert gate._dependency_check(tmp_path / "python.exe", tmp_path).blockers == (
        "DEPENDENCY_CHECK_FAILED",
    )


def test_quality_context_reports_missing_and_malformed_evidence(tmp_path: Path) -> None:
    missing = gate._quality_context(
        tmp_path,
        tmp_path / "missing.json",
        current_revision="revision",
        changed_paths=(),
    )
    assert "EVIDENCE_FILE_MISSING" in missing.blockers[0]

    malformed = tmp_path / "quality.json"
    malformed.write_text(
        json.dumps(
            {
                "status": "FAILED",
                "profile": "standard",
                "verification_status": "NOT_VERIFIED",
                "selected_pytest_arguments": [],
                "step_telemetry": ["invalid"],
            }
        ),
        encoding="utf-8",
    )
    context = gate._quality_context(
        tmp_path,
        malformed,
        current_revision="revision",
        changed_paths=(" M changed.py",),
    )
    assert {
        "FULL_QUALITY_STATUS_NOT_PASSING",
        "FULL_QUALITY_PROFILE_REQUIRED",
        "FULL_QUALITY_VERIFICATION_REQUIRED",
        "FULL_TEST_SUITE_EVIDENCE_REQUIRED",
        "DETERMINISTIC_QUALITY_EVIDENCE_MISSING",
        "FULL_QUALITY_CURRENT_REPOSITORY_DIRTY",
    }.issubset(context.blockers)


def test_quality_context_detects_bad_deterministic_hash_and_payload(
    tmp_path: Path,
) -> None:
    deterministic = tmp_path / "deterministic.json"
    deterministic.write_text(json.dumps({"status": "BLOCKED"}), encoding="utf-8")
    quality = tmp_path / "quality.json"
    rows = [
        {"step_id": step, "status": "PASS", "exit_code": 0}
        for step in ("dependency_check", "ruff_format", "ruff_lint", "mypy", "pytest")
    ]
    rows.append(
        {
            "step_id": "deterministic_quality_gate",
            "status": "PASS",
            "exit_code": 0,
            "artifact_path": deterministic.name,
            "output_sha256": "0" * 64,
        }
    )
    quality.write_text(
        json.dumps(
            {
                "status": "TECHNICAL_QUALITY_PASS",
                "profile": "full",
                "verification_status": "FULL_VERIFIED",
                "selected_pytest_arguments": ["FULL_TEST_SUITE"],
                "step_telemetry": rows,
            }
        ),
        encoding="utf-8",
    )
    context = gate._quality_context(
        tmp_path,
        quality,
        current_revision="revision",
        changed_paths=(),
    )
    assert "DETERMINISTIC_QUALITY_EVIDENCE_HASH_MISMATCH" in context.blockers
    assert "DETERMINISTIC_QUALITY_GATE_NOT_PASSING" in context.blockers
    assert "FULL_QUALITY_EVIDENCE_CODE_REVISION_MISMATCH" in context.blockers
    assert "FULL_QUALITY_EVIDENCE_CHANGE_SET_NOT_CLEAN" in context.blockers


def test_all_test_inventory_predicates_count_matching_files(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    (tests / "contract").mkdir(parents=True)
    (tests / "test_unit.py").write_text("pytest.mark.unit\n", encoding="utf-8")
    (tests / "contract" / "test_api.py").write_text("", encoding="utf-8")
    (tests / "test_schema.py").write_text("", encoding="utf-8")
    (tests / "test_integration.py").write_text(
        "pytest.mark.integration_like\n", encoding="utf-8"
    )
    (tests / "test_binance.py").write_text("", encoding="utf-8")
    (tests / "test_paper.py").write_text("", encoding="utf-8")

    assert gate._test_inventory(tmp_path, "unit") == 1
    assert gate._test_inventory(tmp_path, "contract_schema") == 2
    assert gate._test_inventory(tmp_path, "integration") == 1
    assert gate._test_inventory(tmp_path, "binance") == 1
    assert gate._test_inventory(tmp_path, "paper") == 1


def test_differential_context_reports_missing_and_invalid_bindings(
    tmp_path: Path,
) -> None:
    missing = gate._differential_context(
        tmp_path / "missing.json",
        tmp_path / "also-missing.json",
        current_revision="revision",
        changed_paths=(),
    )
    assert missing.replay_pass is False

    latest = tmp_path / "latest.json"
    stability = tmp_path / "stability.json"
    latest.write_text(
        json.dumps(
            {
                "status": "BLOCKED",
                "blockers": ["X"],
                "code_revision": "old",
                "clock_source": "wall",
                "latest_verification": "invalid",
                "baseline_runtime": "invalid",
                "current_runtime": "invalid",
                "comparisons": [
                    "invalid",
                    {
                        "passed": False,
                        "blockers": ["X"],
                        "baseline_semantic_sha256": "a",
                        "current_semantic_sha256": "b",
                        "benchmark_name": "event-replay-order-state",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    stability.write_text(
        json.dumps(
            {
                "status": "BLOCKED",
                "blockers": ["X"],
                "code_revision": "different",
                "benchmark_driver_sha256": "different",
                "clock_source": "different",
                "max_regression_percent": 99,
            }
        ),
        encoding="utf-8",
    )
    context = gate._differential_context(
        latest,
        stability,
        current_revision="revision",
        changed_paths=(" M changed.py",),
    )
    assert context.replay_pass is False
    assert {
        "DIFFERENTIAL_EVIDENCE_NOT_PASSING",
        "DIFFERENTIAL_COMPARISON_INVALID",
        "DIFFERENTIAL_COMPARISON_NOT_PASSING",
        "PYTHON_RUNTIME_BEHAVIOR_DRIFT",
        "DIFFERENTIAL_CURRENT_REPOSITORY_DIRTY",
    }.issubset(context.blockers)


def test_ci_reference_artifact_and_path_checks_cover_failure_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gate._ci_check(tmp_path).blockers == ("CI_PYTHON_WORKFLOW_MISSING",)

    monkeypatch.setattr(
        gate,
        "_git",
        lambda *_args: (_ for _ in ()).throw(ValueError("GIT_SCAN_FAILED")),
    )
    assert gate._hardcoded_reference_check(tmp_path).blockers == ("GIT_SCAN_FAILED",)

    walked = False

    def walk(
        root: Path, *, topdown: bool, onerror: Callable[[OSError], None]
    ) -> object:
        nonlocal walked
        assert topdown is True
        walked = True
        onerror(OSError(5, "denied", str(root / "blocked")))
        yield str(root), ["cache-python312"], ["module.cp312-win_amd64.pyd"]

    monkeypatch.setattr(os, "walk", walk)
    artifact = gate._active_artifact_check(tmp_path)
    assert walked
    assert "ACTIVE_CP312_ARTIFACT_PRESENT" in artifact.blockers
    assert "ACTIVE_CP312_ARTIFACT_SCAN_FAILED" in artifact.blockers

    monkeypatch.setenv("PATH", os.pathsep.join(("C:/Python312", "C:/Python314")))
    assert gate._path_dependency_check().blockers == ("PYTHON312_PATH_ENTRY_PRESENT",)


def test_ci_and_artifact_scans_cover_irrelevant_legacy_and_bounded_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "docs.yml").write_text("name: docs\n", encoding="utf-8")
    (workflows / "python.yml").write_text("run: python 3.12.10\n", encoding="utf-8")
    ci = gate._ci_check(tmp_path)
    assert any("CI_CANONICAL_RUNTIME_MISSING" in item for item in ci.blockers)
    assert any("CI_LEGACY_RUNTIME_REFERENCE_PRESENT" in item for item in ci.blockers)

    source = tmp_path / "src" / "large.py"
    source.parent.mkdir(parents=True)
    source.write_text("safe", encoding="utf-8")
    original_stat = Path.stat

    def stat(path: Path) -> object:
        if path == source:
            return SimpleNamespace(st_size=gate._MAX_EVIDENCE_BYTES + 1)
        return original_stat(path)

    monkeypatch.setattr(gate, "_git", lambda *_args: "src/large.py\0")
    monkeypatch.setattr(Path, "stat", stat)
    assert gate._hardcoded_reference_check(tmp_path).status == "PASS"
    monkeypatch.undo()

    artifact_names = [f"module-{index}.cp312.pyd" for index in range(200)]
    monkeypatch.setattr(
        os,
        "walk",
        lambda *_args, **_kwargs: iter(((str(tmp_path), [], artifact_names),)),
    )
    artifact = gate._active_artifact_check(tmp_path)
    assert artifact.status == "BLOCKED"
    assert artifact.evidence["count"] == 200


def test_assess_removal_gate_builds_complete_checklist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate, "_repository_state", lambda _root: ("revision", (), ()))
    monkeypatch.setattr(gate, "_runtime_probe", lambda *_args: ({}, ()))
    quality = gate._QualityContext(
        (),
        {"ruff_format": True, "ruff_lint": True, "mypy": True, "pytest": True},
        True,
        {},
    )
    differential = gate._DifferentialContext((), True, {})
    monkeypatch.setattr(gate, "_quality_context", lambda *_args, **_kwargs: quality)
    monkeypatch.setattr(
        gate, "_differential_context", lambda *_args, **_kwargs: differential
    )
    monkeypatch.setattr(
        gate,
        "_canonical_runtime_check",
        lambda *_args: gate._check("CPYTHON_3_14_7", passed=True),
    )
    monkeypatch.setattr(
        gate, "_venv_check", lambda *_args: gate._check("FRESH_VENV", passed=True)
    )
    monkeypatch.setattr(
        gate,
        "_dependency_check",
        lambda *_args: gate._check("DEPENDENCY_RESOLUTION", passed=True),
    )
    monkeypatch.setattr(
        gate, "_import_check", lambda *_args: gate._check("FULL_IMPORTS", passed=True)
    )
    monkeypatch.setattr(gate, "_test_inventory", lambda *_args: 1)
    monkeypatch.setattr(
        gate,
        "_vscode_check",
        lambda *_args: gate._check("VSCODE_INTERPRETER", passed=True),
    )
    monkeypatch.setattr(
        gate, "_ci_check", lambda *_args: gate._check("CI_RUNTIME", passed=True)
    )
    monkeypatch.setattr(
        gate,
        "_hardcoded_reference_check",
        lambda *_args: gate._check("HARD_CODED_PYTHON_312_REFS", passed=True),
    )
    monkeypatch.setattr(
        gate,
        "_active_artifact_check",
        lambda *_args: gate._check("ACTIVE_CP312_ARTIFACTS", passed=True),
    )
    monkeypatch.setattr(
        gate,
        "_path_dependency_check",
        lambda: gate._check("PYTHON312_PATH_DEPENDENCY", passed=True),
    )

    result = gate.assess_removal_gate(
        repository_root=tmp_path,
        full_quality_evidence=Path("quality.json"),
        differential_evidence=Path("differential.json"),
        stability_evidence=Path("stability.json"),
    )
    assert result["status"] == "PASS"
    checks = result["checks"]
    assert isinstance(checks, list)
    assert len(checks) == len(gate._REQUIRED_GATE_IDS)


@pytest.mark.parametrize(("status", "expected"), [("PASS", 0), ("BLOCKED", 2)])
def test_main_writes_pass_and_blocked_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    expected: int,
) -> None:
    output = tmp_path / "runtime" / "artifacts" / "python_migration" / "gate.json"
    monkeypatch.setattr(
        gate, "assess_removal_gate", lambda **_kwargs: {"status": status}
    )
    written: list[tuple[Path, object]] = []
    monkeypatch.setattr(
        gate,
        "write_json_object_verified",
        lambda path, payload, **_kwargs: written.append((path, payload)),
    )
    result = gate.main(
        [
            "--repository-root",
            str(tmp_path),
            "--full-quality-evidence",
            "quality.json",
            "--differential-evidence",
            "differential.json",
            "--stability-evidence",
            "stability.json",
            "--output",
            str(output),
        ]
    )
    assert result == expected
    assert written == [(output, {"status": status})]
    assert f"PYTHON_312_REMOVAL_GATE_{status}" in capsys.readouterr().out

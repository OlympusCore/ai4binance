from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.ops import python_runtime_removal_gate as gate


def passing_checks() -> tuple[gate.RemovalGateCheck, ...]:
    return tuple(
        gate.RemovalGateCheck(
            gate_id=gate_id,
            status="PASS",
            blockers=(),
            evidence={"verified": True},
        )
        for gate_id in gate._REQUIRED_GATE_IDS
    )


def test_removal_gate_pass_only_starts_governed_lifecycle() -> None:
    payload = gate.evaluate_removal_gate(
        passing_checks(),
        code_revision="revision-1",
    )

    assert payload["status"] == "PASS"
    assert payload["blockers"] == []
    assert payload["removal_candidate_allowed"] is True
    assert payload["required_post_gate_lifecycle"] == [
        "DEPRECATED",
        "QUARANTINED",
        "PROVEN_UNUSED",
        "UNINSTALL",
    ]
    assert payload["next_required_lifecycle_state"] == "DEPRECATED"
    assert payload["uninstall_allowed"] is False
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_removal_gate_blocks_missing_duplicate_and_dirty_subject() -> None:
    checks = list(passing_checks())
    checks.pop()
    checks.append(checks[0])

    payload = gate.evaluate_removal_gate(
        checks,
        code_revision="revision-1",
        changed_paths=(" M src/ai4binance/example.py",),
    )

    assert payload["status"] == "BLOCKED"
    blockers = payload["blockers"]
    assert isinstance(blockers, list)
    assert "DUPLICATE_REMOVAL_GATE:CPYTHON_3_14_7" in blockers
    assert "MISSING_REMOVAL_GATE:PYTHON312_PATH_DEPENDENCY" in blockers
    assert "PYTHON_REMOVAL_GATE_REPOSITORY_DIRTY" in blockers
    assert payload["removal_candidate_allowed"] is False
    assert payload["next_required_lifecycle_state"] is None
    assert payload["uninstall_allowed"] is False


def full_quality_evidence(
    tmp_path: Path,
    *,
    attested_revision: str,
) -> Path:
    deterministic_path = tmp_path / "deterministic-quality.json"
    deterministic_payload = {
        "status": "PASS",
        "quality_evidence_gate": {
            "quality_gate": {
                "workspace_attestation": {
                    "git_commit": attested_revision,
                    "change_set_sha256": hashlib.sha256(b"").hexdigest(),
                }
            }
        },
    }
    deterministic_path.write_text(json.dumps(deterministic_payload), encoding="utf-8")
    rows = [
        {"step_id": step_id, "status": "PASS", "exit_code": 0}
        for step_id in (
            "dependency_check",
            "ruff_format",
            "ruff_lint",
            "mypy",
            "pytest",
        )
    ]
    rows.append(
        {
            "step_id": "deterministic_quality_gate",
            "status": "PASS",
            "exit_code": 0,
            "artifact_path": deterministic_path.name,
            "output_sha256": hashlib.sha256(
                deterministic_path.read_bytes()
            ).hexdigest(),
        }
    )
    path = tmp_path / "full-quality.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "test-full",
                "status": "TECHNICAL_QUALITY_PASS",
                "profile": "full",
                "verification_status": "FULL_VERIFIED",
                "selected_pytest_arguments": ["FULL_TEST_SUITE"],
                "step_telemetry": rows,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_full_quality_context_rejects_stale_or_dirty_evidence(tmp_path: Path) -> None:
    path = full_quality_evidence(tmp_path, attested_revision="old-revision")

    context = gate._quality_context(
        tmp_path,
        path,
        current_revision="current-revision",
        changed_paths=(" M pyproject.toml",),
    )

    assert "FULL_QUALITY_EVIDENCE_CODE_REVISION_MISMATCH" in context.blockers
    assert "FULL_QUALITY_CURRENT_REPOSITORY_DIRTY" in context.blockers
    assert context.pytest_pass is False


def test_full_quality_context_accepts_exact_clean_subject(tmp_path: Path) -> None:
    path = full_quality_evidence(tmp_path, attested_revision="current-revision")

    context = gate._quality_context(
        tmp_path,
        path,
        current_revision="current-revision",
        changed_paths=(),
    )

    assert context.blockers == ()
    assert context.pytest_pass is True
    assert all(context.step_status.values())


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_full_quality_context_accepts_powershell_bom(
    tmp_path: Path,
    encoding: str,
) -> None:
    path = full_quality_evidence(tmp_path, attested_revision="current-revision")
    payload = path.read_text(encoding="utf-8")
    path.write_text(payload, encoding=encoding)

    context = gate._quality_context(
        tmp_path,
        path,
        current_revision="current-revision",
        changed_paths=(),
    )

    assert context.blockers == ()
    assert context.pytest_pass is True


def differential_evidence(tmp_path: Path) -> tuple[Path, Path]:
    stability = {
        "status": "PASS",
        "blockers": [],
        "code_revision": "current-revision",
        "benchmark_driver_sha256": "a" * 64,
        "clock_source": "process_time_ns",
        "max_regression_percent": 10.0,
    }
    latest = {
        **stability,
        "baseline_runtime": {"version": "3.12.10"},
        "current_runtime": {"version": "3.14.7"},
        "latest_verification": {
            "status": "PASS",
            "blockers": [],
            "current_code_revision": "current-revision",
        },
        "comparisons": [
            {
                "benchmark_name": "event-replay-order-state",
                "passed": True,
                "blockers": [],
                "baseline_semantic_sha256": "b" * 64,
                "current_semantic_sha256": "b" * 64,
            }
        ],
    }
    latest_path = tmp_path / "latest.json"
    stability_path = tmp_path / "stability.json"
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    stability_path.write_text(json.dumps(stability), encoding="utf-8")
    return latest_path, stability_path


def test_differential_context_accepts_exact_stable_evidence(tmp_path: Path) -> None:
    latest, stability = differential_evidence(tmp_path)

    context = gate._differential_context(
        latest,
        stability,
        current_revision="current-revision",
        changed_paths=(),
    )

    assert context.blockers == ()
    assert context.replay_pass is True


def test_differential_context_blocks_semantic_drift_and_dirty_subject(
    tmp_path: Path,
) -> None:
    latest_path, stability_path = differential_evidence(tmp_path)
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["comparisons"][0]["current_semantic_sha256"] = "c" * 64
    latest_path.write_text(json.dumps(latest), encoding="utf-8")

    context = gate._differential_context(
        latest_path,
        stability_path,
        current_revision="current-revision",
        changed_paths=(" M src/ai4binance/example.py",),
    )

    assert "PYTHON_RUNTIME_BEHAVIOR_DRIFT" in context.blockers
    assert "DIFFERENTIAL_CURRENT_REPOSITORY_DIRTY" in context.blockers


def test_active_reference_scan_excludes_tests_and_detects_active_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = tmp_path / "scripts" / "start.ps1"
    active.parent.mkdir(parents=True)
    active.write_text("C:/Python312/python.exe\n", encoding="utf-8")
    historical = tmp_path / "tests" / "test_history.py"
    historical.parent.mkdir(parents=True)
    historical.write_text('baseline = "3.12.10"\n', encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "_git",
        lambda root, *args: "scripts/start.ps1\0tests/test_history.py\0",
    )

    check = gate._hardcoded_reference_check(tmp_path)

    assert check.status == "BLOCKED"
    assert check.evidence["references"] == ["scripts/start.ps1:1"]


def test_active_artifact_classification_preserves_quarantined_evidence() -> None:
    assert gate._is_active_cp312_artifact("scripts/__pycache__/audit.cpython-312.pyc")
    assert gate._is_active_cp312_artifact(".mypy_cache/3.12/cache.db")
    assert not gate._is_active_cp312_artifact(
        "runtime/artifacts/maintenance_archive/python312/Lib/module.py"
    )
    assert not gate._is_active_cp312_artifact(
        ".venv/Lib/site-packages/setuptools/compat/py312.py"
    )


def test_vscode_and_ci_checks_reject_legacy_or_missing_runtime(tmp_path: Path) -> None:
    settings = tmp_path / ".vscode" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"python.defaultInterpreterPath":"C:/Python312/python.exe"}',
        encoding="utf-8",
    )
    workflow = tmp_path / ".github" / "workflows" / "quality.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("run: uv python install 3.12.10\n", encoding="utf-8")

    vscode = gate._vscode_check(tmp_path)
    ci = gate._ci_check(tmp_path)

    assert vscode.status == "BLOCKED"
    assert "VSCODE_LEGACY_RUNTIME_REFERENCE_PRESENT" in vscode.blockers
    assert ci.status == "BLOCKED"
    assert any("CI_LEGACY_RUNTIME_REFERENCE_PRESENT" in item for item in ci.blockers)


def test_vscode_check_accepts_canonical_interpreter_without_format_dependency(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".vscode" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"python.defaultInterpreterPath":"${workspaceFolder}/.venv/Scripts/python.exe"}',
        encoding="utf-8",
    )

    check = gate._vscode_check(tmp_path)

    assert check.status == "PASS"
    assert check.blockers == ()


def test_main_rejects_output_outside_runtime(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PYTHON_REMOVAL_GATE_OUTPUT_OUTSIDE_RUNTIME"):
        gate.main(
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
                "outside.json",
            ]
        )


def test_canonical_runtime_check_reports_every_mismatch(tmp_path: Path) -> None:
    check = gate._canonical_runtime_check(
        tmp_path / ".venv" / "Scripts" / "python.exe",
        tmp_path,
        {
            "implementation": "PyPy",
            "version": "3.12.10",
            "machine": "arm64",
            "gil_enabled": False,
            "py_gil_disabled": 1,
            "soabi": "cp312-win_amd64",
            "jit_enabled": True,
        },
        ("CANONICAL_PYTHON_PROBE_FAILED",),
    )

    assert check.status == "BLOCKED"
    assert set(check.blockers) == {
        "CANONICAL_PYTHON_PROBE_FAILED",
        "CANONICAL_RUNTIME_IMPLEMENTATION_MISMATCH",
        "CANONICAL_RUNTIME_VERSION_MISMATCH",
        "CANONICAL_RUNTIME_ARCHITECTURE_MISMATCH",
        "CANONICAL_RUNTIME_STANDARD_GIL_REQUIRED",
        "CANONICAL_RUNTIME_SOABI_MISMATCH",
        "CANONICAL_RUNTIME_JIT_MUST_BE_DISABLED",
    }


def test_parse_venv_config_is_bounded_and_normalized(tmp_path: Path) -> None:
    missing = tmp_path / "missing.cfg"
    assert gate._parse_venv_config(missing) == {}

    oversized = tmp_path / "oversized.cfg"
    oversized.write_bytes(b"x" * 32_769)
    assert gate._parse_venv_config(oversized) == {}

    config = tmp_path / "pyvenv.cfg"
    config.write_text(
        " Version_Info = 3.14.7\ninclude-system-site-packages = FALSE\nignored line\n",
        encoding="utf-8",
    )
    assert gate._parse_venv_config(config) == {
        "version_info": "3.14.7",
        "include-system-site-packages": "FALSE",
    }


def test_venv_check_rejects_invalid_prefix_config_and_legacy_abi(
    tmp_path: Path,
) -> None:
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text(
        "version_info = 3.12.10\ninclude-system-site-packages = true\n",
        encoding="utf-8",
    )
    artifact = venv / "Lib" / "legacy.cp312-win_amd64.pyd"
    artifact.parent.mkdir()
    artifact.write_bytes(b"legacy")

    check = gate._venv_check(
        tmp_path,
        {"prefix": "bad\x00prefix", "base_prefix": "bad\x00prefix"},
    )

    assert check.status == "BLOCKED"
    assert set(check.blockers) == {
        "VENV_PREFIX_MISMATCH",
        "VENV_ISOLATION_MISSING",
        "VENV_VERSION_MISMATCH",
        "VENV_SYSTEM_SITE_PACKAGES_NOT_DISABLED",
        "VENV_CP312_ABI_ARTIFACT_PRESENT",
    }


def test_module_inventory_maps_packages_and_skips_main(tmp_path: Path) -> None:
    package = tmp_path / "src" / "ai4binance" / "feature"
    package.mkdir(parents=True)
    (tmp_path / "src" / "ai4binance" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "__main__.py").write_text("raise SystemExit\n", encoding="utf-8")

    assert gate._module_names(tmp_path) == (
        "ai4binance",
        "ai4binance.feature",
        "ai4binance.feature.worker",
    )


@pytest.mark.parametrize(
    ("payload", "expected_blocker"),
    [
        (None, "FULL_IMPORT_RESULT_INVALID"),
        ({"errors": "invalid"}, "FULL_IMPORT_RESULT_INVALID"),
        (
            {"errors": [{"module": "ai4binance", "error_type": "ImportError"}]},
            "FULL_IMPORT_FAILURE",
        ),
    ],
)
def test_import_check_fails_closed_for_invalid_probe_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object] | None,
    expected_blocker: str,
) -> None:
    monkeypatch.setattr(gate, "_module_names", lambda root: ("ai4binance",))
    monkeypatch.setattr(
        gate,
        "_run_python_json",
        lambda *args, **kwargs: (payload, ()),
    )

    check = gate._import_check(tmp_path / "python.exe", tmp_path)

    assert check.status == "BLOCKED"
    assert expected_blocker in check.blockers


def test_import_check_rejects_empty_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "_module_names", lambda root: ())
    monkeypatch.setattr(
        gate,
        "_run_python_json",
        lambda *args, **kwargs: ({"errors": []}, ()),
    )

    check = gate._import_check(tmp_path / "python.exe", tmp_path)

    assert check.blockers == ("FIRST_PARTY_MODULE_INVENTORY_EMPTY",)


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "expected"),
    [
        (1, "", "broken", "DEPENDENCY_CHECK_NOT_PASSING"),
        (
            0,
            "x" * (gate._MAX_CAPTURE_BYTES + 1),
            "",
            "DEPENDENCY_CHECK_OUTPUT_TOO_LARGE",
        ),
    ],
    ids=("nonzero-exit", "oversized-output"),
)
def test_dependency_check_rejects_failure_or_oversized_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: str,
    stderr: str,
    expected: str,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        ),
    )

    check = gate._dependency_check(tmp_path / "python.exe", tmp_path)

    assert expected in check.blockers


def test_quality_check_rejects_missing_step_and_empty_inventory() -> None:
    context = gate._QualityContext(
        (), {"pytest": False}, False, {"path": "quality.json"}
    )

    check = gate._quality_check(
        "UNIT_TESTS",
        context,
        required_steps=("pytest",),
        inventory_count=0,
    )

    assert check.blockers == (
        "QUALITY_STEP_NOT_PASSING:pytest",
        "UNIT_TESTS_INVENTORY_EMPTY",
    )


def test_test_inventory_rejects_unknown_predicate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="UNKNOWN_TEST_INVENTORY:unknown"):
        gate._test_inventory(tmp_path, "unknown")

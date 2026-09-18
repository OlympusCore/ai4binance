"""Evaluate Python 3.12 removal readiness without uninstalling any runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re

# Subprocess execution is restricted to fixed shell-free validation argv.
import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai4binance.storage import write_json_object_verified

_SCHEMA_VERSION = "python-runtime-removal-gate:v1"
_CANONICAL_VERSION = "3.14.7"
_LEGACY_VERSION = "3.12.10"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_MAX_EVIDENCE_BYTES = 2_000_000
_MAX_CAPTURE_BYTES = 1_000_000
_LIFECYCLE = ("DEPRECATED", "QUARANTINED", "PROVEN_UNUSED", "UNINSTALL")

_GATE_DEFINITIONS = (
    ("CPYTHON_3_14_7", "CPython 3.14.7", "PASS"),
    ("FRESH_VENV", "Fresh .venv", "PASS"),
    ("DEPENDENCY_RESOLUTION", "Dependency resolution", "PASS"),
    ("FULL_IMPORTS", "Full imports", "PASS"),
    ("RUFF", "Ruff", "PASS"),
    ("MYPY", "MyPy", "PASS"),
    ("UNIT_TESTS", "Unit tests", "PASS"),
    ("CONTRACT_SCHEMA_TESTS", "Contract/schema tests", "PASS"),
    ("INTEGRATION_TESTS", "Integration tests", "PASS"),
    ("DETERMINISTIC_REPLAY", "Deterministic replay", "PASS"),
    (
        "PYTHON_312_314_DIFFERENTIAL",
        "Python 3.12/3.14 differential",
        "PASS",
    ),
    ("BINANCE_ADAPTERS", "Binance adapters", "PASS"),
    ("PAPER_TRADING", "Paper trading", "PASS"),
    ("VSCODE_INTERPRETER", "VS Code interpreter", "PASS"),
    ("CI_RUNTIME", "CI runtime", "PASS"),
    ("HARD_CODED_PYTHON_312_REFS", "Hard-coded Python 3.12 refs", "ZERO"),
    ("ACTIVE_CP312_ARTIFACTS", "Active cp312 artifacts", "ZERO"),
    ("PYTHON312_PATH_DEPENDENCY", "Python312 PATH dependency", "ZERO"),
)
_GATE_METADATA = {
    gate_id: (label, expectation) for gate_id, label, expectation in _GATE_DEFINITIONS
}
_REQUIRED_GATE_IDS = tuple(item[0] for item in _GATE_DEFINITIONS)

_LEGACY_REFERENCE_PATTERN = re.compile(
    r"(?i)(?:3[.]12(?:[.]10)?|python[_-]?312|py[_-]?312|cp[_-]?312)"
)
_CP312_COMPILED_PATTERN = re.compile(r"(?i)(?:cpython[-_]?312|cp312(?:[-_.]|$))")
_CP312_NAMED_PATTERN = re.compile(r"(?i)(?:python[_-]?312(?:[-_.]|$)|py[_-]?312[-_])")
_REFERENCE_EXCLUDED_PREFIXES = ("docs/", "tests/", "runtime/")
_REFERENCE_EXCLUDED_PATHS = frozenset(
    {"src/ai4binance/ops/python_runtime_removal_gate.py"}
)
_ARTIFACT_EXCLUDED_PREFIXES = (
    "runtime/artifacts/maintenance_archive/",
    "runtime/artifacts/python_migration/",
    "runtime/artifacts/quality/",
    "runtime/quality/",
)


@dataclass(frozen=True)
class RemovalGateCheck:
    """One deterministic removal-gate result."""

    gate_id: str
    status: str
    blockers: tuple[str, ...]
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.gate_id not in _GATE_METADATA:
            raise ValueError(f"UNKNOWN_PYTHON_REMOVAL_GATE:{self.gate_id}")
        if self.status not in {"PASS", "BLOCKED"}:
            raise ValueError("PYTHON_REMOVAL_GATE_STATUS_INVALID")
        if (self.status == "PASS") == bool(self.blockers):
            raise ValueError("PYTHON_REMOVAL_GATE_BLOCKER_SHAPE_INVALID")

    def to_payload(self) -> dict[str, object]:
        label, expectation = _GATE_METADATA[self.gate_id]
        return {
            "gate_id": self.gate_id,
            "label": label,
            "expectation": expectation,
            "status": self.status,
            "blockers": list(self.blockers),
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class _QualityContext:
    blockers: tuple[str, ...]
    step_status: Mapping[str, bool]
    pytest_pass: bool
    evidence: Mapping[str, object]


@dataclass(frozen=True)
class _DifferentialContext:
    blockers: tuple[str, ...]
    replay_pass: bool
    evidence: Mapping[str, object]


def _check(
    gate_id: str,
    *,
    passed: bool,
    blockers: Sequence[str] = (),
    evidence: Mapping[str, object] | None = None,
) -> RemovalGateCheck:
    normalized_blockers = tuple(dict.fromkeys(blockers))
    if passed and normalized_blockers:
        raise ValueError("PASSING_PYTHON_REMOVAL_GATE_CANNOT_HAVE_BLOCKERS")
    if not passed and not normalized_blockers:
        normalized_blockers = (f"{gate_id}_NOT_PROVEN",)
    return RemovalGateCheck(
        gate_id=gate_id,
        status="PASS" if passed else "BLOCKED",
        blockers=normalized_blockers,
        evidence={} if evidence is None else evidence,
    )


def evaluate_removal_gate(
    checks: Sequence[RemovalGateCheck],
    *,
    code_revision: str,
    changed_paths: Sequence[str] = (),
    repository_blockers: Sequence[str] = (),
) -> dict[str, object]:
    """Combine the exact checklist and retain uninstall as external authority."""
    by_id: dict[str, RemovalGateCheck] = {}
    blockers = list(repository_blockers)
    for check in checks:
        if check.gate_id in by_id:
            blockers.append(f"DUPLICATE_REMOVAL_GATE:{check.gate_id}")
            continue
        by_id[check.gate_id] = check

    unknown = sorted(set(by_id).difference(_REQUIRED_GATE_IDS))
    blockers.extend(f"UNKNOWN_REMOVAL_GATE:{gate_id}" for gate_id in unknown)
    ordered: list[RemovalGateCheck] = []
    for gate_id in _REQUIRED_GATE_IDS:
        observed = by_id.get(gate_id)
        if observed is None:
            blockers.append(f"MISSING_REMOVAL_GATE:{gate_id}")
            current_check = _check(
                gate_id,
                passed=False,
                blockers=(f"{gate_id}_EVIDENCE_MISSING",),
            )
        else:
            current_check = observed
        ordered.append(current_check)
        blockers.extend(f"{gate_id}:{item}" for item in current_check.blockers)

    normalized_changes = tuple(sorted(set(changed_paths)))
    if normalized_changes:
        blockers.append("PYTHON_REMOVAL_GATE_REPOSITORY_DIRTY")
    blockers = list(dict.fromkeys(blockers))
    passed = not blockers and all(check.status == "PASS" for check in ordered)
    return {
        "schema_version": _SCHEMA_VERSION,
        "status": "PASS" if passed else "BLOCKED",
        "blockers": blockers,
        "code_revision": code_revision,
        "changed_paths": list(normalized_changes),
        "target_runtime": f"CPython {_CANONICAL_VERSION}",
        "legacy_runtime": f"CPython {_LEGACY_VERSION}",
        "checks": [check.to_payload() for check in ordered],
        "removal_candidate_allowed": passed,
        "required_post_gate_lifecycle": list(_LIFECYCLE),
        "next_required_lifecycle_state": "DEPRECATED" if passed else None,
        "uninstall_allowed": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"EVIDENCE_FILE_MISSING:{path}")
    if path.stat().st_size > _MAX_EVIDENCE_BYTES:
        raise ValueError(f"EVIDENCE_FILE_TOO_LARGE:{path}")
    try:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("utf-16")
        payload = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"EVIDENCE_FILE_INVALID:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"EVIDENCE_OBJECT_REQUIRED:{path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repository_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("EVIDENCE_PATH_OUTSIDE_REPOSITORY")
    return resolved


def _git(root: Path, *arguments: str) -> str:
    git = shutil_which_required("git")
    process = subprocess.run(  # noqa: S603  # nosec B603
        [git, "-C", str(root), *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if process.returncode != 0:
        raise ValueError(f"GIT_COMMAND_FAILED:{arguments[0]}")
    if len(process.stdout.encode("utf-8")) > _MAX_CAPTURE_BYTES:
        raise ValueError("GIT_OUTPUT_TOO_LARGE")
    return process.stdout


def shutil_which_required(command: str) -> str:
    from shutil import which

    resolved = which(command)
    if resolved is None:
        raise ValueError(f"COMMAND_NOT_FOUND:{command}")
    return resolved


def _repository_state(root: Path) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    try:
        revision = _git(root, "rev-parse", "HEAD").strip()
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    except ValueError as exc:
        return "UNKNOWN", (), (str(exc),)
    changes = tuple(line for line in status.splitlines() if line.strip())
    return revision, changes, ()


def _run_python_json(
    executable: Path,
    root: Path,
    code: str,
    *,
    input_text: str | None = None,
    timeout_seconds: int = 60,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    if not executable.is_file() or not executable.resolve().is_relative_to(root):
        return None, ("CANONICAL_PYTHON_INVALID",)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        process = subprocess.run(  # noqa: S603  # nosec B603
            [str(executable), "-B", "-c", code],
            cwd=root,
            env=environment,
            input=input_text,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, ("CANONICAL_PYTHON_PROBE_FAILED",)
    captured_size = len(process.stdout.encode("utf-8")) + len(
        process.stderr.encode("utf-8")
    )
    if captured_size > _MAX_CAPTURE_BYTES:
        return None, ("CANONICAL_PYTHON_PROBE_OUTPUT_TOO_LARGE",)
    if process.returncode != 0:
        return None, ("CANONICAL_PYTHON_PROBE_FAILED",)
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        return None, ("CANONICAL_PYTHON_PROBE_INVALID",)
    if not isinstance(payload, dict):
        return None, ("CANONICAL_PYTHON_PROBE_INVALID",)
    return payload, ()


def _runtime_probe(
    executable: Path, root: Path
) -> tuple[dict[str, Any], tuple[str, ...]]:
    code = """
import json
import platform
import sys
import sysconfig

jit = getattr(sys, "_jit", None)
print(json.dumps({
    "implementation": platform.python_implementation(),
    "version": platform.python_version(),
    "machine": platform.machine().casefold(),
    "gil_enabled": sys._is_gil_enabled(),
    "py_gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
    "soabi": sysconfig.get_config_var("SOABI"),
    "jit_enabled": bool(jit is not None and jit.is_enabled()),
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
}, sort_keys=True))
"""
    payload, blockers = _run_python_json(executable, root, code)
    return ({} if payload is None else payload), blockers


def _canonical_runtime_check(
    executable: Path,
    root: Path,
    runtime: Mapping[str, Any],
    probe_blockers: Sequence[str],
) -> RemovalGateCheck:
    blockers = list(probe_blockers)
    if runtime.get("implementation") != "CPython":
        blockers.append("CANONICAL_RUNTIME_IMPLEMENTATION_MISMATCH")
    if runtime.get("version") != _CANONICAL_VERSION:
        blockers.append("CANONICAL_RUNTIME_VERSION_MISMATCH")
    if str(runtime.get("machine", "")).casefold() not in {"amd64", "x86_64"}:
        blockers.append("CANONICAL_RUNTIME_ARCHITECTURE_MISMATCH")
    if runtime.get("gil_enabled") is not True or runtime.get("py_gil_disabled") != 0:
        blockers.append("CANONICAL_RUNTIME_STANDARD_GIL_REQUIRED")
    if runtime.get("soabi") != "cp314-win_amd64":
        blockers.append("CANONICAL_RUNTIME_SOABI_MISMATCH")
    if runtime.get("jit_enabled") is not False:
        blockers.append("CANONICAL_RUNTIME_JIT_MUST_BE_DISABLED")
    return _check(
        "CPYTHON_3_14_7",
        passed=not blockers,
        blockers=blockers,
        evidence={
            "executable": str(executable),
            "runtime": dict(runtime),
            "repository_root": str(root),
        },
    )


def _parse_venv_config(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size > 32_768:
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            result[key.strip().casefold()] = value.strip()
    return result


def _venv_check(root: Path, runtime: Mapping[str, Any]) -> RemovalGateCheck:
    venv = (root / ".venv").resolve()
    config_path = venv / "pyvenv.cfg"
    config = _parse_venv_config(config_path)
    blockers: list[str] = []
    try:
        observed_prefix = Path(str(runtime.get("prefix", ""))).resolve()
        observed_base = Path(str(runtime.get("base_prefix", ""))).resolve()
    except (OSError, ValueError):
        observed_prefix = Path()
        observed_base = Path()
        blockers.append("VENV_RUNTIME_PREFIX_INVALID")
    if observed_prefix != venv:
        blockers.append("VENV_PREFIX_MISMATCH")
    if observed_base == observed_prefix:
        blockers.append("VENV_ISOLATION_MISSING")
    if config.get("version_info") != _CANONICAL_VERSION:
        blockers.append("VENV_VERSION_MISMATCH")
    if config.get("include-system-site-packages", "").casefold() != "false":
        blockers.append("VENV_SYSTEM_SITE_PACKAGES_NOT_DISABLED")
    legacy_abi_artifacts = sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in venv.rglob("*")
        if path.is_file() and _CP312_COMPILED_PATTERN.search(path.name)
    )
    if legacy_abi_artifacts:
        blockers.append("VENV_CP312_ABI_ARTIFACT_PRESENT")
    return _check(
        "FRESH_VENV",
        passed=not blockers,
        blockers=blockers,
        evidence={
            "pyvenv_config": str(config_path),
            "version_info": config.get("version_info"),
            "include_system_site_packages": config.get("include-system-site-packages"),
            "legacy_abi_artifacts": legacy_abi_artifacts,
            "freshness_basis": "STRUCTURAL_ISOLATION_AND_ABI_SCAN",
        },
    )


def _dependency_check(executable: Path, root: Path) -> RemovalGateCheck:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        process = subprocess.run(  # noqa: S603  # nosec B603
            [str(executable), "-B", "-m", "pip", "check"],
            cwd=root,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _check(
            "DEPENDENCY_RESOLUTION",
            passed=False,
            blockers=("DEPENDENCY_CHECK_FAILED",),
        )
    output_size = len(process.stdout.encode("utf-8")) + len(
        process.stderr.encode("utf-8")
    )
    blockers: list[str] = []
    if process.returncode != 0:
        blockers.append("DEPENDENCY_CHECK_NOT_PASSING")
    if output_size > _MAX_CAPTURE_BYTES:
        blockers.append("DEPENDENCY_CHECK_OUTPUT_TOO_LARGE")
    return _check(
        "DEPENDENCY_RESOLUTION",
        passed=not blockers,
        blockers=blockers,
        evidence={"command": ".venv/Scripts/python.exe -m pip check"},
    )


def _module_names(root: Path) -> tuple[str, ...]:
    package_root = root / "src" / "ai4binance"
    modules: set[str] = set()
    for path in package_root.rglob("*.py"):
        relative = path.relative_to(root / "src")
        if path.name == "__main__.py":
            continue
        parts = relative.with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            modules.add(".".join(parts))
    return tuple(sorted(modules))


def _import_check(executable: Path, root: Path) -> RemovalGateCheck:
    modules = _module_names(root)
    code = """
import importlib
import json
import sys

modules = json.load(sys.stdin)
errors = []
for module_name in modules:
    try:
        importlib.import_module(module_name)
    except BaseException as exc:
        errors.append({
            "module": module_name,
            "error_type": type(exc).__name__,
        })
print(json.dumps({"module_count": len(modules), "errors": errors}, sort_keys=True))
"""
    payload, probe_blockers = _run_python_json(
        executable,
        root,
        code,
        input_text=json.dumps(modules),
        timeout_seconds=120,
    )
    blockers = list(probe_blockers)
    result = {} if payload is None else payload
    errors = result.get("errors")
    if not modules:
        blockers.append("FIRST_PARTY_MODULE_INVENTORY_EMPTY")
    if not isinstance(errors, list):
        blockers.append("FULL_IMPORT_RESULT_INVALID")
        errors = []
    elif errors:
        blockers.append("FULL_IMPORT_FAILURE")
    return _check(
        "FULL_IMPORTS",
        passed=not blockers,
        blockers=blockers,
        evidence={"module_count": len(modules), "errors": errors[:50]},
    )


def _quality_context(
    root: Path,
    evidence_path: Path,
    *,
    current_revision: str,
    changed_paths: Sequence[str],
) -> _QualityContext:
    blockers: list[str] = []
    step_status: dict[str, bool] = {}
    evidence: dict[str, object] = {"path": str(evidence_path)}
    try:
        payload = _load_json(evidence_path)
    except ValueError as exc:
        return _QualityContext((str(exc),), step_status, False, evidence)
    evidence["run_id"] = payload.get("run_id")
    evidence["profile"] = payload.get("profile")
    evidence["verification_status"] = payload.get("verification_status")
    if payload.get("status") != "TECHNICAL_QUALITY_PASS":
        blockers.append("FULL_QUALITY_STATUS_NOT_PASSING")
    if payload.get("profile") != "full":
        blockers.append("FULL_QUALITY_PROFILE_REQUIRED")
    if payload.get("verification_status") != "FULL_VERIFIED":
        blockers.append("FULL_QUALITY_VERIFICATION_REQUIRED")
    if payload.get("selected_pytest_arguments") != ["FULL_TEST_SUITE"]:
        blockers.append("FULL_TEST_SUITE_EVIDENCE_REQUIRED")

    telemetry = payload.get("step_telemetry")
    rows = telemetry if isinstance(telemetry, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        step_id = row.get("step_id")
        if isinstance(step_id, str):
            step_status[step_id] = (
                row.get("status") == "PASS" and row.get("exit_code") == 0
            )
    required_steps = ("dependency_check", "ruff_format", "ruff_lint", "mypy", "pytest")
    for step_id in required_steps:
        if not step_status.get(step_id, False):
            blockers.append(f"FULL_QUALITY_STEP_NOT_PASSING:{step_id}")

    deterministic_row = next(
        (
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("step_id") == "deterministic_quality_gate"
        ),
        None,
    )
    deterministic_payload: dict[str, Any] = {}
    if deterministic_row is None:
        blockers.append("DETERMINISTIC_QUALITY_EVIDENCE_MISSING")
    else:
        try:
            deterministic_path = _resolve_repository_path(
                root, str(deterministic_row.get("artifact_path", ""))
            )
            expected_sha256 = deterministic_row.get("output_sha256")
            if _sha256_file(deterministic_path) != expected_sha256:
                blockers.append("DETERMINISTIC_QUALITY_EVIDENCE_HASH_MISMATCH")
            deterministic_payload = _load_json(deterministic_path)
            evidence["deterministic_quality_path"] = str(deterministic_path)
        except (OSError, ValueError) as exc:
            blockers.append(str(exc))
    if deterministic_payload.get("status") != "PASS":
        blockers.append("DETERMINISTIC_QUALITY_GATE_NOT_PASSING")
    quality_gate = deterministic_payload.get("quality_evidence_gate")
    quality_gate_payload = quality_gate if isinstance(quality_gate, dict) else {}
    nested_quality = quality_gate_payload.get("quality_gate")
    nested_quality_payload = nested_quality if isinstance(nested_quality, dict) else {}
    attestation = nested_quality_payload.get("workspace_attestation")
    attestation_payload = attestation if isinstance(attestation, dict) else {}
    evidence_revision = attestation_payload.get("git_commit")
    evidence["attested_code_revision"] = evidence_revision
    if evidence_revision != current_revision:
        blockers.append("FULL_QUALITY_EVIDENCE_CODE_REVISION_MISMATCH")
    if attestation_payload.get("change_set_sha256") != _EMPTY_SHA256:
        blockers.append("FULL_QUALITY_EVIDENCE_CHANGE_SET_NOT_CLEAN")
    if changed_paths:
        blockers.append("FULL_QUALITY_CURRENT_REPOSITORY_DIRTY")
    normalized_blockers = tuple(dict.fromkeys(blockers))
    return _QualityContext(
        normalized_blockers,
        step_status,
        not normalized_blockers and step_status.get("pytest", False),
        evidence,
    )


def _quality_check(
    gate_id: str,
    context: _QualityContext,
    *,
    required_steps: Sequence[str],
    inventory_count: int | None = None,
) -> RemovalGateCheck:
    blockers = list(context.blockers)
    blockers.extend(
        f"QUALITY_STEP_NOT_PASSING:{step_id}"
        for step_id in required_steps
        if not context.step_status.get(step_id, False)
    )
    if inventory_count is not None and inventory_count < 1:
        blockers.append(f"{gate_id}_INVENTORY_EMPTY")
    evidence = dict(context.evidence)
    if inventory_count is not None:
        evidence["test_inventory_count"] = inventory_count
    return _check(
        gate_id,
        passed=not blockers,
        blockers=blockers,
        evidence=evidence,
    )


def _test_inventory(root: Path, predicate: str) -> int:
    files = tuple((root / "tests").rglob("test_*.py"))
    if predicate == "unit":
        return sum(
            "pytest.mark.unit" in path.read_text(encoding="utf-8") for path in files
        )
    if predicate == "contract_schema":
        return sum(
            path.is_relative_to(root / "tests" / "contract")
            or "schema" in path.name.casefold()
            or "contract" in path.name.casefold()
            for path in files
        )
    if predicate == "integration":
        return sum(
            "pytest.mark.integration_like" in path.read_text(encoding="utf-8")
            or "integration" in path.name.casefold()
            for path in files
        )
    if predicate == "binance":
        return sum(
            "binance" in path.name.casefold() or "exchange" in path.name.casefold()
            for path in files
        )
    if predicate == "paper":
        return sum(
            "paper" in path.name.casefold() or "virtual_runtime" in path.name.casefold()
            for path in files
        )
    raise ValueError(f"UNKNOWN_TEST_INVENTORY:{predicate}")


def _differential_context(
    latest_path: Path,
    stability_path: Path,
    *,
    current_revision: str,
    changed_paths: Sequence[str],
) -> _DifferentialContext:
    blockers: list[str] = []
    evidence: dict[str, object] = {
        "latest_path": str(latest_path),
        "stability_path": str(stability_path),
    }
    try:
        latest = _load_json(latest_path)
        stability = _load_json(stability_path)
    except ValueError as exc:
        return _DifferentialContext((str(exc),), False, evidence)
    if latest.get("status") != "PASS" or latest.get("blockers") != []:
        blockers.append("DIFFERENTIAL_EVIDENCE_NOT_PASSING")
    if latest.get("code_revision") != current_revision:
        blockers.append("DIFFERENTIAL_EVIDENCE_CODE_REVISION_MISMATCH")
    if latest.get("clock_source") != "process_time_ns":
        blockers.append("DIFFERENTIAL_CLOCK_SOURCE_MISMATCH")
    latest_verification = latest.get("latest_verification")
    verification = latest_verification if isinstance(latest_verification, dict) else {}
    if verification.get("status") != "PASS" or verification.get("blockers") != []:
        blockers.append("DIFFERENTIAL_LATEST_VERIFICATION_NOT_PASSING")
    if verification.get("current_code_revision") != current_revision:
        blockers.append("DIFFERENTIAL_VERIFICATION_CODE_REVISION_MISMATCH")
    if stability.get("status") != "PASS" or stability.get("blockers") != []:
        blockers.append("DIFFERENTIAL_STABILITY_NOT_PASSING")
    for field in (
        "code_revision",
        "benchmark_driver_sha256",
        "clock_source",
        "max_regression_percent",
    ):
        if latest.get(field) != stability.get(field):
            blockers.append(f"DIFFERENTIAL_STABILITY_BINDING_MISMATCH:{field}")
    baseline_runtime = latest.get("baseline_runtime")
    baseline = baseline_runtime if isinstance(baseline_runtime, dict) else {}
    current_runtime = latest.get("current_runtime")
    current = current_runtime if isinstance(current_runtime, dict) else {}
    if baseline.get("version") != _LEGACY_VERSION:
        blockers.append("DIFFERENTIAL_BASELINE_RUNTIME_MISMATCH")
    if current.get("version") != _CANONICAL_VERSION:
        blockers.append("DIFFERENTIAL_CURRENT_RUNTIME_MISMATCH")
    comparisons = latest.get("comparisons")
    rows = comparisons if isinstance(comparisons, list) else []
    if not rows:
        blockers.append("DIFFERENTIAL_COMPARISONS_MISSING")
    replay_pass = False
    for row in rows:
        if not isinstance(row, dict):
            blockers.append("DIFFERENTIAL_COMPARISON_INVALID")
            continue
        if row.get("passed") is not True or row.get("blockers") != []:
            blockers.append("DIFFERENTIAL_COMPARISON_NOT_PASSING")
        if row.get("baseline_semantic_sha256") != row.get("current_semantic_sha256"):
            blockers.append("PYTHON_RUNTIME_BEHAVIOR_DRIFT")
        if row.get("benchmark_name") == "event-replay-order-state":
            replay_pass = row.get("passed") is True and row.get("blockers") == []
    if changed_paths:
        blockers.append("DIFFERENTIAL_CURRENT_REPOSITORY_DIRTY")
    evidence.update(
        {
            "code_revision": latest.get("code_revision"),
            "benchmark_driver_sha256": latest.get("benchmark_driver_sha256"),
            "clock_source": latest.get("clock_source"),
            "comparison_count": len(rows),
        }
    )
    return _DifferentialContext(tuple(dict.fromkeys(blockers)), replay_pass, evidence)


def _vscode_check(root: Path) -> RemovalGateCheck:
    path = root / ".vscode" / "settings.json"
    blockers: list[str] = []
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    normalized = text.replace("\\", "/")
    expected = "${workspaceFolder}/.venv/Scripts/python.exe"
    interpreter_pattern = re.compile(
        r'"python[.]defaultInterpreterPath"\s*:\s*'
        r'"[$][{]workspaceFolder[}]/[.]venv/Scripts/python[.]exe"',
        re.IGNORECASE,
    )
    if interpreter_pattern.search(normalized) is None:
        blockers.append("VSCODE_CANONICAL_INTERPRETER_MISSING")
    if _LEGACY_REFERENCE_PATTERN.search(text):
        blockers.append("VSCODE_LEGACY_RUNTIME_REFERENCE_PRESENT")
    return _check(
        "VSCODE_INTERPRETER",
        passed=not blockers,
        blockers=blockers,
        evidence={"path": str(path), "canonical_interpreter": expected},
    )


def _ci_check(root: Path) -> RemovalGateCheck:
    workflow_root = root / ".github" / "workflows"
    workflows = tuple(
        sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    )
    blockers: list[str] = []
    python_workflows: list[str] = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if "python" not in text.casefold() and "uv " not in text.casefold():
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        python_workflows.append(relative)
        if _CANONICAL_VERSION not in text:
            blockers.append(f"CI_CANONICAL_RUNTIME_MISSING:{relative}")
        if _LEGACY_REFERENCE_PATTERN.search(text):
            blockers.append(f"CI_LEGACY_RUNTIME_REFERENCE_PRESENT:{relative}")
    if not python_workflows:
        blockers.append("CI_PYTHON_WORKFLOW_MISSING")
    return _check(
        "CI_RUNTIME",
        passed=not blockers,
        blockers=blockers,
        evidence={"python_workflows": python_workflows},
    )


def _hardcoded_reference_check(root: Path) -> RemovalGateCheck:
    blockers: list[str] = []
    references: list[str] = []
    try:
        tracked = _git(root, "ls-files", "-z").split("\0")
    except ValueError as exc:
        return _check(
            "HARD_CODED_PYTHON_312_REFS",
            passed=False,
            blockers=(str(exc),),
        )
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not normalized or normalized in _REFERENCE_EXCLUDED_PATHS:
            continue
        if normalized.startswith(_REFERENCE_EXCLUDED_PREFIXES):
            continue
        path = root / relative
        try:
            if not path.is_file() or path.stat().st_size > _MAX_EVIDENCE_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            blockers.append(f"ACTIVE_REFERENCE_SCAN_FAILED:{normalized}")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _LEGACY_REFERENCE_PATTERN.search(line):
                references.append(f"{normalized}:{line_number}")
    if references:
        blockers.append("ACTIVE_HARD_CODED_PYTHON_312_REFERENCE_PRESENT")
    return _check(
        "HARD_CODED_PYTHON_312_REFS",
        passed=not blockers,
        blockers=blockers,
        evidence={"count": len(references), "references": references[:100]},
    )


def _is_active_cp312_artifact(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    casefolded = normalized.casefold()
    if casefolded.startswith(_ARTIFACT_EXCLUDED_PREFIXES):
        return False
    name = Path(normalized).name
    if _CP312_COMPILED_PATTERN.search(name) or _CP312_NAMED_PATTERN.search(name):
        return True
    parts = tuple(part.casefold() for part in Path(normalized).parts)
    return ".mypy_cache" in parts and "3.12" in parts


def _active_artifact_check(root: Path) -> RemovalGateCheck:
    artifacts: list[str] = []
    scan_errors: list[str] = []

    def on_error(error: OSError) -> None:
        filename = str(error.filename or "UNKNOWN").replace("\\", "/")
        scan_errors.append(f"{type(error).__name__}:{filename}")

    for directory, names, files in os.walk(root, topdown=True, onerror=on_error):
        current = Path(directory)
        names[:] = [
            name
            for name in names
            if name != ".git"
            and not any(
                (str((current / name).relative_to(root)).replace("\\", "/") + "/")
                .casefold()
                .startswith(prefix)
                for prefix in _ARTIFACT_EXCLUDED_PREFIXES
            )
        ]
        for name in (*names, *files):
            relative = str((current / name).relative_to(root)).replace("\\", "/")
            if _is_active_cp312_artifact(relative):
                artifacts.append(relative)
                if len(artifacts) >= 200:
                    break
        if len(artifacts) >= 200:
            break
    blockers: list[str] = []
    if artifacts:
        blockers.append("ACTIVE_CP312_ARTIFACT_PRESENT")
    if scan_errors:
        blockers.append("ACTIVE_CP312_ARTIFACT_SCAN_FAILED")
    return _check(
        "ACTIVE_CP312_ARTIFACTS",
        passed=not blockers,
        blockers=blockers,
        evidence={
            "count": len(artifacts),
            "artifacts": sorted(set(artifacts)),
            "scan_error_count": len(scan_errors),
            "scan_errors": sorted(set(scan_errors))[:20],
            "quarantined_evidence_excluded": True,
        },
    )


def _path_dependency_check() -> RemovalGateCheck:
    entries = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    legacy_entries = sorted(
        entry
        for entry in entries
        if _LEGACY_REFERENCE_PATTERN.search(entry.replace("\\", "/"))
    )
    return _check(
        "PYTHON312_PATH_DEPENDENCY",
        passed=not legacy_entries,
        blockers=("PYTHON312_PATH_ENTRY_PRESENT",) if legacy_entries else (),
        evidence={"count": len(legacy_entries), "entries": legacy_entries},
    )


def assess_removal_gate(
    *,
    repository_root: Path,
    full_quality_evidence: Path,
    differential_evidence: Path,
    stability_evidence: Path,
) -> dict[str, object]:
    """Collect current evidence and evaluate the removal checklist."""
    root = repository_root.resolve()
    revision, changed_paths, repository_blockers = _repository_state(root)
    executable = root / ".venv" / "Scripts" / "python.exe"
    runtime, runtime_blockers = _runtime_probe(executable, root)
    quality = _quality_context(
        root,
        _resolve_repository_path(root, full_quality_evidence),
        current_revision=revision,
        changed_paths=changed_paths,
    )
    differential = _differential_context(
        _resolve_repository_path(root, differential_evidence),
        _resolve_repository_path(root, stability_evidence),
        current_revision=revision,
        changed_paths=changed_paths,
    )
    checks = [
        _canonical_runtime_check(executable, root, runtime, runtime_blockers),
        _venv_check(root, runtime),
        _dependency_check(executable, root),
        _import_check(executable, root),
        _quality_check("RUFF", quality, required_steps=("ruff_format", "ruff_lint")),
        _quality_check("MYPY", quality, required_steps=("mypy",)),
        _quality_check(
            "UNIT_TESTS",
            quality,
            required_steps=("pytest",),
            inventory_count=_test_inventory(root, "unit"),
        ),
        _quality_check(
            "CONTRACT_SCHEMA_TESTS",
            quality,
            required_steps=("pytest",),
            inventory_count=_test_inventory(root, "contract_schema"),
        ),
        _quality_check(
            "INTEGRATION_TESTS",
            quality,
            required_steps=("pytest",),
            inventory_count=_test_inventory(root, "integration"),
        ),
        _check(
            "DETERMINISTIC_REPLAY",
            passed=not differential.blockers and differential.replay_pass,
            blockers=(
                differential.blockers
                if differential.blockers
                else (() if differential.replay_pass else ("REPLAY_EVIDENCE_MISSING",))
            ),
            evidence=differential.evidence,
        ),
        _check(
            "PYTHON_312_314_DIFFERENTIAL",
            passed=not differential.blockers,
            blockers=differential.blockers,
            evidence=differential.evidence,
        ),
        _quality_check(
            "BINANCE_ADAPTERS",
            quality,
            required_steps=("pytest",),
            inventory_count=_test_inventory(root, "binance"),
        ),
        _quality_check(
            "PAPER_TRADING",
            quality,
            required_steps=("pytest",),
            inventory_count=_test_inventory(root, "paper"),
        ),
        _vscode_check(root),
        _ci_check(root),
        _hardcoded_reference_check(root),
        _active_artifact_check(root),
        _path_dependency_check(),
    ]
    return evaluate_removal_gate(
        checks,
        code_revision=revision,
        changed_paths=changed_paths,
        repository_blockers=repository_blockers,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the fail-closed Python 3.12 removal gate."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--full-quality-evidence", type=Path, required=True)
    parser.add_argument("--differential-evidence", type=Path, required=True)
    parser.add_argument("--stability-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    root = args.repository_root.resolve()
    output = _resolve_repository_path(root, args.output)
    evidence_root = (root / "runtime" / "artifacts" / "python_migration").resolve()
    if not output.is_relative_to(evidence_root):
        raise ValueError("PYTHON_REMOVAL_GATE_OUTPUT_OUTSIDE_RUNTIME")
    payload = assess_removal_gate(
        repository_root=root,
        full_quality_evidence=args.full_quality_evidence,
        differential_evidence=args.differential_evidence,
        stability_evidence=args.stability_evidence,
    )
    write_json_object_verified(
        output,
        payload,
        blocker="PYTHON_REMOVAL_GATE_WRITE_VERIFY_FAILED",
        indent=2,
    )
    if payload["status"] == "PASS":
        print("PYTHON_312_REMOVAL_GATE_PASS")
        return 0
    print("PYTHON_312_REMOVAL_GATE_BLOCKED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

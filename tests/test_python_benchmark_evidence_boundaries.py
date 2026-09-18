"""Corrupted measurement evidence and failed worker processes remain blocked."""

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai4binance.ops import python_migration_benchmark as b
from tests.test_python_migration_benchmark import (
    passing_host_load_attestation,
    passing_stability,
)


def measurement() -> dict[str, Any]:
    return {
        "measurement": {
            "benchmark_name": "test",
            "environment_id": "local",
            "code_revision": "revision",
            "measured_at": "2026-01-01T00:00:00+00:00",
            "iterations": 5,
            "samples_ns_per_operation": [10.0] * 5,
        },
        "semantic_sha256": "a" * 64,
    }


@pytest.mark.parametrize("loader", [b._load_payload, b._load_stability_payload])
@pytest.mark.parametrize("payload", [[], {}, {"schema_version": "unknown"}])
def test_measurement_loaders_reject_foreign_schemas(
    tmp_path: Path, loader: Callable[[Path], dict[str, Any]], payload: object
) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        loader(path)


@pytest.mark.parametrize("rows", [None, [], ["bad"], [measurement(), measurement()]])
def test_measurement_rows_require_unique_typed_entries(rows: object) -> None:
    with pytest.raises(ValueError, match=r"BENCHMARK_(SET_INVALID|DUPLICATE)"):
        b._measurement_rows({"benchmarks": rows})


@pytest.mark.parametrize("rows", [None, ["bad"], [{}], [{"benchmark_name": "x"}] * 2])
def test_comparison_rows_reject_malformed_names(rows: object) -> None:
    assert b._comparison_rows({"comparisons": rows}) == {}


@pytest.mark.parametrize(
    "overrides",
    [
        {"logical_processor_count": True},
        {"logical_processor_count": 0},
        {"schema_version": "bad"},
        {"samples_percent": []},
        {"samples_percent": [True, 1]},
        {"samples_percent": [101, 1]},
        {"samples_percent": [100, 100]},
        {"sample_count": 3},
    ],
)
def test_host_attestation_rejects_invalid_or_busy_samples(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="HOST_LOAD_ATTESTATION_INVALID"):
        b._measurement_host_load_attestation(
            passing_host_load_attestation() | overrides
        )


def test_non_mapping_host_attestation_is_rejected() -> None:
    with pytest.raises(ValueError, match="HOST_LOAD_ATTESTATION_INVALID"):
        b._measurement_host_load_attestation(None)


def test_runtime_identity_rejects_every_noncanonical_dimension() -> None:
    assert b._current_runtime_blockers({}, "expected") == [
        "CANONICAL_RUNTIME_IMPLEMENTATION_MISMATCH",
        "CANONICAL_RUNTIME_VERSION_MISMATCH",
        "CANONICAL_RUNTIME_ARCHITECTURE_MISMATCH",
        "CANONICAL_RUNTIME_STANDARD_GIL_REQUIRED",
        "CANONICAL_RUNTIME_FREE_THREADED_FORBIDDEN",
        "CANONICAL_RUNTIME_SOABI_MISMATCH",
        "CANONICAL_RUNTIME_EXPERIMENTAL_JIT_FORBIDDEN",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "SOURCE_DUPLICATE"),
        ("set", "SET_MISMATCH"),
        ("iterations", "MEASUREMENT_MISMATCH"),
    ],
)
def test_abba_aggregation_rejects_noncomparable_runs(
    mutation: str, message: str
) -> None:
    first: dict[str, Any] = {
        "benchmarks": [measurement()],
        "host_load_attestation": passing_host_load_attestation(),
    }
    second = deepcopy(first)
    if mutation != "duplicate":
        second["run_id"] = "second"
    if mutation == "set":
        second["benchmarks"][0]["measurement"]["benchmark_name"] = "other"
    if mutation == "iterations":
        second["benchmarks"][0]["measurement"]["iterations"] = 10
    with pytest.raises(ValueError, match=message):
        b._aggregate_abba_measurements((first, second))


def test_comparison_reports_all_measurement_identity_mismatches() -> None:
    baseline: dict[str, Any] = {
        "runtime": {},
        "code_revision": "old",
        "benchmark_driver_sha256": "old",
        "benchmarks": [measurement()],
    }
    current: dict[str, Any] = {
        "runtime": {},
        "code_revision": "new",
        "benchmark_driver_sha256": "new",
        "benchmarks": [measurement()],
    }
    current["benchmarks"][0]["measurement"]["iterations"] = 10
    result = b._compare(
        baseline=baseline,
        current=current,
        baseline_version="old",
        current_version="new",
        max_regression_percent=10,
    )
    assert result["status"] == "BLOCKED"
    assert {
        "BASELINE_RUNTIME_VERSION_MISMATCH",
        "BENCHMARK_CODE_REVISION_MISMATCH",
        "BENCHMARK_DRIVER_MISMATCH",
        "BENCHMARK_CLOCK_SOURCE_MISMATCH",
        "test:BENCHMARK_ITERATION_MISMATCH",
    }.issubset(cast(list[str], result["blockers"]))
    current["benchmarks"] = []
    assert "BENCHMARK_SET_MISMATCH" in cast(
        list[str],
        b._compare(
            baseline=baseline,
            current=current,
            baseline_version="old",
            current_version="new",
            max_regression_percent=10,
        )["blockers"],
    )


@pytest.mark.parametrize("count", [0, 1, 21])
def test_stability_requires_bounded_independent_runs(count: int) -> None:
    with pytest.raises(ValueError, match="between 2 and 20"):
        b._diagnose_stability([{}] * count)


def test_stability_reports_invalid_binding_and_policy() -> None:
    result = b._diagnose_stability([{}, {"code_revision": "other"}])
    assert result["status"] == "BLOCKED"
    assert {
        "BENCHMARK_CODE_REVISION_MISMATCH",
        "BENCHMARK_DRIVER_MISMATCH",
        "BENCHMARK_CLOCK_SOURCE_MISMATCH",
        "BENCHMARK_POLICY_MISMATCH",
        "BENCHMARK_SET_MISMATCH",
    }.issubset(cast(list[str], result["blockers"]))


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("missing", "LATEST_EVIDENCE_GIT_UNAVAILABLE"),
        ("error", "LATEST_EVIDENCE_REPOSITORY_STATE_UNAVAILABLE"),
        ("failed", "LATEST_EVIDENCE_REPOSITORY_STATE_UNAVAILABLE"),
        ("ok", None),
    ],
)
def test_git_probe_classifies_read_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: str
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None if mode == "missing" else "git")
    runner = Mock(
        return_value=SimpleNamespace(
            returncode=1 if mode == "failed" else 0, stdout=" revision \n"
        )
    )
    if mode == "error":
        runner.side_effect = OSError("offline")
    monkeypatch.setattr(subprocess, "run", runner)
    assert b._git_output(tmp_path, "rev-parse", "HEAD") == (
        "revision" if mode == "ok" else None,
        expected,
    )


def test_repository_state_retains_errors_and_changed_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = Mock(return_value=(None, "UNAVAILABLE"))
    monkeypatch.setattr(b, "_git_output", probe)
    assert b._repository_state(tmp_path) == ("UNKNOWN", (), ("UNAVAILABLE",))
    probe.side_effect = [
        (str(tmp_path.parent), None),
        ("", None),
        (None, "UNAVAILABLE"),
    ]
    revision, changed, blockers = b._repository_state(tmp_path)
    assert revision == "UNKNOWN"
    assert changed == ()
    assert "LATEST_EVIDENCE_REPOSITORY_ROOT_MISMATCH" in blockers
    assert "UNAVAILABLE" in blockers
    probe.side_effect = [
        (str(tmp_path), None),
        ("head", None),
        (" M file.py\n\n?? new.py", None),
    ]
    assert b._repository_state(tmp_path) == ("head", (" M file.py", "?? new.py"), ())


@pytest.mark.parametrize(
    ("mode", "blocker"),
    [
        ("limits", "HOST_LOAD_UNAVAILABLE_DURING_MEASUREMENT"),
        ("spawn", "MEASUREMENT_PROCESS_UNAVAILABLE"),
        ("timeout", "MEASUREMENT_PROCESS_TIMEOUT"),
        ("probe", "HOST_LOAD_UNAVAILABLE_DURING_MEASUREMENT"),
        ("invalid", "HOST_LOAD_SAMPLE_INVALID_DURING_MEASUREMENT"),
        ("failed", "MEASUREMENT_PROCESS_FAILED"),
        ("empty", "MEASUREMENT_HOST_LOAD_SAMPLE_MISSING"),
        ("communicate", "MEASUREMENT_PROCESS_TIMEOUT"),
    ],
)
def test_worker_failures_stop_only_the_owned_fake_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, blocker: str
) -> None:
    limits = Mock(return_value=(20, 5, 30))
    if mode == "limits":
        limits.side_effect = OSError("unknown")
    monkeypatch.setattr(b, "_measurement_host_load_limits", limits)
    process = Mock()
    process.returncode = 1 if mode == "failed" else 0
    process.poll.return_value = (
        0 if mode in {"failed", "empty", "communicate"} else None
    )
    if mode in {"timeout", "communicate"}:
        process.terminate.side_effect = OSError("exited")
        process.kill.side_effect = OSError("exited")
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("test", 5),
            None,
            None,
        ]
    launcher = Mock(return_value=process)
    if mode == "spawn":
        launcher.side_effect = OSError("missing")
    monkeypatch.setattr(subprocess, "Popen", launcher)
    if mode == "timeout":
        monkeypatch.setattr(time, "monotonic", Mock(side_effect=[0, 10000]))
    sampler = Mock(return_value=-1)
    if mode == "probe":
        sampler.side_effect = OSError("failed")
    error, samples = b._run_measurement_process(
        python_executable=tmp_path / "python",
        repository_root=tmp_path,
        environment_id="test",
        code_revision="head",
        output=tmp_path / "result.json",
        affinity_cpu=0,
        load_sampler=sampler,
        sleeper=lambda _: None,
    )
    assert error == blocker
    assert samples == ()
    if mode in {"timeout", "probe", "invalid", "communicate"}:
        process.terminate.assert_called_once()


def test_latest_evidence_rejects_forged_pass_and_stale_stability() -> None:
    result = b._verify_latest_payload(
        {"status": "PASS", "execution_allowed": True},
        stability=passing_stability(revision="old", driver_sha256="b" * 64)
        | {"diagnostics": []},
        current_code_revision="new",
        current_driver_sha256="c" * 64,
        changed_paths=(),
    )
    assert result["status"] == "BLOCKED"
    assert {
        "LATEST_EVIDENCE_CONTRACT_INVALID",
        "LATEST_EVIDENCE_SAFETY_STATE_INVALID",
        "LATEST_EVIDENCE_POLICY_MISMATCH",
        "LATEST_EVIDENCE_STABILITY_CONTRACT_INVALID",
        "LATEST_EVIDENCE_STABILITY_REVISION_MISMATCH",
        "LATEST_EVIDENCE_STABILITY_DRIVER_MISMATCH",
        "LATEST_EVIDENCE_STABILITY_BINDING_MISSING",
    }.issubset(cast(list[str], result["blockers"]))
    assert result["execution_allowed"] is False
    with pytest.raises(ValueError, match="requires a blocked verification"):
        b._invalidate_latest_payload({}, {"status": "PASS"})


def test_process_clock_uses_cpu_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "process_time_ns", lambda: 123)
    assert b._process_clock_ns() == 123


@pytest.mark.parametrize(
    ("hashes", "error"),
    [
        (["a", "b", "changed"], "DETERMINISM_REGRESSION"),
        (["a", "b", "a", "changed"], "REPLAY_REGRESSION"),
    ],
)
def test_measurement_rejects_changed_semantics(
    monkeypatch: pytest.MonkeyPatch, hashes: list[str], error: str
) -> None:
    monkeypatch.setattr(b, "measure_operation", Mock(return_value=None))
    monkeypatch.setattr(b, "_semantic_sha256", Mock(side_effect=hashes))
    with pytest.raises(RuntimeError, match=error):
        b._measure(
            environment_id="test",
            code_revision="head",
            decision_iterations=1,
            replay_iterations=1,
            repetitions=5,
        )

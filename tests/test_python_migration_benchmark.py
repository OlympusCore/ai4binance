from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.ops import python_migration_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/workflows/runbook_python_runtime_migration_benchmark.md"


def passing_stability(
    *,
    revision: str = "current-revision",
    driver_sha256: str = "a" * 64,
) -> dict[str, object]:
    return {
        "schema_version": "python-migration-stability-evidence:v1",
        "status": "PASS",
        "blockers": [],
        "comparison_count": 2,
        "code_revision": revision,
        "benchmark_driver_sha256": driver_sha256,
        "clock_source": "process_time_ns",
        "max_regression_percent": 10.0,
        "diagnostics": [{"stable_outcome": True}],
    }


def passing_stability_binding() -> dict[str, object]:
    stability = passing_stability()
    return {
        field: stability[field]
        for field in (
            "schema_version",
            "status",
            "blockers",
            "comparison_count",
            "code_revision",
            "benchmark_driver_sha256",
            "clock_source",
            "max_regression_percent",
        )
    }


def install_advancing_process_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    tick = 0

    def clock() -> int:
        nonlocal tick
        tick += 1_000_000
        return tick

    monkeypatch.setattr(benchmark, "_process_clock_ns", clock)


def passing_host_load_attestation() -> dict[str, object]:
    return {
        "schema_version": "measurement-host-load-attestation:v1",
        "status": "PASS",
        "blockers": [],
        "external_load_budget_percent": 25.0,
        "benchmark_cpu_budget_percent": 5.0,
        "logical_processor_count": 20,
        "max_percent": 30.0,
        "required_consecutive_busy_samples": 2,
        "sample_count": 2,
        "samples_percent": [10.0, 12.0],
    }


def test_python_migration_benchmark_uses_stable_replay_measurement_horizon() -> None:
    args = benchmark._parser().parse_args(
        [
            "measure",
            "--environment-id",
            "test-windows-x86-64",
            "--code-revision",
            "test-revision",
            "--output",
            "measurement.json",
        ]
    )

    assert args.replay_iterations == 200_000
    assert args.decision_iterations == 5_000
    assert args.repetitions == 9
    assert args.affinity_cpu is None


def test_process_affinity_rejects_invalid_cpu_index() -> None:
    with pytest.raises(ValueError, match="PROCESS_AFFINITY_CPU_INVALID"):
        benchmark._set_process_affinity(-1)


def test_measure_command_records_requested_process_affinity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    requested_cpus: list[int] = []

    def pin(cpu_index: int) -> dict[str, int]:
        requested_cpus.append(cpu_index)
        return {"cpu_index": cpu_index, "mask": 1 << cpu_index}

    monkeypatch.setattr(benchmark, "_set_process_affinity", pin)
    output = tmp_path / "measurement.json"

    result = benchmark.main(
        [
            "measure",
            "--environment-id",
            "test-windows-x86-64",
            "--code-revision",
            "test-revision",
            "--output",
            str(output),
            "--decision-iterations",
            "1",
            "--replay-iterations",
            "1",
            "--repetitions",
            "3",
            "--affinity-cpu",
            "0",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert requested_cpus == [0]
    assert payload["process_affinity"] == {"cpu_index": 0, "mask": 1}


def test_abba_aggregation_blocks_conflicting_semantic_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    first = cast(
        dict[str, Any],
        benchmark._measure(
            environment_id="test-windows-x86-64",
            code_revision="test-revision",
            decision_iterations=1,
            replay_iterations=1,
            repetitions=5,
        ),
    )
    first["host_load_attestation"] = passing_host_load_attestation()
    second = cast(dict[str, Any], json.loads(json.dumps(first)))
    second["benchmarks"][0]["semantic_sha256"] = "0" * 64

    with pytest.raises(
        ValueError,
        match="PAIRED_BENCHMARK_AGGREGATION_SEMANTIC_MISMATCH",
    ):
        benchmark._aggregate_abba_measurements((first, second))


def test_abba_aggregation_blocks_conflicting_process_affinity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    first = cast(
        dict[str, Any],
        benchmark._measure(
            environment_id="test-windows-x86-64",
            code_revision="test-revision",
            decision_iterations=1,
            replay_iterations=1,
            repetitions=5,
            process_affinity={"cpu_index": 0, "mask": 1},
        ),
    )
    first["host_load_attestation"] = passing_host_load_attestation()
    second = cast(dict[str, Any], json.loads(json.dumps(first)))
    second["process_affinity"] = {"cpu_index": 2, "mask": 4}

    with pytest.raises(
        ValueError,
        match="PAIRED_BENCHMARK_AGGREGATION_METADATA_MISMATCH:process_affinity",
    ):
        benchmark._aggregate_abba_measurements((first, second))


def test_abba_aggregation_rejects_busy_host_load_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    first = cast(
        dict[str, Any],
        benchmark._measure(
            environment_id="test-windows-x86-64",
            code_revision="test-revision",
            decision_iterations=1,
            replay_iterations=1,
            repetitions=5,
            process_affinity={"cpu_index": 0, "mask": 1},
        ),
    )
    first["host_load_attestation"] = passing_host_load_attestation()
    second = cast(dict[str, Any], json.loads(json.dumps(first)))
    second_attestation = cast(dict[str, object], second["host_load_attestation"])
    second_attestation["sample_count"] = 3
    second_attestation["samples_percent"] = [10.0, 40.0, 45.0]

    with pytest.raises(
        ValueError,
        match="MEASUREMENT_HOST_LOAD_ATTESTATION_INVALID",
    ):
        benchmark._aggregate_abba_measurements((first, second))


def test_comparison_blocks_cross_runtime_process_affinity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    baseline = cast(
        dict[str, Any],
        benchmark._measure(
            environment_id="test-windows-x86-64",
            code_revision="test-revision",
            decision_iterations=1,
            replay_iterations=1,
            repetitions=5,
            process_affinity={"cpu_index": 0, "mask": 1},
        ),
    )
    current = cast(dict[str, Any], json.loads(json.dumps(baseline)))
    current["process_affinity"] = {"cpu_index": 2, "mask": 4}

    comparison = benchmark._compare(
        baseline=baseline,
        current=current,
        baseline_version="3.14.7",
        current_version="3.14.7",
        max_regression_percent=10.0,
    )

    assert comparison["status"] == "BLOCKED"
    blockers = comparison["blockers"]
    assert isinstance(blockers, list)
    assert "BENCHMARK_PROCESS_AFFINITY_MISMATCH" in blockers


def test_python_migration_benchmark_measures_and_compares(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    measurement = tmp_path / "measurement.json"
    comparison = tmp_path / "comparison.json"
    latest = tmp_path / "latest.json"
    measured = benchmark.main(
        [
            "measure",
            "--environment-id",
            "test-windows-x86-64",
            "--code-revision",
            "test-revision",
            "--output",
            str(measurement),
            "--decision-iterations",
            "2",
            "--replay-iterations",
            "2",
            "--repetitions",
            "5",
        ]
    )

    assert measured == 0
    compared = benchmark.main(
        [
            "compare",
            "--baseline",
            str(measurement),
            "--current",
            str(measurement),
            "--output",
            str(comparison),
            "--baseline-version",
            "3.14.7",
            "--latest-output",
            str(latest),
        ]
    )

    assert compared == 0
    payload = json.loads(comparison.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["blockers"] == []
    assert payload["clock_source"] == "process_time_ns"
    assert payload["baseline_evidence_sha256"] == payload["current_evidence_sha256"]
    assert len(payload["comparisons"]) == 2
    assert all(row["passed"] is True for row in payload["comparisons"])
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert json.loads(latest.read_text(encoding="utf-8")) == payload


def test_python_migration_benchmark_blocks_semantic_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    comparison = tmp_path / "comparison.json"
    latest = tmp_path / "latest.json"
    measured = benchmark.main(
        [
            "measure",
            "--environment-id",
            "test-windows-x86-64",
            "--code-revision",
            "test-revision",
            "--output",
            str(baseline),
            "--decision-iterations",
            "1",
            "--replay-iterations",
            "1",
            "--repetitions",
            "5",
        ]
    )
    assert measured == 0
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["benchmarks"][0]["semantic_sha256"] = "0" * 64
    current.write_text(json.dumps(payload), encoding="utf-8")

    compared = benchmark.main(
        [
            "compare",
            "--baseline",
            str(baseline),
            "--current",
            str(current),
            "--output",
            str(comparison),
            "--baseline-version",
            "3.14.7",
            "--latest-output",
            str(latest),
        ]
    )

    assert compared == 2
    result = json.loads(comparison.read_text(encoding="utf-8"))
    assert result["status"] == "BLOCKED"
    assert any("DETERMINISM_REGRESSION" in item for item in result["blockers"])
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert json.loads(latest.read_text(encoding="utf-8")) == result


def test_python_migration_stability_diagnosis_blocks_outcome_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    measurement = tmp_path / "measurement.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    diagnosis = tmp_path / "diagnosis.json"
    latest = tmp_path / "latest.json"
    assert (
        benchmark.main(
            [
                "measure",
                "--environment-id",
                "test-windows-x86-64",
                "--code-revision",
                "test-revision",
                "--output",
                str(measurement),
                "--decision-iterations",
                "1",
                "--replay-iterations",
                "1",
                "--repetitions",
                "5",
            ]
        )
        == 0
    )
    assert (
        benchmark.main(
            [
                "compare",
                "--baseline",
                str(measurement),
                "--current",
                str(measurement),
                "--output",
                str(first),
                "--baseline-version",
                "3.14.7",
            ]
        )
        == 0
    )
    changed = json.loads(first.read_text(encoding="utf-8"))
    changed["status"] = "BLOCKED"
    changed["blockers"] = [
        "decision-governance-evaluate:PERFORMANCE_REGRESSION_DETECTED"
    ]
    changed["comparisons"][0]["passed"] = False
    changed["comparisons"][0]["blockers"] = ["PERFORMANCE_REGRESSION_DETECTED"]
    second.write_text(json.dumps(changed), encoding="utf-8")

    diagnosed = benchmark.main(
        [
            "diagnose-stability",
            "--comparison",
            str(first),
            "--comparison",
            str(second),
            "--output",
            str(diagnosis),
            "--latest-output",
            str(latest),
        ]
    )

    assert diagnosed == 2
    payload = json.loads(diagnosis.read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED"
    assert "INPUT_COMPARISON_NOT_PASSING:2" in payload["blockers"]
    assert (
        "BENCHMARK_OUTCOME_UNSTABLE:decision-governance-evaluate" in payload["blockers"]
    )
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_payload["status"] == "BLOCKED"
    assert any(
        item.startswith("stability:BENCHMARK_OUTCOME_UNSTABLE")
        for item in latest_payload["blockers"]
    )
    assert latest_payload["stability_evidence"]["status"] == "BLOCKED"


def test_python_migration_stability_rejects_duplicate_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    measurement = tmp_path / "measurement.json"
    comparison = tmp_path / "comparison.json"
    diagnosis = tmp_path / "diagnosis.json"
    assert (
        benchmark.main(
            [
                "measure",
                "--environment-id",
                "test-windows-x86-64",
                "--code-revision",
                "test-revision",
                "--output",
                str(measurement),
                "--decision-iterations",
                "1",
                "--replay-iterations",
                "1",
                "--repetitions",
                "5",
            ]
        )
        == 0
    )
    assert (
        benchmark.main(
            [
                "compare",
                "--baseline",
                str(measurement),
                "--current",
                str(measurement),
                "--output",
                str(comparison),
                "--baseline-version",
                "3.14.7",
            ]
        )
        == 0
    )

    diagnosed = benchmark.main(
        [
            "diagnose-stability",
            "--comparison",
            str(comparison),
            "--comparison",
            str(comparison),
            "--output",
            str(diagnosis),
        ]
    )

    assert diagnosed == 2
    payload = json.loads(diagnosis.read_text(encoding="utf-8"))
    assert "BENCHMARK_STABILITY_INPUT_DUPLICATE" in payload["blockers"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_python_migration_stability_rejects_invalid_measurement_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_advancing_process_clock(monkeypatch)
    measurement = tmp_path / "measurement.json"
    comparison = tmp_path / "comparison.json"
    assert (
        benchmark.main(
            [
                "measure",
                "--environment-id",
                "test-windows-x86-64",
                "--code-revision",
                "test-revision",
                "--output",
                str(measurement),
                "--decision-iterations",
                "1",
                "--replay-iterations",
                "1",
                "--repetitions",
                "5",
            ]
        )
        == 0
    )
    assert (
        benchmark.main(
            [
                "compare",
                "--baseline",
                str(measurement),
                "--current",
                str(measurement),
                "--output",
                str(comparison),
                "--baseline-version",
                "3.14.7",
            ]
        )
        == 0
    )
    valid_payload = json.loads(comparison.read_text(encoding="utf-8"))
    invalid_payload = dict(valid_payload)
    invalid_payload["current_evidence_sha256"] = "not-a-sha256"

    diagnosis = benchmark._diagnose_stability([valid_payload, invalid_payload])

    assert diagnosis["status"] == "BLOCKED"
    blockers = diagnosis["blockers"]
    assert isinstance(blockers, list)
    assert "BENCHMARK_MEASUREMENT_EVIDENCE_BINDING_INVALID" in blockers
    assert diagnosis["execution_allowed"] is False
    assert diagnosis["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_latest_pass_is_rejected_when_subject_is_stale_or_dirty() -> None:
    latest = {
        "status": "PASS",
        "blockers": [],
        "code_revision": "old-revision",
        "benchmark_driver_sha256": "a" * 64,
        "clock_source": "process_time_ns",
        "max_regression_percent": 10.0,
        "current_runtime": {
            "implementation": "CPython",
            "version": "3.14.7",
            "machine": "amd64",
            "gil_enabled": True,
            "py_gil_disabled": 0,
            "soabi": "cp314-win_amd64",
            "jit_enabled": False,
        },
        "comparisons": [
            {"benchmark_name": "decision-governance-evaluate", "passed": True}
        ],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "stability_evidence": passing_stability_binding(),
    }

    result = benchmark._verify_latest_payload(
        latest,
        stability=passing_stability(),
        current_code_revision="current-revision",
        current_driver_sha256="b" * 64,
        changed_paths=(" M src/ai4binance/example.py",),
    )

    assert result["status"] == "BLOCKED"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "LATEST_EVIDENCE_CODE_REVISION_MISMATCH" in blockers
    assert "LATEST_EVIDENCE_DRIVER_MISMATCH" in blockers
    assert "LATEST_EVIDENCE_REPOSITORY_DIRTY" in blockers
    assert result["execution_allowed"] is False
    assert result["promotion_status"] == "RESEARCH_ONLY"
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    invalid_clock = dict(latest)
    invalid_clock["clock_source"] = "perf_counter_ns"
    invalid_result = benchmark._verify_latest_payload(
        invalid_clock,
        stability=passing_stability(),
        current_code_revision="current-revision",
        current_driver_sha256="a" * 64,
        changed_paths=(),
    )
    invalid_blockers = invalid_result["blockers"]
    assert isinstance(invalid_blockers, list)
    assert "LATEST_EVIDENCE_CLOCK_SOURCE_MISMATCH" in invalid_blockers


def test_latest_pass_is_accepted_only_for_the_exact_clean_subject() -> None:
    latest = {
        "status": "PASS",
        "blockers": [],
        "code_revision": "current-revision",
        "benchmark_driver_sha256": "a" * 64,
        "clock_source": "process_time_ns",
        "max_regression_percent": 10.0,
        "current_runtime": {
            "implementation": "CPython",
            "version": "3.14.7",
            "machine": "amd64",
            "gil_enabled": True,
            "py_gil_disabled": 0,
            "soabi": "cp314-win_amd64",
            "jit_enabled": False,
        },
        "comparisons": [
            {"benchmark_name": "decision-governance-evaluate", "passed": True}
        ],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "stability_evidence": passing_stability_binding(),
    }

    result = benchmark._verify_latest_payload(
        latest,
        stability=passing_stability(),
        current_code_revision="current-revision",
        current_driver_sha256="a" * 64,
        changed_paths=(),
    )

    assert result["status"] == "PASS"
    assert result["blockers"] == []
    assert result["execution_allowed"] is False
    assert result["promotion_status"] == "RESEARCH_ONLY"
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_latest_pass_is_rejected_when_stability_is_blocked() -> None:
    latest = {
        "status": "PASS",
        "blockers": [],
        "code_revision": "current-revision",
        "benchmark_driver_sha256": "a" * 64,
        "clock_source": "process_time_ns",
        "max_regression_percent": 10.0,
        "current_runtime": {
            "implementation": "CPython",
            "version": "3.14.7",
            "machine": "amd64",
            "gil_enabled": True,
            "py_gil_disabled": 0,
            "soabi": "cp314-win_amd64",
            "jit_enabled": False,
        },
        "comparisons": [
            {"benchmark_name": "decision-governance-evaluate", "passed": True}
        ],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "stability_evidence": passing_stability_binding(),
    }
    stability = passing_stability()
    stability["status"] = "BLOCKED"
    stability["blockers"] = ["BENCHMARK_OUTCOME_UNSTABLE"]

    result = benchmark._verify_latest_payload(
        latest,
        stability=stability,
        current_code_revision="current-revision",
        current_driver_sha256="a" * 64,
        changed_paths=(),
    )

    assert result["status"] == "BLOCKED"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "LATEST_EVIDENCE_STABILITY_NOT_PASSING" in blockers
    assert result["execution_allowed"] is False
    assert result["promotion_status"] == "RESEARCH_ONLY"
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_verify_latest_invalidates_the_stale_pass_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_path = tmp_path / "latest.json"
    stability_path = tmp_path / "stability.json"
    verification_path = tmp_path / "verification.json"
    stability = passing_stability()
    latest = {
        "schema_version": "python-migration-performance-evidence:v1",
        "status": "PASS",
        "blockers": [],
        "code_revision": "old-revision",
        "benchmark_driver_sha256": "a" * 64,
        "clock_source": "process_time_ns",
        "max_regression_percent": 10.0,
        "current_runtime": {
            "implementation": "CPython",
            "version": "3.14.7",
            "machine": "amd64",
            "gil_enabled": True,
            "py_gil_disabled": 0,
            "soabi": "cp314-win_amd64",
            "jit_enabled": False,
        },
        "comparisons": [
            {"benchmark_name": "decision-governance-evaluate", "passed": True}
        ],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "stability_evidence": passing_stability_binding(),
    }
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    stability_path.write_text(json.dumps(stability), encoding="utf-8")

    def clean_repository_state(
        _: Path,
    ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        return "current-revision", (), ()

    monkeypatch.setattr(benchmark, "_repository_state", clean_repository_state)
    monkeypatch.setattr(benchmark, "_driver_sha256", lambda: "a" * 64)

    verified = benchmark.main(
        [
            "verify-latest",
            "--latest",
            str(latest_path),
            "--stability",
            str(stability_path),
            "--repository-root",
            str(tmp_path),
            "--output",
            str(verification_path),
        ]
    )

    assert verified == 2
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    invalidated = json.loads(latest_path.read_text(encoding="utf-8"))
    assert verification["status"] == "BLOCKED"
    assert "LATEST_EVIDENCE_CODE_REVISION_MISMATCH" in verification["blockers"]
    assert invalidated["status"] == "BLOCKED"
    assert (
        "verification:LATEST_EVIDENCE_CODE_REVISION_MISMATCH" in invalidated["blockers"]
    )
    assert invalidated["latest_verification"]["status"] == "BLOCKED"
    assert invalidated["execution_allowed"] is False
    assert invalidated["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_host_quiescence_requires_sustained_strong_idle_samples() -> None:
    loads = iter((52.0, 20.0) + (19.0,) * 11)

    quiet, samples, blocker = benchmark._await_host_quiescence(
        sampler=lambda: next(loads),
        sleeper=lambda _: None,
    )

    assert quiet is True
    assert samples == (52.0, 20.0) + (19.0,) * 11
    assert blocker is None
    assert benchmark._cpu_load_percent_between(
        (100, 300, 200),
        (140, 380, 220),
    ) == pytest.approx(60.0)


def test_host_quiescence_waits_through_transient_busy_window() -> None:
    loads = iter((42.0,) * 6 + (20.0,) * 12)
    waits: list[float] = []

    quiet, samples, blocker = benchmark._await_host_quiescence(
        sampler=lambda: next(loads),
        sleeper=waits.append,
    )

    assert quiet is True
    assert samples == (42.0,) * 6 + (20.0,) * 12
    assert waits == [0.5] * 17
    assert blocker is None


def test_paired_measurement_process_uses_stability_sampling_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_command: list[str] = []

    class FakeProcess:
        returncode = 0

        def __init__(self) -> None:
            self.poll_count = 0

        def poll(self) -> int | None:
            self.poll_count += 1
            return None if self.poll_count == 1 else 0

        def communicate(self, **_: object) -> tuple[str, str]:
            return "", ""

        def terminate(self) -> None:
            self.returncode = -1

        def kill(self) -> None:
            self.returncode = -1

    def fake_popen(command: list[str], **_: object) -> FakeProcess:
        captured_command.extend(command)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    python_executable = tmp_path / "python.exe"
    output = tmp_path / "measurement.json"

    blocker, samples = benchmark._run_measurement_process(
        python_executable=python_executable,
        repository_root=tmp_path,
        environment_id="test-windows-amd64",
        code_revision="test-revision",
        output=output,
        affinity_cpu=0,
        load_sampler=lambda: 10.0,
        sleeper=lambda _: None,
    )

    assert blocker is None
    assert samples == (10.0,)
    assert captured_command[-4:] == [
        "--repetitions",
        str(benchmark._PAIRED_REPETITIONS),
        "--affinity-cpu",
        "0",
    ]
    assert benchmark._PAIRED_REPETITIONS == 21


def test_paired_measurement_process_blocks_sustained_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BusyProcess:
        returncode = 0
        terminated = False

        def poll(self) -> None:
            return None

        def communicate(self, **_: object) -> tuple[str, str]:
            return "", ""

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -1

        def kill(self) -> None:
            self.terminated = True
            self.returncode = -1

    process = BusyProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(os, "cpu_count", lambda: 20)
    loads = iter((40.0, 45.0))

    blocker, samples = benchmark._run_measurement_process(
        python_executable=tmp_path / "python.exe",
        repository_root=tmp_path,
        environment_id="test-windows-amd64",
        code_revision="test-revision",
        output=tmp_path / "measurement.json",
        affinity_cpu=0,
        load_sampler=lambda: next(loads),
        sleeper=lambda _: None,
    )

    assert blocker == "HOST_NOT_QUIESCENT_DURING_MEASUREMENT"
    assert samples == (40.0, 45.0)
    assert process.terminated is True


def test_paired_benchmark_records_mutation_immediately_after_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 20)
    evidence_root = tmp_path / "runtime" / "artifacts" / "python_migration"
    evidence_root.mkdir(parents=True)
    baseline_python = tmp_path / "python312.exe"
    current_python = tmp_path / "python314.exe"
    baseline_python.write_text("test", encoding="utf-8")
    current_python.write_text("test", encoding="utf-8")
    measurement_calls = 0
    repository_states = iter(
        (
            ("current-revision", (), ()),
            ("current-revision", (), ()),
            ("current-revision", (" M tracked.py",), ()),
            ("current-revision", (" M tracked.py",), ()),
        )
    )

    monkeypatch.setattr(
        benchmark,
        "_repository_state",
        lambda _: next(repository_states),
    )
    monkeypatch.setattr(benchmark, "_driver_sha256", lambda: "a" * 64)
    monkeypatch.setattr(
        benchmark,
        "_await_host_quiescence",
        lambda: (True, (10.0,) * 12, None),
    )

    def blocked_measurement(**_: object) -> tuple[str | None, tuple[float, ...]]:
        nonlocal measurement_calls
        measurement_calls += 1
        return "HOST_NOT_QUIESCENT_DURING_MEASUREMENT", (40.0, 45.0)

    monkeypatch.setattr(benchmark, "_run_measurement_process", blocked_measurement)

    orchestration = benchmark._run_paired_benchmark(
        baseline_python=baseline_python,
        current_python=current_python,
        baseline_version="3.12.10",
        repository_root=tmp_path,
        output_directory=evidence_root / "mutation-run",
        latest_output=evidence_root / "latest.json",
        environment_id="test-windows-amd64",
    )

    assert measurement_calls == 1
    assert orchestration["status"] == "BLOCKED"
    blockers = orchestration["blockers"]
    assert isinstance(blockers, list)
    assert "REPOSITORY_MUTATED_DURING_PAIRED_BENCHMARK" in blockers
    assert "HOST_NOT_QUIESCENT_DURING_MEASUREMENT:round-1:baseline" in blockers


def test_paired_benchmark_blocks_before_measurement_when_host_is_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 20)
    evidence_root = tmp_path / "runtime" / "artifacts" / "python_migration"
    evidence_root.mkdir(parents=True)
    baseline_python = tmp_path / "python312.exe"
    current_python = tmp_path / "python314.exe"
    baseline_python.write_text("test", encoding="utf-8")
    current_python.write_text("test", encoding="utf-8")
    process_called = False

    monkeypatch.setattr(
        benchmark,
        "_repository_state",
        lambda _: ("current-revision", (), ()),
    )
    monkeypatch.setattr(benchmark, "_driver_sha256", lambda: "a" * 64)
    monkeypatch.setattr(
        benchmark,
        "_await_host_quiescence",
        lambda: (
            False,
            (42.0,) * benchmark._QUIESCENCE_ATTEMPTS,
            "HOST_NOT_QUIESCENT",
        ),
    )

    def unexpected_measurement(
        **_: object,
    ) -> tuple[str | None, tuple[float, ...]]:
        nonlocal process_called
        process_called = True
        return None, (10.0, 12.0)

    monkeypatch.setattr(benchmark, "_run_measurement_process", unexpected_measurement)
    latest = evidence_root / "latest.json"
    output_directory = evidence_root / "busy-run"

    result = benchmark.main(
        [
            "run-paired",
            "--baseline-python",
            str(baseline_python),
            "--current-python",
            str(current_python),
            "--baseline-version",
            "3.12.10",
            "--repository-root",
            str(tmp_path),
            "--output-directory",
            str(output_directory),
            "--latest-output",
            str(latest),
            "--environment-id",
            "test-windows-amd64",
        ]
    )

    orchestration = json.loads(
        (output_directory / "orchestration.json").read_text(encoding="utf-8")
    )
    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    stability_path = output_directory / "stability-diagnosis.json"
    stability = json.loads(stability_path.read_text(encoding="utf-8"))
    verification_path = output_directory / "latest-verification.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    assert result == 2
    assert process_called is False
    assert orchestration["status"] == "BLOCKED"
    assert orchestration["measurement_order"] == [
        ["baseline", "current"],
        ["current", "baseline"],
        ["baseline", "current"],
        ["current", "baseline"],
    ]
    assert orchestration["measurement_policy"] == {
        "clock_source": "process_time_ns",
        "repetitions_per_round_per_runtime": 21,
        "samples_per_cycle_per_runtime": 42,
        "process_affinity_cpu": 0,
        "process_affinity_mask": 1,
        "max_attempts_per_round_runtime": 3,
    }
    assert orchestration["host_load_policy"] == {
        "max_percent": 20.0,
        "attempts": 120,
        "required_consecutive_samples": 12,
        "probe_seconds": 0.5,
        "wait_seconds": 0.5,
        "max_wait_seconds": 119.5,
        "during_measurement_required_consecutive_busy_samples": 2,
        "during_measurement_load_limits": {
            "external_load_budget_percent": 25.0,
            "benchmark_cpu_budget_percent": 5.0,
            "logical_processor_count": 20,
            "max_percent": 30.0,
        },
    }
    assert len(orchestration["quiescence_checks"]) == 3
    assert [
        item["measurement_attempt"] for item in orchestration["quiescence_checks"]
    ] == [1, 2, 3]
    assert "HOST_NOT_QUIESCENT:round-1:baseline" in orchestration["blockers"]
    assert orchestration["stability_path"] == str(stability_path)
    assert orchestration["verification_path"] == str(verification_path)
    assert stability["status"] == "BLOCKED"
    assert stability["comparison_count"] == 0
    assert stability["code_revision"] == "current-revision"
    assert "BENCHMARK_STABILITY_INSUFFICIENT_COMPARISONS" in stability["blockers"]
    assert stability["execution_allowed"] is False
    assert verification["status"] == "BLOCKED"
    assert verification["current_code_revision"] == "current-revision"
    assert "LATEST_EVIDENCE_NOT_PASSING" in verification["blockers"]
    assert "LATEST_EVIDENCE_STABILITY_NOT_PASSING" in verification["blockers"]
    assert verification["execution_allowed"] is False
    assert latest_payload["status"] == "BLOCKED"
    assert latest_payload["stability_evidence"]["status"] == "BLOCKED"
    assert latest_payload["stability_evidence"]["code_revision"] == ("current-revision")
    assert latest_payload["latest_verification"]["status"] == "BLOCKED"
    assert latest_payload["latest_verification"]["current_code_revision"] == (
        "current-revision"
    )
    assert latest_payload["execution_allowed"] is False
    assert latest_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_paired_benchmark_blocks_while_quality_gate_mutex_is_owned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 20)
    evidence_root = tmp_path / "runtime" / "artifacts" / "python_migration"
    evidence_root.mkdir(parents=True)
    baseline_python = tmp_path / "python312.exe"
    current_python = tmp_path / "python314.exe"
    baseline_python.write_text("test", encoding="utf-8")
    current_python.write_text("test", encoding="utf-8")
    measurement_called = False

    monkeypatch.setattr(
        benchmark,
        "_repository_state",
        lambda _: ("current-revision", (), ()),
    )
    monkeypatch.setattr(benchmark, "_driver_sha256", lambda: "a" * 64)
    monkeypatch.setattr(
        benchmark,
        "_try_acquire_quality_gate_mutex",
        lambda _: (None, "QUALITY_GATE_ALREADY_RUNNING"),
    )

    def unexpected_measurement(**_: object) -> tuple[str | None, tuple[float, ...]]:
        nonlocal measurement_called
        measurement_called = True
        return None, (10.0, 12.0)

    monkeypatch.setattr(benchmark, "_run_measurement_process", unexpected_measurement)
    latest = evidence_root / "latest.json"
    output_directory = evidence_root / "quality-overlap-run"

    result = benchmark.main(
        [
            "run-paired",
            "--baseline-python",
            str(baseline_python),
            "--current-python",
            str(current_python),
            "--baseline-version",
            "3.12.10",
            "--repository-root",
            str(tmp_path),
            "--output-directory",
            str(output_directory),
            "--latest-output",
            str(latest),
            "--environment-id",
            "test-windows-amd64",
        ]
    )

    orchestration = json.loads(
        (output_directory / "orchestration.json").read_text(encoding="utf-8")
    )
    assert result == 2
    assert measurement_called is False
    assert orchestration["status"] == "BLOCKED"
    assert "QUALITY_GATE_ALREADY_RUNNING" in orchestration["blockers"]
    assert orchestration["comparison_paths"] == []
    assert orchestration["execution_allowed"] is False
    assert orchestration["promotion_status"] == "RESEARCH_ONLY"
    assert orchestration["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_paired_benchmark_rejects_output_outside_runtime(tmp_path: Path) -> None:
    baseline_python = tmp_path / "python312.exe"
    current_python = tmp_path / "python314.exe"
    baseline_python.write_text("test", encoding="utf-8")
    current_python.write_text("test", encoding="utf-8")

    with pytest.raises(ValueError, match="PAIRED_BENCHMARK_OUTPUT_OUTSIDE_RUNTIME"):
        benchmark._run_paired_benchmark(
            baseline_python=baseline_python,
            current_python=current_python,
            baseline_version="3.12.10",
            repository_root=tmp_path,
            output_directory=tmp_path / "outside",
            latest_output=tmp_path / "outside-latest.json",
            environment_id="test-windows-amd64",
        )


def test_paired_benchmark_runs_abba_and_publishes_only_verified_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = tmp_path / "runtime" / "artifacts" / "python_migration"
    evidence_root.mkdir(parents=True)
    baseline_python = tmp_path / "python312.exe"
    current_python = tmp_path / "python314.exe"
    baseline_python.write_text("test", encoding="utf-8")
    current_python.write_text("test", encoding="utf-8")
    calls: list[str] = []
    attempts = 0
    quiescence_attempts = 0
    driver_sha256 = "a" * 64

    monkeypatch.setattr(
        benchmark,
        "_repository_state",
        lambda _: ("current-revision", (), ()),
    )
    monkeypatch.setattr(benchmark, "_driver_sha256", lambda: driver_sha256)

    def await_host_quiescence() -> tuple[bool, tuple[float, ...], str | None]:
        nonlocal quiescence_attempts
        quiescence_attempts += 1
        if quiescence_attempts == 1:
            return False, (40.0, 45.0), "HOST_NOT_QUIESCENT"
        return True, (10.0, 12.0), None

    monkeypatch.setattr(benchmark, "_await_host_quiescence", await_host_quiescence)

    def fake_measurement(
        *,
        python_executable: Path,
        repository_root: Path,
        environment_id: str,
        code_revision: str,
        output: Path,
        affinity_cpu: int,
    ) -> tuple[str | None, tuple[float, ...]]:
        nonlocal attempts
        del repository_root
        assert affinity_cpu == 0
        attempts += 1
        if attempts == 1:
            return "HOST_NOT_QUIESCENT_DURING_MEASUREMENT", (40.0, 45.0)
        calls.append(python_executable.name)
        is_current = python_executable == current_python
        measured_at = f"2026-09-06T00:00:0{len(calls)}+00:00"
        sample = 120.0 if len(calls) % 2 == 0 else 100.0
        runtime = {
            "implementation": "CPython",
            "version": "3.14.7" if is_current else "3.12.10",
            "machine": "amd64",
            "soabi": "cp314-win_amd64" if is_current else None,
            "py_gil_disabled": 0 if is_current else None,
            "gil_enabled": True if is_current else None,
            "jit_available": is_current,
            "jit_enabled": False,
        }
        benchmarks = []
        for name, iterations in (
            ("decision-governance-evaluate", 5_000),
            ("event-replay-order-state", benchmark._DEFAULT_REPLAY_ITERATIONS),
        ):
            benchmarks.append(
                {
                    "measurement": {
                        "benchmark_name": name,
                        "environment_id": environment_id,
                        "code_revision": code_revision,
                        "measured_at": measured_at,
                        "iterations": iterations,
                        "samples_ns_per_operation": [sample] * 9,
                        "execution_allowed": False,
                        "schema_version": "1.0",
                    },
                    "semantic_sha256": "b" * 64,
                }
            )
        output.write_text(
            json.dumps(
                {
                    "schema_version": "python-migration-performance-evidence:v1",
                    "artifact_origin": "python_migration_benchmark_measurement",
                    "environment_id": environment_id,
                    "code_revision": code_revision,
                    "benchmark_driver_sha256": driver_sha256,
                    "clock_source": "process_time_ns",
                    "process_affinity": {"cpu_index": 0, "mask": 1},
                    "runtime": runtime,
                    "benchmarks": benchmarks,
                    "execution_allowed": False,
                    "promotion_status": "RESEARCH_ONLY",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                }
            ),
            encoding="utf-8",
        )
        return None, (10.0, 12.0)

    monkeypatch.setattr(benchmark, "_run_measurement_process", fake_measurement)
    latest = evidence_root / "latest.json"
    output_directory = evidence_root / "passing-run"

    result = benchmark.main(
        [
            "run-paired",
            "--baseline-python",
            str(baseline_python),
            "--current-python",
            str(current_python),
            "--baseline-version",
            "3.12.10",
            "--repository-root",
            str(tmp_path),
            "--output-directory",
            str(output_directory),
            "--latest-output",
            str(latest),
            "--environment-id",
            "test-windows-amd64",
        ]
    )

    orchestration = json.loads(
        (output_directory / "orchestration.json").read_text(encoding="utf-8")
    )
    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    first_comparison = json.loads(
        (output_directory / "cycle1-comparison.json").read_text(encoding="utf-8")
    )
    second_comparison = json.loads(
        (output_directory / "cycle2-comparison.json").read_text(encoding="utf-8")
    )
    first_baseline = json.loads(
        (output_directory / "cycle1-baseline.json").read_text(encoding="utf-8")
    )
    stability = json.loads(
        (output_directory / "stability-diagnosis.json").read_text(encoding="utf-8")
    )
    assert result == 0
    assert calls == [
        "python312.exe",
        "python314.exe",
        "python314.exe",
        "python312.exe",
        "python312.exe",
        "python314.exe",
        "python314.exe",
        "python312.exe",
    ]
    assert orchestration["status"] == "PASS"
    assert orchestration["quiescence_checks"][0]["status"] == "BLOCKED"
    assert orchestration["quiescence_checks"][0]["blocker"] == ("HOST_NOT_QUIESCENT")
    assert orchestration["quiescence_checks"][1]["status"] == "PASS"
    assert orchestration["measurement_host_load_checks"][0]["status"] == "BLOCKED"
    assert orchestration["measurement_host_load_checks"][0]["blocker"] == (
        "HOST_NOT_QUIESCENT_DURING_MEASUREMENT"
    )
    assert all(
        item["status"] == "PASS"
        for item in orchestration["measurement_host_load_checks"][1:]
    )
    assert len(orchestration["comparison_paths"]) == 2
    assert first_comparison["comparisons"] == second_comparison["comparisons"]
    assert first_comparison["status"] == "PASS"
    assert first_comparison["comparisons"][0]["baseline_median_ns"] == 110.0
    assert first_comparison["comparisons"][0]["current_median_ns"] == 110.0
    assert first_baseline["aggregation"] == {
        "method": "ABBA_ORDER_BALANCED_SAMPLE_POOL",
        "source_count": 2,
    }
    assert first_baseline["process_affinity"] == {"cpu_index": 0, "mask": 1}
    assert len(first_baseline["source_host_load_attestations"]) == 2
    assert len(first_baseline["source_measurement_evidence_sha256s"]) == 2
    assert (
        len(first_baseline["benchmarks"][0]["measurement"]["samples_ns_per_operation"])
        == 18
    )
    assert (
        first_comparison["baseline_evidence_sha256"]
        != second_comparison["baseline_evidence_sha256"]
    )
    assert (
        first_comparison["current_evidence_sha256"]
        != second_comparison["current_evidence_sha256"]
    )
    assert stability["status"] == "PASS"
    assert len(set(stability["comparison_sha256s"])) == 2
    assert len(stability["measurement_evidence_bindings"]) == 2
    assert latest_payload["status"] == "PASS"
    assert latest_payload["latest_verification"]["status"] == "PASS"
    assert latest_payload["execution_allowed"] is False
    assert latest_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_python_migration_benchmark_has_permanent_fail_closed_rule() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "src/ai4binance/ops/python_migration_benchmark.py" in text
    assert "--max-regression-percent 10" in text
    assert "semantic digest mismatch" in text
    assert "execution_allowed=false" in text
    assert "promotion_status=RESEARCH_ONLY" in text
    assert "live_eligibility_status=LIVE_ORDER_BLOCKED" in text

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.ops.performance import (
    BenchmarkArtifactWriter,
    BenchmarkMeasurement,
    PerformanceRegressionPolicy,
    compare_performance,
    measure_operation,
)
from ai4binance.storage import JsonlAuditStore

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def test_resource_probe_measures_one_real_call_without_approving_a_budget() -> None:
    from ai4binance.ops.performance import measure_resource_operation

    calls: list[str] = []
    result, measured = measure_resource_operation(lambda: calls.append("called"))
    assert result is None
    assert calls == ["called"]
    assert measured.max_duration_ms >= 0
    assert measured.cpu_time_ms >= 0
    assert measured.peak_ram_mb is None or measured.peak_ram_mb > 0
    assert measured.disk_io_bytes is None or measured.disk_io_bytes >= 0
    assert measured.llm_calls is None
    assert measured.max_retries is None
    assert measured.budget_status == "NOT_VERIFIED"
    assert measured.counter_scope == "SHARED_PROCESS_DURING_OPERATION"
    assert not measured.execution_allowed


def test_resource_probe_keeps_unsupported_counters_unknown_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.ops.performance as performance

    monkeypatch.setattr(performance, "_process_resource_snapshot", lambda: (None, None))
    _, measured = performance.measure_resource_operation(lambda: 7)
    assert measured.disk_io_bytes is None
    assert measured.peak_ram_mb is None
    with pytest.raises(ZeroDivisionError):
        performance.measure_resource_operation(lambda: 1 / 0)


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_resource_probe_rejects_invalid_measurements(value: float) -> None:
    from ai4binance.ops.performance import OperationResourceMeasurement

    with pytest.raises(ValueError, match="finite"):
        OperationResourceMeasurement(value, 0, None, None)


def test_resource_probe_does_not_turn_an_observation_into_an_approved_budget() -> None:
    from ai4binance.ops.performance import OperationResourceMeasurement

    with pytest.raises(ValueError, match="cannot approve"):
        OperationResourceMeasurement(0, 0, None, None, budget_status="APPROVED")


def test_resource_summary_retains_unknown_counters_and_failure_samples() -> None:
    from ai4binance.ops.performance import (
        OperationResourceMeasurement,
        summarize_resource_measurements,
    )

    # These numeric samples exercise summary semantics only, never runtime proof.
    samples = (
        OperationResourceMeasurement(1, 1, 4, 2),
        OperationResourceMeasurement(
            3, 2, None, None, operation_status="ERROR", error_type="ValueError"
        ),
        OperationResourceMeasurement(
            2, 1, 5, 4, operation_status="TIMEOUT", error_type="TimeoutError"
        ),
    )
    summary = summarize_resource_measurements(samples)
    assert summary["measurement_count"] == 3
    assert summary["operation_counts"] == {"SUCCESS": 1, "ERROR": 1, "TIMEOUT": 1}
    assert summary["evidence_class"] == "OBSERVED_SAMPLES_ONLY"
    assert summary["execution_allowed"] is False
    metrics = summary["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["max_duration_ms"] == {
        "measured_sample_count": 3,
        "unmeasured_sample_count": 0,
        "minimum": 1,
        "median": 2,
        "p95": 3,
        "maximum": 3,
    }
    assert metrics["peak_ram_mb"]["unmeasured_sample_count"] == 1
    assert metrics["disk_io_bytes"]["measured_sample_count"] == 2
    assert metrics["llm_calls"]["maximum"] is None
    assert metrics["gpu_memory_mb"]["maximum"] is None
    assert summary["timeout_policies"] == ["NOT_CONFIGURED"]


def test_empty_resource_summary_does_not_turn_missing_data_into_zero_usage() -> None:
    from ai4binance.ops.performance import summarize_resource_measurements

    summary = summarize_resource_measurements(())
    assert summary["measurement_count"] == 0
    metrics = summary["metrics"]
    assert isinstance(metrics, dict)
    assert all(metric["maximum"] is None for metric in metrics.values())
    assert summary["memory_scopes"] == []
    assert summary["execution_allowed"] is False


def measurement(
    samples: tuple[float, ...],
    *,
    name: str = "decision-cycle",
    environment: str = "ci-windows-py312",
) -> BenchmarkMeasurement:
    return BenchmarkMeasurement(
        benchmark_name=name,
        environment_id=environment,
        code_revision="abc123",
        measured_at=NOW,
        iterations=10,
        samples_ns_per_operation=samples,
    )


def test_measure_operation_uses_bounded_injected_clock() -> None:
    ticks = iter((0, 100, 100, 220, 220, 360))
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1

    result = measure_operation(
        benchmark_name="small-operation",
        operation=operation,
        environment_id="test-host",
        code_revision="revision-1",
        iterations=10,
        repetitions=3,
        clock=lambda: next(ticks),
        measured_at=NOW,
    )

    assert calls == 31
    assert result.samples_ns_per_operation == (10.0, 12.0, 14.0)
    assert result.median_ns_per_operation == 12.0
    assert result.p95_ns_per_operation == 14.0
    assert result.execution_allowed is False


@pytest.mark.parametrize(
    ("baseline", "current", "policy", "passed", "blockers", "regression"),
    [
        (
            measurement((100, 100, 100, 100, 100)),
            measurement((105, 105, 105, 105, 105)),
            PerformanceRegressionPolicy(),
            True,
            (),
            5.0,
        ),
        (
            measurement((100, 100, 100, 100, 100)),
            measurement((111, 111, 111, 111, 111)),
            PerformanceRegressionPolicy(),
            False,
            ("PERFORMANCE_REGRESSION_DETECTED",),
            11.0,
        ),
        (
            measurement((100, 100, 100)),
            measurement((100, 100, 100), name="other", environment="other-host"),
            PerformanceRegressionPolicy(minimum_samples=5),
            False,
            (
                "BENCHMARK_IDENTITY_MISMATCH",
                "BENCHMARK_ENVIRONMENT_MISMATCH",
                "BENCHMARK_SAMPLE_INSUFFICIENT",
            ),
            None,
        ),
    ],
)
def test_compare_performance_is_fail_closed(
    baseline: BenchmarkMeasurement,
    current: BenchmarkMeasurement,
    policy: PerformanceRegressionPolicy,
    passed: bool,
    blockers: tuple[str, ...],
    regression: float | None,
) -> None:
    result = compare_performance(baseline, current, policy)
    assert result.passed is passed
    assert result.blockers == blockers
    if regression is None:
        assert result.regression_percent is None
    else:
        assert result.regression_percent == pytest.approx(regression)
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_artifact_writer_is_atomic_and_audited(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    path = tmp_path / "latest.json"
    baseline = measurement((100, 100, 100, 100, 100))
    current = measurement((105, 105, 105, 105, 105))
    comparison = compare_performance(baseline, current)

    BenchmarkArtifactWriter(path, JsonlAuditStore(audit_path)).write(
        current, comparison
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["measurement"]["benchmark_name"] == "decision-cycle"
    assert payload["comparison"]["passed"] is True
    assert payload["execution_allowed"] is False
    assert not path.with_suffix(".json.tmp").exists()
    assert "PERFORMANCE_BENCHMARK_RECORDED" in audit_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: measurement((1.0, 2.0)),
        lambda: BenchmarkMeasurement(
            "name", "env", "rev", datetime(2026, 1, 1), 1, (1.0, 2.0, 3.0)
        ),
        lambda: measurement((1.0, 0.0, 3.0)),
        lambda: PerformanceRegressionPolicy(max_regression_percent=-1),
        lambda: PerformanceRegressionPolicy(minimum_samples=2),
    ],
)
def test_invalid_benchmark_contracts_are_rejected(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"must|requires|samples"):
        factory()


@pytest.mark.parametrize(("iterations", "repetitions"), [(0, 3), (1, 2)])
def test_measurement_bounds_are_rejected(iterations: int, repetitions: int) -> None:
    with pytest.raises(ValueError, match=r"iterations|repetitions"):
        measure_operation(
            benchmark_name="name",
            operation=lambda: None,
            environment_id="env",
            code_revision="rev",
            iterations=iterations,
            repetitions=repetitions,
        )


def test_non_advancing_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="clock"):
        measure_operation(
            benchmark_name="name",
            operation=lambda: None,
            environment_id="env",
            code_revision="rev",
            iterations=1,
            repetitions=3,
            clock=lambda: 1,
            measured_at=NOW,
        )

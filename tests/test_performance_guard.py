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

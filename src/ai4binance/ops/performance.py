"""Environment-bound performance evidence and fail-closed regression gates."""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified


def _require_text(name: str, value: str) -> None:
    if not value.strip() or len(value) > 500:
        raise ValueError(f"{name} must be non-empty and bounded")


@dataclass(frozen=True, slots=True)
class BenchmarkMeasurement:
    """One immutable local benchmark result; never a cross-host guarantee."""

    benchmark_name: str
    environment_id: str
    code_revision: str
    measured_at: datetime
    iterations: int
    samples_ns_per_operation: tuple[float, ...]
    execution_allowed: bool = False
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _require_text("benchmark_name", self.benchmark_name)
        _require_text("environment_id", self.environment_id)
        _require_text("code_revision", self.code_revision)
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        if not 1 <= self.iterations <= 1_000_000:
            raise ValueError("iterations must be between 1 and 1,000,000")
        if not 3 <= len(self.samples_ns_per_operation) <= 100:
            raise ValueError("benchmark requires between 3 and 100 samples")
        if any(sample <= 0 for sample in self.samples_ns_per_operation):
            raise ValueError("benchmark samples must be positive")
        if self.execution_allowed:
            raise ValueError("benchmark evidence cannot authorize execution")

    @property
    def median_ns_per_operation(self) -> float:
        return float(statistics.median(self.samples_ns_per_operation))

    @property
    def p95_ns_per_operation(self) -> float:
        ordered = sorted(self.samples_ns_per_operation)
        index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
        return float(ordered[index])


@dataclass(frozen=True, slots=True)
class PerformanceRegressionPolicy:
    """Host-scoped regression threshold; it does not weaken quality gates."""

    max_regression_percent: float = 10.0
    minimum_samples: int = 5

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_regression_percent <= 100.0:
            raise ValueError("max_regression_percent must be between 0 and 100")
        if not 3 <= self.minimum_samples <= 100:
            raise ValueError("minimum_samples must be between 3 and 100")


@dataclass(frozen=True, slots=True)
class PerformanceComparison:
    benchmark_name: str
    environment_id: str
    baseline_median_ns: float
    current_median_ns: float
    regression_percent: float | None
    passed: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.passed == bool(self.blockers):
            raise ValueError("performance result and blockers disagree")
        if self.execution_allowed:
            raise ValueError("performance comparison cannot authorize execution")


def measure_operation(
    *,
    benchmark_name: str,
    operation: Callable[[], object],
    environment_id: str,
    code_revision: str,
    iterations: int = 1_000,
    repetitions: int = 7,
    clock: Callable[[], int] = time.perf_counter_ns,
    measured_at: datetime | None = None,
) -> BenchmarkMeasurement:
    """Measure a bounded callable after one warm-up invocation."""
    if not 1 <= iterations <= 1_000_000:
        raise ValueError("iterations must be between 1 and 1,000,000")
    if not 3 <= repetitions <= 100:
        raise ValueError("repetitions must be between 3 and 100")
    operation()
    samples: list[float] = []
    for _ in range(repetitions):
        started = clock()
        for _ in range(iterations):
            operation()
        elapsed = clock() - started
        if elapsed <= 0:
            raise ValueError("benchmark clock must advance")
        samples.append(elapsed / iterations)
    return BenchmarkMeasurement(
        benchmark_name=benchmark_name,
        environment_id=environment_id,
        code_revision=code_revision,
        measured_at=measured_at or datetime.now(UTC),
        iterations=iterations,
        samples_ns_per_operation=tuple(samples),
    )


def compare_performance(
    baseline: BenchmarkMeasurement,
    current: BenchmarkMeasurement,
    policy: PerformanceRegressionPolicy | None = None,
) -> PerformanceComparison:
    """Compare only like-for-like evidence and block material regressions."""
    policy = policy or PerformanceRegressionPolicy()
    blockers: list[str] = []
    if baseline.benchmark_name != current.benchmark_name:
        blockers.append("BENCHMARK_IDENTITY_MISMATCH")
    if baseline.environment_id != current.environment_id:
        blockers.append("BENCHMARK_ENVIRONMENT_MISMATCH")
    if (
        len(baseline.samples_ns_per_operation) < policy.minimum_samples
        or len(current.samples_ns_per_operation) < policy.minimum_samples
    ):
        blockers.append("BENCHMARK_SAMPLE_INSUFFICIENT")

    regression: float | None = None
    if not blockers:
        regression = (
            (current.median_ns_per_operation - baseline.median_ns_per_operation)
            / baseline.median_ns_per_operation
            * 100.0
        )
        if regression > policy.max_regression_percent:
            blockers.append("PERFORMANCE_REGRESSION_DETECTED")
    return PerformanceComparison(
        benchmark_name=current.benchmark_name,
        environment_id=current.environment_id,
        baseline_median_ns=baseline.median_ns_per_operation,
        current_median_ns=current.median_ns_per_operation,
        regression_percent=regression,
        passed=not blockers,
        blockers=tuple(blockers),
    )


@dataclass(frozen=True, slots=True)
class BenchmarkArtifactWriter:
    """Atomically persist the latest evidence and append an audit event."""

    path: Path
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def write(
        self,
        measurement: BenchmarkMeasurement,
        comparison: PerformanceComparison | None = None,
    ) -> None:
        payload = {
            "measurement": to_primitive(measurement),
            "comparison": to_primitive(comparison) if comparison else None,
            "execution_allowed": False,
            "schema_version": "1.0",
        }
        write_json_object_verified(
            self.path,
            payload,
            blocker="PERFORMANCE_BENCHMARK_DESTINATION_VERIFY_FAILED",
            subject_id=f"{measurement.benchmark_name}:{measurement.code_revision}",
            indent=2,
            durable=True,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="PERFORMANCE_BENCHMARK_RECORDED",
                    timestamp=measurement.measured_at,
                    snapshot_id=(
                        f"{measurement.benchmark_name}:{measurement.code_revision}"
                    ),
                    payload=payload,
                )
            )

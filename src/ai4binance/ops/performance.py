"""Environment-bound performance evidence and fail-closed regression gates."""

from __future__ import annotations

import ctypes
import importlib
import os
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any, cast

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


@dataclass(frozen=True, slots=True)
class OperationResourceMeasurement:
    """Observed process counters for one operation, never an approved budget."""

    max_duration_ms: float
    cpu_time_ms: float
    peak_ram_mb: float | None
    disk_io_bytes: int | None
    max_retries: int | None = None
    llm_calls: int | None = None
    timeout_policy: str = "NOT_CONFIGURED"
    memory_scope: str = "PROCESS_LIFETIME_HIGH_WATERMARK"
    counter_scope: str = "SHARED_PROCESS_DURING_OPERATION"
    budget_status: str = "NOT_VERIFIED"
    execution_allowed: bool = False
    operation_status: str = "SUCCESS"
    error_type: str | None = None
    gpu_memory_mb: float | None = None
    operation_scope: str = "CALLABLE_ONLY"

    def __post_init__(self) -> None:
        for value in (
            self.max_duration_ms,
            self.cpu_time_ms,
            self.peak_ram_mb,
            self.gpu_memory_mb,
        ):
            if value is not None and (
                isinstance(value, bool) or not isfinite(value) or value < 0
            ):
                raise ValueError("resource measurements must be finite and nonnegative")
        for value in (self.disk_io_bytes, self.max_retries, self.llm_calls):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("resource counters must be nonnegative")
        if self.operation_status not in {"SUCCESS", "ERROR", "TIMEOUT"}:
            raise ValueError("resource operation status is invalid")
        if self.operation_scope not in {"CALLABLE_ONLY", "CORE_HANDOFF"}:
            raise ValueError("resource operation scope is invalid")
        if (self.operation_status == "SUCCESS") != (self.error_type is None):
            raise ValueError("resource operation status and error type disagree")
        if self.execution_allowed or self.budget_status != "NOT_VERIFIED":
            raise ValueError(
                "resource observations cannot approve a budget or execution"
            )


def measure_resource_operation[T](
    operation: Callable[[], T],
    *,
    on_measurement: Callable[[OperationResourceMeasurement], None] | None = None,
) -> tuple[T, OperationResourceMeasurement]:
    """Measure a real call without retries, model invocation, or authority changes."""
    _, io_before = _process_resource_snapshot()
    cpu_started = time.process_time_ns()
    started = time.perf_counter_ns()
    error: BaseException | None = None
    try:
        result = operation()
    except BaseException as failure:
        error = failure
        raise
    finally:
        elapsed = time.perf_counter_ns() - started
        cpu_elapsed = time.process_time_ns() - cpu_started
        peak_ram, io_after = _process_resource_snapshot()
        disk_io = (
            io_after - io_before
            if io_before is not None and io_after is not None and io_after >= io_before
            else None
        )
        measured = OperationResourceMeasurement(
            max_duration_ms=elapsed / 1_000_000,
            cpu_time_ms=cpu_elapsed / 1_000_000,
            peak_ram_mb=peak_ram,
            disk_io_bytes=disk_io,
            operation_status="SUCCESS"
            if error is None
            else "TIMEOUT"
            if isinstance(error, TimeoutError)
            else "ERROR",
            error_type=None if error is None else type(error).__name__,
        )
        if on_measurement is not None:
            try:
                on_measurement(measured)
            except Exception as emission_error:
                if error is not None:
                    raise error from emission_error
                raise
    return result, measured


@dataclass(frozen=True, slots=True)
class OperationResourceLimits:
    """Declared limits; their presence never establishes approval or measurement."""

    max_duration_ms: float
    cpu_time_ms: float
    peak_ram_mb: float
    disk_io_bytes: int
    max_retries: int
    llm_calls: int
    gpu_memory_mb: float
    timeout_policy: str
    memory_scope: str

    def __post_init__(self) -> None:
        for value in (
            self.max_duration_ms,
            self.cpu_time_ms,
            self.peak_ram_mb,
            self.gpu_memory_mb,
        ):
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError("resource limits must be finite and nonnegative")
        for value in (self.disk_io_bytes, self.max_retries, self.llm_calls):
            if type(value) is not int or value < 0:
                raise ValueError("resource limit counters must be nonnegative integers")
        if self.timeout_policy != "RUNNER_ENFORCED":
            raise ValueError("resource limits require a runner-enforced timeout")
        if self.memory_scope != "PROCESS_LIFETIME_HIGH_WATERMARK":
            raise ValueError(
                "resource limits must match available memory counter scope"
            )


def aggregate_resource_measurements(
    measurements: Sequence[OperationResourceMeasurement],
) -> OperationResourceMeasurement:
    """Conservatively total one cycle; overlapping shared counters may overcount."""
    if not measurements:
        raise ValueError("resource aggregation requires actual observations")
    failure = next(
        (item for item in measurements if item.operation_status != "SUCCESS"), None
    )
    return OperationResourceMeasurement(
        max_duration_ms=sum(item.max_duration_ms for item in measurements),
        cpu_time_ms=sum(item.cpu_time_ms for item in measurements),
        peak_ram_mb=_peak_optional_resource(
            [item.peak_ram_mb for item in measurements]
        ),
        disk_io_bytes=_sum_optional_resource(
            [item.disk_io_bytes for item in measurements]
        ),
        max_retries=_sum_optional_resource([item.max_retries for item in measurements]),
        llm_calls=_sum_optional_resource([item.llm_calls for item in measurements]),
        gpu_memory_mb=_peak_optional_resource(
            [item.gpu_memory_mb for item in measurements]
        ),
        timeout_policy="RUNNER_ENFORCED"
        if all(item.timeout_policy == "RUNNER_ENFORCED" for item in measurements)
        else "NOT_CONFIGURED",
        operation_status="SUCCESS" if failure is None else failure.operation_status,
        error_type=None if failure is None else failure.error_type,
        operation_scope="CORE_HANDOFF"
        if all(item.operation_scope == "CORE_HANDOFF" for item in measurements)
        else "CALLABLE_ONLY",
    )


def _sum_optional_resource(values: Sequence[int | None]) -> int | None:
    return (
        None
        if any(value is None for value in values)
        else sum(value for value in values if value is not None)
    )


def _peak_optional_resource(values: Sequence[float | None]) -> float | None:
    return (
        None
        if any(value is None for value in values)
        else max(value for value in values if value is not None)
    )


def resource_budget_blockers(
    measured: OperationResourceMeasurement,
    limits: OperationResourceLimits,
) -> tuple[str, ...]:
    """Compare observed counters without approving a policy or execution."""
    blockers = []
    if measured.operation_status != "SUCCESS":
        blockers.append("RESOURCE_OPERATION_" + measured.operation_status)
    if measured.timeout_policy != limits.timeout_policy:
        blockers.append("RESOURCE_TIMEOUT_NOT_ENFORCED")
    if measured.memory_scope != limits.memory_scope:
        blockers.append("RESOURCE_MEMORY_SCOPE_MISMATCH")
    for field_name in (
        "max_duration_ms",
        "cpu_time_ms",
        "peak_ram_mb",
        "disk_io_bytes",
        "max_retries",
        "llm_calls",
        "gpu_memory_mb",
    ):
        value = getattr(measured, field_name)
        if value is None:
            blockers.append("RESOURCE_" + field_name.upper() + "_UNMEASURED")
        elif value > getattr(limits, field_name):
            blockers.append("RESOURCE_" + field_name.upper() + "_EXCEEDED")
    return tuple(blockers)


def _process_resource_snapshot() -> tuple[float | None, int | None]:
    """Read available OS counters; unsupported counters remain unknown."""
    try:
        if os.name == "nt":
            return _windows_resource_snapshot()
        resource = cast(Any, importlib.import_module("resource"))
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        values = dict(
            line.split(":", 1)
            for line in Path("/proc/self/io").read_text(encoding="ascii").splitlines()
        )
        return peak, int(values["read_bytes"]) + int(values["write_bytes"])
    except OSError, ValueError, KeyError, AttributeError:
        return None, None


def _windows_resource_snapshot() -> tuple[float | None, int | None]:
    from ctypes import wintypes

    class MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("faults", wintypes.DWORD),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("quota_peak_paged", ctypes.c_size_t),
            ("quota_paged", ctypes.c_size_t),
            ("quota_peak_nonpaged", ctypes.c_size_t),
            ("quota_nonpaged", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t),
            ("peak_pagefile", ctypes.c_size_t),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "read_operations",
                "write_operations",
                "other_operations",
                "read_bytes",
                "write_bytes",
                "other_bytes",
            )
        ]

    kernel = cast(Any, ctypes.WinDLL("kernel32", use_last_error=True))
    process = kernel.GetCurrentProcess
    process.restype = wintypes.HANDLE
    handle = process()
    memory_api = cast(
        Any, ctypes.WinDLL("psapi", use_last_error=True)
    ).GetProcessMemoryInfo
    memory_api.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(MemoryCounters),
        wintypes.DWORD,
    ]
    memory_api.restype = wintypes.BOOL
    memory = MemoryCounters()
    memory.cb = ctypes.sizeof(memory)
    peak = (
        memory.peak_working_set / (1024**2)
        if memory_api(handle, ctypes.byref(memory), memory.cb)
        else None
    )
    io_api = kernel.GetProcessIoCounters
    io_api.argtypes = [wintypes.HANDLE, ctypes.POINTER(IoCounters)]
    io_api.restype = wintypes.BOOL
    io = IoCounters()
    transfer = (
        int(io.read_bytes + io.write_bytes)
        if io_api(handle, ctypes.byref(io))
        else None
    )
    return peak, transfer


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

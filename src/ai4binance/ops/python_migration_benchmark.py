"""Produce fail-closed, host-bound Python migration benchmark evidence."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import shutil

# Subprocess execution is restricted to fixed shell-free benchmark argv.
import subprocess  # nosec B404
import sys
import sysconfig
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from ai4binance.events import DeterministicEventBus, DomainEvent
from ai4binance.execution.order_state import OrderStateMachine
from ai4binance.governance import (
    DecisionGovernanceEngine,
    DgeGovernanceContext,
    DgeMarketAction,
    DgeTradeCandidate,
)
from ai4binance.ops.performance import (
    BenchmarkMeasurement,
    PerformanceRegressionPolicy,
    compare_performance,
    measure_operation,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified

_SCHEMA_VERSION = "python-migration-performance-evidence:v1"
_STABILITY_SCHEMA_VERSION = "python-migration-stability-evidence:v1"
_LATEST_VERIFICATION_SCHEMA_VERSION = "python-migration-latest-verification:v1"
_CANONICAL_VERSION = "3.14.7"
_CANONICAL_SOABI = "cp314-win_amd64"
_CANONICAL_MAX_REGRESSION_PERCENT = 10.0
_CANONICAL_CLOCK_SOURCE = "process_time_ns"
# Keep each replay sample well above the Windows process CPU-time accounting quantum.
_DEFAULT_REPLAY_ITERATIONS = 200_000
_PAIRED_REPETITIONS = 21
_PAIRED_AFFINITY_CPU = 0
_PAIRED_ORCHESTRATION_SCHEMA_VERSION = "python-migration-paired-run:v1"
_MEASUREMENT_HOST_LOAD_SCHEMA_VERSION = "measurement-host-load-attestation:v1"
_MEASUREMENT_MAX_ATTEMPTS = 3
_MEASUREMENT_TIMEOUT_SECONDS = 600.0
_MAX_HOST_LOAD_PERCENT = 25.0
_QUIESCENCE_MAX_HOST_LOAD_PERCENT = 20.0
_QUIESCENCE_ATTEMPTS = 120
_QUIESCENCE_REQUIRED_CONSECUTIVE_SAMPLES = 12
_QUIESCENCE_PROBE_SECONDS = 0.5
_QUIESCENCE_WAIT_SECONDS = 0.5
_MEASUREMENT_REQUIRED_CONSECUTIVE_BUSY_SAMPLES = 2
_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102


def _process_clock_ns() -> int:
    return time.process_time_ns()


class _FileTime(ctypes.Structure):
    _fields_ = (("low", ctypes.c_uint32), ("high", ctypes.c_uint32))


def _filetime_ticks(value: _FileTime) -> int:
    return (int(value.high) << 32) | int(value.low)


def _windows_system_cpu_times() -> tuple[int, int, int]:
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        raise OSError("HOST_LOAD_PROBE_UNAVAILABLE")
    kernel32 = win_dll("kernel32", use_last_error=True)
    idle = _FileTime()
    kernel = _FileTime()
    user = _FileTime()
    if not kernel32.GetSystemTimes(
        ctypes.byref(idle),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise OSError("HOST_LOAD_PROBE_FAILED")
    return _filetime_ticks(idle), _filetime_ticks(kernel), _filetime_ticks(user)


def _cpu_load_percent_between(
    before: tuple[int, int, int],
    after: tuple[int, int, int],
) -> float:
    idle_delta = after[0] - before[0]
    kernel_delta = after[1] - before[1]
    user_delta = after[2] - before[2]
    total_delta = kernel_delta + user_delta
    busy_delta = total_delta - idle_delta
    if total_delta <= 0 or busy_delta < 0:
        raise ValueError("HOST_LOAD_SAMPLE_INVALID")
    return min(100.0, max(0.0, busy_delta / total_delta * 100.0))


def _host_cpu_load_percent(*, probe_seconds: float) -> float:
    if platform.system() != "Windows":
        raise OSError("HOST_LOAD_PROBE_UNSUPPORTED_PLATFORM")
    before = _windows_system_cpu_times()
    time.sleep(probe_seconds)
    after = _windows_system_cpu_times()
    return _cpu_load_percent_between(before, after)


def _quality_gate_mutex_name(repository_root: Path) -> str:
    normalized_root = str(repository_root.resolve()).lower().encode("utf-8")
    suffix = hashlib.sha256(normalized_root).hexdigest().upper()
    return f"Local\\AI4BinanceQualityGate-{suffix}"


def _try_acquire_quality_gate_mutex(
    repository_root: Path,
) -> tuple[int | None, str | None]:
    """Acquire the repository quality mutex without waiting."""
    win_dll = getattr(ctypes, "WinDLL", None)
    if platform.system() != "Windows" or win_dll is None:
        return None, "QUALITY_GATE_MUTEX_UNAVAILABLE"

    kernel32 = win_dll("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    create_mutex.restype = ctypes.c_void_p
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    wait_for_single_object.restype = ctypes.c_uint32
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_bool

    handle = create_mutex(None, False, _quality_gate_mutex_name(repository_root))
    if not handle:
        return None, "QUALITY_GATE_MUTEX_UNAVAILABLE"
    wait_result = int(wait_for_single_object(handle, 0))
    if wait_result in {_WAIT_OBJECT_0, _WAIT_ABANDONED}:
        return int(handle), None
    close_handle(handle)
    if wait_result == _WAIT_TIMEOUT:
        return None, "QUALITY_GATE_ALREADY_RUNNING"
    return None, "QUALITY_GATE_MUTEX_UNAVAILABLE"


def _release_quality_gate_mutex(handle: int | None) -> None:
    if handle is None:
        return
    win_dll = getattr(ctypes, "WinDLL", None)
    if platform.system() != "Windows" or win_dll is None:
        return
    kernel32 = win_dll("kernel32", use_last_error=True)
    release_mutex = kernel32.ReleaseMutex
    release_mutex.argtypes = (ctypes.c_void_p,)
    release_mutex.restype = ctypes.c_bool
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_bool
    try:
        release_mutex(handle)
    finally:
        close_handle(handle)


def _set_process_affinity(cpu_index: int) -> dict[str, int]:
    """Pin this benchmark process to one allowed Windows logical processor."""
    if not 0 <= cpu_index < ctypes.sizeof(ctypes.c_size_t) * 8:
        raise ValueError("PROCESS_AFFINITY_CPU_INVALID")
    win_dll = getattr(ctypes, "WinDLL", None)
    if platform.system() != "Windows" or win_dll is None:
        raise OSError("PROCESS_AFFINITY_UNSUPPORTED_PLATFORM")

    kernel32 = win_dll("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_affinity_mask = kernel32.GetProcessAffinityMask
    get_process_affinity_mask.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    )
    get_process_affinity_mask.restype = ctypes.c_bool
    set_process_affinity_mask = kernel32.SetProcessAffinityMask
    set_process_affinity_mask.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    set_process_affinity_mask.restype = ctypes.c_bool

    process = get_current_process()
    process_mask = ctypes.c_size_t()
    system_mask = ctypes.c_size_t()
    if not get_process_affinity_mask(
        process,
        ctypes.byref(process_mask),
        ctypes.byref(system_mask),
    ):
        raise OSError(ctypes.get_last_error(), "PROCESS_AFFINITY_QUERY_FAILED")

    affinity_mask = 1 << cpu_index
    if process_mask.value & affinity_mask == 0:
        raise ValueError("PROCESS_AFFINITY_CPU_NOT_ALLOWED")
    if not set_process_affinity_mask(process, affinity_mask):
        raise OSError(ctypes.get_last_error(), "PROCESS_AFFINITY_SET_FAILED")
    return {"cpu_index": cpu_index, "mask": affinity_mask}


def _await_host_quiescence(
    *,
    sampler: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[bool, tuple[float, ...], str | None]:
    sample = sampler or (
        lambda: _host_cpu_load_percent(probe_seconds=_QUIESCENCE_PROBE_SECONDS)
    )
    samples: list[float] = []
    consecutive = 0
    for attempt in range(_QUIESCENCE_ATTEMPTS):
        try:
            load_percent = float(sample())
        except (OSError, ValueError):
            return False, tuple(samples), "HOST_LOAD_UNAVAILABLE"
        if not 0.0 <= load_percent <= 100.0:
            return False, tuple(samples), "HOST_LOAD_SAMPLE_INVALID"
        samples.append(load_percent)
        consecutive = (
            consecutive + 1 if load_percent <= _QUIESCENCE_MAX_HOST_LOAD_PERCENT else 0
        )
        if consecutive >= _QUIESCENCE_REQUIRED_CONSECUTIVE_SAMPLES:
            return True, tuple(samples), None
        if attempt + 1 < _QUIESCENCE_ATTEMPTS:
            sleeper(_QUIESCENCE_WAIT_SECONDS)
    return False, tuple(samples), "HOST_NOT_QUIESCENT"


def _measurement_host_load_limits() -> tuple[int, float, float]:
    logical_processor_count = os.cpu_count()
    if logical_processor_count is None or logical_processor_count < 1:
        raise OSError("HOST_LOGICAL_PROCESSOR_COUNT_UNAVAILABLE")
    benchmark_cpu_budget_percent = 100.0 / logical_processor_count
    max_percent = min(
        100.0,
        _MAX_HOST_LOAD_PERCENT + benchmark_cpu_budget_percent,
    )
    return logical_processor_count, benchmark_cpu_budget_percent, max_percent


def _semantic_sha256(value: object) -> str:
    payload = json.dumps(
        to_primitive(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _runtime_payload() -> dict[str, object]:
    gil_probe = getattr(sys, "_is_gil_enabled", None)
    jit = getattr(sys, "_jit", None)
    return {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "machine": platform.machine().casefold(),
        "soabi": sysconfig.get_config_var("SOABI"),
        "py_gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
        "gil_enabled": gil_probe() if callable(gil_probe) else None,
        "jit_available": jit is not None,
        "jit_enabled": bool(jit is not None and jit.is_enabled()),
    }


def _driver_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _candidate() -> DgeTradeCandidate:
    return DgeTradeCandidate(
        candidate_id="candidate:python-migration-benchmark",
        symbol="BTCUSDT",
        market="SPOT",
        requested_action=DgeMarketAction.BUY,
        setup_name="support_reclaim",
        score=Decimal("72"),
        confidence=Decimal("0.70"),
        risk_reward=Decimal("2.4"),
        capital_source="CURRENT_CAPITAL_REVIEW",
        primary_timeframe="1h",
        mtf_bias="BULLISH",
        regime="RANGE",
        evidence_refs=("benchmark:candidate:1", "benchmark:candidate:2"),
    )


def _context() -> DgeGovernanceContext:
    return DgeGovernanceContext(
        context_id="context:python-migration-benchmark",
        data_snapshot_id="snapshot:python-migration-benchmark",
        semantic_graph_id="semantic:python-migration-benchmark",
        position_context_ref="position:python-migration-benchmark",
        wallet_verified=True,
        oos_approved=False,
        risk_approved=False,
        execution_feasible=False,
        human_approval_recorded=False,
        config_hash="config:sha256:python-migration-benchmark",
        evidence_refs=("benchmark:context:1", "benchmark:context:2"),
    )


def _event(
    *,
    event_id: str,
    sequence: int,
    event_type: str,
    payload: tuple[tuple[str, str], ...] = (),
    previous_hash: str = "GENESIS",
) -> DomainEvent:
    return DomainEvent.create(
        event_id=event_id,
        aggregate_id="paper-order:python-migration-benchmark",
        event_type=event_type,
        sequence=sequence,
        occurred_at=datetime.fromisoformat(f"2026-09-06T00:00:0{sequence}+00:00"),
        payload=payload,
        previous_hash=previous_hash,
    )


def _events() -> tuple[DomainEvent, ...]:
    submitted = _event(
        event_id="benchmark-event-1",
        sequence=1,
        event_type="ORDER_SUBMITTED",
        payload=(("action", "BUY"), ("quantity", "2"), ("symbol", "BTCUSDT")),
    )
    accepted = _event(
        event_id="benchmark-event-2",
        sequence=2,
        event_type="ORDER_ACCEPTED",
        previous_hash=submitted.event_hash,
    )
    filled = _event(
        event_id="benchmark-event-3",
        sequence=3,
        event_type="ORDER_FILLED",
        payload=(("fill_price", "101"), ("fill_quantity", "2")),
        previous_hash=accepted.event_hash,
    )
    return submitted, accepted, filled


def _measure(
    *,
    environment_id: str,
    code_revision: str,
    decision_iterations: int,
    replay_iterations: int,
    repetitions: int,
    process_affinity: dict[str, int] | None = None,
) -> dict[str, object]:
    engine = DecisionGovernanceEngine()
    candidate = _candidate()
    context = _context()
    events = _events()

    def evaluate_decision() -> object:
        return engine.evaluate(candidate, context)

    def replay_events() -> object:
        bus = DeterministicEventBus()
        bus.replay(events)
        return OrderStateMachine.replay(bus.snapshot())

    decision_before = evaluate_decision()
    replay_before = replay_events()
    measurements = (
        measure_operation(
            benchmark_name="decision-governance-evaluate",
            operation=evaluate_decision,
            environment_id=environment_id,
            code_revision=code_revision,
            iterations=decision_iterations,
            repetitions=repetitions,
            clock=_process_clock_ns,
        ),
        measure_operation(
            benchmark_name="event-replay-order-state",
            operation=replay_events,
            environment_id=environment_id,
            code_revision=code_revision,
            iterations=replay_iterations,
            repetitions=repetitions,
            clock=_process_clock_ns,
        ),
    )
    semantic_hashes = {
        "decision-governance-evaluate": _semantic_sha256(decision_before),
        "event-replay-order-state": _semantic_sha256(replay_before),
    }
    if (
        _semantic_sha256(evaluate_decision())
        != semantic_hashes["decision-governance-evaluate"]
    ):
        raise RuntimeError("DETERMINISM_REGRESSION: decision-governance-evaluate")
    if _semantic_sha256(replay_events()) != semantic_hashes["event-replay-order-state"]:
        raise RuntimeError("REPLAY_REGRESSION: event-replay-order-state")
    return {
        "schema_version": _SCHEMA_VERSION,
        "artifact_origin": "python_migration_benchmark_measurement",
        "environment_id": environment_id,
        "code_revision": code_revision,
        "benchmark_driver_sha256": _driver_sha256(),
        "clock_source": _CANONICAL_CLOCK_SOURCE,
        "process_affinity": process_affinity,
        "runtime": _runtime_payload(),
        "benchmarks": [
            {
                "measurement": to_primitive(measurement),
                "semantic_sha256": semantic_hashes[measurement.benchmark_name],
            }
            for measurement in measurements
        ],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _measurement(payload: dict[str, Any]) -> BenchmarkMeasurement:
    raw = cast(dict[str, Any], payload["measurement"])
    return BenchmarkMeasurement(
        benchmark_name=str(raw["benchmark_name"]),
        environment_id=str(raw["environment_id"]),
        code_revision=str(raw["code_revision"]),
        measured_at=datetime.fromisoformat(str(raw["measured_at"])),
        iterations=int(raw["iterations"]),
        samples_ns_per_operation=tuple(
            float(value) for value in raw["samples_ns_per_operation"]
        ),
    )


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _SCHEMA_VERSION
    ):
        raise ValueError("PYTHON_MIGRATION_BENCHMARK_SCHEMA_INVALID")
    return cast(dict[str, Any], payload)


def _measurement_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_rows = payload.get("benchmarks")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("PAIRED_BENCHMARK_AGGREGATION_BENCHMARK_SET_INVALID")
    rows: dict[str, dict[str, Any]] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("PAIRED_BENCHMARK_AGGREGATION_BENCHMARK_SET_INVALID")
        row = cast(dict[str, Any], raw_row)
        measurement = _measurement(row)
        if measurement.benchmark_name in rows:
            raise ValueError("PAIRED_BENCHMARK_AGGREGATION_BENCHMARK_DUPLICATE")
        rows[measurement.benchmark_name] = row
    return rows


def _measurement_host_load_attestation(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("MEASUREMENT_HOST_LOAD_ATTESTATION_INVALID")
    attestation = cast(dict[str, Any], payload)
    raw_samples = attestation.get("samples_percent")
    logical_processor_count = attestation.get("logical_processor_count")
    if (
        not isinstance(logical_processor_count, int)
        or isinstance(logical_processor_count, bool)
        or logical_processor_count < 1
    ):
        raise ValueError("MEASUREMENT_HOST_LOAD_ATTESTATION_INVALID")
    benchmark_cpu_budget_percent = 100.0 / logical_processor_count
    max_percent = min(
        100.0,
        _MAX_HOST_LOAD_PERCENT + benchmark_cpu_budget_percent,
    )
    if (
        attestation.get("schema_version") != _MEASUREMENT_HOST_LOAD_SCHEMA_VERSION
        or attestation.get("status") != "PASS"
        or attestation.get("blockers") != []
        or attestation.get("external_load_budget_percent") != _MAX_HOST_LOAD_PERCENT
        or attestation.get("benchmark_cpu_budget_percent")
        != benchmark_cpu_budget_percent
        or attestation.get("max_percent") != max_percent
        or attestation.get("required_consecutive_busy_samples")
        != _MEASUREMENT_REQUIRED_CONSECUTIVE_BUSY_SAMPLES
        or not isinstance(raw_samples, list)
        or not raw_samples
        or attestation.get("sample_count") != len(raw_samples)
    ):
        raise ValueError("MEASUREMENT_HOST_LOAD_ATTESTATION_INVALID")
    consecutive_busy = 0
    for raw_sample in raw_samples:
        if (
            not isinstance(raw_sample, (int, float))
            or isinstance(raw_sample, bool)
            or not 0.0 <= float(raw_sample) <= 100.0
        ):
            raise ValueError("MEASUREMENT_HOST_LOAD_ATTESTATION_INVALID")
        consecutive_busy = (
            consecutive_busy + 1 if float(raw_sample) > max_percent else 0
        )
        if consecutive_busy >= _MEASUREMENT_REQUIRED_CONSECUTIVE_BUSY_SAMPLES:
            raise ValueError("MEASUREMENT_HOST_LOAD_ATTESTATION_INVALID")
    return attestation


def _aggregate_abba_measurements(
    payloads: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, object]:
    """Pool equal-runtime AB/BA samples without weakening comparison policy."""
    first, second = payloads
    invariant_fields = (
        "schema_version",
        "environment_id",
        "code_revision",
        "benchmark_driver_sha256",
        "clock_source",
        "process_affinity",
        "runtime",
        "execution_allowed",
        "promotion_status",
        "live_eligibility_status",
    )
    for field in invariant_fields:
        if first.get(field) != second.get(field):
            raise ValueError(f"PAIRED_BENCHMARK_AGGREGATION_METADATA_MISMATCH:{field}")

    source_sha256s = [_semantic_sha256(payload) for payload in payloads]
    if len(set(source_sha256s)) != len(source_sha256s):
        raise ValueError("PAIRED_BENCHMARK_AGGREGATION_SOURCE_DUPLICATE")
    host_load_attestations = [
        _measurement_host_load_attestation(payload.get("host_load_attestation"))
        for payload in payloads
    ]

    rows_by_source = tuple(_measurement_rows(payload) for payload in payloads)
    benchmark_names = set(rows_by_source[0])
    if benchmark_names != set(rows_by_source[1]):
        raise ValueError("PAIRED_BENCHMARK_AGGREGATION_BENCHMARK_SET_MISMATCH")

    benchmarks: list[dict[str, object]] = []
    for name in sorted(benchmark_names):
        source_rows = tuple(rows[name] for rows in rows_by_source)
        source_measurements = tuple(_measurement(row) for row in source_rows)
        anchor = source_measurements[0]
        if any(
            (
                measurement.environment_id != anchor.environment_id
                or measurement.code_revision != anchor.code_revision
                or measurement.iterations != anchor.iterations
                or measurement.schema_version != anchor.schema_version
                or measurement.execution_allowed != anchor.execution_allowed
            )
            for measurement in source_measurements[1:]
        ):
            raise ValueError(
                f"PAIRED_BENCHMARK_AGGREGATION_MEASUREMENT_MISMATCH:{name}"
            )
        semantic_hashes = {str(row.get("semantic_sha256", "")) for row in source_rows}
        if len(semantic_hashes) != 1 or "" in semantic_hashes:
            raise ValueError(f"PAIRED_BENCHMARK_AGGREGATION_SEMANTIC_MISMATCH:{name}")
        aggregate = BenchmarkMeasurement(
            benchmark_name=name,
            environment_id=anchor.environment_id,
            code_revision=anchor.code_revision,
            measured_at=max(
                measurement.measured_at for measurement in source_measurements
            ),
            iterations=anchor.iterations,
            samples_ns_per_operation=tuple(
                sample
                for measurement in source_measurements
                for sample in measurement.samples_ns_per_operation
            ),
        )
        benchmarks.append(
            {
                "measurement": cast(dict[str, object], to_primitive(aggregate)),
                "semantic_sha256": next(iter(semantic_hashes)),
            }
        )

    return {
        "schema_version": _SCHEMA_VERSION,
        "artifact_origin": "python_migration_benchmark_abba_aggregate",
        "environment_id": first.get("environment_id"),
        "code_revision": first.get("code_revision"),
        "benchmark_driver_sha256": first.get("benchmark_driver_sha256"),
        "clock_source": first.get("clock_source"),
        "process_affinity": first.get("process_affinity"),
        "runtime": first.get("runtime"),
        "source_measurement_evidence_sha256s": source_sha256s,
        "source_host_load_attestations": host_load_attestations,
        "aggregation": {
            "method": "ABBA_ORDER_BALANCED_SAMPLE_POOL",
            "source_count": len(payloads),
        },
        "benchmarks": benchmarks,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _load_stability_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _STABILITY_SCHEMA_VERSION
    ):
        raise ValueError("PYTHON_MIGRATION_STABILITY_SCHEMA_INVALID")
    return cast(dict[str, Any], payload)


def _current_runtime_blockers(
    runtime: dict[str, Any], expected_version: str
) -> list[str]:
    blockers: list[str] = []
    if runtime.get("implementation") != "CPython":
        blockers.append("CANONICAL_RUNTIME_IMPLEMENTATION_MISMATCH")
    if runtime.get("version") != expected_version:
        blockers.append("CANONICAL_RUNTIME_VERSION_MISMATCH")
    if runtime.get("machine") not in {"amd64", "x86_64"}:
        blockers.append("CANONICAL_RUNTIME_ARCHITECTURE_MISMATCH")
    if runtime.get("gil_enabled") is not True:
        blockers.append("CANONICAL_RUNTIME_STANDARD_GIL_REQUIRED")
    if runtime.get("py_gil_disabled") != 0:
        blockers.append("CANONICAL_RUNTIME_FREE_THREADED_FORBIDDEN")
    if runtime.get("soabi") != _CANONICAL_SOABI:
        blockers.append("CANONICAL_RUNTIME_SOABI_MISMATCH")
    if runtime.get("jit_enabled") is not False:
        blockers.append("CANONICAL_RUNTIME_EXPERIMENTAL_JIT_FORBIDDEN")
    return blockers


def _compare(
    *,
    baseline: dict[str, Any],
    current: dict[str, Any],
    baseline_version: str,
    current_version: str,
    max_regression_percent: float,
) -> dict[str, object]:
    blockers: list[str] = []
    baseline_evidence_sha256 = _semantic_sha256(baseline)
    current_evidence_sha256 = _semantic_sha256(current)
    baseline_runtime = cast(dict[str, Any], baseline.get("runtime", {}))
    current_runtime = cast(dict[str, Any], current.get("runtime", {}))
    if baseline_runtime.get("version") != baseline_version:
        blockers.append("BASELINE_RUNTIME_VERSION_MISMATCH")
    blockers.extend(_current_runtime_blockers(current_runtime, current_version))
    if baseline.get("code_revision") != current.get("code_revision"):
        blockers.append("BENCHMARK_CODE_REVISION_MISMATCH")
    if baseline.get("benchmark_driver_sha256") != current.get(
        "benchmark_driver_sha256"
    ):
        blockers.append("BENCHMARK_DRIVER_MISMATCH")
    if baseline.get("process_affinity") != current.get("process_affinity"):
        blockers.append("BENCHMARK_PROCESS_AFFINITY_MISMATCH")
    if (
        baseline.get("clock_source") != _CANONICAL_CLOCK_SOURCE
        or current.get("clock_source") != _CANONICAL_CLOCK_SOURCE
    ):
        blockers.append("BENCHMARK_CLOCK_SOURCE_MISMATCH")

    baseline_rows = {
        str(row["measurement"]["benchmark_name"]): row
        for row in cast(list[dict[str, Any]], baseline.get("benchmarks", []))
    }
    current_rows = {
        str(row["measurement"]["benchmark_name"]): row
        for row in cast(list[dict[str, Any]], current.get("benchmarks", []))
    }
    if set(baseline_rows) != set(current_rows):
        blockers.append("BENCHMARK_SET_MISMATCH")

    comparisons: list[dict[str, object]] = []
    policy = PerformanceRegressionPolicy(
        max_regression_percent=max_regression_percent,
        minimum_samples=5,
    )
    for name in sorted(set(baseline_rows) & set(current_rows)):
        baseline_measurement = _measurement(baseline_rows[name])
        current_measurement = _measurement(current_rows[name])
        comparison = compare_performance(
            baseline_measurement,
            current_measurement,
            policy,
        )
        row_blockers = list(comparison.blockers)
        if baseline_measurement.iterations != current_measurement.iterations:
            row_blockers.append("BENCHMARK_ITERATION_MISMATCH")
        if baseline_rows[name].get("semantic_sha256") != current_rows[name].get(
            "semantic_sha256"
        ):
            row_blockers.append("DETERMINISM_REGRESSION")
        blockers.extend(f"{name}:{blocker}" for blocker in row_blockers)
        comparison_payload = cast(dict[str, object], to_primitive(comparison))
        comparison_payload["passed"] = not row_blockers
        comparison_payload["blockers"] = row_blockers
        comparison_payload["baseline_semantic_sha256"] = baseline_rows[name].get(
            "semantic_sha256"
        )
        comparison_payload["current_semantic_sha256"] = current_rows[name].get(
            "semantic_sha256"
        )
        comparisons.append(comparison_payload)

    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "schema_version": _SCHEMA_VERSION,
        "artifact_origin": "python_migration_benchmark_comparison",
        "baseline_evidence_sha256": baseline_evidence_sha256,
        "current_evidence_sha256": current_evidence_sha256,
        "baseline_runtime": baseline_runtime,
        "current_runtime": current_runtime,
        "code_revision": current.get("code_revision"),
        "benchmark_driver_sha256": current.get("benchmark_driver_sha256"),
        "clock_source": current.get("clock_source"),
        "max_regression_percent": max_regression_percent,
        "comparisons": comparisons,
        "status": "PASS" if not unique_blockers else "BLOCKED",
        "blockers": unique_blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _comparison_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("comparisons")
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            return {}
        row = cast(dict[str, Any], raw)
        name = row.get("benchmark_name")
        if not isinstance(name, str) or not name or name in result:
            return {}
        result[name] = row
    return result


def _diagnose_stability(
    comparisons: list[dict[str, Any]],
) -> dict[str, object]:
    if not 2 <= len(comparisons) <= 20:
        raise ValueError("benchmark stability requires between 2 and 20 comparisons")

    blockers: list[str] = []
    comparison_sha256s = [_semantic_sha256(item) for item in comparisons]
    evidence_bindings: list[dict[str, str]] = []
    binding_invalid = False
    for item in comparisons:
        baseline_sha256 = item.get("baseline_evidence_sha256")
        current_sha256 = item.get("current_evidence_sha256")
        if not (
            isinstance(baseline_sha256, str)
            and len(baseline_sha256) == 64
            and all(character in "0123456789abcdef" for character in baseline_sha256)
            and isinstance(current_sha256, str)
            and len(current_sha256) == 64
            and all(character in "0123456789abcdef" for character in current_sha256)
        ):
            binding_invalid = True
            continue
        evidence_bindings.append(
            {
                "baseline_evidence_sha256": baseline_sha256,
                "current_evidence_sha256": current_sha256,
            }
        )
    if binding_invalid or len(evidence_bindings) != len(comparisons):
        blockers.append("BENCHMARK_MEASUREMENT_EVIDENCE_BINDING_INVALID")
    binding_pairs = {
        (
            binding["baseline_evidence_sha256"],
            binding["current_evidence_sha256"],
        )
        for binding in evidence_bindings
    }
    if len(set(comparison_sha256s)) != len(comparison_sha256s) or len(
        binding_pairs
    ) != len(evidence_bindings):
        blockers.append("BENCHMARK_STABILITY_INPUT_DUPLICATE")
    revisions = {str(item.get("code_revision", "")) for item in comparisons}
    driver_hashes = {
        str(item.get("benchmark_driver_sha256", "")) for item in comparisons
    }
    if len(revisions) != 1 or "" in revisions:
        blockers.append("BENCHMARK_CODE_REVISION_MISMATCH")
    if len(driver_hashes) != 1 or "" in driver_hashes:
        blockers.append("BENCHMARK_DRIVER_MISMATCH")
    clock_sources = {str(item.get("clock_source", "")) for item in comparisons}
    if clock_sources != {_CANONICAL_CLOCK_SOURCE}:
        blockers.append("BENCHMARK_CLOCK_SOURCE_MISMATCH")
    thresholds = {
        float(value)
        for item in comparisons
        if isinstance((value := item.get("max_regression_percent")), (int, float))
        and not isinstance(value, bool)
    }
    if thresholds != {_CANONICAL_MAX_REGRESSION_PERCENT}:
        blockers.append("BENCHMARK_POLICY_MISMATCH")

    rows_by_run = [_comparison_rows(item) for item in comparisons]
    benchmark_sets = [set(rows) for rows in rows_by_run]
    if any(not names for names in benchmark_sets) or any(
        names != benchmark_sets[0] for names in benchmark_sets[1:]
    ):
        blockers.append("BENCHMARK_SET_MISMATCH")

    for index, item in enumerate(comparisons, start=1):
        if item.get("status") != "PASS" or item.get("blockers") != []:
            blockers.append(f"INPUT_COMPARISON_NOT_PASSING:{index}")

    diagnostics: list[dict[str, object]] = []
    common_names = set.intersection(*benchmark_sets) if benchmark_sets else set()
    for name in sorted(common_names):
        rows = [run[name] for run in rows_by_run]
        outcomes = [row.get("passed") is True for row in rows]
        regressions = [
            float(value)
            for row in rows
            if isinstance((value := row.get("regression_percent")), (int, float))
            and not isinstance(value, bool)
        ]
        semantic_pairs = {
            (
                str(row.get("baseline_semantic_sha256", "")),
                str(row.get("current_semantic_sha256", "")),
            )
            for row in rows
        }
        environments = {str(row.get("environment_id", "")) for row in rows}
        if len(set(outcomes)) != 1:
            blockers.append(f"BENCHMARK_OUTCOME_UNSTABLE:{name}")
        if len(environments) != 1 or "" in environments:
            blockers.append(f"BENCHMARK_ENVIRONMENT_MISMATCH:{name}")
        if len(semantic_pairs) != 1 or any(
            not baseline or not current for baseline, current in semantic_pairs
        ):
            blockers.append(f"BENCHMARK_SEMANTIC_IDENTITY_MISMATCH:{name}")
        diagnostics.append(
            {
                "benchmark_name": name,
                "outcomes": outcomes,
                "regression_percentages": regressions,
                "regression_spread_percent": (
                    max(regressions) - min(regressions)
                    if len(regressions) == len(comparisons)
                    else None
                ),
                "stable_outcome": len(set(outcomes)) == 1,
            }
        )

    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "schema_version": _STABILITY_SCHEMA_VERSION,
        "artifact_origin": "python_migration_benchmark_stability_diagnosis",
        "comparison_count": len(comparisons),
        "code_revision": next(iter(revisions)) if len(revisions) == 1 else None,
        "benchmark_driver_sha256": (
            next(iter(driver_hashes)) if len(driver_hashes) == 1 else None
        ),
        "clock_source": (
            next(iter(clock_sources)) if len(clock_sources) == 1 else None
        ),
        "max_regression_percent": (
            next(iter(thresholds)) if len(thresholds) == 1 else None
        ),
        "comparison_sha256s": comparison_sha256s,
        "measurement_evidence_bindings": evidence_bindings,
        "diagnostics": diagnostics,
        "status": "PASS" if not unique_blockers else "BLOCKED",
        "blockers": unique_blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _blocked_stability_payload(
    *,
    comparisons: list[dict[str, Any]],
    code_revision: str,
    driver_sha256: str,
    blockers: list[str],
) -> dict[str, object]:
    stability_blockers = ["BENCHMARK_STABILITY_INSUFFICIENT_COMPARISONS", *blockers]
    return {
        "schema_version": _STABILITY_SCHEMA_VERSION,
        "artifact_origin": "python_migration_benchmark_stability_diagnosis",
        "comparison_count": len(comparisons),
        "code_revision": code_revision,
        "benchmark_driver_sha256": driver_sha256,
        "clock_source": _CANONICAL_CLOCK_SOURCE,
        "max_regression_percent": _CANONICAL_MAX_REGRESSION_PERCENT,
        "comparison_sha256s": [_semantic_sha256(item) for item in comparisons],
        "measurement_evidence_bindings": [],
        "diagnostics": [],
        "status": "BLOCKED",
        "blockers": list(dict.fromkeys(stability_blockers)),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _bind_stability_to_latest(
    comparison: dict[str, Any],
    stability: dict[str, object],
) -> dict[str, object]:
    payload = cast(dict[str, object], dict(comparison))
    stability_binding = {
        "schema_version": stability.get("schema_version"),
        "status": stability.get("status"),
        "blockers": stability.get("blockers"),
        "comparison_count": stability.get("comparison_count"),
        "code_revision": stability.get("code_revision"),
        "benchmark_driver_sha256": stability.get("benchmark_driver_sha256"),
        "clock_source": stability.get("clock_source"),
        "max_regression_percent": stability.get("max_regression_percent"),
    }
    payload["stability_evidence"] = stability_binding
    if stability.get("status") != "PASS":
        raw_blockers = comparison.get("blockers")
        blockers = list(raw_blockers) if isinstance(raw_blockers, list) else []
        stability_blockers = stability.get("blockers")
        if isinstance(stability_blockers, list):
            blockers.extend(f"stability:{item}" for item in stability_blockers)
        payload["status"] = "BLOCKED"
        payload["blockers"] = list(dict.fromkeys(blockers))
    payload["execution_allowed"] = False
    payload["promotion_status"] = "RESEARCH_ONLY"
    payload["live_eligibility_status"] = "LIVE_ORDER_BLOCKED"
    return payload


def _git_output(
    repository_root: Path, *arguments: str
) -> tuple[str | None, str | None]:
    git = shutil.which("git")
    if git is None:
        return None, "LATEST_EVIDENCE_GIT_UNAVAILABLE"
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [git, "-C", str(repository_root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "LATEST_EVIDENCE_REPOSITORY_STATE_UNAVAILABLE"
    if completed.returncode != 0:
        return None, "LATEST_EVIDENCE_REPOSITORY_STATE_UNAVAILABLE"
    return completed.stdout.strip(), None


def _repository_state(
    repository_root: Path,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    resolved = repository_root.resolve()
    blockers: list[str] = []
    top_level, error = _git_output(resolved, "rev-parse", "--show-toplevel")
    if error is not None:
        return "UNKNOWN", (), (error,)
    if top_level is None or Path(top_level).resolve() != resolved:
        blockers.append("LATEST_EVIDENCE_REPOSITORY_ROOT_MISMATCH")

    revision, error = _git_output(resolved, "rev-parse", "HEAD")
    if error is not None or not revision:
        blockers.append(error or "LATEST_EVIDENCE_REPOSITORY_STATE_UNAVAILABLE")
        revision = "UNKNOWN"

    status, error = _git_output(
        resolved,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    changed: tuple[str, ...]
    if error is not None:
        blockers.append(error)
        changed = ()
    else:
        changed = tuple(line for line in (status or "").splitlines() if line)
    return revision, changed, tuple(dict.fromkeys(blockers))


def _verify_latest_payload(
    latest: dict[str, Any],
    *,
    stability: dict[str, Any],
    current_code_revision: str,
    current_driver_sha256: str,
    changed_paths: tuple[str, ...],
    repository_blockers: tuple[str, ...] = (),
) -> dict[str, object]:
    blockers = list(repository_blockers)
    rows = _comparison_rows(latest)
    latest_status = latest.get("status")
    latest_blockers = latest.get("blockers")
    if latest_status != "PASS":
        blockers.append("LATEST_EVIDENCE_NOT_PASSING")
    if latest_status == "PASS" and (
        latest_blockers != []
        or not rows
        or any(row.get("passed") is not True for row in rows.values())
    ):
        blockers.append("LATEST_EVIDENCE_CONTRACT_INVALID")
    if (
        latest.get("execution_allowed") is not False
        or latest.get("promotion_status") != "RESEARCH_ONLY"
        or latest.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        blockers.append("LATEST_EVIDENCE_SAFETY_STATE_INVALID")
    if latest.get("code_revision") != current_code_revision:
        blockers.append("LATEST_EVIDENCE_CODE_REVISION_MISMATCH")
    if latest.get("benchmark_driver_sha256") != current_driver_sha256:
        blockers.append("LATEST_EVIDENCE_DRIVER_MISMATCH")
    if latest.get("clock_source") != _CANONICAL_CLOCK_SOURCE:
        blockers.append("LATEST_EVIDENCE_CLOCK_SOURCE_MISMATCH")
    if latest.get("max_regression_percent") != _CANONICAL_MAX_REGRESSION_PERCENT:
        blockers.append("LATEST_EVIDENCE_POLICY_MISMATCH")
    if changed_paths:
        blockers.append("LATEST_EVIDENCE_REPOSITORY_DIRTY")

    stability_diagnostics = stability.get("diagnostics")
    if stability.get("status") != "PASS":
        blockers.append("LATEST_EVIDENCE_STABILITY_NOT_PASSING")
    if stability.get("status") == "PASS" and (
        stability.get("schema_version") != _STABILITY_SCHEMA_VERSION
        or stability.get("blockers") != []
        or not isinstance(stability_diagnostics, list)
        or not stability_diagnostics
        or any(
            not isinstance(item, dict) or item.get("stable_outcome") is not True
            for item in stability_diagnostics
        )
        or not isinstance(stability.get("comparison_count"), int)
        or cast(int, stability.get("comparison_count")) < 2
        or stability.get("clock_source") != _CANONICAL_CLOCK_SOURCE
        or stability.get("max_regression_percent") != _CANONICAL_MAX_REGRESSION_PERCENT
    ):
        blockers.append("LATEST_EVIDENCE_STABILITY_CONTRACT_INVALID")
    if stability.get("code_revision") != current_code_revision:
        blockers.append("LATEST_EVIDENCE_STABILITY_REVISION_MISMATCH")
    if stability.get("benchmark_driver_sha256") != current_driver_sha256:
        blockers.append("LATEST_EVIDENCE_STABILITY_DRIVER_MISMATCH")
    stability_binding = latest.get("stability_evidence")
    if not isinstance(stability_binding, dict):
        blockers.append("LATEST_EVIDENCE_STABILITY_BINDING_MISSING")
    elif any(
        stability_binding.get(field) != stability.get(field)
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
    ):
        blockers.append("LATEST_EVIDENCE_STABILITY_BINDING_MISMATCH")

    runtime = latest.get("current_runtime")
    if not isinstance(runtime, dict):
        blockers.append("LATEST_EVIDENCE_RUNTIME_INVALID")
    else:
        blockers.extend(
            f"LATEST_EVIDENCE_{blocker}"
            for blocker in _current_runtime_blockers(
                cast(dict[str, Any], runtime), _CANONICAL_VERSION
            )
        )

    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "schema_version": _LATEST_VERIFICATION_SCHEMA_VERSION,
        "artifact_origin": "python_migration_latest_evidence_verification",
        "latest_code_revision": latest.get("code_revision"),
        "current_code_revision": current_code_revision,
        "latest_benchmark_driver_sha256": latest.get("benchmark_driver_sha256"),
        "current_benchmark_driver_sha256": current_driver_sha256,
        "stability_status": stability.get("status"),
        "stability_code_revision": stability.get("code_revision"),
        "stability_benchmark_driver_sha256": stability.get("benchmark_driver_sha256"),
        "stability_max_regression_percent": stability.get("max_regression_percent"),
        "changed_paths": list(changed_paths),
        "status": "PASS" if not unique_blockers else "BLOCKED",
        "blockers": unique_blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _invalidate_latest_payload(
    latest: dict[str, Any],
    verification: dict[str, object],
) -> dict[str, object]:
    if verification.get("status") != "BLOCKED":
        raise ValueError("latest evidence invalidation requires a blocked verification")
    payload = cast(dict[str, object], dict(latest))
    raw_blockers = latest.get("blockers")
    blockers = list(raw_blockers) if isinstance(raw_blockers, list) else []
    verification_blockers = verification.get("blockers")
    if isinstance(verification_blockers, list):
        blockers.extend(f"verification:{item}" for item in verification_blockers)
    payload["status"] = "BLOCKED"
    payload["blockers"] = list(dict.fromkeys(blockers))
    payload["latest_verification"] = {
        "schema_version": verification.get("schema_version"),
        "status": verification.get("status"),
        "blockers": verification.get("blockers"),
        "current_code_revision": verification.get("current_code_revision"),
        "current_benchmark_driver_sha256": verification.get(
            "current_benchmark_driver_sha256"
        ),
    }
    payload["execution_allowed"] = False
    payload["promotion_status"] = "RESEARCH_ONLY"
    payload["live_eligibility_status"] = "LIVE_ORDER_BLOCKED"
    return payload


def _write(path: Path, payload: dict[str, object]) -> None:
    write_json_object_verified(
        path,
        payload,
        blocker="PYTHON_MIGRATION_BENCHMARK_WRITE_FAILED",
        subject_id=str(payload.get("code_revision", "unknown")),
        indent=2,
        durable=True,
    )


def _run_measurement_process(
    *,
    python_executable: Path,
    repository_root: Path,
    environment_id: str,
    code_revision: str,
    output: Path,
    affinity_cpu: int,
    load_sampler: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[str | None, tuple[float, ...]]:
    command = [
        str(python_executable),
        "-B",
        "-m",
        "ai4binance.ops.python_migration_benchmark",
        "measure",
        "--environment-id",
        environment_id,
        "--code-revision",
        code_revision,
        "--output",
        str(output),
        "--repetitions",
        str(_PAIRED_REPETITIONS),
        "--affinity-cpu",
        str(affinity_cpu),
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository_root / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    sample = load_sampler or (
        lambda: _host_cpu_load_percent(probe_seconds=_QUIESCENCE_PROBE_SECONDS)
    )
    try:
        _, _, measurement_max_load_percent = _measurement_host_load_limits()
    except OSError:
        return "HOST_LOAD_UNAVAILABLE_DURING_MEASUREMENT", ()
    try:
        process = subprocess.Popen(  # noqa: S603  # nosec B603
            command,
            cwd=repository_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return "MEASUREMENT_PROCESS_UNAVAILABLE", ()

    def stop_process() -> None:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            process.communicate()

    samples: list[float] = []
    consecutive_busy = 0
    started = time.monotonic()
    while process.poll() is None:
        if time.monotonic() - started >= _MEASUREMENT_TIMEOUT_SECONDS:
            stop_process()
            return "MEASUREMENT_PROCESS_TIMEOUT", tuple(samples)
        try:
            load_percent = float(sample())
        except (OSError, ValueError):
            stop_process()
            return "HOST_LOAD_UNAVAILABLE_DURING_MEASUREMENT", tuple(samples)
        if not 0.0 <= load_percent <= 100.0:
            stop_process()
            return "HOST_LOAD_SAMPLE_INVALID_DURING_MEASUREMENT", tuple(samples)
        samples.append(load_percent)
        consecutive_busy = (
            consecutive_busy + 1 if load_percent > measurement_max_load_percent else 0
        )
        if consecutive_busy >= _MEASUREMENT_REQUIRED_CONSECUTIVE_BUSY_SAMPLES:
            stop_process()
            return "HOST_NOT_QUIESCENT_DURING_MEASUREMENT", tuple(samples)
        if process.poll() is None:
            sleeper(_QUIESCENCE_WAIT_SECONDS)

    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        stop_process()
        return "MEASUREMENT_PROCESS_TIMEOUT", tuple(samples)
    if process.returncode != 0:
        return "MEASUREMENT_PROCESS_FAILED", tuple(samples)
    if not samples:
        return "MEASUREMENT_HOST_LOAD_SAMPLE_MISSING", ()
    return None, tuple(samples)


def _blocked_latest_payload(
    *,
    code_revision: str,
    driver_sha256: str,
    blockers: list[str],
    comparison: dict[str, Any] | None = None,
) -> dict[str, object]:
    payload = (
        cast(dict[str, object], dict(comparison))
        if comparison is not None
        else {
            "schema_version": _SCHEMA_VERSION,
            "artifact_origin": "python_migration_paired_benchmark",
            "code_revision": code_revision,
            "benchmark_driver_sha256": driver_sha256,
            "clock_source": _CANONICAL_CLOCK_SOURCE,
            "max_regression_percent": _CANONICAL_MAX_REGRESSION_PERCENT,
            "comparisons": [],
        }
    )
    raw_blockers = payload.get("blockers")
    combined = list(raw_blockers) if isinstance(raw_blockers, list) else []
    combined.extend(blockers)
    payload["status"] = "BLOCKED"
    payload["blockers"] = list(dict.fromkeys(combined))
    payload["execution_allowed"] = False
    payload["promotion_status"] = "RESEARCH_ONLY"
    payload["live_eligibility_status"] = "LIVE_ORDER_BLOCKED"
    return payload


def _latest_with_verification(
    latest: dict[str, Any],
    verification: dict[str, object],
) -> dict[str, object]:
    if verification.get("status") != "PASS":
        return _invalidate_latest_payload(latest, verification)
    payload = cast(dict[str, object], dict(latest))
    payload["latest_verification"] = {
        "schema_version": verification.get("schema_version"),
        "status": verification.get("status"),
        "blockers": verification.get("blockers"),
        "current_code_revision": verification.get("current_code_revision"),
        "current_benchmark_driver_sha256": verification.get(
            "current_benchmark_driver_sha256"
        ),
    }
    payload["execution_allowed"] = False
    payload["promotion_status"] = "RESEARCH_ONLY"
    payload["live_eligibility_status"] = "LIVE_ORDER_BLOCKED"
    return payload


def _run_paired_benchmark(
    *,
    baseline_python: Path,
    current_python: Path,
    baseline_version: str,
    repository_root: Path,
    output_directory: Path,
    latest_output: Path,
    environment_id: str,
    initial_blockers: tuple[str, ...] = (),
) -> dict[str, object]:
    root = repository_root.resolve()
    evidence_root = (root / "runtime" / "artifacts" / "python_migration").resolve()
    output_dir = output_directory.resolve()
    latest_path = latest_output.resolve()
    if not output_dir.is_relative_to(evidence_root) or not latest_path.is_relative_to(
        evidence_root
    ):
        raise ValueError("PAIRED_BENCHMARK_OUTPUT_OUTSIDE_RUNTIME")
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise ValueError("PAIRED_BENCHMARK_OUTPUT_DIRECTORY_NOT_EMPTY")
    else:
        output_dir.mkdir(parents=True)

    revision, changed_paths, repository_blockers = _repository_state(root)
    driver_sha256 = _driver_sha256()
    blockers = [*initial_blockers, *repository_blockers]
    if changed_paths:
        blockers.append("PAIRED_BENCHMARK_REPOSITORY_DIRTY")

    executable_by_role = {
        "baseline": baseline_python.resolve(),
        "current": current_python.resolve(),
    }
    for role, executable in executable_by_role.items():
        if not executable.is_relative_to(root) or not executable.is_file():
            blockers.append(f"PAIRED_BENCHMARK_{role.upper()}_PYTHON_INVALID")

    plan = (
        ("baseline", "current"),
        ("current", "baseline"),
        ("baseline", "current"),
        ("current", "baseline"),
    )
    quiescence_checks: list[dict[str, object]] = []
    measurement_host_load_checks: list[dict[str, object]] = []
    comparisons: list[dict[str, Any]] = []
    comparison_paths: list[str] = []
    measurement_paths_by_round: list[dict[str, Path]] = []

    for round_number, order in enumerate(plan, start=1):
        measurement_paths: dict[str, Path] = {}
        for role in order:
            if blockers:
                break
            measurement_path = output_dir / f"round{round_number}-{role}.json"
            for measurement_attempt in range(1, _MEASUREMENT_MAX_ATTEMPTS + 1):
                quiet, samples, quiescence_blocker = _await_host_quiescence()
                quiescence_checks.append(
                    {
                        "round": round_number,
                        "runtime_role": role,
                        "measurement_attempt": measurement_attempt,
                        "samples_percent": list(samples),
                        "status": "PASS" if quiet else "BLOCKED",
                        "blocker": quiescence_blocker,
                    }
                )
                if not quiet:
                    if (
                        quiescence_blocker == "HOST_NOT_QUIESCENT"
                        and measurement_attempt < _MEASUREMENT_MAX_ATTEMPTS
                    ):
                        continue
                    blockers.append(
                        f"{quiescence_blocker or 'HOST_NOT_QUIESCENT'}:"
                        f"round-{round_number}:{role}"
                    )
                    break

                observed_revision, observed_changes, observed_blockers = (
                    _repository_state(root)
                )
                if (
                    observed_revision != revision
                    or observed_changes
                    or observed_blockers
                ):
                    blockers.extend(observed_blockers)
                    blockers.append("REPOSITORY_MUTATED_DURING_PAIRED_BENCHMARK")
                    break

                process_blocker, measurement_load_samples = _run_measurement_process(
                    python_executable=executable_by_role[role],
                    repository_root=root,
                    environment_id=environment_id,
                    code_revision=revision,
                    output=measurement_path,
                    affinity_cpu=_PAIRED_AFFINITY_CPU,
                )
                measurement_host_load_checks.append(
                    {
                        "round": round_number,
                        "runtime_role": role,
                        "measurement_attempt": measurement_attempt,
                        "samples_percent": list(measurement_load_samples),
                        "status": "PASS" if process_blocker is None else "BLOCKED",
                        "blocker": process_blocker,
                    }
                )
                (
                    post_measurement_revision,
                    post_measurement_changes,
                    post_measurement_blockers,
                ) = _repository_state(root)
                if (
                    post_measurement_revision != revision
                    or post_measurement_changes
                    or post_measurement_blockers
                ):
                    blockers.extend(post_measurement_blockers)
                    blockers.append("REPOSITORY_MUTATED_DURING_PAIRED_BENCHMARK")
                    if process_blocker is not None:
                        blockers.append(
                            f"{process_blocker}:round-{round_number}:{role}"
                        )
                    break
                if process_blocker is None:
                    (
                        logical_processor_count,
                        benchmark_cpu_budget_percent,
                        measurement_max_load_percent,
                    ) = _measurement_host_load_limits()
                    measurement_payload = _load_payload(measurement_path)
                    measurement_payload["host_load_attestation"] = {
                        "schema_version": _MEASUREMENT_HOST_LOAD_SCHEMA_VERSION,
                        "status": "PASS",
                        "blockers": [],
                        "external_load_budget_percent": _MAX_HOST_LOAD_PERCENT,
                        "benchmark_cpu_budget_percent": (benchmark_cpu_budget_percent),
                        "logical_processor_count": logical_processor_count,
                        "max_percent": measurement_max_load_percent,
                        "required_consecutive_busy_samples": (
                            _MEASUREMENT_REQUIRED_CONSECUTIVE_BUSY_SAMPLES
                        ),
                        "sample_count": len(measurement_load_samples),
                        "samples_percent": list(measurement_load_samples),
                    }
                    _write(measurement_path, measurement_payload)
                    measurement_paths[role] = measurement_path
                    break
                if (
                    process_blocker == "HOST_NOT_QUIESCENT_DURING_MEASUREMENT"
                    and measurement_attempt < _MEASUREMENT_MAX_ATTEMPTS
                ):
                    continue
                blockers.append(f"{process_blocker}:round-{round_number}:{role}")
                break

        if blockers:
            break
        measurement_paths_by_round.append(measurement_paths)
        if round_number % 2:
            continue

        cycle_number = round_number // 2
        cycle_rounds = measurement_paths_by_round[-2:]
        first_round, second_round = cycle_rounds
        try:
            baseline_aggregate = _aggregate_abba_measurements(
                (
                    _load_payload(first_round["baseline"]),
                    _load_payload(second_round["baseline"]),
                )
            )
            current_aggregate = _aggregate_abba_measurements(
                (
                    _load_payload(first_round["current"]),
                    _load_payload(second_round["current"]),
                )
            )
        except ValueError as exc:
            blockers.append(f"PAIRED_BENCHMARK_AGGREGATION_INVALID:{exc}")
            break
        baseline_aggregate_path = output_dir / f"cycle{cycle_number}-baseline.json"
        current_aggregate_path = output_dir / f"cycle{cycle_number}-current.json"
        _write(baseline_aggregate_path, baseline_aggregate)
        _write(current_aggregate_path, current_aggregate)
        comparison = _compare(
            baseline=cast(dict[str, Any], baseline_aggregate),
            current=cast(dict[str, Any], current_aggregate),
            baseline_version=baseline_version,
            current_version=_CANONICAL_VERSION,
            max_regression_percent=_CANONICAL_MAX_REGRESSION_PERCENT,
        )
        comparison_path = output_dir / f"cycle{cycle_number}-comparison.json"
        _write(comparison_path, comparison)
        comparisons.append(cast(dict[str, Any], comparison))
        comparison_paths.append(str(comparison_path))

    stability_path = output_dir / "stability-diagnosis.json"
    verification_path = output_dir / "latest-verification.json"
    if len(comparisons) == len(plan) // 2:
        stability = _diagnose_stability(comparisons)
        _write(stability_path, stability)
        candidate = _bind_stability_to_latest(comparisons[-1], stability)
        final_revision, final_changes, final_blockers = _repository_state(root)
        verification = _verify_latest_payload(
            cast(dict[str, Any], candidate),
            stability=cast(dict[str, Any], stability),
            current_code_revision=final_revision,
            current_driver_sha256=_driver_sha256(),
            changed_paths=final_changes,
            repository_blockers=final_blockers,
        )
        if final_revision != revision:
            raw_verification_blockers = verification.get("blockers")
            verification_blockers = (
                list(raw_verification_blockers)
                if isinstance(raw_verification_blockers, list)
                else []
            )
            verification_blockers.append(
                "LATEST_EVIDENCE_REPOSITORY_MUTATED_DURING_VERIFICATION"
            )
            verification["status"] = "BLOCKED"
            verification["blockers"] = list(dict.fromkeys(verification_blockers))
        _write(verification_path, verification)
        final_latest = _latest_with_verification(
            cast(dict[str, Any], candidate), verification
        )
        _write(latest_path, final_latest)
        stability_blockers = stability.get("blockers")
        if isinstance(stability_blockers, list):
            blockers.extend(f"stability:{item}" for item in stability_blockers)
        raw_final_verification_blockers = verification.get("blockers")
        if isinstance(raw_final_verification_blockers, list):
            blockers.extend(
                f"verification:{item}" for item in raw_final_verification_blockers
            )
    else:
        latest = _blocked_latest_payload(
            code_revision=revision,
            driver_sha256=driver_sha256,
            blockers=blockers,
            comparison=comparisons[-1] if comparisons else None,
        )
        stability = _blocked_stability_payload(
            comparisons=comparisons,
            code_revision=revision,
            driver_sha256=driver_sha256,
            blockers=blockers,
        )
        _write(stability_path, stability)
        candidate = _bind_stability_to_latest(
            cast(dict[str, Any], latest),
            stability,
        )
        final_revision, final_changes, final_blockers = _repository_state(root)
        verification = _verify_latest_payload(
            cast(dict[str, Any], candidate),
            stability=cast(dict[str, Any], stability),
            current_code_revision=final_revision,
            current_driver_sha256=_driver_sha256(),
            changed_paths=final_changes,
            repository_blockers=final_blockers,
        )
        if final_revision != revision:
            raw_verification_blockers = verification.get("blockers")
            verification_blockers = (
                list(raw_verification_blockers)
                if isinstance(raw_verification_blockers, list)
                else []
            )
            verification_blockers.append(
                "LATEST_EVIDENCE_REPOSITORY_MUTATED_DURING_VERIFICATION"
            )
            verification["status"] = "BLOCKED"
            verification["blockers"] = list(dict.fromkeys(verification_blockers))
        _write(verification_path, verification)
        _write(
            latest_path,
            _latest_with_verification(
                cast(dict[str, Any], candidate),
                verification,
            ),
        )
        raw_final_verification_blockers = verification.get("blockers")
        if isinstance(raw_final_verification_blockers, list):
            blockers.extend(
                f"verification:{item}" for item in raw_final_verification_blockers
            )

    unique_blockers = list(dict.fromkeys(blockers))
    payload: dict[str, object] = {
        "schema_version": _PAIRED_ORCHESTRATION_SCHEMA_VERSION,
        "artifact_origin": "python_migration_paired_benchmark_orchestration",
        "code_revision": revision,
        "benchmark_driver_sha256": driver_sha256,
        "environment_id": environment_id,
        "measurement_order": [list(order) for order in plan],
        "measurement_policy": {
            "clock_source": _CANONICAL_CLOCK_SOURCE,
            "repetitions_per_round_per_runtime": _PAIRED_REPETITIONS,
            "samples_per_cycle_per_runtime": _PAIRED_REPETITIONS * 2,
            "process_affinity_cpu": _PAIRED_AFFINITY_CPU,
            "process_affinity_mask": 1 << _PAIRED_AFFINITY_CPU,
            "max_attempts_per_round_runtime": _MEASUREMENT_MAX_ATTEMPTS,
        },
        "host_load_policy": {
            "max_percent": _QUIESCENCE_MAX_HOST_LOAD_PERCENT,
            "attempts": _QUIESCENCE_ATTEMPTS,
            "required_consecutive_samples": _QUIESCENCE_REQUIRED_CONSECUTIVE_SAMPLES,
            "probe_seconds": _QUIESCENCE_PROBE_SECONDS,
            "wait_seconds": _QUIESCENCE_WAIT_SECONDS,
            "max_wait_seconds": (
                _QUIESCENCE_ATTEMPTS * _QUIESCENCE_PROBE_SECONDS
                + (_QUIESCENCE_ATTEMPTS - 1) * _QUIESCENCE_WAIT_SECONDS
            ),
            "during_measurement_required_consecutive_busy_samples": (
                _MEASUREMENT_REQUIRED_CONSECUTIVE_BUSY_SAMPLES
            ),
            "during_measurement_load_limits": {
                "external_load_budget_percent": _MAX_HOST_LOAD_PERCENT,
                "benchmark_cpu_budget_percent": (_measurement_host_load_limits()[1]),
                "logical_processor_count": _measurement_host_load_limits()[0],
                "max_percent": _measurement_host_load_limits()[2],
            },
        },
        "quiescence_checks": quiescence_checks,
        "measurement_host_load_checks": measurement_host_load_checks,
        "comparison_paths": comparison_paths,
        "stability_path": str(stability_path) if stability_path.is_file() else None,
        "verification_path": (
            str(verification_path) if verification_path.is_file() else None
        ),
        "latest_path": str(latest_path),
        "status": "PASS" if not unique_blockers else "BLOCKED",
        "blockers": unique_blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    _write(output_dir / "orchestration.json", payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    paired = subparsers.add_parser("run-paired")
    paired.add_argument("--baseline-python", type=Path, required=True)
    paired.add_argument("--current-python", type=Path, required=True)
    paired.add_argument("--baseline-version", required=True)
    paired.add_argument("--repository-root", type=Path, required=True)
    paired.add_argument("--output-directory", type=Path, required=True)
    paired.add_argument("--latest-output", type=Path, required=True)
    paired.add_argument("--environment-id", required=True)

    measure = subparsers.add_parser("measure")
    measure.add_argument("--environment-id", required=True)
    measure.add_argument("--code-revision", required=True)
    measure.add_argument("--output", type=Path, required=True)
    measure.add_argument("--decision-iterations", type=int, default=5_000)
    measure.add_argument(
        "--replay-iterations",
        type=int,
        default=_DEFAULT_REPLAY_ITERATIONS,
    )
    measure.add_argument("--repetitions", type=int, default=9)
    measure.add_argument("--affinity-cpu", type=int)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--current", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--baseline-version", required=True)
    compare.add_argument("--current-version", default=_CANONICAL_VERSION)
    compare.add_argument(
        "--max-regression-percent",
        type=float,
        default=_CANONICAL_MAX_REGRESSION_PERCENT,
    )
    compare.add_argument("--latest-output", type=Path)

    stability = subparsers.add_parser("diagnose-stability")
    stability.add_argument(
        "--comparison",
        action="append",
        dest="comparisons",
        type=Path,
        required=True,
    )
    stability.add_argument("--output", type=Path, required=True)
    stability.add_argument("--latest-output", type=Path)

    verify_latest = subparsers.add_parser("verify-latest")
    verify_latest.add_argument("--latest", type=Path, required=True)
    verify_latest.add_argument("--stability", type=Path, required=True)
    verify_latest.add_argument("--repository-root", type=Path, required=True)
    verify_latest.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run-paired":
        mutex_handle, mutex_blocker = _try_acquire_quality_gate_mutex(
            args.repository_root
        )
        try:
            payload = _run_paired_benchmark(
                baseline_python=args.baseline_python,
                current_python=args.current_python,
                baseline_version=args.baseline_version,
                repository_root=args.repository_root,
                output_directory=args.output_directory,
                latest_output=args.latest_output,
                environment_id=args.environment_id,
                initial_blockers=(mutex_blocker,) if mutex_blocker else (),
            )
        finally:
            _release_quality_gate_mutex(mutex_handle)
        print(f"PYTHON_MIGRATION_PAIRED_{payload['status']}")
        return 0 if payload["status"] == "PASS" else 2

    if args.command == "measure":
        process_affinity = (
            _set_process_affinity(args.affinity_cpu)
            if args.affinity_cpu is not None
            else None
        )
        payload = _measure(
            environment_id=args.environment_id,
            code_revision=args.code_revision,
            decision_iterations=args.decision_iterations,
            replay_iterations=args.replay_iterations,
            repetitions=args.repetitions,
            process_affinity=process_affinity,
        )
        _write(args.output, payload)
        print("PYTHON_MIGRATION_BENCHMARK_MEASURED")
        return 0

    if args.command == "compare":
        payload = _compare(
            baseline=_load_payload(args.baseline),
            current=_load_payload(args.current),
            baseline_version=args.baseline_version,
            current_version=args.current_version,
            max_regression_percent=args.max_regression_percent,
        )
        _write(args.output, payload)
        if args.latest_output is not None:
            _write(args.latest_output, payload)
        print(f"PYTHON_MIGRATION_BENCHMARK_{payload['status']}")
        return 0 if payload["status"] == "PASS" else 2

    if args.command == "diagnose-stability":
        comparisons = [_load_payload(path) for path in args.comparisons]
        payload = _diagnose_stability(comparisons)
        _write(args.output, payload)
        if args.latest_output is not None:
            _write(
                args.latest_output,
                _bind_stability_to_latest(comparisons[-1], payload),
            )
        print(f"PYTHON_MIGRATION_STABILITY_{payload['status']}")
        return 0 if payload["status"] == "PASS" else 2

    revision, changed_paths, repository_blockers = _repository_state(
        args.repository_root
    )
    latest = _load_payload(args.latest)
    payload = _verify_latest_payload(
        latest,
        stability=_load_stability_payload(args.stability),
        current_code_revision=revision,
        current_driver_sha256=_driver_sha256(),
        changed_paths=changed_paths,
        repository_blockers=repository_blockers,
    )
    _write(args.output, payload)
    if payload["status"] != "PASS":
        _write(args.latest, _invalidate_latest_payload(latest, payload))
    print(f"PYTHON_MIGRATION_LATEST_{payload['status']}")
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Focused fail-closed coverage for GPU governance value contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

import pytest

from ai4binance.enterprise import gpu
from ai4binance.enterprise.gpu import (
    GpuCircuitBreaker,
    GpuCircuitBreakerState,
    GpuComputePolicy,
    GpuComputeProfile,
    GpuLease,
    GpuLeaseKind,
    GpuLeaseState,
    GpuPolicyMatrixRow,
    GpuRuntimeSelection,
    GpuTelemetryAssessment,
    GpuTelemetrySnapshot,
    GpuWorkloadKind,
)

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def _telemetry(**changes: object) -> GpuTelemetrySnapshot:
    values: dict[str, object] = {
        "observed_at": NOW,
        "cuda_available": True,
        "allocator_memory_allocated_bytes": 1,
        "allocator_memory_reserved_bytes": 2,
        "allocator_peak_allocated_bytes": 3,
        "allocator_peak_reserved_bytes": 4,
        "total_vram_bytes": 100,
        "free_vram_bytes": 50,
        "gpu_utilization_pct": 10,
        "active_gpu_processes": 1,
        "source": ("test",),
    }
    values.update(changes)
    return GpuTelemetrySnapshot(**values)  # type: ignore[arg-type]


def _profile(**changes: object) -> GpuComputeProfile:
    values: dict[str, object] = {
        "name": "profile",
        "workload": GpuWorkloadKind.LLM_INFERENCE,
        "lease_kind": GpuLeaseKind.LLM_GPU,
    }
    values.update(changes)
    return GpuComputeProfile(**values)  # type: ignore[arg-type]


def _matrix(**changes: object) -> GpuPolicyMatrixRow:
    values: dict[str, object] = {
        "capability": "capability",
        "default_compute": "CPU",
        "cuda_stance": "optional",
        "governing_rule": "governed",
        "required_telemetry": "required",
        "fallback": "CPU",
        "promotion_gate": "benchmark",
    }
    values.update(changes)
    return GpuPolicyMatrixRow(**values)  # type: ignore[arg-type]


def _lease(**changes: object) -> GpuLease:
    values: dict[str, object] = {
        "lease_id": "lease-1",
        "workload": GpuWorkloadKind.LLM_INFERENCE,
        "lease_kind": GpuLeaseKind.LLM_GPU,
        "compute_profile": "profile",
        "device": "cuda",
        "issued_at": NOW,
    }
    values.update(changes)
    return GpuLease(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _telemetry(observed_at=NOW.replace(tzinfo=None)),
        lambda: _telemetry(allocator_memory_allocated_bytes=-1),
        lambda: _telemetry(allocator_peak_allocated_bytes=0),
        lambda: _telemetry(allocator_peak_reserved_bytes=0),
        lambda: _telemetry(total_vram_bytes=-1),
        lambda: _telemetry(free_vram_bytes=-1),
        lambda: _telemetry(free_vram_bytes=101),
        lambda: _telemetry(gpu_utilization_pct=101),
        lambda: _telemetry(active_gpu_processes=-1),
        lambda: _telemetry(source=("",)),
        lambda: _telemetry(source=("x", "x")),
        lambda: _profile(name=" "),
        lambda: _profile(gpu_eligible=False),
        lambda: _matrix(workloads=(cast(GpuWorkloadKind, "bad"),)),
        lambda: _matrix(workloads=(GpuWorkloadKind.LLM_INFERENCE,) * 2),
        lambda: _matrix(lease_ttl_minutes=0),
        lambda: _matrix(workloads=(GpuWorkloadKind.LLM_INFERENCE,)),
        lambda: _matrix(priority=-1),
        lambda: _matrix(capability=" "),
    ],
)
def test_gpu_telemetry_profile_and_matrix_reject_unsafe_values(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_gpu_telemetry_assessment_and_selection_contracts_fail_closed() -> None:
    assessment = GpuTelemetryAssessment(
        observed_at=NOW,
        source_label="test",
        cuda_available=True,
        device_name="GPU",
        driver_version="1",
        total_vram_bytes=100,
        free_vram_bytes=50,
        gpu_utilization_pct=10,
        active_gpu_processes=1,
        headroom_percent=20,
        healthy=True,
    )
    invalid_assessments: tuple[Callable[[], object], ...] = (
        lambda: replace(assessment, source_label=" "),
        lambda: replace(assessment, headroom_percent=0),
        lambda: replace(assessment, blockers=("",)),
        lambda: replace(assessment, blockers=("A", "A"), healthy=False),
        lambda: replace(assessment, blockers=("A",)),
    )
    for factory in invalid_assessments:
        with pytest.raises(ValueError, match=r"."):
            factory()

    selection = GpuRuntimeSelection(
        workload=GpuWorkloadKind.LLM_INFERENCE,
        requested_device="auto",
        selected_device="cpu",
        compute_profile="profile",
        lease_kind=GpuLeaseKind.LLM_GPU,
        lease_state=GpuLeaseState.REQUESTED,
        telemetry_source="test",
    )
    invalid_selections: tuple[Callable[[], object], ...] = (
        lambda: replace(
            selection,
            requested_device=cast(Literal["cpu", "cuda", "auto"], "bad"),
        ),
        lambda: replace(
            selection,
            selected_device=cast(Literal["cpu", "cuda"], "bad"),
        ),
        lambda: replace(selection, compute_profile=" "),
        lambda: replace(selection, telemetry_source=" "),
        lambda: replace(selection, priority=-1),
        lambda: replace(selection, lease_ttl_minutes=0),
        lambda: replace(selection, blockers=("",)),
        lambda: replace(selection, blockers=("A", "A")),
    )
    for factory in invalid_selections:
        with pytest.raises(ValueError, match=r"."):
            factory()


def test_gpu_leases_breaker_policy_and_payload_helpers_cover_invalid_paths() -> None:
    invalid_leases: tuple[Callable[[], object], ...] = (
        lambda: _lease(lease_id=" "),
        lambda: _lease(device=cast(Literal["cpu", "cuda"], "bad")),
        lambda: _lease(priority=-1),
        lambda: _lease(state=GpuLeaseState.GRANTED),
        lambda: _lease(state=GpuLeaseState.RELEASED),
        lambda: _lease(state=GpuLeaseState.EXPIRED),
        lambda: _lease(granted_at=NOW - timedelta(seconds=1)),
        lambda: _lease(released_at=NOW),
        lambda: _lease(expires_at=NOW - timedelta(seconds=1)),
        lambda: _lease(telemetry=GpuTelemetrySnapshot(observed_at=NOW)),
        lambda: _lease(blockers=("",)),
        lambda: _lease(blockers=("A", "A")),
    )
    for factory in invalid_leases:
        with pytest.raises(ValueError, match=r"."):
            factory()

    invalid_breakers: tuple[Callable[[], object], ...] = (
        lambda: GpuCircuitBreaker(failure_count=-1),
        lambda: GpuCircuitBreaker(failure_threshold=0),
        lambda: GpuCircuitBreaker(open_cooldown=timedelta(0)),
        lambda: GpuCircuitBreaker(
            state=GpuCircuitBreakerState.OPEN,
            opened_at=NOW,
            last_reason="reason",
        ),
        lambda: GpuCircuitBreaker(state=GpuCircuitBreakerState.OPEN),
    )
    for factory in invalid_breakers:
        with pytest.raises(ValueError, match=r"."):
            factory()

    with pytest.raises(ValueError, match="failure reason"):
        GpuCircuitBreaker().record_failure(" ", occurred_at=NOW)
    assert GpuCircuitBreaker().record_failure("x", occurred_at=NOW).allows_gpu()
    assert (
        not GpuCircuitBreaker(failure_threshold=1)
        .record_failure("x", occurred_at=NOW)
        .allows_gpu()
    )
    with pytest.raises(ValueError, match="device selection"):
        gpu._normalize_device("bad")
    with pytest.raises(ValueError, match="timezone-aware"):
        gpu._require_aware(NOW.replace(tzinfo=None), "test")
    with pytest.raises(ValueError, match="ISO 8601"):
        gpu._parse_datetime(None, "test")
    with pytest.raises(ValueError, match="timestamps"):
        gpu._optional_datetime(1)
    with pytest.raises(ValueError, match="sequence"):
        gpu._tuple_from_payload(1, field_name="blockers")
    with pytest.raises(ValueError, match="non-empty"):
        gpu._tuple_from_payload(("",), field_name="blockers")
    with pytest.raises(ValueError, match="unique"):
        gpu._tuple_from_payload(("A", "A"), field_name="blockers")
    with pytest.raises(ValueError, match="integer"):
        gpu._int_from_payload(object(), field_name="priority")
    with pytest.raises(ValueError, match="object"):
        gpu._require_mapping(())

    with pytest.raises(ValueError, match="headroom"):
        GpuComputePolicy(vram_headroom_percent=0)
    with pytest.raises(ValueError, match="lease ttl"):
        GpuComputePolicy(lease_ttl_minutes=0)
    with pytest.raises(ValueError, match="full device"):
        GpuComputePolicy(allow_full_device_allocation=True)
    with pytest.raises(ValueError, match="requires at least one profile"):
        GpuComputePolicy(profiles=())
    with pytest.raises(ValueError, match="requires a policy matrix"):
        GpuComputePolicy(policy_matrix=())

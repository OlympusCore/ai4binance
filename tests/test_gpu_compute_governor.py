from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.enterprise import (
    GpuCircuitBreaker,
    GpuCircuitBreakerState,
    GpuComputePolicy,
    GpuLease,
    GpuLeaseJournal,
    GpuLeaseJournalCorruptionError,
    GpuLeaseKind,
    GpuLeaseState,
    GpuPolicyMatrixRow,
    GpuResourceGovernor,
    GpuTelemetryAssessment,
    GpuTelemetrySnapshot,
    GpuWorkloadKind,
)


def test_gpu_compute_policy_exposes_the_canonical_terms_and_profiles() -> None:
    policy = GpuComputePolicy()

    assert policy.canonical_terms() == (
        "CPU_DEFAULT",
        "CUDA_OPTIONAL",
        "GPU_RESOURCE_GOVERNED",
        "LLM_GPU_ELIGIBLE",
        "TRAINING_GPU_ELIGIBLE",
        "BACKTEST_PROFILE_DRIVEN",
        "HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE",
        "CPU_REFERENCE_IMPLEMENTATION",
        "CPU_FALLBACK_REQUIRED",
        "BENCHMARK_BEFORE_PROMOTION",
        "CORRECTNESS_PARITY_REQUIRED",
        "VRAM_HEADROOM_REQUIRED",
        "GPU_CIRCUIT_BREAKER",
        "GPU_TELEMETRY_REQUIRED",
        "REBENCHMARK_ON_MATERIAL_CHANGE",
        "DETERMINISTIC_CORE_GPU_INDEPENDENT",
    )
    matrix = policy.canonical_policy_matrix()
    assert len(matrix) == 16
    assert matrix[0] == GpuPolicyMatrixRow(
        capability="Market ingestion",
        default_compute="CPU_DEFAULT",
        cuda_stance="No",
        governing_rule="Deterministic hot-path ingest stays CPU-only",
        required_telemetry="Not required",
        fallback="CPU only",
        promotion_gate="Not applicable",
    )
    assert matrix[7].capability == "Voice transcription"
    assert matrix[8].capability == "Local LLM"
    assert matrix[-1].capability == "Benchmark"
    assert (
        policy.matrix_row_for_workload(GpuWorkloadKind.LLM_INFERENCE).lease_ttl_minutes
        == 20
    )
    assert policy.priority_for_workload(GpuWorkloadKind.LLM_INFERENCE) == 8
    assert policy.lease_ttl_for_workload(GpuWorkloadKind.BACKTEST_ACCELERATION) == 120
    assert (
        policy.profile_for(GpuWorkloadKind.LLM_INFERENCE).lease_kind
        is GpuLeaseKind.LLM_GPU
    )
    assert (
        policy.profile_for(GpuWorkloadKind.MODEL_TRAINING).lease_kind
        is GpuLeaseKind.TRAINING_GPU
    )
    assert (
        policy.profile_for(GpuWorkloadKind.BACKTEST_ACCELERATION).benchmark_required
        is True
    )


def test_gpu_telemetry_snapshot_tracks_allocator_memory_and_headroom() -> None:
    observed_at = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    snapshot = GpuTelemetrySnapshot(
        observed_at=observed_at,
        cuda_available=True,
        device_name="RTX 4090",
        driver_version="550.40",
        allocator_memory_allocated_bytes=256 * 1024 * 1024,
        allocator_memory_reserved_bytes=512 * 1024 * 1024,
        allocator_peak_allocated_bytes=768 * 1024 * 1024,
        allocator_peak_reserved_bytes=1024 * 1024 * 1024,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=3 * 1024 * 1024 * 1024,
        gpu_utilization_pct=42,
        active_gpu_processes=1,
        source=("torch.cuda.is_available", "nvidia-smi"),
    )

    assert snapshot.has_vram_headroom(20) is True
    assert snapshot.as_source_label() == "torch.cuda.is_available+nvidia-smi"

    with pytest.raises(ValueError, match="reserved memory must cover allocated"):
        GpuTelemetrySnapshot(
            observed_at=observed_at,
            allocator_memory_allocated_bytes=512,
            allocator_memory_reserved_bytes=256,
        )


def test_gpu_resource_governor_falls_back_to_cpu_when_requested() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    selection = governor.select_runtime(
        GpuWorkloadKind.LLM_INFERENCE,
        "cpu",
        telemetry=telemetry,
    )

    assert selection.selected_device == "cpu"
    assert selection.lease_state is GpuLeaseState.RELEASED
    assert selection.cpu_fallback_used is False
    assert selection.blockers == ()
    assert (
        governor.select_voice_runtime("cpu", telemetry=telemetry).selected_device
        == "cpu"
    )


def test_gpu_resource_governor_grants_cuda_when_policy_and_headroom_allow() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    selection = governor.select_runtime(
        GpuWorkloadKind.LLM_INFERENCE,
        "cuda",
        telemetry=telemetry,
    )

    assert selection.selected_device == "cuda"
    assert selection.lease_state is GpuLeaseState.GRANTED
    assert selection.cpu_fallback_used is False
    assert (
        governor.select_llm_runtime("cuda", telemetry=telemetry).selected_device
        == "cuda"
    )
    lease = governor.issue_lease(
        GpuWorkloadKind.LLM_INFERENCE,
        "cuda",
        telemetry=telemetry,
        lease_id="lease-1",
    )
    assert lease is not None
    assert lease.state is GpuLeaseState.GRANTED
    assert lease.lease_kind is GpuLeaseKind.LLM_GPU
    assert lease.compute_profile == "LLM_INFERENCE_GPU"
    assert lease.priority == 8
    assert lease.expires_at == lease.issued_at + timedelta(minutes=20)
    assert len(governor.active_leases) == 1


def test_gpu_resource_governor_tracks_and_releases_active_leases() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    lease = governor.issue_llm_lease(
        "cuda",
        telemetry=telemetry,
        lease_id="lease-track-1",
    )

    assert lease is not None
    assert lease.priority == 8
    assert lease.expires_at == lease.issued_at + timedelta(minutes=20)
    assert governor.active_leases == (lease,)

    released = governor.release_lease(
        lease,
        released_at=datetime(2099, 8, 27, 12, 5, tzinfo=UTC),
    )

    assert released.state is GpuLeaseState.RELEASED
    assert not governor.active_leases


def test_gpu_resource_governor_tracks_leases_through_restart(
    tmp_path: Path,
) -> None:
    journal = GpuLeaseJournal(tmp_path / "gpu-track-leases.jsonl")
    governor = GpuResourceGovernor(lease_journal=journal)
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )
    lease = GpuLease(
        lease_id="lease-track-persisted",
        workload=GpuWorkloadKind.LLM_INFERENCE,
        lease_kind=GpuLeaseKind.LLM_GPU,
        compute_profile="LLM_INFERENCE_GPU",
        device="cuda",
        priority=8,
        state=GpuLeaseState.GRANTED,
        issued_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
        granted_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
        expires_at=datetime(2099, 8, 27, 12, 20, tzinfo=UTC),
        telemetry=telemetry,
    )

    governor.track_lease(lease, now=lease.issued_at)

    restarted = GpuResourceGovernor(lease_journal=journal)

    assert restarted.active_leases == (lease,)


def test_gpu_lease_journal_rejects_state_mismatches(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "gpu-leases-corrupt.jsonl"
    journal_path.write_text(
        '{"event_type":"GPU_LEASE_RELEASED","payload":{"lease_id":"lease-1","workload":"LLM_INFERENCE","lease_kind":"LLM_GPU","compute_profile":"LLM_INFERENCE_GPU","device":"cuda","priority":8,"state":"GRANTED","issued_at":"2026-08-27T12:00:00+00:00","granted_at":"2026-08-27T12:00:00+00:00","released_at":null,"expired_at":null,"expires_at":"2026-08-27T12:20:00+00:00","telemetry":null,"blockers":[]}}\n',
        encoding="utf-8",
    )
    journal = GpuLeaseJournal(journal_path)

    with pytest.raises(GpuLeaseJournalCorruptionError):
        journal.recover_active_leases(now=datetime(2099, 8, 27, 12, 30, tzinfo=UTC))


def test_gpu_resource_governor_rejects_untrackable_requested_leases(
    tmp_path: Path,
) -> None:
    journal = GpuLeaseJournal(tmp_path / "gpu-leases-requested-track.jsonl")
    governor = GpuResourceGovernor(lease_journal=journal)
    requested_lease = GpuLease(
        lease_id="lease-requested",
        workload=GpuWorkloadKind.LLM_INFERENCE,
        lease_kind=GpuLeaseKind.LLM_GPU,
        compute_profile="LLM_INFERENCE_GPU",
        device="cuda",
        state=GpuLeaseState.REQUESTED,
        issued_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="cannot be journaled"):
        governor.track_lease(requested_lease, now=requested_lease.issued_at)


def test_gpu_lease_rejects_impossible_time_ordering() -> None:
    with pytest.raises(ValueError, match="grant time cannot precede issue time"):
        GpuLease(
            lease_id="lease-impossible",
            workload=GpuWorkloadKind.LLM_INFERENCE,
            lease_kind=GpuLeaseKind.LLM_GPU,
            compute_profile="LLM_INFERENCE_GPU",
            device="cuda",
            state=GpuLeaseState.GRANTED,
            issued_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
            granted_at=datetime(2099, 8, 27, 11, 59, tzinfo=UTC),
            expires_at=datetime(2099, 8, 27, 12, 20, tzinfo=UTC),
        )


def test_gpu_lease_requested_state_is_not_recovered_as_active(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "gpu-leases-requested.jsonl"
    journal_path.write_text(
        '{"event_type":"GPU_LEASE_ISSUED","payload":{"lease_id":"lease-1","workload":"LLM_INFERENCE","lease_kind":"LLM_GPU","compute_profile":"LLM_INFERENCE_GPU","device":"cuda","priority":8,"state":"REQUESTED","issued_at":"2099-08-27T12:00:00+00:00","granted_at":null,"released_at":null,"expired_at":null,"expires_at":"2099-08-27T12:20:00+00:00","telemetry":null,"blockers":[]}}\n',
        encoding="utf-8",
    )
    journal = GpuLeaseJournal(journal_path)

    with pytest.raises(GpuLeaseJournalCorruptionError):
        journal.recover_active_leases(now=datetime(2099, 8, 27, 12, 30, tzinfo=UTC))


def test_gpu_resource_governor_restores_active_leases_from_persisted_journal(
    tmp_path: Path,
) -> None:
    journal = GpuLeaseJournal(tmp_path / "gpu-leases.jsonl")
    governor = GpuResourceGovernor(lease_journal=journal)
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2099, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    lease = governor.issue_llm_lease(
        "cuda",
        telemetry=telemetry,
        lease_id="lease-persisted-1",
    )

    assert lease is not None
    assert governor.active_leases == (lease,)

    restarted = GpuResourceGovernor(lease_journal=journal)

    assert restarted.active_leases == (lease,)
    assert restarted.active_leases[0].expires_at == lease.expires_at
    assert restarted.active_leases[0].priority == 8


def test_gpu_lease_journal_skips_released_and_expired_leases_on_replay(
    tmp_path: Path,
) -> None:
    journal = GpuLeaseJournal(tmp_path / "gpu-leases.jsonl")
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )
    issued_at = datetime(2026, 8, 27, 11, 0, tzinfo=UTC)
    lease = GpuLease(
        lease_id="lease-replayed-1",
        workload=GpuWorkloadKind.LLM_INFERENCE,
        lease_kind=GpuLeaseKind.LLM_GPU,
        compute_profile="LLM_INFERENCE_GPU",
        device="cuda",
        priority=8,
        state=GpuLeaseState.GRANTED,
        issued_at=issued_at,
        granted_at=issued_at,
        expires_at=issued_at + timedelta(minutes=20),
        telemetry=telemetry,
    )

    journal.append_issued(lease, occurred_at=issued_at)
    journal.append_released(
        lease.release(released_at=datetime(2099, 8, 27, 11, 5, tzinfo=UTC)),
        occurred_at=datetime(2099, 8, 27, 11, 5, tzinfo=UTC),
    )

    restored = GpuResourceGovernor(lease_journal=journal)

    assert restored.active_leases == ()

    expired_journal = GpuLeaseJournal(tmp_path / "gpu-leases-expired.jsonl")
    expired_journal.append_issued(lease, occurred_at=issued_at)

    replayed = expired_journal.recover_active_leases(
        now=datetime(2026, 8, 27, 11, 30, tzinfo=UTC)
    )

    assert replayed == ()


def test_gpu_resource_governor_ignores_expired_gpu_leases_for_admission() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )
    expired_lease = GpuLease(
        lease_id="expired-lease",
        workload=GpuWorkloadKind.MODEL_TRAINING,
        lease_kind=GpuLeaseKind.TRAINING_GPU,
        compute_profile="TRAINING_GPU",
        device="cuda",
        state=GpuLeaseState.ACTIVE,
        issued_at=datetime(2026, 8, 27, 11, 0, tzinfo=UTC),
        granted_at=datetime(2026, 8, 27, 11, 0, tzinfo=UTC),
        expires_at=datetime(2026, 8, 27, 11, 30, tzinfo=UTC),
        telemetry=telemetry,
    )

    governor.active_leases = (expired_lease,)

    selection = governor.select_llm_runtime("cuda", telemetry=telemetry)
    refreshed = governor.refresh_active_leases(now=telemetry.observed_at)

    assert selection.selected_device == "cuda"
    assert "HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE" not in selection.blockers
    assert refreshed == ()


def test_gpu_resource_governor_blocks_parallel_gpu_leases() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )
    active_lease = GpuLease(
        lease_id="active-lease",
        workload=GpuWorkloadKind.MODEL_TRAINING,
        lease_kind=GpuLeaseKind.TRAINING_GPU,
        compute_profile="TRAINING_GPU",
        device="cuda",
        state=GpuLeaseState.ACTIVE,
        issued_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        granted_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        telemetry=telemetry,
    )

    selection = governor.select_runtime(
        GpuWorkloadKind.BACKTEST_ACCELERATION,
        "cuda",
        telemetry=telemetry,
        active_leases=(active_lease,),
    )

    assert selection.selected_device == "cpu"
    assert selection.lease_state is GpuLeaseState.DENIED
    assert "HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE" in selection.blockers
    assert "BENCHMARK_BEFORE_PROMOTION" in selection.blockers
    assert (
        governor.select_backtest_runtime(
            "cuda", telemetry=telemetry, active_leases=(active_lease,)
        ).selected_device
        == "cpu"
    )


def test_backtest_gpu_requires_explicit_benchmark_approval() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    blocked = governor.select_backtest_runtime(
        "cuda",
        telemetry=telemetry,
    )
    approved = governor.select_backtest_runtime(
        "cuda",
        telemetry=telemetry,
        benchmark_approved=True,
    )

    assert blocked.selected_device == "cpu"
    assert blocked.lease_state is GpuLeaseState.DENIED
    assert "BENCHMARK_BEFORE_PROMOTION" in blocked.blockers
    assert blocked.benchmark_required is True
    assert blocked.benchmark_approved is False

    assert approved.selected_device == "cuda"
    assert approved.lease_state is GpuLeaseState.GRANTED
    assert approved.blockers == ()
    assert approved.benchmark_required is True
    assert approved.benchmark_approved is True
    assert (
        governor.issue_backtest_lease(
            "cuda",
            telemetry=telemetry,
            benchmark_approved=True,
            lease_id="backtest-lease-1",
        )
        is not None
    )


def test_gpu_circuit_breaker_blocks_and_recovers_gpu_access() -> None:
    breaker = GpuCircuitBreaker()
    governor = GpuResourceGovernor(circuit_breaker=breaker)
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    governor.record_gpu_failure(
        "CUDA_OOM",
        occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )
    governor.record_gpu_failure(
        "DRIVER_ERROR",
        occurred_at=datetime(2026, 8, 27, 12, 1, tzinfo=UTC),
    )

    blocked = governor.select_llm_runtime("cuda", telemetry=telemetry)
    blocker = governor.circuit_breaker
    assert blocker.state is GpuCircuitBreakerState.OPEN
    assert blocked.selected_device == "cpu"
    assert "GPU_CIRCUIT_BREAKER" in blocked.blockers

    governor.request_gpu_revalidation(now=datetime(2026, 8, 27, 12, 4, tzinfo=UTC))
    assert governor.circuit_breaker.state is GpuCircuitBreakerState.OPEN

    governor.request_gpu_revalidation(now=datetime(2026, 8, 27, 12, 6, tzinfo=UTC))
    state = cast(Any, governor.circuit_breaker.state)
    assert state == GpuCircuitBreakerState.HALF_OPEN

    probe = governor.select_llm_runtime("cuda", telemetry=telemetry)
    assert probe.selected_device == "cuda"
    assert probe.blockers == ()

    closed = governor.record_gpu_success(
        occurred_at=datetime(2026, 8, 27, 12, 6, tzinfo=UTC)
    )
    assert closed.state is GpuCircuitBreakerState.CLOSED
    assert closed.failure_count == 0


def test_gpu_telemetry_observation_feeds_the_breaker() -> None:
    governor = GpuResourceGovernor()
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=False,
        source=("unit-test",),
    )

    assert telemetry.governance_blockers(20) == ("CUDA_UNAVAILABLE",)
    assessment = telemetry.assess(20)
    assert isinstance(assessment, GpuTelemetryAssessment)
    assert assessment.healthy is False
    assert assessment.blockers == ("CUDA_UNAVAILABLE",)

    first = governor.observe_telemetry(telemetry)
    first_assessment = governor.last_telemetry_assessment
    second = governor.observe_telemetry(
        replace(
            telemetry,
            observed_at=datetime(2026, 8, 27, 12, 1, tzinfo=UTC),
        )
    )
    second_assessment = governor.last_telemetry_assessment

    assert first.state is GpuCircuitBreakerState.CLOSED
    assert first.failure_count == 1
    assert first_assessment == assessment
    assert second.state is GpuCircuitBreakerState.OPEN
    assert second.failure_count == 0
    assert second.last_reason == "CUDA_UNAVAILABLE"
    assert second_assessment is not None
    assert second_assessment.observed_at == datetime(2026, 8, 27, 12, 1, tzinfo=UTC)
    assert second_assessment.blockers == ("CUDA_UNAVAILABLE",)

    healthy = governor.observe_telemetry(
        GpuTelemetrySnapshot(
            observed_at=datetime(2026, 8, 27, 12, 7, tzinfo=UTC),
            cuda_available=True,
            device_name="RTX 4090",
            driver_version="550.40",
            total_vram_bytes=10 * 1024 * 1024 * 1024,
            free_vram_bytes=8 * 1024 * 1024 * 1024,
            active_gpu_processes=0,
            source=("unit-test",),
        )
    )

    assert healthy.state is GpuCircuitBreakerState.HALF_OPEN

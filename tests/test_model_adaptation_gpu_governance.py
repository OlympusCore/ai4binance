from __future__ import annotations

from datetime import UTC, datetime

from ai4binance.enterprise import (
    GpuLease,
    GpuLeaseKind,
    GpuLeaseState,
    GpuTelemetrySnapshot,
    GpuWorkloadKind,
)
from ai4binance.learning import (
    ModelAdaptationCandidate,
    ModelAdaptationMethod,
    select_model_adaptation_runtime,
)


def test_model_adaptation_runtime_uses_the_training_facade() -> None:
    candidate = ModelAdaptationCandidate(
        candidate_id="adaptation:001",
        method=ModelAdaptationMethod.LORA,
        base_model_ref="BASE_MODEL",
        dataset_ref="DATASET",
        evaluation_ref="EVALUATION",
        oos_evidence_ref="OOS",
        model_card_ref="MODEL_CARD",
        red_team_ref="RED_TEAM",
        risk_review_ref="RISK_REVIEW",
    )
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )

    decision = select_model_adaptation_runtime(
        candidate,
        "cuda",
        telemetry=telemetry,
        lease_id="training-lease-1",
    )

    assert decision.runtime_selection.workload is GpuWorkloadKind.MODEL_TRAINING
    assert decision.runtime_selection.selected_device == "cuda"
    assert decision.runtime_selection.lease_state is GpuLeaseState.GRANTED
    assert decision.telemetry_assessment is not None
    assert decision.telemetry_assessment.source_label == "unit-test"
    assert decision.telemetry_assessment.healthy is True
    assert decision.lease is not None
    assert decision.lease.lease_id == "training-lease-1"
    assert decision.lease.lease_kind is GpuLeaseKind.TRAINING_GPU
    assert decision.lease.device == "cuda"


def test_model_adaptation_runtime_blocks_parallel_llm_gpu_leases() -> None:
    candidate = ModelAdaptationCandidate(
        candidate_id="adaptation:002",
        method=ModelAdaptationMethod.PEFT,
        base_model_ref="BASE_MODEL",
        dataset_ref="DATASET",
        evaluation_ref="EVALUATION",
        oos_evidence_ref="OOS",
        model_card_ref="MODEL_CARD",
        red_team_ref="RED_TEAM",
        risk_review_ref="RISK_REVIEW",
    )
    telemetry = GpuTelemetrySnapshot(
        observed_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        cuda_available=True,
        total_vram_bytes=10 * 1024 * 1024 * 1024,
        free_vram_bytes=8 * 1024 * 1024 * 1024,
        source=("unit-test",),
    )
    active_llm_lease = GpuLease(
        lease_id="llm-lease",
        workload=GpuWorkloadKind.LLM_INFERENCE,
        lease_kind=GpuLeaseKind.LLM_GPU,
        compute_profile="LLM_INFERENCE_GPU",
        device="cuda",
        state=GpuLeaseState.ACTIVE,
        issued_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        granted_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        telemetry=telemetry,
    )

    decision = select_model_adaptation_runtime(
        candidate,
        "cuda",
        telemetry=telemetry,
        active_leases=(active_llm_lease,),
    )

    assert decision.runtime_selection.selected_device == "cpu"
    assert (
        "HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE" in decision.runtime_selection.blockers
    )
    assert decision.telemetry_assessment is not None
    assert decision.telemetry_assessment.source_label == "unit-test"
    assert decision.lease is None

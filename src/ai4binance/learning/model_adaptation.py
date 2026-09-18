"""Governance board for PEFT, LoRA and QLoRA research candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise import (
    GpuLease,
    GpuResourceGovernor,
    GpuRuntimeSelection,
    GpuTelemetryAssessment,
    GpuTelemetrySnapshot,
    GpuWorkloadKind,
)


class ModelAdaptationMethod(StrEnum):
    PEFT = "PEFT"
    LORA = "LORA"
    QLORA = "QLORA"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _optional_ref_missing(name: str, value: str | None) -> str | None:
    if value is None or not value.strip():
        return f"MODEL_ADAPTATION_{name}_MISSING"
    return None


@dataclass(frozen=True, slots=True)
class ModelAdaptationCandidate:
    candidate_id: str
    method: ModelAdaptationMethod
    base_model_ref: str
    dataset_ref: str | None
    evaluation_ref: str | None
    oos_evidence_ref: str | None
    model_card_ref: str | None
    red_team_ref: str | None
    risk_review_ref: str | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("model adaptation candidate id", self.candidate_id)
        _require_text("model adaptation base model ref", self.base_model_ref)
        if self.method not in ModelAdaptationMethod:
            raise ValueError("model adaptation method is invalid")
        if self.execution_allowed:
            raise ValueError("model adaptation candidate cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError(
                "model adaptation candidate cannot promote production state"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("model adaptation candidate must remain live blocked")


@dataclass(frozen=True, slots=True)
class ModelAdaptationAssessment:
    candidate_id: str
    method: ModelAdaptationMethod
    blockers: tuple[str, ...]
    required_reviews: tuple[str, ...]
    recommendation: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("model adaptation assessment candidate id", self.candidate_id)
        if self.method not in ModelAdaptationMethod:
            raise ValueError("model adaptation assessment method is invalid")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("model adaptation blockers cannot contain blanks")
        if any(not review.strip() for review in self.required_reviews):
            raise ValueError("model adaptation reviews cannot contain blanks")
        if self.execution_allowed:
            raise ValueError("model adaptation assessment cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError(
                "model adaptation assessment cannot promote production state"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("model adaptation assessment must remain live blocked")


@dataclass(frozen=True, slots=True)
class ModelAdaptationRuntimeDecision:
    candidate_id: str
    method: ModelAdaptationMethod
    runtime_selection: GpuRuntimeSelection
    lease: GpuLease | None = None
    telemetry_assessment: GpuTelemetryAssessment | None = None

    def __post_init__(self) -> None:
        _require_text("model adaptation runtime candidate id", self.candidate_id)
        if self.method not in ModelAdaptationMethod:
            raise ValueError("model adaptation runtime method is invalid")
        if self.runtime_selection.workload is not GpuWorkloadKind.MODEL_TRAINING:
            raise ValueError("model adaptation runtime must use the training workload")
        if self.lease is not None:
            if self.lease.workload is not GpuWorkloadKind.MODEL_TRAINING:
                raise ValueError("model adaptation runtime lease must use training")
            if self.lease.device != self.runtime_selection.selected_device:
                raise ValueError("model adaptation runtime lease must match device")
        if self.runtime_selection.selected_device == "cuda" and self.lease is None:
            raise ValueError("cuda training runtime must carry a lease")


def assess_model_adaptation_candidate(
    candidate: ModelAdaptationCandidate,
) -> ModelAdaptationAssessment:
    evidence_blockers = tuple(
        blocker
        for blocker in (
            _optional_ref_missing("DATASET_REF", candidate.dataset_ref),
            _optional_ref_missing("EVALUATION_REF", candidate.evaluation_ref),
            _optional_ref_missing("OOS_EVIDENCE_REF", candidate.oos_evidence_ref),
            _optional_ref_missing("MODEL_CARD_REF", candidate.model_card_ref),
            _optional_ref_missing("RED_TEAM_REF", candidate.red_team_ref),
            _optional_ref_missing("RISK_REVIEW_REF", candidate.risk_review_ref),
        )
        if blocker is not None
    )
    blockers = (*evidence_blockers, "LIVE_ORDER_BLOCKED")
    reviews = (
        "DATASET_LINEAGE_REVIEW",
        "OOS_EVALUATION_REVIEW",
        "RED_TEAM_AND_SAFETY_REVIEW",
        "QUALITY_DEPARTMENT_REVIEW",
    )
    recommendation = "RESEARCH_ONLY" if evidence_blockers else "STAGED_CANDIDATE"
    return ModelAdaptationAssessment(
        candidate_id=candidate.candidate_id,
        method=candidate.method,
        blockers=blockers,
        required_reviews=reviews,
        recommendation=recommendation,
    )


def select_model_adaptation_runtime(
    candidate: ModelAdaptationCandidate,
    preferred_device: str,
    *,
    governor: GpuResourceGovernor | None = None,
    telemetry: GpuTelemetrySnapshot | None = None,
    active_leases: tuple[GpuLease, ...] | None = None,
    lease_id: str | None = None,
) -> ModelAdaptationRuntimeDecision:
    governor = governor or GpuResourceGovernor()
    selection = governor.select_training_runtime(
        preferred_device,
        telemetry=telemetry,
        active_leases=active_leases,
    )
    lease = None
    if selection.selected_device == "cuda":
        lease = governor.issue_training_lease(
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            lease_id=lease_id,
        )
    return ModelAdaptationRuntimeDecision(
        candidate_id=candidate.candidate_id,
        method=candidate.method,
        runtime_selection=selection,
        lease=lease,
        telemetry_assessment=governor.last_telemetry_assessment,
    )

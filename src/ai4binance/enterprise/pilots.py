"""Shadow and paper pilot readiness contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai4binance.enterprise.contracts import WorkflowIdentity


class PilotStage(StrEnum):
    SHADOW = "SHADOW"
    PAPER_SOAK = "PAPER_SOAK"


@dataclass(frozen=True, slots=True)
class PilotReadinessReport:
    identity: WorkflowIdentity
    pilot_id: str
    stage: PilotStage
    candidate_ref: str
    required_evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    order_intent: str = "NONE"
    portfolio_mutation: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.pilot_id.strip() or not self.candidate_ref.strip():
            raise ValueError("pilot readiness identity is required")
        _require_unique("pilot evidence refs", self.required_evidence_refs)
        _require_unique("pilot blockers", self.blockers)
        if not self.required_evidence_refs:
            raise ValueError("pilot readiness requires evidence")
        if self.order_intent != "NONE":
            raise ValueError("pilot readiness cannot create order intent")
        if self.portfolio_mutation:
            raise ValueError("pilot readiness cannot mutate portfolio")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("pilot readiness cannot promote production state")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("pilot readiness cannot authorize execution")
        if self.stage is PilotStage.PAPER_SOAK and "USER_APPROVAL_REQUIRED" not in (
            self.blockers
        ):
            raise ValueError("paper soak readiness requires user approval blocker")


def build_shadow_readiness(
    identity: WorkflowIdentity,
    *,
    pilot_id: str,
    candidate_ref: str,
    evidence_refs: tuple[str, ...],
) -> PilotReadinessReport:
    return PilotReadinessReport(
        identity=identity,
        pilot_id=pilot_id,
        stage=PilotStage.SHADOW,
        candidate_ref=candidate_ref,
        required_evidence_refs=evidence_refs,
        blockers=("LIVE_ORDER_BLOCKED",),
    )


def build_paper_soak_readiness(
    identity: WorkflowIdentity,
    *,
    pilot_id: str,
    candidate_ref: str,
    evidence_refs: tuple[str, ...],
) -> PilotReadinessReport:
    return PilotReadinessReport(
        identity=identity,
        pilot_id=pilot_id,
        stage=PilotStage.PAPER_SOAK,
        candidate_ref=candidate_ref,
        required_evidence_refs=evidence_refs,
        blockers=("USER_APPROVAL_REQUIRED", "LIVE_ORDER_BLOCKED"),
    )


def write_pilot_readiness_artifact(report: PilotReadinessReport, path: Path) -> Path:
    """Persist a pilot readiness report as a local production artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report_to_payload(report), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def report_to_payload(report: PilotReadinessReport) -> dict[str, object]:
    return {
        "identity": {
            "work_order_id": report.identity.work_order_id,
            "run_id": report.identity.run_id,
            "trace_id": report.identity.trace_id,
            "created_at": report.identity.created_at.isoformat(),
            "snapshot_id": report.identity.snapshot_id,
        },
        "pilot_id": report.pilot_id,
        "stage": report.stage.value,
        "candidate_ref": report.candidate_ref,
        "required_evidence_refs": list(report.required_evidence_refs),
        "blockers": list(report.blockers),
        "order_intent": report.order_intent,
        "portfolio_mutation": report.portfolio_mutation,
        "execution_allowed": report.execution_allowed,
        "promotion_status": report.promotion_status,
        "live_eligibility_status": report.live_eligibility_status,
    }


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

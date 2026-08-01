"""Shadow and paper pilot readiness contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

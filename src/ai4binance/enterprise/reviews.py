"""Periodic learning and promotion review cadence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity


class ReviewCadence(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMIANNUAL = "SEMIANNUAL"
    INCIDENT_TRIGGERED = "INCIDENT_TRIGGERED"


class ReviewOutcome(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED"
    EXPERIMENT_PROPOSAL = "EXPERIMENT_PROPOSAL"
    BACKTEST_REQUIRED = "BACKTEST_REQUIRED"
    CAPA_REQUIRED = "CAPA_REQUIRED"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    CONTINUE_RESEARCH = "CONTINUE_RESEARCH"
    SHADOW_CANDIDATE = "SHADOW_CANDIDATE"
    PAPER_SOAK_CANDIDATE = "PAPER_SOAK_CANDIDATE"
    KEEP_CURRENT_CHAMPION = "KEEP_CURRENT_CHAMPION"
    RETIRE_CANDIDATE = "RETIRE_CANDIDATE"
    APPROVE_EXTENDED_PAPER_SOAK = "APPROVE_EXTENDED_PAPER_SOAK"
    READY_FOR_USER_PROMOTION_APPROVAL = "READY_FOR_USER_PROMOTION_APPROVAL"
    ARCHITECTURE_REVIEW_REQUIRED = "ARCHITECTURE_REVIEW_REQUIRED"


_ALLOWED_OUTCOMES = {
    ReviewCadence.MONTHLY: {
        ReviewOutcome.NO_CHANGE,
        ReviewOutcome.INVESTIGATION_REQUIRED,
        ReviewOutcome.EXPERIMENT_PROPOSAL,
        ReviewOutcome.BACKTEST_REQUIRED,
        ReviewOutcome.CAPA_REQUIRED,
    },
    ReviewCadence.QUARTERLY: {
        ReviewOutcome.REJECT_CANDIDATE,
        ReviewOutcome.CONTINUE_RESEARCH,
        ReviewOutcome.SHADOW_CANDIDATE,
        ReviewOutcome.PAPER_SOAK_CANDIDATE,
    },
    ReviewCadence.SEMIANNUAL: {
        ReviewOutcome.KEEP_CURRENT_CHAMPION,
        ReviewOutcome.RETIRE_CANDIDATE,
        ReviewOutcome.APPROVE_EXTENDED_PAPER_SOAK,
        ReviewOutcome.READY_FOR_USER_PROMOTION_APPROVAL,
        ReviewOutcome.ARCHITECTURE_REVIEW_REQUIRED,
    },
    ReviewCadence.INCIDENT_TRIGGERED: {
        ReviewOutcome.INVESTIGATION_REQUIRED,
        ReviewOutcome.CAPA_REQUIRED,
        ReviewOutcome.ARCHITECTURE_REVIEW_REQUIRED,
    },
}


@dataclass(frozen=True, slots=True)
class PeriodicReviewRecord:
    identity: WorkflowIdentity
    review_id: str
    cadence: ReviewCadence
    owner_department_id: DepartmentId
    subject_ref: str
    outcome: ReviewOutcome
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ("PRODUCTION_MUTATION_BLOCKED",)
    production_mutation_allowed: bool = False
    user_approval_required: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.review_id.strip() or not self.subject_ref.strip():
            raise ValueError("periodic review identity is required")
        _require_unique("periodic review evidence refs", self.evidence_refs)
        _require_unique("periodic review blockers", self.blockers)
        if self.outcome not in _ALLOWED_OUTCOMES[self.cadence]:
            raise ValueError("periodic review outcome is outside cadence")
        if self.production_mutation_allowed:
            raise ValueError("periodic review cannot mutate production")
        if not self.user_approval_required:
            raise ValueError("periodic review requires user approval")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("periodic review cannot promote production state")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("periodic review cannot authorize execution")


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

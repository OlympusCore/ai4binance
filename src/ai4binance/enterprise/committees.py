"""Workflow-template committees for enterprise governance decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity


class CommitteeId(StrEnum):
    EXECUTIVE_MANAGEMENT = "EXECUTIVE_MANAGEMENT"
    INVESTMENT_RISK = "INVESTMENT_RISK"
    TECHNOLOGY_CHANGE_ADVISORY = "TECHNOLOGY_CHANGE_ADVISORY"
    MODEL_PARAMETER_PROMOTION = "MODEL_PARAMETER_PROMOTION"
    QUALITY_AUDIT_REVIEW = "QUALITY_AUDIT_REVIEW"


class CommitteeOutcome(StrEnum):
    NO_TRADE = "NO_TRADE"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    WATCHLIST = "WATCHLIST"
    WAIT_FOR_RETEST = "WAIT_FOR_RETEST"
    PAPER_CANDIDATE = "PAPER_CANDIDATE"
    MANUAL_PLAN = "MANUAL_PLAN"
    LIVE_ORDER_BLOCKED = "LIVE_ORDER_BLOCKED"
    REJECT_CHANGE = "REJECT_CHANGE"
    REVISE_CHANGE = "REVISE_CHANGE"
    SANDBOX_APPROVED = "SANDBOX_APPROVED"
    TEST_APPROVED = "TEST_APPROVED"
    READY_FOR_USER_APPROVAL = "READY_FOR_USER_APPROVAL"
    CHALLENGER = "CHALLENGER"
    SHADOW_APPROVED = "SHADOW_APPROVED"
    PAPER_SOAK_APPROVED = "PAPER_SOAK_APPROVED"
    PROMOTION_REJECTED = "PROMOTION_REJECTED"


@dataclass(frozen=True, slots=True)
class CommitteeTemplate:
    committee_id: CommitteeId
    participant_departments: tuple[DepartmentId, ...]
    allowed_outcomes: tuple[CommitteeOutcome, ...]
    user_approval_required_for_material_change: bool = True
    persistent_agent: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if len(self.participant_departments) < 2:
            raise ValueError("committee requires at least two departments")
        if len(set(self.participant_departments)) != len(self.participant_departments):
            raise ValueError("committee participants must be unique")
        if not self.allowed_outcomes:
            raise ValueError("committee requires allowed outcomes")
        if len(set(self.allowed_outcomes)) != len(self.allowed_outcomes):
            raise ValueError("committee outcomes must be unique")
        if not self.user_approval_required_for_material_change:
            raise ValueError("committee material changes require user approval")
        if self.persistent_agent:
            raise ValueError("committee must be a workflow template, not an agent")
        _require_fail_closed(self.execution_allowed, self.live_eligibility_status)


@dataclass(frozen=True, slots=True)
class CommitteeDecision:
    identity: WorkflowIdentity
    committee_id: CommitteeId
    decision_id: str
    subject_ref: str
    outcome: CommitteeOutcome
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",)
    user_approval_required: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.subject_ref.strip():
            raise ValueError("committee decision identity is required")
        _require_unique("committee decision evidence refs", self.evidence_refs)
        _require_unique("committee decision blockers", self.blockers)
        if not self.user_approval_required:
            raise ValueError("committee decision requires user approval")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("committee decision cannot promote production state")
        _require_fail_closed(self.execution_allowed, self.live_eligibility_status)


@dataclass(frozen=True, slots=True)
class CommitteeRegistry:
    templates: tuple[CommitteeTemplate, ...]
    _by_id: Mapping[CommitteeId, CommitteeTemplate] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.templates) != len(CommitteeId):
            raise ValueError("committee registry must cover every committee")
        by_id = {item.committee_id: item for item in self.templates}
        if len(by_id) != len(self.templates):
            raise ValueError("committee IDs must be unique")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def get(self, committee_id: CommitteeId) -> CommitteeTemplate:
        return self._by_id[committee_id]

    def validate_decision(self, decision: CommitteeDecision) -> CommitteeDecision:
        template = self.get(decision.committee_id)
        if decision.outcome not in template.allowed_outcomes:
            raise ValueError("committee decision outcome is outside template")
        return decision


def build_default_committee_registry() -> CommitteeRegistry:
    return CommitteeRegistry(
        (
            CommitteeTemplate(
                CommitteeId.EXECUTIVE_MANAGEMENT,
                (
                    DepartmentId.EXECUTIVE_OFFICE,
                    DepartmentId.SOFTWARE_ENGINEERING,
                    DepartmentId.QUALITY_AUDIT,
                    DepartmentId.MULTI_OPS,
                ),
                (
                    CommitteeOutcome.RESEARCH_ONLY,
                    CommitteeOutcome.REVISE_CHANGE,
                    CommitteeOutcome.READY_FOR_USER_APPROVAL,
                ),
            ),
            CommitteeTemplate(
                CommitteeId.INVESTMENT_RISK,
                (
                    DepartmentId.TRADER,
                    DepartmentId.FINANCE_PORTFOLIO,
                    DepartmentId.MARKET_INTELLIGENCE,
                    DepartmentId.RISK_VALIDATION,
                    DepartmentId.QUALITY_AUDIT,
                ),
                (
                    CommitteeOutcome.NO_TRADE,
                    CommitteeOutcome.RESEARCH_ONLY,
                    CommitteeOutcome.WATCHLIST,
                    CommitteeOutcome.WAIT_FOR_RETEST,
                    CommitteeOutcome.PAPER_CANDIDATE,
                    CommitteeOutcome.MANUAL_PLAN,
                    CommitteeOutcome.LIVE_ORDER_BLOCKED,
                ),
            ),
            CommitteeTemplate(
                CommitteeId.TECHNOLOGY_CHANGE_ADVISORY,
                (
                    DepartmentId.SOFTWARE_ENGINEERING,
                    DepartmentId.RESEARCH_DEVELOPMENT,
                    DepartmentId.QUALITY_AUDIT,
                    DepartmentId.MULTI_OPS,
                    DepartmentId.RISK_VALIDATION,
                ),
                (
                    CommitteeOutcome.REJECT_CHANGE,
                    CommitteeOutcome.REVISE_CHANGE,
                    CommitteeOutcome.SANDBOX_APPROVED,
                    CommitteeOutcome.TEST_APPROVED,
                    CommitteeOutcome.READY_FOR_USER_APPROVAL,
                ),
            ),
            CommitteeTemplate(
                CommitteeId.MODEL_PARAMETER_PROMOTION,
                (
                    DepartmentId.RESEARCH_DEVELOPMENT,
                    DepartmentId.MULTI_OPS,
                    DepartmentId.QUALITY_AUDIT,
                    DepartmentId.RISK_VALIDATION,
                    DepartmentId.TRADER,
                ),
                (
                    CommitteeOutcome.RESEARCH_ONLY,
                    CommitteeOutcome.CHALLENGER,
                    CommitteeOutcome.SHADOW_APPROVED,
                    CommitteeOutcome.PAPER_SOAK_APPROVED,
                    CommitteeOutcome.PROMOTION_REJECTED,
                    CommitteeOutcome.READY_FOR_USER_APPROVAL,
                ),
            ),
            CommitteeTemplate(
                CommitteeId.QUALITY_AUDIT_REVIEW,
                (
                    DepartmentId.QUALITY_AUDIT,
                    DepartmentId.MULTI_OPS,
                    DepartmentId.RISK_VALIDATION,
                    DepartmentId.EXECUTIVE_OFFICE,
                ),
                (
                    CommitteeOutcome.RESEARCH_ONLY,
                    CommitteeOutcome.REVISE_CHANGE,
                    CommitteeOutcome.READY_FOR_USER_APPROVAL,
                ),
            ),
        )
    )


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_fail_closed(
    execution_allowed: bool,
    live_eligibility_status: str,
) -> None:
    if execution_allowed or live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError("committee contract cannot authorize execution")

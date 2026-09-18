"""Dependency-neutral contracts for governed virtual-market evaluation."""

from __future__ import annotations

from dataclasses import dataclass

DGE_APPROVED_PAPER_ONLY = "APPROVED_PAPER_ONLY"
DGE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
DGE_EVALUATION_FAILED = "DGE_EVALUATION_FAILED"
DGE_EVALUATION_UNAVAILABLE = "DGE_EVALUATION_UNAVAILABLE"
DGE_SIMULATION_NOT_APPROVED = "DGE_SIMULATION_NOT_APPROVED"


@dataclass(frozen=True, slots=True)
class VirtualGovernanceResult:
    """Application-facing result from one deterministic governance evaluation."""

    decision_id: str
    status: str
    blockers: tuple[str, ...]
    simulation_allowed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.status.strip():
            raise ValueError("virtual governance result identity is required")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("virtual governance result blockers cannot be blank")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("virtual governance result blockers must be unique")
        if not isinstance(self.simulation_allowed, bool):
            raise ValueError("virtual governance simulation allowance must be boolean")
        if self.simulation_allowed and self.status != DGE_APPROVED_PAPER_ONLY:
            raise ValueError(
                "virtual governance simulation requires approved paper-only status"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual governance result cannot authorize live execution"
            )

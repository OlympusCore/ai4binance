"""Durable-style governed run state with sticky blockers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

_TERMINAL = {"COMPLETED", "BLOCKED", "FAILED"}
_STICKY_BLOCKERS = {"HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"}


class GovernedRunStatus(StrEnum):
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(slots=True)
class GovernedRunState:
    run_id: str
    project: str
    current_step: str = "received"
    status: GovernedRunStatus = GovernedRunStatus.RECEIVED
    step_count: int = 0
    max_steps: int = 12
    evidence_hashes: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    checkpoint_id: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.project.strip():
            raise ValueError("governed run identity is required")
        if not 1 <= self.max_steps <= 100:
            raise ValueError("governed run max_steps is invalid")
        if self.step_count < 0:
            raise ValueError("governed run step_count cannot be negative")
        if self.started_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("governed run timestamps must be timezone-aware")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("governed run cannot authorize trading")

    def transition(
        self,
        status: GovernedRunStatus,
        step: str,
        *,
        blockers: tuple[str, ...] = (),
        evidence_hashes: tuple[str, ...] | None = None,
    ) -> None:
        if self.status.value in _TERMINAL:
            raise RuntimeError("TERMINAL_GOVERNED_RUN_STATE")
        if not step.strip():
            raise ValueError("governed run step is required")
        next_count = self.step_count + 1
        if next_count > self.max_steps:
            self.status = GovernedRunStatus.BLOCKED
            self.current_step = "step_limit"
            self.blockers = _unique(
                (*self.blockers, "GOVERNED_RUN_STEP_LIMIT_EXCEEDED")
            )
            self.updated_at = datetime.now(UTC)
            raise RuntimeError("GOVERNED_RUN_STEP_LIMIT_EXCEEDED")
        sticky = tuple(item for item in self.blockers if item in _STICKY_BLOCKERS)
        self.step_count = next_count
        self.status = status
        self.current_step = step
        self.blockers = _unique((*self.blockers, *blockers, *sticky))
        if evidence_hashes is not None:
            self.evidence_hashes = _unique((*self.evidence_hashes, *evidence_hashes))
        self.updated_at = datetime.now(UTC)
        self.__post_init__()

    def bind_checkpoint(self, checkpoint_id: str) -> None:
        if not checkpoint_id.strip():
            raise ValueError("checkpoint identity is required")
        self.checkpoint_id = checkpoint_id
        self.updated_at = datetime.now(UTC)


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value.strip()))

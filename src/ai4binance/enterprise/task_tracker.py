"""Fail-closed enterprise task loop tracker."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise.contracts import TaskStatus


class TaskLoopStopReason(StrEnum):
    ITERATION_LIMIT = "TASK_LOOP_ITERATION_LIMIT_REACHED"
    REPEATED_ACTION = "TASK_LOOP_REPEATED_ACTION_BLOCKED"
    INCOMPLETE_STEPS = "TASK_LOOP_INCOMPLETE_STEPS"
    HUMAN_REVIEW = "HUMAN_REVIEW_REQUIRED"
    LIVE_BLOCKED = "LIVE_ORDER_BLOCKED"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class TaskLoopPolicy:
    max_iterations: int = 3
    max_repeated_actions: int = 1
    human_review_required: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("task loop max_iterations must be positive")
        if self.max_repeated_actions < 0:
            raise ValueError("task loop max_repeated_actions cannot be negative")
        if self.execution_allowed:
            raise ValueError("task loop policy cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("task loop policy cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("task loop policy must remain live blocked")


@dataclass(frozen=True, slots=True)
class TaskLoopStep:
    step_id: str
    description: str
    status: TaskStatus
    evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("task loop step id", self.step_id)
        _require_text("task loop step description", self.description)
        _require_unique_text("task loop step evidence refs", self.evidence_refs)
        _require_unique_text("task loop step blockers", self.blockers)
        if self.status not in TaskStatus:
            raise ValueError("task loop step status is invalid")


@dataclass(frozen=True, slots=True)
class TaskLoopReport:
    loop_id: str
    steps: tuple[TaskLoopStep, ...]
    iteration_count: int
    status: TaskStatus
    blockers: tuple[str, ...]
    next_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("task loop id", self.loop_id)
        if self.iteration_count < 0:
            raise ValueError("task loop iteration_count cannot be negative")
        _require_unique_text("task loop blockers", self.blockers)
        _require_unique_text("task loop next actions", self.next_actions)
        if self.status not in TaskStatus:
            raise ValueError("task loop report status is invalid")
        if self.status is TaskStatus.COMPLETED and self.blockers:
            raise ValueError("completed task loop cannot have blockers")
        if self.status is not TaskStatus.COMPLETED and not self.blockers:
            raise ValueError("unfinished task loop requires blockers")
        if self.execution_allowed:
            raise ValueError("task loop report cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("task loop report cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("task loop report must remain live blocked")


class EnterpriseTaskTracker:
    """Evaluate task progress without creating autonomous execution authority."""

    def __init__(self, policy: TaskLoopPolicy | None = None) -> None:
        self.policy = policy or TaskLoopPolicy()

    def evaluate(
        self,
        *,
        loop_id: str,
        steps: tuple[TaskLoopStep, ...],
        iteration_count: int,
        recent_action_ids: tuple[str, ...] = (),
    ) -> TaskLoopReport:
        blockers: list[str] = []
        next_actions: list[str] = []
        if not steps:
            blockers.append(TaskLoopStopReason.INCOMPLETE_STEPS.value)
            next_actions.append("Define at least one audited task step.")
        if iteration_count >= self.policy.max_iterations:
            blockers.append(TaskLoopStopReason.ITERATION_LIMIT.value)
            next_actions.append("Escalate repeated loop to human review.")
        repeated = _repeated_actions(
            recent_action_ids,
            max_repeated_actions=self.policy.max_repeated_actions,
        )
        if repeated:
            blockers.append(TaskLoopStopReason.REPEATED_ACTION.value)
            next_actions.append("Stop repeating the same action and revise the plan.")
        incomplete = tuple(
            step
            for step in steps
            if step.status not in {TaskStatus.COMPLETED, TaskStatus.REJECTED}
        )
        if incomplete:
            blockers.append(TaskLoopStopReason.INCOMPLETE_STEPS.value)
            next_actions.append("Complete or explicitly reject remaining steps.")
        blockers.extend(blocker for step in steps for blocker in step.blockers)
        if self.policy.human_review_required:
            blockers.append(TaskLoopStopReason.HUMAN_REVIEW.value)
            next_actions.append("Obtain independent human review before promotion.")
        blockers.append(TaskLoopStopReason.LIVE_BLOCKED.value)
        status = TaskStatus.COMPLETED if not blockers else TaskStatus.BLOCKED
        return TaskLoopReport(
            loop_id=loop_id,
            steps=steps,
            iteration_count=iteration_count,
            status=status,
            blockers=_stable_unique(tuple(blockers)),
            next_actions=_stable_unique(tuple(next_actions)),
        )


def _repeated_actions(
    action_ids: tuple[str, ...],
    *,
    max_repeated_actions: int,
) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    repeated: list[str] = []
    for action_id in action_ids:
        _require_text("task loop action id", action_id)
        counts[action_id] = counts.get(action_id, 0) + 1
        if counts[action_id] > max_repeated_actions:
            repeated.append(action_id)
    return _stable_unique(tuple(repeated))

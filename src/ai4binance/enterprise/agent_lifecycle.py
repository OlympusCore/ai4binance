"""Typed fail-closed lifecycle state machine for enterprise agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class AgentLifecycleState(StrEnum):
    IDLE = "IDLE"
    PERCEIVE = "PERCEIVE"
    REASON = "REASON"
    PLAN = "PLAN"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    HUMAN_CHECK = "HUMAN_CHECK"
    DONE = "DONE"
    ERROR = "ERROR"


class AgentLifecycleEvent(StrEnum):
    TASK_RECEIVED = "TASK_RECEIVED"
    CONTEXT_LOADED = "CONTEXT_LOADED"
    GOALS_IDENTIFIED = "GOALS_IDENTIFIED"
    STEPS_GENERATED = "STEPS_GENERATED"
    APPROVAL_NEEDED = "APPROVAL_NEEDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TOOL_CALLED = "TOOL_CALLED"
    RESULT_RECEIVED = "RESULT_RECEIVED"
    TASK_COMPLETE = "TASK_COMPLETE"
    TOOL_FAILED = "TOOL_FAILED"
    RETRY_REQUESTED = "RETRY_REQUESTED"
    RESET = "RESET"


class AgentLifecycleBlocker(StrEnum):
    INVALID_TRANSITION = "AGENT_LIFECYCLE_INVALID_TRANSITION"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    HUMAN_REJECTED = "AGENT_LIFECYCLE_HUMAN_REJECTED"
    RETRY_LIMIT_REACHED = "AGENT_LIFECYCLE_RETRY_LIMIT_REACHED"
    EVIDENCE_REQUIRED = "AGENT_LIFECYCLE_EVIDENCE_REQUIRED"
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
class AgentLifecyclePolicy:
    max_retries: int = 1
    human_check_required_before_tool: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("agent lifecycle max_retries cannot be negative")
        if self.execution_allowed:
            raise ValueError("agent lifecycle policy cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("agent lifecycle policy cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agent lifecycle policy must remain live blocked")


@dataclass(frozen=True, slots=True)
class AgentLifecycleTransition:
    from_state: AgentLifecycleState
    event: AgentLifecycleEvent
    to_state: AgentLifecycleState
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.from_state not in AgentLifecycleState:
            raise ValueError("agent lifecycle from_state is invalid")
        if self.event not in AgentLifecycleEvent:
            raise ValueError("agent lifecycle event is invalid")
        if self.to_state not in AgentLifecycleState:
            raise ValueError("agent lifecycle to_state is invalid")
        _require_unique_text("agent lifecycle evidence refs", self.evidence_refs)


@dataclass(frozen=True, slots=True)
class AgentLifecycleSnapshot:
    lifecycle_id: str
    state: AgentLifecycleState
    transitions: tuple[AgentLifecycleTransition, ...]
    retry_count: int = 0
    human_approved: bool = False
    blockers: tuple[str, ...] = (AgentLifecycleBlocker.LIVE_BLOCKED.value,)
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("agent lifecycle id", self.lifecycle_id)
        if self.state not in AgentLifecycleState:
            raise ValueError("agent lifecycle state is invalid")
        if self.retry_count < 0:
            raise ValueError("agent lifecycle retry_count cannot be negative")
        _require_unique_text("agent lifecycle blockers", self.blockers)
        if AgentLifecycleBlocker.LIVE_BLOCKED.value not in self.blockers:
            raise ValueError("agent lifecycle snapshot must remain live blocked")
        if self.execution_allowed:
            raise ValueError("agent lifecycle snapshot cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("agent lifecycle snapshot cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agent lifecycle snapshot must remain live blocked")


class AgentLifecycleStateMachine:
    """Apply only declared agent lifecycle transitions."""

    _TRANSITIONS: ClassVar[
        dict[tuple[AgentLifecycleState, AgentLifecycleEvent], AgentLifecycleState]
    ] = {
        (AgentLifecycleState.IDLE, AgentLifecycleEvent.TASK_RECEIVED): (
            AgentLifecycleState.PERCEIVE
        ),
        (AgentLifecycleState.PERCEIVE, AgentLifecycleEvent.CONTEXT_LOADED): (
            AgentLifecycleState.REASON
        ),
        (AgentLifecycleState.REASON, AgentLifecycleEvent.GOALS_IDENTIFIED): (
            AgentLifecycleState.PLAN
        ),
        (AgentLifecycleState.PLAN, AgentLifecycleEvent.STEPS_GENERATED): (
            AgentLifecycleState.ACT
        ),
        (AgentLifecycleState.ACT, AgentLifecycleEvent.APPROVAL_NEEDED): (
            AgentLifecycleState.HUMAN_CHECK
        ),
        (AgentLifecycleState.HUMAN_CHECK, AgentLifecycleEvent.APPROVED): (
            AgentLifecycleState.ACT
        ),
        (AgentLifecycleState.HUMAN_CHECK, AgentLifecycleEvent.REJECTED): (
            AgentLifecycleState.IDLE
        ),
        (AgentLifecycleState.ACT, AgentLifecycleEvent.TOOL_CALLED): (
            AgentLifecycleState.OBSERVE
        ),
        (AgentLifecycleState.OBSERVE, AgentLifecycleEvent.RESULT_RECEIVED): (
            AgentLifecycleState.REASON
        ),
        (AgentLifecycleState.REASON, AgentLifecycleEvent.TASK_COMPLETE): (
            AgentLifecycleState.DONE
        ),
        (AgentLifecycleState.ACT, AgentLifecycleEvent.TOOL_FAILED): (
            AgentLifecycleState.ERROR
        ),
        (AgentLifecycleState.OBSERVE, AgentLifecycleEvent.TOOL_FAILED): (
            AgentLifecycleState.ERROR
        ),
        (AgentLifecycleState.ERROR, AgentLifecycleEvent.RETRY_REQUESTED): (
            AgentLifecycleState.REASON
        ),
        (AgentLifecycleState.DONE, AgentLifecycleEvent.RESET): (
            AgentLifecycleState.IDLE
        ),
        (AgentLifecycleState.ERROR, AgentLifecycleEvent.RESET): (
            AgentLifecycleState.IDLE
        ),
    }

    def __init__(self, policy: AgentLifecyclePolicy | None = None) -> None:
        self.policy = policy or AgentLifecyclePolicy()

    def start(self, lifecycle_id: str) -> AgentLifecycleSnapshot:
        return AgentLifecycleSnapshot(
            lifecycle_id=lifecycle_id,
            state=AgentLifecycleState.IDLE,
            transitions=(),
        )

    def apply(
        self,
        snapshot: AgentLifecycleSnapshot,
        event: AgentLifecycleEvent,
        *,
        evidence_refs: tuple[str, ...],
    ) -> AgentLifecycleSnapshot:
        _require_unique_text("agent lifecycle event evidence refs", evidence_refs)
        target = self._TRANSITIONS.get((snapshot.state, event))
        if target is None:
            return self._blocked(
                snapshot,
                (
                    AgentLifecycleBlocker.INVALID_TRANSITION.value,
                    AgentLifecycleBlocker.LIVE_BLOCKED.value,
                ),
            )
        if event is AgentLifecycleEvent.TOOL_CALLED:
            approval_blockers = self._tool_call_blockers(snapshot, evidence_refs)
            if approval_blockers:
                return self._blocked(snapshot, approval_blockers)
        if event is AgentLifecycleEvent.RETRY_REQUESTED:
            retry_count = snapshot.retry_count + 1
            if retry_count > self.policy.max_retries:
                return self._blocked(
                    snapshot,
                    (
                        AgentLifecycleBlocker.RETRY_LIMIT_REACHED.value,
                        AgentLifecycleBlocker.LIVE_BLOCKED.value,
                    ),
                )
        else:
            retry_count = snapshot.retry_count
        human_approved = (
            True
            if event is AgentLifecycleEvent.APPROVED
            else False
            if event in {AgentLifecycleEvent.REJECTED, AgentLifecycleEvent.RESET}
            else snapshot.human_approved
        )
        blockers: tuple[str, ...] = (AgentLifecycleBlocker.LIVE_BLOCKED.value,)
        if event is AgentLifecycleEvent.REJECTED:
            blockers = (
                AgentLifecycleBlocker.HUMAN_REJECTED.value,
                AgentLifecycleBlocker.LIVE_BLOCKED.value,
            )
        transition = AgentLifecycleTransition(
            from_state=snapshot.state,
            event=event,
            to_state=target,
            evidence_refs=evidence_refs,
        )
        return AgentLifecycleSnapshot(
            lifecycle_id=snapshot.lifecycle_id,
            state=target,
            transitions=(*snapshot.transitions, transition),
            retry_count=retry_count,
            human_approved=human_approved,
            blockers=blockers,
        )

    def _tool_call_blockers(
        self,
        snapshot: AgentLifecycleSnapshot,
        evidence_refs: tuple[str, ...],
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.policy.human_check_required_before_tool and not snapshot.human_approved:
            blockers.append(AgentLifecycleBlocker.HUMAN_APPROVAL_REQUIRED.value)
        if not evidence_refs:
            blockers.append(AgentLifecycleBlocker.EVIDENCE_REQUIRED.value)
        blockers.append(AgentLifecycleBlocker.LIVE_BLOCKED.value)
        return _stable_unique(tuple(blockers)) if len(blockers) > 1 else ()

    def _blocked(
        self,
        snapshot: AgentLifecycleSnapshot,
        blockers: tuple[str, ...],
    ) -> AgentLifecycleSnapshot:
        return AgentLifecycleSnapshot(
            lifecycle_id=snapshot.lifecycle_id,
            state=snapshot.state,
            transitions=snapshot.transitions,
            retry_count=snapshot.retry_count,
            human_approved=snapshot.human_approved,
            blockers=_stable_unique(blockers),
        )

"""Bounded management-meeting state machine."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.enterprise.contracts import MeetingAgenda, MeetingState

_ORDER = (
    MeetingState.PREPARE,
    MeetingState.COLLECT_DEPARTMENT_BRIEFS,
    MeetingState.IDENTIFY_CONFLICTS,
    MeetingState.CHALLENGE_ROUND,
    MeetingState.RISK_AND_QUALITY_REVIEW,
    MeetingState.DECIDE,
    MeetingState.ASSIGN_ACTIONS,
    MeetingState.MONITOR,
    MeetingState.CLOSE_AND_REVIEW,
)


@dataclass(frozen=True, slots=True)
class MeetingTransition:
    meeting_id: str
    from_state: MeetingState
    to_state: MeetingState
    reason_codes: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.meeting_id.strip():
            raise ValueError("meeting transition identity is required")
        if not self.reason_codes:
            raise ValueError("meeting transition requires reasons")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("meeting transition cannot authorize execution")


@dataclass(frozen=True, slots=True)
class MeetingStateMachine:
    agenda: MeetingAgenda

    def next_state(self) -> MeetingState | None:
        index = _ORDER.index(self.agenda.state)
        if index == len(_ORDER) - 1:
            return None
        return _ORDER[index + 1]

    def transition_to(self, target: MeetingState) -> MeetingTransition:
        expected = self.next_state()
        if expected is None:
            raise ValueError("meeting is already closed")
        if target is not expected:
            raise ValueError("meeting state transition must be sequential")
        return MeetingTransition(
            meeting_id=self.agenda.meeting_id,
            from_state=self.agenda.state,
            to_state=target,
            reason_codes=("SEQUENTIAL_STATE_TRANSITION", "LIVE_ORDER_BLOCKED"),
        )

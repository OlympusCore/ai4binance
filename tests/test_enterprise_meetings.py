from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai4binance.enterprise.contracts import (
    DepartmentId,
    MeetingAgenda,
    MeetingState,
    WorkflowIdentity,
)
from ai4binance.enterprise.meetings import MeetingStateMachine, MeetingTransition

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def agenda(state: MeetingState = MeetingState.PREPARE) -> MeetingAgenda:
    return MeetingAgenda(
        identity(),
        "meeting-1",
        "technology-change-advisory-board",
        state,
        (
            DepartmentId.SOFTWARE_ENGINEERING,
            DepartmentId.QUALITY_AUDIT,
            DepartmentId.MULTI_OPS,
        ),
        ("Review enterprise governance slice.",),
        ("DecisionRecord", "ActionItem"),
    )


def test_meeting_state_machine_allows_only_sequential_transitions() -> None:
    machine = MeetingStateMachine(agenda())
    transition = machine.transition_to(MeetingState.COLLECT_DEPARTMENT_BRIEFS)

    assert transition.from_state is MeetingState.PREPARE
    assert transition.to_state is MeetingState.COLLECT_DEPARTMENT_BRIEFS
    assert transition.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_meeting_state_machine_rejects_skips_and_closed_meetings() -> None:
    with pytest.raises(ValueError, match="sequential"):
        MeetingStateMachine(agenda()).transition_to(MeetingState.DECIDE)
    with pytest.raises(ValueError, match="already closed"):
        MeetingStateMachine(agenda(MeetingState.CLOSE_AND_REVIEW)).transition_to(
            MeetingState.PREPARE
        )


def test_meeting_transition_cannot_authorize_execution() -> None:
    transition = MeetingStateMachine(agenda()).transition_to(
        MeetingState.COLLECT_DEPARTMENT_BRIEFS
    )

    with pytest.raises(ValueError, match="authorize"):
        replace(transition, execution_allowed=True)
    with pytest.raises(ValueError, match="requires reasons"):
        MeetingTransition(
            "meeting-1",
            MeetingState.PREPARE,
            MeetingState.COLLECT_DEPARTMENT_BRIEFS,
            (),
        )

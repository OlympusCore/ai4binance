from __future__ import annotations

import pytest

from ai4binance.enterprise.agent_lifecycle import (
    AgentLifecycleBlocker,
    AgentLifecycleEvent,
    AgentLifecyclePolicy,
    AgentLifecycleSnapshot,
    AgentLifecycleState,
    AgentLifecycleStateMachine,
    AgentLifecycleTransition,
)


def test_agent_lifecycle_happy_path_requires_human_check_and_stays_live_blocked() -> (
    None
):
    machine = AgentLifecycleStateMachine()
    snapshot = machine.start("life-1")

    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.TASK_RECEIVED,
        evidence_refs=("prompt-ref",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.CONTEXT_LOADED,
        evidence_refs=("context-packet",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.GOALS_IDENTIFIED,
        evidence_refs=("goals",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.STEPS_GENERATED,
        evidence_refs=("task-tracker",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.APPROVAL_NEEDED,
        evidence_refs=("approval-request",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.APPROVED,
        evidence_refs=("human-approval",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.TOOL_CALLED,
        evidence_refs=("tool-call-preview",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.RESULT_RECEIVED,
        evidence_refs=("tool-result",),
    )
    snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.TASK_COMPLETE,
        evidence_refs=("quality-opinion",),
    )

    assert snapshot.state is AgentLifecycleState.DONE
    assert snapshot.human_approved is True
    assert snapshot.blockers == (AgentLifecycleBlocker.LIVE_BLOCKED.value,)
    assert snapshot.execution_allowed is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert [transition.event for transition in snapshot.transitions] == [
        AgentLifecycleEvent.TASK_RECEIVED,
        AgentLifecycleEvent.CONTEXT_LOADED,
        AgentLifecycleEvent.GOALS_IDENTIFIED,
        AgentLifecycleEvent.STEPS_GENERATED,
        AgentLifecycleEvent.APPROVAL_NEEDED,
        AgentLifecycleEvent.APPROVED,
        AgentLifecycleEvent.TOOL_CALLED,
        AgentLifecycleEvent.RESULT_RECEIVED,
        AgentLifecycleEvent.TASK_COMPLETE,
    ]


def test_agent_lifecycle_blocks_tool_call_before_human_approval() -> None:
    machine = AgentLifecycleStateMachine()
    snapshot = machine.start("life-2")
    for event, evidence in (
        (AgentLifecycleEvent.TASK_RECEIVED, "prompt-ref"),
        (AgentLifecycleEvent.CONTEXT_LOADED, "context-packet"),
        (AgentLifecycleEvent.GOALS_IDENTIFIED, "goals"),
        (AgentLifecycleEvent.STEPS_GENERATED, "steps"),
    ):
        snapshot = machine.apply(snapshot, event, evidence_refs=(evidence,))

    blocked = machine.apply(
        snapshot,
        AgentLifecycleEvent.TOOL_CALLED,
        evidence_refs=("tool-call-preview",),
    )

    assert blocked.state is AgentLifecycleState.ACT
    assert AgentLifecycleBlocker.HUMAN_APPROVAL_REQUIRED.value in blocked.blockers
    assert AgentLifecycleBlocker.LIVE_BLOCKED.value in blocked.blockers
    assert blocked.transitions == snapshot.transitions


def test_agent_lifecycle_blocks_invalid_transition_and_retry_limit() -> None:
    machine = AgentLifecycleStateMachine(
        AgentLifecyclePolicy(max_retries=0, human_check_required_before_tool=False)
    )
    snapshot = machine.start("life-3")

    invalid = machine.apply(
        snapshot,
        AgentLifecycleEvent.TASK_COMPLETE,
        evidence_refs=("premature",),
    )

    assert invalid.state is AgentLifecycleState.IDLE
    assert AgentLifecycleBlocker.INVALID_TRANSITION.value in invalid.blockers

    for event, evidence in (
        (AgentLifecycleEvent.TASK_RECEIVED, "prompt-ref"),
        (AgentLifecycleEvent.CONTEXT_LOADED, "context-packet"),
        (AgentLifecycleEvent.GOALS_IDENTIFIED, "goals"),
        (AgentLifecycleEvent.STEPS_GENERATED, "steps"),
    ):
        snapshot = machine.apply(snapshot, event, evidence_refs=(evidence,))
    error_snapshot = machine.apply(
        snapshot,
        AgentLifecycleEvent.TOOL_FAILED,
        evidence_refs=("tool-failure",),
    )
    blocked_retry = machine.apply(
        error_snapshot,
        AgentLifecycleEvent.RETRY_REQUESTED,
        evidence_refs=("retry",),
    )

    assert error_snapshot.state is AgentLifecycleState.ERROR
    assert AgentLifecycleBlocker.RETRY_LIMIT_REACHED.value in blocked_retry.blockers


def test_agent_lifecycle_allows_retry_and_reset_after_error() -> None:
    machine = AgentLifecycleStateMachine(
        AgentLifecyclePolicy(max_retries=1, human_check_required_before_tool=False)
    )
    snapshot = machine.start("life-4")
    for event, evidence in (
        (AgentLifecycleEvent.TASK_RECEIVED, "prompt-ref"),
        (AgentLifecycleEvent.CONTEXT_LOADED, "context-packet"),
        (AgentLifecycleEvent.GOALS_IDENTIFIED, "goals"),
        (AgentLifecycleEvent.STEPS_GENERATED, "steps"),
        (AgentLifecycleEvent.TOOL_FAILED, "tool-failure"),
    ):
        snapshot = machine.apply(snapshot, event, evidence_refs=(evidence,))

    retry = machine.apply(
        snapshot,
        AgentLifecycleEvent.RETRY_REQUESTED,
        evidence_refs=("retry",),
    )
    reset = machine.apply(
        snapshot,
        AgentLifecycleEvent.RESET,
        evidence_refs=("reset",),
    )

    assert retry.state is AgentLifecycleState.REASON
    assert retry.retry_count == 1
    assert reset.state is AgentLifecycleState.IDLE
    assert reset.human_approved is False


def test_agent_lifecycle_rejected_human_check_returns_idle_with_blocker() -> None:
    machine = AgentLifecycleStateMachine()
    snapshot = machine.start("life-5")
    for event, evidence in (
        (AgentLifecycleEvent.TASK_RECEIVED, "prompt-ref"),
        (AgentLifecycleEvent.CONTEXT_LOADED, "context-packet"),
        (AgentLifecycleEvent.GOALS_IDENTIFIED, "goals"),
        (AgentLifecycleEvent.STEPS_GENERATED, "steps"),
        (AgentLifecycleEvent.APPROVAL_NEEDED, "approval-request"),
    ):
        snapshot = machine.apply(snapshot, event, evidence_refs=(evidence,))

    rejected = machine.apply(
        snapshot,
        AgentLifecycleEvent.REJECTED,
        evidence_refs=("human-rejection",),
    )

    assert rejected.state is AgentLifecycleState.IDLE
    assert rejected.human_approved is False
    assert AgentLifecycleBlocker.HUMAN_REJECTED.value in rejected.blockers


def test_agent_lifecycle_blocks_tool_call_without_evidence() -> None:
    machine = AgentLifecycleStateMachine()
    snapshot = machine.start("life-6")
    for event, evidence in (
        (AgentLifecycleEvent.TASK_RECEIVED, "prompt-ref"),
        (AgentLifecycleEvent.CONTEXT_LOADED, "context-packet"),
        (AgentLifecycleEvent.GOALS_IDENTIFIED, "goals"),
        (AgentLifecycleEvent.STEPS_GENERATED, "steps"),
        (AgentLifecycleEvent.APPROVAL_NEEDED, "approval-request"),
        (AgentLifecycleEvent.APPROVED, "human-approval"),
    ):
        snapshot = machine.apply(snapshot, event, evidence_refs=(evidence,))

    blocked = machine.apply(
        snapshot,
        AgentLifecycleEvent.TOOL_CALLED,
        evidence_refs=(),
    )

    assert blocked.state is AgentLifecycleState.ACT
    assert AgentLifecycleBlocker.EVIDENCE_REQUIRED.value in blocked.blockers


def test_agent_lifecycle_rejects_execution_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize execution"):
        AgentLifecyclePolicy(execution_allowed=True)


def test_agent_lifecycle_contracts_reject_unsafe_shapes() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        AgentLifecyclePolicy(max_retries=-1)
    with pytest.raises(ValueError, match="promote"):
        AgentLifecyclePolicy(promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="live blocked"):
        AgentLifecyclePolicy(live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="cannot be empty"):
        AgentLifecycleStateMachine().start("")
    with pytest.raises(ValueError, match="must be unique"):
        AgentLifecycleTransition(
            AgentLifecycleState.IDLE,
            AgentLifecycleEvent.TASK_RECEIVED,
            AgentLifecycleState.PERCEIVE,
            ("same", "same"),
        )
    with pytest.raises(ValueError, match="cannot contain blanks"):
        AgentLifecycleSnapshot(
            lifecycle_id="life-7",
            state=AgentLifecycleState.IDLE,
            transitions=(),
            blockers=("", AgentLifecycleBlocker.LIVE_BLOCKED.value),
        )
    with pytest.raises(ValueError, match="must remain live blocked"):
        AgentLifecycleSnapshot(
            lifecycle_id="life-8",
            state=AgentLifecycleState.IDLE,
            transitions=(),
            blockers=("ONLY_INTERNAL_BLOCKER",),
        )
    with pytest.raises(ValueError, match="cannot promote"):
        AgentLifecycleSnapshot(
            lifecycle_id="life-9",
            state=AgentLifecycleState.IDLE,
            transitions=(),
            promotion_status="LIVE_ELIGIBLE",
        )

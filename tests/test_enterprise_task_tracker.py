from __future__ import annotations

import pytest

from ai4binance.enterprise.contracts import TaskStatus
from ai4binance.enterprise.task_tracker import (
    EnterpriseTaskTracker,
    TaskLoopPolicy,
    TaskLoopReport,
    TaskLoopStep,
)


def test_task_tracker_stops_repeated_incomplete_loop_fail_closed() -> None:
    tracker = EnterpriseTaskTracker(TaskLoopPolicy(max_iterations=2))
    step = TaskLoopStep(
        step_id="inspect",
        description="Inspect current modules",
        status=TaskStatus.IN_PROGRESS,
        evidence_refs=("src:enterprise",),
    )

    report = tracker.evaluate(
        loop_id="loop-1",
        steps=(step,),
        iteration_count=2,
        recent_action_ids=("inspect", "inspect"),
    )

    assert report.status is TaskStatus.BLOCKED
    assert "TASK_LOOP_ITERATION_LIMIT_REACHED" in report.blockers
    assert "TASK_LOOP_REPEATED_ACTION_BLOCKED" in report.blockers
    assert "TASK_LOOP_INCOMPLETE_STEPS" in report.blockers
    assert "HUMAN_REVIEW_REQUIRED" in report.blockers
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_task_tracker_rejects_execution_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize execution"):
        TaskLoopPolicy(execution_allowed=True)

    with pytest.raises(ValueError, match="cannot authorize execution"):
        TaskLoopReport(
            loop_id="loop",
            steps=(
                TaskLoopStep(
                    step_id="done",
                    description="Done",
                    status=TaskStatus.COMPLETED,
                ),
            ),
            iteration_count=1,
            status=TaskStatus.BLOCKED,
            blockers=("LIVE_ORDER_BLOCKED",),
            next_actions=("Review",),
            execution_allowed=True,
        )


def test_task_tracker_flags_empty_steps_and_keeps_live_block() -> None:
    tracker = EnterpriseTaskTracker(TaskLoopPolicy(human_review_required=False))

    report = tracker.evaluate(
        loop_id="loop-empty",
        steps=(),
        iteration_count=0,
        recent_action_ids=(),
    )

    assert report.status is TaskStatus.BLOCKED
    assert "TASK_LOOP_INCOMPLETE_STEPS" in report.blockers
    assert "LIVE_ORDER_BLOCKED" in report.blockers
    assert "Define at least one audited task step." in report.next_actions


def test_task_tracker_contracts_reject_invalid_policy_step_report_and_actions() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        TaskLoopPolicy(max_iterations=0)

    with pytest.raises(ValueError, match="cannot be negative"):
        TaskLoopPolicy(max_repeated_actions=-1)

    with pytest.raises(ValueError, match="cannot promote production state"):
        TaskLoopPolicy(promotion_status="STAGED_CANDIDATE")

    with pytest.raises(ValueError, match="must remain live blocked"):
        TaskLoopPolicy(live_eligibility_status="READY")

    with pytest.raises(ValueError, match="cannot be empty"):
        TaskLoopStep(step_id="", description="inspect", status=TaskStatus.QUEUED)

    with pytest.raises(ValueError, match="cannot contain blanks"):
        TaskLoopStep(
            step_id="s1",
            description="inspect",
            status=TaskStatus.QUEUED,
            evidence_refs=("",),
        )

    valid_step = TaskLoopStep(
        step_id="s2",
        description="inspect",
        status=TaskStatus.COMPLETED,
    )

    with pytest.raises(ValueError, match="cannot have blockers"):
        TaskLoopReport(
            loop_id="loop-complete",
            steps=(valid_step,),
            iteration_count=1,
            status=TaskStatus.COMPLETED,
            blockers=("LIVE_ORDER_BLOCKED",),
            next_actions=("None",),
        )

    with pytest.raises(ValueError, match="requires blockers"):
        TaskLoopReport(
            loop_id="loop-blocked",
            steps=(valid_step,),
            iteration_count=1,
            status=TaskStatus.BLOCKED,
            blockers=(),
            next_actions=("Review",),
        )

    tracker = EnterpriseTaskTracker()
    with pytest.raises(ValueError, match="cannot be empty"):
        tracker.evaluate(
            loop_id="loop-actions",
            steps=(valid_step,),
            iteration_count=0,
            recent_action_ids=("",),
        )

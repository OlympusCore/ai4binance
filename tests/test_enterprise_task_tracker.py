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

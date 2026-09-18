from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai4binance.governance import GovernedRunState, GovernedRunStatus


def test_governed_run_state_preserves_sticky_blockers_and_evidence() -> None:
    state = GovernedRunState("run-1", "ai4binance", max_steps=3)
    state.transition(
        GovernedRunStatus.RUNNING,
        "analysis",
        blockers=("OOS_EVIDENCE_INCOMPLETE",),
        evidence_hashes=("a" * 64,),
    )

    assert state.step_count == 1
    assert state.current_step == "analysis"
    assert "HUMAN_REVIEW_REQUIRED" in state.blockers
    assert "LIVE_ORDER_BLOCKED" in state.blockers
    assert state.evidence_hashes == ("a" * 64,)
    assert state.execution_allowed is False
    assert state.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_governed_run_state_blocks_terminal_and_step_limit() -> None:
    state = GovernedRunState("run-1", "ai4binance", max_steps=1)
    state.transition(GovernedRunStatus.COMPLETED, "done")
    with pytest.raises(RuntimeError, match="TERMINAL"):
        state.transition(GovernedRunStatus.RUNNING, "again")

    limited = GovernedRunState("run-2", "ai4binance", max_steps=1)
    limited.transition(GovernedRunStatus.RUNNING, "one")
    with pytest.raises(RuntimeError, match="STEP_LIMIT"):
        limited.transition(GovernedRunStatus.RUNNING, "two")
    assert limited.status is GovernedRunStatus.BLOCKED


def test_governed_run_state_contracts_reject_authority_drift() -> None:
    with pytest.raises(ValueError, match="identity"):
        GovernedRunState("", "ai4binance")
    with pytest.raises(ValueError, match="cannot authorize"):
        GovernedRunState("run", "ai4binance", execution_allowed=True)
    with pytest.raises(ValueError, match="timezone"):
        GovernedRunState(
            "run",
            "ai4binance",
            started_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="max_steps"):
        GovernedRunState("run", "ai4binance", max_steps=0)
    with pytest.raises(ValueError, match="step_count"):
        GovernedRunState("run", "ai4binance", step_count=-1)
    state = GovernedRunState("run", "ai4binance")
    with pytest.raises(ValueError, match="step"):
        state.transition(GovernedRunStatus.RUNNING, " ")
    with pytest.raises(ValueError, match="checkpoint"):
        state.bind_checkpoint(" ")
    state.bind_checkpoint("checkpoint-1")
    assert state.checkpoint_id == "checkpoint-1"

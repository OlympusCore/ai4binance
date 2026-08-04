from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.agents import (
    AgentTrajectoryReviewConfig,
    AgentTrajectorySignal,
    AgentTrajectoryStep,
    AgentTrajectoryVerdict,
    review_agent_trajectory,
)


def step(
    index: int,
    tool_name: str,
    output: object,
    *,
    arguments: object | None = None,
    ok: bool | None = None,
    verification_passed: bool = False,
) -> AgentTrajectoryStep:
    return AgentTrajectoryStep.from_observation(
        index=index,
        tool_name=tool_name,
        arguments=arguments or {"target": "research-artifact"},
        output=output,
        ok=ok,
        verification_passed=verification_passed,
    )


def test_review_continues_research_for_verified_progress() -> None:
    review = review_agent_trajectory(
        session_id="session-1",
        task_name="summarize quality artifacts",
        steps=(
            step(1, "read_file", "quality report loaded", ok=True),
            step(2, "pytest", "17 passed", ok=True, verification_passed=True),
        ),
    )

    assert review.verdict is AgentTrajectoryVerdict.CONTINUE_RESEARCH
    assert review.signals == ()
    assert review.blockers == ("LIVE_ORDER_BLOCKED",)
    assert review.execution_allowed is False
    assert review.promotion_status == "RESEARCH_ONLY_TRAJECTORY_REVIEW"
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_review_watchlists_repeated_error_class_without_repeated_output() -> None:
    review = review_agent_trajectory(
        session_id="session-2",
        task_name="repair focused test",
        steps=(
            step(1, "pytest", "AssertionError: expected 1"),
            step(2, "pytest", "AssertionError: expected 2"),
            step(3, "pytest", "AssertionError: expected 3"),
        ),
    )

    assert review.verdict is AgentTrajectoryVerdict.WATCHLIST
    assert AgentTrajectorySignal.REPEATED_ERROR_CLASS in review.signals
    assert "REPEATED_ERROR_CLASS" in review.blockers
    assert review.execution_allowed is False


def test_review_recommends_restart_for_rewrite_retest_cycle() -> None:
    review = review_agent_trajectory(
        session_id="session-3",
        task_name="repair loop",
        steps=(
            step(1, "apply_patch", "patched file", ok=True),
            step(2, "pytest", "AssertionError: first failure"),
            step(3, "apply_patch", "patched file again", ok=True),
            step(4, "pytest", "AssertionError: second failure"),
        ),
        config=AgentTrajectoryReviewConfig(
            max_steps_without_progress=10,
            rewrite_retest_failures_threshold=2,
        ),
    )

    assert review.verdict is AgentTrajectoryVerdict.RESTART_RECOMMENDED
    assert AgentTrajectorySignal.REWRITE_RETEST_CYCLE in review.signals
    assert "RESTART_RECOMMENDED" in review.blockers
    assert review.execution_allowed is False


def test_review_recommends_restart_after_steps_without_progress() -> None:
    review = review_agent_trajectory(
        session_id="session-4",
        task_name="long artifact rewrite",
        steps=(
            step(1, "apply_patch", "changed docs", ok=True),
            step(2, "read_file", "same context", ok=True),
            step(3, "apply_patch", "changed docs again", ok=True),
        ),
        config=AgentTrajectoryReviewConfig(max_steps_without_progress=3),
    )

    assert review.verdict is AgentTrajectoryVerdict.RESTART_RECOMMENDED
    assert AgentTrajectorySignal.STEPS_WITHOUT_PROGRESS in review.signals
    assert review.execution_allowed is False


def test_budget_guardrail_requires_human_review_without_network_call() -> None:
    review = review_agent_trajectory(
        session_id="session-5",
        task_name="expensive advisory synthesis",
        steps=(step(1, "pytest", "passed", ok=True, verification_passed=True),),
        budget_usd_spent=5.0,
        budget_usd_limit=5.0,
    )

    assert review.verdict is AgentTrajectoryVerdict.HUMAN_REVIEW_REQUIRED
    assert AgentTrajectorySignal.BUDGET_GUARDRAIL in review.signals
    assert "HUMAN_REVIEW_REQUIRED" in review.blockers
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_step_redacts_secret_like_previews_but_keeps_digests() -> None:
    observed = AgentTrajectoryStep.from_observation(
        index=1,
        tool_name="curl",
        arguments={"Authorization": "Bearer sk-super-secret-token"},
        output="provider returned lv_secret_token_value",
        ok=True,
    )

    assert observed.args_preview == "[REDACTED_CREDENTIAL]"
    assert observed.output_preview == "[REDACTED_CREDENTIAL]"
    assert len(observed.args_digest) == 64
    assert len(observed.output_digest) == 64


def test_contract_rejects_authority_drift_and_bad_shapes() -> None:
    good = review_agent_trajectory(
        session_id="session-6",
        task_name="safe review",
        steps=(step(1, "pytest", "passed", ok=True, verification_passed=True),),
    )

    with pytest.raises(ValueError, match="execution authority"):
        replace(good, execution_allowed=True)
    with pytest.raises(ValueError, match="live blocked"):
        replace(good, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="sha256"):
        replace(good.steps[0], args_digest="not-a-digest")
    with pytest.raises(ValueError, match="secret-like"):
        replace(good.steps[0], args_preview="OPENAI_API_KEY=sk-secret-value")

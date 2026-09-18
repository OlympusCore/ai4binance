from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.governance import (
    AgenticPatternDefinition,
    AgenticPatternId,
    AgenticSkillPlan,
    build_default_agentic_pattern_catalog,
    recommend_agentic_skill_plan,
)
from ai4binance.governance.agentic_patterns import _plan_blockers


def test_agentic_catalog_contains_nine_safe_patterns() -> None:
    catalog = build_default_agentic_pattern_catalog()
    ids = tuple(item.pattern_id for item in catalog)

    assert ids == tuple(AgenticPatternId)
    assert len(catalog) == 9
    assert len(set(ids)) == 9
    assert all(item.bounded_authority == "RESEARCH_ONLY" for item in catalog)
    assert all(not item.execution_allowed for item in catalog)
    assert all(item.live_eligibility_status == "LIVE_ORDER_BLOCKED" for item in catalog)


def test_high_risk_workflows_force_human_review_and_live_blocker() -> None:
    plan = recommend_agentic_skill_plan(
        task_name="Deploy trading policy change",
        risk_domain="code_deployment",
        independent_checks=4,
    )

    assert plan.selected_pattern.pattern_id is AgenticPatternId.HUMAN_IN_THE_LOOP
    assert plan.escalation_required is True
    assert "HUMAN_REVIEW_REQUIRED" in plan.blockers
    assert "LIVE_ORDER_BLOCKED" in plan.blockers
    assert plan.execution_allowed is False
    assert plan.promotion_status == "RESEARCH_ONLY"
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_recommendation_selects_parallel_routing_and_bounded_autonomy() -> None:
    parallel = recommend_agentic_skill_plan(
        task_name="Competitor research",
        independent_checks=3,
    )
    routed = recommend_agentic_skill_plan(
        task_name="Customer complaint comes in",
        needs_routing=True,
    )
    autonomous = recommend_agentic_skill_plan(
        task_name="Refresh read-only artifact index",
        bounded_actions=True,
        downside_controlled=True,
    )

    assert parallel.selected_pattern.pattern_id is AgenticPatternId.PARALLELIZATION
    assert routed.selected_pattern.pattern_id is AgenticPatternId.ROUTING
    assert (
        autonomous.selected_pattern.pattern_id is AgenticPatternId.AUTONOMOUS_WORKFLOW
    )
    assert autonomous.execution_allowed is False
    assert autonomous.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_recommendation_covers_quality_stages_debate_and_reflection() -> None:
    debate = recommend_agentic_skill_plan(
        task_name="CFO and operator debate",
        opposing_views=True,
    )
    evaluator = recommend_agentic_skill_plan(
        task_name="Draft policy response",
        quality_sensitive=True,
    )
    chain = recommend_agentic_skill_plan(
        task_name="Research outline compose final check",
        stages=4,
    )
    reflection = recommend_agentic_skill_plan(task_name="Review weak evidence")

    assert debate.selected_pattern.pattern_id is AgenticPatternId.MULTI_AGENT_DEBATE
    assert evaluator.selected_pattern.pattern_id is AgenticPatternId.EVALUATOR_OPTIMIZER
    assert chain.selected_pattern.pattern_id is AgenticPatternId.PROMPT_CHAINING
    assert reflection.selected_pattern.pattern_id is AgenticPatternId.REFLECTION


def test_risk_domain_aliases_and_unknown_domain_are_safe() -> None:
    deployment = recommend_agentic_skill_plan(
        task_name="Release application",
        risk_domain="deployment",
    )
    unknown = recommend_agentic_skill_plan(
        task_name="General brainstorming",
        risk_domain="made-up-domain",
    )

    assert deployment.selected_pattern.pattern_id is AgenticPatternId.HUMAN_IN_THE_LOOP
    assert "HUMAN_REVIEW_REQUIRED" in deployment.blockers
    assert unknown.selected_pattern.pattern_id is AgenticPatternId.REFLECTION
    assert unknown.blockers == ("LIVE_ORDER_BLOCKED",)


def test_bounded_action_without_downside_control_avoids_autonomy() -> None:
    plan = recommend_agentic_skill_plan(
        task_name="Cleanup generated artifacts",
        bounded_actions=True,
        downside_controlled=False,
    )

    assert plan.selected_pattern.pattern_id is AgenticPatternId.ORCHESTRATOR_WORKER
    assert "AUTONOMOUS_EXECUTION_NOT_SELECTED" in plan.blockers
    assert plan.execution_allowed is False


def test_agentic_contracts_reject_authority_drift() -> None:
    definition = build_default_agentic_pattern_catalog()[0]
    plan = recommend_agentic_skill_plan(task_name="safe review")
    with pytest.raises(ValueError, match="promote"):
        replace(definition, bounded_authority="PAPER_APPROVED")
    with pytest.raises(ValueError, match="authorize"):
        replace(definition, execution_allowed=True)
    with pytest.raises(ValueError, match="non-empty"):
        replace(definition, use_when=())
    with pytest.raises(ValueError, match="blanks"):
        replace(definition, required_inputs=("",))
    with pytest.raises(ValueError, match="stop and review"):
        replace(definition, stopping_rule="")
    with pytest.raises(ValueError, match="counts"):
        recommend_agentic_skill_plan(task_name="bad", independent_checks=-1)
    with pytest.raises(ValueError, match="identity"):
        AgenticPatternDefinition(
            AgenticPatternId.REFLECTION,
            "",
            "role",
            ("a",),
            ("b",),
            "stop",
            "review",
        )
    with pytest.raises(ValueError, match="task name"):
        replace(plan, task_name="")
    with pytest.raises(ValueError, match="unique"):
        replace(plan, blockers=("A", "A"))
    with pytest.raises(ValueError, match="blanks"):
        replace(plan, measurement_plan=("",))
    with pytest.raises(ValueError, match="stop and review"):
        replace(plan, review_rule="")
    with pytest.raises(ValueError, match="promote or execute"):
        replace(plan, execution_allowed=True)
    with pytest.raises(ValueError, match="live blocked"):
        replace(plan, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="task name"):
        AgenticSkillPlan(
            "",
            definition,
            ("input",),
            "stop",
            "review",
            ("measure",),
            ("LIVE_ORDER_BLOCKED",),
            False,
        )


def test_autonomous_blocker_guard_is_defensive() -> None:
    blockers = _plan_blockers(
        AgenticPatternId.AUTONOMOUS_WORKFLOW,
        high_risk=False,
        bounded_actions=False,
        downside_controlled=False,
    )

    assert "AUTONOMOUS_WORKFLOW_NOT_BOUNDED" in blockers

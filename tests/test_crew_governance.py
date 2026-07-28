"""Crew, local-LLM and BTCUSDT validation workflow governance tests."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from ai4binance.governance.crew import (
    CrewAuthority,
    CrewCadence,
    CrewGovernanceAgreement,
    CrewPlanStatus,
    CrewProcessPlan,
    CrewRoleDefinition,
    CrewTaskDefinition,
    EngineBinding,
    build_enterprise_ai_crew_plan,
)


def test_enterprise_crew_plan_is_fail_closed_and_targets_btcusdt() -> None:
    plan = build_enterprise_ai_crew_plan()
    task = plan.biweekly_validation_task

    assert plan.validation_symbol == "BTCUSDT"
    assert task.task_id == "btcusdt_biweekly_backtest_tuning"
    assert task.symbol == "BTCUSDT"
    assert task.cadence is CrewCadence.BIWEEKLY
    assert task.interval_days == 14
    assert task.output_artifacts == ("Backtest/validation/BTCUSDT",)
    assert "LIVE_ORDER_BLOCKED" in task.blockers
    assert task.emits_signal_opportunity is True
    assert plan.execution_allowed is False
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert plan.governance is not None
    assert plan.governance.status is CrewPlanStatus.HUMAN_REVIEW_REQUIRED
    assert plan.governance.local_llm_only is True
    assert plan.governance.cloud_fallback_allowed is False
    assert plan.governance.autonomous_execution_allowed is False
    assert "HUMAN_REVIEW_REQUIRED" in plan.governance.blockers
    assert "LIVE_ORDER_BLOCKED" in plan.governance.blockers
    assert task.task_id in plan.governance.validation_points
    assert all(not role.may_submit_orders for role in plan.roles)
    assert all(not role.may_emit_trading_signal for role in plan.roles)
    assert any(role.may_emit_signal_opportunity for role in plan.roles)
    assert all(not engine.execution_allowed for engine in plan.engines)
    assert all(not task.execution_allowed for task in plan.tasks)
    assert "local_llm_advisory_loop" in plan.topological_order()


def test_enterprise_crew_plan_accepts_explicit_validation_symbol_override() -> None:
    plan = build_enterprise_ai_crew_plan(validation_symbol=" ethusdt ")

    assert plan.validation_symbol == "ETHUSDT"
    assert plan.biweekly_validation_task.symbol == "ETHUSDT"
    assert plan.biweekly_validation_task.task_id == "ethusdt_biweekly_backtest_tuning"
    assert plan.biweekly_validation_task.output_artifacts == (
        "Backtest/validation/ETHUSDT",
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CrewRoleDefinition(
            "",
            "Role",
            CrewAuthority.READ_ONLY,
            ("responsibility",),
        ),
        lambda: CrewRoleDefinition(
            "role",
            "Role",
            CrewAuthority.READ_ONLY,
            (),
        ),
        lambda: CrewRoleDefinition(
            "role",
            "Role",
            CrewAuthority.READ_ONLY,
            ("a",),
            may_submit_orders=True,
        ),
        lambda: EngineBinding(
            "engine",
            "local_llm_llama_cpp",
            "qwen3:8b",
            CrewAuthority.RESEARCH_ONLY,
            False,
            (),
            (),
        ),
        lambda: CrewTaskDefinition(
            "task",
            "role",
            "engine",
            CrewCadence.BIWEEKLY,
            (),
            "BTCUSDT",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
            interval_days=7,
        ),
        lambda: CrewTaskDefinition(
            "task",
            "role",
            "engine",
            CrewCadence.DAILY,
            (),
            "BTCUSDT",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
            interval_days=14,
        ),
        lambda: CrewTaskDefinition(
            "task",
            "role",
            "engine",
            CrewCadence.DAILY,
            (),
            "BTCUSDT",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
            emits_trading_signal=True,
        ),
        lambda: CrewTaskDefinition(
            "task",
            "role",
            "engine",
            CrewCadence.DAILY,
            (),
            "BTCUSDT",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
            submits_orders=True,
        ),
        lambda: replace(build_enterprise_ai_crew_plan(), execution_allowed=True),
        lambda: CrewGovernanceAgreement(
            "agreement",
            ("role",),
            ("task",),
            ("task",),
            local_llm_only=False,
        ),
        lambda: CrewGovernanceAgreement(
            "agreement",
            ("role",),
            ("task",),
            ("missing",),
        ),
        lambda: CrewGovernanceAgreement(
            "agreement",
            ("role",),
            ("task",),
            ("task",),
            cloud_fallback_allowed=True,
        ),
        lambda: CrewGovernanceAgreement(
            "agreement",
            ("role",),
            ("task",),
            ("task",),
            autonomous_execution_allowed=True,
        ),
        lambda: CrewGovernanceAgreement(
            "agreement",
            ("role",),
            ("task",),
            ("task",),
            blockers=("HUMAN_REVIEW_REQUIRED",),
        ),
    ],
)
def test_crew_contract_rejects_authority_or_shape_drift(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_crew_process_rejects_unknown_dependencies() -> None:
    plan = build_enterprise_ai_crew_plan()
    broken = replace(
        plan.tasks[0],
        dependencies=("missing",),
    )

    with pytest.raises(ValueError, match="unknown"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=(broken, *plan.tasks[1:]),
        )


def test_crew_process_rejects_governance_plan_mismatch() -> None:
    plan = build_enterprise_ai_crew_plan()
    assert plan.governance is not None
    broken_governance = replace(plan.governance, role_ids=("missing",))

    with pytest.raises(ValueError, match="governance roles"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=plan.tasks,
            governance=broken_governance,
        )

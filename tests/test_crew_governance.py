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
    assert task.output_artifacts == (
        "runtime/artifacts/research/backtest/validation/BTCUSDT",
    )
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
        "runtime/artifacts/research/backtest/validation/ETHUSDT",
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


@pytest.mark.parametrize(
    "factory",
    [
        lambda: EngineBinding(
            "",
            "deterministic_core",
            "internal",
            CrewAuthority.RESEARCH_ONLY,
            True,
            (),
            (),
        ),
        lambda: EngineBinding(
            "engine",
            "deterministic_core",
            "internal",
            CrewAuthority.RESEARCH_ONLY,
            True,
            ("runtime/a.json", "runtime/a.json"),
            (),
        ),
        lambda: EngineBinding(
            "engine",
            "deterministic_core",
            "internal",
            CrewAuthority.RESEARCH_ONLY,
            True,
            (),
            (),
            execution_allowed=True,
        ),
        lambda: CrewTaskDefinition(
            "",
            "role",
            "engine",
            CrewCadence.DAILY,
            (),
            "BTCUSDT",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
        ),
        lambda: CrewTaskDefinition(
            "task",
            "role",
            "engine",
            CrewCadence.DAILY,
            ("dep", "dep"),
            "BTCUSDT",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
        ),
        lambda: CrewTaskDefinition(
            "task",
            "role",
            "engine",
            CrewCadence.DAILY,
            (),
            "@@@",
            ("1h",),
            (),
            (),
            CrewAuthority.RESEARCH_ONLY,
        ),
        lambda: CrewGovernanceAgreement(
            "",
            ("role",),
            ("task",),
            ("task",),
        ),
        lambda: CrewGovernanceAgreement(
            "agreement",
            ("role", " "),
            ("task",),
            ("task",),
        ),
    ],
)
def test_crew_contracts_reject_blank_duplicate_and_execution_drift(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_crew_process_rejects_identity_shape_and_unknown_bindings() -> None:
    plan = build_enterprise_ai_crew_plan()

    with pytest.raises(ValueError, match="identity is required"):
        CrewProcessPlan(
            process_id="",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=plan.tasks,
        )

    with pytest.raises(ValueError, match="validation symbol is invalid"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="@@@",
            roles=plan.roles,
            engines=plan.engines,
            tasks=plan.tasks,
        )

    with pytest.raises(ValueError, match="requires roles, engines and tasks"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=(),
            engines=plan.engines,
            tasks=plan.tasks,
        )

    duplicate_roles = (
        plan.roles[0],
        replace(plan.roles[0], display_name="Duplicate Role"),
        *plan.roles[1:],
    )
    with pytest.raises(ValueError, match="role identities must be unique"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=duplicate_roles,
            engines=plan.engines,
            tasks=plan.tasks,
        )

    duplicate_engines = (
        plan.engines[0],
        replace(plan.engines[0], provider="duplicate-provider"),
        *plan.engines[1:],
    )
    with pytest.raises(ValueError, match="engine identities must be unique"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=duplicate_engines,
            tasks=plan.tasks,
        )

    duplicate_tasks = (
        plan.tasks[0],
        replace(plan.tasks[0], symbol="ETHUSDT"),
        *plan.tasks[1:],
    )
    with pytest.raises(ValueError, match="task identities must be unique"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=duplicate_tasks,
        )

    broken_role_task = replace(plan.tasks[0], role_id="missing-role")
    with pytest.raises(ValueError, match="role is unknown"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=(broken_role_task, *plan.tasks[1:]),
        )

    broken_engine_task = replace(plan.tasks[0], engine_id="missing-engine")
    with pytest.raises(ValueError, match="engine is unknown"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=(broken_engine_task, *plan.tasks[1:]),
        )


def test_crew_process_rejects_governance_task_mismatch_and_dependency_cycle() -> None:
    plan = build_enterprise_ai_crew_plan()
    assert plan.governance is not None

    validation_points = set(plan.governance.validation_points)
    replaced_task_id = next(
        task_id
        for task_id in plan.governance.task_ids
        if task_id not in validation_points
    )
    broken_task_ids = tuple(
        "missing-task" if task_id == replaced_task_id else task_id
        for task_id in plan.governance.task_ids
    )
    broken_governance = replace(plan.governance, task_ids=broken_task_ids)
    with pytest.raises(ValueError, match="governance tasks"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=plan.tasks,
            governance=broken_governance,
        )

    cycle_tasks = (
        replace(plan.tasks[0], dependencies=(plan.tasks[1].task_id,)),
        replace(plan.tasks[1], dependencies=(plan.tasks[0].task_id,)),
        *plan.tasks[2:],
    )
    with pytest.raises(ValueError, match="dependency cycle"):
        CrewProcessPlan(
            process_id="broken",
            validation_symbol="BTCUSDT",
            roles=plan.roles,
            engines=plan.engines,
            tasks=cycle_tasks,
            governance=plan.governance,
        )


def test_crew_biweekly_validation_requires_exactly_one_matching_task() -> None:
    plan = build_enterprise_ai_crew_plan()
    wrong_symbol_tasks = (
        replace(plan.biweekly_validation_task, symbol="ETHUSDT"),
        *tuple(
            task for task in plan.tasks if task is not plan.biweekly_validation_task
        ),
    )

    wrong_symbol_plan = CrewProcessPlan(
        process_id="broken",
        validation_symbol="BTCUSDT",
        roles=plan.roles,
        engines=plan.engines,
        tasks=wrong_symbol_tasks,
        governance=plan.governance,
    )
    with pytest.raises(
        ValueError, match="exactly one validation-symbol biweekly task is required"
    ):
        _ = wrong_symbol_plan.biweekly_validation_task

    with pytest.raises(ValueError, match="validation symbol is invalid"):
        build_enterprise_ai_crew_plan(validation_symbol="@@@")

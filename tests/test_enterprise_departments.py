from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.enterprise.contracts import DepartmentId
from ai4binance.enterprise.departments import (
    AgentClassification,
    DepartmentDefinition,
    DepartmentRegistry,
    ResourceClass,
    build_default_department_registry,
    default_separation_of_duties_rules,
)


def test_default_department_registry_matches_pyramid_and_independent_controls() -> None:
    registry = build_default_department_registry()
    controls = {item.department_id for item in registry.independent_controls()}

    assert len(registry.departments) == len(DepartmentId)
    assert controls == {
        DepartmentId.QUALITY_AUDIT,
        DepartmentId.RISK_VALIDATION,
        DepartmentId.MULTI_OPS,
    }
    assert all(
        item.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for item in registry.departments
    )
    assert all(not item.execution_allowed for item in registry.departments)
    assert registry.get(DepartmentId.EXECUTIVE_OFFICE).reports_to is None


def test_registry_validates_agent_classification_authority() -> None:
    registry = build_default_department_registry()
    data_supply = registry.validate_assignment(
        department_id=DepartmentId.DATA_SUPPLY,
        classification=AgentClassification.DATA_ACQUISITION_AGENT,
    )

    assert data_supply.resource_class is ResourceClass.IO_BOUND
    with pytest.raises(ValueError, match="outside department authority"):
        registry.validate_assignment(
            department_id=DepartmentId.TRADER,
            classification=AgentClassification.RISK_GATE,
        )


def test_department_definitions_reject_unbounded_or_unsafe_authority() -> None:
    quality = build_default_department_registry().get(DepartmentId.QUALITY_AUDIT)

    with pytest.raises(ValueError, match="bounded"):
        replace(quality, max_runtime_concurrency=11)
    with pytest.raises(ValueError, match="independent-control"):
        replace(quality, independent_control=False)
    with pytest.raises(ValueError, match="live execution"):
        replace(quality, execution_allowed=True)
    with pytest.raises(ValueError, match="display_name"):
        replace(quality, display_name="")
    with pytest.raises(ValueError, match="unique"):
        replace(quality, authority_scope=("AUDIT", "AUDIT"))
    with pytest.raises(ValueError, match="classifications cannot be empty"):
        replace(quality, allowed_classifications=())
    with pytest.raises(ValueError, match="classifications must be unique"):
        replace(
            quality,
            allowed_classifications=(
                AgentClassification.QUALITY_REVIEWER,
                AgentClassification.QUALITY_REVIEWER,
            ),
        )
    with pytest.raises(ValueError, match="only independent"):
        DepartmentDefinition(
            DepartmentId.TRADER,
            "Trader",
            "TraderDepartmentManager",
            "Prepare trade candidates.",
            ("SETUP_SELECTION",),
            (AgentClassification.DEPARTMENT_MANAGER,),
            ResourceClass.CPU_LIGHT,
            1,
            veto_authority=True,
        )


def test_registry_rejects_duplicate_departments_and_missing_control_line() -> None:
    registry = build_default_department_registry()
    duplicate = (*registry.departments, registry.departments[0])
    missing_risk = tuple(
        item
        for item in registry.departments
        if item.department_id is not DepartmentId.RISK_VALIDATION
    )

    with pytest.raises(ValueError, match="unique"):
        DepartmentRegistry(duplicate)
    with pytest.raises(ValueError, match="independent"):
        DepartmentRegistry(missing_risk)
    with pytest.raises(ValueError, match="cannot be empty"):
        DepartmentRegistry(())
    with pytest.raises(ValueError, match="reports_to"):
        DepartmentRegistry(
            (
                replace(
                    registry.get(DepartmentId.EXECUTIVE_OFFICE),
                    reports_to=DepartmentId.TRADER,
                ),
                *tuple(
                    item
                    for item in registry.departments
                    if item.department_id
                    not in {
                        DepartmentId.EXECUTIVE_OFFICE,
                        DepartmentId.TRADER,
                    }
                ),
            )
        )
    assert len(registry.operational_departments()) == len(DepartmentId) - 3


def test_separation_of_duties_rules_block_self_approval_and_veto_override() -> None:
    rules = default_separation_of_duties_rules()
    by_id = {rule.rule_id: rule for rule in rules}

    assert by_id["SOFTWARE_CANNOT_SELF_APPROVE"].subject_department is (
        DepartmentId.SOFTWARE_ENGINEERING
    )
    assert (
        by_id["TRADER_CANNOT_OVERRIDE_RISK"].blocker == "TRADER_RISK_OVERRIDE_BLOCKED"
    )
    assert by_id["GENERAL_MANAGER_CANNOT_REMOVE_VETO"].prohibited_authority == (
        "VETO_OVERRIDE"
    )
    assert all(rule.live_eligibility_status == "LIVE_ORDER_BLOCKED" for rule in rules)
    with pytest.raises(ValueError, match="live execution"):
        replace(rules[0], live_eligibility_status="LIVE_ELIGIBLE")

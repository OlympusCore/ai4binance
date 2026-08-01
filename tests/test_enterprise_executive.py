from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai4binance.enterprise.contracts import (
    BoardDirective,
    DepartmentId,
    Priority,
    WorkflowIdentity,
)
from ai4binance.enterprise.departments import build_default_department_registry
from ai4binance.enterprise.executive import (
    ExecutiveRoutingDecision,
    GeneralManagerController,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def directive() -> BoardDirective:
    return BoardDirective(
        identity(),
        "directive-1",
        "board-chair",
        "Apply pyramid governance contracts.",
        ("NO_LIVE_AUTHORITY",),
        ("RESEARCH_ONLY",),
        "cpu-light",
        600,
    )


def test_general_manager_routes_to_departments_and_independent_controls() -> None:
    controller = GeneralManagerController(build_default_department_registry())
    decision = controller.route_directive(
        directive(),
        requested_departments=(DepartmentId.SOFTWARE_ENGINEERING,),
        priority=Priority.P2,
    )

    assert decision.assigned_departments == (
        DepartmentId.SOFTWARE_ENGINEERING,
        DepartmentId.QUALITY_AUDIT,
        DepartmentId.RISK_VALIDATION,
        DepartmentId.MULTI_OPS,
    )
    assert decision.meeting_required is True
    assert decision.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_general_manager_builds_fail_closed_work_order_preview() -> None:
    controller = GeneralManagerController(build_default_department_registry())
    order = controller.build_work_order(
        directive(),
        requested_departments=(DepartmentId.DATA_SUPPLY, DepartmentId.TRADER),
        priority=Priority.P1,
    )

    assert order.execution_allowed is False
    assert order.promotion_status == "RESEARCH_ONLY"
    assert DepartmentId.QUALITY_AUDIT in order.assigned_departments
    assert DepartmentId.RISK_VALIDATION in order.assigned_departments
    assert DepartmentId.MULTI_OPS in order.assigned_departments


def test_general_manager_rejects_empty_or_unsafe_routing() -> None:
    controller = GeneralManagerController(build_default_department_registry())

    with pytest.raises(ValueError, match="requested departments"):
        controller.route_directive(
            directive(),
            requested_departments=(),
            priority=Priority.P2,
        )
    with pytest.raises(ValueError, match="departments must be unique"):
        ExecutiveRoutingDecision(
            "directive-1",
            (DepartmentId.TRADER, DepartmentId.TRADER),
            ("LIVE_ORDER_BLOCKED",),
            True,
        )
    with pytest.raises(ValueError, match="authorize"):
        replace(
            controller.route_directive(
                directive(),
                requested_departments=(DepartmentId.TRADER,),
                priority=Priority.P2,
            ),
            execution_allowed=True,
        )

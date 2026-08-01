"""Deterministic executive controller for board directives."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.enterprise.contracts import (
    BoardDirective,
    DepartmentId,
    ExecutiveWorkOrder,
    Priority,
    WorkflowIdentity,
    WorkOrderStatus,
)
from ai4binance.enterprise.departments import DepartmentRegistry
from ai4binance.enterprise.prompt_intake import (
    ExecutivePromptIntake,
    PromptAccessPolicy,
    PromptAccessStatus,
)

_CONTROL_DEPARTMENTS = (
    DepartmentId.QUALITY_AUDIT,
    DepartmentId.RISK_VALIDATION,
    DepartmentId.MULTI_OPS,
)


@dataclass(frozen=True, slots=True)
class ExecutiveRoutingDecision:
    directive_id: str
    assigned_departments: tuple[DepartmentId, ...]
    blockers: tuple[str, ...]
    meeting_required: bool
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.directive_id.strip():
            raise ValueError("executive routing identity is required")
        if not self.assigned_departments:
            raise ValueError("executive routing requires departments")
        if len(set(self.assigned_departments)) != len(self.assigned_departments):
            raise ValueError("executive routing departments must be unique")
        if not self.blockers:
            raise ValueError("executive routing must retain blockers")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("executive routing cannot promote production state")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("executive routing cannot authorize execution")


@dataclass(frozen=True, slots=True)
class GeneralManagerController:
    """Create department work-order previews without direct specialist control."""

    registry: DepartmentRegistry

    def intake_prompt(
        self,
        *,
        identity: WorkflowIdentity,
        prompt_id: str,
        submitted_by: str,
        raw_prompt: str,
        objective: str | None = None,
        constraints: tuple[str, ...] = (),
        authority_scope: tuple[str, ...] = (),
    ) -> ExecutivePromptIntake:
        intake = ExecutivePromptIntake.from_raw_prompt(
            identity=identity,
            prompt_id=prompt_id,
            submitted_by=submitted_by,
            raw_prompt=raw_prompt,
            objective=objective,
            constraints=constraints,
            authority_scope=authority_scope,
        )
        decision = PromptAccessPolicy(self.registry).authorize_raw_prompt(
            actor_department_id=DepartmentId.EXECUTIVE_OFFICE,
            actor_role=self.registry.get(DepartmentId.EXECUTIVE_OFFICE).manager_role,
            intake=intake,
        )
        if decision.status is not PromptAccessStatus.ALLOWED:
            raise RuntimeError("GENERAL_MANAGER_PROMPT_ACCESS_REQUIRED")
        return intake

    def build_directive_from_prompt(
        self,
        *,
        identity: WorkflowIdentity,
        prompt_id: str,
        directive_id: str,
        submitted_by: str,
        raw_prompt: str,
        resource_budget: str,
        time_budget_seconds: int,
        objective: str | None = None,
        constraints: tuple[str, ...] = (),
        authority_scope: tuple[str, ...] = (),
    ) -> BoardDirective:
        intake = self.intake_prompt(
            identity=identity,
            prompt_id=prompt_id,
            submitted_by=submitted_by,
            raw_prompt=raw_prompt,
            objective=objective,
            constraints=constraints,
            authority_scope=authority_scope,
        )
        return intake.to_board_directive(
            directive_id=directive_id,
            resource_budget=resource_budget,
            time_budget_seconds=time_budget_seconds,
        )

    def route_directive(
        self,
        directive: BoardDirective,
        *,
        requested_departments: tuple[DepartmentId, ...],
        priority: Priority,
    ) -> ExecutiveRoutingDecision:
        if not requested_departments:
            raise ValueError("executive routing requires requested departments")
        assigned = _stable_unique((*requested_departments, *_CONTROL_DEPARTMENTS))
        for department in assigned:
            self.registry.get(department)
        blockers = ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
        return ExecutiveRoutingDecision(
            directive_id=directive.directive_id,
            assigned_departments=assigned,
            blockers=blockers,
            meeting_required=len(assigned) > 1,
        )

    def build_work_order(
        self,
        directive: BoardDirective,
        *,
        requested_departments: tuple[DepartmentId, ...],
        priority: Priority,
    ) -> ExecutiveWorkOrder:
        decision = self.route_directive(
            directive,
            requested_departments=requested_departments,
            priority=priority,
        )
        return ExecutiveWorkOrder(
            identity=directive.identity,
            directive_id=directive.directive_id,
            objective=directive.objective,
            assigned_departments=decision.assigned_departments,
            priority=priority,
            status=WorkOrderStatus.HUMAN_REVIEW_REQUIRED,
            blockers=decision.blockers,
        )


def _stable_unique(values: tuple[DepartmentId, ...]) -> tuple[DepartmentId, ...]:
    seen: set[DepartmentId] = set()
    ordered: list[DepartmentId] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)

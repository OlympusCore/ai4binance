"""Layered context packets for department-safe work orders."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.enterprise.contracts import DepartmentId
from ai4binance.enterprise.prompt_intake import (
    ExecutivePromptIntake,
    contains_restricted_prompt_content,
)


class ContextLayerId(StrEnum):
    SYSTEM = "SYSTEM"
    DOMAIN = "DOMAIN"
    TASK = "TASK"
    INTERACTION = "INTERACTION"
    RESPONSE = "RESPONSE"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _assert_no_restricted(name: str, value: str) -> None:
    if contains_restricted_prompt_content(value):
        raise ValueError(f"{name} contains restricted prompt content")


@dataclass(frozen=True, slots=True)
class ContextLayer:
    layer_id: ContextLayerId
    content: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.layer_id not in ContextLayerId:
            raise ValueError("context layer id is invalid")
        _require_text("context layer content", self.content)
        _require_unique_text("context layer evidence refs", self.evidence_refs)
        _assert_no_restricted("context layer content", self.content)


@dataclass(frozen=True, slots=True)
class DepartmentContextPacket:
    packet_id: str
    prompt_ref: str
    department_id: DepartmentId
    sanitized_objective: str
    layers: tuple[ContextLayer, ...]
    constraints: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("context packet id", self.packet_id)
        _require_text("context packet prompt ref", self.prompt_ref)
        _require_text("context packet objective", self.sanitized_objective)
        _require_unique_text("context packet constraints", self.constraints)
        _assert_no_restricted("context packet objective", self.sanitized_objective)
        for constraint in self.constraints:
            _assert_no_restricted("context packet constraint", constraint)
        if self.department_id not in DepartmentId:
            raise ValueError("context packet department is invalid")
        if not self.layers:
            raise ValueError("context packet requires layers")
        if self.execution_allowed:
            raise ValueError("context packet cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("context packet cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("context packet must remain live blocked")


def build_department_context_packet(
    *,
    intake: ExecutivePromptIntake,
    department_id: DepartmentId,
    task_requirements: tuple[str, ...],
    output_contract: str,
) -> DepartmentContextPacket:
    _require_unique_text("context task requirements", task_requirements)
    _require_text("context output contract", output_contract)
    _assert_no_restricted("context output contract", output_contract)
    for requirement in task_requirements:
        _assert_no_restricted("context task requirement", requirement)
    layers = (
        ContextLayer(
            ContextLayerId.SYSTEM,
            "AGENTS.md and deterministic AI4BINANCE governance remain authoritative.",
            (intake.raw_prompt_ref,),
        ),
        ContextLayer(
            ContextLayerId.DOMAIN,
            (
                "Trading authority is advisory-only; return NO_TRADE or "
                "LIVE_ORDER_BLOCKED when evidence is incomplete."
            ),
            (intake.raw_prompt_ref,),
        ),
        ContextLayer(
            ContextLayerId.TASK,
            "\n".join(task_requirements),
            (intake.raw_prompt_ref,),
        ),
        ContextLayer(
            ContextLayerId.RESPONSE,
            output_contract,
            (intake.raw_prompt_ref,),
        ),
    )
    return DepartmentContextPacket(
        packet_id=f"context:{intake.prompt_id}:{department_id.value}",
        prompt_ref=intake.raw_prompt_ref,
        department_id=department_id,
        sanitized_objective=intake.objective,
        layers=layers,
        constraints=tuple(
            dict.fromkeys(
                (
                    *intake.constraints,
                    "RAW_PROMPT_NOT_INCLUDED",
                    "DEPARTMENT_CONTEXT_ONLY",
                )
            )
        ),
    )

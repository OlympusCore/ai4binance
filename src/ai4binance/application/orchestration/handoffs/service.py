"""Fail-closed validation for typed agent handoffs."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ai4binance.core.contracts.handoffs import (
    AuthorityScope,
    HandoffBudget,
    HandoffBudgetUsage,
    HandoffEnvelope,
    HandoffResult,
    HandoffStatus,
)

_TERMINAL_STATUSES = {
    HandoffStatus.COMPLETED,
    HandoffStatus.REJECTED,
    HandoffStatus.BLOCKED,
    HandoffStatus.EXPIRED,
    HandoffStatus.CANCELLED,
    HandoffStatus.FAILED,
}


def validate_handoff_envelope(
    envelope: HandoffEnvelope,
    *,
    allowed_roles: tuple[str, ...],
    allowed_workflows: tuple[str, ...],
    now: datetime,
    parent_envelope: HandoffEnvelope | None = None,
) -> HandoffEnvelope:
    """Validate an envelope and return the validated lifecycle state."""
    _require_aware("handoff validation time", now)
    if envelope.status is not HandoffStatus.CREATED:
        raise ValueError("handoff envelope must start in CREATED state")
    if now >= envelope.expires_at:
        raise ValueError("handoff envelope has expired")
    if now >= envelope.budget.deadline:
        raise ValueError("handoff budget deadline has expired")
    if envelope.from_role == envelope.to_role:
        raise ValueError("handoff requires distinct from_role and to_role")
    _require_registry_membership(
        name="allowed roles",
        registry=allowed_roles,
        values=(envelope.from_role, envelope.to_role),
    )
    _require_registry_membership(
        name="allowed workflows",
        registry=allowed_workflows,
        values=(envelope.workflow_id,),
    )
    if not envelope.context_refs:
        raise ValueError("handoff requires context references")
    if not envelope.evidence_refs:
        raise ValueError("handoff requires evidence references")
    if not envelope.governance_refs:
        raise ValueError("handoff requires governance references")
    if not envelope.policy_versions:
        raise ValueError("handoff requires policy version references")
    _require_authority_chain(
        receiver=envelope.receiver_authority,
        sender=envelope.sender_delegated_authority,
        workflow=envelope.workflow_allowed_authority,
        governance=envelope.governance_policy_authority,
    )
    _require_delegation_identity(envelope, parent_envelope=parent_envelope)
    return replace(envelope, status=HandoffStatus.VALIDATED)


def accept_handoff(
    envelope: HandoffEnvelope,
    *,
    allowed_roles: tuple[str, ...],
    allowed_workflows: tuple[str, ...],
    now: datetime,
    parent_envelope: HandoffEnvelope | None = None,
) -> HandoffEnvelope:
    """Validate and accept a handoff before receiver work starts."""
    validated = validate_handoff_envelope(
        envelope,
        allowed_roles=allowed_roles,
        allowed_workflows=allowed_workflows,
        now=now,
        parent_envelope=parent_envelope,
    )
    return replace(validated, status=HandoffStatus.ACCEPTED)


def start_handoff(
    envelope: HandoffEnvelope,
    *,
    now: datetime,
) -> HandoffEnvelope:
    """Move an accepted handoff into the worker execution state."""
    _require_aware("handoff start time", now)
    if envelope.status is not HandoffStatus.ACCEPTED:
        raise ValueError("handoff can only start from ACCEPTED state")
    if now >= envelope.expires_at:
        raise ValueError("handoff envelope has expired")
    if now >= envelope.budget.deadline:
        raise ValueError("handoff budget deadline has expired")
    return replace(envelope, status=HandoffStatus.IN_PROGRESS)


def validate_handoff_result(
    envelope: HandoffEnvelope,
    result: HandoffResult,
) -> HandoffResult:
    """Validate a receiver result against the original handoff envelope."""
    if envelope.status is not HandoffStatus.IN_PROGRESS:
        raise ValueError("handoff result requires an in-progress envelope")
    if result.status not in _TERMINAL_STATUSES:
        raise ValueError("handoff result must use a terminal lifecycle state")
    if result.handoff_id != envelope.handoff_id:
        raise ValueError("handoff result identity does not match envelope")
    if result.output_contract != envelope.expected_output_contract:
        raise ValueError("handoff result output contract does not match envelope")
    missing_fields = tuple(
        field
        for field in envelope.required_output_fields
        if field not in result.output_fields
    )
    if missing_fields:
        raise ValueError("handoff result is missing required output fields")
    missing_blockers = tuple(
        blocker
        for blocker in envelope.inherited_blockers
        if blocker not in result.inherited_blockers
    )
    if missing_blockers:
        raise ValueError("handoff result dropped inherited blockers")
    if any(
        evidence.snapshot_id != envelope.snapshot_id
        for evidence in result.produced_evidence_refs
    ):
        raise ValueError("handoff result evidence must keep the envelope snapshot")
    if result.status is HandoffStatus.COMPLETED and not result.produced_evidence_refs:
        raise ValueError("completed handoff requires produced evidence references")
    if result.started_at > envelope.expires_at:
        raise ValueError("handoff result started after envelope expiry")
    if result.completed_at > envelope.expires_at:
        raise ValueError("handoff result completed after envelope expiry")
    if result.completed_at > envelope.budget.deadline:
        raise ValueError("handoff result completed after budget deadline")
    _require_tool_usage(envelope=envelope, result=result)
    _require_budget_usage(envelope.budget, result.budget_usage)
    return result


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_registry_membership(
    *,
    name: str,
    registry: tuple[str, ...],
    values: tuple[str, ...],
) -> None:
    if not registry:
        raise ValueError(f"handoff requires {name} registry")
    unknown = tuple(value for value in values if value not in registry)
    if unknown:
        raise ValueError(f"handoff references unknown {name}")


def _require_authority_chain(
    *,
    receiver: AuthorityScope,
    sender: AuthorityScope,
    workflow: AuthorityScope,
    governance: AuthorityScope,
) -> None:
    if not receiver.is_subset_of(sender):
        raise ValueError("receiver authority cannot exceed sender delegation")
    if not sender.is_subset_of(workflow):
        raise ValueError("sender delegation cannot exceed workflow authority")
    if not workflow.is_subset_of(governance):
        raise ValueError("workflow authority cannot exceed governance policy")


def _require_delegation_identity(
    envelope: HandoffEnvelope,
    *,
    parent_envelope: HandoffEnvelope | None,
) -> None:
    if envelope.parent_handoff_id is None:
        if parent_envelope is not None:
            raise ValueError("root handoff cannot provide a parent envelope")
        if envelope.root_handoff_id != envelope.handoff_id:
            raise ValueError("root handoff must reference itself")
        if envelope.delegation.delegation_depth != 0:
            raise ValueError("root handoff delegation depth must be zero")
        return
    if envelope.parent_handoff_id == envelope.handoff_id:
        raise ValueError("handoff cannot be its own parent")
    if envelope.root_handoff_id == envelope.handoff_id:
        raise ValueError("delegated handoff root must differ from handoff_id")
    if not envelope.delegation.delegation_allowed:
        raise ValueError("delegated handoff requires delegation permission")
    if envelope.delegation.delegation_depth < 1:
        raise ValueError("delegated handoff requires positive delegation depth")
    if parent_envelope is None:
        raise ValueError("delegated handoff requires a parent envelope")
    _require_parent_chain(envelope, parent_envelope)


def _require_parent_chain(
    child: HandoffEnvelope,
    parent: HandoffEnvelope,
) -> None:
    if child.parent_handoff_id != parent.handoff_id:
        raise ValueError("delegated handoff parent identity does not match")
    if parent.status not in {HandoffStatus.ACCEPTED, HandoffStatus.IN_PROGRESS}:
        raise ValueError("delegated handoff parent must be accepted or in progress")
    if not parent.delegation.delegation_allowed:
        raise ValueError("parent handoff does not allow delegation")
    if child.root_handoff_id != parent.root_handoff_id:
        raise ValueError("delegated handoff root identity does not match parent")
    for field_name in ("workflow_id", "cycle_id", "snapshot_id"):
        if getattr(child, field_name) != getattr(parent, field_name):
            raise ValueError(f"delegated handoff {field_name} must match parent")
    if child.from_role != parent.to_role:
        raise ValueError("delegated handoff sender must be the parent receiver")
    if child.delegation.delegation_depth != parent.delegation.delegation_depth + 1:
        raise ValueError("delegated handoff depth must extend parent by one")
    if child.delegation.max_delegation_depth > parent.delegation.max_delegation_depth:
        raise ValueError("delegated handoff max depth cannot exceed parent")
    if child.expires_at > parent.expires_at:
        raise ValueError("delegated handoff expiry cannot exceed parent")
    if child.budget.deadline > parent.budget.deadline:
        raise ValueError("delegated handoff deadline cannot exceed parent")
    if not child.receiver_authority.is_subset_of(parent.receiver_authority):
        raise ValueError("delegated handoff receiver authority cannot exceed parent")
    if not child.sender_delegated_authority.is_subset_of(parent.receiver_authority):
        raise ValueError("delegated handoff sender authority cannot exceed parent")
    if not set(child.allowed_tools) <= set(parent.allowed_tools):
        raise ValueError("delegated handoff tools cannot exceed parent")
    if not set(parent.prohibited_actions) <= set(child.prohibited_actions):
        raise ValueError("delegated handoff cannot weaken prohibited actions")
    _require_child_budget_within_parent(child.budget, parent.budget)


def _require_child_budget_within_parent(
    child: HandoffBudget,
    parent: HandoffBudget,
) -> None:
    if child.max_steps > parent.max_steps:
        raise ValueError("delegated handoff step budget cannot exceed parent")
    if child.max_tool_calls > parent.max_tool_calls:
        raise ValueError("delegated handoff tool budget cannot exceed parent")
    if child.max_llm_calls > parent.max_llm_calls:
        raise ValueError("delegated handoff llm budget cannot exceed parent")
    if child.max_tokens > parent.max_tokens:
        raise ValueError("delegated handoff token budget cannot exceed parent")


def _require_tool_usage(
    *,
    envelope: HandoffEnvelope,
    result: HandoffResult,
) -> None:
    if len(result.tool_usage) != result.budget_usage.tool_calls:
        raise ValueError("handoff tool usage count must match budget usage")
    allowed_tools = set(envelope.allowed_tools)
    prohibited_actions = set(envelope.prohibited_actions)
    for record in result.tool_usage:
        tool_id, _, action_id = record.partition(":")
        if tool_id not in allowed_tools:
            raise ValueError("handoff result used an unauthorized tool")
        if record in prohibited_actions or action_id in prohibited_actions:
            raise ValueError("handoff result attempted a prohibited action")


def _require_budget_usage(
    budget: HandoffBudget,
    usage: HandoffBudgetUsage,
) -> None:
    if usage.steps > budget.max_steps:
        raise ValueError("handoff step budget exceeded")
    if usage.tool_calls > budget.max_tool_calls:
        raise ValueError("handoff tool-call budget exceeded")
    if usage.llm_calls > budget.max_llm_calls:
        raise ValueError("handoff llm-call budget exceeded")
    if usage.total_tokens > budget.max_tokens:
        raise ValueError("handoff token budget exceeded")

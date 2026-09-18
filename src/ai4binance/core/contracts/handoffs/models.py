"""Typed, fail-closed contracts for agent handoffs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class HandoffStatus(StrEnum):
    """Lifecycle states for a bounded handoff."""

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_fail_closed(
    *,
    execution_allowed: bool,
    promotion_status: str,
    live_eligibility_status: str,
    label: str,
) -> None:
    if execution_allowed:
        raise ValueError(f"{label} cannot authorize execution")
    if promotion_status != "RESEARCH_ONLY":
        raise ValueError(f"{label} must remain research-only")
    if live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError(f"{label} must remain live blocked")


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class AuthorityScope:
    """Fail-closed authority set carried by a handoff boundary."""

    authority_ids: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_unique_text("authority scope", self.authority_ids)
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="authority scope",
        )

    def is_subset_of(self, other: AuthorityScope) -> bool:
        """Return whether this scope is contained by another scope."""
        return set(self.authority_ids) <= set(other.authority_ids)


@dataclass(frozen=True, slots=True)
class HandoffEvidenceRef:
    """Reference to canonical evidence; prose summaries are not evidence."""

    evidence_id: str
    evidence_type: str
    producer: str
    snapshot_id: str
    schema_version: str
    created_at: datetime
    content_hash: str
    confidence: float

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "evidence_type",
            "producer",
            "snapshot_id",
            "schema_version",
            "content_hash",
        ):
            _require_text(field_name, getattr(self, field_name))
        _require_aware("evidence created_at", self.created_at)
        if not _SHA256_HEX_RE.fullmatch(self.content_hash):
            raise ValueError("evidence content_hash must be a SHA-256 hex digest")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("evidence confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class HandoffBudget:
    """Bounded resource budget for one handoff."""

    max_steps: int
    max_tool_calls: int
    max_llm_calls: int
    max_tokens: int
    deadline: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "max_steps",
            "max_tool_calls",
            "max_llm_calls",
            "max_tokens",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")
        if self.max_steps < 1:
            raise ValueError("handoff budget requires at least one step")
        _require_aware("handoff budget deadline", self.deadline)


@dataclass(frozen=True, slots=True)
class HandoffBudgetUsage:
    """Actual bounded resource usage reported by a completed handoff."""

    steps: int
    tool_calls: int
    llm_calls: int
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        for field_name in (
            "steps",
            "tool_calls",
            "llm_calls",
            "input_tokens",
            "output_tokens",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")

    @property
    def total_tokens(self) -> int:
        """Return total token usage for budget enforcement."""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class HandoffDelegation:
    """Delegation controls for sub-agent handoff chains."""

    delegation_allowed: bool
    delegation_depth: int
    max_delegation_depth: int

    def __post_init__(self) -> None:
        if self.delegation_depth < 0:
            raise ValueError("delegation_depth cannot be negative")
        if self.max_delegation_depth < 0:
            raise ValueError("max_delegation_depth cannot be negative")
        if self.delegation_depth > self.max_delegation_depth:
            raise ValueError("delegation depth exceeds maximum delegation depth")
        if not self.delegation_allowed and self.delegation_depth > 0:
            raise ValueError("delegation depth requires delegation permission")


@dataclass(frozen=True, slots=True)
class HandoffEnvelope:
    """Typed transfer of task responsibility, context, evidence, and constraints."""

    schema_version: str
    handoff_id: str
    root_handoff_id: str
    parent_handoff_id: str | None
    workflow_id: str
    cycle_id: str
    snapshot_id: str
    from_role: str
    to_role: str
    task_type: str
    objective: str
    context_refs: tuple[str, ...]
    evidence_refs: tuple[HandoffEvidenceRef, ...]
    blocker_refs: tuple[str, ...]
    constraints: tuple[str, ...]
    receiver_authority: AuthorityScope
    sender_delegated_authority: AuthorityScope
    workflow_allowed_authority: AuthorityScope
    governance_policy_authority: AuthorityScope
    allowed_tools: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    expected_output_contract: str
    required_output_fields: tuple[str, ...]
    budget: HandoffBudget
    delegation: HandoffDelegation
    governance_refs: tuple[str, ...]
    policy_versions: tuple[str, ...]
    correlation_id: str
    causation_id: str
    created_at: datetime
    expires_at: datetime
    status: HandoffStatus = HandoffStatus.CREATED
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "handoff_id",
            "root_handoff_id",
            "workflow_id",
            "cycle_id",
            "snapshot_id",
            "from_role",
            "to_role",
            "task_type",
            "objective",
            "expected_output_contract",
            "correlation_id",
            "causation_id",
        ):
            _require_text(field_name, getattr(self, field_name))
        if self.parent_handoff_id is not None:
            _require_text("parent_handoff_id", self.parent_handoff_id)
        for name, values in (
            ("context refs", self.context_refs),
            ("blocker refs", self.blocker_refs),
            ("constraints", self.constraints),
            ("allowed tools", self.allowed_tools),
            ("prohibited actions", self.prohibited_actions),
            ("required output fields", self.required_output_fields),
            ("governance refs", self.governance_refs),
            ("policy versions", self.policy_versions),
        ):
            _require_unique_text(name, values)
        evidence_ids = tuple(item.evidence_id for item in self.evidence_refs)
        _require_unique_text("handoff evidence refs", evidence_ids)
        if any(item.snapshot_id != self.snapshot_id for item in self.evidence_refs):
            raise ValueError("handoff evidence must reference the handoff snapshot")
        _require_aware("handoff created_at", self.created_at)
        _require_aware("handoff expires_at", self.expires_at)
        if self.expires_at <= self.created_at:
            raise ValueError("handoff expires_at must be after created_at")
        if self.budget.deadline > self.expires_at:
            raise ValueError("handoff budget deadline cannot exceed expires_at")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="handoff envelope",
        )

    @property
    def inherited_blockers(self) -> tuple[str, ...]:
        """Return inherited blockers in stable unique order."""
        return _stable_unique(self.blocker_refs)


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """Auditable result for a typed handoff."""

    handoff_id: str
    status: HandoffStatus
    output_contract: str
    output_ref: str
    output_fields: tuple[str, ...]
    produced_evidence_refs: tuple[HandoffEvidenceRef, ...]
    inherited_blockers: tuple[str, ...]
    new_blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    tool_usage: tuple[str, ...]
    budget_usage: HandoffBudgetUsage
    started_at: datetime
    completed_at: datetime
    audit_ref: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in ("handoff_id", "output_contract", "audit_ref"):
            _require_text(field_name, getattr(self, field_name))
        if self.status is HandoffStatus.COMPLETED:
            _require_text("output_ref", self.output_ref)
        for name, values in (
            ("output fields", self.output_fields),
            ("inherited blockers", self.inherited_blockers),
            ("new blockers", self.new_blockers),
            ("warnings", self.warnings),
            ("tool usage", self.tool_usage),
        ):
            _require_unique_text(name, values)
        evidence_ids = tuple(item.evidence_id for item in self.produced_evidence_refs)
        _require_unique_text("produced evidence refs", evidence_ids)
        _require_aware("handoff started_at", self.started_at)
        _require_aware("handoff completed_at", self.completed_at)
        if self.completed_at < self.started_at:
            raise ValueError("handoff completed_at cannot precede started_at")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="handoff result",
        )

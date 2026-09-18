"""Typed handoff contract tests for fail-closed agent orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ai4binance.agents.evidence import (
    AgentEvidenceReference,
    AgentEvidenceStatus,
    build_handoff_evidence_ref,
)
from ai4binance.application.orchestration.handoffs import (
    accept_handoff,
    start_handoff,
    validate_handoff_envelope,
    validate_handoff_result,
)
from ai4binance.core.contracts.handoffs import (
    AuthorityScope,
    HandoffBudget,
    HandoffBudgetUsage,
    HandoffDelegation,
    HandoffEnvelope,
    HandoffEvidenceRef,
    HandoffResult,
    HandoffStatus,
)

NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
HASH = "a" * 64
ALLOWED_ROLES = ("DataQualityAgent", "LiquidityAnalysisAgent")
ALLOWED_WORKFLOWS = ("workflow-1",)


def authority(*authority_ids: str) -> AuthorityScope:
    return AuthorityScope(authority_ids=authority_ids)


def evidence_ref(
    *,
    evidence_id: str = "evidence:data-quality:1",
    snapshot_id: str = "snapshot-1",
    content_hash: str = HASH,
    confidence: float = 0.9,
) -> HandoffEvidenceRef:
    return HandoffEvidenceRef(
        evidence_id=evidence_id,
        evidence_type="DATA_QUALITY_EVIDENCE",
        producer="DataQualityAgent",
        snapshot_id=snapshot_id,
        schema_version="DataQualityEvidence/v1",
        created_at=NOW,
        content_hash=content_hash,
        confidence=confidence,
    )


def budget() -> HandoffBudget:
    return HandoffBudget(
        max_steps=3,
        max_tool_calls=1,
        max_llm_calls=0,
        max_tokens=500,
        deadline=NOW + timedelta(minutes=10),
    )


def envelope(**overrides: object) -> HandoffEnvelope:
    base: dict[str, Any] = {
        "schema_version": "HandoffEnvelope/v1",
        "handoff_id": "handoff-1",
        "root_handoff_id": "handoff-1",
        "parent_handoff_id": None,
        "workflow_id": "workflow-1",
        "cycle_id": "cycle-1",
        "snapshot_id": "snapshot-1",
        "from_role": "DataQualityAgent",
        "to_role": "LiquidityAnalysisAgent",
        "task_type": "LIQUIDITY_ANALYSIS",
        "objective": "Produce liquidity evidence for the shared snapshot.",
        "context_refs": ("context:market-snapshot:snapshot-1",),
        "evidence_refs": (evidence_ref(),),
        "blocker_refs": ("STALE_MARKET_DATA",),
        "constraints": ("NO_AUTHORITY_ESCALATION",),
        "receiver_authority": authority("READ_CONTEXT", "WRITE_EVIDENCE"),
        "sender_delegated_authority": authority(
            "READ_CONTEXT",
            "WRITE_EVIDENCE",
        ),
        "workflow_allowed_authority": authority(
            "READ_CONTEXT",
            "WRITE_EVIDENCE",
            "REQUEST_REVIEW",
        ),
        "governance_policy_authority": authority(
            "READ_CONTEXT",
            "WRITE_EVIDENCE",
            "REQUEST_REVIEW",
            "HUMAN_REVIEW",
        ),
        "allowed_tools": ("read-only-evidence",),
        "prohibited_actions": ("LIVE_ORDER", "RISK_OVERRIDE"),
        "expected_output_contract": "LiquidityEvidence/v1",
        "required_output_fields": ("snapshot_id", "evidence_refs", "blockers"),
        "budget": budget(),
        "delegation": HandoffDelegation(
            delegation_allowed=False,
            delegation_depth=0,
            max_delegation_depth=2,
        ),
        "governance_refs": (
            "docs/governance/framework_orchestration_ai_multi_agent.md",
        ),
        "policy_versions": ("AI4B-GOV-AGT-001@3.0.0",),
        "correlation_id": "correlation-1",
        "causation_id": "causation-1",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
    }
    base.update(overrides)
    return HandoffEnvelope(**base)


def result(**overrides: object) -> HandoffResult:
    base: dict[str, Any] = {
        "handoff_id": "handoff-1",
        "status": HandoffStatus.COMPLETED,
        "output_contract": "LiquidityEvidence/v1",
        "output_ref": "evidence:liquidity:1",
        "output_fields": ("snapshot_id", "evidence_refs", "blockers"),
        "produced_evidence_refs": (
            evidence_ref(
                evidence_id="evidence:liquidity:1",
                snapshot_id="snapshot-1",
            ),
        ),
        "inherited_blockers": ("STALE_MARKET_DATA",),
        "new_blockers": (),
        "warnings": (),
        "tool_usage": ("read-only-evidence:1",),
        "budget_usage": HandoffBudgetUsage(
            steps=1,
            tool_calls=1,
            llm_calls=0,
            input_tokens=100,
            output_tokens=50,
        ),
        "started_at": NOW,
        "completed_at": NOW + timedelta(seconds=5),
        "audit_ref": "audit:handoff-1",
    }
    base.update(overrides)
    return HandoffResult(**base)


def accept_valid_handoff(**overrides: object) -> HandoffEnvelope:
    return accept_handoff(
        envelope(**overrides),
        allowed_roles=ALLOWED_ROLES,
        allowed_workflows=ALLOWED_WORKFLOWS,
        now=NOW,
    )


def start_valid_handoff(**overrides: object) -> HandoffEnvelope:
    return start_handoff(accept_valid_handoff(**overrides), now=NOW)


@pytest.mark.parametrize(
    ("authority_ids", "match"),
    [
        (("READ_CONTEXT", ""), "authority scope cannot contain blanks"),
        (("READ_CONTEXT", "READ_CONTEXT"), "authority scope must be unique"),
    ],
)
def test_authority_scope_requires_nonblank_unique_ids(
    authority_ids: tuple[str, ...],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        AuthorityScope(authority_ids=authority_ids)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"execution_allowed": True}, "authority scope cannot authorize execution"),
        (
            {"promotion_status": "PAPER_ONLY"},
            "authority scope must remain research-only",
        ),
        (
            {"live_eligibility_status": "LIVE_ELIGIBLE"},
            "authority scope must remain live blocked",
        ),
    ],
)
def test_authority_scope_rejects_authority_escalation(
    override: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        AuthorityScope(authority_ids=("READ_CONTEXT",), **override)


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: evidence_ref(content_hash="not-a-sha256"),
            "content_hash must be a SHA-256 hex digest",
        ),
        (
            lambda: evidence_ref(confidence=float("nan")),
            "confidence must be between zero and one",
        ),
        (
            lambda: evidence_ref(confidence=1.01),
            "confidence must be between zero and one",
        ),
    ],
)
def test_handoff_evidence_ref_rejects_untrusted_evidence_metadata(
    factory: Callable[[], HandoffEvidenceRef],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: HandoffBudget(
                max_steps=-1,
                max_tool_calls=1,
                max_llm_calls=0,
                max_tokens=500,
                deadline=NOW + timedelta(minutes=10),
            ),
            "max_steps cannot be negative",
        ),
        (
            lambda: HandoffBudget(
                max_steps=3,
                max_tool_calls=-1,
                max_llm_calls=0,
                max_tokens=500,
                deadline=NOW + timedelta(minutes=10),
            ),
            "max_tool_calls cannot be negative",
        ),
        (
            lambda: HandoffBudget(
                max_steps=3,
                max_tool_calls=1,
                max_llm_calls=-1,
                max_tokens=500,
                deadline=NOW + timedelta(minutes=10),
            ),
            "max_llm_calls cannot be negative",
        ),
        (
            lambda: HandoffBudget(
                max_steps=3,
                max_tool_calls=1,
                max_llm_calls=0,
                max_tokens=-1,
                deadline=NOW + timedelta(minutes=10),
            ),
            "max_tokens cannot be negative",
        ),
    ],
)
def test_handoff_budget_rejects_negative_limits(
    factory: Callable[[], HandoffBudget],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


def test_handoff_budget_requires_at_least_one_step() -> None:
    with pytest.raises(ValueError, match="requires at least one step"):
        HandoffBudget(
            max_steps=0,
            max_tool_calls=1,
            max_llm_calls=0,
            max_tokens=500,
            deadline=NOW + timedelta(minutes=10),
        )


@pytest.mark.parametrize(
    "field_name",
    ["steps", "tool_calls", "llm_calls", "input_tokens", "output_tokens"],
)
def test_handoff_budget_usage_rejects_negative_usage(field_name: str) -> None:
    values = {
        "steps": 1,
        "tool_calls": 1,
        "llm_calls": 0,
        "input_tokens": 100,
        "output_tokens": 50,
        field_name: -1,
    }

    with pytest.raises(ValueError, match=f"{field_name} cannot be negative"):
        HandoffBudgetUsage(**values)


def test_handoff_envelope_rejects_cross_snapshot_evidence() -> None:
    with pytest.raises(ValueError, match="must reference the handoff snapshot"):
        envelope(evidence_refs=(evidence_ref(snapshot_id="other-snapshot"),))


def test_handoff_envelope_rejects_invalid_time_boundaries() -> None:
    with pytest.raises(ValueError, match="expires_at must be after created_at"):
        envelope(expires_at=NOW)

    with pytest.raises(ValueError, match="budget deadline cannot exceed expires_at"):
        envelope(expires_at=NOW + timedelta(minutes=5))


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"execution_allowed": True}, "handoff envelope cannot authorize execution"),
        (
            {"promotion_status": "PAPER_ONLY"},
            "handoff envelope must remain research-only",
        ),
        (
            {"live_eligibility_status": "LIVE_ELIGIBLE"},
            "handoff envelope must remain live blocked",
        ),
    ],
)
def test_handoff_envelope_rejects_authority_escalation(
    override: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        envelope(**override)


def test_completed_handoff_result_requires_output_ref() -> None:
    with pytest.raises(ValueError, match="output_ref cannot be empty"):
        result(output_ref="")


def test_handoff_result_rejects_invalid_time_order() -> None:
    with pytest.raises(ValueError, match="completed_at cannot precede started_at"):
        result(completed_at=NOW - timedelta(seconds=1))


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"execution_allowed": True}, "handoff result cannot authorize execution"),
        (
            {"promotion_status": "PAPER_ONLY"},
            "handoff result must remain research-only",
        ),
        (
            {"live_eligibility_status": "LIVE_ELIGIBLE"},
            "handoff result must remain live blocked",
        ),
    ],
)
def test_handoff_result_rejects_authority_escalation(
    override: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        result(**override)


def test_valid_handoff_accepts_without_execution_authority() -> None:
    accepted = accept_handoff(
        envelope(),
        allowed_roles=ALLOWED_ROLES,
        allowed_workflows=ALLOWED_WORKFLOWS,
        now=NOW,
    )

    assert accepted.status is HandoffStatus.ACCEPTED
    assert accepted.execution_allowed is False
    assert accepted.promotion_status == "RESEARCH_ONLY"
    assert accepted.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_handoff_rejects_receiver_authority_escalation() -> None:
    escalated = envelope(
        receiver_authority=authority(
            "READ_CONTEXT",
            "WRITE_EVIDENCE",
            "RISK_VETO",
        )
    )

    with pytest.raises(
        ValueError,
        match="receiver authority cannot exceed sender delegation",
    ):
        validate_handoff_envelope(
            escalated,
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )


def test_handoff_rejects_mixed_snapshot_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="handoff evidence must reference the handoff snapshot",
    ):
        envelope(evidence_refs=(evidence_ref(snapshot_id="other-snapshot"),))


def test_handoff_result_cannot_drop_inherited_blockers() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="dropped inherited blockers"):
        validate_handoff_result(active, result(inherited_blockers=()))


def test_handoff_result_must_match_expected_output_contract() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="output contract does not match"):
        validate_handoff_result(
            active,
            result(output_contract="TradeDecision/v1"),
        )


def test_handoff_result_must_include_required_output_fields() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="missing required output fields"):
        validate_handoff_result(
            active,
            result(output_fields=("snapshot_id", "evidence_refs")),
        )


def test_delegated_handoff_requires_bounded_parent_chain() -> None:
    parent = accept_valid_handoff(
        delegation=HandoffDelegation(
            delegation_allowed=True,
            delegation_depth=0,
            max_delegation_depth=2,
        ),
    )
    delegated = envelope(
        handoff_id="handoff-2",
        root_handoff_id="handoff-1",
        parent_handoff_id="handoff-1",
        from_role="LiquidityAnalysisAgent",
        to_role="DataQualityAgent",
        delegation=HandoffDelegation(
            delegation_allowed=True,
            delegation_depth=1,
            max_delegation_depth=2,
        ),
    )

    validated = validate_handoff_envelope(
        delegated,
        allowed_roles=ALLOWED_ROLES,
        allowed_workflows=ALLOWED_WORKFLOWS,
        now=NOW,
        parent_envelope=parent,
    )

    assert validated.status is HandoffStatus.VALIDATED


def test_delegated_handoff_requires_real_parent_envelope() -> None:
    delegated = envelope(
        handoff_id="handoff-2",
        root_handoff_id="handoff-1",
        parent_handoff_id="handoff-1",
        from_role="LiquidityAnalysisAgent",
        to_role="DataQualityAgent",
        delegation=HandoffDelegation(
            delegation_allowed=True,
            delegation_depth=1,
            max_delegation_depth=2,
        ),
    )

    with pytest.raises(ValueError, match="requires a parent envelope"):
        validate_handoff_envelope(
            delegated,
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )


def test_handoff_validation_requires_registered_roles() -> None:
    with pytest.raises(ValueError, match="unknown allowed roles"):
        validate_handoff_envelope(
            envelope(),
            allowed_roles=("DataQualityAgent",),
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )


def test_handoff_validation_requires_registered_workflow() -> None:
    with pytest.raises(ValueError, match="unknown allowed workflows"):
        validate_handoff_envelope(
            envelope(),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=("workflow-other",),
            now=NOW,
        )


def test_handoff_validation_rejects_time_and_registry_boundary_failures() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_handoff_envelope(
            envelope(),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=datetime(2026, 8, 21, 9, 0),
        )
    with pytest.raises(ValueError, match="must start in CREATED"):
        validate_handoff_envelope(
            envelope(status=HandoffStatus.ACCEPTED),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )
    with pytest.raises(ValueError, match="envelope has expired"):
        validate_handoff_envelope(
            envelope(
                budget=HandoffBudget(
                    1,
                    1,
                    0,
                    100,
                    NOW + timedelta(seconds=1),
                ),
                expires_at=NOW + timedelta(seconds=1),
            ),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="budget deadline has expired"):
        validate_handoff_envelope(
            envelope(
                budget=HandoffBudget(
                    1,
                    1,
                    0,
                    100,
                    NOW + timedelta(seconds=1),
                ),
                expires_at=NOW + timedelta(seconds=10),
            ),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="distinct from_role and to_role"):
        validate_handoff_envelope(
            envelope(to_role="DataQualityAgent"),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )
    with pytest.raises(ValueError, match="requires allowed roles registry"):
        validate_handoff_envelope(
            envelope(),
            allowed_roles=(),
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("context_refs", "context references"),
        ("evidence_refs", "evidence references"),
        ("governance_refs", "governance references"),
        ("policy_versions", "policy version references"),
    ],
)
def test_handoff_validation_requires_core_reference_sets(
    field: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_handoff_envelope(
            envelope(**{field: ()}),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )


def test_handoff_result_requires_in_progress_state() -> None:
    accepted = accept_valid_handoff()

    with pytest.raises(ValueError, match="in-progress envelope"):
        validate_handoff_result(accepted, result())


def test_handoff_result_rejects_unauthorized_tool_usage() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="unauthorized tool"):
        validate_handoff_result(
            active,
            result(tool_usage=("write-gateway:1",)),
        )


def test_handoff_result_rejects_budget_overrun() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="tool-call budget exceeded"):
        validate_handoff_result(
            active,
            result(
                tool_usage=("read-only-evidence:1", "read-only-evidence:2"),
                budget_usage=HandoffBudgetUsage(
                    steps=1,
                    tool_calls=2,
                    llm_calls=0,
                    input_tokens=100,
                    output_tokens=50,
                ),
            ),
        )


def test_handoff_result_rejects_terminal_time_tool_and_budget_failures() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="terminal lifecycle"):
        validate_handoff_result(active, result(status=HandoffStatus.IN_PROGRESS))
    with pytest.raises(ValueError, match="identity does not match"):
        validate_handoff_result(active, result(handoff_id="other-handoff"))
    with pytest.raises(ValueError, match="envelope snapshot"):
        validate_handoff_result(
            active,
            result(
                produced_evidence_refs=(
                    evidence_ref(
                        evidence_id="evidence:liquidity:2",
                        snapshot_id="other-snapshot",
                    ),
                )
            ),
        )
    with pytest.raises(ValueError, match="started after envelope expiry"):
        validate_handoff_result(
            active,
            result(
                started_at=active.expires_at + timedelta(seconds=1),
                completed_at=active.expires_at + timedelta(seconds=2),
            ),
        )
    with pytest.raises(ValueError, match="completed after envelope expiry"):
        validate_handoff_result(
            active,
            result(completed_at=active.expires_at + timedelta(seconds=1)),
        )
    with pytest.raises(ValueError, match="completed after budget deadline"):
        validate_handoff_result(
            active,
            result(completed_at=active.budget.deadline + timedelta(seconds=1)),
        )
    with pytest.raises(ValueError, match="tool usage count"):
        validate_handoff_result(
            active,
            result(tool_usage=()),
        )
    with pytest.raises(ValueError, match="prohibited action"):
        validate_handoff_result(
            active,
            result(tool_usage=("read-only-evidence:LIVE_ORDER",)),
        )
    with pytest.raises(ValueError, match="handoff step budget exceeded"):
        validate_handoff_result(
            active,
            result(
                budget_usage=HandoffBudgetUsage(
                    steps=4,
                    tool_calls=1,
                    llm_calls=0,
                    input_tokens=100,
                    output_tokens=50,
                )
            ),
        )


def test_delegated_handoff_rejects_parent_chain_mismatches() -> None:
    parent = accept_valid_handoff(
        delegation=HandoffDelegation(
            delegation_allowed=True,
            delegation_depth=0,
            max_delegation_depth=2,
        ),
    )

    def delegated(**overrides: object) -> HandoffEnvelope:
        base: dict[str, object] = {
            "handoff_id": "handoff-2",
            "root_handoff_id": "handoff-1",
            "parent_handoff_id": "handoff-1",
            "from_role": "LiquidityAnalysisAgent",
            "to_role": "DataQualityAgent",
            "delegation": HandoffDelegation(
                delegation_allowed=True,
                delegation_depth=1,
                max_delegation_depth=2,
            ),
        }
        return envelope(**(base | overrides))

    cases = (
        (
            delegated(parent_handoff_id="handoff-3"),
            "parent identity",
            ALLOWED_WORKFLOWS,
        ),
        (
            delegated(root_handoff_id="other-root"),
            "root identity",
            ALLOWED_WORKFLOWS,
        ),
        (
            delegated(workflow_id="other-workflow"),
            "workflow_id must match parent",
            ("workflow-1", "other-workflow"),
        ),
        (
            delegated(
                from_role="DataQualityAgent",
                to_role="LiquidityAnalysisAgent",
            ),
            "sender must be the parent receiver",
            ALLOWED_WORKFLOWS,
        ),
        (
            delegated(
                delegation=HandoffDelegation(
                    delegation_allowed=True,
                    delegation_depth=2,
                    max_delegation_depth=2,
                )
            ),
            "depth must extend parent",
            ALLOWED_WORKFLOWS,
        ),
        (
            delegated(expires_at=parent.expires_at + timedelta(seconds=1)),
            "expiry cannot exceed parent",
            ALLOWED_WORKFLOWS,
        ),
        (
            delegated(allowed_tools=("read-only-evidence", "extra-tool")),
            "tools cannot exceed parent",
            ALLOWED_WORKFLOWS,
        ),
    )
    for invalid, message, workflows in cases:
        with pytest.raises(ValueError, match=message):
            validate_handoff_envelope(
                invalid,
                allowed_roles=ALLOWED_ROLES,
                allowed_workflows=workflows,
                now=NOW,
                parent_envelope=parent,
            )


def test_handoff_start_rejects_invalid_lifecycle_and_deadlines() -> None:
    accepted = accept_valid_handoff()

    with pytest.raises(ValueError, match="ACCEPTED state"):
        start_handoff(envelope(), now=NOW)
    with pytest.raises(ValueError, match="envelope has expired"):
        start_handoff(
            accept_valid_handoff(
                budget=HandoffBudget(
                    1,
                    1,
                    0,
                    100,
                    NOW + timedelta(seconds=1),
                ),
                expires_at=NOW + timedelta(seconds=1),
            ),
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="budget deadline has expired"):
        start_handoff(
            accept_valid_handoff(
                budget=HandoffBudget(
                    1,
                    1,
                    0,
                    100,
                    NOW + timedelta(seconds=1),
                ),
                expires_at=NOW + timedelta(seconds=10),
            ),
            now=NOW + timedelta(seconds=1),
        )

    assert start_handoff(accepted, now=NOW).status is HandoffStatus.IN_PROGRESS


def test_handoff_validation_rejects_authority_chain_mismatches() -> None:
    with pytest.raises(ValueError, match="sender delegation cannot exceed workflow"):
        validate_handoff_envelope(
            envelope(
                workflow_allowed_authority=authority("READ_CONTEXT"),
            ),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )
    with pytest.raises(ValueError, match="workflow authority cannot exceed governance"):
        validate_handoff_envelope(
            envelope(
                governance_policy_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                ),
            ),
            allowed_roles=ALLOWED_ROLES,
            allowed_workflows=ALLOWED_WORKFLOWS,
            now=NOW,
        )


def test_delegated_handoff_rejects_structural_delegation_failures() -> None:
    parent = accept_valid_handoff(
        delegation=HandoffDelegation(
            delegation_allowed=True,
            delegation_depth=0,
            max_delegation_depth=2,
        ),
    )

    def delegated(**overrides: object) -> HandoffEnvelope:
        base: dict[str, object] = {
            "handoff_id": "handoff-2",
            "root_handoff_id": "handoff-1",
            "parent_handoff_id": "handoff-1",
            "from_role": "LiquidityAnalysisAgent",
            "to_role": "DataQualityAgent",
            "delegation": HandoffDelegation(
                delegation_allowed=True,
                delegation_depth=1,
                max_delegation_depth=2,
            ),
        }
        return envelope(**(base | overrides))

    structural_cases = (
        (
            envelope(),
            parent,
            "root handoff cannot provide a parent envelope",
        ),
        (envelope(root_handoff_id="handoff-2"), None, "root handoff must reference"),
        (
            envelope(
                delegation=HandoffDelegation(
                    delegation_allowed=True,
                    delegation_depth=1,
                    max_delegation_depth=2,
                )
            ),
            None,
            "root handoff delegation depth must be zero",
        ),
        (
            envelope(
                handoff_id="handoff-2",
                parent_handoff_id="handoff-2",
            ),
            parent,
            "cannot be its own parent",
        ),
        (
            envelope(
                handoff_id="handoff-2",
                root_handoff_id="handoff-2",
                parent_handoff_id="handoff-1",
            ),
            parent,
            "root must differ",
        ),
        (
            envelope(
                handoff_id="handoff-2",
                root_handoff_id="handoff-1",
                parent_handoff_id="handoff-1",
            ),
            parent,
            "requires delegation permission",
        ),
        (
            delegated(
                delegation=HandoffDelegation(
                    delegation_allowed=True,
                    delegation_depth=1,
                    max_delegation_depth=3,
                )
            ),
            parent,
            "max depth cannot exceed parent",
        ),
        (
            delegated(
                budget=HandoffBudget(
                    max_steps=3,
                    max_tool_calls=1,
                    max_llm_calls=0,
                    max_tokens=500,
                    deadline=parent.budget.deadline + timedelta(seconds=1),
                ),
                expires_at=parent.expires_at,
            ),
            parent,
            "deadline cannot exceed parent",
        ),
        (
            delegated(
                receiver_authority=authority("READ_CONTEXT", "REQUEST_REVIEW"),
                sender_delegated_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                    "REQUEST_REVIEW",
                ),
                workflow_allowed_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                    "REQUEST_REVIEW",
                ),
                governance_policy_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                    "REQUEST_REVIEW",
                    "HUMAN_REVIEW",
                ),
            ),
            parent,
            "receiver authority cannot exceed parent",
        ),
        (
            delegated(
                sender_delegated_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                    "REQUEST_REVIEW",
                ),
                workflow_allowed_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                    "REQUEST_REVIEW",
                ),
                governance_policy_authority=authority(
                    "READ_CONTEXT",
                    "WRITE_EVIDENCE",
                    "REQUEST_REVIEW",
                    "HUMAN_REVIEW",
                ),
            ),
            parent,
            "sender authority cannot exceed parent",
        ),
        (
            delegated(prohibited_actions=("LIVE_ORDER",)),
            parent,
            "cannot weaken prohibited actions",
        ),
        (
            delegated(
                budget=HandoffBudget(
                    max_steps=4,
                    max_tool_calls=1,
                    max_llm_calls=0,
                    max_tokens=500,
                    deadline=NOW + timedelta(minutes=10),
                )
            ),
            parent,
            "step budget cannot exceed parent",
        ),
        (
            delegated(
                budget=HandoffBudget(
                    max_steps=3,
                    max_tool_calls=2,
                    max_llm_calls=0,
                    max_tokens=500,
                    deadline=NOW + timedelta(minutes=10),
                )
            ),
            parent,
            "tool budget cannot exceed parent",
        ),
        (
            delegated(
                budget=HandoffBudget(
                    max_steps=3,
                    max_tool_calls=1,
                    max_llm_calls=1,
                    max_tokens=500,
                    deadline=NOW + timedelta(minutes=10),
                )
            ),
            parent,
            "llm budget cannot exceed parent",
        ),
        (
            delegated(
                budget=HandoffBudget(
                    max_steps=3,
                    max_tool_calls=1,
                    max_llm_calls=0,
                    max_tokens=501,
                    deadline=NOW + timedelta(minutes=10),
                )
            ),
            parent,
            "token budget cannot exceed parent",
        ),
    )

    for invalid, parent_envelope, message in structural_cases:
        with pytest.raises(ValueError, match=message):
            validate_handoff_envelope(
                invalid,
                allowed_roles=ALLOWED_ROLES,
                allowed_workflows=ALLOWED_WORKFLOWS,
                now=NOW,
                parent_envelope=parent_envelope,
            )


def test_handoff_result_rejects_llm_and_token_budget_overruns() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="llm-call budget exceeded"):
        validate_handoff_result(
            active,
            result(
                budget_usage=HandoffBudgetUsage(
                    steps=1,
                    tool_calls=1,
                    llm_calls=1,
                    input_tokens=100,
                    output_tokens=50,
                )
            ),
        )
    with pytest.raises(ValueError, match="token budget exceeded"):
        validate_handoff_result(
            active,
            result(
                budget_usage=HandoffBudgetUsage(
                    steps=1,
                    tool_calls=1,
                    llm_calls=0,
                    input_tokens=400,
                    output_tokens=101,
                )
            ),
        )


def test_delegation_depth_cannot_exceed_maximum() -> None:
    with pytest.raises(
        ValueError,
        match="delegation depth exceeds maximum delegation depth",
    ):
        HandoffDelegation(
            delegation_allowed=True,
            delegation_depth=3,
            max_delegation_depth=2,
        )


def test_completed_handoff_result_requires_produced_evidence() -> None:
    active = start_valid_handoff()

    with pytest.raises(ValueError, match="requires produced evidence references"):
        validate_handoff_result(active, result(produced_evidence_refs=()))


def test_agent_evidence_adapter_requires_content_hash() -> None:
    reference = AgentEvidenceReference(
        evidence_id="agent-evidence-1",
        source_id="source-1",
        claim="Shared snapshot is stale.",
        status=AgentEvidenceStatus.VERIFIED,
        observed_at=NOW,
        content_hash=None,
    )

    with pytest.raises(ValueError, match="requires a content_hash"):
        build_handoff_evidence_ref(
            reference,
            producer="DataQualityAgent",
            snapshot_id="snapshot-1",
            confidence=1.0,
        )


def test_agent_evidence_adapter_builds_handoff_reference() -> None:
    reference = AgentEvidenceReference(
        evidence_id="agent-evidence-1",
        source_id="source-1",
        claim="Shared snapshot is stale.",
        status=AgentEvidenceStatus.VERIFIED,
        observed_at=NOW,
        content_hash=HASH,
    )

    handoff_ref = build_handoff_evidence_ref(
        reference,
        producer="DataQualityAgent",
        snapshot_id="snapshot-1",
        confidence=1.0,
    )

    assert handoff_ref.evidence_id == reference.evidence_id
    assert handoff_ref.snapshot_id == "snapshot-1"
    assert handoff_ref.content_hash == HASH

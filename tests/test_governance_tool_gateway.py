from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.governance import (
    CapabilityStore,
    OutcomeStatus,
    OutcomeVerification,
    RunContext,
    ToolDescriptor,
    ToolGateway,
    ToolLoopGuard,
    ToolLoopGuardConfig,
    ToolOutcome,
    ToolOutcomeStatus,
    ToolPermission,
    ToolPolicyDecision,
    ToolPolicyDocument,
    ToolPolicyEngine,
    ToolPolicyRule,
    ToolRegistry,
    ToolSideEffect,
    deny_all_tool_policy,
)


def read_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        name="quality-triage",
        description="Read local quality triage artifacts",
        allowed_projects=("ai4binance",),
        side_effect=ToolSideEffect.READ_LOCAL,
        tags=("quality", "triage"),
        schema_tokens=64,
    )


def test_tool_registry_shortlist_hides_dangerous_tools() -> None:
    registry = ToolRegistry(
        (
            read_descriptor(),
            ToolDescriptor(
                name="submit-order",
                description="Forbidden financial order submission",
                allowed_projects=("ai4binance",),
                side_effect=ToolSideEffect.FINANCIAL,
                tags=("order",),
            ),
        )
    )

    selection = registry.shortlist("quality order triage", project="ai4binance")

    assert tuple(item.name for item in selection.selected) == ("quality-triage",)
    assert selection.schema_tokens == 64


def test_policy_default_denies_and_dangerous_allow_rules_are_rejected() -> None:
    policy = ToolPolicyEngine(deny_all_tool_policy())
    result = policy.evaluate(
        read_descriptor(),
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
    )

    assert result.decision is ToolPolicyDecision.DENY
    assert result.reason_codes == ("POLICY_DEFAULT_DENY",)
    with pytest.raises(ValueError, match="dangerous"):
        ToolPolicyRule(
            "bad",
            ToolPolicyDecision.ALLOW,
            ("submit-order",),
            ("ai4binance",),
            (ToolPermission.WRITE_APPROVED,),
            (ToolSideEffect.FINANCIAL,),
        )


def test_tool_policy_contracts_reject_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="identity"):
        ToolDescriptor("", "desc", ("ai4binance",), ToolSideEffect.READ_LOCAL)
    with pytest.raises(ValueError, match="allowed projects"):
        ToolDescriptor("tool", "desc", (), ToolSideEffect.READ_LOCAL)
    with pytest.raises(ValueError, match="tags"):
        ToolDescriptor(
            "tool",
            "desc",
            ("ai4binance",),
            ToolSideEffect.READ_LOCAL,
            tags=("a", "a"),
        )
    with pytest.raises(ValueError, match="schema"):
        ToolDescriptor(
            "tool",
            "desc",
            ("ai4binance",),
            ToolSideEffect.READ_LOCAL,
            schema_tokens=-1,
        )
    with pytest.raises(ValueError, match="selectors"):
        ToolPolicyRule(
            "",
            ToolPolicyDecision.DENY,
            ("tool",),
            ("ai4binance",),
            (ToolPermission.READ_ONLY,),
            (ToolSideEffect.READ_LOCAL,),
        )
    rule = ToolPolicyRule(
        "same",
        ToolPolicyDecision.DENY,
        ("tool",),
        ("ai4binance",),
        (ToolPermission.READ_ONLY,),
        (ToolSideEffect.READ_LOCAL,),
    )
    with pytest.raises(ValueError, match="identity"):
        ToolPolicyDocument("", "1")
    with pytest.raises(ValueError, match="default"):
        ToolPolicyDocument("policy", "1", default=ToolPolicyDecision.ALLOW)
    with pytest.raises(ValueError, match="rule IDs"):
        ToolPolicyDocument("policy", "1", rules=(rule, rule))


def test_policy_require_approval_flow_and_registry_degraded_paths() -> None:
    descriptor = read_descriptor()
    approval_rule = ToolPolicyRule(
        "approve-read",
        ToolPolicyDecision.REQUIRE_APPROVAL,
        ("quality-triage",),
        ("ai4binance",),
        (ToolPermission.READ_ONLY,),
        (ToolSideEffect.READ_LOCAL,),
    )
    policy = ToolPolicyEngine(ToolPolicyDocument("policy", "1", rules=(approval_rule,)))
    assert (
        policy.evaluate(
            descriptor,
            project="ai4binance",
            permission=ToolPermission.READ_ONLY,
            approved=False,
        ).decision
        is ToolPolicyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate(
            descriptor,
            project="ai4binance",
            permission=ToolPermission.READ_ONLY,
            approved=True,
        ).decision
        is ToolPolicyDecision.ALLOW
    )
    registry = ToolRegistry((descriptor,))
    with pytest.raises(PermissionError, match="TOOL_NOT_REGISTERED"):
        registry.require("missing")
    with pytest.raises(ValueError, match="unique"):
        ToolRegistry((descriptor, descriptor))
    with pytest.raises(ValueError, match="max_tools"):
        registry.shortlist("quality", project="ai4binance", max_tools=0)
    assert registry.shortlist(" ", project="ai4binance").blockers == ("NO_TOOL_MATCH",)
    assert registry.shortlist("quality", project="other").blockers == ("NO_TOOL_MATCH",)
    assert registry.shortlist(
        "quality",
        project="ai4binance",
        max_schema_tokens=1,
    ).blockers == ("NO_TOOL_MATCH",)


def test_gateway_attests_not_executed_unknown_and_success_outcomes() -> None:
    registry = ToolRegistry((read_descriptor(),))
    policy = ToolPolicyEngine(
        ToolPolicyDocument(
            "policy",
            "1",
            rules=(
                ToolPolicyRule(
                    "allow-read",
                    ToolPolicyDecision.ALLOW,
                    ("quality-triage",),
                    ("ai4binance",),
                    (ToolPermission.READ_ONLY,),
                    (ToolSideEffect.READ_LOCAL,),
                ),
            ),
        )
    )
    gateway = ToolGateway(registry, policy)
    blocked = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.NETWORK_READ,
        approved=False,
        operation=lambda: "should not run",
    )
    assert blocked.value is None
    assert blocked.record.outcome.status is ToolOutcomeStatus.NOT_EXECUTED
    assert blocked.record.execution_allowed is False
    assert blocked.record.decision_record is not None
    assert blocked.record.outcome_attestation is not None
    assert blocked.record.outcome_attestation.outcome is OutcomeStatus.NOT_EXECUTED

    unknown = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: "read",
    )
    assert unknown.value == "read"
    assert unknown.record.outcome.status is ToolOutcomeStatus.UNKNOWN
    assert unknown.record.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert unknown.record.outcome_attestation is not None
    assert unknown.record.outcome_attestation.outcome is OutcomeStatus.UNKNOWN

    succeeded = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: "read",
        outcome_validator=lambda value: ToolOutcome(
            ToolOutcomeStatus.SUCCEEDED,
            (),
        ),
        attestation_validator=lambda value: OutcomeVerification(
            OutcomeStatus.SUCCEEDED,
            "test_validator",
            (),
        ),
        run_context=RunContext("run-1", "read-step"),
        evidence_hashes=("a" * 64,),
    )
    assert succeeded.value == "read"
    assert succeeded.record.outcome.status is ToolOutcomeStatus.SUCCEEDED
    assert succeeded.record.decision_record is not None
    assert succeeded.record.decision_record.run_id == "run-1"
    assert succeeded.record.outcome_attestation is not None
    assert succeeded.record.outcome_attestation.validator == "test_validator"


def test_gateway_consumes_capability_before_allowed_execution(tmp_path: Path) -> None:
    registry = ToolRegistry((read_descriptor(),))
    policy = ToolPolicyEngine(
        ToolPolicyDocument(
            "policy",
            "1",
            rules=(
                ToolPolicyRule(
                    "allow-read",
                    ToolPolicyDecision.ALLOW,
                    ("quality-triage",),
                    ("ai4binance",),
                    (ToolPermission.READ_ONLY,),
                    (ToolSideEffect.READ_LOCAL,),
                ),
            ),
        )
    )
    gateway = ToolGateway(registry, policy, capability_store=CapabilityStore(tmp_path))

    result = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: "read",
    )

    assert result.value == "read"
    assert result.record.capability_lease is not None
    assert result.record.capability_lease.consumed_at is not None
    assert result.record.decision_record is not None
    assert (
        result.record.decision_record.capability_lease_id
        == result.record.capability_lease.lease_id
    )


def test_gateway_blocks_repeated_no_progress_before_execution() -> None:
    registry = ToolRegistry((read_descriptor(),))
    policy = ToolPolicyEngine(
        ToolPolicyDocument(
            "policy",
            "1",
            rules=(
                ToolPolicyRule(
                    "allow-read",
                    ToolPolicyDecision.ALLOW,
                    ("quality-triage",),
                    ("ai4binance",),
                    (ToolPermission.READ_ONLY,),
                    (ToolSideEffect.READ_LOCAL,),
                ),
            ),
        )
    )
    gateway = ToolGateway(
        registry,
        policy,
        loop_guard=ToolLoopGuard(
            ToolLoopGuardConfig(no_progress_warn_after=1, no_progress_block_after=1)
        ),
    )

    first = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: {"status": "same"},
        tool_arguments={"source": "state"},
    )
    second = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: {"status": "should-not-run"},
        tool_arguments={"source": "state"},
    )

    assert first.value == {"status": "same"}
    assert first.record.loop_after is not None
    assert second.value is None
    assert second.record.outcome.status is ToolOutcomeStatus.NOT_EXECUTED
    assert second.record.loop_before is not None
    assert second.record.loop_before.code == "IDEMPOTENT_NO_PROGRESS_BLOCKED"


def test_gateway_failure_and_record_contracts_are_fail_closed() -> None:
    registry = ToolRegistry((read_descriptor(),))
    policy = ToolPolicyEngine(
        ToolPolicyDocument(
            "policy",
            "1",
            rules=(
                ToolPolicyRule(
                    "allow-read",
                    ToolPolicyDecision.ALLOW,
                    ("quality-triage",),
                    ("ai4binance",),
                    (ToolPermission.READ_ONLY,),
                    (ToolSideEffect.READ_LOCAL,),
                ),
            ),
        )
    )
    gateway = ToolGateway(registry, policy)
    missing = gateway.execute(
        tool="missing",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: "nope",
    )
    assert missing.record.outcome.status is ToolOutcomeStatus.NOT_EXECUTED

    failed = gateway.execute(
        tool="quality-triage",
        project="ai4binance",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        operation=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert failed.record.outcome.status is ToolOutcomeStatus.FAILED
    with pytest.raises(ValueError, match="requires reasons"):
        ToolOutcome(ToolOutcomeStatus.FAILED, ())
    with pytest.raises(ValueError, match="identity"):
        failed.record.__class__(
            "",
            "ai4binance",
            ToolPolicyDecision.ALLOW,
            (),
            ToolOutcome(ToolOutcomeStatus.SUCCEEDED, ()),
        )
    with pytest.raises(ValueError, match="authorize"):
        failed.record.__class__(
            "tool",
            "ai4binance",
            ToolPolicyDecision.ALLOW,
            (),
            ToolOutcome(ToolOutcomeStatus.SUCCEEDED, ()),
            execution_allowed=True,
        )

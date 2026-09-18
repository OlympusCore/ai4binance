from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.governance import (
    CANONICAL_MCP_ROUTE,
    DEFAULT_DENIED_MCP_TOOLS,
    EXECUTION_SENSITIVE_MCP_TOOLS,
    CapabilityStore,
    CapabilityToolPermission,
    McpAuthorityClass,
    McpGatewayContract,
    McpGatewayKind,
    McpRouteStep,
    McpToolPolicy,
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
    ToolPermissionAction,
    ToolPolicyDecision,
    ToolPolicyDocument,
    ToolPolicyEngine,
    ToolPolicyRule,
    ToolRegistry,
    ToolSelection,
    ToolSideEffect,
    build_ai4binance_mcp_gateway_contract,
    classify_mcp_tool_authority,
    deny_all_tool_policy,
)
from ai4binance.governance.mcp_gateway import McpAuthorizationResult


def read_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        name="quality-triage",
        description="Read local quality triage artifacts",
        allowed_projects=("ai4binance",),
        side_effect=ToolSideEffect.READ_LOCAL,
        tags=("quality", "triage"),
        schema_tokens=64,
    )


def test_capability_tool_permission_requires_governed_chain() -> None:
    permission = CapabilityToolPermission(
        principal="news_agent",
        capability_id="NEWS_CLAIM_EXTRACTION",
        resource="evidence_store",
        tool="evidence_store.append",
        actions=(ToolPermissionAction.READ, ToolPermissionAction.APPEND),
        denied=(ToolPermissionAction.DELETE, ToolPermissionAction.EXECUTE_ORDER),
    )

    assert permission.principal == "news_agent"
    assert permission.capability_id == "NEWS_CLAIM_EXTRACTION"
    assert ToolPermissionAction.EXECUTE_ORDER in permission.denied

    with pytest.raises(ValueError, match="dangerous"):
        CapabilityToolPermission(
            principal="news_agent",
            capability_id="NEWS_CLAIM_EXTRACTION",
            resource="evidence_store",
            tool="evidence_store.delete",
            actions=(ToolPermissionAction.DELETE,),
            denied=(),
        )

    with pytest.raises(ValueError, match="EXECUTE_ORDER"):
        CapabilityToolPermission(
            principal="news_agent",
            capability_id="NEWS_CLAIM_EXTRACTION",
            resource="evidence_store",
            tool="evidence_store.append",
            actions=(ToolPermissionAction.READ,),
            denied=(ToolPermissionAction.DELETE,),
        )

    with pytest.raises(ValueError, match="OrderGateway"):
        CapabilityToolPermission(
            principal="llm_agent",
            capability_id="ADVISORY_ASSESSMENT",
            resource="OrderGateway",
            tool="OrderGateway",
            actions=(ToolPermissionAction.READ,),
            llm_based_agent=True,
            exposed=True,
        )


def test_mcp_gateway_contract_forces_policy_authorization_route() -> None:
    gateway = build_ai4binance_mcp_gateway_contract()

    assert gateway.gateways == (
        McpGatewayKind.FILESYSTEM,
        McpGatewayKind.GITHUB,
        McpGatewayKind.POSTGRESQL,
        McpGatewayKind.RESEARCH,
        McpGatewayKind.WOLFRAM,
        McpGatewayKind.QUANT_RESEARCH,
        McpGatewayKind.MARKET_DATA,
        McpGatewayKind.EVIDENCE,
        McpGatewayKind.GOVERNANCE,
        McpGatewayKind.BINANCE_READ_ONLY,
    )
    assert gateway.route == (
        McpRouteStep.AGENT,
        McpRouteStep.TOOL_POLICY,
        McpRouteStep.AUTHORIZATION,
        McpRouteStep.MCP_GATEWAY,
        McpRouteStep.TOOL,
    )
    assert gateway.route == CANONICAL_MCP_ROUTE
    assert gateway.direct_agent_to_mcp_allowed is False
    assert gateway.execution_allowed is False
    assert gateway.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    allowed = gateway.authorize(agent="research_agent", tool="github.search")
    assert allowed.mcp_invocation_allowed is True
    assert allowed.execution_allowed is False
    assert allowed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    quant_allowed = gateway.authorize(
        agent="research_agent",
        tool="quant_research.verify_formula",
    )
    assert quant_allowed.mcp_invocation_allowed is True
    assert quant_allowed.execution_allowed is False
    assert quant_allowed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    wolfram_status_allowed = gateway.authorize(
        agent="research_agent",
        tool="quant_research.wolfram_status",
    )
    assert wolfram_status_allowed.mcp_invocation_allowed is True
    assert wolfram_status_allowed.execution_allowed is False
    assert wolfram_status_allowed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    market_allowed = gateway.authorize(
        agent="research_agent",
        tool="market.get_snapshot",
    )
    assert market_allowed.mcp_invocation_allowed is True
    assert market_allowed.execution_allowed is False
    assert market_allowed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    denied = gateway.authorize(agent="research_agent", tool="exchange.place_order")
    assert denied.decision is ToolPolicyDecision.DENY
    assert denied.reason_codes == ("MCP_TOOL_DENIED",)

    default_denied = gateway.authorize(
        agent="research_agent",
        tool="filesystem.write",
    )
    assert default_denied.decision is ToolPolicyDecision.DENY
    assert default_denied.reason_codes == ("MCP_POLICY_DEFAULT_DENY",)

    missing_agent_policy = gateway.authorize(
        agent="market_agent",
        tool="github.search",
    )
    assert missing_agent_policy.decision is ToolPolicyDecision.DENY
    assert missing_agent_policy.reason_codes == ("MCP_AGENT_POLICY_MISSING",)


def test_mcp_tool_policy_rejects_shortcuts_and_destructive_tools() -> None:
    policy = McpToolPolicy(
        agent="research_agent",
        allowed=("github.search", "filesystem.read"),
    )

    assert policy.denied == DEFAULT_DENIED_MCP_TOOLS
    assert policy.direct_agent_to_mcp_allowed is False
    assert (
        policy.authorize(
            agent="research_agent",
            tool="filesystem.read",
        ).mcp_invocation_allowed
        is True
    )

    with pytest.raises(ValueError, match="direct agent to MCP"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            direct_agent_to_mcp_allowed=True,
        )
    with pytest.raises(ValueError, match="destructive and order"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            denied=("filesystem.delete", "shell.admin"),
        )
    with pytest.raises(ValueError, match="cannot also be denied"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            denied=(*DEFAULT_DENIED_MCP_TOOLS, "github.search"),
        )
    with pytest.raises(ValueError, match="canonical"):
        McpGatewayContract(route=tuple(reversed(CANONICAL_MCP_ROUTE)))
    with pytest.raises(ValueError, match="cannot grant trading authority"):
        McpGatewayContract(execution_allowed=True)


def test_mcp_gateway_contract_rejects_invalid_shapes_and_shortcuts() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        classify_mcp_tool_authority(" ")

    with pytest.raises(ValueError, match="requires reason codes"):
        McpAuthorizationResult(
            agent="research_agent",
            tool="github.search",
            decision=ToolPolicyDecision.DENY,
            reason_codes=(),
        )
    with pytest.raises(ValueError, match="route must be canonical"):
        McpAuthorizationResult(
            agent="research_agent",
            tool="github.search",
            decision=ToolPolicyDecision.DENY,
            reason_codes=("MCP_TOOL_DENIED",),
            route=tuple(reversed(CANONICAL_MCP_ROUTE)),
        )
    with pytest.raises(ValueError, match="cannot grant trading authority"):
        McpAuthorizationResult(
            agent="research_agent",
            tool="github.search",
            decision=ToolPolicyDecision.DENY,
            reason_codes=("MCP_TOOL_DENIED",),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="requires allowed tools"):
        McpToolPolicy(agent="research_agent", allowed=())
    with pytest.raises(ValueError, match="cannot contain empty values"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            denied=(" ",),
        )
    with pytest.raises(ValueError, match="cannot also be denied"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            denied=(*DEFAULT_DENIED_MCP_TOOLS, "github.search"),
        )
    with pytest.raises(ValueError, match="Agent -> Tool Policy -> Authorization"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            route=tuple(reversed(CANONICAL_MCP_ROUTE)),
        )
    with pytest.raises(ValueError, match="must deny"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            default_decision=ToolPolicyDecision.ALLOW,
        )
    with pytest.raises(ValueError, match="prohibited"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            direct_agent_to_mcp_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot also be denied"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("github.search",),
            denied=("github.search",),
        )
    with pytest.raises(ValueError, match="must list every gateway kind"):
        McpGatewayContract(gateways=())
    with pytest.raises(ValueError, match="requires at least one tool policy"):
        McpGatewayContract(policies=())
    with pytest.raises(ValueError, match="policy agents"):
        McpGatewayContract(
            policies=(
                McpToolPolicy(
                    agent="research_agent",
                    allowed=("github.search",),
                ),
                McpToolPolicy(
                    agent="research_agent",
                    allowed=("filesystem.read",),
                ),
            )
        )
    with pytest.raises(ValueError, match="prohibited"):
        McpGatewayContract(direct_agent_to_mcp_allowed=True)
    with pytest.raises(ValueError, match="cannot grant trading authority"):
        McpGatewayContract(live_eligibility_status="READY")
    with pytest.raises(ValueError, match="requires reason codes"):
        McpAuthorizationResult(
            agent="research_agent",
            tool="github.search",
            decision=ToolPolicyDecision.DENY,
            reason_codes=(),
        )
    with pytest.raises(ValueError, match="route must be canonical"):
        McpAuthorizationResult(
            agent="research_agent",
            tool="github.search",
            decision=ToolPolicyDecision.DENY,
            reason_codes=("MCP_TOOL_DENIED",),
            route=tuple(reversed(CANONICAL_MCP_ROUTE)),
        )
    with pytest.raises(ValueError, match="cannot grant trading authority"):
        McpAuthorizationResult(
            agent="research_agent",
            tool="github.search",
            decision=ToolPolicyDecision.DENY,
            reason_codes=("MCP_TOOL_DENIED",),
            execution_allowed=True,
        )


def test_mcp_authority_class_blocks_execution_sensitive_tools() -> None:
    assert (
        classify_mcp_tool_authority("market.get_snapshot")
        is McpAuthorityClass.MCP_R0_READ_ONLY
    )
    assert (
        classify_mcp_tool_authority("quant_research.verify_formula")
        is McpAuthorityClass.MCP_R1_ANALYZE_COMPUTE
    )
    assert (
        classify_mcp_tool_authority("wolfram.evaluate")
        is McpAuthorityClass.MCP_R1_ANALYZE_COMPUTE
    )
    assert (
        classify_mcp_tool_authority("evidence.register")
        is McpAuthorityClass.MCP_R2_CREATE_RESEARCH_ARTIFACTS
    )
    assert (
        classify_mcp_tool_authority("order.live.submit")
        is McpAuthorityClass.MCP_X_EXECUTION_SENSITIVE
    )
    assert "order.live.submit" in EXECUTION_SENSITIVE_MCP_TOOLS
    assert set(EXECUTION_SENSITIVE_MCP_TOOLS).issubset(DEFAULT_DENIED_MCP_TOOLS)

    with pytest.raises(ValueError, match="execution-sensitive"):
        McpToolPolicy(
            agent="research_agent",
            allowed=("live.inspect",),
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


def test_tool_registry_selection_and_shortlist_edges_are_fail_closed() -> None:
    registry = ToolRegistry(
        (
            read_descriptor(),
            ToolDescriptor(
                name="alternate-quality",
                description="Alternative local quality triage helper",
                allowed_projects=("ai4binance",),
                side_effect=ToolSideEffect.READ_LOCAL,
                tags=("quality", "triage"),
                schema_tokens=32,
            ),
            ToolDescriptor(
                name="large-schema",
                description="Candidate that exceeds the schema budget",
                allowed_projects=("ai4binance",),
                side_effect=ToolSideEffect.READ_LOCAL,
                tags=("quality",),
                schema_tokens=1024,
            ),
            ToolDescriptor(
                name="foreign-tool",
                description="Not allowed in this project",
                allowed_projects=("other",),
                side_effect=ToolSideEffect.READ_LOCAL,
                tags=("quality",),
                schema_tokens=16,
            ),
        )
    )

    assert ToolSelection(query="quality", blockers=("NO_TOOL_MATCH",)).blockers == (
        "NO_TOOL_MATCH",
    )
    with pytest.raises(ValueError, match="schema tokens cannot be negative"):
        ToolSelection(query="quality", selected=(read_descriptor(),), schema_tokens=-1)
    with pytest.raises(ValueError, match="empty tool selection requires blockers"):
        ToolSelection(query="quality")
    with pytest.raises(ValueError, match="cannot be negative"):
        ToolRegistry((read_descriptor(),)).shortlist(
            "quality", project="ai4binance", max_schema_tokens=-1
        )

    zero_score = registry.shortlist("unmatched", project="ai4binance")
    assert zero_score.blockers == ("NO_TOOL_MATCH",)

    limited = registry.shortlist("alternate quality", project="ai4binance", max_tools=1)
    assert tuple(item.name for item in limited.selected) == ("alternate-quality",)
    assert limited.schema_tokens == 32

    budget_limited = registry.shortlist(
        "alternate quality",
        project="ai4binance",
        max_schema_tokens=40,
    )
    assert tuple(item.name for item in budget_limited.selected) == (
        "alternate-quality",
    )
    assert budget_limited.schema_tokens == 32


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


def test_tool_registry_shortlist_filters_hidden_tools_and_limits_budget() -> None:
    registry = ToolRegistry(
        (
            read_descriptor(),
            ToolDescriptor(
                name="alternate-quality",
                description="Alternative local quality triage helper",
                allowed_projects=("ai4binance",),
                side_effect=ToolSideEffect.READ_LOCAL,
                tags=("quality", "triage"),
                schema_tokens=32,
            ),
            ToolDescriptor(
                name="submit-order",
                description="Forbidden quality helper",
                allowed_projects=("ai4binance",),
                side_effect=ToolSideEffect.FINANCIAL,
                tags=("quality", "triage"),
                schema_tokens=8,
            ),
            ToolDescriptor(
                name="write-evidence",
                description="External write helper",
                allowed_projects=("ai4binance",),
                side_effect=ToolSideEffect.EXTERNAL_WRITE,
                tags=("quality", "triage"),
                schema_tokens=8,
            ),
        )
    )

    capped = registry.shortlist(
        "quality triage",
        project="ai4binance",
        max_tools=1,
        max_schema_tokens=128,
    )
    assert tuple(item.name for item in capped.selected) == ("quality-triage",)
    assert capped.schema_tokens == 64

    budgeted = registry.shortlist(
        "quality triage",
        project="ai4binance",
        max_tools=4,
        max_schema_tokens=64,
    )
    assert tuple(item.name for item in budgeted.selected) == ("quality-triage",)
    assert budgeted.blockers == ()

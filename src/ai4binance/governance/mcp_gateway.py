"""Default-deny MCP gateway contracts for governed agent tool access."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.governance.tool_policy import ToolPolicyDecision


class McpGatewayKind(StrEnum):
    FILESYSTEM = "Filesystem MCP"
    GITHUB = "GitHub MCP"
    POSTGRESQL = "PostgreSQL MCP"
    RESEARCH = "Research MCP"
    WOLFRAM = "Wolfram MCP"
    QUANT_RESEARCH = "Quant Research MCP"
    MARKET_DATA = "Canonical Market Data MCP"
    EVIDENCE = "Evidence MCP"
    GOVERNANCE = "Governance MCP"
    BINANCE_READ_ONLY = "future Binance READ-ONLY adapter"


class McpAuthorityClass(StrEnum):
    """Capability authority classes for MCP fabric tools."""

    MCP_R0_READ_ONLY = "MCP_R0_READ_ONLY"
    MCP_R1_ANALYZE_COMPUTE = "MCP_R1_ANALYZE_COMPUTE"
    MCP_R2_CREATE_RESEARCH_ARTIFACTS = "MCP_R2_CREATE_RESEARCH_ARTIFACTS"
    MCP_R3_CONTROLLED_STATE_MUTATION = "MCP_R3_CONTROLLED_STATE_MUTATION"
    MCP_X_EXECUTION_SENSITIVE = "MCP_X_EXECUTION_SENSITIVE"


class McpRouteStep(StrEnum):
    AGENT = "Agent"
    TOOL_POLICY = "Tool Policy"
    AUTHORIZATION = "Authorization"
    MCP_GATEWAY = "MCP Gateway"
    TOOL = "Tool"


CANONICAL_MCP_ROUTE: tuple[McpRouteStep, ...] = tuple(McpRouteStep)
DEFAULT_DENIED_MCP_TOOLS = (
    "filesystem.delete",
    "shell.admin",
    "exchange.place_order",
    "risk.override",
    "governance.override",
    "strategy.promote",
    "parameter.promote",
    "kill_switch.disable",
    "live.enable",
    "order.live.submit",
    "credential.read",
    "secret.export",
)

EXECUTION_SENSITIVE_MCP_TOOLS = (
    "risk.override",
    "governance.override",
    "strategy.promote",
    "parameter.promote",
    "kill_switch.disable",
    "live.enable",
    "order.live.submit",
    "credential.read",
    "secret.export",
)


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain empty values")


def classify_mcp_tool_authority(tool: str) -> McpAuthorityClass:
    """Return the maximum MCP authority class implied by a tool name."""
    _require_non_empty("MCP tool", tool)
    if tool in EXECUTION_SENSITIVE_MCP_TOOLS or tool.startswith(
        ("order.live.", "live.", "credential.", "secret.")
    ):
        return McpAuthorityClass.MCP_X_EXECUTION_SENSITIVE
    if tool.startswith(("quant_research.", "wolfram.", "analytics.")):
        return McpAuthorityClass.MCP_R1_ANALYZE_COMPUTE
    if tool.startswith(("evidence.register", "experiment.register")):
        return McpAuthorityClass.MCP_R2_CREATE_RESEARCH_ARTIFACTS
    if tool.startswith(("market.", "evidence.", "governance.")):
        return McpAuthorityClass.MCP_R0_READ_ONLY
    return McpAuthorityClass.MCP_R0_READ_ONLY


@dataclass(frozen=True, slots=True)
class McpAuthorizationResult:
    agent: str
    tool: str
    decision: ToolPolicyDecision
    reason_codes: tuple[str, ...]
    route: tuple[McpRouteStep, ...] = CANONICAL_MCP_ROUTE
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("MCP authorization agent", self.agent)
        _require_non_empty("MCP authorization tool", self.tool)
        _require_unique("MCP authorization reasons", self.reason_codes)
        if not self.reason_codes:
            raise ValueError("MCP authorization requires reason codes")
        if self.route != CANONICAL_MCP_ROUTE:
            raise ValueError("MCP authorization route must be canonical")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("MCP authorization cannot grant trading authority")

    @property
    def mcp_invocation_allowed(self) -> bool:
        return self.decision is ToolPolicyDecision.ALLOW


@dataclass(frozen=True, slots=True)
class McpToolPolicy:
    agent: str
    allowed: tuple[str, ...]
    denied: tuple[str, ...] = DEFAULT_DENIED_MCP_TOOLS
    route: tuple[McpRouteStep, ...] = CANONICAL_MCP_ROUTE
    default_decision: ToolPolicyDecision = ToolPolicyDecision.DENY
    direct_agent_to_mcp_allowed: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("MCP tool policy agent", self.agent)
        _require_unique("MCP allowed tools", self.allowed)
        _require_unique("MCP denied tools", self.denied)
        if not self.allowed:
            raise ValueError("MCP tool policy requires allowed tools")
        overlap = set(self.allowed) & set(self.denied)
        if overlap:
            raise ValueError("MCP allowed tools cannot also be denied")
        if any(
            classify_mcp_tool_authority(tool)
            is McpAuthorityClass.MCP_X_EXECUTION_SENSITIVE
            for tool in self.allowed
        ):
            raise ValueError("execution-sensitive MCP tools cannot be allowed")
        if self.route != CANONICAL_MCP_ROUTE:
            raise ValueError("MCP route must be Agent -> Tool Policy -> Authorization")
        if self.default_decision is not ToolPolicyDecision.DENY:
            raise ValueError("MCP policy default must deny")
        if self.direct_agent_to_mcp_allowed:
            raise ValueError("direct agent to MCP access is prohibited")
        required_denials = set(DEFAULT_DENIED_MCP_TOOLS)
        if not required_denials.issubset(set(self.denied)):
            raise ValueError("MCP policy must deny destructive and order tools")

    def authorize(self, *, agent: str, tool: str) -> McpAuthorizationResult:
        _require_non_empty("MCP authorization request agent", agent)
        _require_non_empty("MCP authorization request tool", tool)
        if agent != self.agent:
            return McpAuthorizationResult(
                agent=agent,
                tool=tool,
                decision=ToolPolicyDecision.DENY,
                reason_codes=("MCP_AGENT_NOT_BOUND_TO_POLICY",),
            )
        if tool in self.denied:
            return McpAuthorizationResult(
                agent=agent,
                tool=tool,
                decision=ToolPolicyDecision.DENY,
                reason_codes=("MCP_TOOL_DENIED",),
            )
        if tool not in self.allowed:
            return McpAuthorizationResult(
                agent=agent,
                tool=tool,
                decision=ToolPolicyDecision.DENY,
                reason_codes=("MCP_POLICY_DEFAULT_DENY",),
            )
        return McpAuthorizationResult(
            agent=agent,
            tool=tool,
            decision=ToolPolicyDecision.ALLOW,
            reason_codes=("MCP_TOOL_ALLOWED_BY_POLICY",),
        )


@dataclass(frozen=True, slots=True)
class McpGatewayContract:
    gateway_id: str = "AI4BINANCE-MCP-GATEWAY"
    version: str = "1.0.0"
    gateways: tuple[McpGatewayKind, ...] = tuple(McpGatewayKind)
    route: tuple[McpRouteStep, ...] = CANONICAL_MCP_ROUTE
    policies: tuple[McpToolPolicy, ...] = (
        McpToolPolicy(
            agent="research_agent",
            allowed=(
                "github.search",
                "filesystem.read",
                "market.get_data_quality",
                "market.get_provenance",
                "market.get_snapshot",
                "evidence.get",
                "evidence.verify",
                "evidence.get_provenance",
                "evidence.find_conflicts",
                "evidence.build_bundle",
                "governance.check_action",
                "governance.check_contract",
                "governance.get_authority",
                "governance.get_blockers",
                "governance.get_policy",
                "quant_research.assess_statistics",
                "quant_research.get_capabilities",
                "quant_research.verify_formula",
                "quant_research.wolfram_status",
            ),
        ),
    )
    direct_agent_to_mcp_allowed: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("MCP gateway_id", self.gateway_id)
        _require_non_empty("MCP gateway version", self.version)
        if self.gateways != tuple(McpGatewayKind):
            raise ValueError("MCP gateway contract must list every gateway kind")
        if self.route != CANONICAL_MCP_ROUTE:
            raise ValueError("MCP gateway route must be canonical")
        if not self.policies:
            raise ValueError("MCP gateway requires at least one tool policy")
        agents = tuple(policy.agent for policy in self.policies)
        _require_unique("MCP gateway policy agents", agents)
        if self.direct_agent_to_mcp_allowed:
            raise ValueError("direct agent to MCP access is prohibited")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("MCP gateway cannot grant trading authority")

    def authorize(self, *, agent: str, tool: str) -> McpAuthorizationResult:
        for policy in self.policies:
            if policy.agent == agent:
                return policy.authorize(agent=agent, tool=tool)
        return McpAuthorizationResult(
            agent=agent,
            tool=tool,
            decision=ToolPolicyDecision.DENY,
            reason_codes=("MCP_AGENT_POLICY_MISSING",),
        )


def build_ai4binance_mcp_gateway_contract() -> McpGatewayContract:
    return McpGatewayContract()

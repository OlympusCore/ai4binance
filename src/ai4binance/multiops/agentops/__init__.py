"""AgentOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.AGENTOPS
CAPABILITIES = (
    OpsCapability.AGENT_REGISTRY,
    OpsCapability.ROLE_DRIFT,
    OpsCapability.LOOP_BUDGET,
    OpsCapability.TOOL_AUTHORIZATION,
    OpsCapability.AGENT_RETIREMENT,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

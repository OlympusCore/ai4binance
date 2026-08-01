"""LLMOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.LLMOPS
CAPABILITIES = (
    OpsCapability.PROMPT_REGISTRY,
    OpsCapability.MODEL_ROUTING,
    OpsCapability.EVAL,
    OpsCapability.GROUNDING,
    OpsCapability.TOKEN_LATENCY,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

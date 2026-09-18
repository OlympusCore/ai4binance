"""TradeOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.TRADEOPS
CAPABILITIES = (
    OpsCapability.PAPER_LIFECYCLE,
    OpsCapability.ORDER_INTENT,
    OpsCapability.EXECUTION_BLOCKERS,
    OpsCapability.CLOSURE_REVIEW,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

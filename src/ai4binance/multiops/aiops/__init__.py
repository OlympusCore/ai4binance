"""AIOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.AIOPS
CAPABILITIES = (
    OpsCapability.HEALTH,
    OpsCapability.INCIDENT,
    OpsCapability.ALERT_CORRELATION,
    OpsCapability.SAFE_RUNBOOKS,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

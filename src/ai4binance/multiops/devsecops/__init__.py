"""DevSecOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.DEVSECOPS
CAPABILITIES = (
    OpsCapability.CI,
    OpsCapability.TESTS,
    OpsCapability.SECRET_SCANNING,
    OpsCapability.RELEASE_GATES,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

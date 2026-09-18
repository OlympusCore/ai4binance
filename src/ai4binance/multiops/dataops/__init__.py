"""DataOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.DATAOPS
CAPABILITIES = (
    OpsCapability.FRESHNESS,
    OpsCapability.RECONCILIATION,
    OpsCapability.QUALITY,
    OpsCapability.DATASET_LINEAGE,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

"""MLOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.MLOPS
CAPABILITIES = (
    OpsCapability.DATASET_REGISTRY,
    OpsCapability.FEATURE_REGISTRY,
    OpsCapability.MODEL_REGISTRY,
    OpsCapability.DRIFT,
    OpsCapability.PROMOTION,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

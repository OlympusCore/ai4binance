"""RAGOps domain metadata."""

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.RAGOPS
CAPABILITIES = (
    OpsCapability.CORPUS_VERSION,
    OpsCapability.CHUNKING,
    OpsCapability.EMBEDDING,
    OpsCapability.RETRIEVAL_QUALITY,
    OpsCapability.SOURCE_LINEAGE,
)

__all__ = ["CAPABILITIES", "DOMAIN"]

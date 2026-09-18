"""Canonical research-domain contracts."""

from ai4binance.domain.research.canonical_cycle import (
    MAX_BOUNDED_OBSERVATIONS,
    CanonicalCycleEnvelope,
    CanonicalCycleStep,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
)
from ai4binance.domain.research.lifecycle import (
    CycleLifecycleReceipt,
    LearningValidationResult,
    LifecycleClosureStep,
    MemoryDisposition,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    BacktestExitReason,
    ClosedTradeAttribution,
    TradeDirection,
    TradeEdgeAggregateView,
    TradeEdgeLedger,
    VirtualClosedTradeRecord,
    VirtualTradeAttributionAggregate,
    VirtualTradeAttributionLedger,
    build_virtual_trade_attribution_ledger,
)

__all__ = (
    "MAX_BOUNDED_OBSERVATIONS",
    "BacktestExitReason",
    "CanonicalCycleEnvelope",
    "CanonicalCycleStep",
    "ClosedTradeAttribution",
    "CycleArtifactKind",
    "CycleArtifactRef",
    "CycleExecutionSurface",
    "CycleGovernanceStatus",
    "CycleLifecycleReceipt",
    "LearningValidationResult",
    "LifecycleClosureStep",
    "MemoryDisposition",
    "TradeDirection",
    "TradeEdgeAggregateView",
    "TradeEdgeLedger",
    "VirtualClosedTradeRecord",
    "VirtualTradeAttributionAggregate",
    "VirtualTradeAttributionLedger",
    "build_virtual_trade_attribution_ledger",
)

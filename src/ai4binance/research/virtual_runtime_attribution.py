"""Compatibility facade for canonical virtual-trade attribution contracts."""

from ai4binance.domain.research.virtual_runtime_attribution import (
    BacktestExitReason as BacktestExitReason,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    ClosedTradeAttribution as ClosedTradeAttribution,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeDirection as TradeDirection,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeEdgeAggregateView as TradeEdgeAggregateView,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeEdgeLedger as TradeEdgeLedger,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    VirtualClosedTradeRecord as VirtualClosedTradeRecord,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    VirtualTradeAttributionAggregate as VirtualTradeAttributionAggregate,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    VirtualTradeAttributionLedger as VirtualTradeAttributionLedger,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    build_virtual_trade_attribution_ledger as build_virtual_trade_attribution_ledger,
)

__all__ = (
    "BacktestExitReason",
    "ClosedTradeAttribution",
    "TradeDirection",
    "TradeEdgeAggregateView",
    "TradeEdgeLedger",
    "VirtualClosedTradeRecord",
    "VirtualTradeAttributionAggregate",
    "VirtualTradeAttributionLedger",
    "build_virtual_trade_attribution_ledger",
)

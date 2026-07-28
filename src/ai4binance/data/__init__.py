"""Market-data acquisition and timeframe utilities."""

from ai4binance.data.acquisition import DataAcquisitionAgent
from ai4binance.data.aggtrades import (
    AggregateTrade,
    AggregateTradeRevision,
    CandleTradeReconciliation,
    build_aggregate_trade_revision,
    reconcile_candle_trades,
)
from ai4binance.data.archive import (
    DatasetIntegrityError,
    DatasetManifest,
    ParquetOHLCVArchive,
)
from ai4binance.data.binance_vision import (
    BinanceVisionIngestor,
    BinanceVisionIntegrityError,
    BinanceVisionSyncResult,
    VerifiedSourceFile,
)

__all__ = (
    "AggregateTrade",
    "AggregateTradeRevision",
    "BinanceVisionIngestor",
    "BinanceVisionIntegrityError",
    "BinanceVisionSyncResult",
    "CandleTradeReconciliation",
    "DataAcquisitionAgent",
    "DatasetIntegrityError",
    "DatasetManifest",
    "ParquetOHLCVArchive",
    "VerifiedSourceFile",
    "build_aggregate_trade_revision",
    "reconcile_candle_trades",
)

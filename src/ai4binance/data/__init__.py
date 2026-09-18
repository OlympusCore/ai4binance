"""Market-data acquisition and timeframe utilities."""

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from ai4binance.data.binance_vision_futures import (
        BinanceVisionFuturesIntegrityError,
        BinanceVisionFuturesReplayIngestor,
        BinanceVisionFuturesSyncResult,
        VerifiedFuturesSourceFile,
    )

_FUTURES_EXPORTS = frozenset(
    {
        "BinanceVisionFuturesIntegrityError",
        "BinanceVisionFuturesReplayIngestor",
        "BinanceVisionFuturesSyncResult",
        "VerifiedFuturesSourceFile",
    }
)


def __getattr__(name: str) -> object:
    """Load futures ingestion exports without creating a validation import cycle."""

    if name not in _FUTURES_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from ai4binance.data import binance_vision_futures

    value = getattr(binance_vision_futures, name)
    globals()[name] = value
    return value


__all__ = (
    "AggregateTrade",
    "AggregateTradeRevision",
    "BinanceVisionFuturesIntegrityError",
    "BinanceVisionFuturesReplayIngestor",
    "BinanceVisionFuturesSyncResult",
    "BinanceVisionIngestor",
    "BinanceVisionIntegrityError",
    "BinanceVisionSyncResult",
    "CandleTradeReconciliation",
    "DataAcquisitionAgent",
    "DatasetIntegrityError",
    "DatasetManifest",
    "ParquetOHLCVArchive",
    "VerifiedFuturesSourceFile",
    "VerifiedSourceFile",
    "build_aggregate_trade_revision",
    "reconcile_candle_trades",
)

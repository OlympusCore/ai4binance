"""Look-ahead-safe Spot and USD-M Futures backtesting primitives."""

from ai4binance.research.backtesting.engine import BacktestEngine, SignalProvider
from ai4binance.research.backtesting.futures_engine import (
    FuturesBacktestConfig,
    FuturesBacktestEngine,
    FuturesBacktestIntent,
    FuturesSignalProvider,
)
from ai4binance.research.backtesting.models import (
    BacktestConfig,
    BacktestIntent,
    BacktestResult,
    ClosureReview,
    MissedOpportunityCategory,
    MissedOpportunityLedger,
    MissedOpportunityRecord,
    PerformanceEngineReport,
    PreVetoOpportunityLedger,
    PreVetoOpportunityRecord,
    RejectedSignal,
    TradeOutcome,
    TradeRecord,
)
from ai4binance.research.backtesting.queue_fill import (
    QueueFillReport,
    QueueFillRequest,
    RestingSide,
    replay_conservative_queue_fill,
)
from ai4binance.research.backtesting.robustness import (
    BacktestRobustnessAnalyzer,
    BacktestRobustnessReport,
    BootstrapAssessment,
    StressResult,
    StressScenario,
)
from ai4binance.research.backtesting.runtime_economics import (
    BacktestRuntimeEconomicsEvidence,
    BacktestRuntimeEconomicsReview,
    BacktestRuntimeEconomicsReviewStatus,
    BacktestRuntimeReviewerResult,
    review_backtest_runtime_economics,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestIntent",
    "BacktestResult",
    "BacktestRobustnessAnalyzer",
    "BacktestRobustnessReport",
    "BacktestRuntimeEconomicsEvidence",
    "BacktestRuntimeEconomicsReview",
    "BacktestRuntimeEconomicsReviewStatus",
    "BacktestRuntimeReviewerResult",
    "BootstrapAssessment",
    "ClosureReview",
    "FuturesBacktestConfig",
    "FuturesBacktestEngine",
    "FuturesBacktestIntent",
    "FuturesSignalProvider",
    "MissedOpportunityCategory",
    "MissedOpportunityLedger",
    "MissedOpportunityRecord",
    "PerformanceEngineReport",
    "PreVetoOpportunityLedger",
    "PreVetoOpportunityRecord",
    "QueueFillReport",
    "QueueFillRequest",
    "RejectedSignal",
    "RestingSide",
    "SignalProvider",
    "StressResult",
    "StressScenario",
    "TradeOutcome",
    "TradeRecord",
    "replay_conservative_queue_fill",
    "review_backtest_runtime_economics",
]

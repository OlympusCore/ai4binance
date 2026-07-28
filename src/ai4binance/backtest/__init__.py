"""Look-ahead-safe Spot backtesting primitives."""

from ai4binance.backtest.engine import BacktestEngine, SignalProvider
from ai4binance.backtest.models import (
    BacktestConfig,
    BacktestIntent,
    BacktestResult,
    ClosureReview,
    RejectedSignal,
    TradeRecord,
)
from ai4binance.backtest.queue_fill import (
    QueueFillReport,
    QueueFillRequest,
    RestingSide,
    replay_conservative_queue_fill,
)
from ai4binance.backtest.robustness import (
    BacktestRobustnessAnalyzer,
    BacktestRobustnessReport,
    BootstrapAssessment,
    StressResult,
    StressScenario,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestIntent",
    "BacktestResult",
    "BacktestRobustnessAnalyzer",
    "BacktestRobustnessReport",
    "BootstrapAssessment",
    "ClosureReview",
    "QueueFillReport",
    "QueueFillRequest",
    "RejectedSignal",
    "RestingSide",
    "SignalProvider",
    "StressResult",
    "StressScenario",
    "TradeRecord",
    "replay_conservative_queue_fill",
]

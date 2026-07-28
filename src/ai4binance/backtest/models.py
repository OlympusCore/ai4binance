"""Immutable backtest inputs, lifecycle records and performance reports."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from ai4binance.backtest.liquidity import LiquidityStressConfig
from ai4binance.execution.paper import ExitReason

ZERO = Decimal("0")


class BacktestExitReason(StrEnum):
    """Exit reasons not owned by the paper execution primitive."""

    STOP_LOSS_EXIT = ExitReason.STOP_LOSS_EXIT
    TRAILING_STOP_EXIT = ExitReason.TRAILING_STOP_EXIT
    TAKE_PROFIT_EXIT = ExitReason.TAKE_PROFIT_EXIT
    END_OF_DATA_EXIT = "END_OF_DATA_EXIT"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Deterministic Spot backtest assumptions."""

    initial_cash_usdt: Decimal = Decimal("1000")
    quantity: Decimal = Decimal("1")
    fee_ratio: Decimal = Decimal("0.001")
    slippage_ratio: Decimal = Decimal("0.0005")
    trailing_multiplier: Decimal = Decimal("1.5")
    tick_size: Decimal = Decimal("0.00000001")
    liquidity_stress: LiquidityStressConfig | None = None

    def __post_init__(self) -> None:
        if self.initial_cash_usdt <= ZERO or self.quantity <= ZERO:
            raise ValueError("initial cash and quantity must be positive")
        if not ZERO <= self.fee_ratio <= Decimal("0.01"):
            raise ValueError("fee_ratio must be between zero and 0.01")
        if not ZERO <= self.slippage_ratio <= Decimal("0.02"):
            raise ValueError("slippage_ratio must be between zero and 0.02")
        if self.trailing_multiplier <= ZERO:
            raise ValueError("trailing_multiplier must be positive")
        if self.tick_size <= ZERO:
            raise ValueError("tick_size must be positive")


@dataclass(frozen=True, slots=True)
class BacktestIntent:
    """Long Spot entry proposed after the referenced candle has closed."""

    signal_id: str
    timestamp: datetime
    stop_loss: Decimal
    take_profit: Decimal
    atr: Decimal
    reason_codes: tuple[str, ...] = ("BACKTEST_SIGNAL",)
    take_profit_levels: tuple[Decimal, ...] = ()
    partial_exit_ratio: Decimal = Decimal("0.5")

    def __post_init__(self) -> None:
        if not self.signal_id.strip() or not self.reason_codes:
            raise ValueError("signal identity and reason codes are required")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("signal timestamp must be timezone-aware")
        if min(self.stop_loss, self.take_profit, self.atr) <= ZERO:
            raise ValueError("signal price geometry values must be positive")
        levels = self.targets
        if tuple(sorted(set(levels))) != levels:
            raise ValueError("take-profit levels must be unique and increasing")
        if not ZERO < self.partial_exit_ratio < Decimal("1"):
            raise ValueError("partial_exit_ratio must be between zero and one")

    @property
    def targets(self) -> tuple[Decimal, ...]:
        """Return explicit staged targets or the backward-compatible target."""
        return self.take_profit_levels or (self.take_profit,)


@dataclass(frozen=True, slots=True)
class RejectedSignal:
    """Signal that could not enter the event lifecycle."""

    signal_id: str
    timestamp: datetime
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClosureReview:
    """Auditable post-trade lifecycle assessment."""

    exit_reason: BacktestExitReason
    lifecycle_error: str | None
    stop_quality: str
    trailing_quality: str
    ignored_signals: int
    htf_weakness: bool
    volatility_expansion: bool
    level_break: bool
    staged_exit_alternative: str
    lesson_candidate: str


@dataclass(frozen=True, slots=True)
class StagedExitRecord:
    """One partial take-profit fill inside a complete trade lifecycle."""

    timestamp: datetime
    price: Decimal
    quantity: Decimal
    fee_usdt: Decimal
    realized_pnl_usdt: Decimal


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """End-of-candle mark-to-market account equity."""

    timestamp: datetime
    equity_usdt: Decimal
    position_quantity: Decimal


@dataclass(frozen=True, slots=True)
class FalseBreakoutRecord:
    """Breakout-tagged entry closed by a protective stop."""

    signal_id: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    net_pnl_usdt: Decimal


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Complete fee-aware long Spot trade record."""

    trade_id: str
    signal_id: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_fee_usdt: Decimal
    exit_fee_usdt: Decimal
    net_pnl_usdt: Decimal
    return_ratio: Decimal
    exit_reason: BacktestExitReason
    closure_review: ClosureReview
    staged_exits: tuple[StagedExitRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    """Core strategy metrics required by the validation contract."""

    net_return: float
    max_drawdown: float
    profit_factor: float | None
    expectancy_usdt: float
    sharpe: float | None
    win_rate: float
    trade_count: int
    buy_and_hold_return: float

    def __post_init__(self) -> None:
        values = (
            self.net_return,
            self.max_drawdown,
            self.expectancy_usdt,
            self.win_rate,
            self.buy_and_hold_return,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("backtest metrics must be finite")


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Reproducible result with lifecycle and rejection evidence."""

    symbol: str
    timeframe: str
    started_at: datetime
    ended_at: datetime
    assumptions: BacktestConfig
    trades: tuple[TradeRecord, ...]
    rejected_signals: tuple[RejectedSignal, ...]
    no_trade_count: int
    metrics: BacktestMetrics
    audit_events: tuple[dict[str, object], ...] = field(default_factory=tuple)
    equity_curve: tuple[EquityPoint, ...] = field(default_factory=tuple)
    false_breakouts: tuple[FalseBreakoutRecord, ...] = field(default_factory=tuple)

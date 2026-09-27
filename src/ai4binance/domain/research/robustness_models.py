"""Immutable research-only robustness evidence contracts."""

from dataclasses import dataclass
from decimal import Decimal

from ai4binance.domain import ValidationStatus
from ai4binance.domain.research.backtest_models import BacktestConfig


@dataclass(frozen=True, slots=True)
class StressScenario:
    """Bounded execution-cost assumptions for one rerun."""

    name: str
    fee_ratio: Decimal
    slippage_ratio: Decimal
    spread_ratio: Decimal = Decimal("0")
    funding_multiplier: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("stress scenario name cannot be empty")
        BacktestConfig(
            fee_ratio=self.fee_ratio,
            slippage_ratio=self.slippage_ratio,
        )
        if self.spread_ratio < Decimal("0"):
            raise ValueError("spread_ratio must be non-negative")
        if self.funding_multiplier < Decimal("1"):
            raise ValueError("funding_multiplier must be at least one")


@dataclass(frozen=True, slots=True)
class StressResult:
    """Comparable metrics from one cost-stress rerun."""

    scenario: StressScenario
    net_return: float
    profit_factor: float | None
    expectancy_usdt: float
    max_drawdown: float
    trade_count: int
    delta_net_return: float
    delta_profit_factor: float | None
    delta_expectancy_usdt: float
    delta_max_drawdown: float
    delta_trade_count: int
    spread_cost_usdt: float
    funding_cost_usdt: float
    funding_supported: bool


@dataclass(frozen=True, slots=True)
class BootstrapAssessment:
    """Seeded resampling distribution over realized trade PnL."""

    simulations: int
    seed: int
    probability_of_loss: float
    median_net_return: float
    p05_net_return: float
    p95_max_drawdown: float


@dataclass(frozen=True, slots=True)
class BacktestRobustnessReport:
    """Research-only robustness evidence with explicit blockers."""

    stress_results: tuple[StressResult, ...]
    bootstrap: BootstrapAssessment
    blockers: tuple[str, ...]
    promotion_status: ValidationStatus
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("robustness evidence cannot grant execution authority")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError("robustness may only research or stage candidates")

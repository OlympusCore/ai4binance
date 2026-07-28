"""Deterministic fee/slippage stress and bootstrap robustness assessment."""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from math import sqrt
from random import Random

from ai4binance.backtest.engine import BacktestEngine, SignalProvider
from ai4binance.backtest.models import BacktestConfig, BacktestResult
from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle

ProviderFactory = Callable[[], SignalProvider]


@dataclass(frozen=True, slots=True)
class StressScenario:
    """Bounded execution-cost assumptions for one rerun."""

    name: str
    fee_ratio: Decimal
    slippage_ratio: Decimal

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("stress scenario name cannot be empty")
        BacktestConfig(
            fee_ratio=self.fee_ratio,
            slippage_ratio=self.slippage_ratio,
        )


@dataclass(frozen=True, slots=True)
class StressResult:
    """Comparable metrics from one cost-stress rerun."""

    scenario: StressScenario
    net_return: float
    max_drawdown: float
    trade_count: int


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


@dataclass(frozen=True, slots=True)
class BacktestRobustnessAnalyzer:
    """Rerun cost scenarios and bootstrap realized outcomes deterministically."""

    scenarios: tuple[StressScenario, ...] = field(
        default_factory=lambda: (
            StressScenario("BASE", Decimal("0.001"), Decimal("0.0005")),
            StressScenario("COST_2X", Decimal("0.002"), Decimal("0.001")),
            StressScenario("SLIPPAGE_STRESS", Decimal("0.002"), Decimal("0.003")),
        )
    )
    simulations: int = 1000
    seed: int = 42

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise ValueError("at least one stress scenario is required")
        if not 100 <= self.simulations <= 10000:
            raise ValueError("simulations must be between 100 and 10000")

    def analyze(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        provider_factory: ProviderFactory,
    ) -> BacktestRobustnessReport:
        """Return cost and resampling evidence without promoting execution."""
        scenario_runs = tuple(
            BacktestEngine(
                BacktestConfig(
                    fee_ratio=scenario.fee_ratio,
                    slippage_ratio=scenario.slippage_ratio,
                )
            ).run(
                symbol=symbol,
                timeframe=timeframe,
                candles=candles,
                signal_provider=provider_factory(),
            )
            for scenario in self.scenarios
        )
        stress_results = tuple(
            StressResult(
                scenario,
                run.metrics.net_return,
                run.metrics.max_drawdown,
                run.metrics.trade_count,
            )
            for scenario, run in zip(self.scenarios, scenario_runs, strict=True)
        )
        bootstrap = self._bootstrap(scenario_runs[0])
        blockers = self._blockers(stress_results, bootstrap)
        return BacktestRobustnessReport(
            stress_results=stress_results,
            bootstrap=bootstrap,
            blockers=blockers,
            promotion_status=(
                ValidationStatus.RESEARCH_ONLY
                if blockers
                else ValidationStatus.STAGED_CANDIDATE
            ),
        )

    def _bootstrap(self, result: BacktestResult) -> BootstrapAssessment:
        pnl = tuple(float(trade.net_pnl_usdt) for trade in result.trades)
        if not pnl:
            return BootstrapAssessment(self.simulations, self.seed, 1.0, 0.0, 0.0, 1.0)
        random = Random(self.seed)  # noqa: S311  # nosec B311
        returns: list[float] = []
        drawdowns: list[float] = []
        initial_cash = float(result.assumptions.initial_cash_usdt)
        block_length = max(1, round(sqrt(len(pnl))))
        for _ in range(self.simulations):
            sampled: list[float] = []
            while len(sampled) < len(pnl):
                start = random.randrange(len(pnl))  # nosec B311
                sampled.extend(
                    pnl[(start + offset) % len(pnl)] for offset in range(block_length)
                )
            path = tuple(sampled[: len(pnl)])
            returns.append(sum(path) / initial_cash)
            drawdowns.append(self._path_drawdown(path, initial_cash))
        returns.sort()
        drawdowns.sort()
        return BootstrapAssessment(
            simulations=self.simulations,
            seed=self.seed,
            probability_of_loss=sum(value < 0.0 for value in returns)
            / self.simulations,
            median_net_return=self._percentile(returns, 0.50),
            p05_net_return=self._percentile(returns, 0.05),
            p95_max_drawdown=self._percentile(drawdowns, 0.95),
        )

    @staticmethod
    def _path_drawdown(path: tuple[float, ...], initial_cash: float) -> float:
        equity = initial_cash
        peak = initial_cash
        drawdown = 0.0
        for pnl in path:
            equity += pnl
            peak = max(peak, equity)
            if peak > 0.0:
                drawdown = max(drawdown, (peak - equity) / peak)
        return drawdown

    @staticmethod
    def _percentile(values: list[float], ratio: float) -> float:
        index = round((len(values) - 1) * ratio)
        return values[index]

    @staticmethod
    def _blockers(
        stress_results: tuple[StressResult, ...],
        bootstrap: BootstrapAssessment,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if min(item.trade_count for item in stress_results) < 5:
            blockers.append("LOW_STRESS_TRADE_COUNT")
        if any(item.net_return <= 0.0 for item in stress_results):
            blockers.append("COST_STRESS_RETURN_NOT_POSITIVE")
        if bootstrap.probability_of_loss > 0.5:
            blockers.append("BOOTSTRAP_LOSS_PROBABILITY_HIGH")
        if bootstrap.p95_max_drawdown > 0.25:
            blockers.append("BOOTSTRAP_DRAWDOWN_EXCESSIVE")
        return tuple(blockers)

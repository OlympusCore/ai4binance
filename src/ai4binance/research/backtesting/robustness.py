"""Deterministic fee/slippage stress and bootstrap robustness assessment."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from math import sqrt
from random import Random

from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting.engine import BacktestEngine, SignalProvider
from ai4binance.research.backtesting.models import BacktestConfig, BacktestResult
from ai4binance.schemas import OHLCVCandle

ProviderFactory = Callable[[], SignalProvider]


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


@dataclass(frozen=True, slots=True)
class BacktestRobustnessAnalyzer:
    """Rerun cost scenarios and bootstrap realized outcomes deterministically."""

    scenarios: tuple[StressScenario, ...] = field(
        default_factory=lambda: (
            StressScenario(
                "BASE",
                Decimal("0.001"),
                Decimal("0.0005"),
                spread_ratio=Decimal("0.00025"),
            ),
            StressScenario(
                "COST_1_5X",
                Decimal("0.0015"),
                Decimal("0.00075"),
                spread_ratio=Decimal("0.000375"),
                funding_multiplier=Decimal("1.5"),
            ),
            StressScenario(
                "COST_2X",
                Decimal("0.002"),
                Decimal("0.001"),
                spread_ratio=Decimal("0.0005"),
                funding_multiplier=Decimal("2"),
            ),
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
        backtest_config: BacktestConfig | None = None,
    ) -> BacktestRobustnessReport:
        """Return cost and resampling evidence without promoting execution."""
        scenario_runs = tuple(
            BacktestEngine(
                replace(
                    backtest_config or BacktestConfig(),
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
        base_result = self._stress_result(self.scenarios[0], scenario_runs[0])
        stress_results = [base_result]
        for scenario, run in zip(
            self.scenarios[1:],
            scenario_runs[1:],
            strict=True,
        ):
            stress_results.append(self._stress_result(scenario, run, base_result))
        bootstrap = self._bootstrap(scenario_runs[0])
        blockers = self._blockers(tuple(stress_results), bootstrap)
        return BacktestRobustnessReport(
            stress_results=tuple(stress_results),
            bootstrap=bootstrap,
            blockers=blockers,
            promotion_status=(
                ValidationStatus.RESEARCH_ONLY
                if blockers
                else ValidationStatus.STAGED_CANDIDATE
            ),
        )

    @staticmethod
    def _stress_result(
        scenario: StressScenario,
        run: BacktestResult,
        baseline: StressResult | None = None,
    ) -> StressResult:
        pnl = []
        spread_cost_usdt = 0.0
        funding_cost_usdt = 0.0
        funding_supported = False
        for trade in run.trades:
            round_turn_notional = float(
                (trade.entry_price + trade.exit_price) * trade.quantity
            )
            spread_cost = round_turn_notional * float(scenario.spread_ratio)
            funding_base = float(trade.funding_cost_usdt)
            market = trade.attribution.market.upper()
            funding_delta = 0.0
            if "FUTURES" in market:
                funding_supported = True
                funding_delta = funding_base * (
                    float(scenario.funding_multiplier) - 1.0
                )
            spread_cost_usdt += spread_cost
            funding_cost_usdt += funding_delta
            pnl.append(float(trade.net_pnl_usdt) - spread_cost - funding_delta)
        initial_cash = float(run.assumptions.initial_cash_usdt)
        net_return, profit_factor, expectancy_usdt, max_drawdown = (
            BacktestRobustnessAnalyzer._metrics_from_pnl(pnl, initial_cash)
        )
        baseline_net_return = (
            baseline.net_return if baseline is not None else net_return
        )
        baseline_profit_factor = (
            baseline.profit_factor if baseline is not None else profit_factor
        )
        baseline_expectancy = (
            baseline.expectancy_usdt if baseline is not None else expectancy_usdt
        )
        baseline_drawdown = (
            baseline.max_drawdown if baseline is not None else max_drawdown
        )
        baseline_trade_count = (
            baseline.trade_count if baseline is not None else len(pnl)
        )
        return StressResult(
            scenario=scenario,
            net_return=net_return,
            profit_factor=profit_factor,
            expectancy_usdt=expectancy_usdt,
            max_drawdown=max_drawdown,
            trade_count=len(pnl),
            delta_net_return=net_return - baseline_net_return,
            delta_profit_factor=(
                None
                if profit_factor is None or baseline_profit_factor is None
                else profit_factor - baseline_profit_factor
            ),
            delta_expectancy_usdt=expectancy_usdt - baseline_expectancy,
            delta_max_drawdown=max_drawdown - baseline_drawdown,
            delta_trade_count=len(pnl) - baseline_trade_count,
            spread_cost_usdt=spread_cost_usdt,
            funding_cost_usdt=funding_cost_usdt,
            funding_supported=funding_supported,
        )

    @staticmethod
    def _metrics_from_pnl(
        pnl: list[float],
        initial_cash: float,
    ) -> tuple[float, float | None, float, float]:
        total_pnl = sum(pnl)
        wins = [value for value in pnl if value > 0.0]
        losses = [value for value in pnl if value < 0.0]
        gross_loss = abs(sum(losses))
        profit_factor = sum(wins) / gross_loss if gross_loss > 0.0 else None
        expectancy = total_pnl / len(pnl) if pnl else 0.0
        equity = initial_cash
        path = [equity]
        for trade_pnl in pnl:
            equity += trade_pnl
            path.append(equity)
        max_drawdown = BacktestRobustnessAnalyzer._closed_trade_drawdown(tuple(path))
        return total_pnl / initial_cash, profit_factor, expectancy, max_drawdown

    @staticmethod
    def _closed_trade_drawdown(equity_path: tuple[float, ...]) -> float:
        peak = equity_path[0] if equity_path else 0.0
        max_drawdown = 0.0
        for equity in equity_path:
            peak = max(peak, equity)
            if peak > 0.0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
        return max_drawdown

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
        modest = next(
            (item for item in stress_results if item.scenario.name == "COST_1_5X"),
            None,
        )
        if modest is None:
            modest = next(
                (item for item in stress_results if item.scenario.name != "BASE"),
                None,
            )
        if modest is not None and (
            modest.net_return <= 0.0
            or modest.expectancy_usdt <= 0.0
            or (modest.profit_factor is not None and modest.profit_factor <= 1.0)
        ):
            blockers.append("FRAGILE_EDGE")
        if bootstrap.probability_of_loss > 0.5:
            blockers.append("BOOTSTRAP_LOSS_PROBABILITY_HIGH")
        if bootstrap.p95_max_drawdown > 0.25:
            blockers.append("BOOTSTRAP_DRAWDOWN_EXCESSIVE")
        return tuple(blockers)

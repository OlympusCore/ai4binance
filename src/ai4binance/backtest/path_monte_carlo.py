"""Deterministic bounded candle-path Monte Carlo robustness analysis."""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from random import Random

from ai4binance.backtest.engine import BacktestEngine, SignalProvider
from ai4binance.backtest.models import BacktestConfig
from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle

ProviderFactory = Callable[[], SignalProvider]
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class CandlePathMonteCarloReport:
    simulations: int
    seed: int
    median_net_return: float
    p05_net_return: float
    p95_max_drawdown: float
    probability_of_loss: float
    return_range: float
    blockers: tuple[str, ...]
    promotion_status: ValidationStatus
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.simulations < 25 or self.execution_allowed:
            raise ValueError("Monte Carlo report dimensions or authority are invalid")
        staged = self.promotion_status is ValidationStatus.STAGED_CANDIDATE
        if staged == bool(self.blockers):
            raise ValueError("Monte Carlo status must match blockers")


@dataclass(frozen=True, slots=True)
class CandlePathMonteCarloAnalyzer:
    simulations: int = 100
    seed: int = 42
    maximum_price_jitter_ratio: Decimal = Decimal("0.0025")
    maximum_volume_jitter_ratio: Decimal = Decimal("0.05")
    maximum_return_range: float = 0.25
    config: BacktestConfig = field(default_factory=BacktestConfig)

    def __post_init__(self) -> None:
        if not 25 <= self.simulations <= 2000:
            raise ValueError("path simulations must be between 25 and 2000")
        ratios = (self.maximum_price_jitter_ratio, self.maximum_volume_jitter_ratio)
        if any(
            not value.is_finite() or not Decimal("0") <= value <= Decimal("0.1")
            for value in ratios
        ):
            raise ValueError("path jitter ratios must be finite and bounded")

    def analyze(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        provider_factory: ProviderFactory,
    ) -> CandlePathMonteCarloReport:
        if len(candles) < 3:
            raise ValueError("path Monte Carlo requires at least three candles")
        random = Random(self.seed)  # noqa: S311  # nosec B311
        returns: list[float] = []
        drawdowns: list[float] = []
        trade_counts: list[int] = []
        for _ in range(self.simulations):
            perturbed = self._perturb(candles, random)
            result = BacktestEngine(self.config).run(
                symbol=symbol,
                timeframe=timeframe,
                candles=perturbed,
                signal_provider=provider_factory(),
            )
            returns.append(result.metrics.net_return)
            drawdowns.append(result.metrics.max_drawdown)
            trade_counts.append(result.metrics.trade_count)
        returns.sort()
        drawdowns.sort()
        probability_of_loss = sum(value < 0.0 for value in returns) / len(returns)
        return_range = returns[-1] - returns[0]
        blockers: list[str] = []
        if min(trade_counts) < 5:
            blockers.append("PATH_MONTE_CARLO_TRADE_COUNT_LOW")
        if probability_of_loss > 0.5:
            blockers.append("PATH_MONTE_CARLO_LOSS_PROBABILITY_HIGH")
        if self._percentile(returns, 0.05) <= 0.0:
            blockers.append("PATH_MONTE_CARLO_P05_NOT_POSITIVE")
        if return_range > self.maximum_return_range:
            blockers.append("PATH_DEPENDENT_EDGE")
        unique = tuple(dict.fromkeys(blockers))
        return CandlePathMonteCarloReport(
            simulations=self.simulations,
            seed=self.seed,
            median_net_return=self._percentile(returns, 0.5),
            p05_net_return=self._percentile(returns, 0.05),
            p95_max_drawdown=self._percentile(drawdowns, 0.95),
            probability_of_loss=probability_of_loss,
            return_range=return_range,
            blockers=unique,
            promotion_status=(
                ValidationStatus.RESEARCH_ONLY
                if unique
                else ValidationStatus.STAGED_CANDIDATE
            ),
        )

    def _perturb(
        self,
        candles: tuple[OHLCVCandle, ...],
        random: Random,
    ) -> tuple[OHLCVCandle, ...]:
        output: list[OHLCVCandle] = []
        for candle in candles:
            open_price = self._jitter(
                candle.open, self.maximum_price_jitter_ratio, random
            )
            close = self._jitter(candle.close, self.maximum_price_jitter_ratio, random)
            high_candidate = self._jitter(
                candle.high, self.maximum_price_jitter_ratio, random
            )
            low_candidate = self._jitter(
                candle.low, self.maximum_price_jitter_ratio, random
            )
            high = max(open_price, close, high_candidate)
            low = min(open_price, close, low_candidate)
            volume = max(
                Decimal("0"),
                self._jitter(candle.volume, self.maximum_volume_jitter_ratio, random),
            )
            output.append(
                OHLCVCandle(candle.timestamp, open_price, high, low, close, volume)
            )
        return tuple(output)

    @staticmethod
    def _jitter(value: Decimal, ratio: Decimal, random: Random) -> Decimal:
        unit = Decimal(str(random.uniform(-1.0, 1.0)))  # nosec B311
        return value * (ONE + ratio * unit)

    @staticmethod
    def _percentile(values: list[float], ratio: float) -> float:
        return values[round((len(values) - 1) * ratio)]

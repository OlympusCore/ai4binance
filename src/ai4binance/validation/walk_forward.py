"""Chronological train-only selection and untouched OOS evaluation."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from hashlib import sha256
from itertools import pairwise
from typing import Protocol

from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting.engine import BacktestEngine, SignalProvider
from ai4binance.research.backtesting.futures_engine import (
    FuturesBacktestEngine,
    FuturesBacktestIntent,
)
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    BacktestResult,
    TradeDirection,
    TradeRecord,
)
from ai4binance.schemas import OHLCVCandle, OOSValidationStatus
from ai4binance.validation.futures_backtest_adapter import (
    runtime_futures_backtest_engine,
)
from ai4binance.validation.futures_oos import (
    FUTURES_OOS_STRATEGY_ID,
    FUTURES_OOS_STRATEGY_VERSION,
)
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.validation.models import (
    MarketRegime,
    ParameterSet,
    RegimePerformance,
    RobustnessAssessment,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardMode,
    WalkForwardReport,
)
from ai4binance.validation.statistics import assess_statistical_evidence
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    PriceOiRegime,
)

StrategyFactory = Callable[[ParameterSet], SignalProvider]
RegimeClassifier = Callable[[OHLCVCandle], MarketRegime]


class FuturesReplayStrategy(Protocol):
    """Callable strategy with an exact hash-bound Futures identity."""

    @property
    def strategy_sha256(self) -> str: ...

    def __call__(
        self,
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None: ...


FuturesStrategyFactory = Callable[[ParameterSet], FuturesReplayStrategy]


@dataclass(frozen=True, slots=True)
class _FoldWindow:
    train: tuple[OHLCVCandle, ...]
    test: tuple[OHLCVCandle, ...]


@dataclass(frozen=True, slots=True)
class _FuturesFoldWindow:
    train: RuntimeFuturesReplayDataset
    test: RuntimeFuturesReplayDataset


@dataclass(frozen=True, slots=True)
class _EvaluatedFuturesFold:
    fold: WalkForwardFold
    strategy_sha256: str


@dataclass(frozen=True, slots=True)
class WalkForwardValidator:
    """Select on train windows and evaluate each test window exactly once."""

    backtest_engine: BacktestEngine = field(default_factory=BacktestEngine)

    def validate(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        parameters: tuple[ParameterSet, ...],
        strategy_factory: StrategyFactory,
        regime_classifier: RegimeClassifier,
        config: WalkForwardConfig,
        hypothesis_count: int | None = None,
    ) -> WalkForwardReport:
        self._validate_inputs(symbol, timeframe, candles, parameters)
        family_size = len(parameters) if hypothesis_count is None else hypothesis_count
        if type(family_size) is not int or family_size < len(parameters):
            raise ValueError(
                "hypothesis count must cover the evaluated parameter family"
            )
        windows = self._build_windows(candles, config)
        folds = tuple(
            self._evaluate_fold(
                fold_index=index,
                symbol=symbol,
                timeframe=timeframe,
                window=window,
                parameters=parameters,
                strategy_factory=strategy_factory,
            )
            for index, window in enumerate(windows)
        )
        regime_performance = self._regime_performance(
            folds,
            windows,
            regime_classifier,
        )
        robustness = self._assess_robustness(
            folds,
            windows,
            regime_performance,
            config,
        )
        statistical_evidence = assess_statistical_evidence(
            tuple(fold.oos_result.metrics.net_return for fold in folds),
            hypothesis_count=family_size,
            min_effective_sample_size=config.min_effective_sample_size,
            minimum_return=config.min_oos_net_return,
            confidence_level=config.confidence_level,
            correction=config.multiple_testing_correction,
            confirmatory=config.confirmatory,
        )
        blockers = list(robustness.blockers)
        blockers.extend(statistical_evidence.blockers)
        if len(folds) < config.min_folds:
            blockers.append("INSUFFICIENT_WALK_FORWARD_FOLDS")
        unique_blockers = tuple(dict.fromkeys(blockers))
        approved = not unique_blockers
        return WalkForwardReport(
            report_id=self._report_id(symbol, timeframe, folds),
            symbol=symbol.strip().upper(),
            timeframe=timeframe,
            created_at=folds[-1].test_ended_at,
            config=config,
            folds=folds,
            regime_performance=regime_performance,
            robustness=replace_blockers(robustness, unique_blockers),
            statistical_evidence=statistical_evidence,
            oos_validation_status=(
                OOSValidationStatus.APPROVED
                if approved
                else OOSValidationStatus.INSUFFICIENT
            ),
            promotion_status=(
                ValidationStatus.STAGED_CANDIDATE
                if approved
                else ValidationStatus.RESEARCH_ONLY
            ),
            blockers=unique_blockers,
        )

    def _evaluate_fold(
        self,
        *,
        fold_index: int,
        symbol: str,
        timeframe: str,
        window: _FoldWindow,
        parameters: tuple[ParameterSet, ...],
        strategy_factory: StrategyFactory,
    ) -> WalkForwardFold:
        training_results = tuple(
            (
                parameter,
                self._bounded_fold_result(
                    self.backtest_engine.run(
                        symbol=symbol,
                        timeframe=timeframe,
                        candles=window.train,
                        signal_provider=strategy_factory(parameter),
                    )
                ),
            )
            for parameter in parameters
        )
        selected, training_result = max(
            training_results,
            key=lambda item: (self._training_objective(item[1]), item[0].name),
        )
        objective = self._training_objective(training_result)
        oos_result = self._bounded_fold_result(
            self.backtest_engine.run(
                symbol=symbol,
                timeframe=timeframe,
                candles=window.test,
                signal_provider=strategy_factory(selected),
            )
        )
        return WalkForwardFold(
            fold_index=fold_index,
            train_started_at=window.train[0].timestamp,
            train_ended_at=window.train[-1].timestamp,
            test_started_at=window.test[0].timestamp,
            test_ended_at=window.test[-1].timestamp,
            selected_parameters=selected,
            training_objective=objective,
            training_result=training_result,
            oos_result=oos_result,
        )

    @staticmethod
    def _bounded_fold_result(result: BacktestResult) -> BacktestResult:
        """Retain decision inputs while releasing duplicated high-volume ledgers."""

        return replace(
            result,
            rejected_signals=(),
            audit_events=(),
            equity_curve=(),
            false_breakouts=(),
            trade_outcomes=(),
            missed_opportunity_ledger=type(result.missed_opportunity_ledger)(),
        )

    @staticmethod
    def _training_objective(result: BacktestResult) -> float:
        metrics = result.metrics
        low_count_penalty = 0.02 if metrics.trade_count < 5 else 0.0
        expectancy_penalty = 0.02 if metrics.expectancy_usdt <= 0.0 else 0.0
        return (
            metrics.net_return
            - metrics.max_drawdown
            - low_count_penalty
            - expectancy_penalty
        )

    @staticmethod
    def _build_windows(
        candles: tuple[OHLCVCandle, ...],
        config: WalkForwardConfig,
    ) -> tuple[_FoldWindow, ...]:
        windows: list[_FoldWindow] = []
        fold_index = 0
        while True:
            stride = config.step_size + config.embargo_size
            if config.mode is WalkForwardMode.ANCHORED:
                train_start = 0
                train_end = config.train_size + fold_index * stride
            else:
                train_start = fold_index * stride
                train_end = train_start + config.train_size
            test_start = train_end + config.purge_size
            test_end = test_start + config.test_size
            if test_end > len(candles):
                break
            windows.append(
                _FoldWindow(
                    train=candles[train_start:train_end],
                    test=candles[test_start:test_end],
                )
            )
            fold_index += 1
        if not windows:
            raise ValueError("insufficient candles for one walk-forward fold")
        return tuple(windows)

    @staticmethod
    def _regime_performance(
        folds: tuple[WalkForwardFold, ...],
        windows: tuple[_FoldWindow, ...],
        classifier: RegimeClassifier,
    ) -> tuple[RegimePerformance, ...]:
        candle_counts: dict[MarketRegime, int] = {}
        trades: dict[MarketRegime, list[TradeRecord]] = {}
        regimes_by_timestamp: dict[datetime, MarketRegime] = {}
        for window in windows:
            for candle in window.test:
                regime = classifier(candle)
                if not isinstance(regime, MarketRegime):
                    raise TypeError("regime classifier must return MarketRegime")
                candle_counts[regime] = candle_counts.get(regime, 0) + 1
                regimes_by_timestamp[candle.timestamp] = regime
        for fold in folds:
            for trade in fold.oos_result.trades:
                regime = regimes_by_timestamp.get(
                    trade.entry_timestamp,
                    MarketRegime.UNKNOWN,
                )
                trades.setdefault(regime, []).append(trade)
        regimes = sorted(set(candle_counts) | set(trades), key=lambda item: item.value)
        return tuple(
            WalkForwardValidator._one_regime_performance(
                regime,
                candle_counts.get(regime, 0),
                trades.get(regime, []),
            )
            for regime in regimes
        )

    @staticmethod
    def _one_regime_performance(
        regime: MarketRegime,
        candle_count: int,
        trades: list[TradeRecord],
    ) -> RegimePerformance:
        pnl = [float(trade.net_pnl_usdt) for trade in trades]
        wins = sum(value > 0.0 for value in pnl)
        return RegimePerformance(
            regime=regime,
            candle_count=candle_count,
            trade_count=len(trades),
            net_pnl_usdt=sum(pnl),
            win_rate=wins / len(pnl) if pnl else 0.0,
        )

    def _assess_robustness(
        self,
        folds: tuple[WalkForwardFold, ...],
        windows: tuple[_FoldWindow, ...],
        regime_performance: tuple[RegimePerformance, ...],
        config: WalkForwardConfig,
    ) -> RobustnessAssessment:
        trades = tuple(trade for fold in folds for trade in fold.oos_result.trades)
        returns = [fold.oos_result.metrics.net_return for fold in folds]
        total_candles = sum(len(window.test) for window in windows)
        profitable_fold_ratio = sum(value > 0.0 for value in returns) / len(returns)
        oos_net_return = sum(returns) / len(returns)
        worst_drawdown = max(fold.oos_result.metrics.max_drawdown for fold in folds)
        turnover = len(trades) / total_candles
        edge_concentration = self._edge_concentration(trades)
        switch_rate = self._parameter_switch_rate(folds)
        regime_count = sum(item.candle_count > 0 for item in regime_performance)
        blockers = self._robustness_blockers(
            total_trades=len(trades),
            profitable_fold_ratio=profitable_fold_ratio,
            oos_net_return=oos_net_return,
            worst_drawdown=worst_drawdown,
            turnover=turnover,
            edge_concentration=edge_concentration,
            switch_rate=switch_rate,
            regime_count=regime_count,
            config=config,
        )
        return RobustnessAssessment(
            total_oos_trades=len(trades),
            profitable_fold_ratio=profitable_fold_ratio,
            oos_net_return=oos_net_return,
            worst_fold_drawdown=worst_drawdown,
            turnover=turnover,
            edge_concentration=edge_concentration,
            parameter_switch_rate=switch_rate,
            regime_count=regime_count,
            blockers=blockers,
        )

    @staticmethod
    def _edge_concentration(trades: tuple[TradeRecord, ...]) -> float:
        positive = [
            float(trade.net_pnl_usdt) for trade in trades if trade.net_pnl_usdt > 0
        ]
        gross_profit = sum(positive)
        return max(positive) / gross_profit if gross_profit > 0.0 else 1.0

    @staticmethod
    def _parameter_switch_rate(folds: tuple[WalkForwardFold, ...]) -> float:
        if len(folds) < 2:
            return 0.0
        switches = sum(
            current.selected_parameters != previous.selected_parameters
            for previous, current in pairwise(folds)
        )
        return switches / (len(folds) - 1)

    @staticmethod
    def _robustness_blockers(
        *,
        total_trades: int,
        profitable_fold_ratio: float,
        oos_net_return: float,
        worst_drawdown: float,
        turnover: float,
        edge_concentration: float,
        switch_rate: float,
        regime_count: int,
        config: WalkForwardConfig,
    ) -> tuple[str, ...]:
        checks = (
            (total_trades < config.min_oos_trades, "LOW_OOS_TRADE_COUNT"),
            (
                profitable_fold_ratio < config.min_profitable_fold_ratio,
                "WEAK_OOS_FOLD_CONSISTENCY",
            ),
            (oos_net_return <= config.min_oos_net_return, "OOS_RETURN_INSUFFICIENT"),
            (worst_drawdown > config.max_oos_drawdown, "EXCESSIVE_OOS_DRAWDOWN"),
            (turnover > config.max_turnover, "EXCESSIVE_OOS_TURNOVER"),
            (
                edge_concentration > config.max_edge_concentration,
                "OOS_EDGE_CONCENTRATION",
            ),
            (
                switch_rate > config.max_parameter_switch_rate,
                "PARAMETER_INSTABILITY",
            ),
            (regime_count < config.min_regime_count, "INSUFFICIENT_REGIME_COVERAGE"),
        )
        return tuple(code for failed, code in checks if failed)

    @staticmethod
    def _report_id(
        symbol: str,
        timeframe: str,
        folds: tuple[WalkForwardFold, ...],
    ) -> str:
        payload = "|".join(
            [symbol.strip().upper(), timeframe]
            + [
                f"{fold.fold_index}:{fold.selected_parameters.name}:{fold.test_ended_at.isoformat()}"
                for fold in folds
            ]
        )
        return f"wf:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _validate_inputs(
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        parameters: tuple[ParameterSet, ...],
    ) -> None:
        if not symbol.strip() or not timeframe.strip() or not parameters:
            raise ValueError("symbol, timeframe and parameter candidates are required")
        if len(set(parameters)) != len(parameters):
            raise ValueError("parameter candidates must be unique")
        timestamps = [candle.timestamp for candle in candles]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            raise ValueError("candles must be unique and strictly chronological")


@dataclass(frozen=True, slots=True)
class FuturesWalkForwardValidator:
    """Validate hash-bound Futures strategies over complete replay windows."""

    backtest_engine: FuturesBacktestEngine = field(
        default_factory=FuturesBacktestEngine
    )
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)

    def validate(
        self,
        *,
        dataset: RuntimeFuturesReplayDataset,
        setup: PriceOiRegime,
        parameters: tuple[ParameterSet, ...],
        strategy_factory: FuturesStrategyFactory,
        regime_classifier: RegimeClassifier,
        config: WalkForwardConfig,
    ) -> WalkForwardReport:
        """Select only on training replay and evaluate untouched OOS windows."""

        self._validate_inputs(dataset, setup, parameters)
        windows = self._build_windows(dataset, config)
        backtest_engine = runtime_futures_backtest_engine(
            dataset,
            base_config=self.backtest_engine.config,
        )
        evaluated = tuple(
            self._evaluate_fold(
                fold_index=index,
                window=window,
                setup=setup,
                parameters=parameters,
                strategy_factory=strategy_factory,
                backtest_engine=backtest_engine,
            )
            for index, window in enumerate(windows)
        )
        folds = tuple(item.fold for item in evaluated)
        candle_windows = tuple(
            _FoldWindow(window.train.candles, window.test.candles) for window in windows
        )
        shared = WalkForwardValidator()
        regime_performance = shared._regime_performance(
            folds,
            candle_windows,
            regime_classifier,
        )
        robustness = shared._assess_robustness(
            folds,
            candle_windows,
            regime_performance,
            config,
        )
        statistical_evidence = assess_statistical_evidence(
            tuple(fold.oos_result.metrics.net_return for fold in folds),
            hypothesis_count=len(parameters),
            min_effective_sample_size=config.min_effective_sample_size,
            minimum_return=config.min_oos_net_return,
            confidence_level=config.confidence_level,
            correction=config.multiple_testing_correction,
            confirmatory=config.confirmatory,
        )
        blockers = [*robustness.blockers, *statistical_evidence.blockers]
        if len(folds) < config.min_folds:
            blockers.append("INSUFFICIENT_WALK_FORWARD_FOLDS")
        blockers.extend(self._futures_blockers(evaluated))
        unique_blockers = tuple(dict.fromkeys(blockers))
        approved = not unique_blockers
        return WalkForwardReport(
            report_id=self._report_id(dataset, folds),
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            created_at=folds[-1].test_ended_at,
            config=config,
            folds=folds,
            regime_performance=regime_performance,
            robustness=replace_blockers(robustness, unique_blockers),
            statistical_evidence=statistical_evidence,
            oos_validation_status=(
                OOSValidationStatus.APPROVED
                if approved
                else OOSValidationStatus.INSUFFICIENT
            ),
            promotion_status=(
                ValidationStatus.STAGED_CANDIDATE
                if approved
                else ValidationStatus.RESEARCH_ONLY
            ),
            blockers=unique_blockers,
        )

    def _evaluate_fold(
        self,
        *,
        fold_index: int,
        window: _FuturesFoldWindow,
        setup: PriceOiRegime,
        parameters: tuple[ParameterSet, ...],
        strategy_factory: FuturesStrategyFactory,
        backtest_engine: FuturesBacktestEngine,
    ) -> _EvaluatedFuturesFold:
        training_results = tuple(
            self._training_result(
                parameter,
                window.train,
                setup,
                strategy_factory,
                backtest_engine,
            )
            for parameter in parameters
        )
        selected, training_result, strategy_sha256 = max(
            training_results,
            key=lambda item: (
                WalkForwardValidator._training_objective(item[1]),
                item[0].name,
            ),
        )
        objective = WalkForwardValidator._training_objective(training_result)
        oos_strategy = strategy_factory(selected)
        self._validate_strategy(oos_strategy)
        if oos_strategy.strategy_sha256 != strategy_sha256:
            raise ValueError("Futures strategy factory identity is non-deterministic")
        oos_result = backtest_engine.run(
            dataset=window.test,
            signal_provider=oos_strategy,
        )
        self._validate_result(
            oos_result,
            dataset=window.test,
            setup=setup,
            strategy_sha256=strategy_sha256,
        )
        return _EvaluatedFuturesFold(
            fold=WalkForwardFold(
                fold_index=fold_index,
                train_started_at=window.train.candles[0].timestamp,
                train_ended_at=window.train.candles[-1].timestamp,
                test_started_at=window.test.candles[0].timestamp,
                test_ended_at=window.test.candles[-1].timestamp,
                selected_parameters=selected,
                training_objective=objective,
                training_result=training_result,
                oos_result=oos_result,
            ),
            strategy_sha256=strategy_sha256,
        )

    def _training_result(
        self,
        parameter: ParameterSet,
        dataset: RuntimeFuturesReplayDataset,
        setup: PriceOiRegime,
        strategy_factory: FuturesStrategyFactory,
        backtest_engine: FuturesBacktestEngine,
    ) -> tuple[ParameterSet, BacktestResult, str]:
        strategy = strategy_factory(parameter)
        self._validate_strategy(strategy)
        result = backtest_engine.run(
            dataset=dataset,
            signal_provider=strategy,
        )
        self._validate_result(
            result,
            dataset=dataset,
            setup=setup,
            strategy_sha256=strategy.strategy_sha256,
        )
        return parameter, result, strategy.strategy_sha256

    @staticmethod
    def _validate_strategy(strategy: FuturesReplayStrategy) -> None:
        strategy_sha256 = getattr(strategy, "strategy_sha256", "")
        if (
            not callable(strategy)
            or not isinstance(strategy_sha256, str)
            or len(strategy_sha256) != 64
            or any(character not in "0123456789abcdef" for character in strategy_sha256)
        ):
            raise ValueError("Futures strategy identity must be a lowercase SHA-256")

    @staticmethod
    def _validate_result(
        result: BacktestResult,
        *,
        dataset: RuntimeFuturesReplayDataset,
        setup: PriceOiRegime,
        strategy_sha256: str,
    ) -> None:
        performance = result.performance_engine_report
        expected_direction = (
            TradeDirection.LONG
            if setup
            in {
                PriceOiRegime.NEW_LONG_PARTICIPATION,
                PriceOiRegime.SHORT_COVERING,
            }
            else TradeDirection.SHORT
        )
        invalid_result = (
            result.symbol != dataset.symbol
            or result.timeframe != dataset.timeframe
            or result.started_at != dataset.candles[0].timestamp
            or result.ended_at != dataset.candles[-1].timestamp
            or result.metrics.market != "USD_M_FUTURES"
            or result.metrics.trade_count != len(result.trades)
            or performance.spot_metrics is not None
            or performance.futures_metrics != result.metrics
            or any(
                "DATA_UNAVAILABLE" in rejected.blockers
                for rejected in result.rejected_signals
            )
            or result.trade_outcomes
            != tuple(trade.trade_outcome for trade in result.trades)
        )
        expected_lineage = (
            FUTURES_OOS_STRATEGY_ID,
            FUTURES_OOS_STRATEGY_VERSION,
            strategy_sha256,
            "USD_M_FUTURES",
            dataset.symbol,
            setup.value,
            dataset.timeframe,
            expected_direction,
        )
        invalid_trade = any(
            (
                trade.attribution.strategy_id,
                trade.attribution.strategy_version,
                trade.attribution.strategy_config_hash,
                trade.attribution.market,
                trade.attribution.symbol,
                trade.attribution.regime,
                trade.attribution.timeframe,
                trade.direction,
            )
            != expected_lineage
            for trade in result.trades
        )
        if invalid_result or invalid_trade:
            raise ValueError("Futures walk-forward result lineage is invalid")

    @staticmethod
    def _futures_blockers(
        evaluated: tuple[_EvaluatedFuturesFold, ...],
    ) -> tuple[str, ...]:
        results = tuple(
            result
            for item in evaluated
            for result in (item.fold.training_result, item.fold.oos_result)
        )
        blockers: list[str] = []
        if len({item.strategy_sha256 for item in evaluated}) != 1:
            blockers.append("FUTURES_STRATEGY_LINEAGE_INCONSISTENT")
        if any(
            trade.exit_reason is BacktestExitReason.LIQUIDATION
            for result in results
            for trade in result.trades
        ):
            blockers.append("FUTURES_LIQUIDATION_OCCURRED")
        invalid_geometry = {
            "FUTURES_LONG_GEOMETRY_INVALID",
            "FUTURES_SHORT_GEOMETRY_INVALID",
            "STOP_BEYOND_LIQUIDATION",
        }
        if any(
            invalid_geometry.intersection(rejected.blockers)
            for result in results
            for rejected in result.rejected_signals
        ):
            blockers.append("FUTURES_ENTRY_GEOMETRY_REJECTED")
        return tuple(blockers)

    @classmethod
    def _build_windows(
        cls,
        dataset: RuntimeFuturesReplayDataset,
        config: WalkForwardConfig,
    ) -> tuple[_FuturesFoldWindow, ...]:
        windows: list[_FuturesFoldWindow] = []
        fold_index = 0
        while True:
            stride = config.step_size + config.embargo_size
            if config.mode is WalkForwardMode.ANCHORED:
                train_start = 0
                train_end = config.train_size + fold_index * stride
            else:
                train_start = fold_index * stride
                train_end = train_start + config.train_size
            test_start = train_end + config.purge_size
            test_end = test_start + config.test_size
            if test_end > len(dataset.candles):
                break
            windows.append(
                _FuturesFoldWindow(
                    train=cls._slice_dataset(dataset, train_start, train_end),
                    test=cls._slice_dataset(dataset, test_start, test_end),
                )
            )
            fold_index += 1
        if not windows:
            raise ValueError("insufficient Futures replay for one walk-forward fold")
        return tuple(windows)

    @staticmethod
    def _slice_dataset(
        dataset: RuntimeFuturesReplayDataset,
        start: int,
        end: int,
    ) -> RuntimeFuturesReplayDataset:
        candles = dataset.candles[start:end]
        first_timestamp = candles[0].timestamp
        last_timestamp = candles[-1].timestamp
        series = {
            metric: tuple(
                point
                for point in points
                if first_timestamp <= point.timestamp <= last_timestamp
            )
            for metric, points in dataset.derivatives.series.items()
        }
        if not series.get(DerivativesMetric.FUNDING_RATE):
            raise ValueError(
                "Futures walk-forward window funding coverage is unavailable"
            )
        derivatives = DerivativesDataset(
            symbol=dataset.symbol,
            as_of=dataset.derivatives.as_of,
            series=series,
            source=dataset.derivatives.source,
        )
        return RuntimeFuturesReplayDataset(
            symbol=dataset.symbol,
            candles=candles,
            derivatives=derivatives,
            timeframe=dataset.timeframe,
        )

    @staticmethod
    def _validate_inputs(
        dataset: RuntimeFuturesReplayDataset,
        setup: PriceOiRegime,
        parameters: tuple[ParameterSet, ...],
    ) -> None:
        if not isinstance(dataset, RuntimeFuturesReplayDataset):
            raise TypeError("Futures walk-forward requires a replay dataset")
        if setup not in {
            PriceOiRegime.NEW_LONG_PARTICIPATION,
            PriceOiRegime.SHORT_COVERING,
            PriceOiRegime.NEW_SHORT_PRESSURE,
            PriceOiRegime.DELEVERAGING,
        }:
            raise ValueError("Futures walk-forward setup must be directional")
        WalkForwardValidator._validate_inputs(
            dataset.symbol,
            dataset.timeframe,
            dataset.candles,
            parameters,
        )

    @staticmethod
    def _report_id(
        dataset: RuntimeFuturesReplayDataset,
        folds: tuple[WalkForwardFold, ...],
    ) -> str:
        payload = "|".join(
            ["USD_M_FUTURES", dataset.symbol, dataset.timeframe]
            + [
                f"{fold.fold_index}:{fold.selected_parameters.name}:"
                f"{fold.test_ended_at.isoformat()}"
                for fold in folds
            ]
        )
        return f"futures-wf:{sha256(payload.encode()).hexdigest()[:20]}"


def replace_blockers(
    assessment: RobustnessAssessment,
    blockers: tuple[str, ...],
) -> RobustnessAssessment:
    """Return a report-consistent immutable robustness assessment."""
    return RobustnessAssessment(
        total_oos_trades=assessment.total_oos_trades,
        profitable_fold_ratio=assessment.profitable_fold_ratio,
        oos_net_return=assessment.oos_net_return,
        worst_fold_drawdown=assessment.worst_fold_drawdown,
        turnover=assessment.turnover,
        edge_concentration=assessment.edge_concentration,
        parameter_switch_rate=assessment.parameter_switch_rate,
        regime_count=assessment.regime_count,
        blockers=blockers,
    )

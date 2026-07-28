"""Chronological train-only selection and untouched OOS evaluation."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from itertools import pairwise

from ai4binance.backtest.engine import BacktestEngine, SignalProvider
from ai4binance.backtest.models import BacktestResult, TradeRecord
from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle, OOSValidationStatus
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

StrategyFactory = Callable[[ParameterSet], SignalProvider]
RegimeClassifier = Callable[[OHLCVCandle], MarketRegime]


@dataclass(frozen=True, slots=True)
class _FoldWindow:
    train: tuple[OHLCVCandle, ...]
    test: tuple[OHLCVCandle, ...]


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
    ) -> WalkForwardReport:
        self._validate_inputs(symbol, timeframe, candles, parameters)
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
            hypothesis_count=len(parameters),
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
                self.backtest_engine.run(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=window.train,
                    signal_provider=strategy_factory(parameter),
                ),
            )
            for parameter in parameters
        )
        selected, training_result = max(
            training_results,
            key=lambda item: (self._training_objective(item[1]), item[0].name),
        )
        objective = self._training_objective(training_result)
        oos_result = self.backtest_engine.run(
            symbol=symbol,
            timeframe=timeframe,
            candles=window.test,
            signal_provider=strategy_factory(selected),
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

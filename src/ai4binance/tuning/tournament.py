"""Research-only parameter-profile tournament backed by walk-forward evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite, sqrt

from ai4binance.research.backtesting.metrics import calculate_metrics
from ai4binance.research.backtesting.models import TradeRecord
from ai4binance.research.backtesting.robustness import BacktestRobustnessAnalyzer
from ai4binance.tuning.models import (
    StrategyParameterTournamentReport,
    StrategyProfileCandidate,
    TournamentConfig,
    TournamentContext,
    TournamentContextEvaluation,
    TournamentEntry,
)
from ai4binance.validation.models import MarketRegime, ParameterSet, RegimePerformance
from ai4binance.validation.walk_forward import (
    RegimeClassifier,
    StrategyFactory,
    WalkForwardValidator,
)


@dataclass(frozen=True, slots=True)
class StrategyParameterTournament:
    """Compare a bounded profile set without changing promotion authority."""

    validator: WalkForwardValidator = field(default_factory=WalkForwardValidator)
    robustness_analyzer: BacktestRobustnessAnalyzer = field(
        default_factory=BacktestRobustnessAnalyzer
    )

    def run(
        self,
        *,
        contexts: tuple[TournamentContext, ...],
        candidates: tuple[StrategyProfileCandidate, ...],
        strategy_factory: StrategyFactory,
        regime_classifier: RegimeClassifier,
        config: TournamentConfig,
    ) -> StrategyParameterTournamentReport:
        if not contexts:
            raise ValueError("tournament requires at least one context")
        if not candidates:
            raise ValueError("tournament requires at least one candidate")
        entries = tuple(
            self._evaluate_candidate(
                candidate=candidate,
                contexts=contexts,
                strategy_factory=strategy_factory,
                regime_classifier=regime_classifier,
                config=config,
            )
            for candidate in candidates
        )
        ranked_entries = tuple(sorted(entries, key=self._ranking_key))
        return StrategyParameterTournamentReport(
            report_id=self._report_id(contexts, ranked_entries, config),
            created_at=ranked_entries[0].evaluations[0].walk_forward_report.created_at,
            config=config,
            entries=ranked_entries,
        )

    def _evaluate_candidate(
        self,
        *,
        candidate: StrategyProfileCandidate,
        contexts: tuple[TournamentContext, ...],
        strategy_factory: StrategyFactory,
        regime_classifier: RegimeClassifier,
        config: TournamentConfig,
    ) -> TournamentEntry:
        evaluations = tuple(
            self._evaluate_context(
                context=context,
                parameters=candidate.parameters,
                strategy_factory=strategy_factory,
                regime_classifier=regime_classifier,
                config=config,
            )
            for context in contexts
        )
        trades = tuple(
            trade
            for evaluation in evaluations
            for fold in evaluation.walk_forward_report.folds
            for trade in fold.oos_result.trades
        )
        initial_cash = sum(
            float(fold.oos_result.assumptions.initial_cash_usdt)
            for evaluation in evaluations
            for fold in evaluation.walk_forward_report.folds
        )
        metrics = calculate_metrics(
            trades,
            initial_cash=initial_cash or 1.0,
            buy_and_hold_return=0.0,
        )
        blockers = self._blockers(
            evaluations, metrics.trade_count, metrics.max_drawdown, config
        )
        return TournamentEntry(
            profile_id=candidate.profile_id,
            parameters=candidate.parameters,
            evaluations=evaluations,
            net_return_after_costs=metrics.net_return,
            profit_factor=metrics.profit_factor,
            expectancy=metrics.expectancy_usdt,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            sortino=self._sortino(trades),
            trade_count=metrics.trade_count,
            win_rate=metrics.win_rate,
            average_r=self._average_r(trades),
            tail_loss=self._tail_loss(trades),
            parameter_stability=self._parameter_stability(evaluations),
            regime_breakdown=self._regime_breakdown(evaluations),
            blockers=blockers,
        )

    def _evaluate_context(
        self,
        *,
        context: TournamentContext,
        parameters: ParameterSet,
        strategy_factory: StrategyFactory,
        regime_classifier: RegimeClassifier,
        config: TournamentConfig,
    ) -> TournamentContextEvaluation:
        report = self.validator.validate(
            symbol=context.symbol,
            timeframe=context.timeframe,
            candles=context.candles,
            parameters=(parameters,),
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=config.walk_forward,
        )
        robustness = self.robustness_analyzer.analyze(
            symbol=context.symbol,
            timeframe=context.timeframe,
            candles=context.candles,
            provider_factory=lambda: strategy_factory(parameters),
        )
        stress_net_returns = tuple(
            (item.scenario.name, item.net_return) for item in robustness.stress_results
        )
        return TournamentContextEvaluation(
            context=context,
            walk_forward_report=report,
            robustness_blockers=robustness.blockers,
            stress_net_returns=stress_net_returns,
            bootstrap_probability_of_loss=robustness.bootstrap.probability_of_loss,
            bootstrap_p95_max_drawdown=robustness.bootstrap.p95_max_drawdown,
        )

    @staticmethod
    def _blockers(
        evaluations: tuple[TournamentContextEvaluation, ...],
        trade_count: int,
        max_drawdown: float,
        config: TournamentConfig,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        blockers.extend(
            blocker
            for evaluation in evaluations
            for blocker in evaluation.walk_forward_report.blockers
        )
        blockers.extend(
            blocker
            for evaluation in evaluations
            for blocker in evaluation.robustness_blockers
        )
        if trade_count < config.min_trade_count:
            blockers.append("TOURNAMENT_TRADE_COUNT_INSUFFICIENT")
        if max_drawdown > config.walk_forward.max_oos_drawdown:
            blockers.append("TOURNAMENT_OOS_DRAWDOWN_EXCESSIVE")

        symbols = tuple(
            evaluation.context.symbol.strip().upper() for evaluation in evaluations
        )
        timeframes = tuple(
            evaluation.context.timeframe.strip() for evaluation in evaluations
        )
        if len(set(symbols)) < config.min_symbol_count:
            blockers.append("TOURNAMENT_SYMBOL_DIVERSITY_INSUFFICIENT")
        elif (
            StrategyParameterTournament._max_share(symbols)
            > config.max_symbol_concentration
        ):
            blockers.append("TOURNAMENT_SYMBOL_DEPENDENCY_EXCESSIVE")
        if len(set(timeframes)) < config.min_timeframe_count:
            blockers.append("TOURNAMENT_TIMEFRAME_DIVERSITY_INSUFFICIENT")
        elif (
            StrategyParameterTournament._max_share(timeframes)
            > config.max_timeframe_concentration
        ):
            blockers.append("TOURNAMENT_TIMEFRAME_DEPENDENCY_EXCESSIVE")

        positive_context_ratio = sum(
            evaluation.walk_forward_report.robustness.oos_net_return > 0.0
            for evaluation in evaluations
        ) / len(evaluations)
        if positive_context_ratio < config.walk_forward.min_profitable_fold_ratio:
            blockers.append("TOURNAMENT_OOS_DEGRADATION")
        if any(
            StrategyParameterTournament._worst_stress_ratio(
                evaluation.stress_net_returns,
                evaluation.walk_forward_report.robustness.oos_net_return,
            )
            < config.min_stress_return_ratio
            for evaluation in evaluations
        ):
            blockers.append("TOURNAMENT_COST_STRESS_COLLAPSE")
        return tuple(dict.fromkeys(blockers))

    @staticmethod
    def _max_share(values: tuple[str, ...]) -> float:
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return max(counts.values()) / len(values)

    @staticmethod
    def _worst_stress_ratio(
        stress_net_returns: tuple[tuple[str, float], ...],
        base_net_return: float,
    ) -> float:
        if not stress_net_returns:
            return 0.0
        if base_net_return <= 0.0:
            return 0.0
        worst = min(net_return for _name, net_return in stress_net_returns)
        return worst / base_net_return

    @staticmethod
    def _average_r(trades: tuple[TradeRecord, ...]) -> float:
        if not trades:
            return 0.0
        return sum(float(trade.realized_r_multiple) for trade in trades) / len(trades)

    @staticmethod
    def _tail_loss(trades: tuple[TradeRecord, ...]) -> float:
        pnl = sorted(float(trade.net_pnl_usdt) for trade in trades)
        if not pnl:
            return 0.0
        index = round((len(pnl) - 1) * 0.05)
        return pnl[index]

    @staticmethod
    def _sortino(trades: tuple[TradeRecord, ...]) -> float | None:
        pnl = [float(trade.net_pnl_usdt) for trade in trades]
        if len(pnl) < 2:
            return None
        mean = sum(pnl) / len(pnl)
        downside = [min(0.0, value) for value in pnl]
        downside_variance = sum(value * value for value in downside) / len(downside)
        if downside_variance == 0.0:
            return None
        score = mean / sqrt(downside_variance) * sqrt(len(pnl))
        return score if isfinite(score) else None

    @staticmethod
    def _parameter_stability(
        evaluations: tuple[TournamentContextEvaluation, ...],
    ) -> float:
        return 1.0 - (
            sum(
                evaluation.walk_forward_report.robustness.parameter_switch_rate
                for evaluation in evaluations
            )
            / len(evaluations)
        )

    @staticmethod
    def _regime_breakdown(
        evaluations: tuple[TournamentContextEvaluation, ...],
    ) -> tuple[RegimePerformance, ...]:
        totals: dict[str, dict[str, float]] = defaultdict(
            lambda: {"candles": 0.0, "trades": 0.0, "pnl": 0.0, "wins": 0.0}
        )
        regime_lookup: dict[str, MarketRegime] = {}
        for evaluation in evaluations:
            for item in evaluation.walk_forward_report.regime_performance:
                key = item.regime.value
                regime_lookup[key] = item.regime
                totals[key]["candles"] += item.candle_count
                totals[key]["trades"] += item.trade_count
                totals[key]["pnl"] += item.net_pnl_usdt
                totals[key]["wins"] += item.win_rate * item.trade_count
        breakdown: list[RegimePerformance] = []
        for key in sorted(totals):
            trades = int(totals[key]["trades"])
            breakdown.append(
                RegimePerformance(
                    regime=regime_lookup[key],
                    candle_count=int(totals[key]["candles"]),
                    trade_count=trades,
                    net_pnl_usdt=totals[key]["pnl"],
                    win_rate=(totals[key]["wins"] / trades) if trades else 0.0,
                )
            )
        return tuple(breakdown)

    @staticmethod
    def _ranking_key(entry: TournamentEntry) -> tuple[object, ...]:
        return (
            bool(entry.blockers),
            -entry.net_return_after_costs,
            -(entry.profit_factor or -1.0),
            -entry.expectancy,
            entry.max_drawdown,
            -(entry.sharpe or float("-inf")),
            -(entry.sortino or float("-inf")),
            -entry.average_r,
            entry.tail_loss,
            -entry.parameter_stability,
            entry.profile_id,
        )

    @staticmethod
    def _report_id(
        contexts: tuple[TournamentContext, ...],
        entries: tuple[TournamentEntry, ...],
        config: TournamentConfig,
    ) -> str:
        context_part = "|".join(
            f"{context.symbol.strip().upper()}:{context.timeframe}:{len(context.candles)}"
            for context in contexts
        )
        entry_part = "|".join(entry.profile_id for entry in entries)
        payload = (
            f"{context_part}|{entry_part}|{config.min_trade_count}|"
            f"{config.walk_forward.train_size}:{config.walk_forward.test_size}:"
            f"{config.walk_forward.step_size}"
        )
        return f"tournament:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"

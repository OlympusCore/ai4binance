"""Evidence-counting learning engine that only proposes validation work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from typing import TYPE_CHECKING

from ai4binance.execution.lifecycle import LifecyclePosition
from ai4binance.learning.models import (
    ExperimentCandidate,
    ExperimentRecommendation,
    FailureAnalysis,
    LearningSummary,
    LessonCandidate,
    ProfitabilityExperiment,
    ProfitabilityMetric,
    ProfitabilityOptimizationLoop,
    StrategyRegimeAttribution,
)
from ai4binance.research.backtesting.models import BacktestResult, TradeRecord
from ai4binance.research.backtesting.robustness import BacktestRobustnessReport
from ai4binance.tuning.models import TuningReport
from ai4binance.validation.models import WalkForwardReport

if TYPE_CHECKING:
    from ai4binance.ops.decision_telemetry import PerformanceEvidenceSnapshot


@dataclass(frozen=True, slots=True)
class ControlledLearningEngine:
    """Aggregate validated artifacts without modifying production state."""

    def analyze(
        self,
        *,
        created_at: datetime,
        backtests: tuple[BacktestResult, ...] = (),
        walk_forward_reports: tuple[WalkForwardReport, ...] = (),
        tuning_reports: tuple[TuningReport, ...] = (),
        robustness_reports: tuple[BacktestRobustnessReport, ...] = (),
        paper_positions: tuple[LifecyclePosition, ...] = (),
        performance_snapshots: tuple[PerformanceEvidenceSnapshot, ...] = (),
    ) -> LearningSummary:
        counts: dict[str, int] = {}
        for result in backtests:
            rejected_signals = getattr(result, "rejected_signals", ())
            metrics = getattr(result, "metrics", None)
            trade_count = int(getattr(metrics, "trade_count", 0))
            self._add(counts, "REJECTED_SIGNALS", len(rejected_signals))
            self._add(counts, "LOW_TRADE_COUNT", int(trade_count < 5))
            missed_opportunity_ledger = getattr(
                result,
                "missed_opportunity_ledger",
                None,
            )
            for record in getattr(missed_opportunity_ledger, "records", ()):
                category = str(getattr(record, "counterfactual_result", "")).strip()
                if not category:
                    continue
                self._add(counts, f"MISSED_{category}", 1)
                if category == "BAD_BLOCK":
                    self._add(counts, "IMPROVEMENT_CANDIDATE", 1)
                    for blocker in getattr(record, "blockers", ()):
                        self._add(counts, f"BAD_BLOCK_{blocker}", 1)
        for walk_forward_report in walk_forward_reports:
            for blocker in getattr(walk_forward_report, "blockers", ()):
                self._add(counts, f"OOS_{blocker}", 1)
        for tuning_report in tuning_reports:
            for blocker in getattr(tuning_report, "blockers", ()):
                self._add(counts, f"TUNING_{blocker}", 1)
        for position in paper_positions:
            if position.closure_review is not None:
                self._add(counts, position.closure_review.lesson_candidate, 1)
        for snapshot in performance_snapshots:
            if not snapshot.auto_learn_consumable:
                continue
            for candidate in snapshot.improvement_candidates:
                self._add(
                    counts,
                    _performance_candidate_code(candidate.affected_component),
                    max(1, candidate.sample_size),
                )
            for root_cause_tag in getattr(snapshot, "root_cause_tags", ()):
                self._add(counts, _performance_root_cause_code(root_cause_tag), 1)
        lessons = tuple(
            LessonCandidate(code, count, self._rationale(code))
            for code, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if count > 0
        )
        experiments = tuple(
            ExperimentRecommendation(
                rank=index,
                experiment_id=f"experiment:{lesson.code.lower()}",
                objective=f"Validate mitigation for {lesson.code}",
                required_validation=("backtest", "walk_forward", "multi_regime_oos"),
            )
            for index, lesson in enumerate(lessons, start=1)
        )
        payload = "|".join(f"{item.code}:{item.evidence_count}" for item in lessons)
        profitability_loop = self._profitability_loop(
            backtests=backtests,
            walk_forward_reports=walk_forward_reports,
            tuning_reports=tuning_reports,
            robustness_reports=robustness_reports,
        )
        if profitability_loop is not None:
            payload = "|".join(
                (
                    payload,
                    profitability_loop.loop_id,
                    *(
                        f"{metric.metric_id}:{metric.value}"
                        for metric in profitability_loop.metrics
                    ),
                )
            )
        digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
        return LearningSummary(
            summary_id=f"learning:{digest}",
            created_at=created_at,
            lessons=lessons,
            experiments=experiments,
            profitability_loop=profitability_loop,
        )

    @staticmethod
    def _add(counts: dict[str, int], code: str, amount: int) -> None:
        counts[code] = counts.get(code, 0) + amount

    @staticmethod
    def _rationale(code: str) -> str:
        return f"Observed recurring evidence for {code}; validation is required."

    @classmethod
    def _profitability_loop(
        cls,
        *,
        backtests: tuple[BacktestResult, ...],
        walk_forward_reports: tuple[WalkForwardReport, ...],
        tuning_reports: tuple[TuningReport, ...],
        robustness_reports: tuple[BacktestRobustnessReport, ...],
    ) -> ProfitabilityOptimizationLoop | None:
        trades = tuple(
            trade for result in backtests for trade in getattr(result, "trades", ())
        )
        oos_trades = cls._oos_trades(walk_forward_reports, tuning_reports)
        if not trades and not oos_trades and not robustness_reports:
            return None

        metrics = (
            ProfitabilityMetric(
                "net_expectancy_after_costs",
                cls._expectancy(trades),
                supported=bool(trades),
            ),
            ProfitabilityMetric(
                "oos_expectancy",
                cls._expectancy(oos_trades),
                supported=bool(oos_trades),
            ),
            ProfitabilityMetric(
                "profit_factor",
                cls._profit_factor(trades),
                supported=cls._profit_factor(trades) is not None,
            ),
            ProfitabilityMetric(
                "max_drawdown",
                cls._max_drawdown(backtests, walk_forward_reports, tuning_reports),
            ),
            ProfitabilityMetric(
                "daily_sharpe",
                cls._daily_sharpe(backtests),
                supported=cls._daily_sharpe(backtests) is not None,
            ),
            ProfitabilityMetric(
                "sortino_if_supported",
                cls._sortino(trades),
                supported=cls._sortino(trades) is not None,
            ),
            ProfitabilityMetric(
                "average_R", cls._average_r(trades), supported=bool(trades)
            ),
            ProfitabilityMetric(
                "median_R", cls._median_r(trades), supported=bool(trades)
            ),
            ProfitabilityMetric(
                "win_rate", cls._win_rate(trades), supported=bool(trades)
            ),
            ProfitabilityMetric(
                "payoff_ratio",
                cls._payoff_ratio(trades),
                supported=cls._payoff_ratio(trades) is not None,
            ),
            ProfitabilityMetric(
                "cost_to_gross_profit_ratio",
                cls._cost_to_gross_profit_ratio(trades),
                supported=cls._cost_to_gross_profit_ratio(trades) is not None,
            ),
            ProfitabilityMetric(
                "strategy_regime_profit_factor",
                cls._strategy_regime_profit_factor(trades),
                supported=cls._strategy_regime_profit_factor(trades) is not None,
            ),
            ProfitabilityMetric(
                "profitable_walk_forward_window_ratio",
                cls._profitable_walk_forward_window_ratio(
                    walk_forward_reports, tuning_reports
                ),
                supported=bool(cls._all_folds(walk_forward_reports, tuning_reports)),
            ),
            ProfitabilityMetric(
                "candidate_to_execution_conversion",
                cls._candidate_to_execution_conversion(backtests),
                supported=(
                    cls._candidate_to_execution_conversion(backtests) is not None
                ),
            ),
            ProfitabilityMetric(
                "blocker_opportunity_cost",
                cls._blocker_opportunity_cost(backtests),
                supported=cls._blocker_opportunity_cost(backtests) is not None,
            ),
        )
        attribution = cls._strategy_regime_attribution(trades)
        failures = cls._failure_analyses(trades)
        experiment_candidates = cls._experiment_candidates(attribution)
        experiments = tuple(
            ProfitabilityExperiment(
                experiment_id=f"profitability:{analysis.improvement_candidate_id}",
                objective=analysis.rationale,
                required_validation=(
                    "bounded_experiment",
                    "walk_forward",
                    "oos",
                    "cost_stress",
                    "human_review",
                    "paper_candidate",
                ),
            )
            for analysis in failures
        )
        loop_payload = "|".join(
            (
                *(f"{metric.metric_id}:{metric.value}" for metric in metrics),
                *(item.candidate_id for item in experiment_candidates),
                *(item.analysis_id for item in failures),
                *(item.experiment_id for item in experiments),
            )
        )
        return ProfitabilityOptimizationLoop(
            loop_id=f"profitability:{sha256(loop_payload.encode('utf-8')).hexdigest()[:20]}",
            stages=(
                "ClosedTrades",
                "EdgeLedger",
                "StrategyRegimeAttribution",
                "FailureAnalysis",
                "ImprovementCandidate",
                "BoundedExperiment",
                "WalkForward",
                "OOS",
                "CostStress",
                "HumanReview",
                "PaperCandidate",
            ),
            metrics=metrics,
            strategy_regime_attribution=attribution,
            failure_analyses=failures,
            experiments=experiments,
            experiment_candidates=experiment_candidates,
        )

    @staticmethod
    def _oos_trades(
        walk_forward_reports: tuple[WalkForwardReport, ...],
        tuning_reports: tuple[TuningReport, ...],
    ) -> tuple[TradeRecord, ...]:
        return tuple(
            trade
            for fold in ControlledLearningEngine._all_folds(
                walk_forward_reports,
                tuning_reports,
            )
            for trade in getattr(getattr(fold, "oos_result", None), "trades", ())
        )

    @staticmethod
    def _all_folds(
        walk_forward_reports: tuple[WalkForwardReport, ...],
        tuning_reports: tuple[TuningReport, ...],
    ) -> tuple[object, ...]:
        direct = tuple(
            fold
            for report in walk_forward_reports
            for fold in getattr(report, "folds", ())
        )
        selected = tuple(
            fold
            for report in tuning_reports
            for fold in next(
                (
                    getattr(
                        getattr(evaluation, "walk_forward_report", None), "folds", ()
                    )
                    for evaluation in getattr(report, "evaluations", ())
                    if getattr(evaluation, "parameters", None)
                    == getattr(report, "selected_parameters", None)
                ),
                (),
            )
        )
        return (*direct, *selected)

    @staticmethod
    def _expectancy(trades: tuple[TradeRecord, ...]) -> float | None:
        if not trades:
            return None
        return sum(float(trade.net_pnl_usdt) for trade in trades) / len(trades)

    @staticmethod
    def _profit_factor(trades: tuple[TradeRecord, ...]) -> float | None:
        wins = [float(trade.net_pnl_usdt) for trade in trades if trade.net_pnl_usdt > 0]
        losses = [
            float(trade.net_pnl_usdt) for trade in trades if trade.net_pnl_usdt < 0
        ]
        gross_loss = abs(sum(losses))
        if not trades or gross_loss == 0.0:
            return None
        return sum(wins) / gross_loss

    @staticmethod
    def _max_drawdown(
        backtests: tuple[BacktestResult, ...],
        walk_forward_reports: tuple[WalkForwardReport, ...],
        tuning_reports: tuple[TuningReport, ...],
    ) -> float:
        values = [
            getattr(getattr(result, "metrics", None), "max_drawdown", 0.0)
            for result in backtests
        ]
        values.extend(
            getattr(
                getattr(getattr(fold, "oos_result", None), "metrics", None),
                "max_drawdown",
                0.0,
            )
            for fold in ControlledLearningEngine._all_folds(
                walk_forward_reports,
                tuning_reports,
            )
        )
        return max(values, default=0.0)

    @staticmethod
    def _daily_sharpe(backtests: tuple[BacktestResult, ...]) -> float | None:
        daily_returns: list[float] = []
        for result in backtests:
            by_day: dict[date, float] = {}
            for point in getattr(result, "equity_curve", ()):
                by_day[point.timestamp.date()] = float(point.equity_usdt)
            ordered = [by_day[key] for key in sorted(by_day)]
            for previous, current in pairwise(ordered):
                if previous > 0.0:
                    daily_returns.append(current / previous - 1.0)
        if len(daily_returns) < 2:
            return None
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((value - mean) ** 2 for value in daily_returns) / (
            len(daily_returns) - 1
        )
        if variance == 0.0:
            return None
        value = mean / (variance**0.5) * (365**0.5)
        return value if isfinite(value) else None

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
        value = mean / (downside_variance**0.5) * (len(pnl) ** 0.5)
        return value if isfinite(value) else None

    @staticmethod
    def _average_r(trades: tuple[TradeRecord, ...]) -> float | None:
        if not trades:
            return None
        return sum(float(trade.realized_r_multiple) for trade in trades) / len(trades)

    @staticmethod
    def _median_r(trades: tuple[TradeRecord, ...]) -> float | None:
        values = sorted(float(trade.realized_r_multiple) for trade in trades)
        if not values:
            return None
        midpoint = len(values) // 2
        if len(values) % 2:
            return values[midpoint]
        return (values[midpoint - 1] + values[midpoint]) / 2.0

    @staticmethod
    def _win_rate(trades: tuple[TradeRecord, ...]) -> float | None:
        if not trades:
            return None
        return sum(trade.net_pnl_usdt > 0 for trade in trades) / len(trades)

    @staticmethod
    def _payoff_ratio(trades: tuple[TradeRecord, ...]) -> float | None:
        wins = [float(trade.net_pnl_usdt) for trade in trades if trade.net_pnl_usdt > 0]
        losses = [
            abs(float(trade.net_pnl_usdt)) for trade in trades if trade.net_pnl_usdt < 0
        ]
        if not wins or not losses:
            return None
        return (sum(wins) / len(wins)) / (sum(losses) / len(losses))

    @staticmethod
    def _cost_to_gross_profit_ratio(trades: tuple[TradeRecord, ...]) -> float | None:
        gross_profit = sum(max(float(trade.gross_pnl_usdt), 0.0) for trade in trades)
        if gross_profit <= 0.0:
            return None
        costs = sum(
            float(
                trade.fee_cost_usdt + trade.slippage_cost_usdt + trade.funding_cost_usdt
            )
            for trade in trades
        )
        return costs / gross_profit

    @classmethod
    def _strategy_regime_profit_factor(
        cls, trades: tuple[TradeRecord, ...]
    ) -> float | None:
        values = [
            item.profit_factor
            for item in cls._strategy_regime_attribution(trades)
            if item.profit_factor is not None
        ]
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _profitable_walk_forward_window_ratio(
        walk_forward_reports: tuple[WalkForwardReport, ...],
        tuning_reports: tuple[TuningReport, ...],
    ) -> float | None:
        folds = ControlledLearningEngine._all_folds(
            walk_forward_reports, tuning_reports
        )
        if not folds:
            return None
        profitable = sum(
            getattr(
                getattr(getattr(fold, "oos_result", None), "metrics", None),
                "net_return",
                0.0,
            )
            > 0.0
            for fold in folds
        )
        return float(profitable / len(folds))

    @staticmethod
    def _candidate_to_execution_conversion(
        backtests: tuple[BacktestResult, ...],
    ) -> float | None:
        discovered = 0
        filled = 0
        for result in backtests:
            counts = dict(
                getattr(getattr(result, "funnel_telemetry", None), "stage_counts", ())
            )
            discovered += counts.get("DISCOVERED", 0)
            filled += counts.get("FILLED", 0)
        if discovered < 1:
            return None
        return filled / discovered

    @classmethod
    def _blocker_opportunity_cost(
        cls, backtests: tuple[BacktestResult, ...]
    ) -> float | None:
        trade_expectancy = cls._expectancy(
            tuple(
                trade for result in backtests for trade in getattr(result, "trades", ())
            )
        )
        if trade_expectancy is None or trade_expectancy <= 0.0:
            return None
        blocked = sum(
            len(getattr(result, "rejected_signals", ())) for result in backtests
        )
        return blocked * trade_expectancy

    @classmethod
    def _strategy_regime_attribution(
        cls,
        trades: tuple[TradeRecord, ...],
    ) -> tuple[StrategyRegimeAttribution, ...]:
        grouped: dict[tuple[str, str, str], list[TradeRecord]] = {}
        for trade in trades:
            key = (
                trade.attribution.strategy_id,
                trade.attribution.strategy_version,
                trade.attribution.regime,
            )
            grouped.setdefault(key, []).append(trade)
        attributions: list[StrategyRegimeAttribution] = []
        for key in sorted(grouped):
            group = tuple(grouped[key])
            wins = [
                float(trade.net_pnl_usdt) for trade in group if trade.net_pnl_usdt > 0
            ]
            losses = [
                float(trade.net_pnl_usdt) for trade in group if trade.net_pnl_usdt < 0
            ]
            gross_loss = abs(sum(losses))
            payoff_ratio = None
            if wins and losses:
                payoff_ratio = (sum(wins) / len(wins)) / (gross_loss / len(losses))
            attributions.append(
                StrategyRegimeAttribution(
                    strategy_id=key[0],
                    strategy_version=key[1],
                    regime=key[2],
                    trade_count=len(group),
                    profit_factor=(sum(wins) / gross_loss)
                    if gross_loss > 0.0
                    else None,
                    net_expectancy_after_costs=cls._expectancy(group) or 0.0,
                    average_r=cls._average_r(group) or 0.0,
                    average_mfe_r=cls._average_excursion_r(group, favorable=True),
                    average_mae_r=cls._average_excursion_r(group, favorable=False),
                    win_rate=cls._win_rate(group) or 0.0,
                    payoff_ratio=payoff_ratio,
                )
            )
        return tuple(attributions)

    @classmethod
    def _failure_analyses(
        cls, trades: tuple[TradeRecord, ...]
    ) -> tuple[FailureAnalysis, ...]:
        grouped: dict[tuple[str, str, str], list[TradeRecord]] = {}
        for trade in trades:
            if trade.net_pnl_usdt >= 0:
                continue
            classification = cls._classify_failure(trade)
            if classification is None:
                continue
            key = (
                classification,
                trade.attribution.strategy_id,
                trade.attribution.regime,
            )
            grouped.setdefault(key, []).append(trade)
        analyses: list[FailureAnalysis] = []
        for key in sorted(grouped):
            group = tuple(grouped[key])
            rationale = cls._failure_rationale(key[0], key[1], key[2], len(group))
            analyses.append(
                FailureAnalysis(
                    analysis_id=(
                        f"failure:{key[0].lower()}:{key[1].lower()}:{key[2].lower()}"
                    ),
                    classification=key[0],
                    strategy_id=key[1],
                    regime=key[2],
                    sample_size=len(group),
                    average_mfe_r=cls._average_excursion_r(group, favorable=True),
                    average_mae_r=cls._average_excursion_r(group, favorable=False),
                    rationale=rationale,
                    improvement_candidate_id=(
                        f"{key[1].lower()}:{key[2].lower()}:{key[0].lower()}"
                    ),
                )
            )
        return tuple(analyses)

    @staticmethod
    def _experiment_candidates(
        attribution: tuple[StrategyRegimeAttribution, ...],
    ) -> tuple[ExperimentCandidate, ...]:
        grouped: dict[tuple[str, str], list[StrategyRegimeAttribution]] = {}
        for item in attribution:
            grouped.setdefault((item.strategy_id, item.strategy_version), []).append(
                item
            )

        candidates: list[ExperimentCandidate] = []
        for key in sorted(grouped):
            items = tuple(grouped[key])
            positive = tuple(
                item for item in items if item.trade_count > 0 and item.average_r > 0.0
            )
            negative = tuple(
                item for item in items if item.trade_count > 0 and item.average_r < 0.0
            )
            if not positive or not negative:
                continue

            reference = max(
                positive,
                key=lambda item: (item.average_r, item.trade_count, item.regime),
            )
            for underperforming in sorted(negative, key=lambda item: item.regime):
                strategy_id = key[0]
                regime = underperforming.regime
                candidates.append(
                    ExperimentCandidate(
                        candidate_id=(
                            "experiment_candidate:"
                            f"{strategy_id.lower()}:"
                            f"{key[1].lower()}:"
                            f"{regime.lower()}:disable"
                        ),
                        strategy_id=strategy_id,
                        strategy_version=key[1],
                        regime=regime,
                        sample_size=underperforming.trade_count,
                        baseline_expectancy_r=underperforming.average_r,
                        reference_regime=reference.regime,
                        reference_expectancy_r=reference.average_r,
                        hypothesis=(
                            f"{strategy_id} underperforms in {regime} versus "
                            f"{reference.regime}; test regime-gated disablement."
                        ),
                        recommendation=(
                            f"Disable {strategy_id} in {regime} until replay, "
                            "walk-forward and OOS evidence improve expectancy."
                        ),
                    )
                )
        return tuple(candidates)

    @classmethod
    def _classify_failure(cls, trade: TradeRecord) -> str | None:
        mfe_r = cls._excursion_r(trade, favorable=True)
        mae_r = cls._excursion_r(trade, favorable=False)
        if mfe_r >= 2.0 and float(trade.realized_r_multiple) <= -0.75:
            return "EXIT_MANAGEMENT_GIVEBACK"
        if mae_r >= 0.9 and mfe_r <= 0.25:
            return "ENTRY_FILTER_WEAK"
        return None

    @staticmethod
    def _failure_rationale(
        classification: str,
        strategy_id: str,
        regime: str,
        sample_size: int,
    ) -> str:
        if classification == "EXIT_MANAGEMENT_GIVEBACK":
            return (
                f"Review exit management for {strategy_id} in {regime}; "
                f"{sample_size} losing trades reached strong MFE "
                "before closing negative."
            )
        return (
            f"Review entry and filter quality for {strategy_id} in {regime}; "
            f"{sample_size} losing trades moved to MAE before showing meaningful MFE."
        )

    @classmethod
    def _average_excursion_r(
        cls,
        trades: tuple[TradeRecord, ...],
        *,
        favorable: bool,
    ) -> float:
        if not trades:
            return 0.0
        values = [cls._excursion_r(trade, favorable=favorable) for trade in trades]
        return sum(values) / len(values)

    @staticmethod
    def _excursion_r(trade: TradeRecord, *, favorable: bool) -> float:
        realized_r = float(trade.realized_r_multiple)
        net_pnl = float(trade.net_pnl_usdt)
        if realized_r == 0.0 or net_pnl == 0.0:
            return 0.0
        initial_risk = abs(net_pnl / realized_r)
        if initial_risk == 0.0:
            return 0.0
        excursion = (
            float(trade.maximum_favorable_excursion)
            if favorable
            else float(trade.maximum_adverse_excursion)
        )
        return excursion / initial_risk


def _performance_candidate_code(affected_component: str) -> str:
    normalized = "".join(
        char if char.isalnum() else "_" for char in affected_component.strip().upper()
    ).strip("_")
    return f"PERFORMANCE_IMPROVEMENT_{normalized or 'UNKNOWN'}"


def _performance_root_cause_code(root_cause_tag: str) -> str:
    normalized = "".join(
        char if char.isalnum() else "_" for char in root_cause_tag.strip().upper()
    ).strip("_")
    return f"ROOT_CAUSE_{normalized or 'UNKNOWN'}"

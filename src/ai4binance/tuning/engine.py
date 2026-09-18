"""Deterministic bounded search backed by walk-forward OOS evidence."""

from dataclasses import dataclass, field
from hashlib import sha256
from itertools import product

from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle
from ai4binance.tuning.models import (
    CandidateEvaluation,
    SearchSpace,
    SensitivityAssessment,
    TuningConfig,
    TuningReport,
)
from ai4binance.validation.models import ParameterSet
from ai4binance.validation.walk_forward import (
    RegimeClassifier,
    StrategyFactory,
    WalkForwardValidator,
)


@dataclass(frozen=True, slots=True)
class TuningEngine:
    """Evaluate a finite whitelist and reject isolated optima."""

    validator: WalkForwardValidator = field(default_factory=WalkForwardValidator)

    def tune(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        search_space: SearchSpace,
        strategy_factory: StrategyFactory,
        regime_classifier: RegimeClassifier,
        config: TuningConfig,
    ) -> TuningReport:
        candidates = self._expand(search_space)
        evaluations = tuple(
            self._evaluate(
                candidate,
                symbol,
                timeframe,
                candles,
                strategy_factory,
                regime_classifier,
                config,
                len(candidates),
            )
            for candidate in candidates
        )
        selected = max(
            evaluations,
            key=lambda item: (
                self._plateau_objective(item, evaluations),
                item.objective,
                item.parameters.name,
            ),
        )
        sensitivity = self._sensitivity(selected, evaluations, config)
        blockers = list(selected.walk_forward_report.blockers)
        blockers.extend(sensitivity.blockers)
        unique_blockers = tuple(dict.fromkeys(blockers))
        return TuningReport(
            report_id=self._report_id(symbol, timeframe, selected, search_space),
            symbol=symbol.strip().upper(),
            timeframe=timeframe,
            created_at=selected.walk_forward_report.created_at,
            search_space=search_space,
            config=config,
            evaluations=evaluations,
            selected_parameters=selected.parameters,
            sensitivity=sensitivity,
            promotion_status=(
                ValidationStatus.STAGED_CANDIDATE
                if not unique_blockers
                else ValidationStatus.RESEARCH_ONLY
            ),
            blockers=unique_blockers,
        )

    def _evaluate(
        self,
        parameters: ParameterSet,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        strategy_factory: StrategyFactory,
        regime_classifier: RegimeClassifier,
        config: TuningConfig,
        hypothesis_count: int,
    ) -> CandidateEvaluation:
        report = self.validator.validate(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            parameters=(parameters,),
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=config.walk_forward,
            hypothesis_count=hypothesis_count,
        )
        blocker_penalty = 0.05 * len(report.blockers)
        objective = (
            report.robustness.oos_net_return
            - report.robustness.worst_fold_drawdown
            - blocker_penalty
        )
        return CandidateEvaluation(parameters, objective, report)

    @classmethod
    def _plateau_objective(
        cls,
        candidate: CandidateEvaluation,
        evaluations: tuple[CandidateEvaluation, ...],
    ) -> float:
        """Prefer broad local performance over an isolated best point."""
        neighborhood = tuple(
            item.objective
            for item in evaluations
            if cls._distance(item.parameters, candidate.parameters) <= 1
        )
        return sum(neighborhood) / len(neighborhood)

    @staticmethod
    def _expand(search_space: SearchSpace) -> tuple[ParameterSet, ...]:
        names = tuple(domain.name for domain in search_space.domains)
        value_sets = tuple(domain.values for domain in search_space.domains)
        candidates = tuple(
            ParameterSet(
                name="|".join(
                    f"{name}={value:g}"
                    for name, value in zip(names, values, strict=True)
                ),
                values=tuple(zip(names, values, strict=True)),
            )
            for values in product(*value_sets)
            if TuningEngine._valid_relationships(dict(zip(names, values, strict=True)))
        )
        if not candidates:
            raise ValueError("search space contains no governance-valid candidates")
        return candidates

    @staticmethod
    def _valid_relationships(values: dict[str, float]) -> bool:
        ema_valid = (
            "ema_fast" not in values
            or "ema_slow" not in values
            or (values["ema_fast"] < values["ema_slow"])
        )
        macd_valid = (
            "macd_fast" not in values
            or "macd_slow" not in values
            or (values["macd_fast"] < values["macd_slow"])
        )
        return ema_valid and macd_valid

    @staticmethod
    def _sensitivity(
        selected: CandidateEvaluation,
        evaluations: tuple[CandidateEvaluation, ...],
        config: TuningConfig,
    ) -> SensitivityAssessment:
        neighbors = tuple(
            item
            for item in evaluations
            if item is not selected
            and TuningEngine._distance(item.parameters, selected.parameters) == 1
        )
        selected_return = selected.walk_forward_report.robustness.oos_net_return
        required_return = selected_return * config.min_neighbor_return_ratio
        passing = tuple(
            item
            for item in neighbors
            if item.walk_forward_report.promotion_status
            is ValidationStatus.STAGED_CANDIDATE
            and item.walk_forward_report.robustness.oos_net_return >= required_return
        )
        pass_ratio = len(passing) / len(neighbors) if neighbors else 0.0
        blockers: list[str] = []
        if len(neighbors) < config.min_neighbor_count:
            blockers.append("INSUFFICIENT_SENSITIVITY_NEIGHBORS")
        if pass_ratio < config.min_neighbor_pass_ratio:
            blockers.append("UNSTABLE_PARAMETER_SENSITIVITY")
        return SensitivityAssessment(
            neighbor_count=len(neighbors),
            passing_neighbor_count=len(passing),
            pass_ratio=pass_ratio,
            minimum_return_ratio=config.min_neighbor_return_ratio,
            blockers=tuple(blockers),
        )

    @staticmethod
    def _distance(left: ParameterSet, right: ParameterSet) -> int:
        left_values = dict(left.values)
        right_values = dict(right.values)
        if set(left_values) != set(right_values):
            return max(len(left_values), len(right_values))
        return sum(left_values[name] != right_values[name] for name in left_values)

    @staticmethod
    def _report_id(
        symbol: str,
        timeframe: str,
        selected: CandidateEvaluation,
        search_space: SearchSpace,
    ) -> str:
        payload = (
            f"{symbol.strip().upper()}|{timeframe}|{selected.parameters.name}|"
            f"{search_space.candidate_count}|{selected.walk_forward_report.report_id}"
        )
        return f"tune:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"

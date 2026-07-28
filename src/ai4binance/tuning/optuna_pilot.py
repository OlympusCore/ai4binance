"""Optional isolated Optuna benchmark against exhaustive governed search."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from itertools import product
from math import isfinite
from typing import Protocol, cast

from ai4binance.tuning.models import SearchSpace

Objective = Callable[[Mapping[str, float]], float]
OptimizerRunner = Callable[
    [tuple[tuple[str, tuple[float, ...]], ...], Objective, int, int],
    tuple[dict[str, float], float, int],
]


class _Trial(Protocol):
    def suggest_categorical(self, name: str, choices: Sequence[float]) -> float: ...


class _Study(Protocol):
    best_params: Mapping[str, object]
    best_value: float

    def optimize(
        self, objective: Callable[[_Trial], float], *, n_trials: int
    ) -> None: ...


class _Samplers(Protocol):
    def TPESampler(self, *, seed: int) -> object: ...  # noqa: N802


class _OptunaModule(Protocol):
    samplers: _Samplers

    def create_study(self, *, direction: str, sampler: object) -> _Study: ...


@dataclass(frozen=True, slots=True)
class OptunaBenchmarkReport:
    baseline_evaluations: int
    pilot_evaluations: int
    baseline_best_score: float
    pilot_best_score: float | None
    score_gap: float | None
    baseline_best_parameters: tuple[tuple[str, float], ...]
    pilot_best_parameters: tuple[tuple[str, float], ...]
    backend_available: bool
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("Optuna pilot cannot grant promotion or execution")


@dataclass(frozen=True, slots=True)
class OptunaBenchmarkPilot:
    seed: int = 42
    trial_budget: int = 32
    maximum_score_gap: float = 1e-9
    optimizer_runner: OptimizerRunner | None = None

    def __post_init__(self) -> None:
        if not 2 <= self.trial_budget <= 4096:
            raise ValueError("Optuna pilot budget must be between 2 and 4096")
        if not isfinite(self.maximum_score_gap) or self.maximum_score_gap < 0.0:
            raise ValueError("Optuna pilot score gap must be finite and non-negative")

    def benchmark(
        self,
        *,
        search_space: SearchSpace,
        objective: Objective,
    ) -> OptunaBenchmarkReport:
        domains = tuple((item.name, item.values) for item in search_space.domains)
        baseline_params, baseline_score, baseline_count = _exhaustive(
            domains, objective
        )
        runner = self.optimizer_runner or _run_optuna
        try:
            pilot_params, pilot_score, pilot_count = runner(
                domains,
                objective,
                min(self.trial_budget, search_space.candidate_count),
                self.seed,
            )
        except ModuleNotFoundError:
            return OptunaBenchmarkReport(
                baseline_count,
                0,
                baseline_score,
                None,
                None,
                tuple(sorted(baseline_params.items())),
                (),
                False,
                ("OPTUNA_OPTIONAL_DEPENDENCY_UNAVAILABLE",),
            )
        gap = baseline_score - pilot_score
        blockers: list[str] = []
        if gap > self.maximum_score_gap:
            blockers.append("OPTUNA_BENCHMARK_SCORE_GAP_EXCESSIVE")
        if pilot_count >= baseline_count:
            blockers.append("OPTUNA_BENCHMARK_NO_EVALUATION_REDUCTION")
        return OptunaBenchmarkReport(
            baseline_count,
            pilot_count,
            baseline_score,
            pilot_score,
            gap,
            tuple(sorted(baseline_params.items())),
            tuple(sorted(pilot_params.items())),
            True,
            tuple(blockers),
        )


def _exhaustive(
    domains: tuple[tuple[str, tuple[float, ...]], ...],
    objective: Objective,
) -> tuple[dict[str, float], float, int]:
    names = tuple(item[0] for item in domains)
    candidates = tuple(product(*(item[1] for item in domains)))
    scored = tuple(
        (
            dict(zip(names, values, strict=True)),
            objective(dict(zip(names, values, strict=True))),
        )
        for values in candidates
    )
    params, score = max(scored, key=lambda item: (item[1], tuple(item[0].values())))
    if not isfinite(score):
        raise ValueError("benchmark objective must return finite scores")
    return params, score, len(scored)


def _run_optuna(
    domains: tuple[tuple[str, tuple[float, ...]], ...],
    objective: Objective,
    budget: int,
    seed: int,
) -> tuple[dict[str, float], float, int]:
    module = cast(_OptunaModule, import_module("optuna"))
    sampler = module.samplers.TPESampler(seed=seed)
    study = module.create_study(direction="maximize", sampler=sampler)

    def trial_objective(trial: _Trial) -> float:
        parameters = {
            name: trial.suggest_categorical(name, values) for name, values in domains
        }
        score = objective(parameters)
        if not isfinite(score):
            raise ValueError("benchmark objective must return finite scores")
        return score

    study.optimize(trial_objective, n_trials=budget)
    parameters: dict[str, float] = {}
    for name, value in study.best_params.items():
        if not isinstance(value, (int, float)):
            raise ValueError("Optuna benchmark returned a non-numeric parameter")
        parameters[name] = float(value)
    return parameters, study.best_value, budget

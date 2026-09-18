from collections.abc import Callable, Mapping
from typing import Never

import pytest

from ai4binance.tuning.models import ParameterDomain, SearchSpace
from ai4binance.tuning.optuna_pilot import Objective, OptunaBenchmarkPilot


def _space() -> SearchSpace:
    return SearchSpace(
        (
            ParameterDomain("ema_fast", (5.0, 8.0, 13.0)),
            ParameterDomain("ema_slow", (21.0, 34.0, 55.0)),
        )
    )


def test_optuna_pilot_accepts_isolated_runner_but_never_promotes() -> None:
    def runner(
        domains: tuple[tuple[str, tuple[float, ...]], ...],
        objective: Objective,
        budget: int,
        seed: int,
    ) -> tuple[dict[str, float], float, int]:
        del domains, budget, seed
        parameters = {"ema_fast": 8.0, "ema_slow": 34.0}
        return parameters, objective(parameters), 4

    def objective(parameters: Mapping[str, float]) -> float:
        return -abs(parameters["ema_fast"] - 8.0) - abs(parameters["ema_slow"] - 34.0)

    report = OptunaBenchmarkPilot(optimizer_runner=runner).benchmark(
        search_space=_space(), objective=objective
    )

    assert report.backend_available is True
    assert report.score_gap == 0.0
    assert report.blockers == ()
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.execution_allowed is False


def test_optuna_pilot_fails_closed_when_dependency_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.tuning.optuna_pilot as module

    def missing(
        domains: tuple[tuple[str, tuple[float, ...]], ...],
        objective: Objective,
        budget: int,
        seed: int,
    ) -> Never:
        del domains, objective, budget, seed
        raise ModuleNotFoundError("optuna")

    monkeypatch.setattr(module, "_run_optuna", missing)
    report = OptunaBenchmarkPilot().benchmark(
        search_space=_space(), objective=lambda params: params["ema_fast"]
    )

    assert report.backend_available is False
    assert report.blockers == ("OPTUNA_OPTIONAL_DEPENDENCY_UNAVAILABLE",)


def test_optuna_adapter_runs_against_isolated_fake_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.tuning.optuna_pilot as module

    class FakeTrial:
        def suggest_categorical(self, name: str, choices: tuple[float, ...]) -> float:
            del name
            return choices[0]

    class FakeStudy:
        def __init__(self) -> None:
            self.best_params: dict[str, object] = {}
            self.best_value = 0.0

        def optimize(
            self,
            objective: Callable[[FakeTrial], float],
            *,
            n_trials: int,
        ) -> None:
            self.best_params = {"ema_fast": 5.0, "ema_slow": 21.0}
            self.best_value = objective(FakeTrial())
            assert n_trials == 2

    class FakeSamplers:
        @staticmethod
        def TPESampler(*, seed: int) -> object:  # noqa: N802
            return {"seed": seed}

    class FakeOptuna:
        samplers = FakeSamplers()

        @staticmethod
        def create_study(*, direction: str, sampler: object) -> FakeStudy:
            assert direction == "maximize"
            assert sampler == {"seed": 3}
            return FakeStudy()

    monkeypatch.setattr(module, "import_module", lambda name: FakeOptuna())
    parameters, score, count = module._run_optuna(
        (("ema_fast", (5.0, 8.0)), ("ema_slow", (21.0, 34.0))),
        lambda values: values["ema_fast"] + values["ema_slow"],
        2,
        3,
    )

    assert parameters == {"ema_fast": 5.0, "ema_slow": 21.0}
    assert score == 26.0
    assert count == 2


def test_optuna_pilot_reports_gap_and_no_reduction() -> None:
    def weak_runner(
        domains: tuple[tuple[str, tuple[float, ...]], ...],
        objective: Objective,
        budget: int,
        seed: int,
    ) -> tuple[dict[str, float], float, int]:
        del domains, budget, seed
        parameters = {"ema_fast": 5.0, "ema_slow": 21.0}
        return parameters, objective(parameters), 9

    report = OptunaBenchmarkPilot(
        optimizer_runner=weak_runner,
        maximum_score_gap=0.0,
    ).benchmark(
        search_space=_space(),
        objective=lambda values: values["ema_fast"] + values["ema_slow"],
    )

    assert report.blockers == (
        "OPTUNA_BENCHMARK_SCORE_GAP_EXCESSIVE",
        "OPTUNA_BENCHMARK_NO_EVALUATION_REDUCTION",
    )

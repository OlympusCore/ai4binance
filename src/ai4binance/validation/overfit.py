"""Transparent strategy-selection overfit and Deflated Sharpe diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from math import e, isfinite, sqrt
from statistics import NormalDist, mean, stdev

_EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True, slots=True)
class DeflatedSharpeAssessment:
    """Multiplicity-adjusted Sharpe evidence; never a live approval."""

    sample_size: int
    hypothesis_count: int
    observed_sharpe: float
    expected_max_sharpe: float
    deflated_sharpe_probability: float
    minimum_probability: float
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        numeric = (
            self.observed_sharpe,
            self.expected_max_sharpe,
            self.deflated_sharpe_probability,
            self.minimum_probability,
        )
        if self.sample_size < 3 or self.hypothesis_count < 1:
            raise ValueError("Deflated Sharpe sample and hypotheses are invalid")
        if any(not isfinite(value) for value in numeric):
            raise ValueError("Deflated Sharpe values must be finite")
        if not 0.0 <= self.deflated_sharpe_probability <= 1.0:
            raise ValueError("Deflated Sharpe probability must be bounded")
        if not 0.5 < self.minimum_probability < 1.0:
            raise ValueError("minimum Deflated Sharpe probability is invalid")
        if self.execution_allowed:
            raise ValueError("statistical evidence cannot authorize execution")


@dataclass(frozen=True, slots=True)
class SelectionOverfitAssessment:
    """Fraction of splits where train-selected candidate falls below OOS median."""

    split_count: int
    candidate_count: int
    overfit_probability: float
    maximum_probability: float
    selected_indices: tuple[int, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.split_count < 1 or self.candidate_count < 2:
            raise ValueError("selection-overfit dimensions are invalid")
        if not 0.0 <= self.overfit_probability <= 1.0:
            raise ValueError("selection-overfit probability must be bounded")
        if not 0.0 <= self.maximum_probability <= 1.0:
            raise ValueError("maximum overfit probability must be bounded")
        if self.execution_allowed:
            raise ValueError("overfit evidence cannot authorize execution")


def assess_deflated_sharpe(
    returns: tuple[float, ...],
    *,
    hypothesis_count: int,
    minimum_probability: float = 0.95,
) -> DeflatedSharpeAssessment:
    """Estimate DSR using observed skew/kurtosis and trial-count multiplicity."""
    if len(returns) < 3 or hypothesis_count < 1:
        raise ValueError("Deflated Sharpe requires three returns and hypotheses")
    if any(not isfinite(value) for value in returns):
        raise ValueError("Deflated Sharpe returns must be finite")
    if not 0.5 < minimum_probability < 1.0:
        raise ValueError("minimum Deflated Sharpe probability is invalid")
    volatility = stdev(returns)
    if volatility <= 0.0:
        probability = 1.0 if mean(returns) > 0.0 else 0.0
        blockers = (
            ()
            if probability >= minimum_probability
            else ("DEFLATED_SHARPE_INSUFFICIENT",)
        )
        return DeflatedSharpeAssessment(
            len(returns),
            hypothesis_count,
            0.0,
            0.0,
            probability,
            minimum_probability,
            blockers,
        )

    observed = mean(returns) / volatility
    centered = tuple((value - mean(returns)) / volatility for value in returns)
    skewness = sum(value**3 for value in centered) / len(centered)
    kurtosis = sum(value**4 for value in centered) / len(centered)
    sharpe_variance = max(
        1e-12,
        (1.0 - skewness * observed + ((kurtosis - 1.0) / 4.0) * observed**2)
        / (len(returns) - 1),
    )
    expected_max = _expected_maximum_sharpe(hypothesis_count, len(returns))
    test_statistic = (observed - expected_max) / sqrt(sharpe_variance)
    probability = NormalDist().cdf(test_statistic)
    blockers = (
        () if probability >= minimum_probability else ("DEFLATED_SHARPE_INSUFFICIENT",)
    )
    return DeflatedSharpeAssessment(
        sample_size=len(returns),
        hypothesis_count=hypothesis_count,
        observed_sharpe=observed,
        expected_max_sharpe=expected_max,
        deflated_sharpe_probability=probability,
        minimum_probability=minimum_probability,
        blockers=blockers,
    )


def assess_selection_overfit(
    training_scores: tuple[tuple[float, ...], ...],
    oos_scores: tuple[tuple[float, ...], ...],
    *,
    maximum_probability: float = 0.5,
) -> SelectionOverfitAssessment:
    """Calculate a deterministic PBO-style split selection diagnostic."""
    if not training_scores or len(training_scores) != len(oos_scores):
        raise ValueError("training and OOS score matrices must align")
    candidate_count = len(training_scores[0])
    if candidate_count < 2 or any(
        len(row) != candidate_count for row in training_scores + oos_scores
    ):
        raise ValueError("score matrices require consistent candidate dimensions")
    if any(
        not isfinite(value) for row in training_scores + oos_scores for value in row
    ):
        raise ValueError("selection-overfit scores must be finite")
    if not 0.0 <= maximum_probability <= 1.0:
        raise ValueError("maximum overfit probability must be bounded")

    selected = tuple(
        max(range(candidate_count), key=lambda index: (row[index], -index))
        for row in training_scores
    )
    below_median = 0
    for selected_index, row in zip(selected, oos_scores, strict=True):
        ordered = sorted(row)
        median = (
            ordered[(candidate_count - 1) // 2] + ordered[candidate_count // 2]
        ) / 2
        below_median += row[selected_index] < median
    probability = below_median / len(training_scores)
    blockers: list[str] = []
    if len(training_scores) < 4:
        blockers.append("INSUFFICIENT_SELECTION_SPLITS")
    if probability > maximum_probability:
        blockers.append("BACKTEST_SELECTION_OVERFIT_HIGH")
    return SelectionOverfitAssessment(
        split_count=len(training_scores),
        candidate_count=candidate_count,
        overfit_probability=probability,
        maximum_probability=maximum_probability,
        selected_indices=selected,
        blockers=tuple(blockers),
    )


def _expected_maximum_sharpe(hypothesis_count: int, sample_size: int) -> float:
    if hypothesis_count == 1:
        return 0.0
    normal = NormalDist()
    trial_variance = 1.0 / (sample_size - 1)
    first = normal.inv_cdf(1.0 - 1.0 / hypothesis_count)
    second = normal.inv_cdf(1.0 - 1.0 / (hypothesis_count * e))
    return sqrt(trial_variance) * ((1.0 - _EULER_GAMMA) * first + _EULER_GAMMA * second)

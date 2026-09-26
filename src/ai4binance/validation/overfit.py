"""Transparent strategy-selection overfit and Deflated Sharpe diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import e, isfinite, log, sqrt
from statistics import NormalDist, mean, stdev

_EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True, slots=True)
class FrozenIsotonicCalibration:
    """Train-only PAVA calibration with immutable cohort and dataset identities."""

    model_id: str
    fitted_through: datetime
    dataset_sha256: str
    cohort_sha256: str
    upper_scores: tuple[float, ...]
    probabilities: tuple[float, ...]
    sample_size: int

    def __post_init__(self) -> None:
        if (
            not self.model_id.strip()
            or self.fitted_through.utcoffset() is None
            or self.sample_size < 2
            or not self.upper_scores
            or len(self.upper_scores) != len(self.probabilities)
            or tuple(sorted(set(self.upper_scores))) != self.upper_scores
            or tuple(sorted(self.probabilities)) != self.probabilities
            or any(
                not isfinite(v) or not 0 <= v <= 1
                for v in (*self.upper_scores, *self.probabilities)
            )
            or any(
                len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
                for h in (self.dataset_sha256, self.cohort_sha256)
            )
        ):
            raise ValueError("frozen calibration parameters or lineage are invalid")

    def predict(self, score: float, *, predicted_at: datetime) -> float:
        if predicted_at.utcoffset() is None or predicted_at <= self.fitted_through:
            raise ValueError("calibration cannot predict inside its training interval")
        if not isfinite(score) or not 0 <= score <= 1:
            raise ValueError("calibration score must be finite and bounded")
        for upper, probability in zip(
            self.upper_scores, self.probabilities, strict=True
        ):
            if score <= upper:
                return probability
        return self.probabilities[-1]


def fit_oos_calibration(
    observations: tuple[OosProbabilityObservation, ...],
    *,
    dataset_sha256: str,
    fitted_through: datetime,
    minimum_observations: int,
) -> FrozenIsotonicCalibration:
    """Fit monotone probabilities only on fully resolved pre-holdout labels.

    Inputs are frozen base-model forecasts, not in-sample fitted predictions.
    Their original probabilities act as raw scores; calibration quality is
    measured exclusively on a later, purged cohort.
    """
    diagnostics = assess_oos_probabilities(
        observations, minimum_observations=minimum_observations
    )
    if diagnostics.blockers or len({o.target_first for o in observations}) < 2:
        raise ValueError("calibration requires sufficient observations of both classes")
    if (
        fitted_through.utcoffset() is None
        or any(o.horizon_end > fitted_through for o in observations)
        or len(dataset_sha256) != 64
        or any(c not in "0123456789abcdef" for c in dataset_sha256)
    ):
        raise ValueError(
            "calibration requires closed horizons and exact dataset lineage"
        )
    # Equal scores are one block. Adjacent violations are pooled until monotone.
    grouped: dict[float, list[int]] = {}
    for observation in observations:
        grouped.setdefault(observation.probability, []).append(
            int(observation.target_first)
        )
    blocks: list[tuple[float, int, int]] = []
    for score, outcomes in sorted(grouped.items()):
        blocks.append((score, sum(outcomes), len(outcomes)))
        while (
            len(blocks) > 1
            and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]
        ):
            right = blocks.pop()
            left = blocks.pop()
            blocks.append((right[0], left[1] + right[1], left[2] + right[2]))
    cohort = [
        (
            o.observation_id,
            o.model_id,
            o.fold_id,
            o.regime,
            o.trained_through.isoformat(),
            o.predicted_at.isoformat(),
            o.resolved_at.isoformat(),
            o.horizon_end.isoformat(),
            o.probability,
            o.target_first,
            o.net_r,
        )
        for o in sorted(observations, key=lambda row: row.observation_id)
    ]
    digest = hashlib.sha256(
        json.dumps(cohort, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return FrozenIsotonicCalibration(
        observations[0].model_id,
        fitted_through,
        dataset_sha256,
        digest,
        tuple(b[0] for b in blocks),
        tuple(b[1] / b[2] for b in blocks),
        len(observations),
    )


def calibrated_holdout(
    calibration: FrozenIsotonicCalibration,
    observations: tuple[OosProbabilityObservation, ...],
    *,
    embargo: timedelta,
    minimum_observations: int,
) -> tuple[tuple[OosProbabilityObservation, ...], ProbabilityDiagnostics]:
    """Apply a frozen mapping to strictly later forecasts without fitting labels."""
    if embargo <= timedelta(0):
        raise ValueError("calibrated holdout requires a positive embargo")
    if not observations or any(
        o.model_id != calibration.model_id
        or o.trained_through > calibration.fitted_through
        or o.predicted_at <= calibration.fitted_through + embargo
        for o in observations
    ):
        raise ValueError("calibrated holdout violates model binding, purge, or embargo")
    transformed = tuple(
        replace(
            o,
            probability=calibration.predict(o.probability, predicted_at=o.predicted_at),
        )
        for o in observations
    )
    return transformed, assess_oos_probabilities(
        transformed, minimum_observations=minimum_observations
    )


@dataclass(frozen=True, slots=True)
class OosProbabilityObservation:
    """Frozen probability of TP-before-SL within one declared horizon.

    Unresolved or simultaneous-touch labels must be censored upstream. The
    observed timestamp is label resolution, not the feature candle timestamp.
    Confidence scores are not accepted as calibrated probabilities implicitly.
    """

    observation_id: str
    model_id: str
    fold_id: str
    regime: str
    trained_through: datetime
    predicted_at: datetime
    resolved_at: datetime
    horizon_end: datetime
    probability: float
    target_first: bool
    net_r: float

    def __post_init__(self) -> None:
        if any(
            not s.strip()
            for s in (self.observation_id, self.model_id, self.fold_id, self.regime)
        ):
            raise ValueError("OOS observation identity is required")
        stamps = (
            self.trained_through,
            self.predicted_at,
            self.resolved_at,
            self.horizon_end,
        )
        if any(t.utcoffset() is None for t in stamps):
            raise ValueError("OOS timestamps must be timezone-aware")
        if (
            not self.trained_through
            < self.predicted_at
            < self.resolved_at
            <= self.horizon_end
        ):
            raise ValueError("OOS observation contains temporal leakage or censoring")
        if (
            not isfinite(self.probability)
            or not 0 <= self.probability <= 1
            or not isfinite(self.net_r)
            or not isinstance(self.target_first, bool)
        ):
            raise ValueError("OOS probability, outcome, or return is invalid")


@dataclass(frozen=True, slots=True)
class ProbabilityDiagnostics:
    """Descriptive OOS metrics; no fit, promotion, or calibration authority."""

    sample_size: int
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    reliability_bins: tuple[tuple[int, float, float], ...]
    mean_net_r: float
    fold_count: int
    regime_counts: tuple[tuple[str, int], ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("OOS diagnostics cannot authorize execution")


def assess_oos_probabilities(
    observations: tuple[OosProbabilityObservation, ...],
    *,
    minimum_observations: int,
    bin_count: int = 10,
) -> ProbabilityDiagnostics:
    """Measure frozen held-out predictions without treating fit quality as approval."""
    if not observations or minimum_observations < 1 or not 2 <= bin_count <= 100:
        raise ValueError("OOS diagnostics require observations and explicit bounds")
    ids = tuple(o.observation_id for o in observations)
    if len(set(ids)) != len(ids) or len({o.model_id for o in observations}) != 1:
        raise ValueError("OOS diagnostics require unique observations from one model")
    n = len(observations)
    brier = mean((o.probability - int(o.target_first)) ** 2 for o in observations)
    # Clip only the logarithm at machine-report precision; Brier retains extremes.
    log_loss = -mean(
        log(max(1e-15, o.probability if o.target_first else 1 - o.probability))
        for o in observations
    )
    bins: list[tuple[int, float, float]] = []
    for index in range(bin_count):
        rows = tuple(
            o
            for o in observations
            if min(int(o.probability * bin_count), bin_count - 1) == index
        )
        bins.append(
            (
                len(rows),
                mean(o.probability for o in rows) if rows else 0.0,
                mean(int(o.target_first) for o in rows) if rows else 0.0,
            )
        )
    ece = sum(count * abs(predicted - actual) for count, predicted, actual in bins) / n
    blockers = (
        ("OOS_PROBABILITY_SAMPLE_INSUFFICIENT",) if n < minimum_observations else ()
    )
    return ProbabilityDiagnostics(
        n,
        brier,
        log_loss,
        ece,
        tuple(bins),
        mean(o.net_r for o in observations),
        len({o.fold_id for o in observations}),
        tuple(
            (regime, sum(o.regime == regime for o in observations))
            for regime in sorted({o.regime for o in observations})
        ),
        blockers,
    )


def paired_ablation_delta(
    baseline: tuple[OosProbabilityObservation, ...],
    challenger: tuple[OosProbabilityObservation, ...],
) -> tuple[float, float, int]:
    """Return paired delta net-R and Brier on the exact same held-out cohort.

    This is descriptive: overlapping trades need block-aware uncertainty and
    the existing multiplicity/DSR gate before any superiority claim.
    """
    assess_oos_probabilities(baseline, minimum_observations=1)
    assess_oos_probabilities(challenger, minimum_observations=1)
    left = {o.observation_id: o for o in baseline}
    right = {o.observation_id: o for o in challenger}
    if left.keys() != right.keys():
        raise ValueError("ablation cohorts must match exactly")
    deltas = []
    for key, a in left.items():
        b = right[key]
        if (
            a.predicted_at,
            a.resolved_at,
            a.horizon_end,
            a.fold_id,
            a.regime,
            a.target_first,
        ) != (
            b.predicted_at,
            b.resolved_at,
            b.horizon_end,
            b.fold_id,
            b.regime,
            b.target_first,
        ):
            raise ValueError("ablation labels, folds, and horizons must match")
        y = int(a.target_first)
        deltas.append(
            (b.net_r - a.net_r, (b.probability - y) ** 2 - (a.probability - y) ** 2)
        )
    return mean(d[0] for d in deltas), mean(d[1] for d in deltas), len(deltas)


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

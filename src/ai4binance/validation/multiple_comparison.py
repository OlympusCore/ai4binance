"""Deterministic block-bootstrap SPA and model-confidence-set diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from random import Random


@dataclass(frozen=True, slots=True)
class CandidatePerformance:
    """One candidate's aligned net-return observations."""

    name: str
    returns: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.returns:
            raise ValueError("candidate identity and returns are required")
        if any(not isfinite(item) for item in self.returns):
            raise ValueError("candidate returns must be finite")


@dataclass(frozen=True, slots=True)
class MultipleComparisonReport:
    """Research-only multiple-testing assessment."""

    sample_size: int
    candidate_count: int
    bootstrap_samples: int
    block_length: int
    best_candidate: str
    observed_best_advantage: float
    spa_p_value: float
    model_confidence_set: tuple[str, ...]
    excluded_models: tuple[str, ...]
    blockers: tuple[str, ...]
    status: str
    promotion_allowed: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.spa_p_value <= 1:
            raise ValueError("SPA p-value is invalid")
        if self.status not in {"RESEARCH_ONLY", "STAGED_CANDIDATE"}:
            raise ValueError("multiple-comparison status is invalid")
        if self.promotion_allowed or self.execution_allowed:
            raise ValueError("multiple-comparison evidence cannot grant authority")


def assess_multiple_comparisons(
    *,
    benchmark_returns: tuple[float, ...],
    candidates: tuple[CandidatePerformance, ...],
    bootstrap_samples: int = 999,
    block_length: int = 8,
    alpha: float = 0.05,
    seed: int = 7,
) -> MultipleComparisonReport:
    """Run a conservative SPA test and paired-bootstrap confidence set."""
    sample_size = len(benchmark_returns)
    if sample_size < 20 or any(not isfinite(item) for item in benchmark_returns):
        raise ValueError("multiple comparison requires 20 finite benchmark returns")
    if not candidates or len({item.name for item in candidates}) != len(candidates):
        raise ValueError("multiple comparison candidates must be unique and non-empty")
    if any(len(item.returns) != sample_size for item in candidates):
        raise ValueError("candidate and benchmark returns must be aligned")
    if bootstrap_samples < 99 or not 1 <= block_length < sample_size:
        raise ValueError("bootstrap dimensions are invalid")
    if not 0 < alpha < 0.5:
        raise ValueError("multiple comparison alpha is invalid")

    differentials = tuple(
        tuple(
            value - benchmark
            for value, benchmark in zip(item.returns, benchmark_returns, strict=True)
        )
        for item in candidates
    )
    means = tuple(_mean(item) for item in differentials)
    best_index = max(range(len(candidates)), key=means.__getitem__)
    observed = sqrt(sample_size) * max(0.0, means[best_index])
    centered = tuple(
        tuple(value - means[index] for value in series)
        for index, series in enumerate(differentials)
    )
    # Reproducibility is required here; this generator is not used for security.
    random = Random(seed)  # noqa: S311  # nosec B311
    exceedances = 0
    indices_by_sample: list[tuple[int, ...]] = []
    for _sample in range(bootstrap_samples):
        indices = _block_indices(random, sample_size, block_length)
        indices_by_sample.append(indices)
        statistic = max(
            sqrt(sample_size) * _mean(tuple(series[index] for index in indices))
            for series in centered
        )
        exceedances += statistic >= observed
    spa_p_value = (exceedances + 1) / (bootstrap_samples + 1)

    best_series = differentials[best_index]
    confidence_set: list[str] = []
    excluded: list[str] = []
    for candidate, series, mean in zip(candidates, differentials, means, strict=True):
        observed_gap = sqrt(sample_size) * (means[best_index] - mean)
        paired = tuple(
            best - value for best, value in zip(best_series, series, strict=True)
        )
        paired_mean = _mean(paired)
        centered_gap = tuple(value - paired_mean for value in paired)
        gap_exceedances = sum(
            sqrt(sample_size) * _mean(tuple(centered_gap[index] for index in indices))
            >= observed_gap
            for indices in indices_by_sample
        )
        p_value = (gap_exceedances + 1) / (bootstrap_samples + 1)
        target = confidence_set if p_value >= alpha else excluded
        target.append(candidate.name)

    blockers: list[str] = []
    if means[best_index] <= 0:
        blockers.append("NO_CANDIDATE_BEATS_BENCHMARK")
    if spa_p_value > alpha:
        blockers.append("SPA_NOT_SIGNIFICANT")
    if len(confidence_set) != 1:
        blockers.append("MODEL_CONFIDENCE_SET_NOT_UNIQUE")
    return MultipleComparisonReport(
        sample_size=sample_size,
        candidate_count=len(candidates),
        bootstrap_samples=bootstrap_samples,
        block_length=block_length,
        best_candidate=candidates[best_index].name,
        observed_best_advantage=means[best_index],
        spa_p_value=spa_p_value,
        model_confidence_set=tuple(confidence_set),
        excluded_models=tuple(excluded),
        blockers=tuple(blockers),
        status="RESEARCH_ONLY" if blockers else "STAGED_CANDIDATE",
    )


def _block_indices(random: Random, size: int, block_length: int) -> tuple[int, ...]:
    indices: list[int] = []
    while len(indices) < size:
        # Deterministic resampling only; never used for secrets or authentication.
        start = random.randrange(size)  # nosec B311
        indices.extend((start + offset) % size for offset in range(block_length))
    return tuple(indices[:size])


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values)

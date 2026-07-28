"""Fail-closed statistical evidence assessment for OOS promotion decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, sqrt
from statistics import stdev


class MultipleTestingCorrection(StrEnum):
    """Supported transparent corrections for parameter-family searches."""

    NONE = "NONE"
    BONFERRONI = "BONFERRONI"


@dataclass(frozen=True, slots=True)
class StatisticalEvidenceAssessment:
    """Uncertainty and multiplicity evidence attached to walk-forward output."""

    effective_sample_size: int
    hypothesis_count: int
    confidence_level: float
    adjusted_alpha: float
    mean_oos_return: float
    confidence_interval: tuple[float, float] | None
    correction: MultipleTestingCorrection
    confirmatory: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.effective_sample_size < 0 or self.hypothesis_count < 1:
            raise ValueError("statistical sample and hypothesis counts are invalid")
        numeric = (self.confidence_level, self.adjusted_alpha, self.mean_oos_return)
        if any(not isfinite(value) for value in numeric):
            raise ValueError("statistical evidence values must be finite")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence level must be between zero and one")
        if not 0.0 < self.adjusted_alpha < 1.0:
            raise ValueError("adjusted alpha must be between zero and one")
        if self.confidence_interval is not None:
            lower, upper = self.confidence_interval
            if not isfinite(lower) or not isfinite(upper) or lower > upper:
                raise ValueError("confidence interval is invalid")


_Z_SCORES = {0.90: 1.644854, 0.95: 1.959964, 0.99: 2.575829}


def assess_statistical_evidence(
    returns: tuple[float, ...],
    *,
    hypothesis_count: int,
    min_effective_sample_size: int,
    minimum_return: float,
    confidence_level: float,
    correction: MultipleTestingCorrection,
    confirmatory: bool,
) -> StatisticalEvidenceAssessment:
    """Assess uncertainty without treating a searched best result as proof."""
    if hypothesis_count < 1 or min_effective_sample_size < 2:
        raise ValueError(
            "statistical thresholds require positive hypotheses and sample >= 2"
        )
    if confidence_level not in _Z_SCORES:
        raise ValueError("confidence level must be one of 0.90, 0.95 or 0.99")
    if not isfinite(minimum_return) or any(not isfinite(value) for value in returns):
        raise ValueError("statistical returns must be finite")

    raw_alpha = 1.0 - confidence_level
    adjusted_alpha = (
        raw_alpha / hypothesis_count
        if correction is MultipleTestingCorrection.BONFERRONI
        else raw_alpha
    )
    mean_return = sum(returns) / len(returns) if returns else 0.0
    interval: tuple[float, float] | None = None
    if len(returns) >= 2:
        margin = _Z_SCORES[confidence_level] * stdev(returns) / sqrt(len(returns))
        interval = (mean_return - margin, mean_return + margin)

    blockers: list[str] = []
    if len(returns) < min_effective_sample_size:
        blockers.append("INSUFFICIENT_EFFECTIVE_SAMPLE_SIZE")
    if hypothesis_count > 1 and correction is MultipleTestingCorrection.NONE:
        blockers.append("MULTIPLE_TESTING_CORRECTION_MISSING")
    if not confirmatory:
        blockers.append("EXPLORATORY_EVIDENCE_NOT_PROMOTABLE")
    if interval is None or interval[0] <= minimum_return:
        blockers.append("OOS_RETURN_CONFIDENCE_INTERVAL_INSUFFICIENT")

    return StatisticalEvidenceAssessment(
        effective_sample_size=len(returns),
        hypothesis_count=hypothesis_count,
        confidence_level=confidence_level,
        adjusted_alpha=adjusted_alpha,
        mean_oos_return=mean_return,
        confidence_interval=interval,
        correction=correction,
        confirmatory=confirmatory,
        blockers=tuple(blockers),
    )

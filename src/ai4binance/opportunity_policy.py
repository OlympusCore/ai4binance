"""Canonical opportunity grading policy.

This module is a contract helper for research-only opportunity visibility. It
does not grant execution, paper eligibility, or live trading authority.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class OpportunityGradePolicy:
    """Single source of truth for opportunity radar grade thresholds."""

    policy_version: str = "opportunity-grade-policy:v1"
    a_threshold: Decimal = Decimal("90")
    b_plus_threshold: Decimal = Decimal("80")
    b_threshold: Decimal = Decimal("70")
    b_minus_threshold: Decimal = Decimal("60")
    c_threshold: Decimal = Decimal("50")

    def __post_init__(self) -> None:
        thresholds = (
            self.a_threshold,
            self.b_plus_threshold,
            self.b_threshold,
            self.b_minus_threshold,
            self.c_threshold,
        )
        if not self.policy_version.strip():
            raise ValueError("opportunity grade policy version is required")
        if any(
            not threshold.is_finite() or threshold < ZERO or threshold > ONE_HUNDRED
            for threshold in thresholds
        ):
            raise ValueError("opportunity grade thresholds must be between 0 and 100")
        if thresholds != tuple(sorted(thresholds, reverse=True)):
            raise ValueError("opportunity grade thresholds must be descending")
        if len(set(thresholds)) != len(thresholds):
            raise ValueError("opportunity grade thresholds must be unique")

    def classify(self, score: Decimal) -> str:
        """Return the canonical grade for a bounded zero-to-100 score."""
        bounded = bounded_opportunity_score(score)
        if bounded >= self.a_threshold:
            return "A"
        if bounded >= self.b_plus_threshold:
            return "B+"
        if bounded >= self.b_threshold:
            return "B"
        if bounded >= self.b_minus_threshold:
            return "B-"
        if bounded >= self.c_threshold:
            return "C"
        return "D"

    def is_b_or_higher(self, grade: str) -> bool:
        return grade in {"A", "B+", "B"}

    def is_b_plus_or_higher(self, grade: str) -> bool:
        return grade in {"A", "B+"}


DEFAULT_OPPORTUNITY_GRADE_POLICY = OpportunityGradePolicy()


def bounded_opportunity_score(value: Decimal) -> Decimal:
    """Clamp non-executable opportunity scores to the canonical 0..100 range."""
    if not value.is_finite():
        return ZERO
    return max(ZERO, min(ONE_HUNDRED, value))


def classify_opportunity_grade(
    score: Decimal,
    *,
    policy: OpportunityGradePolicy = DEFAULT_OPPORTUNITY_GRADE_POLICY,
) -> str:
    """Classify an opportunity score through the canonical grade policy."""
    return policy.classify(score)


def count_opportunity_grades(
    scores: Iterable[Decimal],
    *,
    policy: OpportunityGradePolicy = DEFAULT_OPPORTUNITY_GRADE_POLICY,
) -> dict[str, int]:
    """Count canonical grade buckets for reporting funnels."""
    counts = {
        "a_or_better_count": 0,
        "b_plus_count": 0,
        "b_count": 0,
    }
    for score in scores:
        grade = policy.classify(score)
        if grade == "A":
            counts["a_or_better_count"] += 1
        elif grade == "B+":
            counts["b_plus_count"] += 1
        elif grade == "B":
            counts["b_count"] += 1
    return counts

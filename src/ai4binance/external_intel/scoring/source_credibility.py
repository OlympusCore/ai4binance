"""Simple deterministic source credibility score."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.external_intel.core.validation import require_unit_interval


@dataclass(frozen=True, slots=True)
class SourceCredibilityInput:
    identity_verification_score: float = 0.0
    domain_expertise_score: float = 0.0
    historical_accuracy_score: float = 0.0
    originality_score: float = 0.0
    evidence_quality_score: float = 0.0
    independent_confirmation_score: float = 0.0
    promotion_penalty: float = 0.0
    manipulation_association_penalty: float = 0.0

    def __post_init__(self) -> None:
        values = (
            ("identity_verification_score", self.identity_verification_score),
            ("domain_expertise_score", self.domain_expertise_score),
            ("historical_accuracy_score", self.historical_accuracy_score),
            ("originality_score", self.originality_score),
            ("evidence_quality_score", self.evidence_quality_score),
            ("independent_confirmation_score", self.independent_confirmation_score),
            ("promotion_penalty", self.promotion_penalty),
            ("manipulation_association_penalty", self.manipulation_association_penalty),
        )
        for name, value in values:
            require_unit_interval(name, value)


def score_source_credibility(item: SourceCredibilityInput) -> float:
    positive = (
        item.identity_verification_score
        + item.domain_expertise_score
        + item.historical_accuracy_score
        + item.originality_score
        + item.evidence_quality_score
        + item.independent_confirmation_score
    ) / 6
    penalty = (item.promotion_penalty + item.manipulation_association_penalty) / 2
    return max(0.0, min(1.0, positive * (1.0 - penalty)))

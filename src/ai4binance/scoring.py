"""Deterministic confluence scoring and setup-tier classification."""

from dataclasses import dataclass, fields
from math import fsum, isclose, isfinite
from typing import ClassVar

from ai4binance.domain import SetupTier, SignalSubScores


@dataclass(frozen=True, slots=True)
class ConfluenceWeights:
    """Materialized ParameterRegistry scoring weights normalized to 100 points."""

    weight_set_id: str = "parameter:score_weights:baseline-v1"
    trend_score: float = 14.0
    volatility_score: float = 8.0
    momentum_score: float = 7.0
    volume_score: float = 8.0
    price_action_score: float = 14.0
    structure_score: float = 16.0
    fib_score: float = 5.0
    pattern_score: float = 7.0
    cycle_score: float = 5.0
    mtf_score: float = 14.0
    sentiment_score: float = 2.0

    VERSION: ClassVar[str] = "baseline-v1"
    WEIGHT_SET_PREFIX: ClassVar[str] = "parameter:score_weights:"

    def __post_init__(self) -> None:
        """Require non-negative weights that total exactly 100 within tolerance."""
        if not self.weight_set_id.strip():
            raise ValueError("weight_set_id cannot be empty")
        if not self.weight_set_id.startswith(self.WEIGHT_SET_PREFIX):
            raise ValueError("weight_set_id must reference ParameterRegistry")
        values = tuple(
            getattr(self, item.name)
            for item in fields(self)
            if item.name != "weight_set_id"
        )
        if any(not isfinite(value) or value < 0.0 for value in values):
            raise ValueError("confluence weights must be finite and non-negative")
        if not isclose(fsum(values), 100.0, abs_tol=1e-9):
            raise ValueError("confluence weights must total 100")


DEFAULT_CONFLUENCE_WEIGHTS = ConfluenceWeights()
SCORE_COMPONENT_FIELDS: tuple[str, ...] = tuple(
    item for item in SignalSubScores.SCORE_FIELDS if item != "risk_penalty_score"
)


def calculate_final_signal_score(
    scores: SignalSubScores,
    *,
    weights: ConfluenceWeights = DEFAULT_CONFLUENCE_WEIGHTS,
    contradiction_penalty: float = 0.0,
    data_quality_penalty: float = 0.0,
    overfit_penalty: float = 0.0,
    weight_set_id: str | None = None,
    validated_score_fields: tuple[str, ...] | None = None,
) -> float:
    """Return a reproducible zero-to-100 score after explicit penalties."""
    expected_weight_set_id = weight_set_id or weights.weight_set_id
    if expected_weight_set_id != weights.weight_set_id:
        raise ValueError(
            "weight_set_id must match the supplied ParameterRegistry weights"
        )
    positive_fields = validated_score_fields or SCORE_COMPONENT_FIELDS
    if not positive_fields:
        raise ValueError("validated_score_fields cannot be empty")
    if len(set(positive_fields)) != len(positive_fields):
        raise ValueError("validated_score_fields must be unique")
    unknown_fields = tuple(
        field_name
        for field_name in positive_fields
        if field_name not in SCORE_COMPONENT_FIELDS
    )
    if unknown_fields:
        raise ValueError("validated_score_fields must be canonical positive scores")
    penalties = (
        scores.risk_penalty_score,
        contradiction_penalty,
        data_quality_penalty,
        overfit_penalty,
    )
    if any(not isfinite(value) or not 0.0 <= value <= 100.0 for value in penalties):
        raise ValueError("penalties must be finite and between 0 and 100")

    positive_score = fsum(
        getattr(scores, field_name) * getattr(weights, field_name) / 100.0
        for field_name in positive_fields
    )
    final_score = max(0.0, min(100.0, positive_score - fsum(penalties)))
    return round(final_score, 6)


def classify_setup_tier(final_signal_score: float) -> SetupTier:
    """Classify the documented score thresholds without execution authority."""
    if not isfinite(final_signal_score) or not 0.0 <= final_signal_score <= 100.0:
        raise ValueError("final_signal_score must be finite and between 0 and 100")
    if final_signal_score >= 85.0:
        return SetupTier.A_STAR
    if final_signal_score >= 78.0:
        return SetupTier.A
    if final_signal_score >= 76.0:
        return SetupTier.B_PLUS
    if final_signal_score >= 70.0:
        return SetupTier.B
    if final_signal_score >= 60.0:
        return SetupTier.C
    return SetupTier.NO_TRADE

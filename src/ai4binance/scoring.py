"""Deterministic confluence scoring and setup-tier classification."""

from dataclasses import dataclass, fields
from math import fsum, isclose, isfinite

from ai4binance.domain import SetupTier, SignalSubScores


@dataclass(frozen=True, slots=True)
class ConfluenceWeights:
    """Versioned baseline weights normalized to 100 points."""

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

    VERSION = "baseline-v1"

    def __post_init__(self) -> None:
        """Require non-negative weights that total exactly 100 within tolerance."""
        values = tuple(getattr(self, item.name) for item in fields(self))
        if any(not isfinite(value) or value < 0.0 for value in values):
            raise ValueError("confluence weights must be finite and non-negative")
        if not isclose(fsum(values), 100.0, abs_tol=1e-9):
            raise ValueError("confluence weights must total 100")


DEFAULT_CONFLUENCE_WEIGHTS = ConfluenceWeights()
SCORE_COMPONENT_FIELDS: tuple[str, ...] = tuple(
    item.name for item in fields(ConfluenceWeights)
)


def calculate_final_signal_score(
    scores: SignalSubScores,
    *,
    weights: ConfluenceWeights = DEFAULT_CONFLUENCE_WEIGHTS,
    contradiction_penalty: float = 0.0,
    data_quality_penalty: float = 0.0,
    overfit_penalty: float = 0.0,
) -> float:
    """Return a reproducible zero-to-100 score after explicit penalties."""
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
        for field_name in SCORE_COMPONENT_FIELDS
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
    if final_signal_score >= 70.0:
        return SetupTier.B
    if final_signal_score >= 60.0:
        return SetupTier.C
    return SetupTier.NO_TRADE

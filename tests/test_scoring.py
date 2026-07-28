"""Deterministic confluence scoring tests."""

import pytest

from ai4binance.domain import SetupTier, SignalSubScores
from ai4binance.scoring import (
    ConfluenceWeights,
    calculate_final_signal_score,
    classify_setup_tier,
)


def test_weighted_score_is_deterministic_and_penalized() -> None:
    scores = SignalSubScores(
        trend_score=80,
        volatility_score=80,
        momentum_score=80,
        volume_score=80,
        price_action_score=80,
        structure_score=80,
        fib_score=80,
        pattern_score=80,
        cycle_score=80,
        mtf_score=80,
        sentiment_score=80,
        risk_penalty_score=5,
    )
    assert calculate_final_signal_score(scores) == 75.0
    assert calculate_final_signal_score(scores) == 75.0


def test_score_is_clamped_at_zero() -> None:
    assert (
        calculate_final_signal_score(
            SignalSubScores(risk_penalty_score=100),
            contradiction_penalty=100,
        )
        == 0.0
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (85.0, SetupTier.A_STAR),
        (78.0, SetupTier.A),
        (70.0, SetupTier.B),
        (60.0, SetupTier.C),
        (59.999, SetupTier.NO_TRADE),
    ],
)
def test_setup_tier_boundaries(score: float, expected: SetupTier) -> None:
    assert classify_setup_tier(score) is expected


def test_weights_must_total_100() -> None:
    with pytest.raises(ValueError, match="must total 100"):
        ConfluenceWeights(trend_score=13.0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        ConfluenceWeights(trend_score=-1.0, structure_score=31.0)


def test_penalties_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="penalties"):
        calculate_final_signal_score(
            SignalSubScores(),
            data_quality_penalty=float("nan"),
        )


def test_tier_classifier_rejects_non_finite_score() -> None:
    with pytest.raises(ValueError, match="final_signal_score"):
        classify_setup_tier(float("inf"))

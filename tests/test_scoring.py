"""Deterministic confluence scoring tests."""

import pytest

from ai4binance.domain import SetupTier, SignalSubScores
from ai4binance.scoring import (
    SCORE_COMPONENT_FIELDS,
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
    assert (
        calculate_final_signal_score(
            scores,
            weight_set_id="parameter:score_weights:baseline-v1",
        )
        == 75.0
    )


def test_score_component_fields_are_canonical_positive_sub_scores() -> None:
    assert SCORE_COMPONENT_FIELDS == (
        "trend_score",
        "volatility_score",
        "momentum_score",
        "volume_score",
        "price_action_score",
        "structure_score",
        "fib_score",
        "pattern_score",
        "cycle_score",
        "mtf_score",
        "sentiment_score",
    )


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
        (76.0, SetupTier.B_PLUS),
        (70.0, SetupTier.B),
        (60.0, SetupTier.C),
        (59.999, SetupTier.NO_TRADE),
    ],
)
def test_setup_tier_boundaries(score: float, expected: SetupTier) -> None:
    assert classify_setup_tier(score) is expected


def test_weights_must_total_100() -> None:
    assert ConfluenceWeights().weight_set_id == "parameter:score_weights:baseline-v1"
    with pytest.raises(ValueError, match="must total 100"):
        ConfluenceWeights(trend_score=13.0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        ConfluenceWeights(trend_score=-1.0, structure_score=31.0)
    with pytest.raises(ValueError, match="weight_set_id"):
        ConfluenceWeights(weight_set_id="")
    with pytest.raises(ValueError, match="ParameterRegistry"):
        ConfluenceWeights(weight_set_id="baseline-v1")


def test_weight_set_id_must_match_supplied_parameter_registry_weights() -> None:
    with pytest.raises(ValueError, match="weight_set_id"):
        calculate_final_signal_score(
            SignalSubScores(trend_score=100),
            weight_set_id="parameter:score_weights:other-v1",
        )


def test_only_validated_positive_score_fields_contribute_before_risk_penalty() -> None:
    scores = SignalSubScores(
        trend_score=100,
        structure_score=100,
        sentiment_score=100,
        risk_penalty_score=10,
    )

    assert (
        calculate_final_signal_score(
            scores,
            validated_score_fields=("trend_score", "structure_score"),
        )
        == 20.0
    )
    with pytest.raises(ValueError, match="canonical positive"):
        calculate_final_signal_score(
            scores,
            validated_score_fields=("risk_penalty_score",),
        )
    with pytest.raises(ValueError, match="unique"):
        calculate_final_signal_score(
            scores,
            validated_score_fields=("trend_score", "trend_score"),
        )


def test_penalties_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="penalties"):
        calculate_final_signal_score(
            SignalSubScores(),
            data_quality_penalty=float("nan"),
        )


def test_tier_classifier_rejects_non_finite_score() -> None:
    with pytest.raises(ValueError, match="final_signal_score"):
        classify_setup_tier(float("inf"))

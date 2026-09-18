"""Supplementary multi-venue coverage and robust-normalization tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.whale_fusion.derivatives.cross_venue import (
    CrossVenueResearchEngine,
    VenueObservation,
    robust_mad_zscores,
)

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def observation(
    venue: str,
    *,
    return_bps: str,
    age: int = 0,
    liquidity: str = "0.3",
    reliability: str = "0.9",
    sequence_valid: bool = True,
) -> VenueObservation:
    return VenueObservation(
        venue,
        NOW - timedelta(seconds=age),
        Decimal("100"),
        Decimal(return_bps),
        Decimal("2"),
        Decimal(liquidity),
        Decimal(reliability),
        sequence_valid,
    )


def test_multi_venue_direction_is_deterministic_and_supplementary_only() -> None:
    result = CrossVenueResearchEngine().evaluate(
        (
            observation("binance", return_bps="20"),
            observation("coinbase", return_bps="10"),
            observation("kraken", return_bps="-5"),
            observation("bybit", return_bps="15"),
        ),
        NOW,
    )
    assert result.score == Decimal("0.1")
    assert result.coverage_ratio == Decimal("1")
    assert result.blockers == ()
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.execution_allowed is False


def test_stale_invalid_and_single_venue_dominance_fail_closed() -> None:
    result = CrossVenueResearchEngine().evaluate(
        (
            observation("binance", return_bps="20", liquidity="1", reliability="1"),
            observation("coinbase", return_bps="10", liquidity="0.01"),
            observation("kraken", return_bps="5", age=500),
            observation("bybit", return_bps="5", sequence_valid=False),
        ),
        NOW,
    )
    assert result.score is None
    assert result.blockers == (
        "VENUE_SEQUENCE_INVALID",
        "INSUFFICIENT_VALID_VENUES",
        "MULTI_VENUE_COVERAGE_BELOW_POLICY",
        "MULTI_VENUE_CONCENTRATION_HIGH",
    )


def test_mad_normalization_handles_insufficient_and_zero_dispersion() -> None:
    assert robust_mad_zscores((Decimal("1"), Decimal("2"))) is None
    assert robust_mad_zscores((Decimal("1"),) * 5) == (Decimal("0"),) * 5
    scores = robust_mad_zscores(tuple(Decimal(value) for value in "12345"))
    assert scores is not None
    assert scores[2] == Decimal("0")
    assert scores[0] < Decimal("0") < scores[-1]


def test_future_timestamp_duplicate_venue_and_naive_now_are_rejected() -> None:
    future = observation("binance", return_bps="1", age=-1)
    result = CrossVenueResearchEngine().evaluate((future,), NOW)
    assert "VENUE_TIMESTAMP_IN_FUTURE" in result.blockers
    duplicate = observation("same", return_bps="1")
    with pytest.raises(ValueError, match="unique"):
        CrossVenueResearchEngine().evaluate((duplicate, duplicate), NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        CrossVenueResearchEngine().evaluate((), datetime(2026, 7, 15))

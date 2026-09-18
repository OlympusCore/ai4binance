"""WHALE-FUSION Phase 6 deterministic fusion score tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.whale_fusion import (
    DerivativesFeatures,
    FusionChannel,
    FusionConfig,
    FusionResult,
    PriceOiRegime,
    Provenance,
    SocialEventType,
    WhaleEventType,
    WhaleFusionEngine,
)
from ai4binance.whale_fusion.onchain import Chain, WhaleEvent
from ai4binance.whale_fusion.social import (
    SocialContradiction,
    SocialEvent,
    SocialStance,
)

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)
SOURCE = Provenance("FUSION_TEST", NOW, "https://fusion.example")


def whale_event(
    event_type: WhaleEventType = WhaleEventType.TOKEN_ACCUMULATION,
    *,
    event_id: str = "whale-1",
    timestamp: datetime = NOW,
    asset: str = "HOT",
) -> WhaleEvent:
    return WhaleEvent(
        event_id=event_id,
        event_type=event_type,
        chain=Chain.ETHEREUM,
        timestamp=timestamp,
        asset=asset,
        amount=Decimal("100"),
        usd_value=Decimal("2000000"),
        transfer_ids=(event_id,),
        confidence=Decimal("0.8"),
        provenance=(SOURCE,),
        reason_codes=("TEST",),
    )


def social_event(
    stance: SocialStance = SocialStance.SUPPORTIVE,
    *,
    event_id: str = "social-1",
    timestamp: datetime = NOW,
    assets: tuple[str, ...] = ("HOT",),
) -> SocialEvent:
    return SocialEvent(
        event_id=event_id,
        post_id=event_id,
        account_id="account-1",
        timestamp=timestamp,
        event_type=SocialEventType.PROJECT_ANNOUNCEMENT,
        stance=stance,
        assets=assets,
        confidence=Decimal("0.7"),
        provenance=(SOURCE,),
        reason_codes=("TEST",),
    )


def derivatives(
    regime: PriceOiRegime = PriceOiRegime.NEW_LONG_PARTICIPATION,
    *,
    symbol: str = "HOTUSDT",
    timestamp: datetime = NOW,
    blockers: tuple[str, ...] = (),
) -> DerivativesFeatures:
    return DerivativesFeatures(
        symbol=symbol,
        as_of=timestamp,
        oi_change_short=Decimal("0.1"),
        oi_change_medium=Decimal("0.2"),
        oi_zscore=Decimal("1"),
        oi_percentile=Decimal("0.8"),
        price_oi_regime=regime,
        funding_percentile=Decimal("0.6"),
        basis_zscore=Decimal("0.5"),
        taker_imbalance=Decimal("0.2"),
        top_vs_global_divergence=Decimal("0.1"),
        mark_index_deviation=Decimal("0.01"),
        blockers=blockers,
    )


def evaluate(**overrides: object) -> FusionResult:
    values: dict[str, object] = {
        "symbol": "HOTUSDT",
        "asset": "HOT",
        "as_of": NOW,
        "whale_events": (whale_event(),),
        "social_events": (social_event(),),
    }
    values.update(overrides)
    return WhaleFusionEngine().evaluate(**values)  # type: ignore[arg-type]


def test_two_independent_positive_channels_produce_research_score() -> None:
    result = evaluate()
    assert result.fusion_score > Decimal("90")
    assert result.direction_score > Decimal("0.8")
    assert result.active_channels == (
        FusionChannel.ONCHAIN,
        FusionChannel.SOCIAL,
    )
    assert result.blockers == ()
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.execution_allowed is False


def test_single_channel_is_explicitly_insufficient() -> None:
    result = evaluate(social_events=())
    assert result.active_channels == (FusionChannel.ONCHAIN,)
    assert "INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT" in result.blockers


def test_three_negative_channels_produce_bearish_research_score() -> None:
    result = evaluate(
        whale_events=(whale_event(WhaleEventType.TOKEN_DISTRIBUTION),),
        social_events=(social_event(SocialStance.NEGATIVE),),
        derivatives=derivatives(PriceOiRegime.NEW_SHORT_PRESSURE),
    )
    assert result.fusion_score < Decimal("20")
    assert result.direction_score < Decimal("-0.6")
    assert len(result.active_channels) == 3


def test_duplicate_ids_do_not_inflate_channel_score() -> None:
    event = whale_event()
    single = evaluate(whale_events=(event,))
    duplicated = evaluate(whale_events=(event, event, event))
    assert duplicated.direction_score == single.direction_score
    assert duplicated.confidence == single.confidence
    assert len(duplicated.contributions) == len(single.contributions)


def test_stale_and_future_evidence_is_ignored() -> None:
    stale = whale_event(timestamp=NOW - timedelta(days=3))
    future = social_event(timestamp=NOW + timedelta(minutes=1))
    result = evaluate(whale_events=(stale,), social_events=(future,))
    assert result.contributions == ()
    assert "STALE_FUSION_EVIDENCE_IGNORED" in result.blockers
    assert "INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT" in result.blockers
    assert result.fusion_score == Decimal("50")


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        (derivatives(symbol="BTCUSDT"), "DERIVATIVES_SYMBOL_MISMATCH"),
        (
            derivatives(blockers=("OI_OR_PRICE_HISTORY_INSUFFICIENT",)),
            "DERIVATIVES_FEATURES_BLOCKED",
        ),
    ],
)
def test_invalid_derivatives_context_is_blocked(
    features: DerivativesFeatures, expected: str
) -> None:
    result = evaluate(derivatives=features)
    assert expected in result.blockers
    assert FusionChannel.DERIVATIVES not in result.active_channels


def test_social_contradiction_reduces_confidence_not_direction() -> None:
    baseline = evaluate()
    contradiction = SocialContradiction(
        "contradiction-1", "HOT", "social-1", "social-2", NOW
    )
    penalized = evaluate(contradictions=(contradiction,))
    assert penalized.direction_score == baseline.direction_score
    assert penalized.confidence < baseline.confidence
    assert penalized.contradiction_count == 1
    assert "SOCIAL_CONTRADICTION_PRESENT" in penalized.blockers


def test_unrelated_assets_do_not_enter_fusion() -> None:
    result = evaluate(
        whale_events=(whale_event(asset="BTC"),),
        social_events=(social_event(assets=("BTC",)),),
    )
    assert result.contributions == ()
    assert result.active_channels == ()


def test_fusion_configuration_and_result_authority_fail_closed() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        FusionConfig(onchain_weight=Decimal("0.5"))
    with pytest.raises(ValueError, match="cannot dominate"):
        FusionConfig(
            onchain_weight=Decimal("0.3"),
            social_weight=Decimal("0.3"),
            derivatives_weight=Decimal("0.4"),
        )
    valid = evaluate()
    with pytest.raises(ValueError, match="execution authority"):
        replace(valid, execution_allowed=True)


def test_fusion_configuration_bounds_fail_closed() -> None:
    with pytest.raises(ValueError, match="evidence_window"):
        FusionConfig(evidence_window=timedelta(0))
    with pytest.raises(ValueError, match="independent channels"):
        FusionConfig(minimum_independent_channels=1)
    with pytest.raises(ValueError, match="contradiction_penalty"):
        FusionConfig(contradiction_penalty=Decimal("2"))
    with pytest.raises(ValueError, match="timezone-aware"):
        WhaleFusionEngine().evaluate(
            symbol="HOTUSDT",
            asset="HOT",
            as_of=datetime(2026, 7, 13),
        )


def test_fusion_result_numeric_contracts_fail_closed() -> None:
    valid = evaluate()
    with pytest.raises(ValueError, match="fusion_score"):
        replace(valid, fusion_score=Decimal("101"))
    with pytest.raises(ValueError, match="direction_score"):
        replace(valid, direction_score=Decimal("2"))
    with pytest.raises(ValueError, match="confidence"):
        replace(valid, confidence=Decimal("2"))

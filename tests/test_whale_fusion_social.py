"""WHALE-FUSION Phase 5 social intelligence tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.whale_fusion import Provenance, SocialEventType
from ai4binance.whale_fusion.social import (
    AccountCategory,
    CanonicalSocialPostNormalizer,
    SocialAccount,
    SocialAccountRegistry,
    SocialClassification,
    SocialContradiction,
    SocialEvent,
    SocialIntelligenceEngine,
    SocialPlatform,
    SocialPost,
    SocialStance,
)

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)
SOURCE = Provenance("SOCIAL_TEST", NOW, "https://social.example")


def account(*, verified: bool = True, confidence: str = "0.9") -> SocialAccount:
    return SocialAccount(
        account_id="project-founder",
        platform=SocialPlatform.X,
        handle="@founder",
        category=AccountCategory.PROJECT_FOUNDER,
        verified=verified,
        confidence=Decimal(confidence),
        provenance=SOURCE,
    )


def registry(*, verified: bool = True) -> SocialAccountRegistry:
    return SocialAccountRegistry.from_accounts((account(verified=verified),))


def post(
    *,
    post_id: str = "post-1",
    account_id: str = "project-founder",
    timestamp: datetime = NOW - timedelta(minutes=5),
    assets: tuple[str, ...] = ("HOT",),
    confidence: str = "0.8",
    stance: SocialStance = SocialStance.SUPPORTIVE,
) -> SocialPost:
    return SocialPost(
        post_id=post_id,
        platform=SocialPlatform.X,
        account_id=account_id,
        timestamp=timestamp,
        text="Explicit provider-normalized announcement",
        event_type=SocialEventType.PROJECT_ANNOUNCEMENT,
        stance=stance,
        assets=assets,
        source_confidence=Decimal(confidence),
        provenance=SOURCE,
    )


def test_all_required_account_categories_are_governed() -> None:
    assert set(AccountCategory) == {
        AccountCategory.PROJECT_FOUNDER,
        AccountCategory.FOUNDATION_OR_PROJECT_TEAM,
        AccountCategory.FUND_MANAGER,
        AccountCategory.MARKET_MAKER_EXECUTIVE,
        AccountCategory.KNOWN_WHALE,
        AccountCategory.ONCHAIN_ANALYST,
        AccountCategory.EXCHANGE,
        AccountCategory.REGULATOR,
        AccountCategory.SECURITY_RESEARCHER,
        AccountCategory.TOKEN_UNLOCK_OR_GOVERNANCE,
    }


def test_verified_allowlisted_post_produces_research_event() -> None:
    engine = SocialIntelligenceEngine(registry())
    result = engine.evaluate(post(), as_of=NOW)
    assert result.blockers == ()
    event = result.events[0]
    assert event.assets == ("HOT",)
    assert event.confidence == Decimal("0.72")
    assert event.promotion_status == "RESEARCH_ONLY"
    assert event.execution_allowed is False
    assert result == engine.evaluate(post(), as_of=NOW)


@pytest.mark.parametrize(
    ("engine", "item", "expected"),
    [
        (
            SocialIntelligenceEngine(SocialAccountRegistry(())),
            post(),
            "SOCIAL_ACCOUNT_NOT_ALLOWLISTED",
        ),
        (
            SocialIntelligenceEngine(registry(verified=False)),
            post(),
            "SOCIAL_ACCOUNT_UNVERIFIED",
        ),
        (
            SocialIntelligenceEngine(registry()),
            post(timestamp=NOW - timedelta(days=2)),
            "SOCIAL_POST_STALE",
        ),
        (
            SocialIntelligenceEngine(registry()),
            post(timestamp=NOW + timedelta(minutes=1)),
            "SOCIAL_POST_FROM_FUTURE",
        ),
        (
            SocialIntelligenceEngine(registry()),
            post(assets=()),
            "SOCIAL_ASSET_CONTEXT_MISSING",
        ),
        (
            SocialIntelligenceEngine(registry()),
            post(confidence="0.1"),
            "SOCIAL_CONFIDENCE_BELOW_MINIMUM",
        ),
    ],
)
def test_social_engine_returns_explicit_blockers(
    engine: SocialIntelligenceEngine, item: SocialPost, expected: str
) -> None:
    result = engine.evaluate(item, as_of=NOW)
    assert result.events == ()
    assert expected in result.blockers


def test_duplicate_post_is_idempotently_blocked() -> None:
    result = SocialIntelligenceEngine(registry()).evaluate(
        post(), as_of=NOW, seen_post_ids=frozenset({"post-1"})
    )
    assert result.duplicate is True
    assert result.blockers == ("DUPLICATE_SOCIAL_POST",)


def test_contradiction_detector_requires_shared_asset_and_opposing_stance() -> None:
    engine = SocialIntelligenceEngine(registry())
    supportive = engine.evaluate(post(post_id="positive"), as_of=NOW).events[0]
    negative = engine.evaluate(
        post(post_id="negative", stance=SocialStance.NEGATIVE), as_of=NOW
    ).events[0]
    neutral = engine.evaluate(
        post(post_id="neutral", stance=SocialStance.NEUTRAL), as_of=NOW
    ).events[0]
    contradiction = engine.contradictions((negative, supportive, neutral))
    assert len(contradiction) == 1
    assert contradiction[0].asset == "HOT"
    assert contradiction[0].execution_allowed is False
    assert contradiction == engine.contradictions((negative, supportive, neutral))

    other_asset = replace(negative, event_id="other", assets=("BTC",))
    assert engine.contradictions((supportive, other_asset)) == ()


def test_normalizer_requires_explicit_event_metadata() -> None:
    payload: dict[str, object] = {
        "post_id": "post-1",
        "platform": "X",
        "account_id": "project-founder",
        "timestamp": 1000,
        "text": "announcement",
        "event_type": "PROJECT_ANNOUNCEMENT",
        "stance": "SUPPORTIVE",
        "assets": ["hot", "HOT"],
        "source_confidence": "0.8",
    }
    result = CanonicalSocialPostNormalizer().normalize(payload, provenance=SOURCE)
    assert result.assets == ("HOT",)
    with pytest.raises(ExchangePayloadError, match="event_type"):
        CanonicalSocialPostNormalizer().normalize(
            {**payload, "event_type": "INFER_FROM_TEXT"}, provenance=SOURCE
        )
    with pytest.raises(ExchangePayloadError, match="assets"):
        CanonicalSocialPostNormalizer().normalize(
            {**payload, "assets": "HOT"}, provenance=SOURCE
        )


def test_registry_and_social_event_contract_fail_closed() -> None:
    duplicate = account()
    with pytest.raises(ValueError, match="unique"):
        SocialAccountRegistry((duplicate, duplicate))
    event = SocialIntelligenceEngine(registry()).evaluate(post(), as_of=NOW).events[0]
    with pytest.raises(ValueError, match="execution authority"):
        SocialEvent(
            event_id=event.event_id,
            post_id=event.post_id,
            account_id=event.account_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            stance=event.stance,
            assets=event.assets,
            confidence=event.confidence,
            provenance=event.provenance,
            reason_codes=event.reason_codes,
            execution_allowed=True,
        )


def test_social_configuration_and_time_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="time windows"):
        SocialIntelligenceEngine(registry(), maximum_age=timedelta(0))
    with pytest.raises(ValueError, match="minimum social confidence"):
        SocialIntelligenceEngine(registry(), minimum_confidence=Decimal("2"))
    with pytest.raises(ValueError, match="timezone-aware"):
        SocialIntelligenceEngine(registry()).evaluate(
            post(), as_of=datetime(2026, 7, 13)
        )
    with pytest.raises(ValueError, match="confidence"):
        replace(account(), confidence=Decimal("2"))


def test_normalizer_rejects_invalid_enum_asset_item_and_confidence() -> None:
    base: dict[str, object] = {
        "post_id": "post-1",
        "platform": "X",
        "account_id": "project-founder",
        "timestamp": 1000,
        "text": "announcement",
        "event_type": "PROJECT_ANNOUNCEMENT",
        "stance": "SUPPORTIVE",
        "assets": ["HOT"],
        "source_confidence": "0.8",
    }
    normalizer = CanonicalSocialPostNormalizer()
    with pytest.raises(ExchangePayloadError, match="platform"):
        normalizer.normalize({**base, "platform": "UNKNOWN"}, provenance=SOURCE)
    with pytest.raises(ExchangePayloadError, match="assets"):
        normalizer.normalize({**base, "assets": [1]}, provenance=SOURCE)
    with pytest.raises(ExchangePayloadError, match="finite"):
        normalizer.normalize({**base, "source_confidence": "NaN"}, provenance=SOURCE)


def test_contradiction_window_and_authority_are_fail_closed() -> None:
    engine = SocialIntelligenceEngine(registry())
    first = engine.evaluate(post(post_id="first"), as_of=NOW).events[0]
    late = replace(
        first,
        event_id="late-event",
        post_id="late",
        timestamp=NOW + timedelta(days=3),
        stance=SocialStance.DENIAL,
    )
    assert engine.contradictions((first, late)) == ()
    with pytest.raises(ValueError, match="execution authority"):
        SocialClassification("post-1", (), (), execution_allowed=True)
    with pytest.raises(ValueError, match="execution authority"):
        SocialContradiction(
            "contradiction-1",
            "HOT",
            "first",
            "second",
            NOW,
            execution_allowed=True,
        )

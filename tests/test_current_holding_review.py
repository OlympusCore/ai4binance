"""Current holding review fail-closed policy tests."""

from decimal import Decimal

import pytest

from ai4binance.portfolio.asset_policy import AssetClassification
from ai4binance.portfolio.current_holding_review import (
    CurrentHoldingAssessment,
    CurrentHoldingInput,
    CurrentHoldingReviewEngine,
    CurrentHoldingReviewPolicy,
    CurrentHoldingReviewReport,
    HoldingDecision,
    RecoveryState,
)
from ai4binance.portfolio.holding_opportunity import RiskRewardProfile


def profile(
    *,
    quality: str = "70",
    rr: str = "2",
    risk: str = "40",
    confidence: str = "0.7",
) -> RiskRewardProfile:
    return RiskRewardProfile(
        Decimal(quality),
        Decimal(rr),
        Decimal(risk),
        Decimal(confidence),
    )


def holding(
    classification: AssetClassification,
    *,
    liquidity: str = "75",
    item_profile: RiskRewardProfile | None = None,
    blockers: tuple[str, ...] = (),
) -> CurrentHoldingInput:
    return CurrentHoldingInput(
        asset="hot",
        symbol="hotusdt",
        classification=classification,
        market_value_usdt=Decimal("100"),
        portfolio_weight=Decimal("0.10"),
        profile=item_profile or profile(),
        liquidity_score=Decimal(liquidity),
        blockers=blockers,
    )


def test_current_holding_review_covers_cash_dust_quality_and_recovery_paths() -> None:
    report = CurrentHoldingReviewEngine().review(
        (
            holding(AssetClassification.CASH_EQUIVALENT),
            holding(AssetClassification.DUST),
            holding(AssetClassification.ACTIVE_POSITION, item_profile=profile()),
            holding(
                AssetClassification.ACTIVE_POSITION,
                item_profile=profile(quality="60", rr="2", risk="40"),
            ),
        )
    )

    actions = tuple(item.recommended_action for item in report.assessments)
    assert actions == (
        HoldingDecision.NO_ACTION,
        HoldingDecision.NO_ACTION,
        HoldingDecision.HOLD_OPPORTUNITY,
        HoldingDecision.RECOVERY_WATCH,
    )
    assert report.assessments[0].manual_approval_required is False
    assert report.assessments[2].recovery_state is RecoveryState.HIGH
    assert report.assessments[3].recovery_state is RecoveryState.MEDIUM
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_current_holding_review_blocks_unsafe_or_weak_holdings() -> None:
    report = CurrentHoldingReviewEngine().review(
        (
            holding(AssetClassification.ILLIQUID, liquidity="20"),
            holding(
                AssetClassification.ACTIVE_POSITION,
                item_profile=profile(quality="80", rr="2", risk="90"),
            ),
            holding(
                AssetClassification.ACTIVE_POSITION,
                item_profile=profile(quality="80", rr="1", risk="40"),
            ),
            holding(
                AssetClassification.ACTIVE_POSITION,
                blockers=("PRICE_STALE",),
            ),
        )
    )

    assert report.assessments[0].recommended_action is HoldingDecision.RESEARCH_ONLY
    assert report.assessments[0].blockers == (
        "ILLIQUID_HOLDING",
        "INSUFFICIENT_EXIT_LIQUIDITY",
    )
    assert report.assessments[1].recommended_action is HoldingDecision.EXIT_CANDIDATE
    assert (
        report.assessments[2].recommended_action is HoldingDecision.CONVERSION_CANDIDATE
    )
    assert report.assessments[3].reason_codes == ("BLOCKED_EVIDENCE",)
    assert report.blockers == (
        "ILLIQUID_HOLDING",
        "INSUFFICIENT_EXIT_LIQUIDITY",
        "PRICE_STALE",
    )


def test_current_holding_review_rejects_invalid_contracts() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        CurrentHoldingReviewPolicy(minimum_risk_reward=Decimal("-1"))
    with pytest.raises(ValueError, match="<= 100"):
        CurrentHoldingReviewPolicy(minimum_hold_quality=Decimal("101"))
    with pytest.raises(ValueError, match="asset and symbol"):
        CurrentHoldingInput(
            asset="bad asset",
            symbol="HOTUSDT",
            classification=AssetClassification.ACTIVE_POSITION,
            market_value_usdt=Decimal("1"),
            portfolio_weight=Decimal("0.1"),
            profile=profile(),
            liquidity_score=Decimal("50"),
        )
    with pytest.raises(ValueError, match="holding input values"):
        CurrentHoldingInput(
            asset="HOT",
            symbol="HOTUSDT",
            classification=AssetClassification.ACTIVE_POSITION,
            market_value_usdt=Decimal("1"),
            portfolio_weight=Decimal("1.1"),
            profile=profile(),
            liquidity_score=Decimal("50"),
        )
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        CurrentHoldingInput(
            asset="HOT",
            symbol="HOTUSDT",
            classification=AssetClassification.ACTIVE_POSITION,
            market_value_usdt=Decimal("1"),
            portfolio_weight=Decimal("0.1"),
            profile=profile(),
            liquidity_score=Decimal("50"),
            blockers=("",),
        )


def test_current_holding_review_outputs_never_grant_execution_authority() -> None:
    with pytest.raises(ValueError, match="identity is required"):
        CurrentHoldingAssessment(
            "",
            "HOTUSDT",
            AssetClassification.ACTIVE_POSITION,
            Decimal("1"),
            Decimal("0.1"),
            Decimal("50"),
            Decimal("2"),
            Decimal("50"),
            RecoveryState.HIGH,
            HoldingDecision.HOLD_OPPORTUNITY,
            ("OK",),
        )
    with pytest.raises(ValueError, match="codes cannot be empty"):
        CurrentHoldingAssessment(
            "HOT",
            "HOTUSDT",
            AssetClassification.ACTIVE_POSITION,
            Decimal("1"),
            Decimal("0.1"),
            Decimal("50"),
            Decimal("2"),
            Decimal("50"),
            RecoveryState.HIGH,
            HoldingDecision.HOLD_OPPORTUNITY,
            ("",),
        )
    with pytest.raises(ValueError, match="cannot grant execution"):
        CurrentHoldingAssessment(
            "HOT",
            "HOTUSDT",
            AssetClassification.ACTIVE_POSITION,
            Decimal("1"),
            Decimal("0.1"),
            Decimal("50"),
            Decimal("2"),
            Decimal("50"),
            RecoveryState.HIGH,
            HoldingDecision.HOLD_OPPORTUNITY,
            ("OK",),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="blockers cannot be empty"):
        CurrentHoldingReviewReport((), ("",))
    with pytest.raises(ValueError, match="cannot grant execution"):
        CurrentHoldingReviewReport((), (), execution_allowed=True)

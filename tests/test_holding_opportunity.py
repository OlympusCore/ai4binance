"""Objective holding-vs-opportunity review tests."""

from decimal import Decimal

import pytest

from ai4binance.markets import CapitalMarket
from ai4binance.portfolio import (
    HoldingOpportunity,
    HoldingOpportunityAction,
    HoldingOpportunityPolicy,
    HoldingsOpportunityReviewEngine,
    PortfolioOpportunity,
    RiskRewardProfile,
)


def profile(
    quality: str,
    rr: str,
    risk: str,
    confidence: str = "0.6",
) -> RiskRewardProfile:
    return RiskRewardProfile(
        Decimal(quality),
        Decimal(rr),
        Decimal(risk),
        Decimal(confidence),
    )


def holding(
    asset: str,
    *,
    value: str,
    liquidatable: str,
    quality: str,
    rr: str,
    risk: str,
) -> HoldingOpportunity:
    return HoldingOpportunity(
        asset,
        f"{asset}USDT",
        Decimal(value),
        Decimal(liquidatable),
        profile(quality, rr, risk),
    )


def opportunity(
    market: CapitalMarket,
    symbol: str,
    *,
    required: str,
    quality: str,
    rr: str,
    risk: str,
) -> PortfolioOpportunity:
    return PortfolioOpportunity(
        market,
        symbol,
        Decimal(required),
        profile(quality, rr, risk),
    )


def test_engine_rotates_weak_hot_partially_into_better_spot_opportunity() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "HOT",
                value="300",
                liquidatable="250",
                quality="45",
                rr="0.9",
                risk="68",
            ),
        ),
        opportunities=(
            opportunity(
                CapitalMarket.SPOT,
                "ETHUSDT",
                required="120",
                quality="72",
                rr="2.0",
                risk="45",
            ),
        ),
        liquid_capital_usdt=Decimal("5"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    advice = report.advice[0]
    assert advice.action is HoldingOpportunityAction.ROTATE_TO_SPOT_REVIEW
    assert advice.subject == "HOT"
    assert advice.target_symbol == "ETHUSDT"
    assert advice.proposed_notional_usdt == Decimal("62.50")
    assert advice.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_engine_uses_liquid_capital_before_selling_any_coin() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "HOT",
                value="300",
                liquidatable="250",
                quality="45",
                rr="0.9",
                risk="68",
            ),
        ),
        opportunities=(
            opportunity(
                CapitalMarket.SPOT,
                "ETHUSDT",
                required="80",
                quality="72",
                rr="2.0",
                risk="45",
            ),
        ),
        liquid_capital_usdt=Decimal("100"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert report.advice[0].action is HoldingOpportunityAction.USE_LIQUID_CAPITAL_REVIEW
    assert report.advice[0].subject == "LIQUID_CAPITAL"


def test_engine_blocks_new_futures_when_ten_percent_cap_is_full() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "SOL",
                value="400",
                liquidatable="300",
                quality="50",
                rr="1.0",
                risk="60",
            ),
        ),
        opportunities=(
            opportunity(
                CapitalMarket.USD_M_FUTURES,
                "BTCUSDT",
                required="80",
                quality="80",
                rr="2.4",
                risk="55",
            ),
        ),
        liquid_capital_usdt=Decimal("10"),
        total_portfolio_value_usdt=Decimal("1000"),
        current_futures_capital_usdt=Decimal("100"),
    )

    assert report.advice[0].action is HoldingOpportunityAction.BLOCKED
    assert report.advice[0].blockers == ("FUTURES_CAPITAL_TARGET_REACHED",)


def test_engine_reduces_weak_holding_to_build_liquid_reserve() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "XRP",
                value="200",
                liquidatable="160",
                quality="40",
                rr="0.8",
                risk="80",
            ),
        ),
        opportunities=(),
        liquid_capital_usdt=Decimal("5"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert (
        report.advice[0].action is HoldingOpportunityAction.REDUCE_TO_LIQUIDITY_REVIEW
    )
    assert report.advice[0].subject == "XRP"
    assert report.advice[0].proposed_notional_usdt == Decimal("40.00")


def test_engine_holds_strong_holding_when_no_better_opportunity_exists() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "BNB",
                value="150",
                liquidatable="100",
                quality="75",
                rr="2.1",
                risk="35",
            ),
        ),
        opportunities=(),
        liquid_capital_usdt=Decimal("80"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert report.advice[0].action is HoldingOpportunityAction.HOLD_REVIEW
    assert report.advice[0].approval_required is False


def test_policy_rejects_unsafe_bounds() -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        HoldingOpportunityPolicy(maximum_single_opportunity_ratio=Decimal("1.5"))
    with pytest.raises(ValueError, match="positive"):
        HoldingOpportunityPolicy(maximum_rotation_ratio_per_holding=Decimal("0"))

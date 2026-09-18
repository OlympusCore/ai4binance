"""Objective holding-vs-opportunity review tests."""

from decimal import Decimal

import pytest

from ai4binance.markets import CapitalMarket
from ai4binance.portfolio import (
    HoldingOpportunity,
    HoldingOpportunityAction,
    HoldingOpportunityAdvice,
    HoldingOpportunityPolicy,
    HoldingOpportunityReport,
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


def test_engine_blocks_rotation_when_no_suitable_source_exists() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "BNB",
                value="200",
                liquidatable="120",
                quality="70",
                rr="1.8",
                risk="35",
            ),
        ),
        opportunities=(
            opportunity(
                CapitalMarket.SPOT,
                "ETHUSDT",
                required="100",
                quality="72",
                rr="2.0",
                risk="45",
            ),
        ),
        liquid_capital_usdt=Decimal("5"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert report.advice[0].action is HoldingOpportunityAction.BLOCKED
    assert report.advice[0].subject == "ROTATION_SOURCE"
    assert report.advice[0].blockers == ("NO_SUITABLE_ROTATION_SOURCE",)


def test_engine_blocks_rotation_when_proposed_notional_is_below_minimum() -> None:
    report = HoldingsOpportunityReviewEngine(
        HoldingOpportunityPolicy(minimum_rotation_usdt=Decimal("30"))
    ).review(
        holdings=(
            holding(
                "HOT",
                value="80",
                liquidatable="40",
                quality="45",
                rr="0.9",
                risk="68",
            ),
        ),
        opportunities=(
            opportunity(
                CapitalMarket.SPOT,
                "ETHUSDT",
                required="60",
                quality="72",
                rr="2.0",
                risk="45",
            ),
        ),
        liquid_capital_usdt=Decimal("25"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert report.advice[0].action is HoldingOpportunityAction.BLOCKED
    assert report.advice[0].subject == "HOT"
    assert report.advice[0].blockers == ("ROTATION_MIN_NOTIONAL_BLOCKED",)


def test_engine_routes_stronger_futures_opportunity_to_futures_review() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            holding(
                "SOL",
                value="500",
                liquidatable="300",
                quality="45",
                rr="0.8",
                risk="68",
            ),
        ),
        opportunities=(
            opportunity(
                CapitalMarket.USD_M_FUTURES,
                "BTCUSDT",
                required="100",
                quality="82",
                rr="2.4",
                risk="45",
            ),
        ),
        liquid_capital_usdt=Decimal("5"),
        total_portfolio_value_usdt=Decimal("1000"),
        current_futures_capital_usdt=Decimal("20"),
    )

    advice = report.advice[0]
    assert advice.action is HoldingOpportunityAction.ROTATE_TO_FUTURES_REVIEW
    assert advice.subject == "SOL"
    assert advice.target_symbol == "BTCUSDT"
    assert advice.market is CapitalMarket.USD_M_FUTURES


def test_engine_falls_back_to_watchlist_when_nothing_actionable_exists() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(),
        opportunities=(),
        liquid_capital_usdt=Decimal("50"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert len(report.advice) == 1
    assert report.advice[0].action is HoldingOpportunityAction.WATCHLIST
    assert report.advice[0].approval_required is False


def test_engine_rejects_invalid_review_amounts_fail_closed() -> None:
    engine = HoldingsOpportunityReviewEngine()

    with pytest.raises(
        ValueError, match="liquid_capital_usdt must be finite and non-negative"
    ):
        engine.review(
            holdings=(),
            opportunities=(),
            liquid_capital_usdt=Decimal("-1"),
            total_portfolio_value_usdt=Decimal("500"),
        )

    with pytest.raises(
        ValueError,
        match="total_portfolio_value_usdt must be finite and positive",
    ):
        engine.review(
            holdings=(),
            opportunities=(),
            liquid_capital_usdt=Decimal("0"),
            total_portfolio_value_usdt=Decimal("0"),
        )


def test_policy_rejects_unsafe_bounds() -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        HoldingOpportunityPolicy(maximum_single_opportunity_ratio=Decimal("1.5"))
    with pytest.raises(ValueError, match="positive"):
        HoldingOpportunityPolicy(maximum_rotation_ratio_per_holding=Decimal("0"))


def test_holding_opportunity_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="quality_score must be between zero and 100"):
        RiskRewardProfile(Decimal("-1"), Decimal("1.0"), Decimal("10"))
    with pytest.raises(ValueError, match="risk_reward must be finite and non-negative"):
        RiskRewardProfile(Decimal("1"), Decimal("-1"), Decimal("10"))
    with pytest.raises(ValueError, match="confidence must be between zero and one"):
        RiskRewardProfile(Decimal("1"), Decimal("1.0"), Decimal("10"), Decimal("1.1"))

    risk_profile = RiskRewardProfile(
        Decimal("60"),
        Decimal("1.5"),
        Decimal("30"),
    )

    with pytest.raises(
        ValueError, match="holding asset and symbol must be alphanumeric"
    ):
        HoldingOpportunity(" ", "SOLUSDT", Decimal("1"), Decimal("1"), risk_profile)
    with pytest.raises(ValueError, match="holding values cannot be negative"):
        HoldingOpportunity("SOL", "SOLUSDT", Decimal("-1"), Decimal("0"), risk_profile)
    with pytest.raises(
        ValueError, match="liquidatable value cannot exceed holding value"
    ):
        HoldingOpportunity("SOL", "SOLUSDT", Decimal("1"), Decimal("2"), risk_profile)
    with pytest.raises(ValueError, match="holding blockers cannot be empty"):
        HoldingOpportunity(
            "SOL",
            "SOLUSDT",
            Decimal("1"),
            Decimal("1"),
            risk_profile,
            blockers=(" ",),
        )

    with pytest.raises(ValueError, match="opportunity symbol must be alphanumeric"):
        PortfolioOpportunity(
            CapitalMarket.SPOT,
            " ",
            Decimal("1"),
            risk_profile,
        )
    with pytest.raises(
        ValueError, match="required_capital_usdt must be finite and positive"
    ):
        PortfolioOpportunity(
            CapitalMarket.SPOT,
            "SOLUSDT",
            Decimal("0"),
            risk_profile,
        )
    with pytest.raises(ValueError, match="opportunity blockers cannot be empty"):
        PortfolioOpportunity(
            CapitalMarket.SPOT,
            "SOLUSDT",
            Decimal("1"),
            risk_profile,
            blockers=(" ",),
        )

    with pytest.raises(
        ValueError, match="holding opportunity advice identity is required"
    ):
        HoldingOpportunityAdvice(
            HoldingOpportunityAction.HOLD_REVIEW,
            " ",
            None,
            CapitalMarket.SPOT,
            Decimal("0"),
            "Valid rationale",
        )
    with pytest.raises(
        ValueError, match="advice notional must be finite and non-negative"
    ):
        HoldingOpportunityAdvice(
            HoldingOpportunityAction.HOLD_REVIEW,
            "SOL",
            None,
            CapitalMarket.SPOT,
            Decimal("-1"),
            "Valid rationale",
        )
    with pytest.raises(ValueError, match="target_symbol cannot be empty"):
        HoldingOpportunityAdvice(
            HoldingOpportunityAction.ROTATE_TO_SPOT_REVIEW,
            "SOL",
            " ",
            CapitalMarket.SPOT,
            Decimal("1"),
            "Valid rationale",
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        HoldingOpportunityAdvice(
            HoldingOpportunityAction.HOLD_REVIEW,
            "SOL",
            None,
            CapitalMarket.SPOT,
            Decimal("0"),
            "Valid rationale",
            execution_allowed=True,
        )

    with pytest.raises(
        ValueError, match="holding opportunity report values are invalid"
    ):
        HoldingOpportunityReport(
            Decimal("-1"),
            Decimal("0"),
            Decimal("0"),
            (),
            (),
        )
    with pytest.raises(ValueError, match="liquid_ratio cannot exceed one"):
        HoldingOpportunityReport(
            Decimal("1"),
            Decimal("1"),
            Decimal("1.1"),
            (),
            (),
        )
    with pytest.raises(ValueError, match="cannot allow execution"):
        HoldingOpportunityReport(
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            (),
            (),
            execution_allowed=True,
        )

    with pytest.raises(ValueError, match="must be finite and non-negative"):
        HoldingOpportunityPolicy(minimum_rotation_usdt=Decimal("-1"))


def test_engine_blocks_blocked_evidence() -> None:
    report = HoldingsOpportunityReviewEngine().review(
        holdings=(
            HoldingOpportunity(
                "SOL",
                "SOLUSDT",
                Decimal("200"),
                Decimal("100"),
                profile("80", "2.0", "30"),
                blockers=("HOLDING_EVIDENCE_BLOCKED",),
            ),
        ),
        opportunities=(
            PortfolioOpportunity(
                CapitalMarket.SPOT,
                "ETHUSDT",
                Decimal("80"),
                profile("72", "2.0", "45"),
                blockers=("OPPORTUNITY_EVIDENCE_BLOCKED",),
            ),
        ),
        liquid_capital_usdt=Decimal("0"),
        total_portfolio_value_usdt=Decimal("500"),
    )

    assert report.blockers == (
        "HOLDING_EVIDENCE_BLOCKED",
        "OPPORTUNITY_EVIDENCE_BLOCKED",
    )
    assert len(report.advice) == 1
    assert report.advice[0].action is HoldingOpportunityAction.BLOCKED
    assert report.advice[0].subject == "ACCOUNT_EVIDENCE"
    assert report.advice[0].blockers == (
        "HOLDING_EVIDENCE_BLOCKED",
        "OPPORTUNITY_EVIDENCE_BLOCKED",
    )

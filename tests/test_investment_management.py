"""Proposal-only investment management assistant tests."""

from datetime import UTC, datetime
from decimal import Decimal

from ai4binance.markets import CapitalMarket
from ai4binance.portfolio import (
    FuturesAccountSnapshotService,
    HoldingOpportunityAction,
    HoldingOpportunityAdvice,
    HoldingOpportunityReport,
    InvestmentManagementAssistant,
    ManagementAction,
    MarketManagementContext,
    OpportunityReviewItem,
    PortfolioAnalytics,
    ValuedSpotAsset,
    WalletSnapshotService,
)
from ai4binance.portfolio.rebalancing import (
    RebalanceAction,
    RebalanceProposal,
)

NOW = datetime(2026, 7, 14, tzinfo=UTC)


def order_payload(*, client_order_id: str, side: str = "BUY") -> dict[str, object]:
    return {
        "orderId": 1,
        "clientOrderId": client_order_id,
        "symbol": "HOTUSDT",
        "side": side,
        "type": "LIMIT",
        "status": "NEW",
        "price": "0.001",
        "origQty": "100",
        "executedQty": "10",
    }


class SpotReader:
    def account(self) -> object:
        return {
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": "HOT", "free": "100", "locked": "10"},
                {"asset": "USDT", "free": "50", "locked": "0"},
            ],
        }

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return [order_payload(client_order_id="spot-open")]


class FuturesReader:
    def account(self) -> object:
        return {
            "canTrade": True,
            "totalWalletBalance": "100",
            "availableBalance": "80",
        }

    def positions(self, symbol: str | None = None) -> object:
        return [
            {
                "symbol": symbol,
                "positionAmt": "5",
                "entryPrice": "0.001",
                "unRealizedProfit": "-1",
            }
        ]

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return [order_payload(client_order_id="futures-open", side="SELL")]


def test_assistant_reviews_positions_orders_and_new_opportunities() -> None:
    spot_wallet = WalletSnapshotService(SpotReader()).capture("HOTUSDT", NOW)
    futures_account = FuturesAccountSnapshotService(FuturesReader()).capture(
        "HOTUSDT", NOW
    )
    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=spot_wallet,
        futures_account=futures_account,
        spot=MarketManagementContext("SPOT", "SELL", "BEARISH", (), ("WEAK_OOS",)),
        futures=MarketManagementContext(
            "USD_M_FUTURES",
            "NO_TRADE",
            "BEARISH",
            ("NEW_SHORT_PRESSURE",),
            ("FUTURES_OOS_NOT_APPROVED",),
        ),
    )

    actions = {
        (item.category, item.market, item.action) for item in report.recommendations
    }
    assert (
        "EXISTING_POSITION",
        "SPOT",
        ManagementAction.REDUCE_RISK_REVIEW,
    ) in actions
    assert (
        "EXISTING_POSITION",
        "USD_M_FUTURES",
        ManagementAction.REDUCE_RISK_REVIEW,
    ) in actions
    assert ("OPEN_ORDER", "SPOT", ManagementAction.OPEN_ORDER_REVIEW) in actions
    assert (
        "NEW_OPPORTUNITY",
        "USD_M_FUTURES",
        ManagementAction.WATCHLIST,
    ) in actions
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_assistant_blocks_management_without_both_account_snapshots() -> None:
    empty = MarketManagementContext("SPOT", "NO_TRADE", "UNKNOWN", (), ())
    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=None,
        futures_account=None,
        spot=empty,
        futures=MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ()),
    )
    assert report.recommendations == ()
    assert report.blockers == (
        "SPOT_WALLET_UNAVAILABLE_FOR_MANAGEMENT",
        "FUTURES_ACCOUNT_UNAVAILABLE_FOR_MANAGEMENT",
    )


def test_assistant_keeps_spot_recommendations_when_futures_is_unavailable() -> None:
    spot_wallet = WalletSnapshotService(SpotReader()).capture("HOTUSDT", NOW)
    spot = MarketManagementContext("SPOT", "SELL", "BEARISH", (), ())
    futures = MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ())

    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=spot_wallet,
        futures_account=None,
        spot=spot,
        futures=futures,
    )

    assert report.recommendations
    assert {item.market for item in report.recommendations} == {"SPOT"}
    assert "FUTURES_ACCOUNT_UNAVAILABLE_FOR_MANAGEMENT" in report.blockers
    assert report.execution_allowed is False


def test_futures_recommendation_marks_unknown_risk_evidence() -> None:
    futures_account = FuturesAccountSnapshotService(FuturesReader()).capture(
        "HOTUSDT", NOW
    )
    empty = MarketManagementContext("SPOT", "NO_TRADE", "UNKNOWN", (), ())
    futures = MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "BEARISH", (), ())

    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=None,
        futures_account=futures_account,
        spot=empty,
        futures=futures,
    )

    position = next(
        item for item in report.recommendations if item.category == "EXISTING_POSITION"
    )
    assert "LIQUIDATION_PRICE_UNAVAILABLE" in position.blockers
    assert "FUNDING_DATA_UNAVAILABLE" in position.blockers
    assert "liquidation" not in position.rationale.lower()
    assert "funding" not in position.rationale.lower()


def test_investment_assistant_surfaces_rebalance_as_manual_review_only() -> None:
    proposal = RebalanceProposal(
        RebalanceAction.SELL,
        Decimal("0.8"),
        Decimal("0.6"),
        Decimal("10"),
        Decimal("20"),
        Decimal("0.02"),
        1,
        (),
    )
    empty = MarketManagementContext("SPOT", "NO_TRADE", "UNKNOWN", (), ())
    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=None,
        futures_account=None,
        spot=empty,
        futures=MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ()),
        rebalance_proposal=proposal,
    )
    recommendation = next(
        item
        for item in report.recommendations
        if item.category == "PORTFOLIO_REBALANCE"
    )
    assert recommendation.action is ManagementAction.REDUCE_RISK_REVIEW
    assert recommendation.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_investment_assistant_surfaces_holding_opportunity_rotation() -> None:
    holding_report = HoldingOpportunityReport(
        Decimal("500"),
        Decimal("5"),
        Decimal("0.01"),
        (
            HoldingOpportunityAdvice(
                HoldingOpportunityAction.ROTATE_TO_SPOT_REVIEW,
                "HOT",
                "ETHUSDT",
                CapitalMarket.SPOT,
                Decimal("62.50"),
                "A stronger risk/reward opportunity exists.",
                ("SOURCE_SYMBOL=HOTUSDT",),
            ),
        ),
        (),
    )
    empty = MarketManagementContext("SPOT", "NO_TRADE", "UNKNOWN", (), ())
    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=None,
        futures_account=None,
        spot=empty,
        futures=MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ()),
        holding_opportunity_report=holding_report,
    )
    recommendation = next(
        item
        for item in report.recommendations
        if item.category == "HOLDING_OPPORTUNITY_REVIEW"
    )
    assert recommendation.subject == "HOT->ETHUSDT"
    assert recommendation.action is ManagementAction.REDUCE_RISK_REVIEW
    assert recommendation.execution_allowed is False


def test_growth_opportunity_prepares_liquidity_when_quote_reserve_is_low() -> None:
    spot_wallet = WalletSnapshotService(SpotReader()).capture("HOTUSDT", NOW)
    analytics = PortfolioAnalytics(
        Decimal("500"),
        (
            ValuedSpotAsset(
                "HOT",
                Decimal("1000000"),
                Decimal("0.0005"),
                Decimal("500"),
                Decimal("1"),
            ),
        ),
        (),
        "HOT",
        Decimal("1"),
        None,
        ("PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED",),
    )

    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=spot_wallet,
        futures_account=None,
        spot=MarketManagementContext(
            "SPOT",
            "NO_TRADE",
            "BULLISH",
            ("trend_continuation",),
            ("ENTRY_TRIGGER_MISSING", "OOS_APPROVAL_MISSING"),
        ),
        futures=MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ()),
        portfolio_analytics=analytics,
    )

    opportunity = next(
        item for item in report.recommendations if item.category == "NEW_OPPORTUNITY"
    )
    liquidity = next(
        item
        for item in report.recommendations
        if item.category == "OPPORTUNITY_LIQUIDITY"
    )
    assert opportunity.action is ManagementAction.WATCHLIST
    assert "PROFIT_GROWTH_REVIEW" in opportunity.blockers
    assert liquidity.subject == "HOT->USDT_RESERVE"
    assert liquidity.action is ManagementAction.PREPARE_LIQUIDITY_REVIEW
    assert "QUOTE_RESERVE_BELOW_TARGET" in liquidity.blockers
    assert "MANUAL_LIQUIDITY_REVIEW_REQUIRED" in liquidity.blockers
    assert liquidity.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_growth_liquidity_review_is_not_added_without_setup_radar() -> None:
    spot_wallet = WalletSnapshotService(SpotReader()).capture("HOTUSDT", NOW)

    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=spot_wallet,
        futures_account=None,
        spot=MarketManagementContext("SPOT", "NO_TRADE", "BULLISH", (), ()),
        futures=MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ()),
    )

    assert {item.category for item in report.recommendations}.isdisjoint(
        {"OPPORTUNITY_LIQUIDITY", "NEW_OPPORTUNITY"}
    )


def test_rich_growth_radar_surfaces_blocked_opportunity_and_liquidity() -> None:
    spot_wallet = WalletSnapshotService(SpotReader()).capture("HOTUSDT", NOW)
    analytics = PortfolioAnalytics(
        Decimal("500"),
        (
            ValuedSpotAsset(
                "HOT",
                Decimal("1000000"),
                Decimal("0.0005"),
                Decimal("500"),
                Decimal("1"),
            ),
        ),
        (),
        "HOT",
        Decimal("1"),
        None,
        ("PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED",),
    )
    radar = (
        OpportunityReviewItem(
            "trend_continuation",
            timeframe="1h",
            direction="BEARISH",
            status="WAIT_FOR_RETEST",
            promotion_status="RESEARCH_ONLY",
            setup_tier="C",
            score=66.9,
            confidence=0.47,
            blockers=("ENTRY_TRIGGER_MISSING",),
        ),
    )

    report = InvestmentManagementAssistant().review(
        symbol="HOTUSDT",
        spot_wallet=spot_wallet,
        futures_account=None,
        spot=MarketManagementContext(
            "SPOT",
            "NO_TRADE",
            "BEARISH",
            (),
            ("NO_READY_CANDIDATE",),
            radar,
        ),
        futures=MarketManagementContext("USD_M_FUTURES", "NO_TRADE", "UNKNOWN", (), ()),
        portfolio_analytics=analytics,
    )

    opportunity = next(
        item for item in report.recommendations if item.category == "NEW_OPPORTUNITY"
    )
    liquidity = next(
        item
        for item in report.recommendations
        if item.category == "OPPORTUNITY_LIQUIDITY"
    )
    assert opportunity.subject == "trend_continuation@1h"
    assert "target R/R 2-3" in opportunity.rationale
    assert "ENTRY_TRIGGER_MISSING" in opportunity.blockers
    assert "TARGET_RR_REVIEW=2_TO_3" in opportunity.blockers
    assert opportunity.execution_allowed is False
    assert liquidity.subject == "HOT->USDT_RESERVE"
    assert liquidity.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"

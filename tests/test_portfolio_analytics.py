"""Read-only portfolio valuation and concentration tests."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from ai4binance.portfolio.analytics import (
    PortfolioAnalytics,
    PortfolioAnalyticsService,
    ValuedSpotAsset,
)
from ai4binance.portfolio.risk_budget import (
    PortfolioRiskAssessment,
    PortfolioRiskPolicy,
)
from ai4binance.portfolio.wallet import SpotBalance, WalletSnapshot

NOW = datetime(2026, 7, 15, tzinfo=UTC)


class Prices:
    def ticker_price(self, symbol: str) -> Decimal:
        prices = {"HOTUSDT": Decimal("0.002"), "XRPUSDT": Decimal("0.5")}
        if symbol not in prices:
            raise ValueError("unpriced")
        return prices[symbol]


def wallet(*balances: SpotBalance) -> WalletSnapshot:
    return WalletSnapshot(NOW, "SPOT", True, balances, "HOTUSDT")


def test_portfolio_analytics_values_nav_weights_pnl_and_concentration() -> None:
    policy = PortfolioRiskPolicy(
        Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("1000")
    )
    report = PortfolioAnalyticsService(Prices(), risk_policy=policy).evaluate(
        wallet(
            SpotBalance("HOT", Decimal("1000"), Decimal("0")),
            SpotBalance("USDT", Decimal("2"), Decimal("0")),
        ),
        average_costs_usdt={"HOT": Decimal("0.001"), "USDT": Decimal("1")},
    )

    assert report.total_value_usdt == Decimal("4")
    assert report.largest_asset == "HOT"
    assert report.largest_weight == Decimal("0.5")
    assert report.unrealized_pnl_usdt == Decimal("1")
    assert report.blockers == ("PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED",)
    assert report.execution_allowed is False


def test_portfolio_analytics_marks_unpriced_and_missing_cost_basis() -> None:
    policy = PortfolioRiskPolicy(
        Decimal("1000"), Decimal("1000"), Decimal("1000"), Decimal("1000")
    )
    report = PortfolioAnalyticsService(Prices(), risk_policy=policy).evaluate(
        wallet(
            SpotBalance("HOT", Decimal("100"), Decimal("0")),
            SpotBalance("UNKNOWN", Decimal("5"), Decimal("0")),
        )
    )

    assert report.unpriced_assets == ("UNKNOWN",)
    assert report.unrealized_pnl_usdt is None
    assert "PORTFOLIO_UNPRICED_ASSETS" in report.blockers
    assert "PORTFOLIO_COST_BASIS_UNAVAILABLE" in report.blockers


def test_portfolio_analytics_rejects_invalid_policy_and_cost() -> None:
    with pytest.raises(ValueError, match="concentration"):
        PortfolioAnalyticsService(Prices(), Decimal("0"))
    with pytest.raises(ValueError, match="average cost"):
        PortfolioAnalyticsService(Prices()).evaluate(
            wallet(SpotBalance("HOT", Decimal("1"), Decimal("0"))),
            average_costs_usdt={"HOT": Decimal("NaN")},
        )
    with pytest.raises(ValueError, match="average cost"):
        PortfolioAnalyticsService(Prices()).evaluate(
            wallet(SpotBalance("HOT", Decimal("1"), Decimal("0"))),
            average_costs_usdt=cast(Mapping[str, Decimal], {"HOT": "bad"}),
        )


def test_portfolio_analytics_models_fail_closed_on_invalid_invariants() -> None:
    with pytest.raises(ValueError, match="valued Spot"):
        ValuedSpotAsset("", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError, match="cost and PnL"):
        ValuedSpotAsset(
            "HOT",
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            average_cost_usdt=Decimal("NaN"),
        )
    with pytest.raises(ValueError, match="portfolio analytics is invalid"):
        PortfolioAnalytics(Decimal("-1"), (), (), None, Decimal("0"), None, ())
    with pytest.raises(ValueError, match="cannot grant execution"):
        PortfolioAnalytics(
            Decimal("0"), (), (), None, Decimal("0"), None, (), execution_allowed=True
        )
    with pytest.raises(ValueError, match="portfolio assessment"):
        PortfolioRiskAssessment("", Decimal("0"), False, ())
    with pytest.raises(ValueError, match="approved proposal"):
        PortfolioRiskAssessment("HOTUSDT", Decimal("1"), True, ("BLOCKED",))
    with pytest.raises(ValueError, match="cannot authorize"):
        PortfolioRiskAssessment("HOTUSDT", Decimal("1"), False, (), True)


def test_portfolio_analytics_skips_zero_balance_and_zero_price() -> None:
    empty = PortfolioAnalyticsService(Prices()).evaluate(
        wallet(SpotBalance("HOT", Decimal("0"), Decimal("0")))
    )
    assert empty.valued_assets == ()

    class ZeroPrice:
        def ticker_price(self, symbol: str) -> Decimal:
            return Decimal("0")

    report = PortfolioAnalyticsService(ZeroPrice()).evaluate(
        wallet(SpotBalance("HOT", Decimal("1"), Decimal("0")))
    )
    assert report.unpriced_assets == ("HOT",)

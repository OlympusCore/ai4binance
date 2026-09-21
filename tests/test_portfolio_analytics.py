"""Read-only portfolio valuation and concentration tests."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from ai4binance.portfolio.analytics import (
    FallbackSpotPriceReader,
    PortfolioAnalytics,
    PortfolioAnalyticsService,
    ValuedSpotAsset,
)
from ai4binance.portfolio.asset_policy import (
    AssetClassification,
    AssetClassificationRecord,
    AssetClassifier,
    AssetPolicy,
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


def test_portfolio_analytics_keeps_cash_in_nav_but_out_of_position_risk() -> None:
    report = PortfolioAnalyticsService(Prices()).evaluate(
        wallet(
            SpotBalance("USDT", Decimal("1000"), Decimal("0")),
            SpotBalance("USDC", Decimal("500"), Decimal("0")),
            SpotBalance("FDUSD", Decimal("250"), Decimal("0")),
        )
    )

    assert report.total_value_usdt == Decimal("1750")
    assert report.largest_asset == "USDT"
    assert report.largest_weight == Decimal("1000") / Decimal("1750")
    assert report.unrealized_pnl_usdt == Decimal("0")
    assert report.blockers == ()
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_portfolio_analytics_preserves_non_cash_risk_vetoes() -> None:
    report = PortfolioAnalyticsService(Prices()).evaluate(
        wallet(
            SpotBalance("HOT", Decimal("300000"), Decimal("0")),
            SpotBalance("USDT", Decimal("1000"), Decimal("0")),
        ),
        average_costs_usdt={"HOT": Decimal("0.001")},
    )

    assert report.total_value_usdt == Decimal("1600")
    assert "PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED" not in report.blockers
    assert "PORTFOLIO_GROSS_LIMIT_EXCEEDED" in report.blockers
    assert "SYMBOL_EXPOSURE_LIMIT_EXCEEDED" in report.blockers
    assert "CORRELATION_GROUP_LIMIT_EXCEEDED" in report.blockers
    assert "STRATEGY_EXPOSURE_LIMIT_EXCEEDED" in report.blockers
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


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


def test_wallet_price_coverage_falls_back_to_the_top_volume_snapshot() -> None:
    class WalletCoverage:
        def ticker_price(self, symbol: str) -> Decimal:
            if symbol == "HOTUSDT":
                return Decimal("0.0012")
            raise ValueError("wallet price is unavailable")

    reader = FallbackSpotPriceReader(WalletCoverage(), Prices())

    assert reader.ticker_price("HOTUSDT") == Decimal("0.0012")
    assert reader.ticker_price("XRPUSDT") == Decimal("0.5")


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


def test_asset_policy_normalizes_and_rejects_invalid_inputs() -> None:
    policy = AssetPolicy(
        protected_assets=(" hot ", "HOT"),
        fee_reserve_assets=("bnb",),
        preferred_quote_assets=("usdt",),
    )

    assert policy.protected_assets == ("HOT",)
    assert policy.fee_reserve_assets == ("BNB",)
    assert policy.preferred_quote_assets == ("USDT",)
    assert policy.is_protected("hot") is True
    assert policy.is_quote_asset("usdt") is True
    with pytest.raises(ValueError, match="preferred_quote_assets"):
        AssetPolicy(preferred_quote_assets=())
    with pytest.raises(ValueError, match="dust_value_threshold"):
        AssetPolicy(dust_value_threshold_usdt=Decimal("-1"))
    with pytest.raises(ValueError, match="alphanumeric"):
        AssetPolicy(protected_assets=("bad-asset",))


def test_asset_classifier_covers_spot_balance_states() -> None:
    policy = AssetPolicy(
        protected_assets=("HOT",),
        automatic_conversion_enabled=True,
    )
    classifier = AssetClassifier(policy)

    protected = classifier.classify_spot_balance(
        SpotBalance("HOT", Decimal("10"), Decimal("0")),
        prices_usdt={"HOT": Decimal("1")},
    )
    fee = classifier.classify_spot_balance(
        SpotBalance("BNB", Decimal("1"), Decimal("0"))
    )
    quote = classifier.classify_spot_balance(
        SpotBalance("USDT", Decimal("10"), Decimal("1"))
    )
    locked = classifier.classify_spot_balance(
        SpotBalance("ABC", Decimal("0"), Decimal("2")),
        prices_usdt={"ABC": Decimal("3")},
    )
    unsupported = classifier.classify_spot_balance(
        SpotBalance("ABC", Decimal("2"), Decimal("0"))
    )
    dust = classifier.classify_spot_balance(
        SpotBalance("ABC", Decimal("1"), Decimal("0")),
        prices_usdt={"ABC": Decimal("1")},
    )
    convertible = classifier.classify_spot_balance(
        SpotBalance("ABC", Decimal("10"), Decimal("0")),
        prices_usdt={"ABC": Decimal("1")},
    )

    assert protected.classification is AssetClassification.PROTECTED_POSITION
    assert fee.classification is AssetClassification.FEE_RESERVE
    assert quote.classification is AssetClassification.CASH_EQUIVALENT
    assert quote.available_for_new_spot_notional == Decimal("10")
    assert quote.funding_eligible is True
    assert locked.classification is AssetClassification.LOCKED
    assert unsupported.classification is AssetClassification.UNSUPPORTED
    assert dust.classification is AssetClassification.DUST
    assert convertible.classification is AssetClassification.CONVERTIBLE
    assert convertible.funding_eligible is True
    assert (
        len(
            classifier.classify_spot_balances(
                (
                    SpotBalance("USDT", Decimal("1"), Decimal("0")),
                    SpotBalance("ABC", Decimal("1"), Decimal("0")),
                ),
                prices_usdt={"ABC": Decimal("6")},
            )
        )
        == 2
    )


def test_asset_classification_record_and_prices_fail_closed() -> None:
    with pytest.raises(ValueError, match="identity"):
        AssetClassificationRecord(
            "",
            AssetClassification.DUST,
            "reason",
            Decimal("0"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        AssetClassificationRecord(
            "HOT",
            AssetClassification.DUST,
            "reason",
            Decimal("-1"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="estimated_value"):
        AssetClassificationRecord(
            "HOT",
            AssetClassification.DUST,
            "reason",
            Decimal("0"),
            Decimal("0"),
            Decimal("NaN"),
        )
    with pytest.raises(ValueError, match="protected assets"):
        AssetClassificationRecord(
            "HOT",
            AssetClassification.PROTECTED_POSITION,
            "reason",
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            funding_eligible=True,
        )
    with pytest.raises(ValueError, match="asset prices"):
        AssetClassifier().classify_spot_balance(
            SpotBalance("HOT", Decimal("1"), Decimal("0")),
            prices_usdt={"HOT": Decimal("-1")},
        )

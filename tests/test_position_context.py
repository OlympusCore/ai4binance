from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai4binance.portfolio.asset_policy import AssetPolicy
from ai4binance.portfolio.futures import FuturesAccountSnapshot, FuturesPosition
from ai4binance.portfolio.position_context import (
    CapitalSourceStatus,
    PositionContextBuilder,
    PositionContextRecord,
    PositionContextReport,
    PositionMarket,
    PositionSide,
)
from ai4binance.portfolio.wallet import SpotBalance, WalletSnapshot

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def test_position_context_is_coin_agnostic_and_blocks_attachment_bias() -> None:
    wallet = WalletSnapshot(
        NOW,
        "SPOT",
        True,
        (
            SpotBalance("HOT", Decimal("1000"), Decimal("0")),
            SpotBalance("USDT", Decimal("25"), Decimal("0")),
        ),
        "ETHUSDT",
    )

    report = PositionContextBuilder(AssetPolicy(protected_assets=("HOT",))).build(
        spot_wallet=wallet,
        prices_usdt={"HOT": Decimal("0.001")},
    )

    assert {record.asset for record in report.records} == {"HOT", "USDT"}
    hot = next(record for record in report.records if record.asset == "HOT")
    usdt = next(record for record in report.records if record.asset == "USDT")
    assert hot.market is PositionMarket.SPOT
    assert hot.side is PositionSide.LONG
    assert hot.capital_source_status is CapitalSourceStatus.PROTECTED_REVIEW_REQUIRED
    assert "COIN_ATTACHMENT_BIAS_BLOCKED" in hot.blockers
    assert "POSITION_IS_CONTEXT_NOT_THESIS" in hot.blockers
    assert usdt.capital_source_status is CapitalSourceStatus.AVAILABLE_CASH
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_position_context_reports_missing_wallet_without_fabricating_positions() -> (
    None
):
    report = PositionContextBuilder().build(spot_wallet=None)

    assert report.records == ()
    assert report.blockers == (
        "SPOT_WALLET_CONTEXT_UNAVAILABLE",
        "POSITION_CONTEXT_EMPTY",
    )
    assert report.promotion_status == "RESEARCH_ONLY"


def test_position_context_reports_reviewable_unpriced_locked_and_futures_paths() -> (
    None
):
    wallet = WalletSnapshot(
        NOW,
        "SPOT",
        True,
        (
            SpotBalance("ADA", Decimal("10"), Decimal("1")),
            SpotBalance("SOL", Decimal("2"), Decimal("0")),
            SpotBalance("ZERO", Decimal("0"), Decimal("0")),
        ),
        "ADAUSDT",
    )
    futures = FuturesAccountSnapshot(
        NOW,
        "BTCUSDT",
        True,
        Decimal("100"),
        Decimal("50"),
        (
            FuturesPosition(
                symbol="ETHUSDT",
                quantity=Decimal("-0.5"),
                entry_price=Decimal("3000"),
                unrealized_pnl=Decimal("-10"),
                mark_price=None,
                liquidation_price=None,
                leverage=None,
                notional=None,
            ),
            FuturesPosition(
                symbol="BTCUSDT",
                quantity=Decimal("0"),
                entry_price=Decimal("60000"),
                unrealized_pnl=Decimal("0"),
            ),
        ),
    )

    report = PositionContextBuilder().build(
        spot_wallet=wallet,
        futures_account=futures,
        prices_usdt={"ADA": Decimal("0.50")},
    )

    ada = next(record for record in report.records if record.asset == "ADA")
    sol = next(record for record in report.records if record.asset == "SOL")
    eth = next(record for record in report.records if record.asset == "ETH")

    assert ada.capital_source_status is CapitalSourceStatus.REVIEWABLE_POSITION
    assert ada.locked_quantity == Decimal("1")
    assert "LOCKED_BALANCE_PRESENT" in ada.blockers
    assert "MANUAL_CAPITAL_RELEASE_REVIEW_REQUIRED" in ada.blockers
    assert sol.notional_usdt is None
    assert "POSITION_USDT_VALUATION_UNAVAILABLE" in sol.blockers
    assert eth.market is PositionMarket.USD_M_FUTURES
    assert eth.side is PositionSide.SHORT
    assert "MARK_PRICE_UNAVAILABLE" in eth.blockers
    assert "LIQUIDATION_PRICE_UNAVAILABLE" in eth.blockers
    assert "LEVERAGE_UNAVAILABLE" in eth.blockers


def test_position_context_rejects_invalid_prices_and_authority() -> None:
    wallet = WalletSnapshot(
        NOW,
        "SPOT",
        True,
        (SpotBalance("ADA", Decimal("10"), Decimal("0")),),
        "ADAUSDT",
    )

    for value in (Decimal("-1"), Decimal("NaN")):
        with pytest.raises(ValueError, match="prices must be finite"):
            PositionContextBuilder().build(
                spot_wallet=wallet,
                prices_usdt={"ADA": value},
            )

    with pytest.raises(ValueError, match="asset is required"):
        PositionContextRecord(
            asset=" ",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            available_quantity=Decimal("0"),
        )
    with pytest.raises(ValueError, match="quantities cannot be negative"):
        PositionContextRecord(
            asset="ADA",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("-1"),
            available_quantity=Decimal("0"),
        )
    with pytest.raises(ValueError, match="locked quantity cannot be negative"):
        PositionContextRecord(
            asset="ADA",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            available_quantity=Decimal("1"),
            locked_quantity=Decimal("-1"),
        )
    with pytest.raises(ValueError, match="notional must be non-negative"):
        PositionContextRecord(
            asset="ADA",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            available_quantity=Decimal("1"),
            notional_usdt=Decimal("NaN"),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        PositionContextRecord(
            asset="ADA",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            available_quantity=Decimal("1"),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="blockers must be unique"):
        PositionContextRecord(
            asset="ADA",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            available_quantity=Decimal("1"),
            blockers=("dup", "dup"),
        )
    with pytest.raises(ValueError, match="evidence refs cannot contain blanks"):
        PositionContextRecord(
            asset="ADA",
            market=PositionMarket.SPOT,
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            available_quantity=Decimal("1"),
            evidence_refs=(" ",),
        )
    with pytest.raises(ValueError, match="between zero and one"):
        PositionContextReport(
            records=(),
            blockers=(),
            concentration_ratio=Decimal("1.1"),
        )
    with pytest.raises(ValueError, match="cannot promote or execute"):
        PositionContextReport(
            records=(),
            blockers=(),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="quote asset must be alphanumeric"):
        PositionContextBuilder(quote_asset="USDT-TEST")

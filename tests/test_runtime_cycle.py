# ruff: noqa: RUF001
"""Wallet-first dual-market runtime regression tests."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from test_cli import public_snapshot

from ai4binance.application.runtime import (
    DualMarketAdvisoryReport,
    MarketAdvisory,
    ReadOnlyRuntimeCycle,
    RuntimeState,
)
from ai4binance.portfolio import (
    CostBasisService,
    FuturesAccountSnapshotService,
    PortfolioAnalyticsService,
    WalletSnapshotService,
)
from ai4binance.schemas import MarketSnapshot
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

NOW = datetime(2026, 7, 14, tzinfo=UTC)


class SpotWalletReader:
    def account(self) -> object:
        return {
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": "HOT", "free": "10", "locked": "0"},
                {"asset": "USDT", "free": "100", "locked": "0"},
            ],
        }

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return []


class FuturesReader:
    def account(self) -> object:
        return {
            "canTrade": True,
            "totalWalletBalance": "100",
            "availableBalance": "90",
        }

    def positions(self, symbol: str | None = None) -> object:
        return [
            {
                "symbol": symbol,
                "positionAmt": "0",
                "entryPrice": "0",
                "unRealizedProfit": "0",
            }
        ]

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol == "HOTUSDT"
        return []


class DerivativesCollectorStub:
    def collect(
        self, symbol: str, period: str = "1h", limit: int = 100
    ) -> DerivativesDataset:
        assert (symbol, period, limit) == ("HOTUSDT", "1h", 100)
        provenance = Provenance("TEST", NOW, "https://example.test")
        points = tuple(
            MetricPoint(
                DerivativesMetric.OPEN_INTEREST,
                datetime(2026, 7, 14, hour=index, tzinfo=UTC),
                Decimal(100 + index),
                provenance,
            )
            for index in range(5)
        )
        series: Mapping[DerivativesMetric, tuple[MetricPoint, ...]] = {
            DerivativesMetric.OPEN_INTEREST: points
        }
        return DerivativesDataset(symbol, NOW, series)


class RecordingAcquisition:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        self.calls.append((symbol, timeframes))
        return public_snapshot()


def cycle(
    *, with_spot_wallet: bool = True, with_futures_wallet: bool = True
) -> ReadOnlyRuntimeCycle:
    return ReadOnlyRuntimeCycle(
        symbol="HOTUSDT",
        timeframes=("15m", "1h", "4h", "1d"),
        spot_acquirer=RecordingAcquisition(),
        spot_wallet_service=(
            WalletSnapshotService(SpotWalletReader()) if with_spot_wallet else None
        ),
        futures_account_service=(
            FuturesAccountSnapshotService(FuturesReader())
            if with_futures_wallet
            else None
        ),
        derivatives_collector=DerivativesCollectorStub(),
    )


def test_runtime_runs_wallet_preflight_and_dual_market_advisory() -> None:
    report = cycle().run(NOW)

    assert report.state is RuntimeState.DEGRADED
    assert report.spot.wallet_status == "READY"
    assert report.futures.wallet_status == "READY"
    assert report.futures.action == "NO_TRADE"
    assert report.futures.bias == "NEUTRAL"
    assert report.blockers == (
        "OI_OR_PRICE_HISTORY_INSUFFICIENT",
        "FUTURES_OOS_NOT_APPROVED",
    )
    assert report.spot_wallet is not None
    assert report.futures_account is not None
    assert report.investment_management is not None
    assert report.investment_management.execution_allowed is False
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runtime_blocks_market_calls_when_wallet_preflight_is_incomplete() -> None:
    acquisition = RecordingAcquisition()
    runtime = ReadOnlyRuntimeCycle(
        symbol="HOTUSDT",
        timeframes=("1h",),
        spot_acquirer=acquisition,
        spot_wallet_service=None,
        futures_account_service=None,
        derivatives_collector=DerivativesCollectorStub(),
    )

    report = runtime.run(NOW)

    assert report.state is RuntimeState.DEGRADED
    assert report.spot.action == "NO_TRADE"
    assert report.futures.action == "NO_TRADE"
    assert report.blockers == (
        "SPOT_WALLET_SERVICE_UNAVAILABLE",
        "FUTURES_ACCOUNT_SERVICE_UNAVAILABLE",
    )
    assert acquisition.calls == []


def test_futures_account_parser_keeps_signed_position_quantity() -> None:
    snapshot = FuturesAccountSnapshotService(FuturesReader()).capture("hotusdt", NOW)
    assert snapshot.symbol == "HOTUSDT"
    assert snapshot.total_wallet_balance == Decimal("100")
    assert snapshot.available_balance == Decimal("90")
    assert snapshot.positions[0].quantity == Decimal("0")
    assert snapshot.open_order_count == 0


class DeliveryFuturesReader(FuturesReader):
    def positions(self, symbol: str | None = None) -> object:
        assert symbol is None
        return [
            {
                "symbol": "BTCUSD_260925",
                "positionAmt": "-2",
                "entryPrice": "65000",
                "unRealizedProfit": "12.5",
                "markPrice": "64950",
                "liquidationPrice": "72000",
                "leverage": "5",
                "marginType": "isolated",
                "notional": "-129900",
                "isolatedMargin": "30000",
            }
        ]

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol is None
        return []


def test_futures_account_accepts_delivery_symbol_and_captures_risk_fields() -> None:
    snapshot = FuturesAccountSnapshotService(DeliveryFuturesReader()).capture(
        "btcusd_260925", NOW
    )

    position = snapshot.positions[0]
    assert snapshot.symbol == "BTCUSD_260925"
    assert position.symbol == "BTCUSD_260925"
    assert position.mark_price == Decimal("64950")
    assert position.liquidation_price == Decimal("72000")
    assert position.leverage == 5
    assert position.margin_type == "ISOLATED"
    assert position.notional == Decimal("-129900")
    assert position.isolated_margin == Decimal("30000")


def _legacy_unicode_contract_fixture() -> None:
    assert FuturesAccountSnapshotService._symbol("å¸å®äººçusdt") == "å¸å®äººçUSDT"


def test_futures_account_accepts_unicode_contract_response() -> None:
    symbol = "\u5e01\u5b89\u4eba\u751fusdt"
    assert FuturesAccountSnapshotService._symbol(symbol) == (
        "\u5e01\u5b89\u4eba\u751fUSDT"
    )


class AccountWideSpotReader(SpotWalletReader):
    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol is None
        return []


class AccountWideFuturesReader(FuturesReader):
    def positions(self, symbol: str | None = None) -> object:
        assert symbol is None
        return [
            {
                "symbol": "HOTUSDT",
                "positionAmt": "5",
                "entryPrice": "0.001",
                "unRealizedProfit": "1",
            },
            {
                "symbol": "BTCUSDT",
                "positionAmt": "-0.01",
                "entryPrice": "60000",
                "unRealizedProfit": "-5",
            },
        ]

    def open_orders(self, symbol: str | None = None) -> object:
        assert symbol is None
        return []


def test_runtime_account_wide_monitoring_keeps_all_positions() -> None:
    runtime = ReadOnlyRuntimeCycle(
        symbol="HOTUSDT",
        timeframes=("1h",),
        spot_acquirer=RecordingAcquisition(),
        spot_wallet_service=WalletSnapshotService(AccountWideSpotReader()),
        futures_account_service=FuturesAccountSnapshotService(
            AccountWideFuturesReader()
        ),
        derivatives_collector=DerivativesCollectorStub(),
        account_wide_monitoring=True,
    )

    report = runtime.run(NOW)

    assert report.futures_account is not None
    assert {item.symbol for item in report.futures_account.positions} == {
        "HOTUSDT",
        "BTCUSDT",
    }
    assert report.investment_management is not None
    subjects = {item.subject for item in report.investment_management.recommendations}
    assert "BTCUSDT_SHORT" in subjects
    assert "USDT_INVENTORY" in subjects
    btc = next(
        item
        for item in report.investment_management.recommendations
        if item.subject == "BTCUSDT_SHORT"
    )
    assert btc.action.value == "HOLD_REVIEW"
    assert "SYMBOL_ANALYSIS_UNAVAILABLE" in btc.blockers


def test_runtime_isolates_futures_preflight_failure_from_spot_analysis() -> None:
    report = cycle(with_futures_wallet=False).run(NOW)

    assert report.state is RuntimeState.DEGRADED
    assert report.spot.wallet_status == "READY"
    assert report.spot_research is not None
    assert report.futures.wallet_status == "BLOCKED"
    assert report.investment_management is not None
    assert any(
        item.market == "SPOT" for item in report.investment_management.recommendations
    )


def test_runtime_isolates_spot_preflight_failure_from_futures_analysis() -> None:
    report = cycle(with_spot_wallet=False).run(NOW)

    assert report.state is RuntimeState.DEGRADED
    assert report.spot.wallet_status == "BLOCKED"
    assert report.futures.wallet_status == "READY"
    assert report.futures.setup_radar
    assert report.investment_management is not None
    assert any(
        item.market == "USD_M_FUTURES"
        for item in report.investment_management.recommendations
    )


class DisabledSpotWalletReader(SpotWalletReader):
    def account(self) -> object:
        payload = super().account()
        assert isinstance(payload, dict)
        payload["canTrade"] = False
        return payload


class SpotPrices:
    def ticker_price(self, symbol: str) -> Decimal:
        assert symbol == "HOTUSDT"
        return Decimal("1")


class SpotHistory:
    def trades(
        self, symbol: str, *, from_id: int | None = None, limit: int = 1_000
    ) -> object:
        assert symbol == "HOTUSDT"
        assert from_id is None
        assert limit == 1_000
        return [
            {
                "id": 1,
                "price": "0.5",
                "qty": "10",
                "quoteQty": "5",
                "commission": "0",
                "commissionAsset": "USDT",
                "isBuyer": True,
                "time": 1,
            }
        ]


def test_runtime_attaches_read_only_cost_basis_to_portfolio_analytics() -> None:
    runtime = ReadOnlyRuntimeCycle(
        symbol="HOTUSDT",
        timeframes=("1h",),
        spot_acquirer=RecordingAcquisition(),
        spot_wallet_service=WalletSnapshotService(SpotWalletReader()),
        futures_account_service=FuturesAccountSnapshotService(FuturesReader()),
        derivatives_collector=DerivativesCollectorStub(),
        analytics_service=PortfolioAnalyticsService(SpotPrices()),
        cost_basis_service=CostBasisService(SpotHistory()),
    )
    report = runtime.run(NOW)
    assert report.cost_basis is not None
    assert report.cost_basis.average_cost_quote == Decimal("0.5")
    assert report.portfolio_analytics is not None
    hot = next(
        item for item in report.portfolio_analytics.valued_assets if item.asset == "HOT"
    )
    assert hot.average_cost_usdt == Decimal("0.5")
    assert "PORTFOLIO_COST_BASIS_UNAVAILABLE" not in report.blockers


def test_runtime_values_spot_wallet_even_when_market_cycle_is_blocked() -> None:
    runtime = ReadOnlyRuntimeCycle(
        symbol="HOTUSDT",
        timeframes=("1h",),
        spot_acquirer=RecordingAcquisition(),
        spot_wallet_service=WalletSnapshotService(DisabledSpotWalletReader()),
        futures_account_service=None,
        derivatives_collector=DerivativesCollectorStub(),
        analytics_service=PortfolioAnalyticsService(SpotPrices()),
    )

    report = runtime.run(NOW)

    assert report.state is RuntimeState.DEGRADED
    assert report.portfolio_analytics is not None
    assert report.portfolio_analytics.total_value_usdt == Decimal("110")
    assert "PORTFOLIO_COST_BASIS_UNAVAILABLE" in report.blockers
    assert report.investment_management is not None
    assert any(
        item.category == "PORTFOLIO_RISK"
        for item in report.investment_management.recommendations
    )
    assert report.portfolio_analytics.execution_allowed is False
    assert report.execution_allowed is False


def test_runtime_contracts_reject_execution_and_invalid_identity() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        MarketAdvisory("OPTIONS", "NO_TRADE", "UNKNOWN", (), (), "BLOCKED")
    with pytest.raises(ValueError, match="cannot grant"):
        MarketAdvisory(
            "SPOT", "NO_TRADE", "UNKNOWN", (), (), "READY", execution_allowed=True
        )
    advisory = MarketAdvisory("SPOT", "NO_TRADE", "UNKNOWN", (), (), "READY")
    with pytest.raises(ValueError, match="timestamp"):
        DualMarketAdvisoryReport(
            "cycle",
            "HOTUSDT",
            datetime(2026, 7, 14),
            RuntimeState.READY,
            advisory,
            advisory,
            (),
        )
    with pytest.raises(ValueError, match="cannot contain blockers"):
        DualMarketAdvisoryReport(
            "cycle",
            "HOTUSDT",
            NOW,
            RuntimeState.READY,
            advisory,
            advisory,
            ("BLOCKED",),
        )


class FailingWalletReader(SpotWalletReader):
    def account(self) -> object:
        raise RuntimeError("unavailable")


class FailingAcquisition(RecordingAcquisition):
    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        super().acquire(symbol, timeframes)
        raise RuntimeError("unavailable")


class FailingDerivativesCollector(DerivativesCollectorStub):
    def collect(
        self, symbol: str, period: str = "1h", limit: int = 100
    ) -> DerivativesDataset:
        del symbol, period, limit
        raise RuntimeError("unavailable")


def test_runtime_maps_wallet_market_and_derivatives_failures_to_blockers() -> None:
    wallet_failed = ReadOnlyRuntimeCycle(
        "HOTUSDT",
        ("1h",),
        RecordingAcquisition(),
        WalletSnapshotService(FailingWalletReader()),
        FuturesAccountSnapshotService(FuturesReader()),
        DerivativesCollectorStub(),
    ).run(NOW)
    assert "SPOT_WALLET_PREFLIGHT_FAILED" in wallet_failed.blockers

    market_failed = ReadOnlyRuntimeCycle(
        "HOTUSDT",
        ("1h",),
        FailingAcquisition(),
        WalletSnapshotService(SpotWalletReader()),
        FuturesAccountSnapshotService(FuturesReader()),
        DerivativesCollectorStub(),
    ).run(NOW)
    assert market_failed.blockers == ("SPOT_MARKET_PREFLIGHT_FAILED",)

    derivatives_failed = ReadOnlyRuntimeCycle(
        "HOTUSDT",
        ("1h",),
        RecordingAcquisition(),
        WalletSnapshotService(SpotWalletReader()),
        FuturesAccountSnapshotService(FuturesReader()),
        FailingDerivativesCollector(),
    ).run(NOW)
    assert derivatives_failed.futures.blockers == ("FUTURES_PUBLIC_DATA_FAILED",)


def test_runtime_rejects_naive_cycle_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        cycle().run(datetime(2026, 7, 14))

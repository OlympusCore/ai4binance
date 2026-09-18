from __future__ import annotations

from datetime import UTC, datetime

from ai4binance.external_intel.core.enums import AssetClass
from ai4binance.external_intel.universe.classifier import classify_asset
from ai4binance.external_intel.universe.snapshot import build_universe_snapshot


def test_universe_classifies_hot_as_eligible_and_stable_base_as_excluded() -> None:
    hot = classify_asset("HOT", spot_symbols=("HOTUSDT",))
    usdt = classify_asset("USDT", spot_symbols=("USDTFDUSD",))

    assert hot.eligible_for_opportunity_scan is True
    assert hot.asset_class is AssetClass.ELIGIBLE_COIN
    assert usdt.eligible_for_opportunity_scan is False
    assert "STABLECOIN_BASE_ASSET" in usdt.exclusion_reasons


def test_universe_excludes_wrapped_and_leveraged_assets() -> None:
    wrapped = classify_asset(
        "WBTC",
        spot_symbols=("WBTCUSDT",),
        metadata_name="Wrapped Bitcoin",
    )
    leveraged = classify_asset("ETHUP", spot_symbols=("ETHUPUSDT",))

    assert wrapped.asset_class is AssetClass.WRAPPED_ASSET
    assert "WRAPPED_ASSET" in wrapped.exclusion_reasons
    assert leveraged.asset_class is AssetClass.LEVERAGED_ASSET
    assert "LEVERAGED_TOKEN" in leveraged.exclusion_reasons


def test_uncertain_wrapped_prefix_requires_manual_review() -> None:
    asset = classify_asset("WILD", spot_symbols=("WILDUSDT",))

    assert asset.asset_class is AssetClass.UNKNOWN
    assert "ASSET_CLASSIFICATION_UNCERTAIN" in asset.exclusion_reasons
    assert "MANUAL_REVIEW_REQUIRED" in asset.exclusion_reasons


def test_universe_snapshot_is_research_only() -> None:
    snapshot = build_universe_snapshot(
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        assets=(classify_asset("HOT", spot_symbols=("HOTUSDT",)),),
    )

    assert snapshot.execution_allowed is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"

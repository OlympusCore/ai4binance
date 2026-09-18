"""Asset classification for EIEF opportunity scans."""

from __future__ import annotations

from ai4binance.domain.universe import classify_asset_eligibility
from ai4binance.external_intel.core.enums import AssetClass
from ai4binance.external_intel.core.models import EligibleAsset


def classify_asset(
    asset: str,
    *,
    spot_symbols: tuple[str, ...] = (),
    futures_symbols: tuple[str, ...] = (),
    metadata_name: str = "",
    liquidity_ok: bool = True,
    data_quality_ok: bool = True,
) -> EligibleAsset:
    classification = classify_asset_eligibility(
        asset,
        spot_symbols=spot_symbols,
        futures_symbols=futures_symbols,
        metadata_name=metadata_name,
        liquidity_ok=liquidity_ok,
        data_quality_ok=data_quality_ok,
    )
    return EligibleAsset(
        asset=classification.asset,
        asset_class=AssetClass(classification.asset_class),
        spot_symbols=classification.spot_symbols,
        futures_symbols=classification.futures_symbols,
        eligible_for_opportunity_scan=classification.eligible,
        exclusion_reasons=classification.exclusion_reasons,
        classification_confidence=classification.confidence,
    )

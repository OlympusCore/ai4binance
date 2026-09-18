"""Build EIEF universe snapshots from classified assets."""

from __future__ import annotations

from datetime import datetime

from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.models import EligibleAsset, UniverseSnapshot


def build_universe_snapshot(
    *,
    observed_at: datetime,
    assets: tuple[EligibleAsset, ...],
) -> UniverseSnapshot:
    material = tuple(sorted(asset.asset for asset in assets))
    blockers = tuple(
        dict.fromkeys(
            reason
            for asset in assets
            for reason in asset.exclusion_reasons
            if reason in {"ASSET_CLASSIFICATION_UNCERTAIN", "MANUAL_REVIEW_REQUIRED"}
        )
    )
    return UniverseSnapshot(
        snapshot_id=eief_id("universe", observed_at.isoformat(), *material),
        observed_at=observed_at,
        assets=tuple(sorted(assets, key=lambda item: item.asset)),
        blockers=blockers,
    )

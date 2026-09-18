"""Regression tests for the canonical local-observability migration."""

from pathlib import Path
from typing import cast

from ai4binance.infrastructure.observability import LocalObserver
from ai4binance.infrastructure.observability.local import (
    LocalObserver as CanonicalLocalObserver,
)
from ai4binance.observability import LocalObserver as LegacyPackageLocalObserver
from ai4binance.observability.local import LocalObserver as LegacyModuleLocalObserver
from ai4binance.ops.kaizen_quality import build_architecture_baseline

ROOT = Path(__file__).resolve().parents[1]


def test_local_observer_facades_preserve_public_identity() -> None:
    assert LocalObserver is CanonicalLocalObserver
    assert LegacyPackageLocalObserver is CanonicalLocalObserver
    assert LegacyModuleLocalObserver is CanonicalLocalObserver


def test_local_observability_migration_is_recorded_as_canonical_and_facade() -> None:
    payload = build_architecture_baseline(ROOT).to_payload()
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    by_path = {cast(str, item["source_path"]): item for item in ledger}

    for leaf in ("__init__.py", "local.py"):
        target = f"src/ai4binance/infrastructure/observability/{leaf}"
        canonical = by_path[target]
        assert canonical["classification"] == "KEEP"
        assert canonical["confidence"] == "HIGH"
        assert canonical["blockers"] == []

        facade = by_path[f"src/ai4binance/observability/{leaf}"]
        assert facade["classification"] == "FACADE"
        assert facade["target_paths"] == [target]
        assert facade["execution_allowed"] is False
        assert facade["promotion_status"] == "RESEARCH_ONLY"
        assert facade["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

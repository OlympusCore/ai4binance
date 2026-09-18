"""Regression tests for the canonical market-identifier migration."""

from pathlib import Path
from typing import cast

from ai4binance.domain.market.markets import CapitalMarket
from ai4binance.markets import CapitalMarket as LegacyCapitalMarket
from ai4binance.ops.kaizen_quality import build_architecture_baseline

ROOT = Path(__file__).resolve().parents[1]


def test_market_identifier_facade_preserves_public_identity() -> None:
    assert LegacyCapitalMarket is CapitalMarket
    assert tuple(CapitalMarket) == (
        CapitalMarket.SPOT,
        CapitalMarket.USD_M_FUTURES,
    )


def test_market_identifier_migration_is_recorded_as_canonical_and_facade() -> None:
    payload = build_architecture_baseline(ROOT).to_payload()
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    by_path = {cast(str, item["source_path"]): item for item in ledger}

    canonical = by_path["src/ai4binance/domain/market/markets.py"]
    assert canonical["classification"] == "KEEP"
    assert canonical["confidence"] == "HIGH"
    assert canonical["blockers"] == []

    facade = by_path["src/ai4binance/markets.py"]
    assert facade["classification"] == "FACADE"
    assert facade["target_paths"] == ["src/ai4binance/domain/market/markets.py"]
    assert facade["execution_allowed"] is False
    assert facade["promotion_status"] == "RESEARCH_ONLY"
    assert facade["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

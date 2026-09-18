from __future__ import annotations

from pathlib import Path

import ai4binance.application as public_application
import ai4binance.application.orchestration.whale_fusion as canonical_whale_fusion
import ai4binance.application.whale_fusion as legacy_whale_fusion

ROOT = Path(__file__).resolve().parents[1]


def test_whale_fusion_legacy_and_public_exports_preserve_canonical_identity() -> None:
    public_symbols = (
        "WhaleFusionCycle",
        "WhaleFusionResearchService",
        "WhaleFusionWorkflowResult",
    )

    for symbol in public_symbols:
        canonical = getattr(canonical_whale_fusion, symbol)
        assert getattr(legacy_whale_fusion, symbol) is canonical
        assert getattr(public_application, symbol) is canonical
        assert canonical.__module__ == (
            "ai4binance.application.orchestration.whale_fusion"
        )


def test_architecture_rule_owns_whale_fusion_placement_and_migration_ledger() -> None:
    architecture = (
        ROOT / "docs" / "architecture" / "framework_architecture_overview.md"
    ).read_text(encoding="utf-8")

    assert (
        "`application/orchestration/whale_fusion.py`: canonical cycle" in architecture
    )
    assert (
        "`application/whale_fusion.py` remains an identity-preserving" in architecture
    )
    assert "`ops/architecture_migration.py`: evidence-only migration" in architecture

"""Regression tests for the canonical runtime-artifact layout migration."""

from pathlib import Path
from typing import cast

from ai4binance.infrastructure.filesystem.runtime_artifacts import (
    RuntimeArtifactLayoutManifest,
    default_runtime_artifact_layout_manifest_path,
    load_runtime_artifact_layout_manifest,
)
from ai4binance.infrastructure.filesystem.runtime_artifacts.layout import (
    RuntimeArtifactLayoutManifest as CanonicalLayoutManifest,
)
from ai4binance.ops.kaizen_quality import build_architecture_baseline
from ai4binance.runtime_artifacts import (
    RuntimeArtifactLayoutManifest as LegacyPackageLayoutManifest,
)
from ai4binance.runtime_artifacts import (
    default_runtime_artifact_layout_manifest_path as legacy_default_manifest_path,
)
from ai4binance.runtime_artifacts import (
    load_runtime_artifact_layout_manifest as legacy_load_manifest,
)
from ai4binance.runtime_artifacts.layout import (
    RuntimeArtifactLayoutManifest as LegacyModuleLayoutManifest,
)

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_artifact_facades_preserve_public_identity() -> None:
    assert RuntimeArtifactLayoutManifest is CanonicalLayoutManifest
    assert LegacyPackageLayoutManifest is CanonicalLayoutManifest
    assert LegacyModuleLayoutManifest is CanonicalLayoutManifest
    assert legacy_default_manifest_path is default_runtime_artifact_layout_manifest_path
    assert legacy_load_manifest is load_runtime_artifact_layout_manifest


def test_runtime_artifact_migration_is_recorded_as_canonical_and_facade() -> None:
    payload = build_architecture_baseline(ROOT).to_payload()
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    by_path = {cast(str, item["source_path"]): item for item in ledger}

    for leaf in ("__init__.py", "layout.py"):
        canonical_path = (
            "src/ai4binance/infrastructure/filesystem/runtime_artifacts/" + leaf
        )
        canonical = by_path[canonical_path]
        assert canonical["classification"] == "KEEP"
        assert canonical["confidence"] == "HIGH"
        assert canonical["blockers"] == []

        facade = by_path[f"src/ai4binance/runtime_artifacts/{leaf}"]
        assert facade["classification"] == "FACADE"
        assert facade["target_paths"] == [canonical_path]
        assert facade["execution_allowed"] is False
        assert facade["promotion_status"] == "RESEARCH_ONLY"
        assert facade["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

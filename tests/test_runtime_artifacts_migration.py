"""Regression tests for the canonical runtime-artifact layout migration."""

import json
from pathlib import Path
from typing import cast

import pytest

from ai4binance.infrastructure.filesystem.runtime_artifacts import (
    RuntimeArtifactLayoutManifest,
    default_runtime_artifact_layout_manifest_path,
    layout,
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


def test_layout_contract_helpers_fail_closed_and_canonicalize_aliases(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="under runtime"):
        layout.RuntimeRetentionPolicy("outside", "keep", 0, 0, False)
    manifest = CanonicalLayoutManifest(
        "runtime/artifacts",
        "runtime",
        {"evidence": "runtime/artifacts/evidence"},
        {"runtime/old": "runtime/artifacts/new", "runtime": "runtime/artifacts"},
    )
    assert (
        manifest.canonicalize_uri(" runtime/old/item ") == "runtime/artifacts/new/item"
    )
    with pytest.raises(ValueError, match="unknown runtime artifact root"):
        manifest.root_for("unknown")
    with pytest.raises(ValueError, match="unknown runtime retention"):
        manifest.retention_for("unknown")
    assert layout._capacity_budget_mapping(None) == {}
    capacity_values: tuple[object, ...] = (
        [],
        {"outside": 1},
        {"runtime/a": True},
        {"runtime/a": 0},
    )
    for value in capacity_values:
        with pytest.raises(
            ValueError,
            match=(
                r"(capacity_budgets must be an object|runtime paths|"
                r"must be an integer|must be positive)"
            ),
        ):
            layout._capacity_budget_mapping(value)
    retention_values: tuple[object, ...] = (None, [], {"x": {}})
    for value in retention_values:
        if value is None:
            assert layout._retention_mapping(value) == {}
        else:
            with pytest.raises(
                ValueError,
                match=(
                    r"(retention must be an object|"
                    r"automatic_cleanup must be boolean)"
                ),
            ):
                layout._retention_mapping(value)

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema version"):
        load_runtime_artifact_layout_manifest(path)
    loaded = load_runtime_artifact_layout_manifest()
    assert loaded.retention
    assert loaded.capacity_budgets


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (("runtime/a", "", 0, 0, False), "cleanup mode"),
        (("runtime/a", "keep", -1, 0, False), "bounds"),
        (("runtime/a", "keep", 0, 0, False, "file"), "entry kind"),
    ],
)
def test_runtime_retention_policy_rejects_invalid_values(
    policy: tuple[object, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        layout.RuntimeRetentionPolicy(*policy)  # type: ignore[arg-type]


def test_layout_mapping_helpers_cover_all_invalid_contract_shapes() -> None:
    text_mapping_values: tuple[object, ...] = (
        None,
        [],
        {},
        {"": "runtime/a"},
        {"a": ""},
    )
    for value in text_mapping_values:
        with pytest.raises(
            ValueError,
            match=r"roots must be (a non-empty object|contain non-empty strings)",
        ):
            layout._text_mapping(value, "roots")
    with pytest.raises(ValueError, match="canonical_root must be a non-empty string"):
        layout._text({}, "canonical_root")
    invalid_retention_values: tuple[object, ...] = (
        {"rule": []},
        {"": {}},
        {"rule": {"automatic_cleanup": "yes"}},
    )
    for value in invalid_retention_values:
        with pytest.raises(
            ValueError,
            match=(
                r"(retention entries must be named objects|"
                r"automatic_cleanup must be boolean)"
            ),
        ):
            layout._retention_mapping(value)
    for policy in (
        {"automatic_cleanup": True, "minimum_age_days": True, "keep_latest": 0},
        {"automatic_cleanup": True, "minimum_age_days": 0, "keep_latest": False},
    ):
        with pytest.raises(
            ValueError,
            match=(
                r"(minimum_age_days must be an integer|"
                r"keep_latest must be an integer)"
            ),
        ):
            layout._retention_mapping({"rule": policy})
    with pytest.raises(ValueError, match="entry kind is invalid"):
        layout._retention_entry_kind("unknown")


def test_manifest_rejects_empty_paths_and_invalid_capacity_budget() -> None:
    with pytest.raises(ValueError, match="paths must be non-empty"):
        CanonicalLayoutManifest("", "runtime", {"x": "runtime/x"}, {})
    with pytest.raises(ValueError, match="capacity budgets"):
        CanonicalLayoutManifest(
            "runtime/a", "runtime", {"x": "runtime/x"}, {}, capacity_budgets={"x": 1}
        )

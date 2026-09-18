from __future__ import annotations

from pathlib import Path

from ai4binance.infrastructure.filesystem import load_optional_json_mapping
from ai4binance.infrastructure.filesystem.opportunity_artifact_loader import (
    load_optional_json_mapping as canonical_load_optional_json_mapping,
)
from ai4binance.infrastructure.opportunity_artifact_loader import (
    load_optional_json_mapping as legacy_load_optional_json_mapping,
)


def test_opportunity_artifact_loader_imports_preserve_function_identity() -> None:
    assert load_optional_json_mapping is canonical_load_optional_json_mapping
    assert legacy_load_optional_json_mapping is canonical_load_optional_json_mapping
    assert (
        canonical_load_optional_json_mapping.__module__
        == "ai4binance.infrastructure.filesystem.opportunity_artifact_loader"
    )


def test_opportunity_artifact_loader_reads_a_json_mapping(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text('{"status": "RESEARCH_ONLY"}', encoding="utf-8")

    assert load_optional_json_mapping(artifact_path) == {"status": "RESEARCH_ONLY"}


def test_opportunity_artifact_loader_returns_none_for_missing_artifact(
    tmp_path: Path,
) -> None:
    assert load_optional_json_mapping(tmp_path / "missing.json") is None


def test_opportunity_artifact_loader_returns_none_for_invalid_payloads(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "artifact.json"

    for payload in ("not-json", "[]", "null", '"text"', "1"):
        artifact_path.write_text(payload, encoding="utf-8")
        assert load_optional_json_mapping(artifact_path) is None

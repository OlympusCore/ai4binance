"""Regression coverage for authority-graph repository-validator integration."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from ai4binance.governance import repository_validator
from ai4binance.governance.repository_validator import RepositoryFindingKind

ROOT = Path(__file__).parents[3]


def test_repository_validator_accepts_aligned_authority_graph_fixture(
    tmp_path: Path,
) -> None:
    _write_authority_graph_fixture(tmp_path)

    findings = tuple(repository_validator._authority_graph_findings(tmp_path))

    assert findings == ()


def test_repository_validator_blocks_provider_authority_metadata_drift(
    tmp_path: Path,
) -> None:
    _write_authority_graph_fixture(tmp_path)
    gemini_path = tmp_path / "GEMINI.md"
    gemini_path.write_text(
        gemini_path.read_text(encoding="utf-8").replace(
            "authority_effect: OPERATIONAL_SPECIALIZATION\n", ""
        ),
        encoding="utf-8",
    )

    findings = tuple(repository_validator._authority_graph_findings(tmp_path))

    assert len(findings) == 2
    assert all(
        finding.kind is RepositoryFindingKind.AUTHORITY_GRAPH_CONFLICT
        for finding in findings
    )
    assert {finding.path for finding in findings} == {"GEMINI.md"}
    assert any(
        "AUTHORITY_METADATA_MISSING:authority_effect" in finding.detail
        for finding in findings
    )
    assert any(
        "PROVIDER_AUTHORITY_DRIFT:authority_effect" in finding.detail
        for finding in findings
    )
    assert all(finding.blocker for finding in findings)


def _write_authority_graph_fixture(root: Path) -> None:
    for schema_name in (
        "authority_layer_development_matrix.schema.json",
        "authority_node.schema.json",
        "authority_edge.schema.json",
        "authority_graph.schema.json",
    ):
        _copy(
            ROOT / "schemas" / "governance" / schema_name,
            root / "schemas" / "governance" / schema_name,
        )
    graph_path = root / "docs" / "registries" / "registry_authority_graph.yaml"
    _copy(ROOT / "docs" / "registries" / "registry_authority_graph.yaml", graph_path)
    payload = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    nodes = payload["nodes"]
    assert isinstance(nodes, list)
    for node in nodes:
        assert isinstance(node, dict)
        _copy(ROOT / str(node["canonical_path"]), root / str(node["canonical_path"]))
    for relative in ("CLAUDE.md", "GEMINI.md"):
        _copy(ROOT / relative, root / relative)
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if "authority_effect:" not in text:
            text = text.replace(
                "authority_scope:",
                "authority_effect: OPERATIONAL_SPECIALIZATION\nauthority_scope:",
            )
        path.write_text(text, encoding="utf-8")
        frontmatter = yaml.safe_load(text.split("---", maxsplit=2)[1])
        assert isinstance(frontmatter, dict)
        if not any(node.get("canonical_path") == relative for node in nodes):
            nodes.append(
                {
                    "node_id": Path(relative).stem.lower() + "-root-adapter",
                    "document_id": frontmatter["document_id"],
                    "canonical_path": relative,
                    "authority_layer": frontmatter["authority_layer"],
                    "authority_effect": frontmatter["authority_effect"],
                    "authority_scope": frontmatter["authority_scope"],
                    "lifecycle_status": frontmatter["status"],
                    "content_role": frontmatter["content_role"],
                    "source_of_truth": frontmatter["source_of_truth"],
                    "source_of_truth_scope": frontmatter["source_of_truth_scope"],
                }
            )
    graph_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    _copy(
        ROOT / "config" / "governance" / "authority_layer_development_matrix.yaml",
        root / "config" / "governance" / "authority_layer_development_matrix.yaml",
    )


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

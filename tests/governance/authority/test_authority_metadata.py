"""Regression coverage for graph-to-frontmatter authority drift checks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ai4binance.governance.authority import (
    AuthorityMetadataFindingKind,
    load_authority_graph,
    validate_authority_graph_metadata,
)

ROOT = Path(__file__).parents[3]
SCHEMA_ROOT = ROOT / "schemas"


def test_graph_metadata_matches_declared_nodes_without_inferencing_values() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    findings = validate_authority_graph_metadata(
        graph,
        ROOT,
        provider_adapter_paths=(),
    )

    assert findings == ()


def test_graph_uses_the_canonical_terminology_projection_identity() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    terminology_policy = next(
        node for node in graph.nodes if node.node_id == "terminology-policy"
    )

    assert terminology_policy.document_id == "AI4B-GOV-TERM-REG-001"
    assert (
        terminology_policy.canonical_path
        == "config/governance/canonical_terminology_registry.yaml"
    )


def test_provider_adapter_drift_is_visible_and_live_blocked(tmp_path: Path) -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    node = replace(graph.nodes[0], canonical_path="core.md")
    (tmp_path / "core.md").write_text(
        "---\n"
        "document_id: AI4B-GOV-FRM-001\n"
        "canonical_path: core.md\n"
        "authority_layer: L1_CORE_CONSTITUTION\n"
        "authority_effect: NORMATIVE_CONSTRAINT\n"
        "authority_scope: core_constitution\n"
        "status: ACTIVE\n"
        "content_role: AUTHORITATIVE\n"
        "source_of_truth: true\n"
        "source_of_truth_scope: canonical\n"
        "---\n",
        encoding="utf-8",
    )
    provider_path = tmp_path / "GEMINI.md"
    provider_path.write_text(
        "---\n"
        "document_id: AI4B-GOV-AGT-GEMINI-001\n"
        "authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS\n"
        "source_of_truth: false\n"
        "---\n",
        encoding="utf-8",
    )

    findings = validate_authority_graph_metadata(
        replace(graph, nodes=(node,), edges=()),
        tmp_path,
        provider_adapter_paths=("GEMINI.md",),
    )

    assert len(findings) == 2
    assert {finding.kind for finding in findings} == {
        AuthorityMetadataFindingKind.PROVIDER_AUTHORITY_DRIFT
    }
    assert {finding.field for finding in findings} == {
        "authority_effect",
        "authority_graph_coverage",
    }
    assert all(finding.execution_allowed is False for finding in findings)
    assert all(
        finding.live_eligibility_status == "LIVE_ORDER_BLOCKED" for finding in findings
    )


def test_authority_metadata_helpers_fail_closed_for_invalid_inputs(
    tmp_path: Path,
) -> None:
    from ai4binance.governance.authority import metadata

    with __import__("pytest").raises(ValueError, match="cannot authorize"):
        metadata.AuthorityMetadataFinding(
            AuthorityMetadataFindingKind.AUTHORITY_METADATA_MISSING,
            "path",
            "field",
            "detail",
            execution_allowed=True,
        )
    assert metadata._compare_metadata(
        "x", {}, dict.fromkeys(metadata._GRAPH_METADATA_FIELDS, "x")
    )
    assert metadata._provider_adapter_findings("x", {})[0].field == "frontmatter"
    yaml_path = tmp_path / "payload.yaml"
    yaml_path.write_text("[not-a-mapping]", encoding="utf-8")
    assert metadata._read_source_metadata(yaml_path) == {}
    yaml_path.write_text("[broken", encoding="utf-8")
    assert metadata._read_source_metadata(yaml_path) == {}
    markdown_path = tmp_path / "document.md"
    markdown_path.write_text("plain", encoding="utf-8")
    assert metadata._read_source_metadata(markdown_path) == {}
    markdown_path.write_text("---\n[broken\n---\n", encoding="utf-8")
    assert metadata._read_source_metadata(markdown_path) == {}


def test_authority_metadata_remaining_fail_closed_branches(tmp_path: Path) -> None:
    import pytest

    from ai4binance.governance.authority import metadata

    with pytest.raises(ValueError, match="details"):
        metadata.AuthorityMetadataFinding(
            AuthorityMetadataFindingKind.AUTHORITY_METADATA_MISSING,
            "",
            "field",
            "detail",
        )
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    with pytest.raises(ValueError, match="blanks"):
        validate_authority_graph_metadata(graph, tmp_path, provider_adapter_paths=("",))
    with pytest.raises(ValueError, match="unique"):
        validate_authority_graph_metadata(
            graph, tmp_path, provider_adapter_paths=("x", "x")
        )
    expected = dict.fromkeys(metadata._GRAPH_METADATA_FIELDS, "expected")
    assert all(
        finding.kind is AuthorityMetadataFindingKind.AUTHORITY_METADATA_DRIFT
        for finding in metadata._compare_metadata(
            "x", expected, expected | {"status": "other"}
        )
        if finding.field == "status"
    )
    assert metadata._read_source_metadata(tmp_path / "missing.md") == {}
    unclosed = tmp_path / "unclosed.md"
    unclosed.write_text("---\ndocument_id: x\n", encoding="utf-8")
    assert metadata._read_source_metadata(unclosed) == {}
    adapter = tmp_path / "adapter.md"
    adapter.write_text("---\nauthority_layer: BAD\n---\n", encoding="utf-8")
    findings = validate_authority_graph_metadata(
        replace(graph, nodes=(graph.nodes[0],), edges=()),
        tmp_path,
        provider_adapter_paths=("adapter.md",),
    )
    adapter_fields = {
        finding.field for finding in findings if finding.path == "adapter.md"
    }
    assert adapter_fields == {
        "authority_layer",
        "authority_effect",
        "source_of_truth",
        "authority_graph_coverage",
    }

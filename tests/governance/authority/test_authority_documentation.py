"""Regression coverage for generated authority-graph Markdown views."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.governance.authority import (
    load_authority_graph,
    render_authority_graph_markdown,
    write_runtime_authority_graph_markdown,
)

SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"


def test_rendered_authority_graph_is_deterministic_and_evidence_only() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    first_render = render_authority_graph_markdown(graph)

    assert first_render == render_authority_graph_markdown(graph)
    assert "document_id: AI4B-GOV-AUTHORITY-GRAPH-VIEW-001" in first_render
    assert "authority_effect: EVIDENCE_ONLY" in first_render
    assert "content_role: GENERATED" in first_render
    assert "source_of_truth: false" in first_render
    assert "execution_allowed: false" in first_render
    assert "live_eligibility_status: LIVE_ORDER_BLOCKED" in first_render
    assert "| core | AI4B-GOV-FRM-001 |" in first_render
    assert (
        "| core-governs-compliance-matrix | core | GOVERNS | compliance-matrix |"
        in (first_render)
    )


def test_generated_view_writes_only_below_runtime(tmp_path: Path) -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    output_path = Path("runtime/reports/authority_graph.md")

    written_path = write_runtime_authority_graph_markdown(graph, tmp_path, output_path)

    assert written_path == tmp_path / output_path
    assert written_path.read_text(encoding="utf-8") == render_authority_graph_markdown(
        graph
    )


@pytest.mark.parametrize(
    "output_path",
    [Path("docs/governance/authority/graph.md"), Path("runtime/graph.json")],
)
def test_generated_view_rejects_governed_or_non_markdown_destinations(
    tmp_path: Path, output_path: Path
) -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    with pytest.raises(ValueError, match=r"runtime|.md extension"):
        write_runtime_authority_graph_markdown(graph, tmp_path, output_path)

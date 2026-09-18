"""Regression coverage for authority-graph registry loading and structure."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.governance.authority import (
    DEFAULT_AUTHORITY_GRAPH_PATH,
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityRelation,
    load_authority_graph,
)

SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"


def test_authority_graph_registry_loads_as_non_authoritative_and_live_blocked() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    assert graph.graph_id == "AI4B-GOV-AUTHORITY-GRAPH-001"
    assert graph.source_of_truth is False
    assert graph.execution_allowed is False
    assert graph.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert {node.node_id for node in graph.nodes_for_scope("core_constitution")} == {
        "core"
    }
    assert DEFAULT_AUTHORITY_GRAPH_PATH.as_posix() == (
        "docs/registries/registry_authority_graph.yaml"
    )


def test_authority_graph_rejects_dangling_edges_and_ambiguous_nodes() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    dangling = AuthorityEdge(
        edge_id="missing-edge",
        from_node_id="core",
        to_node_id="missing-node",
        relation=AuthorityRelation.GOVERNS,
        edge_family=AuthorityEdgeFamily.AUTHORITY,
    )

    with pytest.raises(ValueError, match="dangling edges"):
        replace(graph, edges=(*graph.edges, dangling))
    with pytest.raises(ValueError, match="node identifiers must be unique"):
        replace(graph, nodes=(*graph.nodes, graph.nodes[0]))

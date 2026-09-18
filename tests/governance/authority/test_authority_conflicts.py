"""Regression coverage for fail-closed authority conflict detection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ai4binance.governance.authority import (
    AuthorityConflictKind,
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityRelation,
    detect_authority_conflicts,
    load_authority_graph,
    resolve_graph_authority,
)

SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"


def test_graph_resolution_reuses_existing_fail_closed_authority_resolver() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    resolution = resolve_graph_authority(graph, "core_constitution")
    missing = resolve_graph_authority(graph, "missing_scope")

    assert resolution.winner_artifact_id == "AI4B-GOV-FRM-001"
    assert resolution.execution_allowed is False
    assert missing.winner_artifact_id is None
    assert "GOVERNANCE_CONFLICT" in missing.blockers
    assert missing.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_conflict_detector_rejects_missing_source_cycles_and_lower_override() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    invalid_edges = (
        *graph.edges,
        AuthorityEdge(
            edge_id="repository-agent-governs-core",
            from_node_id="repository-agent-instructions",
            to_node_id="core",
            relation=AuthorityRelation.GOVERNS,
            edge_family=AuthorityEdgeFamily.AUTHORITY,
        ),
        AuthorityEdge(
            edge_id="repository-file-governance-governs-core",
            from_node_id="repository-file-governance",
            to_node_id="core",
            relation=AuthorityRelation.GOVERNS,
            edge_family=AuthorityEdgeFamily.AUTHORITY,
        ),
    )

    conflicts = detect_authority_conflicts(
        replace(graph, edges=invalid_edges),
        required_scopes=("core_constitution", "missing_scope"),
    )
    kinds = {conflict.kind for conflict in conflicts}

    assert AuthorityConflictKind.MISSING_SOURCE_OF_TRUTH in kinds
    assert AuthorityConflictKind.AUTHORITY_PRECEDENCE_CYCLE in kinds
    assert AuthorityConflictKind.LOWER_AUTHORITY_OVERRIDE in kinds
    assert all(conflict.execution_allowed is False for conflict in conflicts)
    assert all(
        conflict.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for conflict in conflicts
    )

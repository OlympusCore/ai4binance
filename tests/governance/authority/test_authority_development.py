"""Regression coverage for authority-layer development responsibilities."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.governance.authority import (
    AUTHORITY_LAYERS,
    AuthorityNode,
    load_authority_graph,
    load_authority_layer_development_matrix,
    validate_authority_graph_layer_development,
)

ROOT = Path(__file__).parents[3]


def test_matrix_covers_each_authority_layer_with_safe_development_boundaries() -> None:
    matrix = load_authority_layer_development_matrix(ROOT)

    assert {layer.authority_layer for layer in matrix.layers} == set(AUTHORITY_LAYERS)
    assert {group.group_id for group in matrix.groups} == {
        "boundary_decision_authority",
        "contract_binding",
        "control_acceptance",
        "ownership_traceability",
        "operational_specialization",
        "evidence_reference_archive",
    }
    assert {
        layer.authority_layer
        for layer in matrix.layers
        if not layer.source_of_truth_allowed
    } == {
        "L8_REPORTS_EVIDENCE_INVENTORIES",
        "L9_REFERENCES_TEMPLATES",
        "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS",
    }
    assert matrix.execution_allowed is False
    assert matrix.promotion_status == "RESEARCH_ONLY"
    assert matrix.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_matrix_rejects_incomplete_coverage_and_unknown_effects() -> None:
    matrix = load_authority_layer_development_matrix(ROOT)

    with pytest.raises(ValueError, match="cover every layer"):
        replace(matrix, layers=matrix.layers[:-1])
    with pytest.raises(ValueError, match="effect is invalid"):
        replace(matrix.layers[0], allowed_authority_effects=("UNKNOWN",))


def test_graph_cannot_exceed_layer_effect_or_evidence_authority_boundaries() -> None:
    matrix = load_authority_layer_development_matrix(ROOT)
    graph = load_authority_graph(schema_root=ROOT / "schemas")
    core = next(node for node in graph.nodes if node.node_id == "core")
    invalid_effect_graph = replace(
        graph,
        nodes=(replace(core, authority_effect="IMPLEMENTATION"),),
        edges=(),
    )
    evidence_node = AuthorityNode(
        node_id="evidence",
        document_id="AI4B-GOV-EVIDENCE-001",
        canonical_path="runtime/evidence.json",
        authority_layer="L8_REPORTS_EVIDENCE_INVENTORIES",
        authority_effect="EVIDENCE_ONLY",
        authority_scope="evidence",
        lifecycle_status="ACTIVE",
        content_role="AUTHORITATIVE",
        source_of_truth=True,
        source_of_truth_scope="evidence",
    )
    invalid_evidence_graph = replace(graph, nodes=(evidence_node,), edges=())

    effect_findings = validate_authority_graph_layer_development(
        invalid_effect_graph, matrix
    )
    evidence_findings = validate_authority_graph_layer_development(
        invalid_evidence_graph, matrix
    )

    assert [finding.code for finding in effect_findings] == [
        "AUTHORITY_LAYER_EFFECT_VIOLATION"
    ]
    assert [finding.code for finding in evidence_findings] == [
        "AUTHORITY_LAYER_SOURCE_OF_TRUTH_FORBIDDEN"
    ]
    assert all("GOVERNANCE_CONFLICT" in finding.blockers for finding in effect_findings)
    assert all(finding.execution_allowed is False for finding in evidence_findings)


def test_current_graph_is_aligned_with_the_development_matrix() -> None:
    matrix = load_authority_layer_development_matrix(ROOT)
    graph = load_authority_graph(schema_root=ROOT / "schemas")

    assert validate_authority_graph_layer_development(graph, matrix) == ()

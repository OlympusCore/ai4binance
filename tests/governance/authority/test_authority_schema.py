"""Regression coverage for authority-graph semantic contracts and schemas."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict, cast

import pytest

from ai4binance.governance.authority import (
    AUTHORITY_EFFECTS,
    AUTHORITY_LAYERS,
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityNode,
    AuthorityRelation,
    authority_edge_family,
)
from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"
NODE_SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/authority_node.schema.json"
)
EDGE_SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/authority_edge.schema.json"
)
GRAPH_SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/authority_graph.schema.json"
)


class AuthorityNodePayload(TypedDict):
    """Complete test payload for the typed AuthorityNode constructor."""

    node_id: str
    document_id: str
    canonical_path: str
    authority_layer: str
    authority_effect: str
    authority_scope: str
    lifecycle_status: str
    content_role: str
    source_of_truth: bool
    source_of_truth_scope: str


def _node_payload(**overrides: object) -> AuthorityNodePayload:
    payload: dict[str, object] = {
        "node_id": "core",
        "document_id": "AI4B-GOV-FRM-001",
        "canonical_path": "docs/governance/framework_core_vnext_governance.md",
        "authority_layer": "L1_CORE_CONSTITUTION",
        "authority_effect": "NORMATIVE_CONSTRAINT",
        "authority_scope": "core_constitution",
        "lifecycle_status": "ACTIVE",
        "content_role": "AUTHORITATIVE",
        "source_of_truth": True,
        "source_of_truth_scope": "canonical",
    }
    payload.update(overrides)
    return cast(AuthorityNodePayload, payload)


def test_authority_model_keeps_layers_effects_and_edge_families_explicit() -> None:
    node = AuthorityNode(**_node_payload())
    edge = AuthorityEdge(
        edge_id="core-governs-codex",
        from_node_id="core",
        to_node_id="codex",
        relation=AuthorityRelation.GOVERNS,
        edge_family=AuthorityEdgeFamily.AUTHORITY,
    )

    assert node.authority_layer in AUTHORITY_LAYERS
    assert node.authority_effect in AUTHORITY_EFFECTS
    assert edge.edge_family is authority_edge_family(edge.relation)
    assert (
        authority_edge_family(AuthorityRelation.SUPERSEDES)
        is AuthorityEdgeFamily.LIFECYCLE
    )
    assert (
        authority_edge_family(AuthorityRelation.REFERENCES)
        is AuthorityEdgeFamily.DEPENDENCY
    )


def test_authority_model_rejects_generated_source_of_truth_and_mismatched_family() -> (
    None
):
    with pytest.raises(ValueError, match="generated authority views"):
        AuthorityNode(**_node_payload(content_role="GENERATED"))
    with pytest.raises(ValueError, match="family must match"):
        AuthorityEdge(
            edge_id="core-reference-codex",
            from_node_id="core",
            to_node_id="codex",
            relation=AuthorityRelation.REFERENCES,
            edge_family=AuthorityEdgeFamily.AUTHORITY,
        )


def test_authority_schemas_validate_closed_graph_and_reject_unsafe_claims() -> None:
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    registry.validate(NODE_SCHEMA_ID, _node_payload())
    registry.validate(
        EDGE_SCHEMA_ID,
        {
            "edge_id": "core-governs-codex",
            "from_node_id": "core",
            "to_node_id": "codex",
            "relation": "GOVERNS",
            "edge_family": "AUTHORITY",
        },
    )
    registry.validate(
        GRAPH_SCHEMA_ID,
        {
            "graph_id": "AI4B-GOV-AUTHORITY-GRAPH-001",
            "version": "1.0.0",
            "status": "ACTIVE",
            "source_of_truth": False,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "nodes": [_node_payload()],
            "edges": [],
        },
    )

    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        registry.validate(
            NODE_SCHEMA_ID,
            _node_payload(content_role="GENERATED", source_of_truth=True),
        )
    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        registry.validate(
            EDGE_SCHEMA_ID,
            {
                "edge_id": "invalid-family",
                "from_node_id": "core",
                "to_node_id": "codex",
                "relation": "REFERENCES",
                "edge_family": "AUTHORITY",
            },
        )
    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        registry.validate(
            GRAPH_SCHEMA_ID,
            {
                "graph_id": "AI4B-GOV-AUTHORITY-GRAPH-001",
                "version": "1.0.0",
                "status": "ACTIVE",
                "source_of_truth": False,
                "execution_allowed": True,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                "nodes": [_node_payload()],
                "edges": [],
            },
        )

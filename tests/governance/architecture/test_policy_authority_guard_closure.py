"""Behavioral closure for fail-closed policy and authority guard branches."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from ai4binance.governance.architecture.model import (
    LogicalArchitectureComponent,
    LogicalArchitectureRegistry,
    LogicalArchitectureRelation,
    LogicalComponentKind,
    LogicalRelationType,
)
from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.impact import AuthorityImpact
from ai4binance.governance.authority.metadata import AuthorityMetadataFinding
from ai4binance.governance.authority.model import (
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityNode,
    AuthorityRelation,
)
from ai4binance.governance.authority_resolution import (
    AuthorityCandidate,
    AuthorityResolution,
    AuthorityResolutionStatus,
    resolve_authority,
    resolve_authority_pair,
)


def _component(component_id: str = "component-a") -> LogicalArchitectureComponent:
    return LogicalArchitectureComponent(
        component_id=component_id,
        component_kind=LogicalComponentKind.CONTROL,
        canonical_domain="13_GOVERNANCE",
        logical_plane="CONTROL & ASSURANCE PLANE",
        dependency_layer="governance",
        runtime_class="GOVERNED_DETERMINISTIC",
        owner="Enterprise Governance",
        authority_effect="EVIDENCE_ONLY",
        source_paths=(f"src/{component_id}.py",),
        contract_refs=(f"docs/{component_id}.md",),
        test_refs=(f"tests/test_{component_id}.py",),
        hot_path=False,
        deterministic=True,
        llm_dependency=False,
        side_effects=False,
        decision_authority=False,
        risk_override=False,
        validation_override=False,
        source_of_truth=False,
        execution_allowed=False,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )


def _relation(
    relation_id: str = "component-a-governs-component-b",
    *,
    from_component_id: str = "component-a",
    to_component_id: str = "component-b",
    relation_type: LogicalRelationType = LogicalRelationType.GOVERNED_BY,
) -> LogicalArchitectureRelation:
    return LogicalArchitectureRelation(
        relation_id=relation_id,
        from_component_id=from_component_id,
        to_component_id=to_component_id,
        relation_type=relation_type,
    )


def _architecture_registry() -> LogicalArchitectureRegistry:
    return LogicalArchitectureRegistry(
        registry_id="AI4B-TEST-LOGICAL-REGISTRY",
        version="1.0.0",
        status="ACTIVE",
        source_of_truth=False,
        execution_allowed=False,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
        components=(_component("component-a"), _component("component-b")),
        relations=(_relation(),),
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"component_id": ""}, "component_id is required"),
        ({"source_paths": ()}, "source_paths must be unique"),
        ({"source_paths": ("src/a.py", "src/a.py")}, "source_paths must be unique"),
        ({"contract_refs": ("../policy.md",)}, "must be repository-relative"),
        ({"side_effects": True}, "cannot declare side effects"),
        ({"decision_authority": True}, "cannot grant authority"),
        ({"source_of_truth": True}, "cannot become a source of truth"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"live_eligibility_status": "READY"}, "must remain live-order blocked"),
    ],
)
def test_logical_component_rejects_authority_and_identity_drift(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_component(), **changes)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"relation_id": ""}, "relation_id is required"),
        ({"from_component_id": ""}, "endpoints are required"),
        ({"to_component_id": "component-a"}, "cannot self-reference"),
    ],
)
def test_logical_relation_rejects_invalid_identity(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_relation(), **changes)


def test_logical_registry_rejects_identity_authority_and_ordering_drift() -> None:
    registry = _architecture_registry()
    invalid_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"registry_id": ""}, "identity is required"),
        ({"status": "DRAFT"}, "must be active"),
        ({"source_of_truth": True}, "cannot become a source of truth"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"live_eligibility_status": "READY"}, "must remain live-order blocked"),
        ({"components": ()}, "must be non-empty and sorted"),
        (
            ({"components": (_component("component-b"), _component("component-a"))}),
            "must be non-empty and sorted",
        ),
        (
            ({"components": (_component("component-a"), _component("component-a"))}),
            "component IDs must be unique",
        ),
        (
            {
                "relations": (
                    _relation("z-relation"),
                    _relation(
                        "a-relation",
                        from_component_id="component-b",
                        to_component_id="component-a",
                    ),
                )
            },
            "relations must be sorted",
        ),
        (
            {
                "relations": (
                    _relation("same-id"),
                    _relation(
                        "same-id",
                        from_component_id="component-b",
                        to_component_id="component-a",
                    ),
                )
            },
            "relation IDs must be unique",
        ),
        (
            {"relations": (_relation("a-relation"), _relation("z-relation"))},
            "relation semantics must be unique",
        ),
        (
            {"relations": (_relation(to_component_id="component-missing"),)},
            "reference unknown components",
        ),
    )

    for changes, error in invalid_cases:
        with pytest.raises(ValueError, match=error):
            replace(registry, **changes)


def _authority_node(
    node_id: str = "node-a",
    *,
    document_id: str | None = None,
    canonical_path: str | None = None,
) -> AuthorityNode:
    return AuthorityNode(
        node_id=node_id,
        document_id=document_id or f"AI4B-{node_id.upper()}",
        canonical_path=canonical_path or f"docs/{node_id}.md",
        authority_layer="L2_GOVERNANCE_COMPLIANCE",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="enterprise_governance",
        lifecycle_status="ACTIVE",
        content_role="AUTHORITATIVE",
        source_of_truth=True,
        source_of_truth_scope="enterprise_governance",
    )


def _authority_edge(
    edge_id: str = "node-a-governs-node-b",
    *,
    from_node_id: str = "node-a",
    to_node_id: str = "node-b",
) -> AuthorityEdge:
    return AuthorityEdge(
        edge_id=edge_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        relation=AuthorityRelation.GOVERNS,
        edge_family=AuthorityEdgeFamily.AUTHORITY,
    )


def _authority_graph() -> AuthorityGraph:
    return AuthorityGraph(
        graph_id="AI4B-TEST-AUTHORITY-GRAPH",
        version="1.0.0",
        status="ACTIVE",
        source_of_truth=False,
        execution_allowed=False,
        live_eligibility_status="LIVE_ORDER_BLOCKED",
        nodes=(_authority_node("node-a"), _authority_node("node-b")),
        edges=(_authority_edge(),),
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"node_id": ""}, "metadata is required"),
        ({"canonical_path": "/docs/policy.md"}, "repository-relative posix"),
        ({"authority_layer": "L99_UNKNOWN"}, "layer is invalid"),
        ({"authority_effect": "AUTHORIZE"}, "effect is invalid"),
        ({"authority_scope": "Not-Snake"}, "scope must use lower_snake_case"),
        (
            {"source_of_truth_scope": "Not-Snake"},
            "source-of-truth scope must use lower_snake_case",
        ),
        (
            {"content_role": "GENERATED"},
            "generated authority views cannot be sources of truth",
        ),
        (
            {"content_role": "REFERENCE"},
            "require authoritative content",
        ),
    ],
)
def test_authority_node_rejects_invalid_or_expansive_metadata(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_authority_node(), **changes)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"edge_id": ""}, "metadata is required"),
        ({"to_node_id": "node-a"}, "cannot self-reference"),
        ({"edge_family": AuthorityEdgeFamily.DEPENDENCY}, "family must match"),
    ],
)
def test_authority_edge_rejects_invalid_identity_or_family(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_authority_edge(), **changes)


def test_authority_graph_rejects_identity_duplicates_and_dangling_edges() -> None:
    graph = _authority_graph()
    node_a = _authority_node("node-a")
    invalid_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"graph_id": ""}, "identity is required"),
        ({"status": "DRAFT"}, "status must be ACTIVE"),
        ({"source_of_truth": True}, "cannot be a source of truth"),
        ({"execution_allowed": True}, "cannot authorize live execution"),
        ({"live_eligibility_status": "READY"}, "cannot authorize live execution"),
        ({"nodes": ()}, "requires nodes"),
        ({"nodes": (node_a, node_a)}, "node identifiers must be unique"),
        (
            {
                "nodes": (
                    node_a,
                    _authority_node("node-b", document_id=node_a.document_id),
                )
            },
            "document identifiers must be unique",
        ),
        (
            {
                "nodes": (
                    node_a,
                    _authority_node("node-b", canonical_path=node_a.canonical_path),
                )
            },
            "canonical paths must be unique",
        ),
        (
            {
                "edges": (
                    _authority_edge("same-id"),
                    _authority_edge(
                        "same-id", from_node_id="node-b", to_node_id="node-a"
                    ),
                )
            },
            "edge identifiers must be unique",
        ),
        (
            {"edges": (_authority_edge(to_node_id="node-missing"),)},
            "contains dangling edges",
        ),
    )
    for changes, error in invalid_cases:
        with pytest.raises(ValueError, match=error):
            replace(graph, **changes)

    with pytest.raises(ValueError, match="authority scope is required"):
        graph.nodes_for_scope("")


def _authority_impact() -> AuthorityImpact:
    return AuthorityImpact(
        changed_node_ids=("node-a",),
        direct_impacted_node_ids=("node-b",),
        transitive_impacted_node_ids=("node-c",),
        required_sync_paths=("docs/node-b.md", "docs/node-c.md"),
        required_test_paths=("tests/test_authority.py",),
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"changed_node_ids": ()}, "requires changed nodes"),
        ({"direct_impacted_node_ids": ("",)}, "identifiers are required"),
        ({"direct_impacted_node_ids": ("node-b", "node-b")}, "must be unique"),
        ({"direct_impacted_node_ids": ("node-a",)}, "cannot be direct impacts"),
        ({"transitive_impacted_node_ids": ("node-b",)}, "must not overlap"),
        ({"change_class": "C0"}, "remain governed changes"),
        ({"promotion_status": "PROMOTED"}, "cannot authorize promotion"),
        ({"execution_allowed": True}, "cannot authorize live execution"),
        ({"live_eligibility_status": "READY"}, "cannot authorize live execution"),
    ],
)
def test_authority_impact_rejects_overlap_and_authority_expansion(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_authority_impact(), **changes)


def _authority_candidate(
    artifact_id: str = "artifact-a", *, source_of_truth: bool = True
) -> AuthorityCandidate:
    return AuthorityCandidate(
        artifact_id=artifact_id,
        authority_scope="enterprise_governance",
        authority_layer="L2_GOVERNANCE_COMPLIANCE",
        lifecycle_status="ACTIVE",
        source_of_truth=source_of_truth,
        canonical_path=f"docs/{artifact_id}.md",
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"artifact_id": ""}, "metadata is required"),
        ({"authority_layer": "L99_UNKNOWN"}, "layer is invalid"),
        ({"canonical_path": "/docs/policy.md"}, "repository-relative posix"),
    ],
)
def test_authority_candidate_rejects_invalid_metadata(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_authority_candidate(), **changes)


def _authority_resolution() -> AuthorityResolution:
    return AuthorityResolution(
        authority_scope="enterprise_governance",
        status=AuthorityResolutionStatus.A_WINS,
        winner_artifact_id="artifact-a",
        candidate_artifact_ids=("artifact-a",),
        blockers=("LIVE_ORDER_BLOCKED",),
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"authority_scope": ""}, "scope is required"),
        ({"candidate_artifact_ids": ()}, "candidates are required"),
        ({"candidate_artifact_ids": ("artifact-a", "artifact-a")}, "must be unique"),
        (
            {"status": AuthorityResolutionStatus.AMBIGUOUS, "blockers": ()},
            "ambiguous authority resolution requires blockers",
        ),
        (
            {"status": AuthorityResolutionStatus.CONFLICT, "blockers": ()},
            "requires governance conflict",
        ),
        ({"execution_allowed": True}, "cannot authorize live execution"),
        ({"live_eligibility_status": "READY"}, "cannot authorize live execution"),
    ],
)
def test_authority_resolution_rejects_unsafe_or_ambiguous_state(
    changes: dict[str, Any], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_authority_resolution(), **changes)


def test_authority_resolution_preserves_all_fail_closed_outcomes() -> None:
    source = _authority_candidate()
    peer = _authority_candidate("artifact-b", source_of_truth=False)
    alternate_scope = replace(peer, authority_scope="other_scope")

    with pytest.raises(ValueError, match="authority scope is required"):
        resolve_authority("", (source,))
    assert resolve_authority("missing_scope", (source,)).status is (
        AuthorityResolutionStatus.NO_AUTHORITY
    )
    assert (
        resolve_authority(
            "enterprise_governance", (replace(source, source_of_truth=False),)
        ).status
        is AuthorityResolutionStatus.NO_AUTHORITY
    )
    assert (
        resolve_authority(
            "enterprise_governance", (source, replace(peer, source_of_truth=True))
        ).status
        is AuthorityResolutionStatus.DUPLICATE_SOURCE_OF_TRUTH
    )
    assert resolve_authority_pair(source, alternate_scope).status is (
        AuthorityResolutionStatus.AMBIGUOUS
    )
    assert resolve_authority_pair(source, source).status is (
        AuthorityResolutionStatus.SAME_AUTHORITY
    )
    assert (
        resolve_authority_pair(peer, source).status is AuthorityResolutionStatus.B_WINS
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"path": ""},
        {"execution_allowed": True},
        {"live_eligibility_status": "READY"},
    ],
)
def test_authority_metadata_finding_rejects_incomplete_or_live_authority(
    changes: dict[str, Any],
) -> None:
    finding = AuthorityMetadataFinding(
        kind="AUTHORITY_METADATA_DRIFT",  # type: ignore[arg-type]
        path="docs/policy.md",
        field="authority_layer",
        detail="metadata differs",
    )
    with pytest.raises(ValueError, match=r"details are required|cannot authorize"):
        replace(finding, **changes)

"""Fail-closed detection of authority-graph conflicts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.model import (
    AUTHORITY_LAYERS,
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityNode,
    AuthorityRelation,
)


class AuthorityConflictKind(StrEnum):
    """Canonical hard-blocker causes from authority graph validation."""

    DUPLICATE_ACTIVE_SOURCE_OF_TRUTH = "DUPLICATE_ACTIVE_SOURCE_OF_TRUTH"
    MISSING_SOURCE_OF_TRUTH = "MISSING_SOURCE_OF_TRUTH"
    AUTHORITY_PRECEDENCE_CYCLE = "AUTHORITY_PRECEDENCE_CYCLE"
    SUPERSESSION_CYCLE = "SUPERSESSION_CYCLE"
    LOWER_AUTHORITY_OVERRIDE = "LOWER_AUTHORITY_OVERRIDE"
    AUTHORITY_SCOPE_COLLISION = "AUTHORITY_SCOPE_COLLISION"


@dataclass(frozen=True, slots=True)
class AuthorityConflict:
    """One deterministic, non-waiving authority conflict finding."""

    kind: AuthorityConflictKind
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    detail: str
    blockers: tuple[str, ...] = ("GOVERNANCE_CONFLICT", "LIVE_ORDER_BLOCKED")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ValueError("authority conflict detail is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("authority conflicts cannot authorize live execution")
        if "GOVERNANCE_CONFLICT" not in self.blockers:
            raise ValueError("authority conflicts require governance conflict blocker")


def detect_authority_conflicts(
    graph: AuthorityGraph,
    *,
    required_scopes: tuple[str, ...] = (),
) -> tuple[AuthorityConflict, ...]:
    """Return all deterministic hard conflicts without resolving around them."""
    if any(not scope.strip() for scope in required_scopes):
        raise ValueError("required authority scopes cannot contain blanks")
    if len(set(required_scopes)) != len(required_scopes):
        raise ValueError("required authority scopes must be unique")
    conflicts: list[AuthorityConflict] = []
    active_by_scope = _active_nodes_by_scope(graph.nodes)
    for scope, nodes in sorted(active_by_scope.items()):
        sources = tuple(node for node in nodes if node.source_of_truth)
        if len(sources) > 1:
            conflicts.append(
                AuthorityConflict(
                    kind=AuthorityConflictKind.DUPLICATE_ACTIVE_SOURCE_OF_TRUTH,
                    node_ids=tuple(sorted(node.node_id for node in sources)),
                    edge_ids=(),
                    detail=f"multiple active sources of truth declare scope {scope}",
                )
            )
        source_scopes = {node.source_of_truth_scope for node in sources}
        if len(source_scopes) > 1:
            conflicts.append(
                AuthorityConflict(
                    kind=AuthorityConflictKind.AUTHORITY_SCOPE_COLLISION,
                    node_ids=tuple(sorted(node.node_id for node in sources)),
                    edge_ids=(),
                    detail=(
                        f"active sources disagree on source-of-truth scope for {scope}"
                    ),
                )
            )
    for scope in sorted(required_scopes):
        sources = tuple(
            node for node in active_by_scope.get(scope, ()) if node.source_of_truth
        )
        if not sources:
            conflicts.append(
                AuthorityConflict(
                    kind=AuthorityConflictKind.MISSING_SOURCE_OF_TRUTH,
                    node_ids=tuple(
                        sorted(node.node_id for node in active_by_scope.get(scope, ()))
                    ),
                    edge_ids=(),
                    detail=(
                        "required authority scope has no active source of truth: "
                        f"{scope}"
                    ),
                )
            )
    conflicts.extend(_precedence_conflicts(graph))
    conflicts.extend(_cycle_conflicts(graph, AuthorityEdgeFamily.AUTHORITY))
    conflicts.extend(_cycle_conflicts(graph, AuthorityEdgeFamily.LIFECYCLE))
    return tuple(
        sorted(
            conflicts,
            key=lambda conflict: (
                conflict.kind.value,
                conflict.node_ids,
                conflict.edge_ids,
            ),
        )
    )


def _active_nodes_by_scope(
    nodes: tuple[AuthorityNode, ...],
) -> dict[str, tuple[AuthorityNode, ...]]:
    grouped: defaultdict[str, list[AuthorityNode]] = defaultdict(list)
    for node in nodes:
        if node.lifecycle_status == "ACTIVE":
            grouped[node.authority_scope].append(node)
    return {scope: tuple(grouped_nodes) for scope, grouped_nodes in grouped.items()}


def _precedence_conflicts(graph: AuthorityGraph) -> tuple[AuthorityConflict, ...]:
    nodes = {node.node_id: node for node in graph.nodes}
    conflicts: list[AuthorityConflict] = []
    for edge in graph.edges:
        source = nodes[edge.from_node_id]
        target = nodes[edge.to_node_id]
        source_rank = AUTHORITY_LAYERS.index(source.authority_layer)
        target_rank = AUTHORITY_LAYERS.index(target.authority_layer)
        invalid = (
            edge.relation is AuthorityRelation.GOVERNS and source_rank > target_rank
        ) or (
            edge.relation is AuthorityRelation.SPECIALIZES and source_rank < target_rank
        )
        if invalid:
            conflicts.append(
                AuthorityConflict(
                    kind=AuthorityConflictKind.LOWER_AUTHORITY_OVERRIDE,
                    node_ids=(source.node_id, target.node_id),
                    edge_ids=(edge.edge_id,),
                    detail=(
                        f"{edge.relation.value} reverses declared authority layers: "
                        f"{source.authority_layer} -> {target.authority_layer}"
                    ),
                )
            )
    return tuple(conflicts)


def _cycle_conflicts(
    graph: AuthorityGraph,
    family: AuthorityEdgeFamily,
) -> tuple[AuthorityConflict, ...]:
    edges = tuple(edge for edge in graph.edges if edge.edge_family is family)
    adjacency: defaultdict[str, list[AuthorityEdge]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.from_node_id].append(edge)
    conflicts: list[AuthorityConflict] = []
    visited: set[str] = set()
    active: list[str] = []
    active_edges: list[AuthorityEdge] = []

    def visit(node_id: str) -> None:
        visited.add(node_id)
        active.append(node_id)
        for edge in sorted(adjacency[node_id], key=lambda item: item.edge_id):
            if edge.to_node_id in active:
                cycle_start = active.index(edge.to_node_id)
                cycle_nodes = tuple(active[cycle_start:])
                cycle_edges = tuple(
                    item.edge_id for item in (*active_edges[cycle_start:], edge)
                )
                conflicts.append(
                    AuthorityConflict(
                        kind=(
                            AuthorityConflictKind.AUTHORITY_PRECEDENCE_CYCLE
                            if family is AuthorityEdgeFamily.AUTHORITY
                            else AuthorityConflictKind.SUPERSESSION_CYCLE
                        ),
                        node_ids=cycle_nodes,
                        edge_ids=cycle_edges,
                        detail=(
                            f"{family.value.lower()} graph contains a prohibited cycle"
                        ),
                    )
                )
            elif edge.to_node_id not in visited:
                active_edges.append(edge)
                visit(edge.to_node_id)
                active_edges.pop()
        active.pop()

    for node_id in sorted(node.node_id for node in graph.nodes):
        if node_id not in visited:
            visit(node_id)
    return tuple(conflicts)

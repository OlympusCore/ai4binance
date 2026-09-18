"""Deterministic, non-executing change-impact analysis for authority graphs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.model import AuthorityRelation

_GOVERNED_CHANGE_CLASS = "C3_GOVERNED"
_LIVE_ORDER_BLOCKED = "LIVE_ORDER_BLOCKED"
_RESEARCH_ONLY = "RESEARCH_ONLY"
_REQUIRED_TEST_PATHS: tuple[str, ...] = (
    "tests/governance/authority/test_authority_conflicts.py",
    "tests/governance/authority/test_authority_impact.py",
    "tests/governance/authority/test_authority_repository_integration.py",
    "tests/test_authority_resolution.py",
    "tests/test_repository_validator.py",
)


@dataclass(frozen=True, slots=True)
class AuthorityImpact:
    """Read-only result for a declared authority-graph change.

    Direct impacts are one relationship hop from a changed node. Transitive
    impacts are later hops and never include a changed or direct-impact node.
    """

    changed_node_ids: tuple[str, ...]
    direct_impacted_node_ids: tuple[str, ...]
    transitive_impacted_node_ids: tuple[str, ...]
    required_sync_paths: tuple[str, ...]
    required_test_paths: tuple[str, ...]
    change_class: str = _GOVERNED_CHANGE_CLASS
    promotion_status: str = _RESEARCH_ONLY
    execution_allowed: bool = False
    live_eligibility_status: str = _LIVE_ORDER_BLOCKED

    def __post_init__(self) -> None:
        if not self.changed_node_ids:
            raise ValueError("authority impact requires changed nodes")
        declared_groups = (
            self.changed_node_ids,
            self.direct_impacted_node_ids,
            self.transitive_impacted_node_ids,
        )
        for node_ids in declared_groups:
            if any(not node_id.strip() for node_id in node_ids):
                raise ValueError("authority impact node identifiers are required")
            if len(set(node_ids)) != len(node_ids):
                raise ValueError("authority impact node identifiers must be unique")
        if set(self.changed_node_ids) & set(self.direct_impacted_node_ids):
            raise ValueError("changed nodes cannot be direct impacts")
        if (set(self.changed_node_ids) | set(self.direct_impacted_node_ids)) & set(
            self.transitive_impacted_node_ids
        ):
            raise ValueError("authority impact node groups must not overlap")
        if self.change_class != _GOVERNED_CHANGE_CLASS:
            raise ValueError("authority impacts remain governed changes")
        if self.promotion_status != _RESEARCH_ONLY:
            raise ValueError("authority impacts cannot authorize promotion")
        if (
            self.execution_allowed
            or self.live_eligibility_status != _LIVE_ORDER_BLOCKED
        ):
            raise ValueError("authority impacts cannot authorize live execution")


def analyze_authority_impact(
    graph: AuthorityGraph, changed_node_ids: tuple[str, ...]
) -> AuthorityImpact:
    """Return affected governed artifacts without inferring authority or approval.

    Only declared authority relationships determine required synchronization.
    Dependency, lifecycle, and reference edges are intentionally excluded so an
    evidence map cannot silently become an authority or promotion engine.
    """
    _validate_changed_node_ids(graph, changed_node_ids)
    downstream = _authority_downstream_adjacency(graph)
    direct = _next_nodes(changed_node_ids, downstream)
    transitive = _transitive_nodes(changed_node_ids, direct, downstream)
    node_paths = {node.node_id: node.canonical_path for node in graph.nodes}
    impacted = (*direct, *transitive)

    return AuthorityImpact(
        changed_node_ids=tuple(sorted(changed_node_ids)),
        direct_impacted_node_ids=direct,
        transitive_impacted_node_ids=transitive,
        required_sync_paths=tuple(sorted(node_paths[node_id] for node_id in impacted)),
        required_test_paths=_REQUIRED_TEST_PATHS,
    )


def _validate_changed_node_ids(
    graph: AuthorityGraph, changed_node_ids: tuple[str, ...]
) -> None:
    if not changed_node_ids:
        raise ValueError("authority impact requires changed nodes")
    if any(not node_id.strip() for node_id in changed_node_ids):
        raise ValueError("authority impact node identifiers are required")
    if len(set(changed_node_ids)) != len(changed_node_ids):
        raise ValueError("authority impact node identifiers must be unique")
    unknown_node_ids = set(changed_node_ids) - {node.node_id for node in graph.nodes}
    if unknown_node_ids:
        raise ValueError(
            "authority impact contains unknown nodes: "
            + ", ".join(sorted(unknown_node_ids))
        )


def _authority_downstream_adjacency(
    graph: AuthorityGraph,
) -> dict[str, tuple[str, ...]]:
    adjacency: dict[str, set[str]] = {node.node_id: set() for node in graph.nodes}
    for edge in graph.edges:
        if edge.relation in {
            AuthorityRelation.GOVERNS,
            AuthorityRelation.MUST_ALIGN_WITH,
        }:
            adjacency[edge.from_node_id].add(edge.to_node_id)
        elif edge.relation is AuthorityRelation.SPECIALIZES:
            adjacency[edge.to_node_id].add(edge.from_node_id)
    return {node_id: tuple(sorted(node_ids)) for node_id, node_ids in adjacency.items()}


def _next_nodes(
    node_ids: tuple[str, ...], adjacency: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    return tuple(
        sorted({target for node_id in node_ids for target in adjacency[node_id]})
    )


def _transitive_nodes(
    changed_node_ids: tuple[str, ...],
    direct_node_ids: tuple[str, ...],
    adjacency: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    excluded = set(changed_node_ids) | set(direct_node_ids)
    discovered: set[str] = set()
    queue: deque[str] = deque(direct_node_ids)
    while queue:
        node_id = queue.popleft()
        for target in adjacency[node_id]:
            if target in excluded or target in discovered:
                continue
            discovered.add(target)
            queue.append(target)
    return tuple(sorted(discovered))

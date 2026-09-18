"""In-memory, fail-closed validation for declared authority graphs."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.governance.authority.model import AuthorityEdge, AuthorityNode


@dataclass(frozen=True, slots=True)
class AuthorityGraph:
    """A non-authoritative projection of declared governance metadata."""

    graph_id: str
    version: str
    status: str
    source_of_truth: bool
    execution_allowed: bool
    live_eligibility_status: str
    nodes: tuple[AuthorityNode, ...]
    edges: tuple[AuthorityEdge, ...]

    def __post_init__(self) -> None:
        if not self.graph_id.strip() or not self.version.strip():
            raise ValueError("authority graph identity is required")
        if self.status != "ACTIVE":
            raise ValueError("authority graph status must be ACTIVE")
        if self.source_of_truth:
            raise ValueError("authority graph cannot be a source of truth")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("authority graph cannot authorize live execution")
        if not self.nodes:
            raise ValueError("authority graph requires nodes")
        node_ids = tuple(node.node_id for node in self.nodes)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("authority graph node identifiers must be unique")
        document_ids = tuple(node.document_id for node in self.nodes)
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("authority graph document identifiers must be unique")
        canonical_paths = tuple(node.canonical_path for node in self.nodes)
        if len(set(canonical_paths)) != len(canonical_paths):
            raise ValueError("authority graph canonical paths must be unique")
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("authority graph edge identifiers must be unique")
        declared_nodes = set(node_ids)
        dangling_edges = tuple(
            edge.edge_id
            for edge in self.edges
            if edge.from_node_id not in declared_nodes
            or edge.to_node_id not in declared_nodes
        )
        if dangling_edges:
            raise ValueError(
                "authority graph contains dangling edges: " + ", ".join(dangling_edges)
            )

    def nodes_for_scope(self, authority_scope: str) -> tuple[AuthorityNode, ...]:
        """Return nodes for one exact declared authority scope."""
        if not authority_scope.strip():
            raise ValueError("authority scope is required")
        return tuple(
            node for node in self.nodes if node.authority_scope == authority_scope
        )

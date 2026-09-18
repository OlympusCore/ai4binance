"""Small deterministic evidence graph."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.external_intel.core.models import (
    EvidenceGraphEdge,
    EvidenceGraphNode,
)
from ai4binance.external_intel.core.validation import require_unique_text


@dataclass(frozen=True, slots=True)
class EvidenceGraph:
    nodes: tuple[EvidenceGraphNode, ...] = ()
    edges: tuple[EvidenceGraphEdge, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        node_ids = tuple(node.node_id for node in self.nodes)
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        require_unique_text("evidence graph nodes", node_ids)
        require_unique_text("evidence graph edges", edge_ids)
        node_set = frozenset(node_ids)
        if any(
            edge.source_node_id not in node_set or edge.target_node_id not in node_set
            for edge in self.edges
        ):
            raise ValueError("evidence graph edge references an unknown node")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("evidence graph cannot grant authority")

    def add_node(self, node: EvidenceGraphNode) -> EvidenceGraph:
        return EvidenceGraph((*self.nodes, node), self.edges)

    def add_edge(self, edge: EvidenceGraphEdge) -> EvidenceGraph:
        return EvidenceGraph(self.nodes, (*self.edges, edge))

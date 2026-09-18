"""Compatibility-preserving authority-graph access to the existing resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai4binance.governance.authority.graph import AuthorityGraph

if TYPE_CHECKING:
    from ai4binance.governance.authority_resolution import AuthorityResolution


def resolve_graph_authority(
    graph: AuthorityGraph,
    authority_scope: str,
) -> AuthorityResolution:
    """Resolve one graph scope through the established public resolver."""
    from ai4binance.governance.authority_resolution import (
        AuthorityCandidate,
        resolve_authority,
    )

    return resolve_authority(
        authority_scope,
        tuple(
            AuthorityCandidate(
                artifact_id=node.document_id,
                authority_scope=node.authority_scope,
                authority_layer=node.authority_layer,
                lifecycle_status=node.lifecycle_status,
                source_of_truth=node.source_of_truth,
                canonical_path=node.canonical_path,
            )
            for node in graph.nodes_for_scope(authority_scope)
        ),
    )

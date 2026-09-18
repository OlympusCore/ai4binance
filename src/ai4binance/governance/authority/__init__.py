"""Typed, read-only contracts for the canonical authority graph."""

from ai4binance.governance.authority.conflicts import (
    AuthorityConflict,
    AuthorityConflictKind,
    detect_authority_conflicts,
)
from ai4binance.governance.authority.development import (
    DEFAULT_AUTHORITY_LAYER_DEVELOPMENT_MATRIX_PATH,
    AuthorityDevelopmentGroup,
    AuthorityLayerDevelopment,
    AuthorityLayerDevelopmentFinding,
    AuthorityLayerDevelopmentMatrix,
    load_authority_layer_development_matrix,
    validate_authority_graph_layer_development,
)
from ai4binance.governance.authority.documentation import (
    render_authority_graph_markdown,
    write_runtime_authority_graph_markdown,
)
from ai4binance.governance.authority.external import (
    DEFAULT_EXTERNAL_AUTHORITY_REGISTRY_PATH,
    ExternalApplicabilityStatus,
    ExternalAuthorityEffect,
    ExternalAuthorityEntry,
    ExternalAuthorityKind,
    ExternalAuthorityRegistry,
    ExternalSourceStatus,
    load_external_authority_registry,
)
from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.impact import (
    AuthorityImpact,
    analyze_authority_impact,
)
from ai4binance.governance.authority.loader import (
    DEFAULT_AUTHORITY_GRAPH_PATH,
    load_authority_graph,
)
from ai4binance.governance.authority.metadata import (
    AuthorityMetadataFinding,
    AuthorityMetadataFindingKind,
    validate_authority_graph_metadata,
)
from ai4binance.governance.authority.model import (
    AUTHORITY_EFFECTS,
    AUTHORITY_LAYERS,
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityNode,
    AuthorityRelation,
    authority_edge_family,
)
from ai4binance.governance.authority.resolution import resolve_graph_authority

__all__ = (
    "AUTHORITY_EFFECTS",
    "AUTHORITY_LAYERS",
    "DEFAULT_AUTHORITY_GRAPH_PATH",
    "DEFAULT_AUTHORITY_LAYER_DEVELOPMENT_MATRIX_PATH",
    "DEFAULT_EXTERNAL_AUTHORITY_REGISTRY_PATH",
    "AuthorityConflict",
    "AuthorityConflictKind",
    "AuthorityDevelopmentGroup",
    "AuthorityEdge",
    "AuthorityEdgeFamily",
    "AuthorityGraph",
    "AuthorityImpact",
    "AuthorityLayerDevelopment",
    "AuthorityLayerDevelopmentFinding",
    "AuthorityLayerDevelopmentMatrix",
    "AuthorityMetadataFinding",
    "AuthorityMetadataFindingKind",
    "AuthorityNode",
    "AuthorityRelation",
    "ExternalApplicabilityStatus",
    "ExternalAuthorityEffect",
    "ExternalAuthorityEntry",
    "ExternalAuthorityKind",
    "ExternalAuthorityRegistry",
    "ExternalSourceStatus",
    "analyze_authority_impact",
    "authority_edge_family",
    "detect_authority_conflicts",
    "load_authority_graph",
    "load_authority_layer_development_matrix",
    "load_external_authority_registry",
    "render_authority_graph_markdown",
    "resolve_graph_authority",
    "validate_authority_graph_layer_development",
    "validate_authority_graph_metadata",
    "write_runtime_authority_graph_markdown",
)

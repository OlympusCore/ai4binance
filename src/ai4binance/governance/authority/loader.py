"""Load the local, non-authoritative authority-graph registry fail-closed."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml

from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.model import (
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityNode,
    AuthorityRelation,
)
from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

DEFAULT_AUTHORITY_GRAPH_PATH = Path("docs/registries/registry_authority_graph.yaml")
_AUTHORITY_GRAPH_SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/authority_graph.schema.json"
)


def load_authority_graph(
    path: Path = DEFAULT_AUTHORITY_GRAPH_PATH,
    *,
    schema_root: Path | None = None,
) -> AuthorityGraph:
    """Load and validate a local authority graph without network resolution."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"authority graph cannot be loaded: {path}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("authority graph must be a mapping")
    selected_schema_root = schema_root or Path(__file__).parents[4] / "schemas"
    try:
        OfflineSchemaRegistry.from_directory(selected_schema_root).validate(
            _AUTHORITY_GRAPH_SCHEMA_ID, payload
        )
    except SchemaValidationError as error:
        raise ValueError("authority graph schema validation failed") from error
    typed_payload = cast(Mapping[str, object], payload)
    return AuthorityGraph(
        graph_id=_required_string(typed_payload, "graph_id"),
        version=_required_string(typed_payload, "version"),
        status=_required_string(typed_payload, "status"),
        source_of_truth=_required_bool(typed_payload, "source_of_truth"),
        execution_allowed=_required_bool(typed_payload, "execution_allowed"),
        live_eligibility_status=_required_string(
            typed_payload, "live_eligibility_status"
        ),
        nodes=tuple(
            _node_from_payload(item) for item in _required_list(typed_payload, "nodes")
        ),
        edges=tuple(
            _edge_from_payload(item) for item in _required_list(typed_payload, "edges")
        ),
    )


def _node_from_payload(value: object) -> AuthorityNode:
    payload = _required_mapping(value, "authority node")
    return AuthorityNode(
        node_id=_required_string(payload, "node_id"),
        document_id=_required_string(payload, "document_id"),
        canonical_path=_required_string(payload, "canonical_path"),
        authority_layer=_required_string(payload, "authority_layer"),
        authority_effect=_required_string(payload, "authority_effect"),
        authority_scope=_required_string(payload, "authority_scope"),
        lifecycle_status=_required_string(payload, "lifecycle_status"),
        content_role=_required_string(payload, "content_role"),
        source_of_truth=_required_bool(payload, "source_of_truth"),
        source_of_truth_scope=_required_string(payload, "source_of_truth_scope"),
    )


def _edge_from_payload(value: object) -> AuthorityEdge:
    payload = _required_mapping(value, "authority edge")
    return AuthorityEdge(
        edge_id=_required_string(payload, "edge_id"),
        from_node_id=_required_string(payload, "from_node_id"),
        to_node_id=_required_string(payload, "to_node_id"),
        relation=AuthorityRelation(_required_string(payload, "relation")),
        edge_family=AuthorityEdgeFamily(_required_string(payload, "edge_family")),
    )


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _required_list(payload: Mapping[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"authority graph {key} must be a list")
    return value


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"authority graph {key} is required")
    return value


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"authority graph {key} must be boolean")
    return value

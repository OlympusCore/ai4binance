"""Deterministic authority-layer development responsibilities and guardrails."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from ai4binance.governance.authority.graph import AuthorityGraph
from ai4binance.governance.authority.model import AUTHORITY_EFFECTS, AUTHORITY_LAYERS
from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

DEFAULT_AUTHORITY_LAYER_DEVELOPMENT_MATRIX_PATH = Path(
    "config/governance/authority_layer_development_matrix.yaml"
)
_SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/"
    "authority_layer_development_matrix.schema.json"
)


@dataclass(frozen=True, slots=True)
class AuthorityDevelopmentGroup:
    """One non-authoritative development responsibility group."""

    group_id: str
    development_responsibility: str

    def __post_init__(self) -> None:
        if not self.group_id.strip() or not self.development_responsibility.strip():
            raise ValueError("authority development group metadata is required")


@dataclass(frozen=True, slots=True)
class AuthorityLayerDevelopment:
    """Guardrails for one authority layer without granting runtime permission."""

    authority_layer: str
    group_id: str
    allowed_authority_effects: tuple[str, ...]
    source_of_truth_allowed: bool

    def __post_init__(self) -> None:
        if self.authority_layer not in AUTHORITY_LAYERS:
            raise ValueError("authority development layer is invalid")
        if not self.group_id.strip():
            raise ValueError("authority development group is required")
        if not self.allowed_authority_effects:
            raise ValueError("authority development effects are required")
        if len(set(self.allowed_authority_effects)) != len(
            self.allowed_authority_effects
        ):
            raise ValueError("authority development effects must be unique")
        if any(
            effect not in AUTHORITY_EFFECTS for effect in self.allowed_authority_effects
        ):
            raise ValueError("authority development effect is invalid")


@dataclass(frozen=True, slots=True)
class AuthorityLayerDevelopmentMatrix:
    """Validated L0-L10 development projection with no decision authority."""

    matrix_id: str
    version: str
    authority_scope: str
    groups: tuple[AuthorityDevelopmentGroup, ...]
    layers: tuple[AuthorityLayerDevelopment, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.matrix_id.strip() or not self.version.strip():
            raise ValueError("authority development matrix identity is required")
        if self.authority_scope != "authority_layer_development":
            raise ValueError("authority development matrix scope is invalid")
        group_ids = tuple(group.group_id for group in self.groups)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("authority development groups must be unique")
        layer_ids = tuple(layer.authority_layer for layer in self.layers)
        if len(set(layer_ids)) != len(layer_ids):
            raise ValueError("authority development layers must be unique")
        if set(layer_ids) != set(AUTHORITY_LAYERS):
            raise ValueError("authority development matrix must cover every layer")
        if any(layer.group_id not in group_ids for layer in self.layers):
            raise ValueError("authority development layer references an unknown group")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("authority development matrix cannot authorize execution")

    def development_for(self, authority_layer: str) -> AuthorityLayerDevelopment:
        """Return the single declared development policy for one known layer."""
        if authority_layer not in AUTHORITY_LAYERS:
            raise ValueError("authority development layer is invalid")
        return next(
            layer for layer in self.layers if layer.authority_layer == authority_layer
        )


@dataclass(frozen=True, slots=True)
class AuthorityLayerDevelopmentFinding:
    """A fail-closed graph deviation from the declared layer guardrails."""

    code: str
    path: str
    detail: str
    blockers: tuple[str, ...] = ("GOVERNANCE_CONFLICT", "LIVE_ORDER_BLOCKED")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.path.strip() or not self.detail.strip():
            raise ValueError("authority development finding metadata is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or "GOVERNANCE_CONFLICT" not in self.blockers
        ):
            raise ValueError("authority development findings cannot waive blockers")


def load_authority_layer_development_matrix(
    repository_root: Path,
) -> AuthorityLayerDevelopmentMatrix:
    """Load the schema-bound, non-authoritative L0-L10 development matrix."""
    root = repository_root.resolve()
    try:
        payload = yaml.safe_load(
            (root / DEFAULT_AUTHORITY_LAYER_DEVELOPMENT_MATRIX_PATH).read_text(
                encoding="utf-8"
            )
        )
        OfflineSchemaRegistry.from_directory(root / "schemas").validate(
            _SCHEMA_ID, payload
        )
    except (OSError, SchemaValidationError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError("authority development matrix validation failed") from error
    mapping = _mapping(payload, "authority development matrix")
    groups = tuple(
        AuthorityDevelopmentGroup(
            group_id=_string(item.get("group_id"), "group_id"),
            development_responsibility=_string(
                item.get("development_responsibility"), "development_responsibility"
            ),
        )
        for item in _list_of_mappings(mapping.get("groups"), "groups")
    )
    layers = tuple(
        AuthorityLayerDevelopment(
            authority_layer=_string(item.get("authority_layer"), "authority_layer"),
            group_id=_string(item.get("group_id"), "group_id"),
            allowed_authority_effects=_strings(
                item.get("allowed_authority_effects"), "allowed_authority_effects"
            ),
            source_of_truth_allowed=_boolean(
                item.get("source_of_truth_allowed"), "source_of_truth_allowed"
            ),
        )
        for item in _list_of_mappings(mapping.get("layers"), "layers")
    )
    safety = _mapping(mapping.get("safety"), "safety")
    return AuthorityLayerDevelopmentMatrix(
        matrix_id=_string(mapping.get("matrix_id"), "matrix_id"),
        version=_string(mapping.get("version"), "version"),
        authority_scope=_string(mapping.get("authority_scope"), "authority_scope"),
        groups=groups,
        layers=layers,
        execution_allowed=_boolean(
            safety.get("execution_allowed"), "execution_allowed"
        ),
        promotion_status=_string(safety.get("promotion_status"), "promotion_status"),
        live_eligibility_status=_string(
            safety.get("live_eligibility_status"), "live_eligibility_status"
        ),
    )


def validate_authority_graph_layer_development(
    graph: AuthorityGraph,
    matrix: AuthorityLayerDevelopmentMatrix,
) -> tuple[AuthorityLayerDevelopmentFinding, ...]:
    """Fail closed when a graph node exceeds its layer's declared responsibility."""
    findings: list[AuthorityLayerDevelopmentFinding] = []
    for node in graph.nodes:
        development = matrix.development_for(node.authority_layer)
        if node.authority_effect not in development.allowed_authority_effects:
            findings.append(
                AuthorityLayerDevelopmentFinding(
                    code="AUTHORITY_LAYER_EFFECT_VIOLATION",
                    path=node.canonical_path,
                    detail=(
                        f"{node.authority_layer} does not permit "
                        f"{node.authority_effect} for development group "
                        f"{development.group_id}."
                    ),
                )
            )
        if node.source_of_truth and not development.source_of_truth_allowed:
            findings.append(
                AuthorityLayerDevelopmentFinding(
                    code="AUTHORITY_LAYER_SOURCE_OF_TRUTH_FORBIDDEN",
                    path=node.canonical_path,
                    detail=(
                        f"{node.authority_layer} belongs to development group "
                        f"{development.group_id} and cannot create authority."
                    ),
                )
            )
    return tuple(sorted(findings, key=lambda finding: (finding.path, finding.code)))


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _list_of_mappings(value: object, name: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return tuple(_mapping(item, name) for item in value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(cast(list[str], value))


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value

"""Typed, read-only contracts for declared governed-knowledge authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

AUTHORITY_LAYERS: tuple[str, ...] = (
    "L0_EXTERNAL_MANDATORY_CONSTRAINTS",
    "L1_CORE_CONSTITUTION",
    "L2_GOVERNANCE_COMPLIANCE",
    "L3_CANONICAL_CONTRACTS_SCHEMAS",
    "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
    "L5_REGISTRIES_ROADMAP",
    "L6_ARCHITECTURE_ONTOLOGY_ADR",
    "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
    "L8_REPORTS_EVIDENCE_INVENTORIES",
    "L9_REFERENCES_TEMPLATES",
    "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS",
)

AUTHORITY_EFFECTS: tuple[str, ...] = (
    "MANDATORY_CONSTRAINT",
    "NORMATIVE_CONSTRAINT",
    "OPERATIONAL_SPECIALIZATION",
    "IMPLEMENTATION",
    "EVIDENCE_ONLY",
    "REFERENCE_ONLY",
    "ARCHIVE_ONLY",
)

_LOWER_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_ACTIVE_LIFECYCLE_STATUS = "ACTIVE"
_GENERATED_CONTENT_ROLE = "GENERATED"
_SOURCE_OF_TRUTH_CONTENT_ROLES = frozenset(
    {"AUTHORITATIVE", "OPERATIONAL", "POLICY_AS_CODE"}
)


class AuthorityEdgeFamily(StrEnum):
    """Relationship families with distinct validation semantics."""

    AUTHORITY = "AUTHORITY"
    LIFECYCLE = "LIFECYCLE"
    DEPENDENCY = "DEPENDENCY"


class AuthorityRelation(StrEnum):
    """Declared graph relationships; relation is not numeric precedence."""

    GOVERNS = "GOVERNS"
    SPECIALIZES = "SPECIALIZES"
    MUST_ALIGN_WITH = "MUST_ALIGN_WITH"
    SUPERSEDES = "SUPERSEDES"
    IMPLEMENTS = "IMPLEMENTS"
    ENFORCES = "ENFORCES"
    VALIDATES = "VALIDATES"
    EVIDENCES = "EVIDENCES"
    GENERATES = "GENERATES"
    DERIVED_FROM = "DERIVED_FROM"
    REFERENCES = "REFERENCES"
    AFFECTS = "AFFECTS"


_AUTHORITY_RELATIONS = frozenset(
    {
        AuthorityRelation.GOVERNS,
        AuthorityRelation.SPECIALIZES,
        AuthorityRelation.MUST_ALIGN_WITH,
    }
)
_LIFECYCLE_RELATIONS = frozenset({AuthorityRelation.SUPERSEDES})


def authority_edge_family(relation: AuthorityRelation) -> AuthorityEdgeFamily:
    """Return the validation family for one declared relation."""
    if relation in _AUTHORITY_RELATIONS:
        return AuthorityEdgeFamily.AUTHORITY
    if relation in _LIFECYCLE_RELATIONS:
        return AuthorityEdgeFamily.LIFECYCLE
    return AuthorityEdgeFamily.DEPENDENCY


@dataclass(frozen=True, slots=True)
class AuthorityNode:
    """Read-only declaration of authority metadata for one governed artifact."""

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

    def __post_init__(self) -> None:
        for value in (
            self.node_id,
            self.document_id,
            self.canonical_path,
            self.authority_layer,
            self.authority_effect,
            self.authority_scope,
            self.lifecycle_status,
            self.content_role,
            self.source_of_truth_scope,
        ):
            if not value.strip():
                raise ValueError("authority node metadata is required")
        if self.canonical_path.startswith("/") or "\\" in self.canonical_path:
            raise ValueError("authority node path must be repository-relative posix")
        if self.authority_layer not in AUTHORITY_LAYERS:
            raise ValueError("authority node layer is invalid")
        if self.authority_effect not in AUTHORITY_EFFECTS:
            raise ValueError("authority node effect is invalid")
        if _LOWER_SNAKE_CASE_RE.fullmatch(self.authority_scope) is None:
            raise ValueError("authority node scope must use lower_snake_case")
        if _LOWER_SNAKE_CASE_RE.fullmatch(self.source_of_truth_scope) is None:
            raise ValueError(
                "authority node source-of-truth scope must use lower_snake_case"
            )
        if self.content_role == _GENERATED_CONTENT_ROLE and self.source_of_truth:
            raise ValueError("generated authority views cannot be sources of truth")
        if (
            self.source_of_truth
            and self.content_role not in _SOURCE_OF_TRUTH_CONTENT_ROLES
        ):
            raise ValueError(
                "source-of-truth authority nodes require authoritative content"
            )


@dataclass(frozen=True, slots=True)
class AuthorityEdge:
    """Read-only relationship between declared authority nodes."""

    edge_id: str
    from_node_id: str
    to_node_id: str
    relation: AuthorityRelation
    edge_family: AuthorityEdgeFamily

    def __post_init__(self) -> None:
        for value in (self.edge_id, self.from_node_id, self.to_node_id):
            if not value.strip():
                raise ValueError("authority edge metadata is required")
        if self.from_node_id == self.to_node_id:
            raise ValueError("authority edge cannot self-reference")
        expected_family = authority_edge_family(self.relation)
        if self.edge_family is not expected_family:
            raise ValueError("authority edge family must match its relation")

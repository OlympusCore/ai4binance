"""Deterministic semantic graph contracts with no calculation authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SemanticEntityType(StrEnum):
    ASSET = "ASSET"
    WALLET_BALANCE = "WALLET_BALANCE"
    SPOT_POSITION = "SPOT_POSITION"
    FUTURES_POSITION = "FUTURES_POSITION"
    CAPITAL_SOURCE = "CAPITAL_SOURCE"
    RISK_CONSTRAINT = "RISK_CONSTRAINT"
    BLOCKER = "BLOCKER"
    DGE_DECISION = "DGE_DECISION"


class SemanticRelationType(StrEnum):
    REPRESENTS = "REPRESENTS"
    HAS_BLOCKER = "HAS_BLOCKER"
    HAS_CAPITAL_SOURCE_STATUS = "HAS_CAPITAL_SOURCE_STATUS"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    GOVERNED_BY = "GOVERNED_BY"


@dataclass(frozen=True, slots=True)
class SemanticEntity:
    entity_id: str
    entity_type: SemanticEntityType
    label: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.label.strip():
            raise ValueError("semantic entity identity is required")
        _require_unique_nonblank("semantic entity evidence refs", self.evidence_refs)


@dataclass(frozen=True, slots=True)
class SemanticEdge:
    source_id: str
    target_id: str
    relation_type: SemanticRelationType
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.target_id.strip():
            raise ValueError("semantic edge identity is required")
        if self.source_id == self.target_id:
            raise ValueError("semantic edge cannot be self-referential")
        _require_unique_nonblank("semantic edge evidence refs", self.evidence_refs)


@dataclass(frozen=True, slots=True)
class SemanticGraphContract:
    graph_id: str
    entities: tuple[SemanticEntity, ...]
    edges: tuple[SemanticEdge, ...]
    blockers: tuple[str, ...]
    schema_version: str = "1.0"
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.graph_id.strip() or not self.schema_version.strip():
            raise ValueError("semantic graph identity is required")
        entity_ids = tuple(entity.entity_id for entity in self.entities)
        _require_unique_nonblank("semantic graph entity ids", entity_ids)
        _require_unique_nonblank("semantic graph blockers", self.blockers)
        known = frozenset(entity_ids)
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ValueError("semantic edge references an unknown entity")
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("semantic graph cannot promote or execute")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

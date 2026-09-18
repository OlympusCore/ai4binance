"""Builders that map typed evidence into shared semantic graph contracts."""

from __future__ import annotations

from hashlib import sha256

from ai4binance.ontology.contracts import (
    SemanticEdge,
    SemanticEntity,
    SemanticEntityType,
    SemanticGraphContract,
    SemanticRelationType,
)
from ai4binance.portfolio.position_context import (
    CapitalSourceStatus,
    PositionContextReport,
    PositionMarket,
)


def build_position_semantic_graph(
    report: PositionContextReport,
) -> SemanticGraphContract:
    """Map position context to graph facts without changing trading behavior."""
    entities: list[SemanticEntity] = []
    edges: list[SemanticEdge] = []
    blockers: list[str] = list(report.blockers)
    for index, record in enumerate(report.records, start=1):
        asset_id = f"asset:{record.asset}"
        position_type = (
            SemanticEntityType.SPOT_POSITION
            if record.market is PositionMarket.SPOT
            else SemanticEntityType.FUTURES_POSITION
        )
        position_id = (
            f"position:{record.market.value}:{record.symbol or record.asset}:{index}"
        )
        capital_id = f"capital_source:{record.capital_source_status.value}:{index}"
        _append_entity(
            entities,
            SemanticEntity(asset_id, SemanticEntityType.ASSET, record.asset),
        )
        entities.append(
            SemanticEntity(
                position_id,
                position_type,
                f"{record.market.value}:{record.asset}:{record.side.value}",
                record.evidence_refs,
            )
        )
        entities.append(
            SemanticEntity(
                capital_id,
                SemanticEntityType.CAPITAL_SOURCE,
                record.capital_source_status.value,
                record.evidence_refs,
            )
        )
        edges.append(
            SemanticEdge(
                position_id,
                asset_id,
                SemanticRelationType.REPRESENTS,
                record.evidence_refs,
            )
        )
        edges.append(
            SemanticEdge(
                position_id,
                capital_id,
                SemanticRelationType.HAS_CAPITAL_SOURCE_STATUS,
                record.evidence_refs,
            )
        )
        if record.capital_source_status in {
            CapitalSourceStatus.PROTECTED_REVIEW_REQUIRED,
            CapitalSourceStatus.REVIEWABLE_POSITION,
        }:
            edges.append(
                SemanticEdge(
                    capital_id,
                    position_id,
                    SemanticRelationType.REQUIRES_REVIEW,
                    record.evidence_refs,
                )
            )
        for blocker in record.blockers:
            blocker_id = f"blocker:{blocker}"
            _append_entity(
                entities,
                SemanticEntity(blocker_id, SemanticEntityType.BLOCKER, blocker),
            )
            edges.append(
                SemanticEdge(
                    position_id,
                    blocker_id,
                    SemanticRelationType.HAS_BLOCKER,
                    record.evidence_refs,
                )
            )
            blockers.append(blocker)
    graph_hash = sha256(
        "|".join(
            (
                *(entity.entity_id for entity in entities),
                *(
                    f"{edge.source_id}>{edge.relation_type.value}>{edge.target_id}"
                    for edge in edges
                ),
            )
        ).encode("utf-8")
    ).hexdigest()[:24]
    return SemanticGraphContract(
        graph_id=f"semantic-position:{graph_hash}",
        entities=tuple(entities),
        edges=tuple(edges),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _append_entity(entities: list[SemanticEntity], entity: SemanticEntity) -> None:
    if any(item.entity_id == entity.entity_id for item in entities):
        return
    entities.append(entity)

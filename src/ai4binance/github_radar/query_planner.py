"""Deterministic capability-gap query planning."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.github_radar.models import (
    LocalCapabilityAssessment,
    LocalCapabilityStatus,
    ResearchOntology,
)


@dataclass(frozen=True, slots=True)
class RadarQuery:
    capability_id: str
    query: str
    local_status: LocalCapabilityStatus


def plan_queries(
    ontology: ResearchOntology,
    baseline: tuple[LocalCapabilityAssessment, ...],
    *,
    capability_ids: tuple[str, ...] = (),
    maximum: int = 20,
) -> tuple[RadarQuery, ...]:
    if not 1 <= maximum <= 100:
        raise ValueError("Radar query maximum must be between 1 and 100")
    known = ontology.by_capability_id
    requested = capability_ids or tuple(known)
    unknown = set(requested) - set(known)
    if unknown:
        raise ValueError(f"unknown Radar capabilities: {sorted(unknown)}")
    statuses = {item.capability_id: item.status for item in baseline}
    priority = {
        LocalCapabilityStatus.RESEARCH_GAP: 0,
        LocalCapabilityStatus.DECLARED: 1,
        LocalCapabilityStatus.TESTED_CONTRACT: 2,
        LocalCapabilityStatus.RUNTIME_WIRED: 3,
        LocalCapabilityStatus.PRODUCTION_EVIDENCE: 4,
    }
    ordered = sorted(requested, key=lambda item: (priority[statuses[item]], item))
    return tuple(
        RadarQuery(
            capability_id=item,
            query=f"{known[item].search_query} language:Python archived:false",
            local_status=statuses[item],
        )
        for item in ordered[:maximum]
    )

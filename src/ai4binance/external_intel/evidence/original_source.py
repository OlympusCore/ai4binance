"""Original-source and copy-ratio assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ai4binance.external_intel.core.models import ExternalEvidence
from ai4binance.external_intel.core.validation import (
    require_aware,
    require_text,
    require_unique_text,
    require_unit_interval,
)


@dataclass(frozen=True, slots=True)
class OriginalSourceAssessment:
    earliest_seen_at: datetime
    earliest_known_source: str
    first_credible_source: str
    independent_source_count: int
    raw_source_count: int
    copy_ratio: float
    evidence_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_aware("earliest_seen_at", self.earliest_seen_at)
        require_text("earliest known source", self.earliest_known_source)
        require_text("first credible source", self.first_credible_source)
        if self.independent_source_count < 0 or self.raw_source_count < 0:
            raise ValueError("source counts cannot be negative")
        if self.independent_source_count > self.raw_source_count:
            raise ValueError("independent sources cannot exceed raw source count")
        require_unit_interval("copy ratio", self.copy_ratio)
        require_unique_text("original source evidence ids", self.evidence_ids)
        require_unique_text("original source blockers", self.blockers)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("original-source assessment cannot grant authority")


def assess_original_sources(
    evidence: tuple[ExternalEvidence, ...],
) -> OriginalSourceAssessment:
    if not evidence:
        raise ValueError("original-source assessment requires evidence")
    ordered = tuple(
        sorted(evidence, key=lambda item: (item.observed_at, item.source_uri))
    )
    origins = tuple(dict.fromkeys(item.author_or_origin for item in ordered))
    credible = tuple(item for item in ordered if item.reliability >= 0.6)
    independent = len(origins)
    raw_count = len(ordered)
    copy_ratio = 1.0 - (independent / raw_count) if raw_count else 1.0
    blockers: list[str] = []
    if independent < 2:
        blockers.append("INDEPENDENT_SOURCE_COUNT_LOW")
    if not credible:
        blockers.append("CREDIBLE_SOURCE_UNAVAILABLE")
    return OriginalSourceAssessment(
        earliest_seen_at=ordered[0].observed_at,
        earliest_known_source=ordered[0].source_uri,
        first_credible_source=(credible[0].source_uri if credible else "UNAVAILABLE"),
        independent_source_count=independent,
        raw_source_count=raw_count,
        copy_ratio=copy_ratio,
        evidence_ids=tuple(item.evidence_id for item in ordered),
        blockers=tuple(blockers),
    )

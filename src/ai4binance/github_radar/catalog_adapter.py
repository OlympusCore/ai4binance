"""One-way adapter from Radar evaluations to the governed research catalog."""

from __future__ import annotations

from datetime import datetime

from ai4binance.github_radar.models import ResearchUnitEvaluation
from ai4binance.research_catalog import CatalogStatus, ResearchCatalogEntry


def to_research_catalog_entry(
    evaluation: ResearchUnitEvaluation,
    *,
    observed_at: datetime,
) -> ResearchCatalogEntry:
    """Create a non-executable RESEARCH_ONLY catalog record."""
    blockers = tuple(
        dict.fromkeys(
            (
                *evaluation.blockers,
                "GITHUB_RADAR_RESEARCH_ONLY",
                "POC_REQUIRES_SEPARATE_HUMAN_APPROVAL",
                "EXTERNAL_CODE_INSTALL_BLOCKED",
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    return ResearchCatalogEntry(
        entry_id=evaluation.research_id,
        title=(
            f"GitHub Radar {evaluation.capability_id}: {evaluation.source.repository}"
        ),
        source_url=evaluation.source.url,
        source_revision=evaluation.source.pinned_revision,
        license_id=evaluation.source.license_id,
        hypothesis=(
            f"Assess {evaluation.source.repository} only for atomic capability "
            f"{evaluation.capability_id}; "
            f"recommendation={evaluation.recommendation.value}, "
            f"score={evaluation.total_score:.2f}."
        ),
        asset_classes=("Binance Spot research",),
        timeframes=("5m", "15m", "1h", "4h", "1d"),
        leakage_risks=evaluation.risks or ("LOOKAHEAD_STATUS_UNVERIFIED",),
        data_requirements=("PINNED_SOURCE_EVIDENCE", "LOCAL_REPRODUCTION_DATA"),
        cost_assumptions=("NO_EXTERNAL_CODE_EXECUTION", "NO_DEPENDENCY_INSTALL"),
        discovered_at=observed_at,
        updated_at=observed_at,
        status=CatalogStatus.RESEARCH_ONLY,
        blockers=blockers,
        execution_allowed=False,
    )

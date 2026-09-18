"""GitHub Radar integration with the existing Research Catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai4binance.github_radar.__main__ import _load_repository_evidence
from ai4binance.github_radar.engine import GitHubRadarEngine
from ai4binance.research_catalog import CatalogStatus


def test_engine_connects_evaluation_to_research_only_catalog() -> None:
    engine = GitHubRadarEngine.from_repository()
    result = engine.assess(
        _load_repository_evidence(
            Path("tests/fixtures/github_radar/repository_evidence.json")
        ),
        observed_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    entry = result.catalog_entry
    assert entry.entry_id == result.evaluation.research_id
    assert entry.status is CatalogStatus.RESEARCH_ONLY
    assert entry.execution_allowed is False
    assert "POC_REQUIRES_SEPARATE_HUMAN_APPROVAL" in entry.blockers
    assert "EXTERNAL_CODE_INSTALL_BLOCKED" in entry.blockers
    assert "LIVE_ORDER_BLOCKED" in entry.blockers
    assert result.catalog.entries == (entry,)

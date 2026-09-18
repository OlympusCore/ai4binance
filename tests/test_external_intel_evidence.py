from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.external_intel.core.enums import SourceType
from ai4binance.external_intel.core.models import ExternalEvidence
from ai4binance.external_intel.core.validation import hash_material
from ai4binance.external_intel.evidence.original_source import assess_original_sources
from ai4binance.external_intel.normalization.deduplication import (
    DuplicateCluster,
    cluster_duplicates,
)


def _evidence(
    evidence_id: str,
    source_uri: str,
    author: str,
    reliability: float,
    observed_at: datetime,
) -> ExternalEvidence:
    return ExternalEvidence(
        evidence_id=evidence_id,
        source_type=SourceType.NEWS_ARTICLE,
        source_uri=source_uri,
        observed_at=observed_at,
        content_sha256=hash_material(evidence_id),
        citation=source_uri,
        author_or_origin=author,
        reliability=reliability,
    )


def test_original_source_counts_independent_sources_not_reposts() -> None:
    now = datetime(2026, 8, 9, tzinfo=UTC)
    assessment = assess_original_sources(
        (
            _evidence("ev1", "https://source.test/a", "same-origin", 0.5, now),
            _evidence(
                "ev2",
                "https://copy.test/a",
                "same-origin",
                0.5,
                now + timedelta(minutes=1),
            ),
        )
    )

    assert assessment.raw_source_count == 2
    assert assessment.independent_source_count == 1
    assert "INDEPENDENT_SOURCE_COUNT_LOW" in assessment.blockers


def test_duplicate_clustering_reports_copy_ratio() -> None:
    clusters = cluster_duplicates(
        (
            ("ev1", "a", "HOT protocol upgrade https://example.test"),
            ("ev2", "b", "hot protocol upgrade https://copy.test"),
            ("ev3", "c", "different claim"),
        )
    )

    copied = next(item for item in clusters if item.raw_count == 2)
    assert copied.unique_author_count == 2
    assert copied.copy_ratio == 0.0


@pytest.mark.parametrize(
    ("raw_count", "author_count", "copy_ratio", "message"),
    [
        (0, 1, 0.0, "counts must be positive"),
        (1, 2, 0.0, "cannot exceed"),
        (1, 1, 1.1, "within zero and one"),
    ],
)
def test_duplicate_cluster_rejects_invalid_counts_and_ratios(
    raw_count: int, author_count: int, copy_ratio: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DuplicateCluster("claim", raw_count, author_count, ("evidence-1",), copy_ratio)

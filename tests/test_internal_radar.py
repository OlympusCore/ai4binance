"""Deterministic proofs for local-only internal image radar intake."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai4binance.internal_radar import run_internal_radar_once


def test_internal_radar_persists_redacted_new_image_candidate(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    (source / "private-name.jpg").write_bytes(b"not-an-image-but-bounded-fixture")

    result = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        observed_at=datetime(2026, 9, 18, tzinfo=UTC),
    )

    payload = result.to_payload()
    assert result.new_candidate_count == 1
    assert result.review_candidate_count == 1
    assert "VISION_ANALYZER_NOT_CONFIGURED" in result.blockers
    assert result.latest_path.is_file()
    candidate = payload["candidates"][0]
    assert isinstance(candidate, dict)
    assert "private-name" not in str(candidate)
    assert "relative_path" not in candidate
    assert payload["privacy"]["source_images_copied"] is False
    assert payload["execution_allowed"] is False


def test_internal_radar_deduplicates_unchanged_image(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    (source / "item.png").write_bytes(b"fixture")

    run_internal_radar_once(repository_root=tmp_path, source_root=source)
    result = run_internal_radar_once(repository_root=tmp_path, source_root=source)

    assert result.scanned_count == 1
    assert result.new_candidate_count == 0
    assert result.review_candidate_count == 1
    assert len(result.candidates) == 1
    assert "NO_NEW_INTERNAL_IMAGE_CANDIDATE" in result.blockers


def test_internal_radar_fails_closed_without_opt_in_source(tmp_path: Path) -> None:
    result = run_internal_radar_once(repository_root=tmp_path, source_root=None)

    assert result.status == "NOT_CONFIGURED"
    assert result.blockers == ("INTERNAL_RADAR_SOURCE_NOT_CONFIGURED",)
    assert result.to_payload()["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

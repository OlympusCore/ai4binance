"""Deterministic proofs for local-only internal image radar intake."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.governance.model_registry import build_advisory_inference_envelope
from ai4binance.internal_radar import run_internal_radar_once
from ai4binance.internal_radar_vision import VisionEvidence


def _payload_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _payload_candidates(payload: dict[str, object]) -> list[dict[str, object]]:
    value = payload["candidates"]
    assert isinstance(value, list)
    return cast(list[dict[str, object]], value)


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
    markdown = result.latest_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "# Internal Image Radar Scan Record" in markdown
    assert "Last scan timestamp (UTC): `2026-09-18T00:00:00+00:00`" in markdown
    assert "[private-name.jpg](file://" in markdown
    assert "NOT_ASSESSED_WITHOUT_CONFIGURED_VISION_ANALYZER" in markdown
    candidate = _payload_candidates(payload)[0]
    assert isinstance(candidate, dict)
    assert "private-name" not in str(candidate)
    privacy = _payload_mapping(payload, "privacy")
    assert privacy["source_paths_disclosed"] is False
    assert privacy["markdown_local_file_links_included"] is True
    assert payload["last_scan_timestamp_utc"] == "2026-09-18T00:00:00+00:00"
    assert "relative_path" not in candidate
    assert privacy["source_images_copied"] is False
    assert payload["execution_allowed"] is False


def test_internal_radar_vision_mode_persists_blocked_evidence_without_image_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    (source / "private-name.jpg").write_bytes(b"bounded-fixture")

    class BlockingVisionRunner:
        def analyze(self, **kwargs: object) -> VisionEvidence:
            source_hash = str(kwargs["source_content_sha256"])
            return VisionEvidence(
                candidate_id=str(kwargs["candidate_id"]),
                source_content_sha256=source_hash,
                status="BLOCKED",
                image_category=None,
                system_contribution=None,
                benefit_categories=(),
                tradeoff_categories=(),
                extracted_text_present=None,
                uncertainty_categories=(),
                confidence=None,
                blockers=("UNREGISTERED_MODEL:local-llamacpp-qwen25vl-3b",),
                inference_envelope=build_advisory_inference_envelope(
                    canonical_model_id="local-llamacpp-qwen25vl-3b",
                    model_version="Qwen2.5-VL-3B-Instruct-Q4_K_M",
                    task_type="LOCAL_IMAGE_ADVISORY_ANALYSIS",
                    prompt_sha256="a" * 64,
                    source_content_sha256=(source_hash,),
                ),
                route_decision=None,
            )

    result = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=BlockingVisionRunner(),  # type: ignore[arg-type]
    )

    payload = result.to_payload()
    candidate = _payload_candidates(payload)[0]
    assert isinstance(candidate, dict)
    assert candidate["assessment_status"] == "BLOCKED"
    assert "private-name" not in str(candidate)
    assert "UNREGISTERED_MODEL:local-llamacpp-qwen25vl-3b" in result.blockers
    assert _payload_mapping(payload, "privacy")["source_images_copied"] is False


def test_internal_radar_vision_summary_only_counts_validated_observations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    (source / "dashboard.jpg").write_bytes(b"bounded-fixture")

    class ObservedVisionRunner:
        def analyze(self, **kwargs: object) -> VisionEvidence:
            source_hash = str(kwargs["source_content_sha256"])
            return VisionEvidence(
                candidate_id=str(kwargs["candidate_id"]),
                source_content_sha256=source_hash,
                status="OBSERVED_UNVERIFIED",
                image_category="DASHBOARD",
                system_contribution="RELEVANT",
                benefit_categories=("OPERATIONAL_VISIBILITY",),
                tradeoff_categories=("HUMAN_REVIEW_REQUIRED",),
                extracted_text_present=True,
                uncertainty_categories=("OCR_UNCERTAIN",),
                confidence=0.75,
                blockers=("VISION_OBSERVATION_REQUIRES_HUMAN_REVIEW",),
                inference_envelope=build_advisory_inference_envelope(
                    canonical_model_id="local-llamacpp-qwen25vl-3b",
                    model_version="Qwen2.5-VL-3B-Instruct-Q4_K_M",
                    task_type="LOCAL_IMAGE_ADVISORY_ANALYSIS",
                    prompt_sha256="b" * 64,
                    source_content_sha256=(source_hash,),
                ),
                route_decision=None,
            )

    result = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=ObservedVisionRunner(),  # type: ignore[arg-type]
    )

    payload = result.to_payload()
    summary = _payload_mapping(payload, "vision_summary")
    assert summary["observed_count"] == 1
    assert summary["benefit_categories"] == {"OPERATIONAL_VISIBILITY": 1}
    assert summary["tradeoff_categories"] == {"HUMAN_REVIEW_REQUIRED": 1}
    progress = payload["vision_progress"]
    assert progress == {"analysed": 1, "awaiting_analysis": 0}
    candidate = _payload_candidates(payload)[0]
    assert isinstance(candidate, dict)
    assert str(candidate["last_scan_timestamp_utc"]).endswith("+00:00")
    markdown = result.latest_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "Last scan timestamp (UTC)" in markdown


def test_internal_radar_vision_processes_every_pending_candidate_once(
    tmp_path: Path,
) -> None:
    source = tmp_path / "images"
    source.mkdir()
    for index in range(4):
        (source / f"image-{index}.jpg").write_bytes(f"fixture-{index}".encode())

    class CountingVisionRunner:
        def __init__(self) -> None:
            self.candidate_ids: list[str] = []

        def analyze(self, **kwargs: object) -> VisionEvidence:
            candidate_id = str(kwargs["candidate_id"])
            self.candidate_ids.append(candidate_id)
            source_hash = str(kwargs["source_content_sha256"])
            return VisionEvidence(
                candidate_id=candidate_id,
                source_content_sha256=source_hash,
                status="BLOCKED",
                image_category=None,
                system_contribution=None,
                benefit_categories=(),
                tradeoff_categories=(),
                extracted_text_present=None,
                uncertainty_categories=(),
                confidence=None,
                blockers=("ADVISORY_ONLY",),
                inference_envelope=build_advisory_inference_envelope(
                    canonical_model_id="local-llamacpp-qwen25vl-3b",
                    model_version="Qwen2.5-VL-3B-Instruct-Q4_K_M",
                    task_type="LOCAL_IMAGE_ADVISORY_ANALYSIS",
                    prompt_sha256="c" * 64,
                    source_content_sha256=(source_hash,),
                ),
                route_decision=None,
            )

    runner = CountingVisionRunner()
    first = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=runner,  # type: ignore[arg-type]
    )
    second = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=runner,  # type: ignore[arg-type]
    )

    assert first.vision_analysis_count == 4
    assert second.vision_analysis_count == 0
    assert len(runner.candidate_ids) == 4


def test_internal_radar_reprocesses_legacy_vision_evidence_once(tmp_path: Path) -> None:
    source = tmp_path / "images"
    source.mkdir()
    (source / "image.jpg").write_bytes(b"fixture")

    class LegacyThenCurrentRunner:
        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, **kwargs: object) -> VisionEvidence:
            self.calls += 1
            source_hash = str(kwargs["source_content_sha256"])
            return VisionEvidence(
                candidate_id=str(kwargs["candidate_id"]),
                source_content_sha256=source_hash,
                status="OBSERVED_UNVERIFIED",
                image_category="ARCHITECTURE_DIAGRAM",
                system_contribution="POTENTIALLY_RELEVANT",
                benefit_categories=("ARCHITECTURE_CONTEXT",),
                tradeoff_categories=("HUMAN_REVIEW_REQUIRED",),
                extracted_text_present=True,
                uncertainty_categories=("CONTEXT_MISSING",),
                confidence=0.5,
                blockers=("ADVISORY_ONLY",),
                inference_envelope=build_advisory_inference_envelope(
                    canonical_model_id="local-llamacpp-qwen25vl-3b",
                    model_version="Qwen2.5-VL-3B-Instruct-Q4_K_M",
                    task_type="LOCAL_IMAGE_ADVISORY_ANALYSIS",
                    prompt_sha256="d" * 64,
                    source_content_sha256=(source_hash,),
                ),
                route_decision=None,
            )

    runner = LegacyThenCurrentRunner()
    first = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=runner,  # type: ignore[arg-type]
    )
    state_path = tmp_path / "runtime" / "state" / "internal_radar" / "known-images.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["pending_candidates"][0]["vision_evidence"]["schema_version"] = "1.0"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    second = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=runner,  # type: ignore[arg-type]
    )
    third = run_internal_radar_once(
        repository_root=tmp_path,
        source_root=source,
        vision_enabled=True,
        vision_runner=runner,  # type: ignore[arg-type]
    )

    assert first.vision_analysis_count == 1
    assert second.vision_analysis_count == 1
    assert third.vision_analysis_count == 0
    assert runner.calls == 2


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

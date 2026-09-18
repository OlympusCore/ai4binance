"""Local-only intake for image evidence supplied to the internal radar.

The radar deliberately stores fingerprints and bounded file metadata, never a
copy of the source image.  A visual inference adapter is intentionally not
implicit: until one is configured, images are reported as review candidates
rather than being given invented semantic conclusions.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from ai4binance.internal_radar_vision import LlamaCppVisionRunner
from ai4binance.storage import write_json_object_verified

_SUPPORTED_SUFFIXES: Final = frozenset(
    {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
)
_MAX_IMAGE_BYTES: Final = 25 * 1024 * 1024
_VISION_EVIDENCE_SCHEMA_VERSION: Final = "1.3"
_LATEST_CHECKPOINT_INTERVAL: Final = 25


@dataclass(frozen=True, slots=True)
class InternalRadarResult:
    """Secret-safe result of one bounded source-folder scan."""

    source_configured: bool
    status: str
    observed_at: datetime
    scanned_count: int
    new_candidate_count: int
    review_candidate_count: int
    vision_enabled: bool
    vision_analysis_count: int
    blockers: tuple[str, ...]
    state_path: Path
    latest_path: Path
    candidates: tuple[dict[str, object], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "command": "internal-radar-once",
            "source_configured": self.source_configured,
            "status": self.status,
            "observed_at": self.observed_at.isoformat(),
            "scanned_count": self.scanned_count,
            "new_candidate_count": self.new_candidate_count,
            "review_candidate_count": self.review_candidate_count,
            "vision_enabled": self.vision_enabled,
            "vision_analysis_count": self.vision_analysis_count,
            "vision_progress": _vision_progress(self.candidates),
            "vision_summary": _vision_summary(self.candidates),
            "candidates": list(self.candidates),
            "blockers": list(self.blockers),
            "state_path": str(self.state_path),
            "latest_path": str(self.latest_path),
            "markdown_record_path": str(self.latest_path.with_suffix(".md")),
            "privacy": {
                "source_images_copied": False,
                "source_paths_disclosed": False,
                "markdown_local_file_links_included": True,
                "exif_extracted": False,
                "visual_inference": (
                    "CONFIGURED" if self.vision_enabled else "NOT_CONFIGURED"
                ),
            },
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


def configured_source_root() -> Path | None:
    """Read the opt-in source directory without baking a machine path into code."""
    raw = os.environ.get("AI4BINANCE_INTERNAL_RADAR_SOURCE", "").strip()
    return Path(raw).expanduser() if raw else None


def include_existing_requested() -> bool:
    """Read the one-cycle local backfill request without making it persistent."""
    return (
        os.environ.get("AI4BINANCE_INTERNAL_RADAR_INCLUDE_EXISTING", "").strip() == "1"
    )


def vision_analysis_requested() -> bool:
    """Read the opt-in vision switch; model admission remains fail-closed."""
    return os.environ.get("AI4BINANCE_INTERNAL_RADAR_VISION_ENABLED", "").strip() == "1"


def run_internal_radar_once(
    *,
    repository_root: Path | None = None,
    source_root: Path | None = None,
    include_existing: bool = False,
    vision_enabled: bool = False,
    vision_runner: LlamaCppVisionRunner | None = None,
    observed_at: datetime | None = None,
) -> InternalRadarResult:
    """Scan one opt-in folder and persist only local, redacted review evidence."""
    root = (repository_root or Path.cwd()).resolve()
    now = observed_at or datetime.now(UTC)
    state_path = root / "runtime" / "state" / "internal_radar" / "known-images.json"
    latest_path = root / "runtime" / "artifacts" / "internal_radar" / "latest.json"
    configured_source = source_root or configured_source_root()
    if configured_source is None:
        return _persist_result(
            InternalRadarResult(
                False,
                "NOT_CONFIGURED",
                now,
                0,
                0,
                0,
                vision_enabled,
                0,
                ("INTERNAL_RADAR_SOURCE_NOT_CONFIGURED",),
                state_path,
                latest_path,
                (),
            )
        )
    try:
        source = configured_source.resolve(strict=True)
    except OSError:
        return _persist_result(
            InternalRadarResult(
                True,
                "BLOCKED",
                now,
                0,
                0,
                0,
                vision_enabled,
                0,
                ("INTERNAL_RADAR_SOURCE_UNAVAILABLE",),
                state_path,
                latest_path,
                (),
            )
        )
    if not source.is_dir():
        return _persist_result(
            InternalRadarResult(
                True,
                "BLOCKED",
                now,
                0,
                0,
                0,
                vision_enabled,
                0,
                ("INTERNAL_RADAR_SOURCE_NOT_DIRECTORY",),
                state_path,
                latest_path,
                (),
            )
        )

    known, pending, pending_state_present = _read_state(state_path)
    files, enumeration_blockers = _image_files(source)
    new_candidates: list[dict[str, object]] = []
    candidates_by_id: dict[str, Path] = {}
    next_known: set[str] = set()
    for path in files:
        candidate, fingerprint = _candidate(path, source)
        if fingerprint is None:
            continue
        next_known.add(fingerprint)
        candidates_by_id[str(candidate["candidate_id"])] = path
        if include_existing or not pending_state_present or fingerprint not in known:
            new_candidates.append(candidate)

    pending_by_id = {
        str(item["candidate_id"]): item
        for item in pending
        if isinstance(item.get("candidate_id"), str)
    }
    for candidate in new_candidates:
        pending_by_id.setdefault(str(candidate["candidate_id"]), candidate)

    vision_blockers: list[str] = []
    vision_analysis_count = 0
    if vision_enabled:
        runner = vision_runner or LlamaCppVisionRunner()
        for candidate_id in sorted(pending_by_id, key=str.casefold):
            candidate = pending_by_id[candidate_id]
            if _has_current_vision_evidence(candidate):
                continue
            source_path = candidates_by_id.get(candidate_id)
            content_sha256 = candidate.get("content_sha256")
            if source_path is None or not isinstance(content_sha256, str):
                continue
            evidence = runner.analyze(
                candidate_id=candidate_id,
                source_content_sha256=content_sha256,
                image_path=source_path,
            )
            vision_analysis_count += 1
            candidate["vision_evidence"] = evidence.to_payload()
            candidate["assessment_status"] = evidence.status
            candidate["system_benefit"] = evidence.system_contribution or "NOT_ASSESSED"
            candidate["system_tradeoff"] = (
                ",".join(evidence.tradeoff_categories)
                if evidence.tradeoff_categories
                else "NOT_ASSESSED"
            )
            candidate["recommendation"] = "HUMAN_REVIEW_REQUIRED"
            vision_blockers.extend(evidence.blockers)
            _write_state_checkpoint(
                state_path=state_path,
                observed_at=now,
                known_fingerprints=known | next_known,
                candidates=pending_by_id,
            )
            if vision_analysis_count % _LATEST_CHECKPOINT_INTERVAL == 0:
                checkpoint_candidates = tuple(
                    pending_by_id[key]
                    for key in sorted(pending_by_id, key=str.casefold)
                )
                _persist_result(
                    InternalRadarResult(
                        True,
                        "RUNNING_WITH_BLOCKERS",
                        now,
                        len(files),
                        len(new_candidates),
                        len(checkpoint_candidates),
                        True,
                        vision_analysis_count,
                        tuple(
                            dict.fromkeys(
                                (
                                    *enumeration_blockers,
                                    *vision_blockers,
                                    "VISION_ANALYSIS_IN_PROGRESS",
                                )
                            )
                        ),
                        state_path,
                        latest_path,
                        checkpoint_candidates,
                    ),
                    candidate_paths=candidates_by_id,
                )
    candidates = tuple(
        pending_by_id[key] for key in sorted(pending_by_id, key=str.casefold)
    )

    blockers = [*enumeration_blockers, *vision_blockers]
    if new_candidates and not vision_enabled:
        blockers.append("VISION_ANALYZER_NOT_CONFIGURED")
    if not new_candidates:
        blockers.append("NO_NEW_INTERNAL_IMAGE_CANDIDATE")
    result = InternalRadarResult(
        True,
        "RUNNING_WITH_BLOCKERS" if blockers else "READY",
        now,
        len(files),
        len(new_candidates),
        len(candidates),
        vision_enabled,
        vision_analysis_count,
        tuple(dict.fromkeys(blockers)),
        state_path,
        latest_path,
        candidates,
    )
    _write_state_checkpoint(
        state_path=state_path,
        observed_at=now,
        known_fingerprints=known | next_known,
        candidates=pending_by_id,
    )
    return _persist_result(result, candidate_paths=candidates_by_id)


def load_internal_radar_latest(repository_root: Path) -> dict[str, object]:
    """Load the secret-safe latest payload for YKB; malformed evidence fails closed."""
    path = repository_root / "runtime" / "artifacts" / "internal_radar" / "latest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "NOT_CONFIGURED",
            "new_candidate_count": 0,
            "review_candidate_count": 0,
            "blockers": ["INTERNAL_RADAR_EVIDENCE_UNAVAILABLE"],
            "latest_path": str(path),
        }
    if not isinstance(value, dict):
        return {
            "status": "BLOCKED",
            "new_candidate_count": 0,
            "review_candidate_count": 0,
            "blockers": ["INTERNAL_RADAR_EVIDENCE_INVALID"],
            "latest_path": str(path),
        }
    return value


def _vision_summary(candidates: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Aggregate only validated categorical vision evidence for YKB reporting."""
    contributions: dict[str, int] = {}
    benefits: dict[str, int] = {}
    tradeoffs: dict[str, int] = {}
    observed_count = 0
    for candidate in candidates:
        evidence = candidate.get("vision_evidence")
        if (
            not isinstance(evidence, dict)
            or evidence.get("status") != "OBSERVED_UNVERIFIED"
        ):
            continue
        observed_count += 1
        _count_text(contributions, evidence.get("system_contribution"))
        _count_texts(benefits, evidence.get("benefit_categories"))
        _count_texts(tradeoffs, evidence.get("tradeoff_categories"))
    return {
        "observed_count": observed_count,
        "contributions": contributions,
        "benefit_categories": benefits,
        "tradeoff_categories": tradeoffs,
    }


def _vision_progress(candidates: tuple[dict[str, object], ...]) -> dict[str, int]:
    """Return persisted, restart-safe progress without inferring semantic success."""
    analysed = sum(
        1 for candidate in candidates if _has_current_vision_evidence(candidate)
    )
    return {"analysed": analysed, "awaiting_analysis": len(candidates) - analysed}


def _has_current_vision_evidence(candidate: dict[str, object]) -> bool:
    evidence = candidate.get("vision_evidence")
    return (
        isinstance(evidence, dict)
        and evidence.get("schema_version") == _VISION_EVIDENCE_SCHEMA_VERSION
    )


def _write_state_checkpoint(
    *,
    state_path: Path,
    observed_at: datetime,
    known_fingerprints: set[str],
    candidates: dict[str, dict[str, object]],
) -> None:
    """Persist every completed local observation so interruption cannot lose it."""
    write_json_object_verified(
        state_path,
        {
            "schema_version": 1,
            "observed_at": observed_at.isoformat(),
            "known_fingerprints": sorted(known_fingerprints),
            "pending_candidates": [
                candidates[key] for key in sorted(candidates, key=str.casefold)
            ],
            "source_configured": True,
        },
        blocker="INTERNAL_RADAR_STATE_WRITE_FAILED",
        subject_id="internal-radar-state",
        indent=2,
    )


def _count_text(counts: dict[str, int], value: object) -> None:
    if isinstance(value, str) and value:
        counts[value] = counts.get(value, 0) + 1


def _count_texts(counts: dict[str, int], value: object) -> None:
    if isinstance(value, list):
        for item in value:
            _count_text(counts, item)


def _persist_result(
    result: InternalRadarResult,
    *,
    candidate_paths: dict[str, Path] | None = None,
) -> InternalRadarResult:
    write_json_object_verified(
        result.latest_path,
        result.to_payload(),
        blocker="INTERNAL_RADAR_LATEST_WRITE_FAILED",
        subject_id="internal-radar-latest",
        indent=2,
    )
    _write_markdown_record(result, candidate_paths=candidate_paths)
    return result


def _write_markdown_record(
    result: InternalRadarResult,
    *,
    candidate_paths: dict[str, Path] | None = None,
) -> None:
    """Persist a local scan record with explicit local Markdown file links."""

    summary = _vision_summary(result.candidates)
    lines = [
        "# Internal Image Radar Scan Record",
        "",
        f"- Observed at (UTC): `{result.observed_at.isoformat()}`",
        f"- Status: `{result.status}`",
        f"- Scanned images: `{result.scanned_count}`",
        f"- New candidates: `{result.new_candidate_count}`",
        f"- Machine analyses in this scan: `{result.vision_analysis_count}`",
        f"- Pending review candidates: `{result.review_candidate_count}`",
        "- Authority: `RESEARCH_ONLY`; `LIVE_ORDER_BLOCKED`.",
        (
            "- Privacy: source images, EXIF, and raw OCR text are not included. "
            "Local file names and file links exist only in this Markdown record."
        ),
        "",
        "## System Contribution Summary",
        "",
        f"- Relevant observations: `{summary['observed_count']}`",
        f"- Contributions: `{_markdown_count_summary(summary['contributions'])}`",
        f"- Benefits: `{_markdown_count_summary(summary['benefit_categories'])}`",
        f"- Trade-offs: `{_markdown_count_summary(summary['tradeoff_categories'])}`",
        f"- Blockers: `{', '.join(result.blockers) or '-'}`",
        "",
        "## Candidate Assessments",
        "",
        (
            "| Image | Candidate ID | Machine status | System contribution | "
            "Benefits | Trade-offs | Confidence |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in result.candidates:
        evidence = candidate.get("vision_evidence")
        vision = evidence if isinstance(evidence, dict) else {}
        benefits = _markdown_categories(vision.get("benefit_categories"))
        tradeoffs = _markdown_categories(vision.get("tradeoff_categories"))
        confidence = vision.get("confidence")
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_image_link(
                        candidate_paths,
                        candidate.get("candidate_id"),
                    ),
                    _markdown_cell(candidate.get("candidate_id")),
                    _markdown_cell(candidate.get("assessment_status")),
                    _markdown_cell(candidate.get("system_benefit")),
                    benefits,
                    tradeoffs,
                    _markdown_cell(confidence),
                )
            )
            + " |"
        )
    path = result.latest_path.with_suffix(".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = "\n".join(lines) + "\n"
    path.write_text(expected, encoding="utf-8", newline="\n")
    if path.read_text(encoding="utf-8") != expected:
        raise OSError("INTERNAL_RADAR_MARKDOWN_WRITE_FAILED")


def _markdown_count_summary(value: object) -> str:
    if not isinstance(value, dict):
        return "-"
    items = sorted(
        (str(key), count)
        for key, count in value.items()
        if isinstance(key, str) and isinstance(count, int) and count > 0
    )
    return ", ".join(f"{key}={count}" for key, count in items) or "-"


def _markdown_categories(value: object) -> str:
    if not isinstance(value, list):
        return "-"
    return ", ".join(_markdown_cell(item) for item in value) or "-"


def _markdown_cell(value: object) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _markdown_image_link(
    candidate_paths: dict[str, Path] | None,
    candidate_id: object,
) -> str:
    if candidate_paths is None or not isinstance(candidate_id, str):
        return "NOT_AVAILABLE"
    source_path = candidate_paths.get(candidate_id)
    if source_path is None:
        return "NOT_AVAILABLE"
    return f"[{_markdown_cell(source_path.name)}]({source_path.resolve().as_uri()})"


def _read_state(
    path: Path,
) -> tuple[set[str], tuple[dict[str, object], ...], bool]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("known_fingerprints", ()) if isinstance(payload, dict) else ()
        known = {item for item in raw if isinstance(item, str) and len(item) == 64}
        raw_pending = (
            payload.get("pending_candidates", ()) if isinstance(payload, dict) else ()
        )
        pending = tuple(item for item in raw_pending if isinstance(item, dict))
        pending_state_present = (
            isinstance(payload, dict) and "pending_candidates" in payload
        )
        return known, pending, pending_state_present
    except (OSError, json.JSONDecodeError):
        return set(), (), False


def _image_files(source: Path) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    candidates: list[Path] = []
    blockers: list[str] = []
    try:
        for path in source.rglob("*"):
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix.casefold() not in _SUPPORTED_SUFFIXES
            ):
                continue
            try:
                path.resolve().relative_to(source)
            except ValueError:
                blockers.append("INTERNAL_RADAR_PATH_ESCAPE_REJECTED")
                continue
            candidates.append(path)
    except OSError:
        blockers.append("INTERNAL_RADAR_SOURCE_ENUMERATION_FAILED")
    return tuple(
        sorted(candidates, key=lambda item: item.as_posix().casefold())
    ), tuple(dict.fromkeys(blockers))


def _candidate(path: Path, source: Path) -> tuple[dict[str, object], str | None]:
    try:
        before = path.stat()
        if before.st_size <= 0 or before.st_size > _MAX_IMAGE_BYTES:
            return {}, None
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        after = path.stat()
    except OSError:
        return {}, None
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        return {}, None
    relative = path.relative_to(source).as_posix()
    fingerprint = hashlib.sha256(f"{relative}:{digest}".encode()).hexdigest()
    return {
        "candidate_id": f"internal-image:{digest[:16]}",
        "content_sha256": digest,
        "relative_path_sha256": hashlib.sha256(relative.encode("utf-8")).hexdigest(),
        "format": path.suffix.casefold().lstrip("."),
        "byte_count": after.st_size,
        "modified_at": datetime.fromtimestamp(after.st_mtime, UTC).isoformat(),
        "assessment_status": "REVIEW_REQUIRED",
        "system_benefit": "NOT_ASSESSED_WITHOUT_CONFIGURED_VISION_ANALYZER",
        "system_tradeoff": "UNTRUSTED_LOCAL_IMAGE_REQUIRES_HUMAN_REVIEW_AND_PROVENANCE",
        "recommendation": "CONFIGURE_LOCAL_VISION_ANALYZER_OR_REVIEW_MANUALLY",
        "execution_allowed": False,
    }, fingerprint


def main() -> int:
    """Run the local radar as a small service entry point."""
    result = run_internal_radar_once(
        include_existing=include_existing_requested(),
        vision_enabled=vision_analysis_requested(),
    )
    print(json.dumps(result.to_payload(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())

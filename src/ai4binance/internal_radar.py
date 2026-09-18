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

from ai4binance.storage import write_json_object_verified

_SUPPORTED_SUFFIXES: Final = frozenset(
    {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
)
_MAX_FILES_PER_SCAN: Final = 2_500
_MAX_IMAGE_BYTES: Final = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class InternalRadarResult:
    """Secret-safe result of one bounded source-folder scan."""

    source_configured: bool
    status: str
    observed_at: datetime
    scanned_count: int
    new_candidate_count: int
    review_candidate_count: int
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
            "candidates": list(self.candidates),
            "blockers": list(self.blockers),
            "state_path": str(self.state_path),
            "latest_path": str(self.latest_path),
            "privacy": {
                "source_images_copied": False,
                "source_paths_disclosed": False,
                "exif_extracted": False,
                "visual_inference": "NOT_CONFIGURED",
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
        os.environ.get("AI4BINANCE_INTERNAL_RADAR_INCLUDE_EXISTING", "").strip()
        == "1"
    )


def run_internal_radar_once(
    *,
    repository_root: Path | None = None,
    source_root: Path | None = None,
    include_existing: bool = False,
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
                ("INTERNAL_RADAR_SOURCE_NOT_DIRECTORY",),
                state_path,
                latest_path,
                (),
            )
        )

    known, pending, pending_state_present = _read_state(state_path)
    files, enumeration_blockers = _image_files(source)
    new_candidates: list[dict[str, object]] = []
    next_known: set[str] = set()
    for path in files:
        candidate, fingerprint = _candidate(path, source)
        if fingerprint is None:
            continue
        next_known.add(fingerprint)
        if include_existing or not pending_state_present or fingerprint not in known:
            new_candidates.append(candidate)

    pending_by_id = {
        str(item["candidate_id"]): item
        for item in pending
        if isinstance(item.get("candidate_id"), str)
    }
    for candidate in new_candidates:
        pending_by_id[str(candidate["candidate_id"])] = candidate
    candidates = tuple(
        pending_by_id[key] for key in sorted(pending_by_id, key=str.casefold)
    )

    blockers = [*enumeration_blockers]
    if new_candidates:
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
        tuple(dict.fromkeys(blockers)),
        state_path,
        latest_path,
        candidates,
    )
    state_payload = {
        "schema_version": 1,
        "observed_at": now.isoformat(),
        "known_fingerprints": sorted(known | next_known),
        "pending_candidates": list(candidates),
        "source_configured": True,
    }
    write_json_object_verified(
        state_path,
        state_payload,
        blocker="INTERNAL_RADAR_STATE_WRITE_FAILED",
        subject_id="internal-radar-state",
        indent=2,
    )
    return _persist_result(result)


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


def _persist_result(result: InternalRadarResult) -> InternalRadarResult:
    write_json_object_verified(
        result.latest_path,
        result.to_payload(),
        blocker="INTERNAL_RADAR_LATEST_WRITE_FAILED",
        subject_id="internal-radar-latest",
        indent=2,
    )
    return result


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
            if len(candidates) >= _MAX_FILES_PER_SCAN:
                blockers.append("INTERNAL_RADAR_SCAN_LIMIT_REACHED")
                break
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
    result = run_internal_radar_once(include_existing=include_existing_requested())
    print(json.dumps(result.to_payload(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())

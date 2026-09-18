"""Deterministic, report-only runtime hygiene capacity and retention review."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.infrastructure.filesystem.runtime_artifacts.layout import (
    RuntimeArtifactLayoutManifest,
    RuntimeRetentionPolicy,
    load_runtime_artifact_layout_manifest,
)

_PROTECTED_SUBTREES = frozenset(
    {
        "runtime/dashboard/browser-profile",
        "runtime/state/private",
    }
)
_OUTPUT_ROOT = Path("runtime/artifacts/maintenance_archive/runtime_hygiene")


@dataclass(frozen=True, slots=True)
class RuntimeCapacityEntry:
    """Exact metadata-only capacity reading for one configured runtime root."""

    path: str
    file_count: int
    total_bytes: int
    oldest_modified_at_utc: str | None
    newest_modified_at_utc: str | None
    excluded_paths: tuple[str, ...]
    access_errors: tuple[str, ...]
    maximum_bytes: int
    delta_bytes: int | None

    @property
    def review_required(self) -> bool:
        return self.total_bytes > self.maximum_bytes or bool(self.access_errors)

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "oldest_modified_at_utc": self.oldest_modified_at_utc,
            "newest_modified_at_utc": self.newest_modified_at_utc,
            "excluded_paths": list(self.excluded_paths),
            "access_errors": list(self.access_errors),
            "maximum_bytes": self.maximum_bytes,
            "delta_bytes": self.delta_bytes,
            "review_required": self.review_required,
        }


@dataclass(frozen=True, slots=True)
class RetentionReviewEntry:
    """Non-destructive owner-review queue for a retention family."""

    policy_id: str
    path: str
    entry_kind: str
    minimum_age_days: int
    keep_latest: int
    observed_entry_count: int
    eligible_entry_count: int
    eligible_total_bytes: int

    def to_payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "path": self.path,
            "entry_kind": self.entry_kind,
            "minimum_age_days": self.minimum_age_days,
            "keep_latest": self.keep_latest,
            "observed_entry_count": self.observed_entry_count,
            "eligible_entry_count": self.eligible_entry_count,
            "eligible_total_bytes": self.eligible_total_bytes,
            "owner_review_required": self.eligible_entry_count > 0,
        }


def build_runtime_hygiene_report(
    repository_root: Path,
    *,
    observed_at: datetime,
    previous_payload: dict[str, object] | None = None,
    manifest: RuntimeArtifactLayoutManifest | None = None,
) -> dict[str, object]:
    """Build an exact, non-mutating hygiene report from governed settings."""
    root = repository_root.resolve()
    layout = manifest or load_runtime_artifact_layout_manifest(
        root / "config/governance/runtime_artifact_layout_manifest.json"
    )
    previous_sizes = _previous_sizes(previous_payload)
    capacities = tuple(
        _capacity_entry(
            root,
            path=path,
            maximum_bytes=maximum_bytes,
            previous_size=previous_sizes.get(path),
        )
        for path, maximum_bytes in sorted(layout.capacity_budgets.items())
    )
    reviews = tuple(
        _retention_review(root, policy_id, policy, observed_at)
        for policy_id, policy in sorted(layout.retention.items())
        if not policy.automatic_cleanup
    )
    review_required = any(entry.review_required for entry in capacities) or any(
        entry.eligible_entry_count > 0 for entry in reviews
    )
    return {
        "schema_version": "1.0",
        "artifact_origin": "runtime_hygiene_capacity_and_retention_review",
        "observed_at_utc": _timestamp(observed_at.timestamp()),
        "status": "OWNER_REVIEW_REQUIRED" if review_required else "PASS",
        "capacity": [entry.to_payload() for entry in capacities],
        "retention_review": [entry.to_payload() for entry in reviews],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def persist_runtime_hygiene_report(
    payload: dict[str, object], output_path: Path
) -> None:
    """Persist one report only under the governed runtime hygiene output root."""
    resolved_output = output_path.resolve()
    root = _repository_root_from_output(resolved_output)
    expected_root = (root / _OUTPUT_ROOT).resolve()
    if not _is_relative_to(resolved_output, expected_root):
        raise ValueError("runtime hygiene output must stay under maintenance archive")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _capacity_entry(
    repository_root: Path,
    *,
    path: str,
    maximum_bytes: int,
    previous_size: int | None,
) -> RuntimeCapacityEntry:
    root = repository_root / path
    file_count, total_bytes, oldest, newest, excluded, access_errors = _scan_exact(
        root, repository_root
    )
    return RuntimeCapacityEntry(
        path=path,
        file_count=file_count,
        total_bytes=total_bytes,
        oldest_modified_at_utc=_timestamp(oldest),
        newest_modified_at_utc=_timestamp(newest),
        excluded_paths=excluded,
        access_errors=access_errors,
        maximum_bytes=maximum_bytes,
        delta_bytes=None if previous_size is None else total_bytes - previous_size,
    )


def _scan_exact(
    root: Path, repository_root: Path
) -> tuple[int, int, float | None, float | None, tuple[str, ...], tuple[str, ...]]:
    if not root.is_dir():
        return 0, 0, None, None, (), ()
    stack = [root]
    file_count = 0
    total_bytes = 0
    oldest: float | None = None
    newest: float | None = None
    excluded: list[str] = []
    access_errors: list[str] = []
    while stack:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name.lower())
        except OSError:
            access_errors.append(current.relative_to(repository_root).as_posix())
            continue
        for entry in entries:
            try:
                relative_path = Path(entry.path).relative_to(repository_root).as_posix()
                if relative_path in _PROTECTED_SUBTREES:
                    excluded.append(relative_path)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                access_errors.append(
                    Path(entry.path).relative_to(repository_root).as_posix()
                )
                continue
            file_count += 1
            total_bytes += stat.st_size
            oldest = stat.st_mtime if oldest is None else min(oldest, stat.st_mtime)
            newest = stat.st_mtime if newest is None else max(newest, stat.st_mtime)
    return (
        file_count,
        total_bytes,
        oldest,
        newest,
        tuple(excluded),
        tuple(dict.fromkeys(access_errors)),
    )


def _retention_review(
    repository_root: Path,
    policy_id: str,
    policy: RuntimeRetentionPolicy,
    observed_at: datetime,
) -> RetentionReviewEntry:
    root = repository_root / policy.path
    entries = _review_entries(root, policy.entry_kind)
    ordered = sorted(entries, key=lambda item: item.stat().st_mtime, reverse=True)
    eligible = [
        item
        for index, item in enumerate(ordered)
        if index >= policy.keep_latest
        and (observed_at.timestamp() - item.stat().st_mtime)
        >= policy.minimum_age_days * 86400
    ]
    return RetentionReviewEntry(
        policy_id=policy_id,
        path=policy.path,
        entry_kind=policy.entry_kind,
        minimum_age_days=policy.minimum_age_days,
        keep_latest=policy.keep_latest,
        observed_entry_count=len(ordered),
        eligible_entry_count=len(eligible),
        eligible_total_bytes=sum(_entry_size(item) for item in eligible),
    )


def _review_entries(root: Path, entry_kind: str) -> list[Path]:
    if not root.is_dir():
        return []
    if entry_kind == "directory":
        return [item for item in root.iterdir() if item.is_dir()]
    return [
        item
        for item in root.rglob("*")
        if item.is_file() and item.suffix.lower() in {".jsonl", ".log"}
    ]


def _entry_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _previous_sizes(payload: dict[str, object] | None) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    capacity = payload.get("capacity")
    if not isinstance(capacity, list):
        return {}
    sizes: dict[str, int] = {}
    for entry in capacity:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        total_bytes = entry.get("total_bytes")
        if isinstance(path, str) and isinstance(total_bytes, int):
            sizes[path] = total_bytes
    return sizes


def _timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return (
        datetime.fromtimestamp(value, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _repository_root_from_output(output_path: Path) -> Path:
    for candidate in output_path.parents:
        if (candidate / "config").is_dir() and (candidate / "src").is_dir():
            return candidate
    raise ValueError("runtime hygiene output is not inside a repository root")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _load_previous(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-report", type=Path)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    previous = args.previous_report
    if previous is not None and not previous.is_absolute():
        previous = root / previous
    payload = build_runtime_hygiene_report(
        root,
        observed_at=datetime.now(UTC),
        previous_payload=_load_previous(previous),
    )
    persist_runtime_hygiene_report(payload, output)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Report-only folder structure audit with pytest-temp emphasis."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import cast
from uuid import uuid4

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified


class FolderRecommendation(StrEnum):
    """Review action for a discovered folder."""

    KEEP = "KEEP"
    CLEAN_AFTER_APPROVAL = "CLEAN_AFTER_APPROVAL"
    ARCHIVE_OR_CLEAN_AFTER_APPROVAL = "ARCHIVE_OR_CLEAN_AFTER_APPROVAL"
    REVIEW_MANUALLY = "REVIEW_MANUALLY"


@dataclass(frozen=True, slots=True)
class FolderAuditEntry:
    """One folder observed during the structure audit."""

    path: str
    classification: str
    recommendation: FolderRecommendation
    rationale: str
    gitignore_expected: bool
    exists: bool
    file_count: int | None = None
    directory_count: int | None = None
    total_bytes: int | None = None
    last_modified_at: datetime | None = None
    scan_error: str | None = None
    cleanup_probe_status: str = "NOT_CHECKED"
    delete_probe_status: str = "NOT_EXECUTED_REPORT_ONLY"
    acl_readable: bool | None = None
    exclusive_access: bool | None = None
    cleanup_blocker: str | None = None
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FolderCleanupRecommendation:
    """Human-reviewable cleanup proposal; never executed by this module."""

    priority: int
    title: str
    paths: tuple[str, ...]
    action: str
    safety_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FolderStructureAuditReport:
    """Persisted report-only outcome."""

    audit_id: str
    generated_at: datetime
    repository: str
    root_directory: str
    folders: tuple[FolderAuditEntry, ...]
    recommendations: tuple[FolderCleanupRecommendation, ...]
    blockers: tuple[str, ...]
    mode: str = "REPORT_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    schema_version: str = "1.1"


@dataclass(frozen=True, slots=True)
class FolderStructureAuditConfig:
    """Bounds for the folder audit."""

    repository_root: Path
    output_directory: Path
    stale_after_days: int = 7
    measure_file_limit: int = 50_000

    def __post_init__(self) -> None:
        if self.stale_after_days <= 0:
            raise ValueError("stale_after_days must be positive")
        if self.measure_file_limit <= 0:
            raise ValueError("measure_file_limit must be positive")


class FolderStructureAuditWriter:
    """Build and persist a non-destructive folder structure audit."""

    def __init__(self, config: FolderStructureAuditConfig) -> None:
        self._config = config

    def run(
        self, *, clock: Callable[[], datetime] | None = None
    ) -> FolderStructureAuditReport:
        """Inspect folder layout and persist latest JSON, Markdown, and JSONL."""
        now = clock or (lambda: datetime.now(UTC))
        generated_at = now()
        root = self._config.repository_root.resolve()
        if not root.is_dir():
            raise ValueError("repository_root must be an existing directory")
        output = self._config.output_directory.resolve()
        _ensure_inside_repository(root, output)
        output.mkdir(parents=True, exist_ok=True)

        folders = tuple(
            sorted(
                self._scan_folders(root, generated_at),
                key=lambda item: (item.recommendation.value, item.path.lower()),
            )
        )
        recommendations = _build_recommendations(folders)
        blockers = _build_blockers(folders)
        report = FolderStructureAuditReport(
            audit_id=f"folder-audit-{generated_at:%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}",
            generated_at=generated_at,
            repository=root.name,
            root_directory=str(root),
            folders=folders,
            recommendations=recommendations,
            blockers=blockers,
        )
        self._persist(output, report)
        return report

    def _scan_folders(
        self, root: Path, generated_at: datetime
    ) -> tuple[FolderAuditEntry, ...]:
        candidates = {path for path in root.iterdir() if path.is_dir()}
        nested = (
            root / "Artifacts" / "TestTemp",
            root / "Artifacts" / "maintenance-archive",
            root / "Artifacts" / "folder-structure-audit",
            root / "Backtest" / "validation",
            root / "State" / "private",
        )
        candidates.update(path for path in nested if path.is_dir())
        return tuple(self._entry_for(root, path, generated_at) for path in candidates)

    def _entry_for(
        self, root: Path, path: Path, generated_at: datetime
    ) -> FolderAuditEntry:
        relative = _relative_path(root, path)
        classification, recommendation, rationale, gitignore_expected = _classify_path(
            relative
        )
        measure = _should_measure(relative)
        file_count: int | None = None
        directory_count: int | None = None
        total_bytes: int | None = None
        last_modified_at: datetime | None = None
        scan_error: str | None = None
        cleanup_probe = _probe_cleanup_access(path, recommendation)
        blockers: tuple[str, ...] = ()
        if measure:
            measurement = _measure_tree(path, self._config.measure_file_limit)
            file_count = measurement.file_count
            directory_count = measurement.directory_count
            total_bytes = measurement.total_bytes
            last_modified_at = measurement.last_modified_at
            scan_error = measurement.scan_error
            blockers = _measurement_blockers(
                relative,
                recommendation,
                generated_at,
                self._config.stale_after_days,
                measurement,
                cleanup_probe,
            )
        elif cleanup_probe.cleanup_blocker is not None:
            blockers = (cleanup_probe.cleanup_blocker,)
        return FolderAuditEntry(
            path=relative,
            classification=classification,
            recommendation=recommendation,
            rationale=rationale,
            gitignore_expected=gitignore_expected,
            exists=path.exists(),
            file_count=file_count,
            directory_count=directory_count,
            total_bytes=total_bytes,
            last_modified_at=last_modified_at,
            scan_error=scan_error,
            cleanup_probe_status=cleanup_probe.status,
            delete_probe_status=cleanup_probe.delete_probe_status,
            acl_readable=cleanup_probe.acl_readable,
            exclusive_access=cleanup_probe.exclusive_access,
            cleanup_blocker=cleanup_probe.cleanup_blocker,
            blockers=blockers,
        )

    def _persist(self, output: Path, report: FolderStructureAuditReport) -> None:
        primitive = cast(dict[str, object], to_primitive(report))
        write_json_object_verified(
            output / "latest.json",
            primitive,
            blocker="FOLDER_STRUCTURE_AUDIT_WRITE_VERIFY_FAILED",
            subject_id=report.audit_id,
            indent=2,
        )
        (output / "latest.md").write_text(_render_markdown(report), encoding="utf-8")
        JsonlAuditStore(output / "runs.jsonl", durable=True).append_verified(
            AuditEvent(
                event_type="FOLDER_STRUCTURE_AUDIT_COMPLETED",
                timestamp=report.generated_at,
                snapshot_id=report.audit_id,
                payload={"report": report},
            )
        )


@dataclass(frozen=True, slots=True)
class _Measurement:
    file_count: int
    directory_count: int
    total_bytes: int
    last_modified_at: datetime | None
    scan_error: str | None


@dataclass(frozen=True, slots=True)
class _CleanupProbe:
    status: str
    delete_probe_status: str
    acl_readable: bool | None
    exclusive_access: bool | None
    cleanup_blocker: str | None


def _ensure_inside_repository(root: Path, path: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("output_directory must be inside repository_root") from error


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _classify_path(
    relative: str,
) -> tuple[str, FolderRecommendation, str, bool]:
    name = relative.replace("\\", "/")
    if _is_pytest_generated(name):
        return (
            "PYTEST_GENERATED_ARTIFACT",
            FolderRecommendation.CLEAN_AFTER_APPROVAL,
            (
                "pytest cache or historical pytest temp output; safe to remove "
                "when no pytest run is active"
            ),
            True,
        )
    if name == ".test-tmp":
        return (
            "GENERATED_TEST_TEMP",
            FolderRecommendation.CLEAN_AFTER_APPROVAL,
            "historical test temp output; safe to remove when no test run is active",
            True,
        )
    if name in {".mypy_cache", ".ruff_cache", "__pycache__"}:
        return (
            "TOOL_CACHE",
            FolderRecommendation.CLEAN_AFTER_APPROVAL,
            "local tool cache; reproducible and ignored",
            True,
        )
    if name in {".git", ".venv", ".agents", ".codex", ".github", ".vscode"}:
        return (
            "REPO_LOCAL_INFRASTRUCTURE",
            FolderRecommendation.KEEP,
            "repository or local development infrastructure",
            name in {".venv"},
        )
    if name in {"src", "tests", "Docs", "Scripts", "README"}:
        return (
            "SOURCE_OR_DOCUMENTATION",
            FolderRecommendation.KEEP,
            "source, tests, scripts, or documentation",
            False,
        )
    if name in {"Secrets", "State/private", "Models"}:
        return (
            "PROTECTED_LOCAL_STATE",
            FolderRecommendation.REVIEW_MANUALLY,
            "protected local state; do not delete in a broad cleanup",
            True,
        )
    if name == "skill-staging":
        return (
            "QUARANTINED_SKILL_STAGING",
            FolderRecommendation.REVIEW_MANUALLY,
            (
                "continuous-discovery skill drafts and admission records; "
                "keep quarantined until manual review and PR approval"
            ),
            True,
        )
    if name in {"Logs", "Artifacts/TestTemp", "Artifacts/maintenance-archive"}:
        return (
            "GENERATED_RUNTIME_ARTIFACT",
            FolderRecommendation.ARCHIVE_OR_CLEAN_AFTER_APPROVAL,
            "generated runtime or validation output",
            True,
        )
    if name.startswith("Artifacts/"):
        return (
            "GENERATED_ARTIFACT_SUBTREE",
            FolderRecommendation.REVIEW_MANUALLY,
            (
                "artifact subtree; inspect before cleanup because reports may "
                "be useful evidence"
            ),
            True,
        )
    if name == "Artifacts":
        return (
            "GENERATED_ARTIFACT_ROOT",
            FolderRecommendation.REVIEW_MANUALLY,
            "artifact root; clean only selected generated subfolders",
            True,
        )
    if name == "Backtest/validation":
        return (
            "RESEARCH_VALIDATION_ARTIFACT",
            FolderRecommendation.REVIEW_MANUALLY,
            "validation evidence; archive rather than delete unless obsolete",
            True,
        )
    if name in {"Data", "Backtest", "State", "Wallet", "Orders", "Opportunities"}:
        return (
            "DOMAIN_STATE_OR_EVIDENCE_ROOT",
            FolderRecommendation.REVIEW_MANUALLY,
            "domain state or evidence root; cleanup needs explicit scope",
            False,
        )
    return (
        "PROJECT_FOLDER",
        FolderRecommendation.REVIEW_MANUALLY,
        "unclassified project folder; inspect owner and freshness before cleanup",
        False,
    )


def _is_pytest_generated(relative: str) -> bool:
    return (
        relative == ".pytest_cache"
        or relative == ".pytest-tmp"
        or relative.startswith(".pytest-audit-temp")
        or relative.startswith(".pytest-money-audit-")
    )


def _should_measure(relative: str) -> bool:
    return _is_pytest_generated(relative) or relative in {
        ".mypy_cache",
        ".ruff_cache",
        ".test-tmp",
        "Artifacts/TestTemp",
        "Logs",
    }


def _measure_tree(path: Path, limit: int) -> _Measurement:
    file_count = 0
    directory_count = 0
    total_bytes = 0
    last_modified: datetime | None = None
    try:
        for item in path.rglob("*"):
            if item.is_dir():
                directory_count += 1
                continue
            if not item.is_file():
                continue
            file_count += 1
            stat = item.stat()
            total_bytes += stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime, UTC)
            if last_modified is None or modified > last_modified:
                last_modified = modified
            if file_count > limit:
                return _Measurement(
                    file_count=file_count,
                    directory_count=directory_count,
                    total_bytes=total_bytes,
                    last_modified_at=last_modified,
                    scan_error="MEASUREMENT_FILE_LIMIT_EXCEEDED",
                )
    except OSError as error:
        return _Measurement(
            file_count=file_count,
            directory_count=directory_count,
            total_bytes=total_bytes,
            last_modified_at=last_modified,
            scan_error=f"{type(error).__name__}: {error}",
        )
    return _Measurement(
        file_count=file_count,
        directory_count=directory_count,
        total_bytes=total_bytes,
        last_modified_at=last_modified,
        scan_error=None,
    )


def _probe_cleanup_access(
    path: Path, recommendation: FolderRecommendation
) -> _CleanupProbe:
    if recommendation not in {
        FolderRecommendation.CLEAN_AFTER_APPROVAL,
        FolderRecommendation.ARCHIVE_OR_CLEAN_AFTER_APPROVAL,
    }:
        return _CleanupProbe(
            status="NOT_APPLICABLE",
            delete_probe_status="NOT_APPLICABLE",
            acl_readable=None,
            exclusive_access=None,
            cleanup_blocker=None,
        )

    acl_readable = True
    exclusive_access = True
    cleanup_blocker: str | None = None
    try:
        next(path.iterdir(), None)
    except OSError:
        acl_readable = False
        cleanup_blocker = "ACL_ACCESS_DENIED"

    if cleanup_blocker is None and not _can_open_children_for_exclusive_read(path):
        exclusive_access = False
        cleanup_blocker = "FOLDER_IN_USE_OR_LOCKED"

    status = "ACCESS_PROBE_READABLE" if cleanup_blocker is None else "CLEANUP_BLOCKED"
    return _CleanupProbe(
        status=status,
        delete_probe_status="NOT_EXECUTED_REPORT_ONLY",
        acl_readable=acl_readable,
        exclusive_access=exclusive_access,
        cleanup_blocker=cleanup_blocker,
    )


def _can_open_children_for_exclusive_read(path: Path) -> bool:
    checked = 0
    try:
        for child in path.rglob("*"):
            if not child.is_file():
                continue
            try:
                with child.open("rb"):
                    pass
            except OSError:
                return False
            checked += 1
            if checked >= 25:
                break
    except OSError:
        return False
    return True


def _measurement_blockers(
    relative: str,
    recommendation: FolderRecommendation,
    generated_at: datetime,
    stale_after_days: int,
    measurement: _Measurement,
    cleanup_probe: _CleanupProbe,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if measurement.scan_error is not None:
        blockers.append("FOLDER_SCAN_INCOMPLETE")
    if cleanup_probe.cleanup_blocker is not None:
        blockers.append(cleanup_probe.cleanup_blocker)
    if (
        recommendation is FolderRecommendation.CLEAN_AFTER_APPROVAL
        and measurement.last_modified_at is not None
        and generated_at - measurement.last_modified_at
        > timedelta(days=stale_after_days)
    ):
        blockers.append("STALE_GENERATED_FOLDER_PRESENT")
    if _is_pytest_generated(relative):
        blockers.append("PYTEST_GENERATED_FOLDER_PRESENT")
    return tuple(dict.fromkeys(blockers))


def _build_blockers(folders: tuple[FolderAuditEntry, ...]) -> tuple[str, ...]:
    blockers = [blocker for folder in folders for blocker in folder.blockers if blocker]
    return tuple(dict.fromkeys(blockers))


def _build_recommendations(
    folders: tuple[FolderAuditEntry, ...],
) -> tuple[FolderCleanupRecommendation, ...]:
    pytest_paths = tuple(
        folder.path
        for folder in folders
        if folder.classification == "PYTEST_GENERATED_ARTIFACT"
    )
    cache_paths = tuple(
        folder.path for folder in folders if folder.classification == "TOOL_CACHE"
    )
    runtime_paths = tuple(
        folder.path
        for folder in folders
        if folder.classification == "GENERATED_RUNTIME_ARTIFACT"
    )
    recommendations: list[FolderCleanupRecommendation] = []
    pytest_cache = tuple(
        folder.path for folder in folders if folder.path == ".pytest_cache"
    )
    if pytest_cache:
        recommendations.append(
            FolderCleanupRecommendation(
                priority=1,
                title="Diagnose .pytest_cache ACL before cleanup",
                paths=pytest_cache,
                action=(
                    "Run an explicit ACL/ownership diagnosis before any forced "
                    "cleanup attempt; do not take ownership automatically."
                ),
                safety_notes=(
                    (
                        "This is a Windows filesystem hygiene blocker, "
                        "not trading evidence."
                    ),
                    "Keep generated cleanup separate from source or Secrets handling.",
                ),
            )
        )
    stale_pytest_paths = tuple(path for path in pytest_paths if path != ".pytest_cache")
    if stale_pytest_paths:
        recommendations.append(
            FolderCleanupRecommendation(
                priority=2,
                title="Clean stale pytest folders after approval",
                paths=stale_pytest_paths,
                action=(
                    "Confirm no pytest process is active, then remove these generated "
                    "folders or archive them if old audit evidence is still needed."
                ),
                safety_notes=(
                    (
                        "Do not remove source, tests, Secrets, State/private, "
                        "Models, or .venv."
                    ),
                    (
                        "Use a unique Artifacts/TestTemp/ai4binance-pytest-* "
                        "basetemp for future runs."
                    ),
                ),
            )
        )
    if cache_paths:
        recommendations.append(
            FolderCleanupRecommendation(
                priority=3,
                title="Clean local tool caches after approval",
                paths=cache_paths,
                action=(
                    "Remove reproducible local caches when the editor and "
                    "quality tools are idle."
                ),
                safety_notes=(
                    "Caches are regenerated by Ruff, MyPy, or Python tooling.",
                ),
            )
        )
    if runtime_paths:
        recommendations.append(
            FolderCleanupRecommendation(
                priority=4,
                title="Archive or prune generated runtime artifacts",
                paths=runtime_paths,
                action="Archive selected old logs and temp artifacts before deletion.",
                safety_notes=(
                    "Keep validation evidence that supports RESEARCH_ONLY decisions.",
                    "Do not delete latest blocker reports without replacing them.",
                ),
            )
        )
    recommendations.append(
        FolderCleanupRecommendation(
            priority=5,
            title="Review manual-scope folders",
            paths=tuple(
                folder.path
                for folder in folders
                if folder.recommendation is FolderRecommendation.REVIEW_MANUALLY
            ),
            action=(
                "Assign owner, evidence purpose, or quarantine status before "
                "any cleanup."
            ),
            safety_notes=(
                "Manual review prevents deleting research evidence or private state.",
            ),
        )
    )
    return tuple(recommendations)


def _render_markdown(report: FolderStructureAuditReport) -> str:
    lines = [
        "# Folder Structure Audit",
        "",
        f"- audit_id: `{report.audit_id}`",
        f"- generated_at: `{report.generated_at.isoformat()}`",
        f"- repository: `{report.repository}`",
        f"- mode: `{report.mode}`",
        f"- live_eligibility_status: `{report.live_eligibility_status}`",
        "",
        "## Recommendations",
    ]
    for item in report.recommendations:
        paths = ", ".join(f"`{path}`" for path in item.paths) or "`NONE`"
        lines.extend(
            [
                "",
                f"### P{item.priority} {item.title}",
                f"- paths: {paths}",
                f"- action: {item.action}",
                f"- safety: {'; '.join(item.safety_notes)}",
            ]
        )
    lines.extend(["", "## Folders", ""])
    lines.append(
        "| path | classification | recommendation | files | bytes | "
        "access | delete | blockers |"
    )
    lines.append("| --- | --- | --- | ---: | ---: | --- | --- | --- |")
    for folder in report.folders:
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{folder.path}`",
                    folder.classification,
                    folder.recommendation.value,
                    "" if folder.file_count is None else str(folder.file_count),
                    "" if folder.total_bytes is None else str(folder.total_bytes),
                    folder.cleanup_probe_status,
                    folder.delete_probe_status,
                    ", ".join(folder.blockers),
                )
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the folder audit CLI."""
    parser = argparse.ArgumentParser(description="AI4BINANCE folder structure audit")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("Artifacts/folder-structure-audit"),
    )
    parser.add_argument("--stale-after-days", type=int, default=7)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the report-only folder audit."""
    parsed = build_parser().parse_args(arguments)
    writer = FolderStructureAuditWriter(
        FolderStructureAuditConfig(
            repository_root=parsed.repository_root,
            output_directory=parsed.output_directory,
            stale_after_days=parsed.stale_after_days,
        )
    )
    report = writer.run()
    print(json.dumps(to_primitive(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

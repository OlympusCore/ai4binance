"""Read-only script inventory and duplication evidence for scripts kaizen."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified

_PARAMETER_PATTERN = re.compile(
    r"(?im)^\s*\[(?:string|int|bool|switch|datetime|path)[^\]]*\]\s*\$(\w+)"
)
_FUNCTION_PATTERN = re.compile(r"(?im)^\s*function\s+([A-Za-z0-9_-]+)\s*(?:\{|$)")
_SCRIPT_REFERENCE_PATTERN = re.compile(r"(?i)([A-Za-z0-9_.-]+\.(?:ps1|py))")
_LOCAL_ABSOLUTE_PATH_PATTERN = re.compile(r"(?i)\b[A-Z]:\\")
_ADMIN_PATTERN = re.compile(r"(?i)(administrator|runas|elevat|forceacl|builtInRole)")
_TASK_SCHEDULER_PATTERN = re.compile(
    r"(?i)(Register-ScheduledTask|Unregister-ScheduledTask|ScheduledTask|New-ScheduledTask)"
)
_PROCESS_PATTERN = re.compile(
    r"(?i)(Start-Process|Stop-Process|Get-Process|Wait-Process)"
)
_ARTIFACT_PATTERN = re.compile(
    r"(?i)(runtime\\|runtime/|Set-Content|Add-Content|ConvertTo-Json)"
)
_DESTRUCTIVE_PATTERN = re.compile(
    r"(?i)(Remove-Item|Move-Item|robocopy|icacls|takeown|Unregister-ScheduledTask|Stop-Process)"
)


@dataclass(frozen=True, slots=True)
class ScriptInventoryEntry:
    """Static, read-only facts about one repository script."""

    path: str
    extension: str
    category: str
    bytes: int
    line_count: int
    parameter_names: tuple[str, ...]
    function_names: tuple[str, ...]
    referenced_scripts: tuple[str, ...]
    destructive_capability: bool
    admin_capability: bool
    task_scheduler_capability: bool
    process_capability: bool
    writes_runtime_artifacts: bool
    hard_coded_local_path_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DuplicateBlockEvidence:
    """Repeated normalized text block found across scripts."""

    fingerprint: str
    occurrence_count: int
    script_count: int
    paths: tuple[str, ...]
    sample: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScriptsInventoryReport:
    """Report-only script kaizen baseline without execution authority."""

    schema_version: str
    generated_at_utc: datetime
    repository_root: str
    scripts_root: str
    status: str
    script_count: int
    total_bytes: int
    total_lines: int
    top_by_bytes: tuple[ScriptInventoryEntry, ...]
    top_by_lines: tuple[ScriptInventoryEntry, ...]
    entries: tuple[ScriptInventoryEntry, ...]
    script_call_graph: Mapping[str, tuple[str, ...]]
    duplicate_blocks: tuple[DuplicateBlockEvidence, ...]
    risk_summary: Mapping[str, int]
    recommended_next_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"


def build_scripts_inventory_report(
    repository_root: Path,
    *,
    scripts_directory: str = "scripts",
    duplicate_block_size: int = 8,
    duplicate_limit: int = 20,
    clock: datetime | None = None,
) -> ScriptsInventoryReport:
    """Build a read-only scripts inventory and duplicate-code baseline."""
    root = repository_root.resolve()
    scripts_root = (root / scripts_directory).resolve()
    if not scripts_root.is_dir():
        raise ValueError("scripts_directory must resolve to an existing directory")
    if duplicate_block_size < 3:
        raise ValueError("duplicate_block_size must be at least 3")
    entries = tuple(
        _inventory_entry(path, root, scripts_root)
        for path in sorted(scripts_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".ps1", ".py"}
    )
    call_graph = _build_call_graph(entries)
    duplicate_blocks = _find_duplicate_blocks(
        (root / entry.path for entry in entries),
        root,
        block_size=duplicate_block_size,
        limit=duplicate_limit,
    )
    total_bytes = sum(entry.bytes for entry in entries)
    total_lines = sum(entry.line_count for entry in entries)
    risk_summary = {
        "destructive_capability_count": sum(
            1 for entry in entries if entry.destructive_capability
        ),
        "admin_capability_count": sum(1 for entry in entries if entry.admin_capability),
        "task_scheduler_capability_count": sum(
            1 for entry in entries if entry.task_scheduler_capability
        ),
        "process_capability_count": sum(
            1 for entry in entries if entry.process_capability
        ),
        "runtime_artifact_writer_count": sum(
            1 for entry in entries if entry.writes_runtime_artifacts
        ),
        "hard_coded_local_path_count": sum(
            entry.hard_coded_local_path_count for entry in entries
        ),
    }
    return ScriptsInventoryReport(
        schema_version="1.0",
        generated_at_utc=clock or datetime.now(UTC),
        repository_root=str(root),
        scripts_root=_relative_path(scripts_root, root),
        status="PASS",
        script_count=len(entries),
        total_bytes=total_bytes,
        total_lines=total_lines,
        top_by_bytes=tuple(
            sorted(entries, key=lambda item: item.bytes, reverse=True)[:10]
        ),
        top_by_lines=tuple(
            sorted(entries, key=lambda item: item.line_count, reverse=True)[:10]
        ),
        entries=entries,
        script_call_graph=call_graph,
        duplicate_blocks=duplicate_blocks,
        risk_summary=risk_summary,
        recommended_next_actions=_recommended_next_actions(entries, duplicate_blocks),
    )


def persist_scripts_inventory_report(
    report: ScriptsInventoryReport,
    output_path: Path,
) -> None:
    """Persist inventory evidence with read-back verification."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = cast(dict[str, object], to_primitive(report))
    write_json_object_verified(
        output_path,
        payload,
        blocker="SCRIPT_INVENTORY_WRITE_VERIFICATION_FAILED",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the script inventory CLI parser."""
    parser = argparse.ArgumentParser(description="AI4BINANCE scripts inventory audit")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--scripts-directory", default="scripts")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/artifacts/scripts_kaizen/script_inventory_latest.json"),
    )
    parser.add_argument("--duplicate-block-size", type=int, default=8)
    parser.add_argument("--duplicate-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the read-only scripts inventory audit."""
    parsed = build_parser().parse_args(arguments)
    report = build_scripts_inventory_report(
        parsed.repository_root,
        scripts_directory=parsed.scripts_directory,
        duplicate_block_size=parsed.duplicate_block_size,
        duplicate_limit=parsed.duplicate_limit,
    )
    output = parsed.output
    if not output.is_absolute():
        output = parsed.repository_root / output
    persist_scripts_inventory_report(report, output)
    payload = cast(dict[str, object], to_primitive(report))
    if parsed.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        summary = {
            "status": report.status,
            "script_count": report.script_count,
            "total_lines": report.total_lines,
            "top_script": report.top_by_lines[0].path if report.top_by_lines else "",
            "duplicate_block_count": len(report.duplicate_blocks),
            "evidence_path": _relative_path(
                output.resolve(),
                parsed.repository_root.resolve(),
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _inventory_entry(
    path: Path,
    root: Path,
    scripts_root: Path,
) -> ScriptInventoryEntry:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    relative = _relative_path(path, root)
    function_names = tuple(dict.fromkeys(_FUNCTION_PATTERN.findall(text)))
    parameter_names = tuple(dict.fromkeys(_PARAMETER_PATTERN.findall(text)))
    referenced_scripts = tuple(
        sorted(
            {
                reference
                for reference in _SCRIPT_REFERENCE_PATTERN.findall(text)
                if reference != path.name
            }
        )
    )
    encoded = text.encode("utf-8")
    return ScriptInventoryEntry(
        path=relative,
        extension=path.suffix.lower(),
        category=_classify_script(path, scripts_root, text),
        bytes=len(encoded),
        line_count=len(text.splitlines()),
        parameter_names=parameter_names,
        function_names=function_names,
        referenced_scripts=referenced_scripts,
        destructive_capability=bool(_DESTRUCTIVE_PATTERN.search(text)),
        admin_capability=bool(_ADMIN_PATTERN.search(text)),
        task_scheduler_capability=bool(_TASK_SCHEDULER_PATTERN.search(text)),
        process_capability=bool(_PROCESS_PATTERN.search(text)),
        writes_runtime_artifacts=bool(_ARTIFACT_PATTERN.search(text)),
        hard_coded_local_path_count=len(_LOCAL_ABSOLUTE_PATH_PATTERN.findall(text)),
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _classify_script(path: Path, scripts_root: Path, text: str) -> str:
    name = path.relative_to(scripts_root).as_posix().lower()
    if "quality" in name or "coverage" in name or "audit" in name:
        return "quality_and_assurance"
    if "mirror" in name or "migrate" in name or "archive" in name:
        return "mirror_migration_archive"
    if "startup" in name or "task" in name:
        return "startup_task_scheduler"
    if "llm" in name or "llama" in name or "qwen" in name or "ollama" in name:
        return "local_llm_process"
    if "security" in name or "admin" in name or "git" in name:
        return "windows_security_admin"
    if "report" in name or "speak" in name or "preflight" in name:
        return "reporting_utility"
    if _TASK_SCHEDULER_PATTERN.search(text):
        return "startup_task_scheduler"
    if _PROCESS_PATTERN.search(text):
        return "local_llm_process"
    return "utility"


def _build_call_graph(
    entries: Sequence[ScriptInventoryEntry],
) -> dict[str, tuple[str, ...]]:
    known_names = {Path(entry.path).name.lower(): entry.path for entry in entries}
    graph: dict[str, tuple[str, ...]] = {}
    for entry in entries:
        targets = {
            known_names[reference.lower()]
            for reference in entry.referenced_scripts
            if reference.lower() in known_names
        }
        graph[entry.path] = tuple(sorted(targets))
    return graph


def _find_duplicate_blocks(
    paths: Iterable[Path],
    root: Path,
    *,
    block_size: int,
    limit: int,
) -> tuple[DuplicateBlockEvidence, ...]:
    occurrences: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for path in paths:
        normalized_lines = tuple(_normalized_code_lines(path))
        for index in range(0, max(0, len(normalized_lines) - block_size + 1)):
            block = normalized_lines[index : index + block_size]
            fingerprint = hashlib.sha256("\n".join(block).encode("utf-8")).hexdigest()
            occurrences[fingerprint].append((_relative_path(path, root), block))
    duplicates: list[DuplicateBlockEvidence] = []
    for fingerprint, matches in occurrences.items():
        paths_for_block = tuple(sorted({path for path, _ in matches}))
        if len(matches) < 2 or len(paths_for_block) < 2:
            continue
        duplicates.append(
            DuplicateBlockEvidence(
                fingerprint=fingerprint,
                occurrence_count=len(matches),
                script_count=len(paths_for_block),
                paths=paths_for_block,
                sample=matches[0][1],
            )
        )
    return tuple(
        sorted(
            duplicates,
            key=lambda item: (item.script_count, item.occurrence_count),
            reverse=True,
        )[:limit]
    )


def _normalized_code_lines(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = re.sub(r'"[^"]*"', '"<str>"', stripped)
        normalized = re.sub(r"'[^']*'", "'<str>'", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        lines.append(normalized)
    return tuple(lines)


def _recommended_next_actions(
    entries: Sequence[ScriptInventoryEntry],
    duplicate_blocks: Sequence[DuplicateBlockEvidence],
) -> tuple[str, ...]:
    actions = [
        (
            "Keep existing script entrypoints stable while moving shared "
            "orchestration into Python."
        ),
        (
            "Prioritize the largest quality and assurance scripts for "
            "characterization tests."
        ),
    ]
    if duplicate_blocks:
        actions.append(
            "Replace repeated helper blocks with one shared implementation "
            "after behavior is characterized."
        )
    if any(entry.task_scheduler_capability for entry in entries):
        actions.append(
            "Move Task Scheduler install/status behavior behind a shared "
            "Windows adapter contract."
        )
    if any(entry.destructive_capability for entry in entries):
        actions.append(
            "Require preview, bounded target validation, and evidence for "
            "cleanup or migration scripts."
        )
    return tuple(actions)


def _relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

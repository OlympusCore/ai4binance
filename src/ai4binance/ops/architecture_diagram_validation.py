"""Validate the governed architecture diagram documentation projection."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ALLOWED_STATUSES = frozenset(
    {
        "CURRENT_VERIFIED",
        "CURRENT_PARTIAL",
        "TARGET_CANONICAL",
        "PROPOSED",
        "DEPRECATED",
        "NOT_VERIFIED",
        "GOVERNANCE_CONFLICT",
        "NOT_APPLICABLE",
        "BLOCKED",
    }
)
DEFERRED_STATUSES = frozenset({"NOT_VERIFIED", "NOT_APPLICABLE"})
MERMAID_TYPES = frozenset(
    {
        "flowchart",
        "sequenceDiagram",
        "stateDiagram-v2",
        "classDiagram",
        "erDiagram",
        "gitGraph",
    }
)
DIAGRAM_FILE_PATTERN = re.compile(r"^d\d{3,4}_[a-z0-9_]+\.md$")
DIAGRAM_ID_PATTERN = re.compile(r"^D\d{3,4}$")
MARKDOWN_DIAGRAM_ID_PATTERN = re.compile(
    r"^Diagram ID:\s*`?(D\d{3,4})`?\s*$", re.MULTILINE
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MERMAID_BLOCK_PATTERN = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class DiagramValidationFinding:
    """One deterministic diagram-system validation failure."""

    code: str
    path: str
    detail: str


@dataclass(frozen=True, slots=True)
class DiagramValidationReport:
    """Complete validation outcome for one repository state."""

    status: str
    registered_count: int
    documented_count: int
    findings: tuple[DiagramValidationFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "registered_count": self.registered_count,
            "documented_count": self.documented_count,
            "findings": [asdict(finding) for finding in self.findings],
        }


def _normalize_repository_path(root: Path, raw_path: str) -> Path | None:
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _load_registry(registry_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    try:
        payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return [], [f"registry cannot be loaded: {exc}"]
    if not isinstance(payload, dict):
        return [], ["registry root must be a mapping"]
    diagrams = payload.get("diagrams")
    if not isinstance(diagrams, list):
        return [], ["registry diagrams must be a list"]
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(diagrams):
        if not isinstance(item, dict):
            errors.append(f"diagrams[{index}] must be a mapping")
            continue
        normalized.append(item)
    return normalized, errors


def _validate_mermaid(path: Path, text: str) -> list[DiagramValidationFinding]:
    blocks = MERMAID_BLOCK_PATTERN.findall(text)
    if not blocks:
        return [
            DiagramValidationFinding(
                "MISSING_MERMAID",
                path.as_posix(),
                "Documented diagrams require one canonical Mermaid block.",
            )
        ]
    first_line = next(
        (line.strip() for line in blocks[0].splitlines() if line.strip()), ""
    )
    diagram_type = first_line.split(maxsplit=1)[0] if first_line else ""
    if diagram_type not in MERMAID_TYPES:
        return [
            DiagramValidationFinding(
                "INVALID_MERMAID_TYPE",
                path.as_posix(),
                f"Unsupported Mermaid declaration: {first_line or '<empty>'}",
            )
        ]
    return []


def _validate_local_links(
    repository_root: Path, path: Path, text: str
) -> list[DiagramValidationFinding]:
    findings: list[DiagramValidationFinding] = []
    for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
        target = raw_target.split("#", maxsplit=1)[0].strip()
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        candidate = (
            repository_root / target.lstrip("/")
            if target.startswith("/")
            else path.parent / target
        ).resolve()
        try:
            candidate.relative_to(repository_root.resolve())
        except ValueError:
            findings.append(
                DiagramValidationFinding(
                    "LINK_OUTSIDE_REPOSITORY",
                    path.relative_to(repository_root).as_posix(),
                    f"Local link escapes the repository: {raw_target}",
                )
            )
            continue
        if not candidate.exists():
            findings.append(
                DiagramValidationFinding(
                    "BROKEN_LOCAL_LINK",
                    path.relative_to(repository_root).as_posix(),
                    f"Local link target does not exist: {raw_target}",
                )
            )
    return findings


def validate_architecture_diagrams(repository_root: Path) -> DiagramValidationReport:
    """Validate registry integrity, diagram sources, relations, and local links."""

    root = repository_root.resolve()
    docs_root = root / "docs" / "architecture" / "diagrams"
    registry_path = docs_root / "diagram_registry.yaml"
    findings: list[DiagramValidationFinding] = []
    if not registry_path.is_file():
        finding = DiagramValidationFinding(
            "REGISTRY_MISSING",
            registry_path.relative_to(root).as_posix(),
            "Canonical diagram registry is missing.",
        )
        return DiagramValidationReport("FAIL", 0, 0, (finding,))

    entries, registry_errors = _load_registry(registry_path)
    findings.extend(
        DiagramValidationFinding(
            "REGISTRY_INVALID",
            registry_path.relative_to(root).as_posix(),
            detail,
        )
        for detail in registry_errors
    )

    by_id: dict[str, dict[str, Any]] = {}
    registered_paths: dict[str, str] = {}
    documented_count = 0
    for index, entry in enumerate(entries):
        diagram_id = entry.get("diagram_id")
        entry_path = f"diagrams[{index}]"
        if not isinstance(diagram_id, str) or not DIAGRAM_ID_PATTERN.fullmatch(
            diagram_id
        ):
            findings.append(
                DiagramValidationFinding(
                    "INVALID_DIAGRAM_ID",
                    entry_path,
                    f"Invalid diagram_id: {diagram_id!r}",
                )
            )
            continue
        if diagram_id in by_id:
            findings.append(
                DiagramValidationFinding(
                    "DUPLICATE_DIAGRAM_ID",
                    entry_path,
                    f"Duplicate diagram ID: {diagram_id}",
                )
            )
            continue
        by_id[diagram_id] = entry

        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            findings.append(
                DiagramValidationFinding(
                    "INVALID_STATUS",
                    entry_path,
                    f"{diagram_id} has unsupported status: {status!r}",
                )
            )

        path_value = entry.get("path")
        if not path_value:
            if status not in DEFERRED_STATUSES:
                findings.append(
                    DiagramValidationFinding(
                        "MISSING_PATH",
                        entry_path,
                        f"{diagram_id} status {status!r} requires a document path.",
                    )
                )
            continue
        if not isinstance(path_value, str):
            findings.append(
                DiagramValidationFinding(
                    "INVALID_PATH",
                    entry_path,
                    f"{diagram_id} path must be a repository-relative string.",
                )
            )
            continue
        normalized_path = _normalize_repository_path(root, path_value)
        if normalized_path is None:
            findings.append(
                DiagramValidationFinding(
                    "PATH_OUTSIDE_REPOSITORY",
                    entry_path,
                    f"{diagram_id} path escapes the repository: {path_value}",
                )
            )
            continue
        if path_value in registered_paths:
            findings.append(
                DiagramValidationFinding(
                    "DUPLICATE_DIAGRAM_PATH",
                    entry_path,
                    f"{diagram_id} shares a path with {registered_paths[path_value]}.",
                )
            )
            continue
        registered_paths[path_value] = diagram_id
        if not normalized_path.is_file():
            findings.append(
                DiagramValidationFinding(
                    "MISSING_REGISTERED_DIAGRAM",
                    path_value,
                    f"Registered diagram file does not exist for {diagram_id}.",
                )
            )
            continue

        documented_count += 1
        text = normalized_path.read_text(encoding="utf-8")
        declared_match = MARKDOWN_DIAGRAM_ID_PATTERN.search(text)
        declared_id = declared_match.group(1) if declared_match else None
        if declared_id != diagram_id:
            findings.append(
                DiagramValidationFinding(
                    "DIAGRAM_ID_MISMATCH",
                    path_value,
                    (
                        f"Registry ID {diagram_id} does not match document ID "
                        f"{declared_id!r}."
                    ),
                )
            )
        findings.extend(
            DiagramValidationFinding(item.code, path_value, item.detail)
            for item in _validate_mermaid(normalized_path, text)
        )
        findings.extend(_validate_local_links(root, normalized_path, text))

    for diagram_id, entry in by_id.items():
        related = entry.get("related_diagrams", [])
        if not isinstance(related, list) or any(
            not isinstance(item, str) for item in related
        ):
            findings.append(
                DiagramValidationFinding(
                    "INVALID_RELATION_LIST",
                    diagram_id,
                    "related_diagrams must be a list of diagram IDs.",
                )
            )
            continue
        for related_id in related:
            if related_id not in by_id:
                findings.append(
                    DiagramValidationFinding(
                        "BROKEN_RELATION",
                        diagram_id,
                        f"Related diagram is not registered: {related_id}",
                    )
                )

    if docs_root.is_dir():
        for candidate in docs_root.rglob("*.md"):
            if not DIAGRAM_FILE_PATTERN.fullmatch(candidate.name):
                continue
            relative = candidate.relative_to(root).as_posix()
            if relative not in registered_paths:
                findings.append(
                    DiagramValidationFinding(
                        "UNREGISTERED_DIAGRAM_FILE",
                        relative,
                        "Diagram document is not present in diagram_registry.yaml.",
                    )
                )

    ordered_findings = tuple(
        sorted(findings, key=lambda item: (item.code, item.path, item.detail))
    )
    return DiagramValidationReport(
        status="PASS" if not ordered_findings else "FAIL",
        registered_count=len(by_id),
        documented_count=documented_count,
        findings=ordered_findings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the AI4Binance architecture diagram system."
    )
    parser.add_argument(
        "repository_root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    args = parser.parse_args(argv)
    report = validate_architecture_diagrams(args.repository_root)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

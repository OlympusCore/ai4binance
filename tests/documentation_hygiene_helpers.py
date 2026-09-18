from __future__ import annotations

from pathlib import Path

STALE_KNOWLEDGE_TEMPLATE_REFERENCE = "/".join(
    ("docs", "templates", "templates_governed_knowledge_objects.md")
)

_ROOT_DOCUMENTATION_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
)
_EXCLUDED_DOCUMENTATION_ANALYSIS_SUBTREES = (
    "docs/archive/",
    "runtime/reports/draft_docs/",
)


def is_excluded_documentation_analysis_path(root: Path, path: Path) -> bool:
    relative_path = path.relative_to(root).as_posix()
    return any(
        relative_path.startswith(excluded_subtree)
        for excluded_subtree in _EXCLUDED_DOCUMENTATION_ANALYSIS_SUBTREES
    )


def documentation_markdown_files(root: Path) -> list[Path]:
    docs = root / "docs"
    operations_reports = root / "runtime" / "reports" / "operations"
    return sorted(
        [
            *(root / filename for filename in _ROOT_DOCUMENTATION_FILES),
            *docs.rglob("*.md"),
            *(
                path
                for path in operations_reports.rglob("*.md")
                if "docs_baseline_" not in path.as_posix()
                and not is_excluded_documentation_analysis_path(root, path)
            ),
        ]
    )


def stale_knowledge_template_offenders(root: Path) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in documentation_markdown_files(root)
        if STALE_KNOWLEDGE_TEMPLATE_REFERENCE in path.read_text(encoding="utf-8")
    ]

"""Documentation folder hygiene tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "Docs"
OPERATIONS_REPORTS = ROOT / "Reports" / "operations"


TEMPORARY_OPERATION_PATTERNS = (
    "*_DIFF_PLAN_*.md",
    "*_IMPLEMENTATION_PLAN.md",
    "*_IMPLEMENTATION_REPORT.md",
    "*_WATCHLIST_*.md",
    "*_DRAFT_QUEUE.md",
)


EXPECTED_OPERATION_REPORTS = {
    "COVERAGE_DIFF_PLAN_20260719.md",
    "DYNAMIC_PORTFOLIO_IMPLEMENTATION_PLAN.md",
    "EVIDENCE_BACKED_X_DRAFT_QUEUE.md",
    "EXTERNAL_RESEARCH_WATCHLIST_20260716.md",
    "OPENBB_FREQTRADE_STRENGTHENING.md",
    "REPO_CLEANUP_DIFF_PLAN_20260728.md",
    "REPOSITORY_CLEANUP_RF_IMPLEMENTATION_REPORT.md",
    "WORKTREE_DIFF_PLAN_20260719.md",
}


def test_docs_contains_no_temporary_operation_documents() -> None:
    offenders = sorted(
        path.relative_to(ROOT).as_posix()
        for pattern in TEMPORARY_OPERATION_PATTERNS
        for path in DOCS.glob(pattern)
    )

    assert offenders == []


def test_operation_reports_are_separated_from_permanent_docs() -> None:
    reports = {
        path.name
        for path in OPERATIONS_REPORTS.glob("*.md")
        if path.name != "README.md"
    }

    assert EXPECTED_OPERATION_REPORTS <= reports


def test_docs_and_reports_have_eli10_explanations() -> None:
    markdown_files = sorted([*DOCS.glob("*.md"), *(ROOT / "Reports").glob("**/*.md")])

    missing = [
        path.relative_to(ROOT).as_posix()
        for path in markdown_files
        if "\n## ELI10\n" not in path.read_text(encoding="utf-8")
    ]

    assert missing == []

    duplicated = [
        path.relative_to(ROOT).as_posix()
        for path in markdown_files
        if path.read_text(encoding="utf-8").count("\n## ELI10\n") != 1
    ]

    assert duplicated == []

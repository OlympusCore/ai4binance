"""Canonical local user-report paths and professional report rendering helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.reporting import to_primitive

_CANONICAL_ROOT_PARTS = ("vscode-projects", "ai4binance")
CANONICAL_SYSTEM_ROOT = Path(Path.cwd().anchor, *_CANONICAL_ROOT_PARTS)


@dataclass(frozen=True, slots=True)
class UserReportPaths:
    report_dir: Path
    artifact_dir: Path
    json_path: Path
    markdown_path: Path
    latest_json_path: Path
    latest_markdown_path: Path


def canonical_system_root(root: Path | None = None) -> Path:
    """Return the only supported full-system root, allowing tests to use temp roots."""
    requested = root or Path.cwd()
    if _is_test_run():
        return requested

    canonical = CANONICAL_SYSTEM_ROOT
    if not canonical.exists():
        raise ValueError("AI4BINANCE_CANONICAL_ROOT_UNAVAILABLE")

    requested_resolved = requested.resolve()
    canonical_resolved = canonical.resolve()
    if requested_resolved != canonical_resolved:
        raise ValueError(
            f"AI4BINANCE_CANONICAL_ROOT_REQUIRED: run the full system from {canonical}"
        )
    return canonical


def user_report_paths(
    root: Path,
    report_type: str,
    stamp: str,
    *,
    file_stem: str,
    latest_stem: str = "latest",
) -> UserReportPaths:
    """Build historical and latest user-facing report paths."""
    report_dir = root / "runtime" / "reports" / report_type
    artifact_dir = root / "runtime" / "artifacts" / "user_reports" / report_type
    return UserReportPaths(
        report_dir=report_dir,
        artifact_dir=artifact_dir,
        json_path=artifact_dir / f"{file_stem}_{stamp}.json",
        markdown_path=report_dir / f"{file_stem}_{stamp}.md",
        latest_json_path=artifact_dir / f"{latest_stem}.json",
        latest_markdown_path=report_dir / f"{latest_stem}.md",
    )


def write_user_report_files(
    paths: UserReportPaths,
    payload: Mapping[str, object],
    markdown: str,
) -> None:
    """Write Markdown to runtime reports and machine payloads to runtime artifacts."""
    paths.report_dir.mkdir(parents=True, exist_ok=True)
    paths.artifact_dir.mkdir(parents=True, exist_ok=True)
    primitive = cast(dict[str, object], to_primitive(dict(payload)))
    json_text = json.dumps(primitive, ensure_ascii=False, indent=2, sort_keys=True)
    paths.json_path.write_text(json_text + "\n", encoding="utf-8")
    paths.latest_json_path.write_text(json_text + "\n", encoding="utf-8")
    paths.markdown_path.write_text(markdown, encoding="utf-8")
    paths.latest_markdown_path.write_text(markdown, encoding="utf-8")


def render_professional_summary(
    *,
    title: str,
    observed_at: object,
    status: object,
    summary: str,
    sections: Sequence[tuple[str, Sequence[str]]],
    blockers: Sequence[object] = (),
) -> str:
    """Render a concise, professional Markdown report for human readers."""
    lines = [
        f"# {title}",
        "",
        "## ELI10",
        "",
        (
            "This local report highlights what the system observed, what is "
            "blocked, and what remains safe to review. It supports human "
            "decision-making only and never grants trading authority."
        ),
        "",
        "## Executive Summary",
        "",
        summary,
        "",
        "## Status",
        "",
        f"- Observed at: `{observed_at}`",
        f"- Status: `{status}`",
        "- Execution: `NO_TRADE`",
        "- Promotion: `RESEARCH_ONLY`",
        "- Live eligibility: `LIVE_ORDER_BLOCKED`",
    ]
    if blockers:
        lines.extend(
            (
                "",
                "## Blockers",
                "",
                *[f"- `{blocker}`" for blocker in blockers[:20]],
            )
        )
    for heading, items in sections:
        lines.extend(("", f"## {heading}", ""))
        if items:
            lines.extend(items)
        else:
            lines.append("- No reportable item is available.")
    lines.extend(
        (
            "",
            "## Safety Boundary",
            "",
            (
                "This report is decision-support evidence only. It does not "
                "authorize live orders, automatic transfers, position closing, "
                "risk-limit changes, or production promotion."
            ),
            "",
        )
    )
    return "\n".join(lines)


def _is_test_run() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ

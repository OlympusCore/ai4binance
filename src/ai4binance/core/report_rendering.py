"""Pure presentation of bounded research report payloads."""

from __future__ import annotations

from collections.abc import Sequence


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

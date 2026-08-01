"""CLI output rendering helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import cast

from ai4binance.reporting import to_primitive

GROUP_ORDER = (
    "core",
    "validation",
    "portfolio",
    "market-research",
    "runtime",
    "accounting",
    "governance",
    "live-spot",
)


def render_payload(
    payload: object,
    *,
    output_format: str = "json",
    command: str | None = None,
) -> str:
    primitive = to_primitive(payload)
    if output_format == "text":
        return render_text(cast(dict[str, object], primitive), command=command)
    return json.dumps(primitive, ensure_ascii=True, sort_keys=True)


def render_text(payload: dict[str, object], *, command: str | None = None) -> str:
    resolved = command or str(payload.get("command", "status"))
    if resolved in {"commands", "help"}:
        return _commands_text(payload)
    if resolved in {"validation-summary", "backtest-results"}:
        return _validation_summary_text(payload)
    if resolved == "opportunities":
        return _opportunities_text(payload)
    if resolved == "skills-audit":
        return _skills_audit_text(payload)
    if resolved == "repository-cleanup-audit":
        return _repository_cleanup_audit_text(payload)
    if resolved == "status":
        return _status_text(payload)
    return _generic_text(payload)


def _commands_text(payload: dict[str, object]) -> str:
    lines = ["AI4BINANCE CLI commands"]
    groups = cast(Mapping[str, Sequence[Mapping[str, object]]], payload["groups"])
    seen: set[str] = set()
    for group in (*GROUP_ORDER, *tuple(groups)):
        if group not in groups or group in seen:
            continue
        seen.add(group)
        commands = groups[group]
        lines.append("")
        lines.append(f"[{group}]")
        for item in commands:
            aliases = _join(item.get("aliases", ()))
            suffix = f" aliases: {aliases}" if aliases else ""
            lines.append(f"- {item['command']}: {item['summary']}{suffix}")
            examples = _join(item.get("examples", ()))
            if examples:
                lines.append(f"  examples: {examples}")
    return "\n".join(lines)


def _validation_summary_text(payload: dict[str, object]) -> str:
    summary = cast(Mapping[str, object], payload["summary"])
    lines = [
        f"Validation summary: {summary.get('symbol', 'UNKNOWN')}",
        f"- runs: {summary.get('run_count', 0)}",
        f"- research_only: {summary.get('research_only_count', 0)}",
        f"- staged_candidates: {summary.get('staged_candidate_count', 0)}",
        f"- live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
    ]
    top_blockers = cast(Iterable[Sequence[object]], summary.get("top_blockers", ()))
    formatted = [f"{item[0]}={item[1]}" for item in top_blockers if len(item) >= 2]
    if formatted:
        lines.append(f"- top_blockers: {', '.join(formatted[:6])}")
    return "\n".join(lines)


def _opportunities_text(payload: dict[str, object]) -> str:
    inbox = cast(Mapping[str, object], payload["inbox"])
    items = cast(Sequence[Mapping[str, object]], inbox.get("items", ()))
    lines = [
        f"Opportunities: {inbox.get('symbol', 'UNKNOWN')}",
        f"- visible_items: {len(items)}",
        f"- live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
    ]
    blockers = _join(inbox.get("blockers", ()))
    if blockers:
        lines.append(f"- blockers: {blockers}")
    for item in items[:5]:
        lines.append(
            "- "
            f"{item.get('market', 'UNKNOWN')} "
            f"{item.get('timeframe', '?')} "
            f"{item.get('setup_name', 'unknown')} "
            f"status={item.get('status', 'UNKNOWN')} "
            f"promotion={item.get('promotion_status', 'RESEARCH_ONLY')}"
        )
    return "\n".join(lines)


def _skills_audit_text(payload: dict[str, object]) -> str:
    report = cast(Mapping[str, object], payload["report"])
    lines = [
        "Agent Skills audit",
        f"- root: {report.get('root', '')}",
        f"- skills: {report.get('skill_count', 0)}",
        f"- issues: {report.get('issue_count', 0)}",
        f"- blockers: {report.get('blocker_count', 0)}",
        f"- high_risk_capabilities: {report.get('high_risk_capability_count', 0)}",
        f"- live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
    ]
    blockers = _join(payload.get("blockers", ()))
    if blockers:
        lines.append(f"- blocker_codes: {blockers}")
    issues = cast(Sequence[Mapping[str, object]], report.get("issues", ()))
    for issue in issues[:8]:
        lines.append(
            "- "
            f"{issue.get('severity', 'INFO')} "
            f"{issue.get('code', 'SKILL_ISSUE')} "
            f"{issue.get('message', '')}"
        )
    return "\n".join(lines)


def _repository_cleanup_audit_text(payload: dict[str, object]) -> str:
    report = cast(Mapping[str, object], payload["report"])
    inventory = cast(Mapping[str, object], report["inventory"])
    baseline = cast(Mapping[str, object], report["performance_baseline"])
    dynamic_usage_files = cast(Sequence[object], report.get("dynamic_usage_files", ()))
    static_unimported_files = cast(
        Sequence[object], report.get("static_unimported_files", ())
    )
    folder_classifications = cast(
        Sequence[Mapping[str, object]], report.get("folder_classifications", ())
    )
    static_classifications = cast(
        Sequence[Mapping[str, object]],
        report.get("static_unimported_classifications", ()),
    )
    exception_reviews = cast(
        Sequence[Mapping[str, object]], report.get("broad_exception_reviews", ())
    )
    broad_exception_sites = cast(
        Sequence[object], report.get("broad_exception_sites", ())
    )
    folder_decisions = _count_mapping_values(folder_classifications, "decision")
    file_decisions = _count_mapping_values(static_classifications, "decision")
    exception_statuses = _count_mapping_values(exception_reviews, "status")
    lines = [
        "Repository cleanup audit",
        f"- status: {payload.get('status', 'REVIEW_REQUIRED')}",
        f"- python_modules: {inventory.get('python_modules', 0)}",
        f"- source_files: {inventory.get('source_files', 0)}",
        f"- test_files: {inventory.get('test_files', 0)}",
        f"- exact_import_cycles: {report.get('exact_import_cycle_count', 0)}",
        f"- dynamic_usage_files: {len(dynamic_usage_files)}",
        f"- static_unimported_files: {len(static_unimported_files)}",
        f"- static_file_decisions: {_format_counts(file_decisions)}",
        f"- folder_decisions: {_format_counts(folder_decisions)}",
        f"- broad_exception_sites: {len(broad_exception_sites)}",
        f"- exception_reviews: {_format_counts(exception_statuses)}",
        f"- python_startup_ms: {baseline.get('python_startup_ms', 0)}",
        f"- live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
    ]
    packages = cast(Sequence[Mapping[str, object]], report.get("work_packages", ()))
    for package in packages:
        lines.append(
            "- "
            f"{package.get('package_id', 'RF-000')} "
            f"{package.get('priority', 'P?')} "
            f"risk={package.get('risk', 'Unknown')}"
        )
    return "\n".join(lines)


def _status_text(payload: dict[str, object]) -> str:
    live_gate = cast(Mapping[str, object], payload.get("live_gate", {}))
    blockers = _join(live_gate.get("blockers", ()))
    trading_mode = payload.get("trading_mode", "paper")
    order_mode = payload.get("order_mode", "manual")
    mode = f"{trading_mode}/{order_mode}"
    lines = [
        f"Status: {payload.get('symbol', 'UNKNOWN')}",
        f"- action: {payload.get('action', 'NO_TRADE')}",
        f"- decision: {payload.get('decision_state', 'NO_TRADE')}",
        f"- setup: {payload.get('setup_tier', 'NO_TRADE')}",
        f"- mode: {mode}",
        f"- live_gate: {live_gate.get('status', 'LIVE_ORDER_BLOCKED')}",
    ]
    if blockers:
        lines.append(f"- blockers: {blockers}")
    return "\n".join(lines)


def _generic_text(payload: dict[str, object]) -> str:
    lines = [str(payload.get("command", "AI4BINANCE"))]
    for key in (
        "status",
        "execution_allowed",
        "live_eligibility_status",
        "promotion_status",
    ):
        if key in payload:
            lines.append(f"- {key}: {payload[key]}")
    blockers = _join(payload.get("blockers", ()))
    if blockers:
        lines.append(f"- blockers: {blockers}")
    return "\n".join(lines)


def _join(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return ", ".join(str(item) for item in value)
    return ""


def _count_mapping_values(
    items: Sequence[Mapping[str, object]],
    key: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "UNKNOWN"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))

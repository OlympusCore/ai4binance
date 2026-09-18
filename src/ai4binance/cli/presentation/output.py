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
    if resolved in {
        "validation-summary",
        "backtest-results",
    }:
        return _validation_summary_text(payload)
    if resolved == "backtest-runtime-economics":
        return _backtest_runtime_economics_text(payload)
    if resolved == "opportunities":
        return _opportunities_text(payload)
    if resolved == "opportunity-recovery-radar":
        return _opportunity_recovery_radar_text(payload)
    if resolved == "skills-audit":
        return _skills_audit_text(payload)
    if resolved == "repository-cleanup-audit":
        return _repository_cleanup_audit_text(payload)
    if resolved == "system-report":
        return _system_report_text(payload)
    if resolved == "vnext-gap-audit":
        return _vnext_gap_audit_text(payload)
    if resolved == "research-public":
        return _research_public_text(payload)
    if resolved == "ykb-report":
        return _ykb_report_text(payload)
    if resolved == "agent-stack-audit":
        return _agent_stack_audit_text(payload)
    if resolved == "virtual-improvement-research-queue":
        return _virtual_improvement_research_queue_text(payload)
    if resolved in {"virtual-market-once", "virtual-runtime-once", "virtual-runtime"}:
        return _virtual_runtime_text(payload)
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
        _live_eligibility_text_line("live", payload),
    ]
    top_blockers = cast(Iterable[Sequence[object]], summary.get("top_blockers", ()))
    formatted = [f"{item[0]}={item[1]}" for item in top_blockers if len(item) >= 2]
    if formatted:
        lines.append(f"- top_blockers: {', '.join(formatted[:6])}")
    return "\n".join(lines)


def _backtest_runtime_economics_text(payload: dict[str, object]) -> str:
    assessment = cast(Mapping[str, object], payload.get("telemetry_assessment", {}))
    lines = [
        f"Backtest runtime economics: {payload.get('artifact_id', 'UNKNOWN')}",
        f"- status: {payload.get('status', 'WATCHLIST')}",
        f"- reviewer_result: {payload.get('reviewer_result', 'WATCHLIST')}",
        f"- hardware_profile: {payload.get('hardware_profile', 'UNKNOWN')}",
        f"- runtime_stack: {payload.get('runtime_stack', 'UNKNOWN')}",
        f"- gpu_available: {payload.get('gpu_available', False)}",
        f"- gpu_requested: {payload.get('gpu_requested', False)}",
        f"- gpu_used: {payload.get('gpu_used', False)}",
        (
            "- telemetry_assessment: "
            f"{assessment.get('healthy', False)} "
            f"{assessment.get('source_label', 'UNKNOWN')} "
            f"{assessment.get('blockers', ())}"
        ),
    ]
    latency = payload.get("measured_latency_ms")
    if latency is not None:
        lines.append(f"- measured_latency_ms: {latency}")
    throughput = payload.get("measured_simulations_per_second")
    if throughput is not None:
        lines.append(f"- measured_simulations_per_second: {throughput}")
    power = payload.get("measured_power_watts")
    if power is not None:
        lines.append(f"- measured_power_watts: {power}")
    monthly_cost = payload.get("claimed_monthly_cost_usd")
    if monthly_cost is not None:
        lines.append(f"- claimed_monthly_cost_usd: {monthly_cost}")
    benchmark_line = _optional_joined_text_line(
        "benchmark_citations",
        cast(Iterable[object], payload.get("benchmark_citations", ())),
    )
    if benchmark_line is not None:
        lines.append(benchmark_line)
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    return "\n".join(lines)


def _virtual_improvement_research_queue_text(payload: dict[str, object]) -> str:
    items = cast(Sequence[Mapping[str, object]], payload.get("items", ()))
    lines = [
        f"Virtual improvement queue: {payload.get('snapshot_id', 'UNKNOWN')}",
        f"- status: {payload.get('status', 'QUEUED_WITH_BLOCKERS')}",
        f"- staged_candidates: {len(items)}",
        _live_eligibility_text_line("live", payload),
    ]
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    for item in items[:5]:
        lines.append(
            "- "
            f"{item.get('priority', 'P1')} "
            f"{item.get('affected_component', 'UNKNOWN_COMPONENT')} "
            f"candidate={item.get('candidate_id', 'UNKNOWN')}"
        )
    return "\n".join(lines)


def _optional_joined_text_line(
    label: str,
    values: Iterable[object],
) -> str | None:
    joined = _join(values)
    if not joined:
        return None
    return f"- {label}: {joined}"


def _optional_colon_text_line(
    label: str,
    values: Iterable[object],
) -> str | None:
    joined = _join(values)
    if not joined:
        return None
    return f"{label}: {joined}"


def _live_eligibility_text_line(
    label: str,
    payload: Mapping[str, object],
    *,
    key: str = "live_eligibility_status",
) -> str:
    return f"- {label}: {payload.get(key, 'LIVE_ORDER_BLOCKED')}"


def _research_public_text(payload: dict[str, object]) -> str:
    decision = cast(
        Mapping[str, object] | None, payload.get("virtual_runtime_decision")
    )
    stages = cast(Sequence[Mapping[str, object]], payload.get("research_stages", ()))
    lines = [
        f"Research public: {payload.get('symbol', 'UNKNOWN')}",
        f"- execution_allowed: {payload.get('execution_allowed', False)}",
        _live_eligibility_text_line("live", payload),
        f"- stages: {len(stages)}",
    ]
    if decision is not None:
        lines.extend(_virtual_runtime_decision_text_lines(decision))
        blocker_line = _optional_joined_text_line(
            "virtual_runtime_blockers",
            cast(Iterable[object], decision.get("blockers", ())),
        )
        if blocker_line is not None:
            lines.append(blocker_line)
    return "\n".join(lines)


def _virtual_market_gate_text_lines(
    virtual_gate: Mapping[str, object],
) -> list[str]:
    return [
        (
            "- virtual_market_gate: "
            f"{virtual_gate.get('automation_mode', 'BOUNDED_AUTONOMOUS_SIMULATION')}"
        ),
        (
            "- virtual_market_gate_authority_profile: "
            f"{virtual_gate.get('authority_profile_id', 'UNKNOWN')}"
        ),
        _live_eligibility_text_line("virtual_market_gate_live", virtual_gate),
    ]


def _virtual_runtime_decision_text_lines(
    decision: Mapping[str, object],
) -> list[str]:
    eligibility = cast(Mapping[str, object] | None, decision.get("eligibility"))
    eligibility_status = "UNKNOWN"
    if eligibility is not None:
        eligibility_status = str(eligibility.get("status", "UNKNOWN"))
    return [
        f"- virtual_runtime_decision: {decision.get('status', 'UNKNOWN')}",
        f"- virtual_runtime_eligibility: {eligibility_status}",
        _live_eligibility_text_line("virtual_runtime_live", decision),
    ]


def _virtual_runtime_boundary_text_lines(
    payload: Mapping[str, object],
) -> list[str]:
    return [
        f"- execution_surface: {payload.get('execution_surface', 'VIRTUAL_MARKET')}",
        (
            "- automation_mode: "
            f"{payload.get('automation_mode', 'BOUNDED_AUTONOMOUS_SIMULATION')}"
        ),
        f"- authority_profile_id: {payload.get('authority_profile_id', 'UNKNOWN')}",
        (
            "- manual_confirmation_required: "
            f"{payload.get('manual_confirmation_required', False)}"
        ),
        (
            "- virtual_simulation_allowed: "
            f"{payload.get('virtual_simulation_allowed', True)}"
        ),
        f"- auto_simulation_allowed: {payload.get('auto_simulation_allowed', True)}",
        f"- external_order_allowed: {payload.get('external_order_allowed', False)}",
        f"- live_order_allowed: {payload.get('live_order_allowed', False)}",
    ]


def _virtual_runtime_outcome_text_lines(
    payload: Mapping[str, object],
) -> list[str]:
    return [
        f"- execution_allowed: {payload.get('execution_allowed', False)}",
        f"- promotion_status: {payload.get('promotion_status', 'RESEARCH_ONLY')}",
        _live_eligibility_text_line("live", payload),
    ]


def _virtual_runtime_text(payload: dict[str, object]) -> str:
    lines = [
        "Virtual market probe",
        f"- status: {payload.get('status', 'READY')}",
    ]
    lines.extend(_virtual_runtime_boundary_text_lines(payload))
    lines.extend(_virtual_runtime_outcome_text_lines(payload))
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    return "\n".join(lines)


def _opportunities_text(payload: dict[str, object]) -> str:
    inbox = cast(Mapping[str, object], payload["inbox"])
    items = cast(Sequence[Mapping[str, object]], inbox.get("items", ()))
    report_v2 = _as_mapping(payload.get("opportunity_report_v2"))
    if report_v2:
        return _opportunity_report_v2_text(payload, inbox, report_v2)
    generation_status = inbox.get(
        "generation_status", payload.get("status", "DEGRADED")
    )
    lines = [
        f"Opportunities: {inbox.get('symbol', 'UNKNOWN')}",
        f"- generation: {generation_status}",
        f"- research_loop: {inbox.get('research_loop_allowed', True)}",
        f"- visible_items: {len(items)}",
        f"- live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
    ]
    research_blockers = _join(inbox.get("research_blockers", ()))
    execution_blockers = _join(inbox.get("execution_blockers", ()))
    next_actions = _join(inbox.get("next_safe_actions", ()))
    if research_blockers:
        lines.append(f"- research_blockers: {research_blockers}")
    if execution_blockers:
        lines.append(f"- execution_blockers: {execution_blockers}")
    if next_actions:
        next_actions_line = _optional_joined_text_line(
            "next_safe_actions",
            cast(Iterable[object], inbox.get("next_safe_actions", ())),
        )
        if next_actions_line is not None:
            lines.append(next_actions_line)
    funnel_parts: list[str] = []
    for raw_count in cast(Sequence[object], inbox.get("funnel_counts", ())):
        if (
            isinstance(raw_count, Sequence)
            and not isinstance(raw_count, str)
            and len(raw_count) >= 2
        ):
            funnel_parts.append(f"{raw_count[0]}={raw_count[1]}")
    if funnel_parts:
        lines.append(f"- funnel: {_join(funnel_parts)}")
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


def _opportunity_report_v2_text(
    payload: dict[str, object],
    inbox: Mapping[str, object],
    report_v2: Mapping[str, object],
) -> str:
    sections = _as_mapping(report_v2.get("sections"))
    items = cast(Sequence[Mapping[str, object]], inbox.get("items", ()))
    lines = [
        "OPPORTUNITY RADAR",
        f"Symbol: {inbox.get('symbol', 'UNKNOWN')}",
        f"Radar: {inbox.get('generation_status', payload.get('status', 'DEGRADED'))}",
        "Trading: NO_TRADE",
        f"Live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
        f"Visible Items: {len(items)}",
    ]
    _append_report_section(
        lines,
        "Top Opportunities",
        cast(
            Sequence[Mapping[str, object]],
            sections.get("top_opportunities", ()),
        ),
    )
    _append_report_section(
        lines,
        "Confirmation Pending",
        cast(
            Sequence[Mapping[str, object]],
            sections.get("confirmation_pending", ()),
        ),
    )
    _append_report_section(
        lines,
        "Developing Setups",
        cast(Sequence[Mapping[str, object]], sections.get("setup_forming", ())),
    )
    _append_report_section(
        lines,
        "Validation Ladder",
        cast(
            Sequence[Mapping[str, object]],
            sections.get("validation_ladder", ()),
        ),
    )
    _append_report_section(
        lines,
        "Rejected / Lost",
        cast(Sequence[Mapping[str, object]], sections.get("rejected_or_lost", ())),
    )
    snapshot_diff = _as_mapping(report_v2.get("snapshot_diff"))
    if snapshot_diff:
        new_count = len(cast(Sequence[object], snapshot_diff.get("new_candidates", ())))
        upgraded_count = len(
            cast(Sequence[object], snapshot_diff.get("upgraded_candidates", ()))
        )
        downgraded_count = len(
            cast(Sequence[object], snapshot_diff.get("downgraded_candidates", ()))
        )
        still_pending_count = len(
            cast(Sequence[object], snapshot_diff.get("still_pending", ()))
        )
        lines.append("Radar Diff:")
        lines.append(f"- new: {new_count}")
        lines.append(f"- upgraded: {upgraded_count}")
        lines.append(f"- downgraded: {downgraded_count}")
        lines.append(f"- still_pending: {still_pending_count}")
    actions = cast(
        Sequence[Mapping[str, object]], report_v2.get("next_safe_actions", ())
    )
    if actions:
        lines.append("Next Safe Actions:")
        for action in actions[:5]:
            lines.append(f"- {action.get('action', 'KEEP_RESEARCH_RADAR_RUNNING')}")
    blockers_line = _optional_colon_text_line(
        "Execution Blockers",
        cast(
            Iterable[object],
            payload.get("execution_blockers", inbox.get("execution_blockers", ())),
        ),
    )
    if blockers_line is not None:
        lines.append(blockers_line)
    return "\n".join(lines)


def _append_report_section(
    lines: list[str],
    title: str,
    candidates: Sequence[Mapping[str, object]],
) -> None:
    lines.append(f"{title}:")
    if not candidates:
        lines.append("- none")
        return
    for item in candidates[:5]:
        missing = _join(
            (
                *cast(Sequence[object], item.get("confirmation_gaps", ())),
                *cast(Sequence[object], item.get("validation_gaps", ())),
            )
        )
        lines.append(
            "- "
            f"{item.get('symbol', 'UNKNOWN')} | "
            f"{item.get('grade', 'D')} | "
            f"{item.get('lifecycle_state', 'WATCH_ONLY')} | "
            f"{item.get('setup_name', 'UNKNOWN_SETUP')} | "
            f"{item.get('timeframe', 'UNSPECIFIED')}"
        )
        if missing:
            lines.append(f"  missing: {missing}")
        lines.append(
            f"  next: {item.get('next_safe_action', 'KEEP_RESEARCH_RADAR_RUNNING')}"
        )


def _opportunity_recovery_radar_text(payload: dict[str, object]) -> str:
    ladder = cast(Sequence[Mapping[str, object]], payload.get("ladder", ()))
    lines = [
        f"Opportunity Recovery Radar: {payload.get('symbol', 'UNKNOWN')}",
        f"- status: {payload.get('status', 'RUNNING_WITH_BLOCKERS')}",
        f"- mode: {payload.get('recovery_mode', 'RECOVERY_GUARDED_RESEARCH_MODE')}",
        f"- hindsight: {payload.get('hindsight_notice', 'HINDSIGHT_ENVELOPE_ONLY')}",
        f"- inventory_units: {payload.get('inventory_units', '0')}",
        f"- range: {payload.get('range_low', '?')} -> {payload.get('range_high', '?')}",
        f"- range_source: {payload.get('range_source', 'UNAVAILABLE')}",
        f"- range_move_ratio: {payload.get('range_move_ratio', '0')}",
        (
            "- ideal_full_cycle_units: "
            f"{payload.get('ideal_full_cycle_end_units', '0')} "
            f"gain={payload.get('ideal_full_cycle_unit_gain', '0')}"
        ),
        _live_eligibility_text_line("live", payload),
        f"- candidates: {len(ladder)}",
    ]
    for item in ladder[:8]:
        item_blockers = _join(cast(Sequence[object], item.get("blockers", ())))
        lenses = cast(
            Sequence[Mapping[str, object]], item.get("lens_contributions", ())
        )
        top_lenses = _join(
            tuple(str(lens.get("lens", "")) for lens in lenses[:3] if lens.get("lens"))
        )
        lines.append(
            "- "
            f"{item.get('ladder_stage', 'RADAR_ONLY')} "
            f"{item.get('setup_name', 'unknown')} "
            f"action={item.get('review_action', 'REVIEW')} "
            f"iq={item.get('intelligence_score', '0')} "
            f"grade={item.get('opportunity_grade', 'RADAR_ONLY')} "
            f"miss_risk={item.get('miss_risk', 'LOW')} "
            f"fp_risk={item.get('false_positive_risk', 'HIGH')} "
            f"top_lenses={top_lenses} "
            f"gain_units={item.get('estimated_cycle_unit_gain', '0')} "
            f"blockers={item_blockers}"
        )
    actions_line = _optional_joined_text_line(
        "next_safe_actions",
        cast(Iterable[object], payload.get("next_safe_actions", ())),
    )
    if actions_line is not None:
        lines.append(actions_line)
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
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
        _live_eligibility_text_line("live", payload),
    ]
    blocker_line = _optional_joined_text_line(
        "blocker_codes", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
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
    root_hygiene_classifications = cast(
        Sequence[Mapping[str, object]],
        report.get("root_hygiene_classifications", ()),
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
    root_hygiene_decisions = _count_mapping_values(
        root_hygiene_classifications,
        "decision",
    )
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
        f"- root_hygiene_decisions: {_format_counts(root_hygiene_decisions)}",
        f"- broad_exception_sites: {len(broad_exception_sites)}",
        f"- exception_reviews: {_format_counts(exception_statuses)}",
        f"- python_startup_ms: {baseline.get('python_startup_ms', 0)}",
        _live_eligibility_text_line("live", payload),
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
    virtual_gate = cast(Mapping[str, object], payload.get("virtual_market_gate", {}))
    assessment = cast(Mapping[str, object], payload.get("telemetry_assessment", {}))
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
    if assessment:
        lines.append(
            "- telemetry_assessment: "
            f"{assessment.get('healthy', False)} "
            f"{assessment.get('source_label', 'UNKNOWN')} "
            f"{assessment.get('blockers', ())}"
        )
    lines.extend(_virtual_market_gate_text_lines(virtual_gate))
    if blockers:
        lines.append(f"- blockers: {blockers}")
    return "\n".join(lines)


def _system_report_text(payload: dict[str, object]) -> str:
    components = cast(Mapping[str, Mapping[str, object]], payload["components"])
    telemetry_raw = payload.get("telemetry_assessment")
    telemetry = (
        cast(Mapping[str, object], telemetry_raw)
        if isinstance(telemetry_raw, Mapping)
        else {}
    )
    contract_raw = payload.get("advanced_agent_operating_contract")
    contract = (
        cast(Mapping[str, object], contract_raw)
        if isinstance(contract_raw, Mapping)
        else {}
    )
    human_controls_raw = contract.get("human_approval_controls")
    human_controls = (
        cast(Mapping[str, object], human_controls_raw)
        if isinstance(human_controls_raw, Mapping)
        else {}
    )
    lines = [
        "System report",
        f"- status: {payload.get('status', 'DEGRADED')}",
        f"- live: {payload.get('live_eligibility_status', 'LIVE_ORDER_BLOCKED')}",
    ]
    markdown_path = payload.get("markdown_path")
    json_path = payload.get("json_path")
    if markdown_path:
        lines.append(f"- markdown_path: {markdown_path}")
    if json_path:
        lines.append(f"- json_path: {json_path}")
    if telemetry:
        lines.append(
            "- telemetry_assessment: "
            f"{telemetry.get('healthy', False)} "
            f"{telemetry.get('source_label', 'UNKNOWN')} "
            f"{telemetry.get('blockers', ())}"
        )
    if contract:
        contract_status = contract.get("status", "RUNNING_WITH_BLOCKERS")
        lines.append(f"- advanced_agent_contract: {contract_status}")
        lines.append(
            f"- orchestration: {contract.get('orchestration', 'MULTI_STEP_WORKFLOWS')}"
        )
        execution_scope = contract.get("execution_scope", "END_TO_END_OPERATIONS")
        lines.append(f"- execution_scope: {execution_scope}")
        guardrails = _join(contract.get("guardrails", ()))
        if guardrails:
            lines.append(f"- guardrails: {guardrails}")
        gates = _join(human_controls.get("gates", ()))
        if gates:
            lines.append(f"- human_approval_gates: {gates}")
    cards_raw = payload.get("dashboard_cards")
    cards = (
        cast(Mapping[str, object], cards_raw) if isinstance(cards_raw, Mapping) else {}
    )
    if cards:
        total = cards.get("metric_count", 0)
        blocked = cards.get("blocked_metric_count", 0)
        watch = cards.get("watch_metric_count", 0)
        lines.append(
            f"- dashboard_cards: total={total} blocked={blocked} watch={watch}"
        )
        card_blocked_ids = _join(cards.get("blocked_metric_ids", ()))
        if card_blocked_ids:
            lines.append(f"- dashboard_blocked_cards: {card_blocked_ids}")
    blockers = _join(payload.get("blockers", ()))
    if blockers:
        lines.append(f"- blockers: {blockers}")
    for name, component in components.items():
        status = component.get("status", component.get("state", "UNKNOWN"))
        component_blockers = _join(component.get("blockers", ()))
        suffix = f" blockers={component_blockers}" if component_blockers else ""
        lines.append(f"- {name}: {status}{suffix}")
        if name == "local_advisory":
            auto_learn_raw = component.get("auto_learn")
            auto_learn = (
                cast(Mapping[str, object], auto_learn_raw)
                if isinstance(auto_learn_raw, Mapping)
                else None
            )
            if auto_learn:
                engine = cast(Mapping[str, object], auto_learn.get("engine", {}))
                lines.append(
                    "- auto_learn: "
                    f"{auto_learn.get('status', 'UNKNOWN')} "
                    f"mode={auto_learn.get('mode', 'RESEARCH_ONLY')} "
                    f"provider={engine.get('provider', 'llama.cpp')} "
                    f"model={engine.get('model', 'qwen3:8b')}"
                )
    return "\n".join(lines)


def _vnext_gap_audit_text(payload: dict[str, object]) -> str:
    counts = cast(Mapping[str, object], payload.get("summary_counts", {}))
    capabilities = cast(Sequence[Mapping[str, object]], payload.get("capabilities", ()))
    lines = [
        "vNext v1.2 gap audit",
        f"- status: {payload.get('status', 'RUNNING_WITH_BLOCKERS')}",
        f"- profile: {payload.get('source_profile', 'VNEXT')}",
        f"- next_phase: {payload.get('next_phase', '-')}",
        f"- complete: {counts.get('COMPLETE', 0)}",
        f"- partial: {counts.get('PARTIAL', 0)}",
        f"- research_only: {counts.get('RESEARCH_ONLY', 0)}",
        f"- missing: {counts.get('MISSING', 0)}",
        _live_eligibility_text_line("live", payload),
    ]
    top_gaps = _join(payload.get("top_gaps", ()))
    if top_gaps:
        lines.append(f"- top_gaps: {top_gaps}")
    for item in capabilities[:10]:
        missing = _join(item.get("missing_controls", ()))
        lines.append(
            "- "
            f"{item.get('priority', 'P?')} "
            f"{item.get('capability_id', 'VNEXT')} "
            f"{item.get('status', 'PARTIAL')} "
            f"phase={item.get('phase', '?')} "
            f"missing={missing or '-'}"
        )
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    return "\n".join(lines)


def _ykb_report_text(payload: dict[str, object]) -> str:
    financial = _as_mapping(payload.get("financial_situation"))
    opportunities = cast(
        Sequence[Mapping[str, object]],
        payload.get("opportunities", ()),
    )
    semi_auto = _as_mapping(payload.get("semi_auto_control"))
    validation = _as_mapping(payload.get("latest_validation"))
    technology = cast(
        Sequence[Mapping[str, object]], payload.get("technology_opportunities", ())
    )
    context = cast(Sequence[Mapping[str, object]], payload.get("important_context", ()))
    spot = cast(Sequence[Mapping[str, object]], payload.get("spot_opportunities", ()))
    futures = cast(
        Sequence[Mapping[str, object]], payload.get("futures_opportunities", ())
    )
    blocker_order = semi_auto.get(
        "blocker_resolution_order_status",
        "PENDING_YKB_APPROVAL",
    )
    risk_oos_live_gate = semi_auto.get(
        "risk_oos_live_gate_status",
        "LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE",
    )
    next_management_action = semi_auto.get(
        "next_management_action",
        "REQUEST_YKB_BLOCKER_ORDER_APPROVAL",
    )
    lines = [
        "YKB executive brief",
        f"- status: {payload.get('status', 'RUNNING_WITH_BLOCKERS')}",
        f"- summary: {payload.get('executive_summary', '')}",
        _live_eligibility_text_line("live", payload),
        f"- markdown_path: {payload.get('markdown_path', '')}",
        f"- auto_audit: {payload.get('auto_audit_status', 'UNKNOWN')}",
        f"- agent_audit: {payload.get('agent_audit_status', 'UNKNOWN')}",
        f"- recovery_radar: {payload.get('recovery_radar_status', 'NOT_REQUESTED')}",
        f"- vnext_gap: {payload.get('vnext_gap_status', 'NOT_REQUESTED')}",
        f"- vnext_top_gaps: {_join(payload.get('vnext_gap_top_gaps', ())) or '-'}",
        (
            "- financial: "
            f"status={financial.get('status', 'UNKNOWN')} "
            f"spot_assets={financial.get('spot_asset_count', 0)} "
            f"futures_positions={financial.get('futures_position_count', 0)} "
            f"reconciliation={financial.get('reconciliation_status', 'UNKNOWN')} "
            f"value={financial.get('value_disclosure', 'REDACTED_SUMMARY_ONLY')}"
        ),
        (
            "- semi_auto: "
            f"{semi_auto.get('mode', 'SEMI_AUTO_CONTROL_MANAGEMENT')} "
            f"{semi_auto.get('workflow_pattern', 'HUMAN_IN_THE_LOOP')}"
        ),
        f"- blocker_order: {blocker_order}",
        f"- risk_oos_live_gate: {risk_oos_live_gate}",
        f"- next_management_action: {next_management_action}",
        (
            "- latest_validation: "
            f"{validation.get('symbol', 'UNKNOWN')} "
            f"{validation.get('timeframe', 'UNAVAILABLE')}/"
            f"{validation.get('playbook', 'UNAVAILABLE')} "
            f"{validation.get('promotion_status', 'RESEARCH_ONLY')}"
        ),
        f"- technology_opportunities: {len(technology)}",
        f"- important_context: {len(context)}",
        f"- spot_trade_plans: {len(spot)}",
        f"- futures_trade_plans: {len(futures)}",
        f"- opportunities: {len(opportunities)}",
    ]
    for item in opportunities[:5]:
        lines.append(
            "- "
            f"{item.get('symbol', 'UNKNOWN')} "
            f"{item.get('setup_name', 'UNKNOWN_SETUP')} "
            f"dge={item.get('dge_status', 'UNKNOWN')} "
            f"action={item.get('governed_action', 'NO_TRADE')} "
            f"fit={item.get('financial_fit', 'UNKNOWN')}"
        )
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    return "\n".join(lines)


def _agent_stack_audit_text(payload: dict[str, object]) -> str:
    report = cast(Mapping[str, object], payload["report"])
    layers = cast(Sequence[Mapping[str, object]], report.get("layers", ()))
    lines = [
        "Agent stack audit",
        f"- status: {payload.get('status', 'REVISION_REQUIRED')}",
        f"- layers: {len(layers)}",
        _live_eligibility_text_line("live", payload),
    ]
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    for layer in layers:
        status = "PASSED" if layer.get("passed") is True else "REVISION_REQUIRED"
        lines.append(f"- {layer.get('layer_id', 'UNKNOWN')}: {status}")
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
    blocker_line = _optional_joined_text_line(
        "blockers", cast(Iterable[object], payload.get("blockers", ()))
    )
    if blocker_line is not None:
        lines.append(blocker_line)
    return "\n".join(lines)


def _join(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return ", ".join(str(item) for item in value)
    return ""


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


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


__all__ = ("GROUP_ORDER", "render_payload", "render_text")

"""Thin safe command-line dispatcher."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from ai4binance.application import WhaleFusionCycle

__path__ = [str(Path(__file__).with_suffix(""))]

from ai4binance.cli.accounting import run_accounting_command
from ai4binance.cli.bootstrap import (
    SnapshotAcquirer,
    normalize_slash_command,
    parse_arguments,
)
from ai4binance.cli.bootstrap.shared import virtual_market_gate_payload
from ai4binance.cli.bootstrap.skill_discovery import run_skill_discovery_command
from ai4binance.cli.commands import command_catalog_payload
from ai4binance.cli.dge import (
    dge_replay_payload,
    dge_rules_payload,
    dge_shadow_rules_payload,
)
from ai4binance.cli.enterprise import (
    run_agent_stack_audit_command,
    run_enterprise_intake,
    run_oek_gap_analysis_command,
    run_quality_system_audit_command,
    run_repository_cleanup_audit_command,
    run_virtual_market_paper_soak_command,
)
from ai4binance.cli.live import run_live_place_spot, run_live_preview_spot
from ai4binance.cli.presentation import render_payload
from ai4binance.cli.research import (
    run_crew_plan,
    run_public_research_command,
    run_second_brain,
    run_sync_validation_data,
    run_validate_research,
    run_virtual_market_retrieval_eval_command,
)
from ai4binance.cli.runtime import build_read_only_runtime, run_runtime_command
from ai4binance.cli.status import (
    agentic_skills_payload,
    agents_payload,
    approvals_payload,
    backtest_runtime_economics_payload,
    lean_governance_payload,
    manual_actions_payload,
    opportunities_payload,
    opportunity_recovery_radar_payload,
    portfolio_command_payload,
    privacy_boundary_payload,
    scan_command_payload,
    skills_audit_payload,
    validation_summary_payload,
)
from ai4binance.cli.voice import run_voice_command
from ai4binance.config import Settings
from ai4binance.decision import build_no_trade_signal
from ai4binance.domain import LiveGateInput
from ai4binance.enterprise import GpuResourceGovernor
from ai4binance.enterprise.vnext_gap_audit import build_vnext_gap_audit
from ai4binance.enterprise.ykb_report import build_ykb_executive_brief
from ai4binance.external_intel.cli.commands import (
    external_intel_payload,
    external_intel_universe_payload,
    open_web_payload,
)
from ai4binance.external_intel.core.enums import MissionName
from ai4binance.ops.auto_audit_loop import run_auto_audit_loop
from ai4binance.ops.security_assurance import run_security_weekly_deep_audit
from ai4binance.ops.system_report import (
    build_system_report,
    system_report_summary_payload,
)
from ai4binance.ops.user_reports import canonical_system_root
from ai4binance.reporting import to_primitive
from ai4binance.safety import evaluate_live_gate

__all__ = ("SnapshotAcquirer", "build_read_only_runtime", "main")


def main(
    arguments: Sequence[str] | None = None,
    *,
    public_acquisition: SnapshotAcquirer | None = None,
    whale_fusion_cycle: WhaleFusionCycle | None = None,
) -> int:
    """Print complete safe runtime status; never submit an order."""
    parsed = parse_arguments(arguments)
    os.chdir(canonical_system_root())
    settings = Settings()
    command = normalize_slash_command(parsed.command, parsed.subject)

    if command in {"commands", "help"}:
        _print_payload(
            command_catalog_payload(parsed.subject),
            output_format=parsed.output_format,
            command="commands",
        )
        return 0

    if command == "system-report":
        result = build_system_report(settings)
        _print_payload(
            system_report_summary_payload(result),
            output_format=parsed.output_format,
            command=command,
        )
        return 0 if result.payload["status"] == "READY" else 2

    if command in {"auto-audit-once", "auto-audit-daemon"}:
        audit_result = run_auto_audit_loop(
            settings,
            max_cycles=(
                1
                if command == "auto-audit-once"
                else parsed.max_cycles
                if parsed.max_cycles is not None
                else 1
            ),
            interval_seconds=parsed.interval_seconds,
            use_local_qwen=parsed.llm,
        )
        _print_payload(
            audit_result.to_payload(),
            output_format=parsed.output_format,
            command=command,
        )
        return 0 if audit_result.status == "READY" else 2

    if command == "security-weekly-deep-audit":
        security_result = run_security_weekly_deep_audit(
            evidence_file=(
                Path(parsed.security_evidence_file)
                if parsed.security_evidence_file
                else None
            )
        )
        _print_payload(
            security_result.to_payload(),
            output_format=parsed.output_format,
            command=command,
        )
        return 0 if security_result.status == "READY" else 2

    if command == "ykb-report":
        ykb_result = build_ykb_executive_brief(
            settings,
            symbol=parsed.symbol,
            use_local_qwen=parsed.llm,
            max_auto_audit_cycles=parsed.max_cycles or 1,
            interval_seconds=parsed.interval_seconds or 0.0,
            blocker_resolution_order_approved=parsed.approve_blocker_order,
            recovery_inventory_units=parsed.inventory_units,
            recovery_range_low=parsed.range_low,
            recovery_range_high=parsed.range_high,
            recovery_cost_basis=parsed.cost_basis,
        )
        _print_payload(
            ykb_result.to_payload(),
            output_format=parsed.output_format,
            command=command,
        )
        return 0 if ykb_result.status == "READY" else 2

    if command == "vnext-gap-audit":
        report = build_vnext_gap_audit(Path.cwd())
        _print_payload(
            report.to_payload(),
            output_format=parsed.output_format,
            command=command,
        )
        return 0 if report.status == "READY" else 2

    if command == "opportunity-recovery-radar":
        payload = opportunity_recovery_radar_payload(
            settings,
            symbol=parsed.symbol,
            inventory_units=parsed.inventory_units,
            range_low=parsed.range_low,
            range_high=parsed.range_high,
            cost_basis=parsed.cost_basis,
        )
        _print_payload(
            payload,
            output_format=parsed.output_format,
            command=command,
        )
        return 0 if payload["status"] == "READY" else 2

    if command in {"dge-rules", "dge-shadow-rules", "dge-replay"}:
        payload = (
            dge_rules_payload()
            if command == "dge-rules"
            else dge_shadow_rules_payload()
            if command == "dge-shadow-rules"
            else dge_replay_payload(decision_id=parsed.subject)
        )
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] in {"READY", "MATCH"} else 2

    if command in {"portfolio", "manual-actions", "approvals"}:
        payload = (
            portfolio_command_payload(settings)
            if command == "portfolio"
            else manual_actions_payload(settings)
            if command == "manual-actions"
            else approvals_payload(settings)
        )
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if not payload["blockers"] else 2

    if command == "opportunities":
        payload = opportunities_payload(settings, parsed.symbol)
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] == "ACTIVE" else 2

    if command in {"scan-spot", "scan-futures", "scan-all"}:
        payload = scan_command_payload(command, settings)
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] == "READY" else 2

    if command in {"validation-summary", "backtest-results"}:
        payload = validation_summary_payload(settings, parsed.symbol)
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if not payload["blockers"] else 2

    if command == "backtest-runtime-economics":
        payload = backtest_runtime_economics_payload(settings)
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] == "RESEARCH_ONLY_BACKTEST_RUNTIME" else 2

    if command == "live-preview-spot":
        return run_live_preview_spot(
            settings,
            confirm_live=parsed.confirm_live,
            symbol=parsed.symbol,
            side=parsed.side,
            order_type=parsed.order_type,
            quantity=parsed.quantity,
            client_order_id=parsed.client_order_id,
            price=parsed.price,
            time_in_force=parsed.time_in_force,
            authorization_id=parsed.authorization_id,
        )

    if command == "live-place-spot":
        return run_live_place_spot(
            settings,
            confirm_live=parsed.confirm_live,
            symbol=parsed.symbol,
            side=parsed.side,
            order_type=parsed.order_type,
            quantity=parsed.quantity,
            client_order_id=parsed.client_order_id,
            price=parsed.price,
            time_in_force=parsed.time_in_force,
            authorization_id=parsed.authorization_id,
        )

    if command.startswith("accounting-"):
        return run_accounting_command(
            command,
            settings,
            max_cycles=parsed.max_cycles,
        )

    if command in {"voice-once", "voice-daemon"}:
        return run_voice_command(
            command,
            settings,
            max_cycles=parsed.max_cycles,
        )

    if command in {
        "runtime-once",
        "runtime-daemon",
        "runtime-research-refresh-once",
        "virtual-market-once",
        "virtual-market-daemon",
        "virtual-market-soak",
        "virtual-runtime-once",
        "virtual-runtime",
        "virtual-runtime-soak",
    }:
        return run_runtime_command(
            command,
            settings,
            max_cycles=parsed.max_cycles,
            public_acquisition=public_acquisition,
        )

    if command == "validate-research":
        return run_validate_research(settings, parsed.symbol)

    if command == "crew-plan":
        return run_crew_plan(settings, parsed.symbol)

    if command == "second-brain":
        return run_second_brain(
            settings,
            query=parsed.query,
            subject=parsed.subject,
            use_llm=parsed.llm,
            render_ui=parsed.ui,
        )

    if command == "virtual-market-retrieval-eval":
        return run_virtual_market_retrieval_eval_command(
            settings,
            query=parsed.query,
        )

    if command == "sync-validation-data":
        return run_sync_validation_data(settings, parsed.symbol, parsed.as_of)

    if command in {"lean-governance", "qaqc-agent"}:
        payload = lean_governance_payload(
            settings,
            mode=(
                "QAQC_AGENT_REVIEW"
                if command == "qaqc-agent"
                else "LEAN_GOVERNANCE_REVIEW"
            ),
        )
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0

    if command == "agents":
        _print_payload(
            agents_payload(), output_format=parsed.output_format, command=command
        )
        return 0

    if command == "agentic-skills":
        payload = agentic_skills_payload(
            task_name=parsed.task,
            risk_domain=parsed.risk_domain,
            independent_checks=parsed.independent_checks,
            stages=parsed.stages,
            requires_human_review=parsed.requires_human_review,
            needs_routing=parsed.needs_routing,
            quality_sensitive=parsed.quality_sensitive,
            bounded_actions=parsed.bounded_actions,
            downside_controlled=parsed.downside_controlled,
            opposing_views=parsed.opposing_views,
        )
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0

    if command == "skills-audit":
        payload = skills_audit_payload(parsed.skills_root)
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if not payload["blockers"] else 2

    if command in {
        "skill-discovery-once",
        "skill-discovery-daemon",
        "skill-discovery-status",
    }:
        return run_skill_discovery_command(
            command,
            settings,
            output_format=parsed.output_format,
            source_file=parsed.source_file,
            max_candidates=parsed.max_candidates,
            min_score=parsed.min_score,
            interval_seconds=parsed.interval_seconds,
            max_cycles=parsed.max_cycles,
        )

    if command == "privacy-boundary":
        payload = privacy_boundary_payload()
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if not payload["blockers"] else 2

    if command == "enterprise-intake":
        return run_enterprise_intake(
            prompt_file=parsed.prompt_file,
            output_format=parsed.output_format,
        )

    if command == "quality-system-audit":
        return run_quality_system_audit_command(output_format=parsed.output_format)

    if command == "agent-stack-audit":
        return run_agent_stack_audit_command(output_format=parsed.output_format)

    if command == "oek-gap-analysis":
        return run_oek_gap_analysis_command(
            change_file=parsed.change_file,
            output_format=parsed.output_format,
        )

    if command == "repository-cleanup-audit":
        return run_repository_cleanup_audit_command(output_format=parsed.output_format)

    if command == "virtual-market-paper-soak":
        return run_virtual_market_paper_soak_command(output_format=parsed.output_format)

    if command in {
        "analyze-public",
        "research-public",
        "archive-public",
        "whale-fusion-research",
    }:
        return run_public_research_command(
            command,
            settings,
            public_acquisition=public_acquisition,
            whale_fusion_cycle=whale_fusion_cycle,
        )

    if command == "external-intel":
        payload = external_intel_payload(
            command=command,
            symbol=parsed.symbol,
            topic=parsed.query or parsed.subject,
        )
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] == "READY" else 2

    if command == "external-intel-universe":
        payload = external_intel_universe_payload()
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] == "READY" else 2

    if command == "external-intel-open-web":
        payload = open_web_payload(
            mission=MissionName(parsed.mission),
            seed_urls=tuple(parsed.seed_url),
            policy_path=settings.open_web_source_config_path,
            evidence_path=settings.open_web_evidence_ledger_path,
        )
        _print_payload(payload, output_format=parsed.output_format, command=command)
        return 0 if payload["status"] == "READY" else 2

    signal = build_no_trade_signal(
        symbol=settings.symbol,
        timeframes=settings.timeframes,
        market_type=settings.market_type,
    )
    live_gate = evaluate_live_gate(
        LiveGateInput(
            live_mode=settings.trading_mode == "live",
            auto_mode=settings.order_mode == "auto",
            allow_auto_live_orders=settings.allow_auto_live_orders,
            confirm_live=bool(parsed.confirm_live),
        )
    )
    signal_payload = cast(dict[str, object], to_primitive(signal))
    signal_payload.update(
        {
            "exchange": settings.exchange,
            "trading_mode": settings.trading_mode,
            "order_mode": settings.order_mode,
            "prefer_no_trade": settings.prefer_no_trade,
            "allow_short_spot": settings.allow_short_spot,
            "live_gate": to_primitive(live_gate),
            "virtual_market_gate": to_primitive(virtual_market_gate_payload()),
        }
    )
    governor = GpuResourceGovernor()
    telemetry = governor.collect_telemetry()
    signal_payload["telemetry_assessment"] = to_primitive(
        telemetry.assess(governor.policy.vram_headroom_percent)
    )
    _print_payload(signal_payload, output_format=parsed.output_format, command="status")
    return 0


def _print_payload(
    payload: object,
    *,
    output_format: str,
    command: str | None = None,
) -> None:
    print(render_payload(payload, output_format=output_format, command=command))


if __name__ == "__main__":
    raise SystemExit(main())

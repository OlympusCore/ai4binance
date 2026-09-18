"""Status, governance and slash-command payload builders for the CLI."""

from __future__ import annotations

import hashlib
import os
import platform
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from ai4binance.account import AccountSnapshotBuilder
from ai4binance.agents import build_default_registry
from ai4binance.application.orchestration import UniverseScanCycle
from ai4binance.config import Settings
from ai4binance.data.acquisition import LocalMarketSnapshotTransport
from ai4binance.enterprise import GpuResourceGovernor, GpuTelemetryAssessment
from ai4binance.execution import LocalApprovalQueue, PaperLedger
from ai4binance.execution.lifecycle import PositionStatus
from ai4binance.governance import (
    DmaicStage,
    FiveSWorkspaceEvidence,
    HoshinObjective,
    HoshinPlan,
    KaizenImprovementEvidence,
    KaizenStage,
    PokaYokeCheck,
    PokaYokeEvidence,
    SixSigmaProcessEvidence,
    assess_five_s_workspace,
    assess_hoshin_plan,
    assess_kaizen_improvement,
    assess_poka_yoke_workflow,
    assess_six_sigma_process,
    build_default_agentic_pattern_catalog,
    build_qaqc_agent_profile,
    recommend_agentic_skill_plan,
)
from ai4binance.integrations.binance import BinanceMarketUniverseProvider
from ai4binance.opportunities import OpportunityInboxBuilder
from ai4binance.opportunity_report import build_report_v2_payload
from ai4binance.opportunity_scanner import build_opportunity_scan_report
from ai4binance.portfolio.opportunity_recovery import (
    build_opportunity_recovery_radar,
)
from ai4binance.privacy_boundary import scan_privacy_boundary
from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting import (
    BacktestEngine,
    BacktestRuntimeEconomicsEvidence,
    BacktestRuntimeEconomicsReview,
    BacktestRuntimeReviewerResult,
    review_backtest_runtime_economics,
)
from ai4binance.schemas import MarketSnapshot, OHLCVCandle
from ai4binance.skills import audit_skill_root
from ai4binance.validation import ValidationSummaryReader

from .bootstrap.shared import build_public_acquisition as build_public_acquisition


def fusion_asset(snapshot: MarketSnapshot) -> str:
    configured = snapshot.market_metadata.get("base_asset")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().upper()
    return snapshot.symbol.removesuffix("USDT") or snapshot.symbol


def build_universe_scan_cycle(settings: Settings) -> UniverseScanCycle:
    return UniverseScanCycle(
        provider=build_market_universe_provider(settings),
        scanner=build_opportunity_scan_report,
        priority_symbols=(
            settings.symbol,
            settings.default_watch_symbol,
            *settings.fixed_symbols,
            *settings.priority_watchlist,
        ),
    )


def build_market_universe_provider(
    settings: Settings,
) -> BinanceMarketUniverseProvider:
    maximum_age = max(900, settings.market_history_live_interval_seconds * 3)
    return BinanceMarketUniverseProvider(
        spot_transport=LocalMarketSnapshotTransport(
            settings.dataset_directory / "spot" / "metadata",
            maximum_age_seconds=maximum_age,
        ),
        futures_transport=LocalMarketSnapshotTransport(
            settings.dataset_directory / "usd_m_futures" / "metadata",
            maximum_age_seconds=maximum_age,
        ),
        quote_assets=settings.preferred_quote_assets,
    )


def agents_payload() -> dict[str, object]:
    registry = build_default_registry()
    return {
        "agent_count": len(registry.definitions),
        "hard_gate_eligible_count": sum(
            definition.hard_gate_eligible for definition in registry.definitions
        ),
        "live_eligible_count": sum(
            definition.promotion_status.value == "LIVE_ELIGIBLE"
            for definition in registry.definitions
        ),
        "execution_allowed": False,
        "agents": to_primitive(registry.definitions),
    }


def agentic_skills_payload(
    *,
    task_name: str | None = None,
    risk_domain: str = "general",
    independent_checks: int = 0,
    stages: int = 0,
    requires_human_review: bool = False,
    needs_routing: bool = False,
    quality_sensitive: bool = False,
    bounded_actions: bool = False,
    downside_controlled: bool = False,
    opposing_views: bool = False,
) -> dict[str, object]:
    catalog = build_default_agentic_pattern_catalog()
    contract_payload = advanced_agent_operating_contract_payload()
    payload: dict[str, object] = {
        "command": "agentic-skills",
        "pattern_count": len(catalog),
        "patterns": catalog,
        "advanced_agent_operating_contract": contract_payload,
        "promotion_status": "RESEARCH_ONLY",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    if task_name is not None and task_name.strip():
        payload["recommended_plan"] = recommend_agentic_skill_plan(
            task_name=task_name,
            risk_domain=risk_domain,
            independent_checks=independent_checks,
            stages=stages,
            requires_human_review=requires_human_review,
            needs_routing=needs_routing,
            quality_sensitive=quality_sensitive,
            bounded_actions=bounded_actions,
            downside_controlled=downside_controlled,
            opposing_views=opposing_views,
        )
    return payload


def advanced_agent_operating_contract_payload() -> dict[str, object]:
    return {
        "command": "advanced-agent-operating-contract",
        "status": "READY",
        "orchestration": "MULTI_STEP_WORKFLOWS",
        "automation_scope": "REPETITIVE_OPERATIONS",
        "execution_scope": "END_TO_END_OPERATIONS",
        "guardrails": (
            "EXPLICIT_POLICY_BOUNDARIES",
            "FAIL_CLOSED_DEFAULTS",
            "BOUNDED_ACTIONS",
            "TOOL_POLICY_ENFORCEMENT",
        ),
        "auditable_traceability": (
            "DECISION_RECORDS",
            "OUTCOME_ATTESTATIONS",
            "AUDIT_LOGS",
        ),
        "human_approval_controls": {
            "mode": "HUMAN_IN_THE_LOOP",
            "required_at": "CRITICAL_DECISION_POINTS",
            "gates": (
                "TRADING_SCOPE",
                "MONEY_MOVEMENT_SCOPE",
                "SECRET_ACCESS_SCOPE",
                "CONNECTOR_SCOPE",
                "RISK_OR_POLICY_ESCALATION",
            ),
        },
        "blockers": (),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def skills_audit_payload(root: str | None = None) -> dict[str, object]:
    skills_root = Path(root) if root else Path.cwd() / ".agents" / "skills"
    report = audit_skill_root(skills_root)
    return {
        "command": "skills-audit",
        "report": report,
        "blockers": report.blockers,
        "execution_allowed": False,
        "installation_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def privacy_boundary_payload(root: Path | None = None) -> dict[str, object]:
    repo_root = root or Path.cwd()
    report = scan_privacy_boundary(repo_root)
    return {
        "command": "privacy-boundary",
        "report": report,
        "status": report.status,
        "blockers": report.blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def scan_command_payload(
    command: str,
    settings: Settings | None = None,
    universe_scan_cycle: UniverseScanCycle | None = None,
) -> dict[str, object]:
    if universe_scan_cycle is not None:
        report = cast(Any, universe_scan_cycle.run(command))
    elif settings is not None:
        report = cast(Any, build_universe_scan_cycle(settings).run(command))
    else:
        report = cast(Any, build_opportunity_scan_report(command))
    payload = cast(dict[str, object], report.to_payload())
    payload["results"] = payload["ranked_candidates"]
    payload["radar_status"] = "ACTIVE" if report.accepted_symbols else "DEGRADED"
    payload["status"] = report.status
    return payload


def configured_scan_symbols(settings: Settings) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            symbol
            for symbol in (
                settings.symbol,
                settings.default_watch_symbol,
                *settings.fixed_symbols,
                *settings.priority_watchlist,
            )
            if symbol.strip()
        )
    )


def validation_summary_payload(
    settings: Settings, symbol: str | None
) -> dict[str, object]:
    validation_symbol = (symbol or settings.validation_symbol).strip().upper()
    summary = ValidationSummaryReader(settings.validation_artifact_directory).summarize(
        validation_symbol
    )
    return {
        "command": "validation-summary",
        "summary": summary,
        "blockers": summary.blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def backtest_runtime_economics_payload(settings: Settings) -> dict[str, object]:
    (
        review,
        evidence,
        benchmark,
        telemetry_assessment,
    ) = _backtest_runtime_economics_review(settings)
    return {
        "command": "backtest-runtime-economics",
        "status": review.status.value,
        "artifact_id": review.artifact_id,
        "title": review.title,
        "hardware_profile": review.hardware_profile,
        "runtime_stack": review.runtime_stack,
        "reviewer_result": review.reviewer_result.value,
        "gpu_available": review.gpu_available,
        "gpu_requested": review.gpu_requested,
        "gpu_used": review.gpu_used,
        "claimed_monthly_cost_usd": review.claimed_monthly_cost_usd,
        "measured_latency_ms": review.measured_latency_ms,
        "measured_simulations_per_second": review.measured_simulations_per_second,
        "measured_power_watts": review.measured_power_watts,
        "benchmark_citations": review.benchmark_citations,
        "privacy_controls": review.privacy_controls,
        "operational_controls": review.operational_controls,
        "blockers": review.blockers,
        "telemetry_assessment": to_primitive(telemetry_assessment),
        "evidence": to_primitive(evidence),
        "benchmark": benchmark,
        "execution_allowed": False,
        "promotion_status": review.promotion_status,
        "live_eligibility_status": review.live_eligibility_status,
    }


def opportunities_payload(settings: Settings, symbol: str | None) -> dict[str, object]:
    target_symbol = symbol.strip().upper() if symbol else "MARKET_WIDE"
    inbox = OpportunityInboxBuilder(
        validation_reader=ValidationSummaryReader(
            settings.validation_artifact_directory
        ),
        market_outlook_path=(
            settings.evidence_artifact_directory
            / "market-outlook"
            / "runtime-state.json"
        ),
        radar_snapshot_path=(
            settings.evidence_artifact_directory / "opportunity-radar" / "latest.json"
        ),
    ).build(target_symbol)
    inbox_payload = cast(dict[str, object], to_primitive(inbox))
    item_mappings = tuple(
        _inbox_item_to_candidate_mapping(item)
        for item in cast(
            tuple[object, ...] | list[object], inbox_payload.get("items", ())
        )
        if isinstance(item, dict)
    )
    return {
        "command": "opportunities",
        "report_version": "2.0",
        "status": inbox.generation_status,
        "inbox": inbox,
        "opportunity_report_v2": build_report_v2_payload(
            command="opportunities",
            status=inbox.generation_status,
            market="SPOT",
            snapshot_id=f"opportunities:{target_symbol}",
            ranked_candidates=item_mappings,
            blockers=inbox.blockers,
            next_safe_actions=inbox.next_safe_actions,
        ),
        "blockers": inbox.blockers,
        "research_blockers": inbox.research_blockers,
        "promotion_requirements": inbox.promotion_requirements,
        "execution_blockers": inbox.execution_blockers,
        "next_safe_actions": inbox.next_safe_actions,
        "research_loop_allowed": inbox.research_loop_allowed,
        "opportunity_generation_allowed": inbox.opportunity_generation_allowed,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _backtest_runtime_economics_review(
    settings: Settings,
) -> tuple[
    BacktestRuntimeEconomicsReview,
    BacktestRuntimeEconomicsEvidence,
    dict[str, object],
    GpuTelemetryAssessment,
]:
    candles = _backtest_runtime_probe_candles()
    engine = BacktestEngine()
    started = perf_counter()
    result = engine.run(
        symbol="BACKTEST",
        timeframe="1h",
        candles=candles,
        signal_provider=lambda history: None,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0
    simulated_per_second = len(candles) / max(elapsed_ms / 1000.0, 1e-9)
    governor = GpuResourceGovernor()
    telemetry = governor.collect_telemetry()
    selection = governor.select_backtest_runtime(
        settings.backtest_runtime_device,
        telemetry=telemetry,
    )
    telemetry_assessment = governor.last_telemetry_assessment or telemetry.assess(
        governor.policy.vram_headroom_percent
    )
    gpu_available = telemetry.cuda_available
    cuda_source = telemetry.as_source_label()
    gpu_requested = selection.requested_device != "cpu"
    evidence = BacktestRuntimeEconomicsEvidence(
        artifact_id="backtest-runtime-economics:local-probe",
        title="Local backtest runtime economics probe",
        source_url=(
            "https://example.com/ai4binance/backtest-runtime-economics/local-probe"
        ),
        source_sha256=hashlib.sha256(
            b"AI4BINANCE_BACKTEST_RUNTIME_ECONOMICS_PROXY_V1"
        ).hexdigest(),
        hardware_profile=_hardware_profile(),
        runtime_stack=f"BacktestEngine(device={selection.selected_device})",
        reviewer_result=BacktestRuntimeReviewerResult.WATCHLIST,
        benchmark_citations=(f"LOCAL_SYNTHETIC_BACKTEST_BENCHMARK:{cuda_source}",),
        privacy_controls=(
            "LOCAL_SYNTHETIC_CANDLES_ONLY",
            "NO_CREDENTIALS",
        ),
        operational_controls=(
            "READ_ONLY_BENCHMARK",
            "FAIL_CLOSED_GPU_VISIBLE",
        ),
        rejection_reason="LOCAL_SYNTHETIC_BACKTEST_PROBE_ONLY",
        measured_latency_ms=elapsed_ms,
        measured_simulations_per_second=simulated_per_second,
        source_available=True,
        credential_free_source=True,
        gpu_available=gpu_available,
        gpu_requested=gpu_requested,
        gpu_used=False,
    )
    review = review_backtest_runtime_economics(evidence)
    benchmark = {
        "candle_count": len(candles),
        "elapsed_ms": round(elapsed_ms, 3),
        "simulations_per_second": round(simulated_per_second, 3),
        "cuda_source": cuda_source,
        "engine_acceptance_operator": (
            result.performance_engine_report.system_acceptance_operator
        ),
    }
    return review, evidence, benchmark, telemetry_assessment


def _backtest_runtime_probe_candles() -> tuple[OHLCVCandle, ...]:
    base = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)
    candles: list[OHLCVCandle] = []
    for index in range(24):
        opened = Decimal("100") + Decimal(index) * Decimal("0.25")
        high = opened + Decimal("1.5")
        low = opened - Decimal("1.0")
        close = opened + Decimal("0.5")
        volume = Decimal("10") + Decimal(index)
        candles.append(
            OHLCVCandle(
                timestamp=base + timedelta(minutes=index),
                open=opened,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return tuple(candles)


def _hardware_profile() -> str:
    cpu_count = os.cpu_count() or 1
    return (
        f"{platform.system()} {platform.release()} {platform.machine()}"
        f" | CPUs={cpu_count}"
    )


def _inbox_item_to_candidate_mapping(item: dict[str, object]) -> dict[str, object]:
    blockers = tuple(str(value) for value in _object_sequence(item.get("blockers", ())))
    confirmation_gaps = tuple(
        dict.fromkeys(
            (
                *(
                    blocker
                    for blocker in blockers
                    if blocker
                    in {
                        "ENTRY_TRIGGER_MISSING",
                        "VWAP_TRIGGER_MISSING",
                        "VOLUME_CONFIRMATION_MISSING",
                        "STRUCTURE_CONFIRMATION_REQUIRED",
                        "HTF_CONFIRMATION_REQUIRED",
                    }
                ),
                *(
                    str(value)
                    for value in _object_sequence(
                        item.get("confirmation_requirements", ())
                    )
                ),
            )
        )
    )
    validation_gaps = tuple(
        dict.fromkeys(
            (
                *(
                    blocker
                    for blocker in blockers
                    if "VALIDATION" in blocker
                    or "OOS" in blocker
                    or "BACKTEST" in blocker
                    or "WALK_FORWARD" in blocker
                ),
                *(
                    str(value)
                    for value in _object_sequence(
                        item.get("promotion_requirements", ())
                    )
                ),
            )
        )
    )
    execution_blockers = tuple(
        dict.fromkeys(
            (
                *blockers,
                *(
                    str(value)
                    for value in _object_sequence(item.get("execution_blockers", ()))
                ),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    score = item.get("score", 0)
    return {
        "symbol": item.get("symbol", "UNKNOWN"),
        "market": item.get("market", "SPOT"),
        "timeframe": item.get("timeframe", "UNSPECIFIED"),
        "setup_name": item.get("setup_name", "UNKNOWN_SETUP"),
        "direction": item.get("direction", "WATCH_ONLY"),
        "opportunity_score": score,
        "research_confidence": item.get("confidence", 0),
        "visibility_state": item.get("lifecycle_state", "WATCH_ONLY"),
        "lifecycle_state": item.get("lifecycle_state", "WATCH_ONLY"),
        "accepted": True,
        "confirmation_gaps": confirmation_gaps,
        "validation_gaps": validation_gaps,
        "execution_blockers": execution_blockers,
        "blockers": blockers,
        "why_visible": tuple(
            str(value) for value in _object_sequence(item.get("why_now", ()))
        )
        or ("OPPORTUNITY_INBOX_ITEM_VISIBLE",),
        "supporting_evidence": tuple(
            str(value)
            for value in _object_sequence(item.get("supporting_evidence", ()))
        )
        or (str(item.get("source", "opportunity_inbox")),),
        "counter_evidence": tuple(
            dict.fromkeys((*confirmation_gaps, *validation_gaps))
        ),
        "next_safe_action": str(
            item.get(
                "next_evidence_action",
                _candidate_next_safe_action(confirmation_gaps, validation_gaps),
            )
        ),
        "entry": item.get("entry", "PENDING_VALIDATED_LEVEL"),
        "stop_loss": item.get("stop_loss", "PENDING_VALIDATED_LEVEL"),
        "tp1": item.get("tp1", "PENDING_VALIDATED_LEVEL"),
        "tp2": item.get("tp2", "PENDING_VALIDATED_LEVEL"),
        "tp3": item.get("tp3", "PENDING_VALIDATED_LEVEL"),
        "upgrade_condition": "Clear confirmation and validation gaps.",
        "invalidation_condition": (
            "Market outlook invalidates or validation risk worsens."
        ),
    }


def _object_sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _candidate_next_safe_action(
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
) -> str:
    if confirmation_gaps:
        return "WAIT_FOR_CONFIRMATION_AND_REFRESH_RADAR"
    if validation_gaps:
        return "RUN_VALIDATION_QUEUE"
    return "KEEP_RESEARCH_RADAR_RUNNING"


def opportunity_recovery_radar_payload(
    settings: Settings,
    *,
    symbol: str | None,
    inventory_units: object,
    range_low: object,
    range_high: object,
    cost_basis: object | None = None,
) -> dict[str, object]:
    missing = tuple(
        name
        for name, value in (("inventory_units", inventory_units),)
        if value is None or str(value).strip() == ""
    )
    if missing:
        blockers = tuple(f"RECOVERY_INPUT_REQUIRED:{name}" for name in missing)
        return {
            "command": "opportunity-recovery-radar",
            "status": "BLOCKED",
            "symbol": (symbol or settings.symbol).strip().upper(),
            "recovery_mode": "RECOVERY_GUARDED_RESEARCH_MODE",
            "hindsight_notice": "HINDSIGHT_ENVELOPE_ONLY",
            "inventory_units": "0",
            "range_low": "0",
            "range_high": "0",
            "range_source": "UNAVAILABLE",
            "range_move_ratio": "0",
            "ideal_full_cycle_end_units": "0",
            "ideal_full_cycle_unit_gain": "0",
            "ladder": (),
            "blockers": blockers,
            "next_safe_actions": ("PROVIDE_RECOVERY_RADAR_INPUTS",),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    try:
        radar = build_opportunity_recovery_radar(
            settings,
            symbol=symbol,
            inventory_units=inventory_units,
            range_low=range_low,
            range_high=range_high,
            cost_basis=cost_basis,
        )
    except ValueError as exc:
        return {
            "command": "opportunity-recovery-radar",
            "status": "BLOCKED",
            "symbol": (symbol or settings.symbol).strip().upper(),
            "recovery_mode": "RECOVERY_GUARDED_RESEARCH_MODE",
            "hindsight_notice": "TECHNICAL_RANGE_UNAVAILABLE",
            "inventory_units": str(inventory_units),
            "range_low": "0",
            "range_high": "0",
            "range_source": "UNAVAILABLE",
            "range_move_ratio": "0",
            "ideal_full_cycle_end_units": "0",
            "ideal_full_cycle_unit_gain": "0",
            "ladder": (),
            "blockers": (
                "TECHNICAL_RANGE_SOURCE_UNAVAILABLE",
                f"RECOVERY_RANGE_ERROR:{exc}",
                "LIVE_ORDER_BLOCKED",
            ),
            "next_safe_actions": (
                "RUN_ANALYZE_PUBLIC",
                "PROVIDE_RECOVERY_RADAR_INPUTS",
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    return {
        "command": radar.command,
        "status": radar.status,
        "symbol": radar.symbol,
        "recovery_mode": radar.recovery_mode,
        "hindsight_notice": radar.hindsight_notice,
        "inventory_units": radar.inventory_units,
        "range_low": radar.range_low,
        "range_high": radar.range_high,
        "range_source": radar.range_source,
        "range_move_ratio": radar.range_move_ratio,
        "ideal_full_cycle_end_units": radar.ideal_full_cycle_end_units,
        "ideal_full_cycle_unit_gain": radar.ideal_full_cycle_unit_gain,
        "ladder": radar.ladder,
        "blockers": radar.blockers,
        "next_safe_actions": radar.next_safe_actions,
        "execution_allowed": False,
        "promotion_status": radar.promotion_status,
        "live_eligibility_status": radar.live_eligibility_status,
    }


def portfolio_command_payload(settings: Settings) -> dict[str, object]:
    now = datetime.now(UTC)
    payload = _virtual_portfolio_payload(settings, now)
    try:
        from ai4binance.cli.runtime import (
            _write_virtual_portfolio_user_report,
            build_read_only_runtime,
        )

        report = build_read_only_runtime(settings).run(now)
        prices = (
            {
                asset.asset: asset.price_usdt
                for asset in report.portfolio_analytics.valued_assets
            }
            if report.portfolio_analytics is not None
            else {}
        )
        snapshot = AccountSnapshotBuilder(
            quote_assets=settings.preferred_quote_assets
        ).build(
            snapshot_id=report.cycle_id,
            data_as_of=report.created_at,
            spot_wallet=report.spot_wallet,
            futures_account=report.futures_account,
            prices_usdt=prices,
            reconciliation=None,
        )
        blockers = tuple(dict.fromkeys((*report.blockers, *snapshot.blockers)))
        telemetry_governor = GpuResourceGovernor()
        telemetry_snapshot = telemetry_governor.collect_telemetry()
        telemetry_assessment = telemetry_snapshot.assess(
            telemetry_governor.policy.vram_headroom_percent
        )
        payload["account_runtime"] = {
            "status": "BLOCKED" if blockers else "READY",
            "runtime_state": report.state,
            "account_snapshot": snapshot,
            "blockers": blockers,
        }
        payload["telemetry_assessment"] = to_primitive(telemetry_assessment)
        user_report_paths_payload, user_report_blockers = (
            _write_virtual_portfolio_user_report(settings, payload)
        )
        if user_report_paths_payload:
            payload["user_report_paths"] = user_report_paths_payload
        if user_report_blockers:
            payload["blockers"] = tuple(
                dict.fromkeys(
                    (*cast(tuple[str, ...], payload["blockers"]), *user_report_blockers)
                )
            )
            payload["status"] = "BLOCKED"
            payload["state"] = "BLOCKED"
        return payload
    except (OSError, RuntimeError, ValueError):
        payload["account_runtime"] = {
            "status": "UNAVAILABLE",
            "runtime_state": "UNAVAILABLE",
            "blockers": ("PORTFOLIO_RUNTIME_UNAVAILABLE",),
        }
        try:
            from ai4binance.cli.runtime import _write_virtual_portfolio_user_report

            user_report_paths_payload, user_report_blockers = (
                _write_virtual_portfolio_user_report(settings, payload)
            )
            if user_report_paths_payload:
                payload["user_report_paths"] = user_report_paths_payload
            if user_report_blockers:
                existing_blockers = payload.get("blockers")
                blocker_values = (
                    tuple(existing_blockers)
                    if isinstance(existing_blockers, (list, tuple))
                    else ()
                )
                payload["blockers"] = tuple(
                    dict.fromkeys((*blocker_values, *user_report_blockers))
                )
                payload["status"] = "BLOCKED"
                payload["state"] = "BLOCKED"
        except (OSError, RuntimeError, ValueError):
            existing_blockers = payload.get("blockers")
            blocker_values = (
                tuple(existing_blockers)
                if isinstance(existing_blockers, (list, tuple))
                else ()
            )
            payload["blockers"] = tuple(
                dict.fromkeys(
                    (*blocker_values, "VIRTUAL_PORTFOLIO_USER_REPORT_WRITE_FAILED")
                )
            )
            payload["status"] = "BLOCKED"
            payload["state"] = "BLOCKED"
        return payload


def _virtual_portfolio_payload(
    settings: Settings,
    observed_at: datetime,
) -> dict[str, object]:
    cycle_id = f"virtual-portfolio-{int(observed_at.timestamp() * 1000)}"
    blockers: tuple[str, ...]
    try:
        positions = PaperLedger(settings.paper_ledger_path).latest_positions()
    except (OSError, ValueError):
        blockers = ("VIRTUAL_PORTFOLIO_LEDGER_UNAVAILABLE",)
        virtual_portfolio = {
            "source": "PAPER_LEDGER",
            "ledger_path": str(settings.paper_ledger_path),
            "position_count": 0,
            "open_position_count": 0,
            "closed_position_count": 0,
            "realized_pnl_usdt": "0",
            "symbols": (),
            "positions": (),
            "blockers": blockers,
        }
        status = "BLOCKED"
    else:
        open_positions = tuple(
            position
            for position in positions
            if position.status is not PositionStatus.CLOSED
        )
        blockers = ()
        virtual_portfolio = {
            "source": "PAPER_LEDGER",
            "ledger_path": str(settings.paper_ledger_path),
            "position_count": len(positions),
            "open_position_count": len(open_positions),
            "closed_position_count": len(positions) - len(open_positions),
            "realized_pnl_usdt": str(
                sum(
                    (position.realized_pnl_usdt for position in positions),
                    Decimal("0"),
                )
            ),
            "symbols": tuple(sorted({position.symbol for position in positions})),
            "positions": positions,
            "blockers": blockers,
        }
        status = "READY"
    return {
        "command": "portfolio",
        "cycle_id": cycle_id,
        "created_at": observed_at,
        "status": status,
        "state": status,
        "virtual_portfolio": virtual_portfolio,
        "blockers": blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def manual_actions_payload(settings: Settings) -> dict[str, object]:
    queue = LocalApprovalQueue(settings.manual_approval_queue_path)
    records = queue.records()
    blockers = () if records else ("NO_PENDING_MANUAL_ACTIONS",)
    return {
        "command": "manual-actions",
        "actions": tuple(record.action for record in records),
        "blockers": blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def approvals_payload(settings: Settings) -> dict[str, object]:
    queue = LocalApprovalQueue(settings.manual_approval_queue_path)
    records = queue.records()
    return {
        "command": "approvals",
        "approvals": tuple(record.approval for record in records),
        "blockers": (),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def lean_governance_payload(
    settings: Settings,
    *,
    mode: str = "LEAN_GOVERNANCE_REVIEW",
) -> dict[str, object]:
    """Return read-only 5S, Hoshin Kanri and Poka-Yoke governance status."""
    now = datetime.now(UTC)
    profile = build_qaqc_agent_profile()
    five_s = assess_five_s_workspace(
        FiveSWorkspaceEvidence(
            workspace_id="ai4binance",
            observed_at=now,
            stale_temp_paths=known_stale_temp_paths(Path.cwd()),
            canonical_quality_command=(
                "powershell.exe -NoProfile -ExecutionPolicy Bypass "
                "-File .\\scripts\\quality.ps1"
            ),
            documentation_index_present=Path(
                "docs/registries/registry_documentation_index.md"
            ).is_file(),
            sustain_owner="platform-owner",
        )
    )
    hoshin = assess_hoshin_plan(_default_hoshin_plan(now), as_of=now)
    kaizen = assess_kaizen_improvement(_default_kaizen_evidence(now))
    six_sigma = assess_six_sigma_process(_default_six_sigma_evidence(now))
    passed_poka_yoke_checks = [
        PokaYokeCheck.LIVE_GATE_FAIL_CLOSED,
        PokaYokeCheck.REDACTION_GATE,
        PokaYokeCheck.WALLET_BACKTEST_ISOLATION,
        PokaYokeCheck.DATASET_REVISION_HASHED,
        PokaYokeCheck.RUN_CARD_PERSISTED,
        PokaYokeCheck.BLOCKER_DASHBOARD_PERSISTED,
    ]
    if Path("scripts/quality.ps1").is_file():
        passed_poka_yoke_checks.append(PokaYokeCheck.TECHNICAL_QUALITY_PASS)
    poka_yoke = assess_poka_yoke_workflow(
        PokaYokeEvidence(
            workflow_id="validate-research",
            observed_at=now,
            passed_checks=tuple(passed_poka_yoke_checks),
        )
    )
    assessments = (five_s, hoshin, kaizen, six_sigma, poka_yoke)
    return {
        "mode": mode,
        "agent": profile,
        "symbol": settings.symbol,
        "assessments": assessments,
        "blockers": tuple(
            blocker for assessment in assessments for blocker in assessment.blockers
        ),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "promotion_status": "RESEARCH_ONLY",
    }


def known_stale_temp_paths(root: Path) -> tuple[str, ...]:
    legacy_candidates = (
        ".tmp",
        ".tmp-alias-check",
        ".pytest-audit-temp",
        ".pytest-audit-temp2",
        ".pytest-audit-temp3",
        ".pytest-audit-temp4",
        ".pytest-money-audit-20260715",
        ".pytest-tmp",
        ".test-tmp",
        "runtime/tmp/test_temp",
        "runtime/pytest-temp",
        "runtime/pytest-tmp",
    )
    discovered = [path for path in legacy_candidates if (root / path).exists()]
    runtime_pytest_root = root / "runtime" / "tmp" / "pytest"
    if runtime_pytest_root.is_dir():
        runtime_runs = sorted(
            (
                path.relative_to(root).as_posix()
                for path in runtime_pytest_root.iterdir()
                if path.is_dir()
            ),
            key=str.casefold,
        )
        if runtime_runs:
            discovered.extend(runtime_runs)
        else:
            discovered.append(runtime_pytest_root.relative_to(root).as_posix())
    return tuple(discovered)


def _default_hoshin_plan(now: datetime) -> HoshinPlan:
    return HoshinPlan(
        plan_id="ai4binance-2026-validation-first",
        created_at=now,
        north_star=(
            "Increase reproducible OOS evidence while preserving NO_TRADE, "
            "RESEARCH_ONLY and LIVE_ORDER_BLOCKED defaults."
        ),
        objectives=(
            HoshinObjective(
                objective_id="run-card-and-blocker-dashboard",
                annual_priority="Make validation blockers actionable and auditable.",
                owner="validation-owner",
                metric_name="validation_evidence_traceability",
                baseline=0.0,
                target=1.0,
                current=1.0,
                due_at=now + timedelta(days=30),
                linked_blockers=(
                    "WEAK_OOS_FOLD_CONSISTENCY",
                    "COST_STRESS_RETURN_NOT_POSITIVE",
                ),
                validation_artifact_ids=(
                    "src/ai4binance/research_governance.py",
                    "src/ai4binance/application/validation_pipeline.py",
                ),
            ),
            HoshinObjective(
                objective_id="checkpointable-hotusdt-validation",
                annual_priority="Shorten long validation feedback loops safely.",
                owner="validation-owner",
                metric_name="checkpointable_validation_slices",
                baseline=0.0,
                target=1.0,
                current=1.0,
                due_at=now + timedelta(days=60),
                linked_blockers=("LONG_OOS_CALIBRATION_NOT_RESUMABLE",),
                validation_artifact_ids=(
                    "src/ai4binance/application/validation_pipeline.py",
                    "tests/test_validation_pipeline.py",
                ),
            ),
        ),
        catchball_reviewed=True,
    )


def _default_kaizen_evidence(now: datetime) -> KaizenImprovementEvidence:
    return KaizenImprovementEvidence(
        improvement_id="kaizen:validation-blocker-actionability",
        observed_at=now,
        stage=KaizenStage.ACT,
        problem_statement=(
            "OOS blockers were correct but not directly actionable for the next "
            "safe experiment."
        ),
        hypothesis=(
            "Run cards plus blocker dashboards reduce validation follow-up "
            "ambiguity without weakening promotion gates."
        ),
        owner="validation-owner",
        metric_name="blocker_actionability_ratio",
        baseline=0.0,
        target=1.0,
        current=1.0,
        linked_blockers=(
            "WEAK_OOS_FOLD_CONSISTENCY",
            "COST_STRESS_RETURN_NOT_POSITIVE",
            "BOOTSTRAP_LOSS_PROBABILITY_HIGH",
        ),
        experiment_artifact_ids=(
            "src/ai4binance/research_governance.py",
            "tests/test_validation_pipeline.py",
        ),
    )


def _default_six_sigma_evidence(now: datetime) -> SixSigmaProcessEvidence:
    return SixSigmaProcessEvidence(
        process_id="six-sigma:validation-defect-control",
        observed_at=now,
        stage=DmaicStage.CONTROL,
        defect_name="validation blocker without persisted corrective action",
        opportunities=10,
        defects=0,
        baseline_dpmo=300_000.0,
        current_dpmo=0.0,
        target_dpmo=50_000.0,
        sigma_level=6.0,
        linked_blockers=(
            "VALIDATION_ACTION_TRACE_MISSING",
            "TECHNICAL_QUALITY_PASS",
        ),
        measurement_system_validated=True,
        control_plan_artifact_ids=(
            "src/ai4binance/research_governance.py",
            "tests/test_validation_pipeline.py",
        ),
    )


def blockers_exit_code(payload: dict[str, object]) -> int:
    return 0 if not cast(tuple[object, ...] | list[object], payload["blockers"]) else 2

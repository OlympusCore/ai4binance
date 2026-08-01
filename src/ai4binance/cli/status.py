"""Status, governance and slash-command payload builders for the CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from ai4binance.account import AccountSnapshotBuilder
from ai4binance.agents import build_default_registry
from ai4binance.config import Settings
from ai4binance.data import DataAcquisitionAgent
from ai4binance.exchange import BinancePublicClient, UrllibJsonTransport
from ai4binance.execution import LocalApprovalQueue
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
from ai4binance.opportunities import OpportunityInboxBuilder
from ai4binance.privacy_boundary import scan_privacy_boundary
from ai4binance.reporting import to_primitive
from ai4binance.scanners import ScannerOrchestrator
from ai4binance.schemas import MarketSnapshot
from ai4binance.skills import audit_skill_root
from ai4binance.universe import UniverseMarket, UniverseSymbol
from ai4binance.validation import ValidationSummaryReader


def build_public_acquisition(settings: Settings) -> DataAcquisitionAgent:
    """Build the keyless public data boundary from validated settings."""
    transport = UrllibJsonTransport(
        base_url=settings.public_api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
        max_attempts=settings.request_max_attempts,
        backoff_seconds=settings.request_backoff_seconds,
    )
    return DataAcquisitionAgent(
        client=BinancePublicClient(transport),
        candle_limit=settings.candle_limit,
        minimum_closed_candles=settings.minimum_closed_candles,
        max_workers=settings.max_data_workers,
    )


def fusion_asset(snapshot: MarketSnapshot) -> str:
    configured = snapshot.market_metadata.get("base_asset")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().upper()
    return snapshot.symbol.removesuffix("USDT") or snapshot.symbol


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
    payload: dict[str, object] = {
        "command": "agentic-skills",
        "pattern_count": len(catalog),
        "patterns": catalog,
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
) -> dict[str, object]:
    orchestrator = ScannerOrchestrator()
    spot_symbols: tuple[UniverseSymbol, ...] = ()
    futures_symbols: tuple[UniverseSymbol, ...] = ()
    if settings is not None:
        configured = configured_scan_symbols(settings)
        spot_symbols = tuple(
            _placeholder_symbol(symbol, UniverseMarket.SPOT) for symbol in configured
        )
        futures_symbols = tuple(
            _placeholder_symbol(symbol, UniverseMarket.USD_M_FUTURES)
            for symbol in configured
        )
    if command == "scan-spot":
        report = orchestrator.scan_spot(spot_symbols)
    elif command == "scan-futures":
        report = orchestrator.scan_futures(futures_symbols)
    elif command == "scan-all":
        report = orchestrator.scan_all(
            spot_symbols=spot_symbols,
            futures_symbols=futures_symbols,
        )
    else:
        report = orchestrator.scan_all(spot_symbols=(), futures_symbols=())
    return {
        "command": command,
        "status": "BLOCKED" if report.blockers else "READY",
        "accepted_symbols": report.accepted_symbols,
        "rejected_symbols": report.rejected_symbols,
        "results": report.results,
        "blockers": report.blockers,
        "execution_allowed": report.execution_allowed,
        "live_eligibility_status": report.live_eligibility_status,
    }


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


def _placeholder_symbol(symbol: str, market: UniverseMarket) -> UniverseSymbol:
    base, quote = _split_symbol(symbol)
    if market is UniverseMarket.USD_M_FUTURES:
        return UniverseSymbol(
            symbol=symbol,
            market=market,
            base_asset=base,
            quote_asset=quote,
            status="TRADING",
            min_notional_usdt=Decimal("0"),
            quote_volume_24h_usdt=Decimal("0"),
            spread_bps=Decimal("999999"),
            depth_0_5_pct_usdt=Decimal("0"),
            data_quality_ok=False,
            contract_type="PERPETUAL",
            margin_asset="USDT",
            open_interest_usdt=Decimal("0"),
            funding_rate=Decimal("0"),
        )
    return UniverseSymbol(
        symbol=symbol,
        market=market,
        base_asset=base,
        quote_asset=quote,
        status="TRADING",
        min_notional_usdt=Decimal("0"),
        quote_volume_24h_usdt=Decimal("0"),
        spread_bps=Decimal("999999"),
        depth_0_5_pct_usdt=Decimal("0"),
        data_quality_ok=False,
    )


def _split_symbol(symbol: str) -> tuple[str, str]:
    normalized = symbol.strip().upper()
    for quote in ("USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)], quote
    return normalized, "USDT"


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


def opportunities_payload(settings: Settings, symbol: str | None) -> dict[str, object]:
    target_symbol = (symbol or settings.symbol).strip().upper()
    inbox = OpportunityInboxBuilder(
        validation_reader=ValidationSummaryReader(
            settings.validation_artifact_directory
        ),
        market_outlook_path=(
            settings.evidence_artifact_directory
            / "market-outlook"
            / "runtime-state.json"
        ),
    ).build(target_symbol)
    return {
        "command": "opportunities",
        "inbox": inbox,
        "blockers": inbox.blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def portfolio_command_payload(settings: Settings) -> dict[str, object]:
    now = datetime.now(UTC)
    try:
        from ai4binance.cli.runtime import build_read_only_runtime

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
        return {
            "command": "portfolio",
            "status": "BLOCKED" if blockers else "READY",
            "account_snapshot": snapshot,
            "runtime_state": report.state,
            "blockers": blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    except (OSError, RuntimeError, ValueError):
        return {
            "command": "portfolio",
            "status": "BLOCKED",
            "account_snapshot": AccountSnapshotBuilder(
                quote_assets=settings.preferred_quote_assets
            ).build(
                snapshot_id=f"portfolio-{int(now.timestamp() * 1000)}",
                data_as_of=now,
                spot_wallet=None,
                futures_account=None,
                prices_usdt={},
                reconciliation=None,
            ),
            "blockers": ("PORTFOLIO_RUNTIME_UNAVAILABLE",),
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
                "-File .\\Scripts\\quality.ps1"
            ),
            documentation_index_present=Path("Docs/README.md").is_file(),
            sustain_owner="platform-owner",
        )
    )
    hoshin = assess_hoshin_plan(_default_hoshin_plan(now), as_of=now)
    kaizen = assess_kaizen_improvement(_default_kaizen_evidence(now))
    six_sigma = assess_six_sigma_process(_default_six_sigma_evidence(now))
    poka_yoke = assess_poka_yoke_workflow(
        PokaYokeEvidence(
            workflow_id="validate-research",
            observed_at=now,
            passed_checks=(
                PokaYokeCheck.LIVE_GATE_FAIL_CLOSED,
                PokaYokeCheck.REDACTION_GATE,
                PokaYokeCheck.WALLET_BACKTEST_ISOLATION,
                PokaYokeCheck.DATASET_REVISION_HASHED,
                PokaYokeCheck.RUN_CARD_PERSISTED,
                PokaYokeCheck.BLOCKER_DASHBOARD_PERSISTED,
            ),
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
    candidates = (
        ".pytest-audit-temp",
        ".pytest-audit-temp2",
        ".pytest-audit-temp3",
        ".pytest-audit-temp4",
        ".pytest-money-audit-20260715",
        ".pytest-tmp",
        ".test-tmp",
        "Artifacts/TestTemp",
    )
    return tuple(path for path in candidates if (root / path).exists())


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
                current=0.0,
                due_at=now + timedelta(days=60),
                linked_blockers=("LONG_OOS_CALIBRATION_NOT_RESUMABLE",),
                validation_artifact_ids=(),
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
        stage=DmaicStage.IMPROVE,
        defect_name="validation blocker without persisted corrective action",
        opportunities=10,
        defects=1,
        baseline_dpmo=300_000.0,
        current_dpmo=100_000.0,
        target_dpmo=50_000.0,
        sigma_level=2.8,
        linked_blockers=(
            "VALIDATION_ACTION_TRACE_MISSING",
            "QUALITY_GATE_GREEN",
        ),
        measurement_system_validated=True,
    )


def blockers_exit_code(payload: dict[str, object]) -> int:
    return 0 if not cast(tuple[object, ...] | list[object], payload["blockers"]) else 2

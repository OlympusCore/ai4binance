"""Research, validation, RAG and public-market CLI command handlers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any, cast

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import (
    ResearchValidationService,
    WhaleFusionCycle,
    WhaleFusionResearchService,
)
from ai4binance.cli.bootstrap.shared import virtual_runtime_decision_payload
from ai4binance.config import Settings
from ai4binance.core.errors import ExchangeError
from ai4binance.data import (
    BinanceVisionIngestor,
    DatasetIntegrityError,
    ParquetOHLCVArchive,
)
from ai4binance.data.binance_vision import BinanceVisionSyncResult
from ai4binance.data.revision import DatasetRevisionBuilder
from ai4binance.decision import build_no_trade_signal
from ai4binance.governance import (
    build_enterprise_ai_crew_plan,
    market_outlook_workflow,
    preview_workflow,
)
from ai4binance.multiops.llmops.contracts import TaskClass, TaskCriticality
from ai4binance.opportunity_radar import build_opportunity_radar_snapshot
from ai4binance.outlook import MarketOutlookArtifactStore
from ai4binance.rag import (
    AdvisoryProviderResult,
    LocalRagIndexer,
    OllamaAdvisoryRunner,
    RagAuthorityCeiling,
    RagEvidenceQualityStatus,
    RagIndex,
    RagSearchHit,
    RetrievalRequest,
    evaluate_governed_retrieval,
    render_rag_ui,
    review_rag_evidence_quality,
)
from ai4binance.reporting import to_primitive
from ai4binance.research_runtime import build_research_application_service
from ai4binance.schemas import MarketSnapshot
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.validation.oos_maturity import prepare_spot_oos_deployment
from ai4binance.validation_pipeline_runtime import (
    SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO,
    HistoricalValidationRuntime,
)
from ai4binance.virtual_wallet_journal import (
    VirtualWalletJournal,
    VirtualWalletJournalError,
)
from ai4binance.whale_fusion import FusionAuditWriter, WhaleFusionEngine
from ai4binance.whale_fusion.integration import (
    WhaleFusionEnvelope,
    attach_fusion_result,
)

from .bootstrap import (
    SnapshotAcquirer,
    normalize_cli_symbol,
    parse_as_of,
    safe_validation_symbol,
)
from .opportunity_radar_persistence import write_opportunity_radar_snapshot
from .status import build_public_acquisition, fusion_asset


def run_validate_research(settings: Settings, symbol: str | None) -> int:
    try:
        validation_symbol = normalize_cli_symbol(symbol) or settings.validation_symbol
        batch = ResearchValidationService(
            archive=ParquetOHLCVArchive(
                settings.dataset_directory / "spot"
                if settings.market_history_local_candles
                else settings.dataset_directory
            ),
            artifact_directory=settings.validation_artifact_directory,
            runtime=HistoricalValidationRuntime(
                report_directory=settings.backtest_report_directory,
                position_notional_to_equity_ratio=(
                    SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO
                ),
            ),
        ).run(validation_symbol, settings.timeframes)
        run_cards = tuple(
            cast(dict[str, object], to_primitive(result.run_card))
            for result in batch.results
            if result.run_card is not None
        )
        oos_deployment = (
            prepare_spot_oos_deployment(
                artifact_root=settings.validation_artifact_directory,
                deployment_path=settings.runtime_validation_deployment_path,
                specification_path=Path(
                    "config/research/virtual_market_acceptance.yaml"
                ),
                run_cards=run_cards,
                observed_at=datetime.now(UTC),
            )
            if run_cards
            else {
                "status": "VALIDATION_RUN_CARDS_MISSING",
                "subject_count": 0,
                "blockers": ["VALIDATION_RUN_CARDS_MISSING"],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )
        payload: dict[str, object] = {
            "symbol": batch.symbol,
            "results": tuple(
                {
                    "playbook": result.playbook,
                    "timeframe": result.timeframe,
                    "candle_count": result.candle_count,
                    "promotion_status": result.promotion_status,
                    "blockers": result.blockers,
                    "backtest_metrics": (
                        cast(Any, result.backtest).metrics
                        if result.backtest is not None
                        else None
                    ),
                    "tuning_report_id": (
                        cast(Any, result.tuning).report_id
                        if result.tuning is not None
                        else None
                    ),
                    "robustness": result.robustness,
                }
                for result in batch.results
            ),
            "execution_allowed": batch.execution_allowed,
            "live_eligibility_status": batch.live_eligibility_status,
            "oos_deployment": oos_deployment,
        }
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        return 0
    except (DatasetIntegrityError, FileNotFoundError, ValueError, OSError):
        validation_symbol = safe_validation_symbol(symbol, settings)
        blocked_payload: dict[str, object] = {
            "symbol": validation_symbol,
            "validation_status": "RESEARCH_ONLY",
            "blockers": ("VALIDATION_DATA_UNAVAILABLE_OR_INVALID",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        print(
            json.dumps(
                to_primitive(blocked_payload), ensure_ascii=False, sort_keys=True
            )
        )
        return 2


def run_crew_plan(settings: Settings, symbol: str | None) -> int:
    validation_symbol = normalize_cli_symbol(symbol) or settings.validation_symbol
    plan = build_enterprise_ai_crew_plan(
        validation_symbol=validation_symbol,
        timeframes=settings.timeframes,
    )
    workflow_preview = preview_workflow(
        market_outlook_workflow(),
        validation_points=("risk_evaluation", "paper_proposal", "closure_review"),
    )
    payload: dict[str, object] = {
        "process_id": plan.process_id,
        "validation_symbol": plan.validation_symbol,
        "governance": plan.governance,
        "biweekly_validation_task": plan.biweekly_validation_task,
        "topological_order": plan.topological_order(),
        "workflow_preview": workflow_preview,
        "roles": plan.roles,
        "engines": plan.engines,
        "tasks": plan.tasks,
        "execution_allowed": plan.execution_allowed,
        "live_eligibility_status": plan.live_eligibility_status,
    }
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def run_second_brain(
    settings: Settings,
    *,
    query: str | None,
    subject: str | None,
    use_llm: bool,
    render_ui: bool,
) -> int:
    resolved_query = query or subject or "BTCUSDT validation blockers"
    try:
        index = LocalRagIndexer(Path.cwd()).build()
    except ValueError:
        blocked_payload: dict[str, object] = {
            "query": resolved_query,
            "hits": (),
            "advisory": None,
            "blockers": ("RAG_INDEX_UNAVAILABLE",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        print(
            json.dumps(
                to_primitive(blocked_payload), ensure_ascii=False, sort_keys=True
            )
        )
        return 2
    index.write(settings.second_brain_index_path)
    production_artifact_path = _write_second_brain_production_artifact(index)
    hits = index.query(
        resolved_query,
        source_prefixes=(
            "docs",
            "artifacts",
            "runtime/artifacts/research/backtest/validation",
            "runtime/reports/backtest",
            "runtime/data/market",
        ),
        authorities=("READ_ONLY", "RESEARCH_ONLY"),
        classifications=("PUBLIC_RESEARCH",),
    )
    retrieval_request = RetrievalRequest(
        query_id=f"second-brain:{resolved_query}",
        query_text=resolved_query,
        task_type="second_brain_query",
        task_class=TaskClass.MODERATE,
        criticality=TaskCriticality.MEDIUM,
        authority_ceiling=(
            RagAuthorityCeiling.ADVISORY_ONLY
            if use_llm
            else RagAuthorityCeiling.REPORT_ONLY
        ),
        allowed_source_prefixes=(
            "docs",
            "artifacts",
            "runtime/artifacts/research/backtest/validation",
            "runtime/reports/backtest",
            "runtime/data/market",
        ),
        required_authorities=("READ_ONLY", "RESEARCH_ONLY"),
        required_classifications=("PUBLIC_RESEARCH",),
        allow_advisory_fusion=use_llm,
    )
    evidence_quality = review_rag_evidence_quality(
        query_id=f"second-brain:{resolved_query}",
        hits=hits,
        citations=tuple(hit.source_uri for hit in hits),
        now=datetime.now(UTC),
    )
    governed_retrieval = evaluate_governed_retrieval(
        retrieval_request,
        hits=hits,
        citations=tuple(hit.source_uri for hit in hits),
        now=datetime.now(UTC),
    )
    advisory = (
        _run_local_advisory(_rag_prompt(resolved_query, hits), hits)
        if use_llm
        and evidence_quality.status
        is RagEvidenceQualityStatus.RESEARCH_ONLY_RAG_EVIDENCE
        and governed_retrieval.advisory_fusion_allowed
        else None
    )
    if advisory is not None:
        governed_retrieval = evaluate_governed_retrieval(
            retrieval_request,
            hits=hits,
            citations=tuple(hit.source_uri for hit in hits),
            now=datetime.now(UTC),
            advisory_result=advisory,
        )
    if render_ui:
        ui_path = settings.second_brain_index_path.with_suffix(".html")
        ui_path.parent.mkdir(parents=True, exist_ok=True)
        ui_path.write_text(render_rag_ui(index, hits), encoding="utf-8")
    else:
        ui_path = None
    payload: dict[str, object] = {
        "index_id": index.index_id,
        "index_path": str(settings.second_brain_index_path),
        "production_artifact_path": str(production_artifact_path),
        "query": resolved_query,
        "hits": hits,
        "evidence_quality": evidence_quality,
        "governed_retrieval": governed_retrieval,
        "advisory": advisory,
        "ui_path": str(ui_path) if ui_path is not None else None,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def run_virtual_market_retrieval_eval_command(
    settings: Settings,
    *,
    query: str | None,
) -> int:
    resolved_query = query or "VIRTUAL_MARKET governance blockers"
    try:
        index = LocalRagIndexer(Path.cwd()).build()
    except ValueError:
        blocked_payload: dict[str, object] = {
            "query": resolved_query,
            "hits": (),
            "advisory": None,
            "blockers": ("RAG_INDEX_UNAVAILABLE",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        print(
            json.dumps(
                to_primitive(blocked_payload), ensure_ascii=False, sort_keys=True
            )
        )
        return 2

    index.write(settings.second_brain_index_path)
    production_artifact_path = _write_second_brain_production_artifact(index)
    hits = index.query(
        resolved_query,
        source_prefixes=(
            "docs",
            "artifacts",
            "runtime/artifacts/research/backtest/validation",
            "runtime/reports/backtest",
            "runtime/data/market",
        ),
        authorities=("READ_ONLY", "RESEARCH_ONLY"),
        classifications=("PUBLIC_RESEARCH",),
    )
    retrieval_request = RetrievalRequest(
        query_id=f"virtual-market-retrieval-eval:{resolved_query}",
        query_text=resolved_query,
        task_type="virtual_market_retrieval_eval",
        task_class=TaskClass.MODERATE,
        criticality=TaskCriticality.MEDIUM,
        authority_ceiling=RagAuthorityCeiling.REPORT_ONLY,
        allowed_source_prefixes=(
            "docs",
            "artifacts",
            "runtime/artifacts/research/backtest/validation",
            "runtime/reports/backtest",
            "runtime/data/market",
        ),
        required_authorities=("READ_ONLY", "RESEARCH_ONLY"),
        required_classifications=("PUBLIC_RESEARCH",),
        allow_advisory_fusion=False,
    )
    evidence_quality = review_rag_evidence_quality(
        query_id=f"virtual-market-retrieval-eval:{resolved_query}",
        hits=hits,
        citations=tuple(hit.source_uri for hit in hits),
        now=datetime.now(UTC),
    )
    governed_retrieval = evaluate_governed_retrieval(
        retrieval_request,
        hits=hits,
        citations=tuple(hit.source_uri for hit in hits),
        now=datetime.now(UTC),
    )
    artifact_path = (
        Path.cwd()
        / "runtime"
        / "artifacts"
        / "virtual-market"
        / "retrieval-eval"
        / "latest.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "command": "virtual-market-retrieval-eval",
        "status": "READY",
        "query": resolved_query,
        "index_id": index.index_id,
        "index_path": str(settings.second_brain_index_path),
        "production_artifact_path": str(production_artifact_path),
        "hits": hits,
        "evidence_quality": evidence_quality,
        "governed_retrieval": governed_retrieval,
        "artifact_path": str(artifact_path),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    artifact_path.write_text(
        json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def _run_local_advisory(
    prompt: str,
    hits: tuple[RagSearchHit, ...],
) -> AdvisoryProviderResult:
    return OllamaAdvisoryRunner().run(prompt, hits)


def run_sync_validation_data(
    settings: Settings,
    symbol: str | None,
    as_of: str | None,
) -> int:
    validation_symbol = normalize_cli_symbol(symbol) or settings.validation_symbol
    as_of_date = parse_as_of(as_of)
    archive_root = (
        settings.dataset_directory / "spot"
        if settings.market_history_local_candles
        else settings.dataset_directory
    )
    archive = ParquetOHLCVArchive(archive_root)
    if settings.market_history_local_candles:
        sync_results = tuple(
            BinanceVisionSyncResult(
                symbol=validation_symbol,
                timeframe=timeframe,
                source_files=(),
                dataset_manifest=archive.manifest(validation_symbol, timeframe),
                source_manifest_path=str(
                    archive_root / validation_symbol / "collection-progress.json"
                ),
            )
            for timeframe in settings.timeframes
        )
    else:
        sync_results = BinanceVisionIngestor.with_network(archive).sync(
            validation_symbol,
            settings.timeframes,
            as_of=as_of_date,
        )
    revision_builder = DatasetRevisionBuilder(archive_root)
    revision = revision_builder.build(
        symbol=validation_symbol,
        timeframes=settings.timeframes,
        generated_at=datetime.now(UTC),
    )
    revision_path = revision_builder.write(revision)
    payload = {
        "symbol": validation_symbol,
        "as_of_exclusive": as_of_date.isoformat(),
        "sync_results": sync_results,
        "revision": revision,
        "revision_path": str(revision_path),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def run_public_research_command(
    command: str,
    settings: Settings,
    *,
    public_acquisition: SnapshotAcquirer | None,
    whale_fusion_cycle: WhaleFusionCycle | None,
    virtual_wallet_journal: VirtualWalletJournal | None = None,
    cycle_report: dict[str, object] | None = None,
) -> int:
    acquisition = public_acquisition or build_public_acquisition(settings)
    try:
        snapshot = acquisition.acquire(settings.symbol, settings.timeframes)
        if command == "whale-fusion-research":
            return _run_whale_fusion_research(
                settings,
                snapshot=snapshot,
                whale_fusion_cycle=whale_fusion_cycle,
            )
        if command == "archive-public":
            return _run_archive_public(settings, snapshot=snapshot)
        return _run_research_or_analysis(
            settings,
            command=command,
            snapshot=snapshot,
            virtual_wallet_journal=virtual_wallet_journal,
            cycle_report=cycle_report,
        )
    except VirtualWalletJournalError:
        signal = build_no_trade_signal(
            symbol=settings.symbol,
            timeframes=settings.timeframes,
            market_type=settings.market_type,
            blocker="VIRTUAL_WALLET_JOURNAL_FAILED",
        )
        print(json.dumps(to_primitive(signal), ensure_ascii=False, sort_keys=True))
        return 2
    except (ExchangeError, ValueError, OSError):
        signal = build_no_trade_signal(
            symbol=settings.symbol,
            timeframes=settings.timeframes,
            market_type=settings.market_type,
            blocker="PUBLIC_DATA_ACQUISITION_FAILED",
        )
        print(json.dumps(to_primitive(signal), ensure_ascii=False, sort_keys=True))
        return 2


def _run_whale_fusion_research(
    settings: Settings,
    *,
    snapshot: MarketSnapshot,
    whale_fusion_cycle: WhaleFusionCycle | None,
) -> int:
    cycle = whale_fusion_cycle or WhaleFusionCycle(
        snapshot_id=snapshot.snapshot_id,
        symbol=snapshot.symbol,
        asset=fusion_asset(snapshot),
    )
    fusion_workflow = WhaleFusionResearchService(
        engine=WhaleFusionEngine(),
        orchestrator=EnterpriseOrchestrator(
            minimum_candles=settings.minimum_closed_candles
        ),
        envelope_builder=WhaleFusionEnvelope,
        snapshot_attacher=attach_fusion_result,
        audit_writer=FusionAuditWriter(
            settings.audit_directory / "whale_fusion_events.jsonl"
        ),
    ).run(snapshot, cycle)
    whale_result = fusion_workflow.analysis.agent_results.get("whale")
    payload = {
        "snapshot_id": snapshot.snapshot_id,
        "symbol": snapshot.symbol,
        "fusion": fusion_workflow.fusion,
        "whale_agent": whale_result,
        "decision": fusion_workflow.analysis.final_decision,
        "audit_written": fusion_workflow.audit_written,
        "blockers": fusion_workflow.blockers,
        "execution_allowed": fusion_workflow.execution_allowed,
        "live_eligibility_status": fusion_workflow.live_eligibility_status,
    }
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def _run_archive_public(settings: Settings, *, snapshot: MarketSnapshot) -> int:
    archive = ParquetOHLCVArchive(
        settings.dataset_directory / "spot"
        if settings.market_history_local_candles
        else settings.dataset_directory
    )
    manifests = tuple(
        archive.manifest(snapshot.symbol, timeframe)
        if settings.market_history_local_candles
        else archive.update(
            snapshot.symbol,
            timeframe,
            tuple(snapshot.ohlcv_by_timeframe[timeframe]),
            source="BINANCE_PUBLIC_REST",
            generated_at=snapshot.created_at,
        )
        for timeframe in snapshot.timeframes
    )
    payload = {
        "symbol": snapshot.symbol,
        "manifests": manifests,
        "wallet_data_included": False,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def _run_research_or_analysis(
    settings: Settings,
    *,
    command: str,
    snapshot: MarketSnapshot,
    virtual_wallet_journal: VirtualWalletJournal | None = None,
    cycle_report: dict[str, object] | None = None,
) -> int:
    workflow_store = (
        JsonlAuditStore(settings.audit_directory / "research_events.jsonl")
        if command == "research-public"
        else None
    )
    if virtual_wallet_journal is not None:
        snapshot = virtual_wallet_journal.analysis_snapshot(snapshot)
    from ai4binance.agents.validation_gate import ValidationGate
    from ai4binance.strategies.engine import StrategyEngine

    service = build_research_application_service(
        orchestrator=EnterpriseOrchestrator(
            minimum_candles=settings.minimum_closed_candles,
            strategy_engine=StrategyEngine(candidate_timeframes=snapshot.timeframes),
            validation_agent=ValidationGate.from_deployment(
                artifact_root=settings.validation_artifact_directory,
                deployment_path=settings.runtime_validation_deployment_path,
                as_of=snapshot.created_at,
            ),
        ),
        audit_store=workflow_store,
        outlook_store=MarketOutlookArtifactStore(
            settings.evidence_artifact_directory / "market-outlook" / "state.json"
        ),
        **(
            {"virtual_portfolio_builder": virtual_wallet_journal.portfolio_builder}
            if virtual_wallet_journal is not None
            else {}
        ),
    )
    research_workflow = service.run(snapshot)
    virtual_wallet_report = (
        virtual_wallet_journal.record_cycle(
            snapshot_id=snapshot.snapshot_id,
            observed_at=snapshot.created_at,
            decision=research_workflow.virtual_runtime_decision,
            request=research_workflow.virtual_runtime_request,
        )
        if virtual_wallet_journal is not None
        else None
    )
    opportunity_radar_started_ns = perf_counter_ns()
    opportunity_radar = build_opportunity_radar_snapshot(
        (snapshot,),
        cycle_id=snapshot.snapshot_id,
        observed_at=snapshot.created_at,
        market=snapshot.market_type.upper(),
    )
    opportunity_radar_duration_ns = perf_counter_ns() - opportunity_radar_started_ns
    opportunity_radar_path = write_opportunity_radar_snapshot(
        opportunity_radar,
        settings.evidence_artifact_directory / "opportunity-radar" / "latest.json",
    )
    state = research_workflow.analysis
    if command == "analyze-public":
        audit_store = JsonlAuditStore(
            settings.audit_directory / "analysis_events.jsonl"
        )
        audit_store.append_verified(
            AuditEvent(
                event_type="MARKET_SNAPSHOT_CREATED",
                timestamp=snapshot.created_at,
                snapshot_id=snapshot.snapshot_id,
                payload={"snapshot": snapshot},
            )
        )
        audit_store.append_verified(
            AuditEvent(
                event_type="ANALYSIS_DECISION_CREATED",
                timestamp=snapshot.created_at,
                snapshot_id=snapshot.snapshot_id,
                payload={
                    "agent_results": state.agent_results,
                    "decision": state.final_decision,
                    "market_outlook": research_workflow.market_outlook,
                },
            )
        )
    candle_counts = {
        timeframe: len(snapshot.ohlcv_by_timeframe[timeframe])
        for timeframe in snapshot.timeframes
    }
    payload = {
        "snapshot_id": snapshot.snapshot_id,
        "symbol": snapshot.symbol,
        "timeframes": snapshot.timeframes,
        "data_quality": snapshot.data_quality,
        "candle_counts": candle_counts,
        "agent_statuses": {
            name: result.status for name, result in state.agent_results.items()
        },
        "candidates": state.candidate_setups,
        "market_outlook": research_workflow.market_outlook,
        "opportunity_radar": opportunity_radar.to_payload(),
        "opportunity_radar_telemetry": {
            "candidate_evaluation_duration_ms": (
                opportunity_radar_duration_ns / 1_000_000
            ),
            "source_snapshot_count": len(opportunity_radar.source_snapshot_ids),
            "candidate_count": opportunity_radar.candidate_count,
        },
        "opportunity_radar_path": str(opportunity_radar_path),
        "decision": state.final_decision,
        "virtual_runtime_decision": virtual_runtime_decision_payload(
            research_workflow.virtual_runtime_decision
        ),
        "virtual_wallets": (
            virtual_wallet_report.get("wallets")
            if virtual_wallet_report is not None
            else None
        ),
        "virtual_wallet_movement_count": (
            virtual_wallet_report.get("movement_count")
            if virtual_wallet_report is not None
            else None
        ),
        "virtual_wallet_report_paths": (
            virtual_wallet_report.get("report_paths")
            if virtual_wallet_report is not None
            else None
        ),
        "research_stages": research_workflow.stages,
        "execution_allowed": research_workflow.execution_allowed,
        "live_eligibility_status": research_workflow.live_eligibility_status,
    }
    if cycle_report is not None:
        risk = state.agent_results.get("risk")
        virtual = research_workflow.virtual_runtime_decision
        cycle_report.update(
            {
                "snapshot_id": snapshot.snapshot_id,
                "symbol": snapshot.symbol,
                "market": snapshot.market_type.upper(),
                "candidate_count": len(state.candidate_setups),
                "candidate_diagnostics": tuple(
                    {
                        "candidate_id": candidate.candidate_id,
                        "setup": candidate.setup_name,
                        "timeframe": candidate.timeframe,
                        "status": candidate.status.value,
                        "blockers": candidate.blockers,
                    }
                    for candidate in state.candidate_setups
                ),
                "risk_approved": risk is not None
                and risk.calculation_metadata.get("approved") is True,
                "virtual_decision_status": virtual.status.value
                if virtual is not None
                else "NO_ACTION",
                "virtual_runtime_evaluated": virtual is not None,
                "virtual_simulation_outcome": (
                    "RUNTIME_DECISION_EVALUATED"
                    if virtual is not None
                    else "PRECONDITIONS_BLOCKED"
                ),
                "virtual_order_ready": virtual is not None
                and virtual.trade_intent is not None,
                "research_blockers": tuple(
                    dict.fromkeys(
                        blocker
                        for stage in research_workflow.stages
                        for blocker in stage.blockers
                    )
                ),
            }
        )
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def _write_second_brain_production_artifact(index: RagIndex) -> Path:
    repository_root = Path.cwd().resolve()
    artifact_directory = repository_root / "runtime" / "artifacts" / "second-brain"
    artifact_directory.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_directory / "index.json"
    index.write(artifact_path)
    return artifact_path


def _rag_prompt(query: str, hits: tuple[RagSearchHit, ...]) -> str:
    return (
        "AI4BINANCE advisory-only opportunity review.\n"
        "Do not authorize execution, do not claim live eligibility.\n"
        f"Question: {query}\n"
        f"Retrieved evidence: {to_primitive(hits)}\n"
        "Return concise research-only opportunities and blockers."
    )

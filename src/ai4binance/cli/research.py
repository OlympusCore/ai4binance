"""Research, validation, RAG and public-market CLI command handlers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import (
    ResearchApplicationService,
    ResearchValidationService,
    WhaleFusionCycle,
    WhaleFusionResearchService,
)
from ai4binance.config import Settings
from ai4binance.data import (
    BinanceVisionIngestor,
    DatasetIntegrityError,
    ParquetOHLCVArchive,
)
from ai4binance.data.revision import DatasetRevisionBuilder
from ai4binance.decision import build_no_trade_signal
from ai4binance.exchange.errors import ExchangeError
from ai4binance.governance import (
    build_enterprise_ai_crew_plan,
    market_outlook_workflow,
    preview_workflow,
)
from ai4binance.outlook import MarketOutlookArtifactStore
from ai4binance.rag import (
    AdvisoryProviderResult,
    LocalRagIndexer,
    OllamaAdvisoryRunner,
    RagEvidenceQualityStatus,
    RagSearchHit,
    render_rag_ui,
    review_rag_evidence_quality,
)
from ai4binance.reporting import to_primitive
from ai4binance.schemas import MarketSnapshot
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.whale_fusion import FusionAuditWriter

from .parser import (
    SnapshotAcquirer,
    normalize_cli_symbol,
    parse_as_of,
    safe_validation_symbol,
)
from .status import build_public_acquisition, fusion_asset


def run_validate_research(settings: Settings, symbol: str | None) -> int:
    try:
        validation_symbol = normalize_cli_symbol(symbol) or settings.validation_symbol
        batch = ResearchValidationService(
            archive=ParquetOHLCVArchive(settings.dataset_directory),
            artifact_directory=settings.validation_artifact_directory,
        ).run(validation_symbol, settings.timeframes)
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
                        result.backtest.metrics if result.backtest is not None else None
                    ),
                    "tuning_report_id": (
                        result.tuning.report_id if result.tuning is not None else None
                    ),
                    "robustness": result.robustness,
                }
                for result in batch.results
            ),
            "execution_allowed": batch.execution_allowed,
            "live_eligibility_status": batch.live_eligibility_status,
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
    hits = index.query(
        resolved_query,
        source_prefixes=("Docs", "Artifacts", "Backtest/validation", "Data/market"),
        authorities=("READ_ONLY", "RESEARCH_ONLY"),
        classifications=("PUBLIC_RESEARCH",),
    )
    evidence_quality = review_rag_evidence_quality(
        query_id=f"second-brain:{resolved_query}",
        hits=hits,
        citations=tuple(hit.source_uri for hit in hits),
        now=datetime.now(UTC),
    )
    advisory = (
        _run_local_advisory(_rag_prompt(resolved_query, hits), hits)
        if use_llm
        and evidence_quality.status
        is RagEvidenceQualityStatus.RESEARCH_ONLY_RAG_EVIDENCE
        else None
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
        "query": resolved_query,
        "hits": hits,
        "evidence_quality": evidence_quality,
        "advisory": advisory,
        "ui_path": str(ui_path) if ui_path is not None else None,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
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
    archive = ParquetOHLCVArchive(settings.dataset_directory)
    sync_results = BinanceVisionIngestor.with_network(archive).sync(
        validation_symbol,
        settings.timeframes,
        as_of=as_of_date,
    )
    revision_builder = DatasetRevisionBuilder(settings.dataset_directory)
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
        return _run_research_or_analysis(settings, command=command, snapshot=snapshot)
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
        orchestrator=EnterpriseOrchestrator(
            minimum_candles=settings.minimum_closed_candles
        ),
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
    archive = ParquetOHLCVArchive(settings.dataset_directory)
    manifests = tuple(
        archive.update(
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
) -> int:
    workflow_store = (
        JsonlAuditStore(settings.audit_directory / "research_events.jsonl")
        if command == "research-public"
        else None
    )
    service = ResearchApplicationService(
        orchestrator=EnterpriseOrchestrator(
            minimum_candles=settings.minimum_closed_candles
        ),
        audit_store=workflow_store,
        outlook_store=MarketOutlookArtifactStore(
            settings.evidence_artifact_directory / "market-outlook" / "state.json"
        ),
    )
    research_workflow = service.run(snapshot)
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
        "decision": state.final_decision,
        "research_stages": research_workflow.stages,
        "execution_allowed": research_workflow.execution_allowed,
        "live_eligibility_status": research_workflow.live_eligibility_status,
    }
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0


def _rag_prompt(query: str, hits: tuple[RagSearchHit, ...]) -> str:
    return (
        "AI4BINANCE advisory-only opportunity review.\n"
        "Do not authorize execution, do not claim live eligibility.\n"
        f"Question: {query}\n"
        f"Retrieved evidence: {to_primitive(hits)}\n"
        "Return concise research-only opportunities and blockers."
    )

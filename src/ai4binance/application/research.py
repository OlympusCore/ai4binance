"""End-to-end research orchestration with explicit fail-closed stage states."""

from dataclasses import dataclass, field, replace
from enum import StrEnum

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application.learning_loop import (
    ControlledLearningLoop,
    LearningLoopResult,
)
from ai4binance.domain import ValidationStatus
from ai4binance.governance import RunContext
from ai4binance.market_context import (
    MarketContextBatch,
    MarketContextRegistry,
    MarketContextRequest,
)
from ai4binance.observability import LocalObserver
from ai4binance.outlook import (
    MarketOutlook,
    MarketOutlookArtifactStore,
    MarketOutlookEngine,
)
from ai4binance.portfolio.wallet import WalletSnapshot, WalletSnapshotService
from ai4binance.schemas import AgentStatus, AnalysisState, MarketSnapshot
from ai4binance.storage import AuditEvent, JsonlAuditStore


class ResearchStageStatus(StrEnum):
    """Observable completion state for one application stage."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class ResearchStage:
    """One deterministic workflow stage with explicit blockers."""

    name: str
    status: ResearchStageStatus
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("research stage name cannot be empty")
        if self.status is ResearchStageStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked research stage requires blockers")
        if self.status is not ResearchStageStatus.BLOCKED and self.blockers:
            raise ValueError("only blocked research stages may contain blockers")


@dataclass(frozen=True, slots=True)
class ResearchWorkflowResult:
    """Snapshot-consistent research result without execution authority."""

    analysis: AnalysisState
    market_outlook: MarketOutlook
    stages: tuple[ResearchStage, ...]
    learning: LearningLoopResult | None = None
    wallet: WalletSnapshot | None = None
    market_context: MarketContextBatch | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("research workflow cannot grant execution authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("research workflow must remain live blocked")


@dataclass(frozen=True, slots=True)
class ResearchApplicationService:
    """Coordinate analysis, governance status and append-only audit persistence."""

    orchestrator: EnterpriseOrchestrator = field(default_factory=EnterpriseOrchestrator)
    outlook_engine: MarketOutlookEngine = field(default_factory=MarketOutlookEngine)
    audit_store: JsonlAuditStore | None = None
    learning_loop: ControlledLearningLoop | None = None
    wallet_service: WalletSnapshotService | None = None
    wallet_capture_enabled: bool = False
    market_context_registry: MarketContextRegistry | None = None
    market_context_provider_ids: tuple[str, ...] = ()
    outlook_store: MarketOutlookArtifactStore | None = None
    observer: LocalObserver | None = None

    def __post_init__(self) -> None:
        if self.wallet_capture_enabled and self.wallet_service is None:
            raise ValueError("wallet capture requires an explicit wallet service")
        if self.market_context_provider_ids and self.market_context_registry is None:
            raise ValueError("market context providers require an explicit registry")

    def run(
        self,
        snapshot: MarketSnapshot,
        *,
        wallet: WalletSnapshot | None = None,
    ) -> ResearchWorkflowResult:
        """Run the safe research path and expose every downstream blocker."""
        if wallet is not None and self.wallet_capture_enabled:
            raise ValueError("wallet override cannot be combined with wallet capture")
        context = RunContext(snapshot.snapshot_id, "research_workflow")
        if self.observer is not None:
            self.observer.emit(
                context,
                "research_workflow_started",
                "RUNNING",
                metadata={
                    "snapshot_id": snapshot.snapshot_id,
                    "symbol": snapshot.symbol,
                },
            )
        captured_wallet = (
            self.wallet_service.capture(snapshot.symbol, snapshot.created_at)
            if self.wallet_capture_enabled and self.wallet_service is not None
            else wallet
        )
        market_context = self._collect_market_context(snapshot)
        analysis_snapshot = self._attach_market_context(
            self._attach_wallet(snapshot, captured_wallet), market_context
        )
        analysis = self.orchestrator.analyze(analysis_snapshot)
        market_outlook = self.outlook_engine.build(analysis)
        learning = (
            self.learning_loop.run(created_at=snapshot.created_at)
            if self.learning_loop is not None
            else None
        )
        workflow = ResearchWorkflowResult(
            analysis=analysis,
            market_outlook=market_outlook,
            stages=self._build_stages(analysis, learning),
            learning=learning,
            wallet=captured_wallet,
            market_context=market_context,
        )
        self._persist(snapshot, workflow)
        if self.observer is not None:
            self.observer.emit(
                context.for_step("research_workflow_completed"),
                "research_workflow_completed",
                "COMPLETED",
                metadata={
                    "snapshot_id": snapshot.snapshot_id,
                    "stage_count": len(workflow.stages),
                    "blockers": tuple(
                        blocker
                        for stage in workflow.stages
                        for blocker in stage.blockers
                    ),
                },
            )
        return workflow

    @staticmethod
    def _build_stages(
        analysis: AnalysisState,
        learning: LearningLoopResult | None = None,
    ) -> tuple[ResearchStage, ...]:
        candidates = analysis.candidate_setups
        risk_result = analysis.agent_results.get("risk")
        strategy_blockers = () if candidates else ("NO_RESEARCH_CANDIDATE",)
        risk_blockers = (
            tuple(risk_result.blockers)
            if risk_result is not None and risk_result.status is not AgentStatus.SUCCESS
            else ("RISK_NOT_EVALUATED",)
            if risk_result is None
            else ()
        )
        promoted = any(
            candidate.promotion_status
            in {ValidationStatus.PAPER_APPROVED, ValidationStatus.LIVE_ELIGIBLE}
            for candidate in candidates
        )
        paper_blockers = (
            ("STRATEGY_NOT_PROMOTED",)
            if not promoted
            else ("PAPER_EXECUTION_REQUIRES_EXPLICIT_ORDER",)
        )
        return (
            ResearchStage("acquisition", ResearchStageStatus.COMPLETED),
            ResearchApplicationService._stage("analysis", tuple(analysis.blockers)),
            ResearchApplicationService._stage("strategy", strategy_blockers),
            ResearchApplicationService._stage("risk", risk_blockers),
            ResearchStage("paper", ResearchStageStatus.BLOCKED, paper_blockers),
            ResearchStage(
                "learning",
                ResearchStageStatus.COMPLETED
                if learning is not None
                else ResearchStageStatus.NOT_RUN,
            ),
        )

    @staticmethod
    def _stage(name: str, blockers: tuple[str, ...]) -> ResearchStage:
        status = (
            ResearchStageStatus.BLOCKED if blockers else ResearchStageStatus.COMPLETED
        )
        return ResearchStage(name=name, status=status, blockers=blockers)

    def _persist(
        self,
        snapshot: MarketSnapshot,
        workflow: ResearchWorkflowResult,
    ) -> None:
        if self.outlook_store is not None:
            self.outlook_store.save(workflow.market_outlook)
        if self.audit_store is None:
            return
        self.audit_store.append_verified(
            AuditEvent(
                event_type="RESEARCH_WORKFLOW_COMPLETED",
                timestamp=snapshot.created_at,
                snapshot_id=snapshot.snapshot_id,
                payload={
                    "snapshot": snapshot,
                    "analysis": workflow.analysis,
                    "market_outlook": workflow.market_outlook,
                    "stages": workflow.stages,
                    "learning": workflow.learning,
                    "wallet": workflow.wallet,
                    "market_context": workflow.market_context,
                    "execution_allowed": workflow.execution_allowed,
                    "live_eligibility_status": workflow.live_eligibility_status,
                },
            )
        )

    @staticmethod
    def _attach_wallet(
        snapshot: MarketSnapshot,
        wallet: WalletSnapshot | None,
    ) -> MarketSnapshot:
        if wallet is None:
            return snapshot
        base_asset = snapshot.symbol.removesuffix("USDT") or snapshot.symbol
        analyzed = wallet.balance(base_asset)
        quote_balances = {
            balance.asset: {
                "free": str(balance.free),
                "locked": str(balance.locked),
            }
            for balance in wallet.balances
            if balance.asset in {"USDT", "USDC"}
        }
        nonzero_balances = {
            balance.asset: {
                "free": str(balance.free),
                "locked": str(balance.locked),
            }
            for balance in wallet.balances
            if balance.free + balance.locked > 0
        }
        return replace(
            snapshot,
            wallet_summary={
                "account_status": wallet.account_status,
                "can_trade": wallet.can_trade,
                "quote_balances": quote_balances,
                "asset_count": len(nonzero_balances),
            },
            inventory_summary={
                "asset": base_asset,
                "quantity": (
                    str(analyzed.free + analyzed.locked)
                    if analyzed is not None
                    else "0"
                ),
                "balances": nonzero_balances,
                "open_order_count": wallet.open_order_count,
            },
        )

    def _collect_market_context(
        self,
        snapshot: MarketSnapshot,
    ) -> MarketContextBatch | None:
        if self.market_context_registry is None or not self.market_context_provider_ids:
            return None
        return self.market_context_registry.collect(
            MarketContextRequest(
                snapshot_id=snapshot.snapshot_id,
                symbol=snapshot.symbol,
                requested_at=snapshot.created_at,
            ),
            self.market_context_provider_ids,
        )

    @staticmethod
    def _attach_market_context(
        snapshot: MarketSnapshot,
        batch: MarketContextBatch | None,
    ) -> MarketSnapshot:
        if batch is None:
            return snapshot
        existing = snapshot.news_snapshot.get("high_impact_events", ())
        incoming = batch.as_news_snapshot()["high_impact_events"]
        existing_events = existing if isinstance(existing, tuple) else ()
        incoming_events = incoming if isinstance(incoming, tuple) else ()
        return replace(
            snapshot,
            news_snapshot={
                **dict(snapshot.news_snapshot),
                **dict(batch.as_news_snapshot()),
                "high_impact_events": (*existing_events, *incoming_events),
            },
        )

"""End-to-end research orchestration with explicit fail-closed stage states."""
# ruff: noqa: E501
# ruff: noqa: ANN401

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast

from ai4binance.application.context.memory import GovernedMemoryCycleBridge
from ai4binance.application.learning_loop import (
    ControlledLearningLoop,
    LearningEvidenceProvider,
    LearningLoopResult,
)
from ai4binance.application.orchestration.canonical_cycle import (
    CanonicalCycleEnvelope,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
)
from ai4binance.application.services.virtual_runtime import (
    VirtualMarketRuntime,
    VirtualPortfolioState,
    VirtualPositionSide,
    VirtualRuntimeRequest,
    run_virtual_market_cycle,
)
from ai4binance.application.virtual_runtime_eligibility import (
    evaluate_virtual_simulation_eligibility,
)
from ai4binance.core.contracts.memory import CompiledCycleContext
from ai4binance.core.contracts.virtual_governance import (
    DGE_APPROVED_PAPER_ONLY,
    DGE_DATA_UNAVAILABLE,
    DGE_EVALUATION_FAILED,
    DGE_EVALUATION_UNAVAILABLE,
    DGE_SIMULATION_NOT_APPROVED,
    VirtualGovernanceResult,
)


class StatusValueLike(Protocol):
    value: str


class DecisionActionLike(Protocol):
    value: str


class FinalDecisionLike(Protocol):
    action: DecisionActionLike


class CandidateLike(Protocol):
    candidate_id: str
    snapshot_id: str
    symbol: str
    timeframe: str
    action: DecisionActionLike
    setup_name: str
    score: float
    confidence: float
    entry_price: object
    invalidation_level: object
    stop_loss: object
    take_profit_levels: tuple[object, ...]
    trailing_stop: object
    risk_reward: object
    market_type: str
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]


class AgentResultLike(Protocol):
    status: StatusValueLike
    blockers: tuple[str, ...]


class AnalysisStateLike(Protocol):
    snapshot_id: str
    blockers: tuple[str, ...]
    agent_results: Mapping[str, AgentResultLike]
    candidate_setups: Sequence[CandidateLike]
    final_decision: FinalDecisionLike | None
    market_snapshot: object


class VirtualGovernanceEvaluatorLike(Protocol):
    def evaluate(
        self,
        *,
        snapshot: object,
        analysis: object,
        candidate: object,
        portfolio: object,
        market: str,
        quantity: Decimal,
        risk_approved: bool,
        portfolio_verified: bool,
    ) -> VirtualGovernanceResult: ...


class BalanceLike(Protocol):
    asset: str
    free: object
    locked: object


class WalletSnapshotLike(Protocol):
    account_status: str
    can_trade: bool
    balances: Sequence[BalanceLike]
    open_order_count: int

    def balance(self, asset: str) -> BalanceLike | None: ...


class MarketContextEventLike(Protocol):
    retrieved_at: object


class MarketContextBatchLike(Protocol):
    events: Sequence[MarketContextEventLike]
    blockers: tuple[str, ...]

    def as_news_snapshot(self) -> Mapping[str, object]: ...


class MarketSnapshotLike(Protocol):
    snapshot_id: str
    symbol: str
    created_at: object
    timeframes: tuple[str, ...]
    wallet_summary: Mapping[str, object]
    inventory_summary: Mapping[str, object]
    news_snapshot: Mapping[str, object]
    sentiment_snapshot: Mapping[str, object]
    derivatives_snapshot: Mapping[str, object]
    market_metadata: Mapping[str, object]


class MarketOutlookLike(Protocol):
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class _RiskAssessmentSnapshot:
    candidate_id: str
    approved: bool
    quantity: Decimal


class OrchestratorLike(Protocol):
    def analyze(self, snapshot: MarketSnapshotLike) -> AnalysisStateLike: ...


class OutlookEngineLike(Protocol):
    def build(self, analysis: AnalysisStateLike) -> MarketOutlookLike: ...


class AuditStoreLike(Protocol):
    def append_verified(self, event: object) -> None: ...


class WalletSnapshotServiceLike(Protocol):
    def capture(self, symbol: str, created_at: object) -> WalletSnapshotLike: ...


class MarketContextRegistryLike(Protocol):
    def collect(
        self,
        request: object,
        provider_ids: tuple[str, ...],
    ) -> MarketContextBatchLike: ...


class OutlookStoreLike(Protocol):
    state_path: Path

    def save(self, market_outlook: MarketOutlookLike) -> None: ...


class ObserverContextLike(Protocol):
    def for_step(self, step_id: str) -> object: ...


class ObserverLike(Protocol):
    def emit(
        self,
        context: object,
        event_type: str,
        status: str,
        *,
        metadata: Mapping[str, object],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class _VirtualLearningPerformanceSnapshot:
    """Minimal report-only virtual learning bridge for improvement candidates."""

    auto_learn_consumable: bool
    improvement_candidates: tuple[object, ...]
    root_cause_tags: tuple[str, ...] = ()


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

    analysis: Any
    market_outlook: Any
    stages: tuple[ResearchStage, ...]
    virtual_runtime_decision: Any | None = None
    virtual_runtime_request: Any | None = None
    learning: LearningLoopResult | None = None
    wallet: Any | None = None
    market_context: Any | None = None
    canonical_cycle: CanonicalCycleEnvelope | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    compiled_cycle_context: CompiledCycleContext | None = None
    memory_candidate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("research workflow cannot grant execution authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("research workflow must remain live blocked")


@dataclass(frozen=True, slots=True)
class ResearchApplicationService:
    """Coordinate analysis, governance status and append-only audit persistence."""

    orchestrator: Any
    outlook_engine: Any
    primitive_converter: Callable[[object], object]
    audit_event_builder: Callable[..., object] | None = None
    market_context_request_builder: Callable[..., object] | None = None
    run_context_builder: Callable[[str, str], object] | None = None
    audit_store: Any | None = None
    learning_loop: ControlledLearningLoop | None = None
    wallet_service: Any | None = None
    wallet_capture_enabled: bool = False
    market_context_registry: Any | None = None
    market_context_provider_ids: tuple[str, ...] = ()
    outlook_store: Any | None = None
    observer: Any | None = None
    learning_evidence_provider: LearningEvidenceProvider | None = None
    virtual_market_runtime: Any | None = None
    virtual_portfolio_builder: Callable[[object, object], Any] | None = None
    virtual_governance_evaluator: VirtualGovernanceEvaluatorLike | None = None
    memory_bridge: GovernedMemoryCycleBridge | None = None

    def __post_init__(self) -> None:
        if self.wallet_capture_enabled and self.wallet_service is None:
            raise ValueError("wallet capture requires an explicit wallet service")
        if self.market_context_provider_ids and self.market_context_registry is None:
            raise ValueError("market context providers require an explicit registry")
        if (
            self.market_context_registry is not None
            and self.market_context_request_builder is None
        ):
            raise ValueError("market context registry requires a request builder")
        if self.audit_store is not None and self.audit_event_builder is None:
            raise ValueError("audit persistence requires an event builder")
        if self.observer is not None and self.run_context_builder is None:
            raise ValueError("observer requires a run context builder")
        if self.virtual_market_runtime is None:
            object.__setattr__(
                self,
                "virtual_market_runtime",
                cast(Any, VirtualMarketRuntime)(),
            )
        if (
            self.virtual_market_runtime is not None
            and self.virtual_portfolio_builder is None
        ):
            object.__setattr__(
                self,
                "virtual_portfolio_builder",
                self._default_virtual_portfolio_builder,
            )

    def run(
        self,
        snapshot: Any,
        *,
        wallet: Any | None = None,
    ) -> ResearchWorkflowResult:
        """Run the safe research path and expose every downstream blocker."""
        if wallet is not None and self.wallet_capture_enabled:
            raise ValueError("wallet override cannot be combined with wallet capture")
        context = (
            self.run_context_builder(snapshot.snapshot_id, "research_workflow")
            if self.observer is not None and self.run_context_builder is not None
            else None
        )
        if self.observer is not None and context is not None:
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
            self._attach_wallet(snapshot, captured_wallet),
            market_context,
        )
        compiled_context = (
            self.memory_bridge.compile(analysis_snapshot)
            if self.memory_bridge is not None
            else None
        )
        analysis = (
            self.orchestrator.analyze(
                analysis_snapshot, compiled_cycle_context=compiled_context
            )
            if compiled_context is not None
            else self.orchestrator.analyze(analysis_snapshot)
        )
        market_outlook = self.outlook_engine.build(analysis)
        (
            virtual_runtime_request,
            virtual_runtime_decision,
        ) = self._evaluate_virtual_runtime(snapshot, analysis)
        learning_artifacts = (
            self.learning_evidence_provider.load(snapshot)
            if self.learning_evidence_provider is not None
            else {}
        )
        learning_artifacts = self._merge_virtual_learning_artifacts(
            learning_artifacts,
            virtual_runtime_decision=virtual_runtime_decision,
        )
        learning = (
            self.learning_loop.run(
                created_at=snapshot.created_at,
                **learning_artifacts,
            )
            if self.learning_loop is not None
            else None
        )
        workflow = ResearchWorkflowResult(
            analysis=analysis,
            market_outlook=market_outlook,
            stages=self._build_stages(
                analysis,
                learning,
                virtual_runtime_decision=virtual_runtime_decision,
            ),
            virtual_runtime_decision=virtual_runtime_decision,
            virtual_runtime_request=virtual_runtime_request,
            learning=learning,
            wallet=captured_wallet,
            market_context=market_context,
            compiled_cycle_context=compiled_context,
            memory_candidate_ids=(
                self.memory_bridge.stage(learning.summary, analysis_snapshot)
                if self.memory_bridge is not None and learning is not None
                else ()
            ),
        )
        workflow = replace(
            workflow,
            canonical_cycle=self._build_canonical_cycle(analysis_snapshot, workflow),
        )
        self._persist(analysis_snapshot, workflow)
        if self.observer is not None and context is not None:
            completion_context = cast(Any, context).for_step(
                "research_workflow_completed"
            )
            self.observer.emit(
                completion_context,
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
        analysis: Any,
        learning: LearningLoopResult | None = None,
        *,
        virtual_runtime_decision: Any | None = None,
    ) -> tuple[ResearchStage, ...]:
        candidates = analysis.candidate_setups
        risk_result = analysis.agent_results.get("risk")
        strategy_blockers = () if candidates else ("NO_RESEARCH_CANDIDATE",)
        risk_blockers = (
            tuple(risk_result.blockers)
            if risk_result is not None and risk_result.status.value != "SUCCESS"
            else ("RISK_NOT_EVALUATED",)
            if risk_result is None
            else ()
        )
        validation_blockers = ("NO_VIRTUAL_SETUP_CANDIDATE",) if not candidates else ()
        virtual_eligibility = evaluate_virtual_simulation_eligibility(
            execution_surface=_virtual_market_execution_surface(),
            analysis_blockers=tuple(analysis.blockers),
            candidate_blockers=strategy_blockers,
            risk_blockers=risk_blockers,
            validation_blockers=validation_blockers,
            dge_blockers=(
                ()
                if virtual_runtime_decision is not None
                else (DGE_SIMULATION_NOT_APPROVED,)
            ),
        )
        virtual_market_blockers = (
            virtual_runtime_decision.eligibility.blockers
            if virtual_runtime_decision is not None
            else virtual_eligibility.blockers
        )
        return (
            ResearchStage("acquisition", ResearchStageStatus.COMPLETED),
            ResearchApplicationService._stage("analysis", tuple(analysis.blockers)),
            ResearchApplicationService._stage("strategy", strategy_blockers),
            ResearchApplicationService._stage("risk", risk_blockers),
            ResearchApplicationService._stage(
                "virtual_market_execution",
                virtual_market_blockers,
            ),
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
        snapshot: Any,
        workflow: ResearchWorkflowResult,
    ) -> None:
        if self.outlook_store is not None:
            self.outlook_store.save(workflow.market_outlook)
        if self.audit_store is None or self.audit_event_builder is None:
            return
        append = getattr(
            self.audit_store,
            "append_verified_idempotent",
            self.audit_store.append_verified,
        )
        append(
            self.audit_event_builder(
                event_type="RESEARCH_WORKFLOW_COMPLETED",
                timestamp=snapshot.created_at,
                snapshot_id=snapshot.snapshot_id,
                payload=self._compact_audit_payload(snapshot, workflow),
            )
        )

    def _compact_audit_payload(
        self,
        snapshot: Any,
        workflow: ResearchWorkflowResult,
    ) -> dict[str, object]:
        status_counts = Counter(
            result.status.value for result in workflow.analysis.agent_results.values()
        )
        final_decision = workflow.analysis.final_decision
        return {
            "snapshot_ref": {
                "snapshot_id": snapshot.snapshot_id,
                "symbol": snapshot.symbol,
                "created_at": snapshot.created_at,
                "timeframes": snapshot.timeframes,
                "sha256": _canonical_sha256(self.primitive_converter, snapshot),
            },
            "analysis_ref": {
                "snapshot_id": workflow.analysis.snapshot_id,
                "sha256": _canonical_sha256(
                    self.primitive_converter, workflow.analysis
                ),
                "agent_result_count": len(workflow.analysis.agent_results),
                "agent_status_counts": dict(sorted(status_counts.items())),
                "candidate_setup_count": len(workflow.analysis.candidate_setups),
                "final_action": (
                    final_decision.action.value
                    if final_decision is not None
                    else "NO_TRADE"
                ),
                "blockers": workflow.analysis.blockers,
            },
            "market_outlook_ref": {
                "snapshot_id": workflow.market_outlook.snapshot_id,
                "sha256": _canonical_sha256(
                    self.primitive_converter,
                    workflow.market_outlook,
                ),
                "artifact_path": (
                    str(self.outlook_store.state_path)
                    if self.outlook_store is not None
                    else None
                ),
            },
            "stages": workflow.stages,
            "learning_present": workflow.learning is not None,
            "memory_candidate_ids": workflow.memory_candidate_ids,
            "compiled_cycle_context": workflow.compiled_cycle_context,
            "wallet_context_attached": workflow.wallet is not None,
            "market_context_attached": workflow.market_context is not None,
            "execution_allowed": workflow.execution_allowed,
            "live_eligibility_status": workflow.live_eligibility_status,
            "virtual_runtime_ref": (
                {
                    "status": workflow.virtual_runtime_decision.status.value,
                    "eligibility_status": (
                        workflow.virtual_runtime_decision.eligibility.status.value
                    ),
                    "blockers": workflow.virtual_runtime_decision.eligibility.blockers,
                    "audit_refs": workflow.virtual_runtime_decision.audit_refs,
                    "trade_intent_present": (
                        workflow.virtual_runtime_decision.trade_intent is not None
                    ),
                }
                if workflow.virtual_runtime_decision is not None
                else None
            ),
            "canonical_cycle": (
                workflow.canonical_cycle.to_payload()
                if workflow.canonical_cycle is not None
                else None
            ),
        }

    def _build_canonical_cycle(
        self,
        snapshot: Any,
        workflow: ResearchWorkflowResult,
    ) -> CanonicalCycleEnvelope:
        cycle_id = f"research:{snapshot.snapshot_id}"
        snapshot_id = str(snapshot.snapshot_id)
        analysis = workflow.analysis
        final_decision = analysis.final_decision
        risk_result = analysis.agent_results.get("risk")
        observations = tuple(
            self._cycle_artifact_ref(
                artifact_id=f"observation:{agent_id}:{snapshot_id}",
                artifact_kind=CycleArtifactKind.OBSERVATION,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload={
                    "agent_id": agent_id,
                    "status": str(
                        getattr(getattr(result, "status", None), "value", "UNKNOWN")
                    ),
                    "blockers": tuple(getattr(result, "blockers", ())),
                    "calculation_metadata": (
                        dict(getattr(result, "calculation_metadata", {}))
                        if isinstance(
                            getattr(result, "calculation_metadata", {}), Mapping
                        )
                        else {}
                    ),
                },
            )
            for agent_id, result in sorted(analysis.agent_results.items())
        )
        if not observations:
            observations = (
                self._cycle_artifact_ref(
                    artifact_id=f"observation:analysis:{snapshot_id}",
                    artifact_kind=CycleArtifactKind.OBSERVATION,
                    cycle_id=cycle_id,
                    snapshot_id=snapshot_id,
                    payload={
                        "blockers": tuple(analysis.blockers),
                        "candidate_count": len(analysis.candidate_setups),
                    },
                ),
            )
        governance_status = self._canonical_governance_status(workflow)
        stage_blockers = tuple(
            dict.fromkeys(
                blocker for stage in workflow.stages for blocker in stage.blockers
            )
        )
        request = workflow.virtual_runtime_request
        runtime_decision = workflow.virtual_runtime_decision
        governance_blockers = tuple(
            dict.fromkeys(
                (
                    *tuple(getattr(request, "dge_blockers", ())),
                    *tuple(
                        getattr(
                            getattr(runtime_decision, "eligibility", None),
                            "blockers",
                            (),
                        )
                    ),
                )
                if request is not None or runtime_decision is not None
                else stage_blockers
            )
        )
        trade_intent = (
            workflow.virtual_runtime_decision.trade_intent
            if workflow.virtual_runtime_decision is not None
            else None
        )
        execution_plan = (
            self._cycle_artifact_ref(
                artifact_id=f"plan:virtual:{snapshot_id}",
                artifact_kind=CycleArtifactKind.VIRTUAL_SIMULATION_PLAN,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload={
                    "intent_id": str(
                        getattr(
                            trade_intent,
                            "intent_id",
                            f"virtual:{snapshot_id}",
                        )
                    ),
                    "decision_id": str(
                        getattr(trade_intent, "decision_id", "UNKNOWN_DECISION")
                    ),
                    "snapshot_id": snapshot_id,
                },
            )
            if governance_status is CycleGovernanceStatus.APPROVED_PAPER_ONLY
            and trade_intent is not None
            else None
        )
        audit_payload = {
            "snapshot_id": snapshot_id,
            "governance_status": governance_status.value,
            "stages": tuple(
                {
                    "name": stage.name,
                    "status": stage.status.value,
                    "blockers": stage.blockers,
                }
                for stage in workflow.stages
            ),
            "blockers": stage_blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        return CanonicalCycleEnvelope(
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            created_at=snapshot.created_at.astimezone(UTC),
            execution_surface=CycleExecutionSurface.VIRTUAL_MARKET,
            governance_status=governance_status,
            canonical_snapshot=self._cycle_artifact_ref(
                artifact_id=f"snapshot:{snapshot_id}",
                artifact_kind=CycleArtifactKind.CANONICAL_SNAPSHOT,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload=snapshot,
            ),
            shared_state=self._cycle_artifact_ref(
                artifact_id=f"state:{snapshot_id}",
                artifact_kind=CycleArtifactKind.SHARED_STATE,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload={
                    "snapshot_id": snapshot_id,
                    "analysis_snapshot_id": str(analysis.snapshot_id),
                    "compiled_cycle_context": workflow.compiled_cycle_context,
                    "analysis_blockers": tuple(analysis.blockers),
                    "candidate_ids": tuple(
                        str(getattr(candidate, "candidate_id", "UNKNOWN_CANDIDATE"))
                        for candidate in analysis.candidate_setups
                    ),
                },
            ),
            observations=observations,
            decision=self._cycle_artifact_ref(
                artifact_id=f"decision:{snapshot_id}",
                artifact_kind=CycleArtifactKind.DECISION,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload={
                    "action": str(
                        getattr(
                            getattr(final_decision, "action", None),
                            "value",
                            "NO_TRADE",
                        )
                    ),
                    "reason_summary": str(
                        getattr(final_decision, "reason_summary", "NO_TRADE")
                    ),
                    "blockers": tuple(analysis.blockers),
                },
            ),
            risk_assessment=self._cycle_artifact_ref(
                artifact_id=f"risk:{snapshot_id}",
                artifact_kind=CycleArtifactKind.RISK_ASSESSMENT,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload={
                    "status": str(
                        getattr(
                            getattr(risk_result, "status", None),
                            "value",
                            "NOT_EVALUATED",
                        )
                    ),
                    "blockers": tuple(
                        getattr(risk_result, "blockers", ("RISK_NOT_EVALUATED",))
                    ),
                    "calculation_metadata": (
                        dict(getattr(risk_result, "calculation_metadata", {}))
                        if isinstance(
                            getattr(risk_result, "calculation_metadata", {}), Mapping
                        )
                        else {}
                    ),
                },
            ),
            governance_result=self._cycle_artifact_ref(
                artifact_id=f"governance:{snapshot_id}",
                artifact_kind=CycleArtifactKind.GOVERNANCE_RESULT,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload={
                    "status": governance_status.value,
                    "runtime_status": str(
                        getattr(
                            getattr(
                                workflow.virtual_runtime_decision,
                                "status",
                                None,
                            ),
                            "value",
                            "NO_ACTION",
                        )
                    ),
                    "blockers": governance_blockers,
                    "audit_refs": tuple(
                        getattr(workflow.virtual_runtime_decision, "audit_refs", ())
                    ),
                },
            ),
            execution_plan=execution_plan,
            audit_trail=self._cycle_artifact_ref(
                artifact_id=f"audit:{snapshot_id}",
                artifact_kind=CycleArtifactKind.AUDIT_TRAIL,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                payload=audit_payload,
            ),
            blockers=governance_blockers,
        )

    def _cycle_artifact_ref(
        self,
        *,
        artifact_id: str,
        artifact_kind: CycleArtifactKind,
        cycle_id: str,
        snapshot_id: str,
        payload: object,
    ) -> CycleArtifactRef:
        return CycleArtifactRef(
            artifact_id=artifact_id,
            artifact_kind=artifact_kind,
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            payload_sha256=_canonical_sha256(self.primitive_converter, payload),
        )

    @staticmethod
    def _canonical_governance_status(
        workflow: ResearchWorkflowResult,
    ) -> CycleGovernanceStatus:
        request = workflow.virtual_runtime_request
        status = str(getattr(request, "dge_decision", "NO_TRADE"))
        if status == DGE_APPROVED_PAPER_ONLY:
            return CycleGovernanceStatus.APPROVED_PAPER_ONLY
        if status == DGE_DATA_UNAVAILABLE:
            return CycleGovernanceStatus.DATA_UNAVAILABLE
        return CycleGovernanceStatus.NO_TRADE

    @staticmethod
    def _merge_virtual_learning_artifacts(
        learning_artifacts: Mapping[str, object],
        *,
        virtual_runtime_decision: Any | None,
    ) -> dict[str, object]:
        merged = dict(learning_artifacts)
        virtual_snapshot = (
            ResearchApplicationService._virtual_learning_performance_snapshot(
                virtual_runtime_decision
            )
        )
        if virtual_snapshot is None:
            return merged
        existing = merged.get("performance_snapshots", ())
        if not isinstance(existing, tuple):
            raise ValueError("performance_snapshots learning evidence must be a tuple")
        merged["performance_snapshots"] = (*existing, virtual_snapshot)
        return merged

    @staticmethod
    def _virtual_learning_performance_snapshot(
        virtual_runtime_decision: Any | None,
    ) -> _VirtualLearningPerformanceSnapshot | None:
        if virtual_runtime_decision is None:
            return None
        halt_review = virtual_runtime_decision.halt_review
        if halt_review is None or not halt_review.improvement_candidates:
            return None
        return _VirtualLearningPerformanceSnapshot(
            auto_learn_consumable=True,
            improvement_candidates=halt_review.improvement_candidates,
            root_cause_tags=halt_review.root_cause_tags,
        )

    def _evaluate_virtual_runtime(
        self,
        snapshot: Any,
        analysis: Any,
    ) -> tuple[Any | None, Any | None]:
        if self.virtual_market_runtime is None:
            return None, None
        candidates = analysis.candidate_setups
        if not candidates:
            return None, None
        risk_assessment = self._risk_assessment(analysis)
        if risk_assessment is None or not risk_assessment.approved:
            return None, None
        candidate = self._candidate_for_virtual_runtime(
            candidates,
            risk_assessment.candidate_id,
        )
        if candidate is None:
            return None, None
        market = self._candidate_market(candidate)
        if market is None:
            return None, None
        portfolio_builder = self.virtual_portfolio_builder
        if portfolio_builder is None:
            portfolio_builder = self._default_virtual_portfolio_builder
        portfolio = portfolio_builder(snapshot, candidate)
        (
            dge_decision_id,
            dge_status,
            dge_blockers,
            dge_simulation_allowed,
        ) = self._evaluate_virtual_governance(
            snapshot=getattr(analysis, "market_snapshot", snapshot),
            analysis=analysis,
            candidate=candidate,
            portfolio=portfolio,
            market=market,
            risk_assessment=risk_assessment,
        )
        execution_inputs, execution_blockers = self._virtual_execution_inputs(
            snapshot,
            candidate=candidate,
            market=market,
        )
        request = cast(Any, VirtualRuntimeRequest)(
            snapshot_id=snapshot.snapshot_id,
            decision_id=dge_decision_id,
            candidate_id=candidate.candidate_id,
            symbol=candidate.symbol,
            market=market,
            action=candidate.action,
            quantity=risk_assessment.quantity,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit_levels=candidate.take_profit_levels,
            portfolio=portfolio,
            strategy_id=candidate.setup_name,
            timeframe=candidate.timeframe,
            analysis_blockers=tuple(analysis.blockers),
            candidate_blockers=tuple(candidate.blockers),
            risk_blockers=self._risk_blockers(analysis),
            validation_blockers=execution_blockers,
            dge_blockers=dge_blockers,
            dge_decision=dge_status,
            dge_simulation_allowed=dge_simulation_allowed,
            **execution_inputs,
        )
        decision = run_virtual_market_cycle(
            request,
            runtime=self.virtual_market_runtime,
        ).decision
        return request, decision

    @staticmethod
    def _candidate_candle_volume(
        snapshot: object,
        candidate: CandidateLike,
    ) -> Decimal | None:
        candles_by_timeframe = getattr(snapshot, "ohlcv_by_timeframe", {})
        if not isinstance(candles_by_timeframe, Mapping):
            return None
        candles = candles_by_timeframe.get(candidate.timeframe, ())
        if not isinstance(candles, Sequence) or not candles:
            return None
        volume = getattr(candles[-1], "volume", None)
        return ResearchApplicationService._bounded_decimal(
            volume,
            minimum=Decimal("0"),
            minimum_inclusive=True,
        )

    @staticmethod
    def _virtual_execution_inputs(
        snapshot: object,
        *,
        candidate: CandidateLike,
        market: str,
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        metadata = getattr(snapshot, "market_metadata", {})
        raw_context = (
            metadata.get("historical_virtual_execution")
            if isinstance(metadata, Mapping)
            else None
        )
        if raw_context is None:
            return ResearchApplicationService._futures_inputs_without_context(
                snapshot,
                candidate=candidate,
                market=market,
            )
        if not isinstance(raw_context, Mapping):
            return {}, ("VIRTUAL_EXECUTION_CONTEXT_INVALID",)
        observed_at = getattr(snapshot, "created_at", None)
        expected = {
            "context_kind": "HISTORICAL_REPLAY_EXECUTION_V1",
            "market": market,
            "symbol": str(getattr(snapshot, "symbol", "")).strip().upper(),
            "observed_at": (
                observed_at.isoformat().replace("+00:00", "Z")
                if isinstance(observed_at, datetime)
                else None
            ),
        }
        if any(raw_context.get(key) != value for key, value in expected.items()):
            return {}, ("VIRTUAL_EXECUTION_CONTEXT_IDENTITY_MISMATCH",)
        decimal_fields = {
            name: ResearchApplicationService._bounded_decimal(
                raw_context.get(name),
                minimum=minimum,
                maximum=maximum,
                minimum_inclusive=minimum_inclusive,
            )
            for name, minimum, maximum, minimum_inclusive in (
                ("fee_ratio", Decimal("0"), Decimal("0.01"), True),
                ("slippage_ratio", Decimal("0"), Decimal("0.02"), True),
                ("half_spread_ratio", Decimal("0"), Decimal("0.02"), True),
                ("tick_size", Decimal("0"), None, False),
                ("step_size", Decimal("0"), None, False),
                ("minimum_notional", Decimal("0"), None, False),
            )
        }
        if any(value is None for value in decimal_fields.values()):
            return {}, ("VIRTUAL_EXECUTION_CONTEXT_INVALID",)
        inputs: dict[str, object] = cast(dict[str, object], decimal_fields)
        candle_volume = ResearchApplicationService._candidate_candle_volume(
            snapshot,
            candidate,
        )
        if candle_volume is not None:
            inputs["candle_volume"] = candle_volume
        if market == "SPOT":
            return inputs, ()
        futures_inputs, blockers = ResearchApplicationService._futures_inputs(
            raw_context,
            candidate=candidate,
        )
        if blockers:
            return inputs, blockers
        inputs.update(futures_inputs)
        return inputs, ()

    @staticmethod
    def _futures_inputs_without_context(
        snapshot: object,
        *,
        candidate: CandidateLike,
        market: str,
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        if market != "USD_M_FUTURES":
            return {}, ()
        raw_context = getattr(snapshot, "derivatives_snapshot", {})
        if not isinstance(raw_context, Mapping):
            return {}, ("FUTURES_EXECUTION_CONTEXT_INVALID",)
        futures_inputs, blockers = ResearchApplicationService._futures_inputs(
            raw_context,
            candidate=candidate,
        )
        return futures_inputs, blockers

    @staticmethod
    def _futures_inputs(
        raw_context: Mapping[str, object],
        *,
        candidate: CandidateLike,
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        action = str(getattr(getattr(candidate, "action", None), "value", ""))
        position_side = (
            VirtualPositionSide.LONG
            if action == "BUY"
            else VirtualPositionSide.SHORT
            if action == "SELL"
            else None
        )
        mark_price = ResearchApplicationService._bounded_decimal(
            raw_context.get("mark_price"), minimum=Decimal("0")
        )
        funding_rate = ResearchApplicationService._bounded_decimal(
            raw_context.get("funding_rate"), minimum=None
        )
        isolated_margin = ResearchApplicationService._bounded_decimal(
            raw_context.get("isolated_margin_usdt"), minimum=Decimal("0")
        )
        maintenance_ratio = ResearchApplicationService._bounded_decimal(
            raw_context.get("maintenance_margin_ratio"),
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        liquidation_fee_ratio = ResearchApplicationService._bounded_decimal(
            raw_context.get("liquidation_fee_ratio", "0.005"),
            minimum=Decimal("0"),
            maximum=Decimal("0.02"),
            minimum_inclusive=True,
        )
        leverage = raw_context.get("leverage")
        funding_payment_due = raw_context.get("funding_payment_due", True)
        if (
            position_side is None
            or mark_price is None
            or funding_rate is None
            or isolated_margin is None
            or maintenance_ratio is None
            or maintenance_ratio >= Decimal("1")
            or liquidation_fee_ratio is None
            or isinstance(leverage, bool)
            or not isinstance(leverage, int)
            or not 1 <= leverage <= 125
            or not isinstance(funding_payment_due, bool)
        ):
            return {}, ("FUTURES_EXECUTION_CONTEXT_INVALID",)
        return (
            {
                "position_side": position_side,
                "mark_price": mark_price,
                "funding_rate": funding_rate,
                "funding_payment_due": funding_payment_due,
                "leverage": leverage,
                "isolated_margin_usdt": isolated_margin,
                "maintenance_margin_ratio": maintenance_ratio,
                "liquidation_fee_ratio": liquidation_fee_ratio,
            },
            (),
        )

    @staticmethod
    def _bounded_decimal(
        value: object,
        *,
        minimum: Decimal | None,
        maximum: Decimal | None = None,
        minimum_inclusive: bool = False,
    ) -> Decimal | None:
        try:
            parsed = Decimal(str(value))
        except (ArithmeticError, ValueError, TypeError):
            return None
        if not parsed.is_finite():
            return None
        if minimum is not None and (
            parsed < minimum if minimum_inclusive else parsed <= minimum
        ):
            return None
        if maximum is not None and parsed > maximum:
            return None
        return parsed

    def _evaluate_virtual_governance(
        self,
        *,
        snapshot: object,
        analysis: object,
        candidate: CandidateLike,
        portfolio: object,
        market: str,
        risk_assessment: _RiskAssessmentSnapshot,
    ) -> tuple[str, str, tuple[str, ...], bool]:
        fallback_id = (
            f"virtual-dge:{getattr(snapshot, 'snapshot_id', 'unknown')}:"
            f"{getattr(candidate, 'candidate_id', 'unknown')}"
        )
        evaluator = self.virtual_governance_evaluator
        if evaluator is None:
            return (
                fallback_id,
                DGE_DATA_UNAVAILABLE,
                (DGE_EVALUATION_UNAVAILABLE,),
                False,
            )
        try:
            result = evaluator.evaluate(
                snapshot=snapshot,
                analysis=analysis,
                candidate=candidate,
                portfolio=portfolio,
                market=market,
                quantity=risk_assessment.quantity,
                risk_approved=risk_assessment.approved,
                portfolio_verified=isinstance(portfolio, VirtualPortfolioState),
            )
            if not isinstance(result, VirtualGovernanceResult):
                raise TypeError(
                    "virtual governance evaluator must return VirtualGovernanceResult"
                )
        except (
            ArithmeticError,
            AttributeError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return (
                fallback_id,
                DGE_DATA_UNAVAILABLE,
                (DGE_EVALUATION_FAILED,),
                False,
            )
        return (
            result.decision_id,
            result.status,
            result.blockers,
            result.simulation_allowed,
        )

    @staticmethod
    def _risk_blockers(analysis: Any) -> tuple[str, ...]:
        risk_result = analysis.agent_results.get("risk")
        if risk_result is None:
            return ("RISK_NOT_EVALUATED",)
        if risk_result.status.value != "SUCCESS":
            return tuple(risk_result.blockers)
        return ()

    @staticmethod
    def _risk_assessment(analysis: Any) -> _RiskAssessmentSnapshot | None:
        risk_result = analysis.agent_results.get("risk")
        if risk_result is None:
            return None
        if getattr(risk_result, "agent_name", "risk") != "risk":
            return None
        metadata = getattr(risk_result, "calculation_metadata", {})
        if not isinstance(metadata, Mapping):
            return None
        candidate_id = metadata.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            return None
        size_usdt = metadata.get("size_usdt")
        quantity = metadata.get("quantity")
        risk_amount_usdt = metadata.get("risk_amount_usdt")
        if any(value is None for value in (size_usdt, quantity, risk_amount_usdt)):
            return None
        if not isinstance(getattr(risk_result, "blockers", ()), tuple):
            return None
        approved = metadata.get("approved") is True
        try:
            return _RiskAssessmentSnapshot(
                candidate_id=candidate_id,
                approved=approved,
                quantity=Decimal(str(quantity)),
            )
        except (ArithmeticError, ValueError, TypeError):
            return None

    @staticmethod
    def _candidate_for_virtual_runtime(
        candidates: Sequence[CandidateLike],
        candidate_id: str,
    ) -> CandidateLike | None:
        for candidate in candidates:
            if getattr(candidate, "candidate_id", "") == candidate_id:
                return candidate
        for candidate in candidates:
            if ResearchApplicationService._candidate_market(candidate) is not None:
                return candidate
        if candidates:
            return candidates[0]
        return None

    @staticmethod
    def _candidate_market(candidate: Any) -> str | None:
        market = str(getattr(candidate, "market_type", "")).strip().upper()
        if market in {"SPOT", "USD_M_FUTURES"}:
            return market
        return None

    @staticmethod
    def _default_virtual_portfolio_builder(
        snapshot: object,
        candidate: object,
    ) -> Any:
        market = ResearchApplicationService._candidate_market(candidate)
        if market is None:
            raise ValueError("virtual portfolio builder requires SPOT or USD_M_FUTURES")
        return cast(Any, VirtualPortfolioState)(
            portfolio_id=(
                f"virtual:{getattr(snapshot, 'snapshot_id', 'unknown')}:{market.lower()}"
            ),
            market=market,
            cash_usdt=Decimal("1000"),
            equity_usdt=Decimal("1000"),
        )

    @staticmethod
    def _attach_wallet(
        snapshot: Any,
        wallet: Any | None,
    ) -> Any:
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
        snapshot: Any,
    ) -> Any | None:
        if (
            self.market_context_registry is None
            or not self.market_context_provider_ids
            or self.market_context_request_builder is None
        ):
            return None
        return self.market_context_registry.collect(
            self.market_context_request_builder(
                snapshot_id=snapshot.snapshot_id,
                symbol=snapshot.symbol,
                requested_at=snapshot.created_at,
            ),
            self.market_context_provider_ids,
        )

    @staticmethod
    def _attach_market_context(
        snapshot: Any,
        batch: Any | None,
    ) -> Any:
        if batch is None:
            return snapshot
        existing = snapshot.news_snapshot.get("high_impact_events", ())
        incoming = batch.as_news_snapshot()["high_impact_events"]
        existing_events = existing if isinstance(existing, tuple) else ()
        incoming_events = incoming if isinstance(incoming, tuple) else ()
        merged_events: dict[str, Mapping[str, object]] = {}
        for raw_event in (*existing_events, *incoming_events):
            if not isinstance(raw_event, Mapping):
                continue
            event_id = raw_event.get("event_id")
            if isinstance(event_id, str) and event_id.strip():
                merged_events[event_id] = raw_event
        ordered_events = tuple(
            sorted(
                merged_events.values(),
                key=lambda item: (
                    item.get("scheduled_at", ""),
                    str(item.get("event_id", "")),
                ),
            )
        )
        news_snapshot = {
            **dict(snapshot.news_snapshot),
            **dict(batch.as_news_snapshot()),
            "high_impact_events": ordered_events,
        }
        if batch.events:
            latest = max(item.retrieved_at for item in batch.events)
            news_snapshot.update(
                {
                    "source_count": len(ordered_events),
                    "directional_vote": 0.0,
                    "score": 50.0,
                    "as_of": latest.isoformat(),
                }
            )
        sentiment_snapshot = dict(snapshot.sentiment_snapshot)
        if batch.events and not _has_external_evidence(sentiment_snapshot):
            latest = max(item.retrieved_at for item in batch.events)
            sentiment_snapshot.update(
                {
                    "source_count": len(ordered_events),
                    "directional_vote": 0.0,
                    "score": 50.0,
                    "as_of": latest.isoformat(),
                }
            )
        return replace(
            snapshot,
            news_snapshot=news_snapshot,
            sentiment_snapshot=sentiment_snapshot,
        )


def _has_external_evidence(snapshot: Mapping[str, object]) -> bool:
    source_count = snapshot.get("source_count")
    if isinstance(source_count, bool) or not isinstance(source_count, (int, float)):
        return False
    return source_count >= 1


def _canonical_sha256(
    primitive_converter: Callable[[object], object],
    value: object,
) -> str:
    primitive = primitive_converter(value)
    encoded = json.dumps(
        primitive,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _virtual_market_execution_surface() -> Any:
    execution_authority = __import__(
        "ai4binance.governance.execution_authority",
        fromlist=["ExecutionSurface"],
    )
    return execution_authority.ExecutionSurface.VIRTUAL_MARKET

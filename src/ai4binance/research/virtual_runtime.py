"""Bounded virtual-market runtime contracts independent from real account state."""

# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
    evaluate_virtual_simulation_eligibility,
)
from ai4binance.application.virtual_runtime_evidence import (
    build_virtual_loss_streak_halt_review,
)
from ai4binance.application.virtual_runtime_performance import (
    calculate_virtual_portfolio_performance_metrics,
)
from ai4binance.application.virtual_runtime_portfolio import (
    build_virtual_fill_preview,
    build_virtual_portfolio_blockers,
)
from ai4binance.domain import Action, ValidationStatus
from ai4binance.domain.research.virtual_runtime_attribution import (
    BacktestExitReason,
    ClosedTradeAttribution,
    TradeDirection,
    VirtualClosedTradeRecord,
    VirtualTradeAttributionAggregate,
    VirtualTradeAttributionLedger,
    build_virtual_trade_attribution_ledger,
)
from ai4binance.governance.blocker_reduction import VirtualBlockerReduction
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.ops.continuous_assurance import (
    DecisionProvenanceRecord,
    EvidenceGraphEdge,
    EvidenceGraphLiteRecord,
    EvidenceGraphNode,
    PolicyEvaluationRecord,
    SemanticContractRecord,
    TrustAssuranceBundle,
    TrustAssuranceResult,
    UncertaintyAssessmentRecord,
    UncertaintyLevel,
)
from ai4binance.ops.decision_telemetry import (
    AcceptanceGateStatus,
    AttributionMethod,
    BlockerEffectivenessRecord,
    BlockerOutcome,
    CanonicalTelemetrySnapshot,
    CounterfactualOutcome,
    CounterfactualType,
    DecisionEffectivenessClass,
    DecisionEffectivenessRecord,
    DecisionInputRecord,
    DecisionOutcomeRecord,
    DecisionProcessRecord,
    DgeEffectivenessMetrics,
    EvidenceQuality,
    ImprovementCandidate,
    MarketType,
    MetricEvidence,
    OpportunityCostType,
    OutcomeAttribution,
    PerformanceAcceptanceResult,
    PerformanceEvidenceSnapshot,
    TelemetryDomain,
    build_performance_evidence_snapshot,
)
from ai4binance.ops.user_reports import (
    UserReportPaths,
    render_professional_summary,
    user_report_paths,
    write_user_report_files,
)
from ai4binance.portfolio.risk_budget import (
    PositionExposure,
    assess_current_exposure,
    assess_proposed_exposure,
)
from ai4binance.research.backtesting.models import (
    MissedOpportunityCategory,
    MissedOpportunityLedger,
    MissedOpportunityRecord,
    TradeOutcome,
)
from ai4binance.research.backtesting.robustness import BacktestRobustnessReport
from ai4binance.research.equity_metrics import EquityObservation
from ai4binance.research.virtual_market import (
    AcceptanceStatus,
    CostStressScenarioEvidence,
    DailyEquityPoint,
    MarketAcceptanceResult,
    MarketPerformanceEvidence,
    RegimeAttribution,
    SystemResearchAcceptance,
    TwoStageProfitabilityEvidence,
    VirtualMarket,
    derive_virtual_runtime_priority_signal,
    evaluate_two_stage_profitability_evidence,
    render_system_acceptance_markdown,
)
from ai4binance.research.virtual_runtime_portfolio_state import (
    VirtualPortfolioState,
    VirtualPositionSide,
)
from ai4binance.research.virtual_runtime_portfolios import (
    IndependentVirtualPortfolios,
)
from ai4binance.research.virtual_runtime_request import VirtualRuntimeRequest
from ai4binance.research.virtual_runtime_risk import VirtualPortfolioRiskGovernor
from ai4binance.research.virtual_runtime_trade_intent import VirtualTradeIntent
from ai4binance.research_governance import (
    VirtualImprovementCandidateCycleExecutiveSummary,
    VirtualImprovementCandidateLifecycleSnapshot,
    VirtualImprovementCandidateOutcomeDashboardPayload,
    VirtualImprovementCandidateRegistryEntry,
    VirtualImprovementExperimentProposal,
    VirtualImprovementExperimentTaskQueue,
    VirtualImprovementExperimentTaskRecord,
    VirtualImprovementNextCandidateIntakeHandoff,
    VirtualImprovementNextCandidateRefusalArtifact,
    VirtualImprovementNextCandidateRegistrationPacket,
    VirtualImprovementOperatorHandoffSummary,
    VirtualImprovementRefusalLedgerEntry,
    VirtualImprovementResearchExecutionInbox,
    VirtualImprovementResearchExecutionSessionManifest,
    VirtualImprovementResearchSessionArtifactBundle,
    VirtualImprovementResearchSessionClosureRecord,
    VirtualImprovementResearchSessionJournal,
    VirtualImprovementResearchSessionReadinessSummary,
    VirtualImprovementResearchWorkPlanner,
    VirtualImprovementReviewResult,
    build_virtual_improvement_candidate_cycle_executive_summary,
    build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal,
    build_virtual_improvement_candidate_outcome_dashboard_payload,
    build_virtual_improvement_candidate_registry_entry,
    build_virtual_improvement_experiment_proposal,
    build_virtual_improvement_experiment_task,
    build_virtual_improvement_experiment_task_queue,
    build_virtual_improvement_next_candidate_intake_handoff,
    build_virtual_improvement_next_candidate_refusal_artifact,
    build_virtual_improvement_next_candidate_registration_packet,
    build_virtual_improvement_operator_handoff_summary,
    build_virtual_improvement_refusal_ledger_entry,
    build_virtual_improvement_research_execution_inbox,
    build_virtual_improvement_research_execution_session_manifest,
    build_virtual_improvement_research_session_artifact_bundle,
    build_virtual_improvement_research_session_closure_record,
    build_virtual_improvement_research_session_journal,
    build_virtual_improvement_research_session_readiness_summary,
    build_virtual_improvement_research_work_planner,
    build_virtual_improvement_review_result,
    consume_virtual_improvement_review_handoff,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.models import WalkForwardReport

if TYPE_CHECKING:
    from ai4binance.execution.lifecycle import (
        LifecycleExit,
        LifecyclePosition,
        PaperClosureReview,
    )
    from ai4binance.execution.paper import ExitReason

ZERO = Decimal("0")
ONE = Decimal("1")


class _VirtualSimulationStatusLegacy(StrEnum):
    """Deterministic eligibility outcome for the virtual execution surface."""

    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"


_VirtualSimulationEligibilityLegacy = VirtualSimulationEligibility


def _evaluate_virtual_simulation_eligibility_legacy(
    *,
    execution_surface: ExecutionSurface,
    analysis_blockers: tuple[str, ...] = (),
    candidate_blockers: tuple[str, ...] = (),
    risk_blockers: tuple[str, ...] = (),
    validation_blockers: tuple[str, ...] = (),
    dge_blockers: tuple[str, ...] = (),
    portfolio_blockers: tuple[str, ...] = (),
    feasibility_blockers: tuple[str, ...] = (),
) -> VirtualSimulationEligibility:
    """Compatibility wrapper that delegates to the canonical eligibility helper."""

    return evaluate_virtual_simulation_eligibility(
        execution_surface=execution_surface,
        analysis_blockers=analysis_blockers,
        candidate_blockers=candidate_blockers,
        risk_blockers=risk_blockers,
        validation_blockers=validation_blockers,
        dge_blockers=dge_blockers,
        portfolio_blockers=portfolio_blockers,
        feasibility_blockers=feasibility_blockers,
    )


class VirtualRuntimeDecisionStatus(StrEnum):
    """Deterministic outcome of one virtual runtime evaluation."""

    NO_ACTION = "NO_ACTION"
    ORDER_READY = "ORDER_READY"


class VirtualAutonomyHaltStatus(StrEnum):
    """Governed halt status for bounded virtual-market autonomy."""

    ACTIVE = "ACTIVE"
    CLEARED = "CLEARED"


class VirtualPositionLifecycleStatus(StrEnum):
    """Deterministic lifecycle state for one virtual position."""

    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class VirtualPortfolioPerformance:
    """Market-specific portfolio KPIs from regularly sampled equity observations."""

    market: str
    starting_equity_usdt: Decimal
    ending_equity_usdt: Decimal
    observation_count: int
    sample_period_seconds: int
    net_return: Decimal
    annualized_return: Decimal | None
    max_drawdown: Decimal
    portfolio_sharpe: Decimal | None
    portfolio_sortino: Decimal | None

    def __post_init__(self) -> None:
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError(
                "virtual portfolio performance market must be SPOT or USD_M_FUTURES"
            )
        object.__setattr__(self, "market", normalized_market)
        if (
            min(
                self.starting_equity_usdt,
                self.ending_equity_usdt,
                self.max_drawdown,
            )
            < ZERO
        ):
            raise ValueError("virtual portfolio performance values cannot be negative")
        if not self.net_return.is_finite():
            raise ValueError("virtual portfolio performance net return must be finite")
        if self.observation_count < 1 or self.sample_period_seconds < 0:
            raise ValueError("virtual portfolio performance sample metadata is invalid")
        if not ZERO <= self.max_drawdown <= ONE:
            raise ValueError(
                "virtual portfolio performance drawdown must stay within zero and one"
            )


@dataclass(frozen=True, slots=True)
class VirtualResearchEvidenceSurface:
    """Research-only evidence bundle for WF/OOS/robustness and improvement staging."""

    attribution_ledger: VirtualTradeAttributionLedger
    market_performance: MarketPerformanceEvidence
    profitability_evidence: TwoStageProfitabilityEvidence
    performance_snapshot: PerformanceEvidenceSnapshot
    improvement_candidates: tuple[ImprovementCandidate, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_nonblank_or_empty(
            "virtual research evidence blockers",
            self.blockers,
        )


@dataclass(frozen=True, slots=True)
class VirtualNoTradeEvidenceSurface:
    """Research-only measurable NO_TRADE evidence with missed-opportunity lineage."""

    missed_opportunity_ledger: MissedOpportunityLedger
    performance_snapshot: PerformanceEvidenceSnapshot
    improvement_candidates: tuple[ImprovementCandidate, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_nonblank_or_empty(
            "virtual no-trade evidence blockers",
            self.blockers,
        )


@dataclass(frozen=True, slots=True)
class VirtualLossStreakHaltReview:
    """Research-only halt review emitted when the loss-streak gate trips."""

    review_id: str
    snapshot_id: str
    decision_id: str
    portfolio_id: str
    halt_scope: str
    status: VirtualAutonomyHaltStatus
    trigger_blocker: str
    market: str
    symbol: str
    strategy_id: str
    strategy_version: str
    regime: str
    consecutive_losses: int
    maximum_consecutive_losses: int
    findings: tuple[str, ...]
    root_cause_tags: tuple[str, ...]
    root_cause_summary: str
    next_bounded_experiment: str
    reset_criteria: tuple[str, ...]
    improvement_candidates: tuple[ImprovementCandidate, ...] = ()
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def halted(self) -> bool:
        return self.status is VirtualAutonomyHaltStatus.ACTIVE

    def __post_init__(self) -> None:
        for value in (
            self.review_id,
            self.snapshot_id,
            self.decision_id,
            self.portfolio_id,
            self.halt_scope,
            self.trigger_blocker,
            self.market,
            self.symbol,
            self.strategy_id,
            self.strategy_version,
            self.regime,
        ):
            if not value.strip():
                raise ValueError("virtual halt review identity is required")
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError("virtual halt review market must be SPOT or USD_M_FUTURES")
        object.__setattr__(self, "market", normalized_market)
        _require_unique_nonblank("virtual halt review findings", self.findings)
        _require_unique_nonblank(
            "virtual halt review root cause tags",
            self.root_cause_tags,
        )
        _require_unique_nonblank(
            "virtual halt review reset criteria",
            self.reset_criteria,
        )
        if not self.root_cause_summary.strip():
            raise ValueError("virtual halt review root cause summary is required")
        if not self.next_bounded_experiment.strip():
            raise ValueError("virtual halt review next bounded experiment is required")
        if self.consecutive_losses < 1:
            raise ValueError("virtual halt review consecutive losses must be positive")
        if self.maximum_consecutive_losses < 1:
            raise ValueError("virtual halt review threshold must be positive")
        if self.halted and (
            self.consecutive_losses < self.maximum_consecutive_losses
            or self.trigger_blocker != "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED"
        ):
            raise ValueError(
                "active virtual halt review must match a tripped loss streak"
            )
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual halt review must remain research only and live blocked"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "snapshot_id": self.snapshot_id,
            "decision_id": self.decision_id,
            "portfolio_id": self.portfolio_id,
            "halt_scope": self.halt_scope,
            "status": self.status.value,
            "trigger_blocker": self.trigger_blocker,
            "market": self.market,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "regime": self.regime,
            "consecutive_losses": self.consecutive_losses,
            "maximum_consecutive_losses": self.maximum_consecutive_losses,
            "findings": list(self.findings),
            "root_cause_tags": list(self.root_cause_tags),
            "root_cause_summary": self.root_cause_summary,
            "next_bounded_experiment": self.next_bounded_experiment,
            "reset_criteria": list(self.reset_criteria),
            "improvement_candidates": [
                candidate.to_payload() for candidate in self.improvement_candidates
            ],
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class VirtualEvidenceSurfaceAdapter:
    """Single consumer-facing adapter for research and no-trade virtual evidence."""

    surface_kind: str
    market: str
    performance_snapshot: PerformanceEvidenceSnapshot
    telemetry_snapshot: CanonicalTelemetrySnapshot
    acceptance_results: tuple[PerformanceAcceptanceResult, ...]
    improvement_candidates: tuple[ImprovementCandidate, ...]
    blockers: tuple[str, ...] = ()
    market_acceptance_result: MarketAcceptanceResult | None = None

    def __post_init__(self) -> None:
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError("virtual evidence adapter surface kind is invalid")
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError(
                "virtual evidence adapter market must be SPOT or USD_M_FUTURES"
            )
        object.__setattr__(self, "market", normalized_market)
        if not self.acceptance_results:
            raise ValueError("virtual evidence adapter requires acceptance results")
        if (
            self.telemetry_snapshot.telemetry_id
            != self.performance_snapshot.snapshot_id
        ):
            raise ValueError(
                "virtual evidence adapter telemetry id must match snapshot"
            )
        if self.telemetry_snapshot.blockers != self.blockers:
            raise ValueError("virtual evidence adapter blockers must match telemetry")
        if any(result.blockers != self.blockers for result in self.acceptance_results):
            raise ValueError(
                "virtual evidence adapter acceptance blockers must match surface blockers"
            )
        if any(
            result.gate_eligible != self.telemetry_snapshot.gate_eligible
            for result in self.acceptance_results
        ):
            raise ValueError(
                "virtual evidence adapter acceptance eligibility must match telemetry"
            )
        if self.market_acceptance_result is not None:
            if self.market_acceptance_result.market.value != normalized_market:
                raise ValueError(
                    "virtual evidence adapter market acceptance must match market"
                )
            if tuple(self.market_acceptance_result.blockers) != self.blockers:
                raise ValueError(
                    "virtual evidence adapter market acceptance blockers must match"
                )
        if self.surface_kind == "RESEARCH":
            if self.telemetry_snapshot.gate_eligible != (not self.blockers):
                raise ValueError(
                    "virtual research evidence telemetry gate eligibility must match blockers"
                )
        elif self.telemetry_snapshot.gate_eligible:
            raise ValueError(
                "virtual no-trade evidence telemetry cannot be gate eligible"
            )
        _require_unique_nonblank_or_empty(
            "virtual evidence adapter blockers",
            self.blockers,
        )

    @property
    def primary_acceptance(self) -> PerformanceAcceptanceResult:
        return self.acceptance_results[0]

    @property
    def snapshot_id(self) -> str:
        return self.performance_snapshot.snapshot_id


@dataclass(frozen=True, slots=True)
class VirtualStagedImprovementCandidate:
    """Governed staging artifact for a research-only improvement candidate."""

    stage_id: str
    snapshot_id: str
    surface_kind: str
    candidate: ImprovementCandidate
    evidence_refs: tuple[str, ...]
    assurance_artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    human_review_required: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.stage_id.strip() or not self.snapshot_id.strip():
            raise ValueError("virtual staged improvement identity is required")
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError("virtual staged improvement surface kind is invalid")
        _require_unique_nonblank(
            "virtual staged improvement evidence refs",
            self.evidence_refs,
        )
        _require_unique_nonblank(
            "virtual staged improvement assurance artifact refs",
            self.assurance_artifact_refs,
        )
        _require_unique_nonblank_or_empty(
            "virtual staged improvement blockers",
            self.blockers,
        )
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError(
                "virtual staged improvement must remain research or staged"
            )
        staged = self.promotion_status is ValidationStatus.STAGED_CANDIDATE
        if staged == bool(self.blockers):
            raise ValueError(
                "virtual staged improvement promotion and blockers are inconsistent"
            )
        if (
            not self.human_review_required
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("virtual staged improvement cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "candidate": self.candidate.to_payload(),
            "evidence_refs": self.evidence_refs,
            "assurance_artifact_refs": self.assurance_artifact_refs,
            "blockers": self.blockers,
            "promotion_status": self.promotion_status.value,
            "human_review_required": True,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchWorkItem:
    """Research-only handoff item for a staged virtual improvement candidate."""

    work_id: str
    stage_id: str
    candidate_id: str
    snapshot_id: str
    surface_kind: str
    affected_component: str
    assurance_artifact_refs: tuple[str, ...]
    required_artifacts: tuple[str, ...]
    blockers: tuple[str, ...]
    triage_reason: str
    priority: str = "P1"
    status: str = "QUEUED_RESEARCH_ONLY"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        required = (
            self.work_id,
            self.stage_id,
            self.candidate_id,
            self.snapshot_id,
            self.surface_kind,
            self.affected_component,
            self.triage_reason,
            self.priority,
            self.status,
        )
        if any(not value.strip() for value in required):
            raise ValueError("virtual improvement work item identity is required")
        _require_unique_nonblank(
            "virtual improvement work item assurance artifact refs",
            self.assurance_artifact_refs,
        )
        _require_unique_nonblank(
            "virtual improvement work item artifacts",
            self.required_artifacts,
        )
        _require_unique_nonblank_or_empty(
            "virtual improvement work item blockers",
            self.blockers,
        )
        if self.priority not in {"P0", "P1"}:
            raise ValueError("virtual improvement work item priority is invalid")
        if not self.triage_reason.strip():
            raise ValueError("virtual improvement work item triage reason is required")
        if self.status != "QUEUED_RESEARCH_ONLY":
            raise ValueError("virtual improvement work item status is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("virtual improvement work item cannot authorize trading")

    def normalized_handoff_payload(self) -> dict[str, object]:
        return {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": self.work_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": (
                "Review the staged virtual improvement candidate and determine "
                "the next bounded research action without granting paper or live authority."
            ),
            "context_refs": (
                f"virtual-improvement-stage:{self.stage_id}",
                f"virtual-improvement-component:{self.affected_component}",
            ),
            "evidence_refs": (
                self.snapshot_id,
                self.stage_id,
                self.candidate_id,
                *self.assurance_artifact_refs,
                *self.required_artifacts,
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "policy_version_refs": (
                "virtual-runtime-improvement-queue/v1",
                "virtual-runtime-staging/v1",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "triage_reason": self.triage_reason,
            "blocker_refs": self.blockers,
            "priority": self.priority,
            "status": self.status,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            "work_id": self.work_id,
            "stage_id": self.stage_id,
            "candidate_id": self.candidate_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "affected_component": self.affected_component,
            "assurance_artifact_refs": list(self.assurance_artifact_refs),
            "required_artifacts": list(self.required_artifacts),
            "blockers": list(self.blockers),
            "triage_reason": self.triage_reason,
            "priority": self.priority,
            "status": self.status,
            "handoff": self.normalized_handoff_payload(),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class VirtualImprovementResearchQueue:
    """Research-only queue visible to downstream governed consumers."""

    queue_id: str
    snapshot_id: str
    surface_kind: str
    items: tuple[VirtualImprovementResearchWorkItem, ...]
    assurance_artifact_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    triage_reason: str
    command: str = "virtual-improvement-research-queue"
    status: str = "QUEUED_WITH_BLOCKERS"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.queue_id.strip() or not self.snapshot_id.strip():
            raise ValueError("virtual improvement research queue identity is required")
        if self.surface_kind not in {"RESEARCH", "NO_TRADE"}:
            raise ValueError(
                "virtual improvement research queue surface kind is invalid"
            )
        if not self.triage_reason.strip():
            raise ValueError(
                "virtual improvement research queue triage reason is required"
            )
        if self.status not in {"READY", "QUEUED_WITH_BLOCKERS"}:
            raise ValueError("virtual improvement research queue status is invalid")
        _require_unique_nonblank(
            "virtual improvement research queue assurance artifact refs",
            self.assurance_artifact_refs,
        )
        _require_unique_nonblank_or_empty(
            "virtual improvement research queue blockers",
            self.blockers,
        )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "virtual improvement research queue cannot authorize trading"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "command": self.command,
            "queue_id": self.queue_id,
            "snapshot_id": self.snapshot_id,
            "surface_kind": self.surface_kind,
            "triage_reason": self.triage_reason,
            "status": self.status,
            "assurance_artifact_refs": list(self.assurance_artifact_refs),
            "items": [item.to_payload() for item in self.items],
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class VirtualRuntimeDecision:
    """Deterministic wallet-independent virtual runtime result."""

    status: VirtualRuntimeDecisionStatus
    eligibility: VirtualSimulationEligibility
    trade_intent: VirtualTradeIntent | None
    portfolio_before: VirtualPortfolioState
    portfolio_after: VirtualPortfolioState
    audit_refs: tuple[str, ...]
    halt_review: VirtualLossStreakHaltReview | None = None

    @property
    def halted(self) -> bool:
        return self.halt_review is not None and self.halt_review.halted

    @property
    def blocker_reduction(self) -> VirtualBlockerReduction | None:
        """Return the canonical blocker reduction attached to the decision."""

        return cast(
            VirtualBlockerReduction | None,
            self.eligibility.blocker_reduction,
        )

    def __post_init__(self) -> None:
        _require_unique_nonblank("virtual runtime audit refs", self.audit_refs)
        if (
            self.status is VirtualRuntimeDecisionStatus.ORDER_READY
            and self.trade_intent is None
        ):
            raise ValueError(
                "ORDER_READY virtual runtime decision requires trade intent"
            )
        if (
            self.status is VirtualRuntimeDecisionStatus.NO_ACTION
            and self.trade_intent is not None
        ):
            raise ValueError("NO_ACTION virtual runtime decision cannot carry intent")
        if (
            self.status is VirtualRuntimeDecisionStatus.ORDER_READY
            and self.halt_review is not None
        ):
            raise ValueError(
                "ORDER_READY virtual runtime decision cannot carry a halt review"
            )
        if self.halt_review is not None and (
            self.status is not VirtualRuntimeDecisionStatus.NO_ACTION
            or "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" not in self.eligibility.blockers
        ):
            raise ValueError(
                "virtual runtime halt review requires a no-action loss-streak veto"
            )


@dataclass(frozen=True, slots=True)
class VirtualPositionExit:
    """Canonical virtual exit event with explicit reason code."""

    timestamp: datetime
    reason: BacktestExitReason
    price: Decimal
    quantity: Decimal
    fee_usdt: Decimal
    net_pnl_usdt: Decimal
    slippage_cost_usdt: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("virtual position exit timestamp must be timezone-aware")
        if (
            min(
                self.price,
                self.quantity,
                self.fee_usdt,
                self.slippage_cost_usdt,
            )
            < ZERO
        ):
            raise ValueError("virtual position exit values cannot be negative")


@dataclass(frozen=True, slots=True)
class VirtualClosureReview:
    """Virtual-market closure review aligned with canonical paper review fields."""

    exit_reason: BacktestExitReason
    lifecycle_error: str | None
    stop_quality: str
    trailing_quality: str
    ignored_signals: int
    htf_weakness: bool
    volatility_expansion: bool
    level_break: bool
    staged_exit_alternative: str
    lesson_candidate: str


@dataclass(frozen=True, slots=True)
class VirtualManagedPosition:
    """Persisted virtual position state for candle-driven exit management."""

    position_id: str
    candidate_id: str
    symbol: str
    market: str
    opened_at: datetime
    entry_price: Decimal
    entry_fee_usdt: Decimal
    initial_quantity: Decimal
    remaining_quantity: Decimal
    stop_loss: Decimal
    trailing_stop: Decimal
    atr: Decimal
    take_profit_levels: tuple[Decimal, ...]
    opportunity_id: str = "UNKNOWN_OPPORTUNITY"
    take_profit_quantity_ratios: tuple[Decimal, ...] = ()
    status: VirtualPositionLifecycleStatus = VirtualPositionLifecycleStatus.OPEN
    next_target_index: int = 0
    realized_pnl_usdt: Decimal = ZERO
    exits: tuple[VirtualPositionExit, ...] = ()
    closure_review: VirtualClosureReview | None = None
    position_side: VirtualPositionSide = VirtualPositionSide.LONG
    maximum_holding_bars: int | None = None
    breakeven_trigger_r: Decimal | None = None
    trailing_atr_multiple: Decimal | None = None
    bars_held: int = 0
    maximum_favorable_excursion_usdt: Decimal = ZERO
    maximum_adverse_excursion_usdt: Decimal = ZERO
    fee_ratio: Decimal = Decimal("0.001")
    slippage_ratio: Decimal = Decimal("0.0005")
    tick_size: Decimal = Decimal("0.00000001")
    strategy_id: str = "UNSPECIFIED_STRATEGY"
    strategy_version: str = "1"
    strategy_config_version: str = "1"
    strategy_config_hash: str = "default"
    regime: str = "UNKNOWN"
    timeframe: str = "UNKNOWN"
    snapshot_id: str = "UNKNOWN_SNAPSHOT"
    decision_id: str = "UNKNOWN_DECISION"
    dge_decision: str = "UNKNOWN"
    risk_policy_version: str = "unknown"
    validation_version: str = "unknown"
    entry_reason: tuple[str, ...] = ("VIRTUAL_MARKET_ENTRY",)
    entry_slippage_cost_usdt: Decimal = ZERO
    funding_cost_usdt: Decimal = ZERO
    isolated_margin_usdt: Decimal | None = None
    initial_margin_usdt: Decimal | None = None
    maintenance_margin_ratio: Decimal | None = None
    liquidation_price: Decimal | None = None
    leverage: int | None = None
    liquidation_fee_ratio: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        from ai4binance.execution.lifecycle import StagedExitPlan

        for value in (
            self.position_id,
            self.candidate_id,
            self.opportunity_id,
            self.symbol,
            self.market,
        ):
            if not value.strip():
                raise ValueError("virtual managed position identity is required")
        if self.opened_at.tzinfo is None or self.opened_at.utcoffset() is None:
            raise ValueError(
                "virtual managed position timestamp must be timezone-aware"
            )
        if (
            min(
                self.entry_price,
                self.initial_quantity,
                self.stop_loss,
                self.trailing_stop,
                self.atr,
                self.tick_size,
            )
            <= ZERO
        ):
            raise ValueError("virtual managed position values must be positive")
        if (
            self.entry_fee_usdt < ZERO
            or self.realized_pnl_usdt < -self.entry_price * self.initial_quantity
        ):
            raise ValueError("virtual managed position accounting is invalid")
        if not ZERO <= self.remaining_quantity <= self.initial_quantity:
            raise ValueError("virtual managed position remaining quantity is invalid")
        if (
            self.status is VirtualPositionLifecycleStatus.CLOSED
            and self.remaining_quantity != ZERO
        ):
            raise ValueError("closed virtual managed position cannot retain quantity")
        if (
            self.status is not VirtualPositionLifecycleStatus.CLOSED
            and self.remaining_quantity == ZERO
        ):
            raise ValueError("active virtual managed position must retain quantity")
        if (
            self.bars_held < 0
            or self.maximum_favorable_excursion_usdt < ZERO
            or self.maximum_adverse_excursion_usdt < ZERO
        ):
            raise ValueError(
                "virtual managed position lifecycle counters must be non-negative"
            )
        if self.entry_slippage_cost_usdt < ZERO:
            raise ValueError("entry slippage cost cannot be negative")
        if not self.funding_cost_usdt.is_finite():
            raise ValueError("funding cost must be finite")
        if (
            not self.liquidation_fee_ratio.is_finite()
            or not ZERO <= self.liquidation_fee_ratio <= Decimal("0.02")
        ):
            raise ValueError("liquidation fee ratio is invalid")
        _require_unique_nonblank(
            "virtual managed position entry reason", self.entry_reason
        )
        if self.maximum_holding_bars is not None and self.maximum_holding_bars < 1:
            raise ValueError("maximum_holding_bars must be positive when configured")
        if self.breakeven_trigger_r is not None and self.breakeven_trigger_r <= ZERO:
            raise ValueError("breakeven_trigger_r must be positive when configured")
        if (
            self.trailing_atr_multiple is not None
            and self.trailing_atr_multiple <= ZERO
        ):
            raise ValueError("trailing_atr_multiple must be positive when configured")
        if not self.take_profit_levels:
            raise ValueError("virtual managed position requires take-profit levels")
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError(
                "virtual managed position market must be SPOT or USD_M_FUTURES"
            )
        object.__setattr__(self, "market", normalized_market)
        if self.position_side is VirtualPositionSide.LONG:
            if tuple(sorted(self.take_profit_levels)) != self.take_profit_levels:
                raise ValueError(
                    "long virtual managed position targets must be ascending"
                )
            if self.stop_loss >= self.entry_price:
                raise ValueError("long stop loss must remain below entry")
        elif self.stop_loss <= self.entry_price:
            raise ValueError("short stop loss must remain above entry")
        if normalized_market == "SPOT":
            if self.position_side is not VirtualPositionSide.LONG:
                raise ValueError("Spot virtual managed position must be long")
            if any(
                value is not None
                for value in (
                    self.isolated_margin_usdt,
                    self.initial_margin_usdt,
                    self.maintenance_margin_ratio,
                    self.liquidation_price,
                    self.leverage,
                )
            ):
                raise ValueError(
                    "Spot virtual managed position cannot contain Futures margin"
                )
        else:
            if any(
                value is None
                for value in (
                    self.isolated_margin_usdt,
                    self.initial_margin_usdt,
                    self.maintenance_margin_ratio,
                    self.liquidation_price,
                    self.leverage,
                )
            ):
                raise ValueError(
                    "Futures virtual managed position requires complete margin evidence"
                )
            isolated_margin = cast(Decimal, self.isolated_margin_usdt)
            initial_margin = cast(Decimal, self.initial_margin_usdt)
            maintenance_ratio = cast(Decimal, self.maintenance_margin_ratio)
            liquidation_price = cast(Decimal, self.liquidation_price)
            leverage = cast(int, self.leverage)
            if (
                min(isolated_margin, initial_margin, liquidation_price) <= ZERO
                or not ZERO < maintenance_ratio < ONE
                or isinstance(leverage, bool)
                or not 1 <= leverage <= 125
                or isolated_margin < initial_margin
            ):
                raise ValueError(
                    "Futures virtual managed position margin evidence is invalid"
                )
            if self.position_side is VirtualPositionSide.LONG:
                if liquidation_price >= self.entry_price:
                    raise ValueError(
                        "long Futures liquidation price must remain below entry"
                    )
            elif liquidation_price <= self.entry_price:
                raise ValueError(
                    "short Futures liquidation price must remain above entry"
                )
        for value in (
            self.strategy_id,
            self.strategy_version,
            self.strategy_config_version,
            self.strategy_config_hash,
            self.regime,
            self.timeframe,
            self.snapshot_id,
            self.decision_id,
            self.dge_decision,
            self.risk_policy_version,
            self.validation_version,
        ):
            if not value.strip():
                raise ValueError(
                    "virtual managed position attribution fields are required"
                )
        if not self.take_profit_quantity_ratios:
            if len(self.take_profit_levels) != 1:
                raise ValueError(
                    "staged virtual managed position requires quantity ratios for multiple targets"
                )
            object.__setattr__(self, "take_profit_quantity_ratios", (ONE,))
        plan = StagedExitPlan(
            targets=self._normalized_targets(),
            quantity_ratios=self.take_profit_quantity_ratios,
        )
        if self.next_target_index < 0 or self.next_target_index > len(plan.targets):
            raise ValueError("virtual managed position target index is invalid")

    def _normalized_targets(self) -> tuple[Decimal, ...]:
        if self.position_side is VirtualPositionSide.LONG:
            return self.take_profit_levels
        descending = tuple(sorted(self.take_profit_levels, reverse=True))
        if descending != self.take_profit_levels:
            raise ValueError(
                "short virtual managed position targets must be descending"
            )
        return tuple(sorted(self.take_profit_levels))


@dataclass(frozen=True, slots=True)
class VirtualExitContext:
    """Explicit deterministic non-price exit triggers for one virtual candle."""

    ignored_signals: int = 0
    htf_weakness: bool = False
    volatility_expansion: bool = False
    level_break: bool = False
    structure_invalidation: bool = False
    regime_failure: bool = False
    momentum_failure: bool = False

    def __post_init__(self) -> None:
        if self.ignored_signals < 0:
            raise ValueError("ignored signal count cannot be negative")


@dataclass(frozen=True, slots=True)
class VirtualFuturesPositionContext:
    """One timestamp-bound mark and funding observation for Futures lifecycle."""

    observed_at: datetime
    mark_price: Decimal
    funding_rate: Decimal
    funding_payment_due: bool = False

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError(
                "Futures position context timestamp must be timezone-aware"
            )
        if not self.mark_price.is_finite() or self.mark_price <= ZERO:
            raise ValueError("Futures position context mark price must be positive")
        if not self.funding_rate.is_finite():
            raise ValueError("Futures position context funding rate must be finite")
        if not isinstance(self.funding_payment_due, bool):
            raise ValueError("Futures position funding payment due must be boolean")


@dataclass(frozen=True, slots=True)
class VirtualPositionUpdateDecision:
    """Deterministic position update result after one candle."""

    position_before: VirtualManagedPosition
    position_after: VirtualManagedPosition
    portfolio_after: VirtualPortfolioState
    exit_reason: BacktestExitReason | None
    closed_trade: VirtualClosedTradeRecord | None
    reason_codes: tuple[str, ...]
    audit_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_unique_nonblank(
            "virtual position update reason codes", self.reason_codes
        )
        _require_unique_nonblank("virtual position update audit refs", self.audit_refs)


@dataclass(frozen=True, slots=True)
class VirtualFillPreview:
    """Deterministic fill preview before portfolio mutation."""

    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    fill_ratio: Decimal
    execution_price: Decimal
    gross_notional_usdt: Decimal
    fee_usdt: Decimal
    slippage_cost_usdt: Decimal
    price_impact_ratio: Decimal
    reason_codes: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_nonblank("virtual fill preview reason codes", self.reason_codes)
        _require_unique_nonblank("virtual fill preview blockers", self.blockers)


@dataclass(frozen=True, slots=True)
class VirtualMarketRuntime:
    """Dedicated virtual runtime boundary that never depends on real accounts."""

    _HALT_REVIEW_REGISTRY_HISTORY_LIMIT = 200

    def evaluate(self, request: VirtualRuntimeRequest) -> VirtualRuntimeDecision:
        fill_preview = self._fill_preview(request)
        portfolio_blockers = self._portfolio_blockers(request, fill_preview)
        governor_blockers = self._portfolio_governor_blockers(request, fill_preview)
        eligibility = evaluate_virtual_simulation_eligibility(
            execution_surface=request.execution_surface,
            analysis_blockers=request.analysis_blockers,
            candidate_blockers=request.candidate_blockers,
            risk_blockers=request.risk_blockers,
            validation_blockers=request.validation_blockers,
            dge_blockers=request.dge_blockers,
            portfolio_blockers=tuple(
                dict.fromkeys((*portfolio_blockers, *governor_blockers))
            ),
            feasibility_blockers=fill_preview.blockers,
        )
        audit_refs = (
            request.snapshot_id,
            request.decision_id,
            request.portfolio.portfolio_id,
        )
        if not eligibility.eligible:
            halt_review = self._loss_streak_halt_review(request, eligibility)
            return VirtualRuntimeDecision(
                status=VirtualRuntimeDecisionStatus.NO_ACTION,
                eligibility=eligibility,
                trade_intent=None,
                portfolio_before=request.portfolio,
                portfolio_after=request.portfolio,
                audit_refs=audit_refs,
                halt_review=halt_review,
            )
        intent = VirtualTradeIntent(
            snapshot_id=request.snapshot_id,
            decision_id=request.decision_id,
            candidate_id=request.candidate_id,
            opportunity_id=request.opportunity_id,
            symbol=request.symbol,
            market=request.market,
            action=request.action,
            quantity=fill_preview.filled_quantity,
            entry_price=fill_preview.execution_price,
            stop_loss=request.stop_loss,
            take_profit_levels=request.take_profit_levels,
            position_side=request.position_side,
            reason_codes=tuple(
                dict.fromkeys((*eligibility.reason_codes, *fill_preview.reason_codes))
            ),
        )
        portfolio_after = self._portfolio_after_fill(request, fill_preview)
        return VirtualRuntimeDecision(
            status=VirtualRuntimeDecisionStatus.ORDER_READY,
            eligibility=eligibility,
            trade_intent=intent,
            portfolio_before=request.portfolio,
            portfolio_after=portfolio_after,
            audit_refs=audit_refs,
        )

    @staticmethod
    def _loss_streak_halt_review(
        request: VirtualRuntimeRequest,
        eligibility: VirtualSimulationEligibility,
    ) -> VirtualLossStreakHaltReview | None:
        return cast(
            VirtualLossStreakHaltReview | None,
            build_virtual_loss_streak_halt_review(request, eligibility),
        )

    @staticmethod
    def _portfolio_governor_blockers(
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        governor = request.portfolio_governor
        policy = governor.exposure_policy
        current = (
            request.current_exposures
            or VirtualMarketRuntime._default_current_exposures(
                request.portfolio,
                request=request,
            )
        )
        current_assessment = assess_current_exposure(current, policy)
        blockers.extend(current_assessment.blockers)
        if not (request.portfolio.market == "SPOT" and request.action is Action.SELL):
            proposed = PositionExposure(
                symbol=request.symbol,
                strategy_id=request.strategy_id,
                correlation_group=request.correlation_group,
                notional_usdt=fill_preview.gross_notional_usdt,
            )
            proposed_assessment = assess_proposed_exposure(current, proposed, policy)
            blockers.extend(proposed_assessment.blockers)
        proposed_risk = VirtualMarketRuntime._proposed_risk_usdt(request, fill_preview)
        if proposed_risk > governor.maximum_risk_per_trade_usdt:
            blockers.append("VIRTUAL_RISK_PER_TRADE_LIMIT_EXCEEDED")
        if (
            request.portfolio.current_open_risk_usdt + proposed_risk
            > governor.maximum_open_risk_usdt
        ):
            blockers.append("VIRTUAL_OPEN_RISK_LIMIT_EXCEEDED")
        if request.portfolio.max_drawdown_ratio > governor.maximum_drawdown_ratio:
            blockers.append("VIRTUAL_DRAWDOWN_LIMIT_EXCEEDED")
        if (
            request.portfolio.consecutive_losses
            >= governor.maximum_consecutive_losses
            > 0
        ):
            blockers.append("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED")
        if not (
            request.portfolio.market == "SPOT" and request.action is Action.SELL
        ) and (
            request.portfolio.open_position_count
            >= request.portfolio.max_concurrent_positions
        ):
            blockers.append("VIRTUAL_MAX_CONCURRENT_POSITIONS_EXCEEDED")
        if request.portfolio.market == "USD_M_FUTURES":
            current_margin_utilization = (
                request.portfolio.margin_utilization_ratio or ZERO
            )
            if current_margin_utilization > governor.maximum_margin_utilization_ratio:
                blockers.append("FUTURES_MARGIN_UTILIZATION_LIMIT_EXCEEDED")
            if (
                request.leverage is not None
                and request.leverage > governor.maximum_futures_leverage
            ):
                blockers.append("FUTURES_LEVERAGE_LIMIT_EXCEEDED")
        return tuple(dict.fromkeys(blockers))

    def process_position(
        self,
        *,
        position: VirtualManagedPosition,
        portfolio: VirtualPortfolioState,
        candle: OHLCVCandle,
        context: VirtualExitContext | None = None,
        futures_context: VirtualFuturesPositionContext | None = None,
        candle_available_at: datetime | None = None,
    ) -> VirtualPositionUpdateDecision:
        from ai4binance.execution.lifecycle import (
            ClosureContext,
            PaperLifecycleEngine,
            PositionStatus,
        )

        exit_context = context or VirtualExitContext()
        if position.market != portfolio.market:
            raise ValueError(
                "virtual managed position market must match portfolio market"
            )
        if position.market == "USD_M_FUTURES":
            if futures_context is None:
                raise ValueError(
                    "Futures virtual position lifecycle requires mark and funding "
                    "context"
                )
            expected_observed_at = candle_available_at or candle.timestamp
            if futures_context.observed_at != expected_observed_at:
                raise ValueError(
                    "Futures position context must match the candle availability time"
                )
            return self._process_futures_position(
                position=position,
                portfolio=portfolio,
                candle=candle,
                context=exit_context,
                futures_context=futures_context,
            )
        if futures_context is not None:
            raise ValueError("Spot position lifecycle cannot use Futures context")
        if position.position_side is not VirtualPositionSide.LONG:
            raise ValueError("Spot virtual position lifecycle requires a long position")
        lifecycle_before = self._lifecycle_position(position)
        engine = PaperLifecycleEngine(
            fee_ratio=position.fee_ratio,
            slippage_ratio=position.slippage_ratio,
            trailing_multiplier=position.trailing_atr_multiple or Decimal("1.5"),
            tick_size=position.tick_size,
        )
        lifecycle_after = engine.process_candle(
            lifecycle_before,
            candle,
            ClosureContext(
                ignored_signals=exit_context.ignored_signals,
                htf_weakness=exit_context.htf_weakness,
                volatility_expansion=exit_context.volatility_expansion,
                level_break=exit_context.level_break,
            ),
        )
        bars_held = position.bars_held + 1
        mfe = max(
            position.maximum_favorable_excursion_usdt,
            max(candle.high - position.entry_price, ZERO) * position.initial_quantity,
        )
        reason_override: BacktestExitReason | None = None
        if (
            lifecycle_after.status is not PositionStatus.CLOSED
            and self._breakeven_trigger_reached(
                position,
                maximum_favorable_excursion_usdt=mfe,
            )
        ):
            lifecycle_after = replace(
                lifecycle_after,
                trailing_stop=max(
                    lifecycle_after.trailing_stop, lifecycle_after.entry_price
                ),
            )
        forced_reason = self._forced_exit_reason(exit_context)
        if (
            forced_reason is not None
            and lifecycle_after.status is not PositionStatus.CLOSED
        ):
            reason_override = forced_reason
            lifecycle_after = self._close_lifecycle_remaining(
                lifecycle_after,
                timestamp=candle.timestamp,
                reason=forced_reason,
                reference_price=candle.close,
                context=exit_context,
                fee_ratio=position.fee_ratio,
                slippage_ratio=position.slippage_ratio,
            )
        elif (
            position.maximum_holding_bars is not None
            and bars_held > position.maximum_holding_bars
            and lifecycle_after.status is not PositionStatus.CLOSED
        ):
            reason_override = BacktestExitReason.TIME_EXIT
            lifecycle_after = self._close_lifecycle_remaining(
                lifecycle_after,
                timestamp=candle.timestamp,
                reason=BacktestExitReason.TIME_EXIT,
                reference_price=candle.close,
                context=exit_context,
                fee_ratio=position.fee_ratio,
                slippage_ratio=position.slippage_ratio,
            )
        position_after = self._managed_position_from_lifecycle(
            original=position,
            lifecycle=lifecycle_after,
            bars_held=bars_held,
            maximum_favorable_excursion_usdt=mfe,
            reason_override=reason_override,
        )
        portfolio_after = self._spot_portfolio_after_position_update(
            portfolio=portfolio,
            position_before=position,
            position_after=position_after,
            mark_price=candle.close,
        )
        new_exits = position_after.exits[len(position.exits) :]
        exit_reason = new_exits[-1].reason if new_exits else None
        closed_trade = (
            self._closed_trade_record(position, position_after)
            if position_after.status is VirtualPositionLifecycleStatus.CLOSED
            else None
        )
        reason_codes = tuple(
            dict.fromkeys(
                (
                    *(exit.reason.value for exit in new_exits),
                    position_after.status.value,
                )
            )
        )
        return VirtualPositionUpdateDecision(
            position_before=position,
            position_after=position_after,
            portfolio_after=portfolio_after,
            exit_reason=exit_reason,
            closed_trade=closed_trade,
            reason_codes=reason_codes,
            audit_refs=(
                position.position_id,
                position.candidate_id,
                position.symbol,
                candle.timestamp.isoformat(),
            ),
        )

    def _process_futures_position(
        self,
        *,
        position: VirtualManagedPosition,
        portfolio: VirtualPortfolioState,
        candle: OHLCVCandle,
        context: VirtualExitContext,
        futures_context: VirtualFuturesPositionContext,
    ) -> VirtualPositionUpdateDecision:
        funding_delta = ZERO
        if futures_context.funding_payment_due:
            direction_sign = (
                ONE if position.position_side is VirtualPositionSide.LONG else -ONE
            )
            funding_delta = (
                position.entry_price
                * position.remaining_quantity
                * futures_context.funding_rate
                * direction_sign
            )
        bars_held = position.bars_held + 1
        if position.position_side is VirtualPositionSide.LONG:
            favorable = max(candle.high - position.entry_price, ZERO)
            adverse = max(position.entry_price - candle.low, ZERO)
        else:
            favorable = max(position.entry_price - candle.low, ZERO)
            adverse = max(candle.high - position.entry_price, ZERO)
        mfe = max(
            position.maximum_favorable_excursion_usdt,
            favorable * position.initial_quantity,
        )
        mae = max(
            position.maximum_adverse_excursion_usdt,
            adverse * position.initial_quantity,
        )
        exits: list[VirtualPositionExit] = []
        remaining = position.remaining_quantity
        realized_pnl = position.realized_pnl_usdt - funding_delta
        next_target_index = position.next_target_index
        exit_reason: BacktestExitReason | None = None

        protective_reason, protective_price = self._futures_protective_exit(
            position,
            candle,
        )
        forced_reason = self._forced_exit_reason(context)
        if protective_reason is not None:
            exit_reason = protective_reason
            exit_event = self._futures_exit(
                position=position,
                timestamp=candle.timestamp,
                reason=protective_reason,
                reference_price=cast(Decimal, protective_price),
                quantity=remaining,
            )
            exits.append(exit_event)
            realized_pnl += exit_event.net_pnl_usdt
            remaining = ZERO
        elif forced_reason is not None:
            exit_reason = forced_reason
            exit_event = self._futures_exit(
                position=position,
                timestamp=candle.timestamp,
                reason=forced_reason,
                reference_price=candle.close,
                quantity=remaining,
            )
            exits.append(exit_event)
            realized_pnl += exit_event.net_pnl_usdt
            remaining = ZERO
        else:
            while next_target_index < len(position.take_profit_levels):
                target = position.take_profit_levels[next_target_index]
                reached = (
                    candle.high >= target
                    if position.position_side is VirtualPositionSide.LONG
                    else candle.low <= target
                )
                if not reached:
                    break
                ratio = position.take_profit_quantity_ratios[next_target_index]
                target_quantity = min(
                    remaining,
                    position.initial_quantity * ratio,
                )
                if next_target_index == len(position.take_profit_levels) - 1:
                    target_quantity = remaining
                exit_event = self._futures_exit(
                    position=position,
                    timestamp=candle.timestamp,
                    reason=BacktestExitReason.TARGET,
                    reference_price=target,
                    quantity=target_quantity,
                )
                exits.append(exit_event)
                realized_pnl += exit_event.net_pnl_usdt
                remaining -= target_quantity
                next_target_index += 1
                exit_reason = BacktestExitReason.TARGET
                if remaining == ZERO:
                    break
            if (
                remaining > ZERO
                and position.maximum_holding_bars is not None
                and bars_held > position.maximum_holding_bars
            ):
                exit_reason = BacktestExitReason.TIME_EXIT
                exit_event = self._futures_exit(
                    position=position,
                    timestamp=candle.timestamp,
                    reason=BacktestExitReason.TIME_EXIT,
                    reference_price=candle.close,
                    quantity=remaining,
                )
                exits.append(exit_event)
                realized_pnl += exit_event.net_pnl_usdt
                remaining = ZERO

        trailing_stop = position.trailing_stop
        if remaining > ZERO:
            trailing_stop = self._futures_trailing_stop(
                position,
                candle=candle,
                maximum_favorable_excursion_usdt=mfe,
            )
        status = (
            VirtualPositionLifecycleStatus.CLOSED
            if remaining == ZERO
            else VirtualPositionLifecycleStatus.PARTIALLY_CLOSED
            if exits
            or position.status is VirtualPositionLifecycleStatus.PARTIALLY_CLOSED
            else VirtualPositionLifecycleStatus.OPEN
        )
        closure_review = (
            _virtual_review(
                reason=cast(BacktestExitReason, exit_reason),
                context=context,
                staged_exit_used=len(position.exits) + len(exits) > 1,
            )
            if status is VirtualPositionLifecycleStatus.CLOSED
            else None
        )
        position_after = replace(
            position,
            remaining_quantity=remaining,
            trailing_stop=trailing_stop,
            status=status,
            next_target_index=next_target_index,
            realized_pnl_usdt=realized_pnl,
            exits=(*position.exits, *exits),
            closure_review=closure_review,
            bars_held=bars_held,
            maximum_favorable_excursion_usdt=mfe,
            maximum_adverse_excursion_usdt=mae,
            funding_cost_usdt=position.funding_cost_usdt + funding_delta,
        )
        portfolio_after = self._futures_portfolio_after_position_update(
            portfolio=portfolio,
            position_before=position,
            position_after=position_after,
            mark_price=futures_context.mark_price,
            funding_delta=funding_delta,
        )
        closed_trade = (
            self._closed_trade_record(position, position_after)
            if status is VirtualPositionLifecycleStatus.CLOSED
            else None
        )
        reason_codes = tuple(
            dict.fromkeys(
                (
                    *(exit.reason.value for exit in exits),
                    *(("FUTURES_FUNDING_APPLIED",) if funding_delta != ZERO else ()),
                    status.value,
                )
            )
        )
        return VirtualPositionUpdateDecision(
            position_before=position,
            position_after=position_after,
            portfolio_after=portfolio_after,
            exit_reason=exit_reason,
            closed_trade=closed_trade,
            reason_codes=reason_codes,
            audit_refs=(
                position.position_id,
                position.candidate_id,
                position.symbol,
                candle.timestamp.isoformat(),
            ),
        )

    @staticmethod
    def _futures_protective_exit(
        position: VirtualManagedPosition,
        candle: OHLCVCandle,
    ) -> tuple[BacktestExitReason | None, Decimal | None]:
        liquidation_price = cast(Decimal, position.liquidation_price)
        if position.position_side is VirtualPositionSide.LONG:
            if candle.low <= liquidation_price:
                return BacktestExitReason.LIQUIDATION, liquidation_price
            protective_stop = max(position.stop_loss, position.trailing_stop)
            if candle.low <= protective_stop:
                reason = (
                    BacktestExitReason.TRAILING_STOP
                    if protective_stop > position.stop_loss
                    else BacktestExitReason.HARD_STOP
                )
                return reason, protective_stop
        else:
            if candle.high >= liquidation_price:
                return BacktestExitReason.LIQUIDATION, liquidation_price
            protective_stop = min(position.stop_loss, position.trailing_stop)
            if candle.high >= protective_stop:
                reason = (
                    BacktestExitReason.TRAILING_STOP
                    if protective_stop < position.stop_loss
                    else BacktestExitReason.HARD_STOP
                )
                return reason, protective_stop
        return None, None

    @staticmethod
    def _futures_exit(
        *,
        position: VirtualManagedPosition,
        timestamp: datetime,
        reason: BacktestExitReason,
        reference_price: Decimal,
        quantity: Decimal,
    ) -> VirtualPositionExit:
        if position.position_side is VirtualPositionSide.LONG:
            raw_price = reference_price * (ONE - position.slippage_ratio)
            price = raw_price.quantize(position.tick_size, rounding=ROUND_DOWN)
            gross_pnl = (price - position.entry_price) * quantity
        else:
            raw_price = reference_price * (ONE + position.slippage_ratio)
            price = raw_price.quantize(position.tick_size, rounding=ROUND_UP)
            gross_pnl = (position.entry_price - price) * quantity
        exit_fee = price * quantity * position.fee_ratio
        liquidation_fee = (
            price * quantity * position.liquidation_fee_ratio
            if reason is BacktestExitReason.LIQUIDATION
            else ZERO
        )
        allocated_entry_fee = (
            position.entry_fee_usdt * quantity / position.initial_quantity
        )
        slippage_cost = abs(price - reference_price) * quantity
        return VirtualPositionExit(
            timestamp=timestamp,
            reason=reason,
            price=price,
            quantity=quantity,
            fee_usdt=exit_fee + liquidation_fee,
            net_pnl_usdt=(gross_pnl - exit_fee - liquidation_fee - allocated_entry_fee),
            slippage_cost_usdt=slippage_cost,
        )

    @staticmethod
    def _futures_trailing_stop(
        position: VirtualManagedPosition,
        *,
        candle: OHLCVCandle,
        maximum_favorable_excursion_usdt: Decimal,
    ) -> Decimal:
        trailing = position.trailing_stop
        if VirtualMarketRuntime._breakeven_trigger_reached(
            position,
            maximum_favorable_excursion_usdt=maximum_favorable_excursion_usdt,
        ):
            trailing = (
                max(trailing, position.entry_price)
                if position.position_side is VirtualPositionSide.LONG
                else min(trailing, position.entry_price)
            )
        if position.trailing_atr_multiple is None:
            return trailing
        distance = position.atr * position.trailing_atr_multiple
        if position.position_side is VirtualPositionSide.LONG:
            return max(trailing, candle.close - distance)
        return min(trailing, candle.close + distance)

    @staticmethod
    def _futures_portfolio_after_position_update(
        *,
        portfolio: VirtualPortfolioState,
        position_before: VirtualManagedPosition,
        position_after: VirtualManagedPosition,
        mark_price: Decimal,
        funding_delta: Decimal,
    ) -> VirtualPortfolioState:
        new_exits = position_after.exits[len(position_before.exits) :]
        cash_usdt = portfolio.cash_usdt - funding_delta
        realized_pnl_delta = -funding_delta
        fee_delta = ZERO
        slippage_delta = ZERO
        for exit_event in new_exits:
            direction_sign = (
                ONE
                if position_before.position_side is VirtualPositionSide.LONG
                else -ONE
            )
            gross_price_pnl = (
                (exit_event.price - position_before.entry_price)
                * exit_event.quantity
                * direction_sign
            )
            margin_release = (
                cast(Decimal, position_before.isolated_margin_usdt)
                * exit_event.quantity
                / position_before.initial_quantity
            )
            cash_usdt += margin_release + gross_price_pnl - exit_event.fee_usdt
            realized_pnl_delta += exit_event.net_pnl_usdt
            fee_delta += exit_event.fee_usdt
            slippage_delta += exit_event.slippage_cost_usdt
        remaining_ratio = (
            ZERO
            if position_after.remaining_quantity == ZERO
            else position_after.remaining_quantity / position_before.initial_quantity
        )
        isolated_margin = (
            cast(Decimal, position_before.isolated_margin_usdt) * remaining_ratio
        )
        initial_margin = (
            cast(Decimal, position_before.initial_margin_usdt) * remaining_ratio
        )
        notional = mark_price * position_after.remaining_quantity
        maintenance_margin = notional * cast(
            Decimal, position_before.maintenance_margin_ratio
        )
        if position_before.position_side is VirtualPositionSide.LONG:
            unrealized_pnl = (
                mark_price - position_before.entry_price
            ) * position_after.remaining_quantity
        else:
            unrealized_pnl = (
                position_before.entry_price - mark_price
            ) * position_after.remaining_quantity
        equity_usdt = cash_usdt + isolated_margin + unrealized_pnl
        high_watermark = max(
            portfolio.high_watermark_usdt or portfolio.equity_usdt,
            equity_usdt,
        )
        drawdown = (
            (high_watermark - equity_usdt) / high_watermark
            if high_watermark > ZERO
            else ZERO
        )
        closed = position_after.status is VirtualPositionLifecycleStatus.CLOSED
        margin_utilization = (
            min(ONE, isolated_margin / equity_usdt)
            if not closed and equity_usdt > ZERO
            else None
        )
        return replace(
            portfolio,
            cash_usdt=cash_usdt,
            equity_usdt=equity_usdt,
            realized_pnl_usdt=portfolio.realized_pnl_usdt + realized_pnl_delta,
            unrealized_pnl_usdt=unrealized_pnl,
            fees_paid_usdt=portfolio.fees_paid_usdt + fee_delta,
            slippage_cost_usdt=portfolio.slippage_cost_usdt + slippage_delta,
            funding_cost_usdt=portfolio.funding_cost_usdt + funding_delta,
            high_watermark_usdt=high_watermark,
            max_drawdown_ratio=max(portfolio.max_drawdown_ratio, drawdown),
            current_open_risk_usdt=(
                ZERO
                if closed
                else abs(position_before.entry_price - position_before.stop_loss)
                * position_after.remaining_quantity
            ),
            position_side=None if closed else position_before.position_side,
            position_entry_price=None if closed else position_before.entry_price,
            position_mark_price=None if closed else mark_price,
            position_notional_usdt=None if closed else notional,
            isolated_margin_usdt=None if closed else isolated_margin,
            initial_margin_usdt=None if closed else initial_margin,
            maintenance_margin_usdt=None if closed else maintenance_margin,
            liquidation_price=(None if closed else position_before.liquidation_price),
            leverage=None if closed else position_before.leverage,
            margin_utilization_ratio=margin_utilization,
            open_position_count=0 if closed else portfolio.open_position_count,
            consecutive_losses=(
                portfolio.consecutive_losses + 1
                if closed and position_after.realized_pnl_usdt < ZERO
                else 0
                if closed
                else portfolio.consecutive_losses
            ),
        )

    @staticmethod
    def _portfolio_blockers(
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> tuple[str, ...]:
        return build_virtual_portfolio_blockers(request, fill_preview)

    def _portfolio_after_fill(
        self,
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> VirtualPortfolioState:
        if request.portfolio.market != "SPOT":
            return self._futures_portfolio_after_fill(request, fill_preview)
        return self._spot_portfolio_after_fill(request, fill_preview)

    @staticmethod
    def _fill_preview(request: VirtualRuntimeRequest) -> VirtualFillPreview:
        return cast(VirtualFillPreview, build_virtual_fill_preview(request))

    @staticmethod
    def _futures_blockers(
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if request.position_side is None:
            blockers.append("FUTURES_POSITION_SIDE_REQUIRED")
            return tuple(blockers)
        if request.mark_price is None:
            blockers.append("FUTURES_MARK_PRICE_UNAVAILABLE")
        if request.funding_rate is None:
            blockers.append("FUNDING_DATA_UNAVAILABLE")
        leverage = request.leverage
        if leverage is None:
            blockers.append("FUTURES_LEVERAGE_UNAVAILABLE")
        if request.isolated_margin_usdt is None:
            blockers.append("FUTURES_ISOLATED_MARGIN_UNAVAILABLE")
        maintenance_margin_ratio = request.maintenance_margin_ratio
        if maintenance_margin_ratio is None:
            blockers.append("FUTURES_MAINTENANCE_MARGIN_UNAVAILABLE")
        if blockers:
            return tuple(blockers)
        isolated_margin_usdt = cast(Decimal, request.isolated_margin_usdt)
        leverage = cast(int, leverage)
        maintenance_margin_ratio = cast(Decimal, maintenance_margin_ratio)
        if request.position_side is VirtualPositionSide.LONG:
            if request.stop_loss >= fill_preview.execution_price or any(
                target <= fill_preview.execution_price
                for target in request.take_profit_levels
            ):
                blockers.append("FUTURES_LONG_GEOMETRY_INVALID")
        else:
            if request.stop_loss <= fill_preview.execution_price or any(
                target >= fill_preview.execution_price
                for target in request.take_profit_levels
            ):
                blockers.append("FUTURES_SHORT_GEOMETRY_INVALID")
        initial_margin = fill_preview.gross_notional_usdt / Decimal(leverage)
        if isolated_margin_usdt < initial_margin:
            blockers.append("INSUFFICIENT_VIRTUAL_MARGIN")
        maintenance_margin = fill_preview.gross_notional_usdt * maintenance_margin_ratio
        if isolated_margin_usdt <= maintenance_margin:
            blockers.append("LIQUIDATION_BUFFER_INSUFFICIENT")
        return tuple(blockers)

    @staticmethod
    def _spot_portfolio_after_fill(
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> VirtualPortfolioState:
        portfolio = request.portfolio
        realized_pnl_delta = ZERO
        inventory_quantity = portfolio.inventory_quantity
        inventory_cost_basis = portfolio.inventory_cost_basis_usdt
        cash_usdt = portfolio.cash_usdt
        open_position_count = portfolio.open_position_count

        if request.action is Action.BUY:
            cash_usdt -= fill_preview.gross_notional_usdt + fill_preview.fee_usdt
            inventory_quantity += fill_preview.filled_quantity
            inventory_cost_basis += fill_preview.gross_notional_usdt
            open_position_count += 1
        else:
            average_cost = (
                inventory_cost_basis / inventory_quantity
                if inventory_quantity > ZERO
                else ZERO
            )
            released_cost_basis = average_cost * fill_preview.filled_quantity
            proceeds = fill_preview.gross_notional_usdt - fill_preview.fee_usdt
            cash_usdt += proceeds
            inventory_quantity -= fill_preview.filled_quantity
            inventory_cost_basis -= released_cost_basis
            realized_pnl_delta = proceeds - released_cost_basis
            if inventory_quantity == ZERO:
                inventory_cost_basis = ZERO
                open_position_count = max(0, open_position_count - 1)

        mark_value = inventory_quantity * fill_preview.execution_price
        unrealized_pnl = mark_value - inventory_cost_basis
        equity_usdt = cash_usdt + mark_value
        high_watermark = max(
            portfolio.high_watermark_usdt or portfolio.equity_usdt, equity_usdt
        )
        drawdown = ZERO
        if high_watermark > ZERO:
            drawdown = (high_watermark - equity_usdt) / high_watermark
        return replace(
            portfolio,
            cash_usdt=cash_usdt,
            equity_usdt=equity_usdt,
            inventory_quantity=inventory_quantity,
            inventory_cost_basis_usdt=inventory_cost_basis,
            realized_pnl_usdt=portfolio.realized_pnl_usdt + realized_pnl_delta,
            unrealized_pnl_usdt=unrealized_pnl,
            fees_paid_usdt=portfolio.fees_paid_usdt + fill_preview.fee_usdt,
            slippage_cost_usdt=(
                portfolio.slippage_cost_usdt + fill_preview.slippage_cost_usdt
            ),
            high_watermark_usdt=high_watermark,
            max_drawdown_ratio=max(portfolio.max_drawdown_ratio, drawdown),
            current_open_risk_usdt=max(
                fill_preview.filled_quantity
                * max(fill_preview.execution_price - request.stop_loss, ZERO),
                ZERO,
            ),
            open_position_count=open_position_count,
        )

    @staticmethod
    def _futures_portfolio_after_fill(
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> VirtualPortfolioState:
        portfolio = request.portfolio
        position_side = cast(VirtualPositionSide, request.position_side)
        mark_price = cast(Decimal, request.mark_price)
        leverage = cast(int, request.leverage)
        isolated_margin = cast(Decimal, request.isolated_margin_usdt)
        maintenance_margin_ratio = cast(Decimal, request.maintenance_margin_ratio)
        funding_rate = cast(Decimal, request.funding_rate)
        notional = fill_preview.gross_notional_usdt
        initial_margin = notional / Decimal(leverage)
        maintenance_margin = notional * maintenance_margin_ratio
        if position_side is VirtualPositionSide.LONG:
            unrealized_pnl = (
                mark_price - fill_preview.execution_price
            ) * fill_preview.filled_quantity
            liquidation_price = fill_preview.execution_price - (
                (isolated_margin - maintenance_margin) / fill_preview.filled_quantity
            )
            funding_cost = (
                notional * funding_rate if request.funding_payment_due else ZERO
            )
        else:
            unrealized_pnl = (
                fill_preview.execution_price - mark_price
            ) * fill_preview.filled_quantity
            liquidation_price = fill_preview.execution_price + (
                (isolated_margin - maintenance_margin) / fill_preview.filled_quantity
            )
            funding_cost = (
                -notional * funding_rate if request.funding_payment_due else ZERO
            )
        available_cash = (
            portfolio.cash_usdt - isolated_margin - fill_preview.fee_usdt - funding_cost
        )
        equity_usdt = available_cash + isolated_margin + unrealized_pnl
        high_watermark = max(
            portfolio.high_watermark_usdt or portfolio.equity_usdt,
            equity_usdt,
        )
        drawdown = ZERO
        if high_watermark > ZERO:
            drawdown = (high_watermark - equity_usdt) / high_watermark
        margin_utilization = ZERO
        if equity_usdt > ZERO:
            margin_utilization = min(ONE, isolated_margin / equity_usdt)
        return replace(
            portfolio,
            cash_usdt=available_cash,
            equity_usdt=equity_usdt,
            realized_pnl_usdt=portfolio.realized_pnl_usdt - funding_cost,
            unrealized_pnl_usdt=unrealized_pnl,
            fees_paid_usdt=portfolio.fees_paid_usdt + fill_preview.fee_usdt,
            slippage_cost_usdt=(
                portfolio.slippage_cost_usdt + fill_preview.slippage_cost_usdt
            ),
            funding_cost_usdt=portfolio.funding_cost_usdt + funding_cost,
            high_watermark_usdt=high_watermark,
            max_drawdown_ratio=max(portfolio.max_drawdown_ratio, drawdown),
            current_open_risk_usdt=abs(fill_preview.execution_price - request.stop_loss)
            * fill_preview.filled_quantity,
            position_side=position_side,
            position_entry_price=fill_preview.execution_price,
            position_mark_price=mark_price,
            position_notional_usdt=notional,
            isolated_margin_usdt=isolated_margin,
            initial_margin_usdt=initial_margin,
            maintenance_margin_usdt=maintenance_margin,
            liquidation_price=liquidation_price,
            leverage=leverage,
            margin_utilization_ratio=margin_utilization,
            open_position_count=1,
        )

    @staticmethod
    def _round_quantity(quantity: Decimal, *, step_size: Decimal) -> Decimal:
        return quantity.quantize(step_size, rounding=ROUND_DOWN)

    @staticmethod
    def _round_price(
        price: Decimal,
        *,
        tick_size: Decimal,
        action: Action,
    ) -> Decimal:
        rounding = ROUND_UP if action is Action.BUY else ROUND_DOWN
        return price.quantize(tick_size, rounding=rounding)

    @staticmethod
    def calculate_portfolio_performance(
        *,
        market: str,
        equity_curve: tuple[DailyEquityPoint, ...],
    ) -> VirtualPortfolioPerformance:
        metrics = calculate_virtual_portfolio_performance_metrics(
            market=market,
            equity_curve=cast(Sequence[EquityObservation], equity_curve),
        )
        return VirtualPortfolioPerformance(
            market=metrics.market,
            starting_equity_usdt=metrics.starting_equity_usdt,
            ending_equity_usdt=metrics.ending_equity_usdt,
            observation_count=metrics.observation_count,
            sample_period_seconds=metrics.sample_period_seconds,
            net_return=metrics.net_return,
            annualized_return=metrics.annualized_return,
            max_drawdown=metrics.max_drawdown,
            portfolio_sharpe=metrics.portfolio_sharpe,
            portfolio_sortino=metrics.portfolio_sortino,
        )

    @staticmethod
    def _default_current_exposures(
        portfolio: VirtualPortfolioState,
        *,
        request: VirtualRuntimeRequest,
    ) -> tuple[PositionExposure, ...]:
        if portfolio.market == "SPOT" and portfolio.inventory_quantity > ZERO:
            return (
                PositionExposure(
                    symbol=request.symbol,
                    strategy_id=request.strategy_id,
                    correlation_group=request.correlation_group,
                    notional_usdt=portfolio.inventory_quantity
                    * (
                        portfolio.position_entry_price
                        or (
                            portfolio.inventory_cost_basis_usdt
                            / portfolio.inventory_quantity
                        )
                    ),
                ),
            )
        if (
            portfolio.market == "USD_M_FUTURES"
            and portfolio.position_notional_usdt is not None
            and portfolio.open_position_count > 0
        ):
            return (
                PositionExposure(
                    symbol=request.symbol,
                    strategy_id=request.strategy_id,
                    correlation_group=request.correlation_group,
                    notional_usdt=portfolio.position_notional_usdt,
                ),
            )
        return ()

    @staticmethod
    def _proposed_risk_usdt(
        request: VirtualRuntimeRequest,
        fill_preview: VirtualFillPreview,
    ) -> Decimal:
        if request.portfolio.market == "USD_M_FUTURES":
            return (
                abs(fill_preview.execution_price - request.stop_loss)
                * fill_preview.filled_quantity
            )
        return (
            max(fill_preview.execution_price - request.stop_loss, ZERO)
            * fill_preview.filled_quantity
        )

    @staticmethod
    def materialize_managed_position(
        *,
        request: VirtualRuntimeRequest,
        decision: VirtualRuntimeDecision,
        opened_at: datetime,
        position_id: str | None = None,
    ) -> VirtualManagedPosition:
        if decision.status is not VirtualRuntimeDecisionStatus.ORDER_READY:
            raise ValueError(
                "managed position requires an ORDER_READY virtual runtime decision"
            )
        intent = decision.trade_intent
        if intent is None:
            raise ValueError(
                "ORDER_READY virtual runtime decision requires trade intent"
            )
        if opened_at.tzinfo is None or opened_at.utcoffset() is None:
            raise ValueError("managed position timestamp must be timezone-aware")
        entry_slippage = abs(intent.entry_price - request.entry_price) * intent.quantity
        funding_cost = (
            decision.portfolio_after.funding_cost_usdt
            - request.portfolio.funding_cost_usdt
        )
        return VirtualManagedPosition(
            position_id=position_id or f"virtual-position:{request.candidate_id}",
            candidate_id=request.candidate_id,
            symbol=request.symbol,
            market=request.market,
            opened_at=opened_at,
            entry_price=intent.entry_price,
            entry_fee_usdt=(
                decision.portfolio_after.fees_paid_usdt
                - request.portfolio.fees_paid_usdt
            ),
            initial_quantity=intent.quantity,
            remaining_quantity=intent.quantity,
            stop_loss=request.stop_loss,
            trailing_stop=request.stop_loss,
            atr=abs(intent.entry_price - request.stop_loss),
            take_profit_levels=request.take_profit_levels,
            opportunity_id=request.opportunity_id,
            fee_ratio=request.fee_ratio,
            slippage_ratio=request.slippage_ratio,
            tick_size=request.tick_size,
            position_side=request.position_side or VirtualPositionSide.LONG,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            strategy_config_version=request.strategy_config_version,
            strategy_config_hash=request.strategy_config_hash,
            regime=request.regime,
            timeframe=request.timeframe,
            snapshot_id=request.snapshot_id,
            decision_id=request.decision_id,
            dge_decision=request.dge_decision,
            risk_policy_version=request.risk_policy_version,
            validation_version=request.validation_version,
            entry_reason=request.entry_reason,
            entry_slippage_cost_usdt=entry_slippage,
            funding_cost_usdt=funding_cost,
            realized_pnl_usdt=-funding_cost,
            isolated_margin_usdt=decision.portfolio_after.isolated_margin_usdt,
            initial_margin_usdt=decision.portfolio_after.initial_margin_usdt,
            maintenance_margin_ratio=request.maintenance_margin_ratio,
            liquidation_price=decision.portfolio_after.liquidation_price,
            leverage=decision.portfolio_after.leverage,
            liquidation_fee_ratio=request.liquidation_fee_ratio,
        )

    @staticmethod
    def _lifecycle_position(position: VirtualManagedPosition) -> LifecyclePosition:
        from ai4binance.execution.lifecycle import (
            LifecycleExit,
            LifecyclePosition,
            PositionStatus,
            StagedExitPlan,
        )

        return LifecyclePosition(
            position_id=position.position_id,
            candidate_id=position.candidate_id,
            symbol=position.symbol,
            opened_at=position.opened_at,
            entry_price=position.entry_price,
            entry_fee_usdt=position.entry_fee_usdt,
            initial_quantity=position.initial_quantity,
            remaining_quantity=position.remaining_quantity,
            stop_loss=position.stop_loss,
            trailing_stop=position.trailing_stop,
            atr=position.atr,
            plan=StagedExitPlan(
                targets=tuple(sorted(position.take_profit_levels)),
                quantity_ratios=position.take_profit_quantity_ratios,
            ),
            status=PositionStatus(position.status.value),
            next_target_index=position.next_target_index,
            realized_pnl_usdt=position.realized_pnl_usdt,
            exits=tuple(
                LifecycleExit(
                    timestamp=exit.timestamp,
                    reason=_paper_exit_reason(exit.reason),
                    price=exit.price,
                    quantity=exit.quantity,
                    fee_usdt=exit.fee_usdt,
                    net_pnl_usdt=exit.net_pnl_usdt,
                )
                for exit in position.exits
            ),
            closure_review=(
                None
                if position.closure_review is None
                else _paper_closure_review(position.closure_review)
            ),
        )

    @staticmethod
    def _managed_position_from_lifecycle(
        *,
        original: VirtualManagedPosition,
        lifecycle: LifecyclePosition,
        bars_held: int,
        maximum_favorable_excursion_usdt: Decimal,
        reason_override: BacktestExitReason | None = None,
    ) -> VirtualManagedPosition:
        from ai4binance.execution.lifecycle import PositionStatus

        exits = tuple(_virtual_exit(exit) for exit in lifecycle.exits)
        review = (
            None
            if lifecycle.closure_review is None
            else _virtual_closure_review(lifecycle.closure_review)
        )
        if reason_override is not None and review is not None and exits:
            review = replace(review, exit_reason=reason_override)
            exits = (*exits[:-1], replace(exits[-1], reason=reason_override))
        elif (
            review is not None
            and lifecycle.status is PositionStatus.CLOSED
            and exits
            and exits[-1].reason is not review.exit_reason
        ):
            exits = (
                *exits[:-1],
                replace(exits[-1], reason=review.exit_reason),
            )
        return replace(
            original,
            remaining_quantity=lifecycle.remaining_quantity,
            trailing_stop=lifecycle.trailing_stop,
            status=VirtualPositionLifecycleStatus(lifecycle.status.value),
            next_target_index=lifecycle.next_target_index,
            realized_pnl_usdt=lifecycle.realized_pnl_usdt,
            exits=exits,
            closure_review=review,
            bars_held=bars_held,
            maximum_favorable_excursion_usdt=maximum_favorable_excursion_usdt,
        )

    @staticmethod
    def _breakeven_trigger_reached(
        position: VirtualManagedPosition,
        *,
        maximum_favorable_excursion_usdt: Decimal,
    ) -> bool:
        trigger = position.breakeven_trigger_r
        if trigger is None:
            return False
        initial_risk = abs(position.entry_price - position.stop_loss) * (
            position.initial_quantity
        )
        if initial_risk <= ZERO:
            return False
        return maximum_favorable_excursion_usdt >= initial_risk * trigger

    @staticmethod
    def _forced_exit_reason(
        context: VirtualExitContext,
    ) -> BacktestExitReason | None:
        if context.structure_invalidation:
            return BacktestExitReason.STRUCTURE_INVALIDATION
        if context.regime_failure:
            return BacktestExitReason.REGIME_EXIT
        if context.momentum_failure:
            return BacktestExitReason.MOMENTUM_FAILURE
        return None

    @staticmethod
    def _close_lifecycle_remaining(
        position: LifecyclePosition,
        *,
        timestamp: datetime,
        reason: BacktestExitReason,
        reference_price: Decimal,
        context: VirtualExitContext,
        fee_ratio: Decimal,
        slippage_ratio: Decimal,
    ) -> LifecyclePosition:
        from ai4binance.execution.lifecycle import LifecycleExit, PositionStatus
        from ai4binance.execution.paper import ExitReason

        quantity = position.remaining_quantity
        price = reference_price * (ONE - slippage_ratio)
        fee = price * quantity * fee_ratio
        allocated_entry_fee = (
            position.entry_fee_usdt * quantity / position.initial_quantity
        )
        pnl = (price - position.entry_price) * quantity - fee - allocated_entry_fee
        review = _virtual_review(
            reason=reason,
            context=context,
            staged_exit_used=bool(position.exits),
        )
        return replace(
            position,
            remaining_quantity=ZERO,
            status=PositionStatus.CLOSED,
            realized_pnl_usdt=position.realized_pnl_usdt + pnl,
            exits=(
                *position.exits,
                LifecycleExit(
                    timestamp=timestamp,
                    reason=ExitReason.TAKE_PROFIT_EXIT,
                    price=price,
                    quantity=quantity,
                    fee_usdt=fee,
                    net_pnl_usdt=pnl,
                ),
            ),
            closure_review=_paper_closure_review(review),
        )

    @staticmethod
    def _spot_portfolio_after_position_update(
        *,
        portfolio: VirtualPortfolioState,
        position_before: VirtualManagedPosition,
        position_after: VirtualManagedPosition,
        mark_price: Decimal,
    ) -> VirtualPortfolioState:
        new_exits = position_after.exits[len(position_before.exits) :]
        cash_usdt = portfolio.cash_usdt
        inventory_quantity = portfolio.inventory_quantity
        inventory_cost_basis = portfolio.inventory_cost_basis_usdt
        realized_pnl_delta = ZERO
        fee_delta = ZERO
        for exit in new_exits:
            proceeds = exit.price * exit.quantity - exit.fee_usdt
            cash_usdt += proceeds
            inventory_quantity -= exit.quantity
            inventory_cost_basis -= position_before.entry_price * exit.quantity
            realized_pnl_delta += exit.net_pnl_usdt
            fee_delta += exit.fee_usdt
        if inventory_quantity == ZERO:
            inventory_cost_basis = ZERO
        mark_value = inventory_quantity * mark_price
        unrealized_pnl = mark_value - inventory_cost_basis
        equity_usdt = cash_usdt + mark_value
        high_watermark = max(
            portfolio.high_watermark_usdt or portfolio.equity_usdt, equity_usdt
        )
        drawdown = ZERO
        if high_watermark > ZERO:
            drawdown = (high_watermark - equity_usdt) / high_watermark
        return replace(
            portfolio,
            cash_usdt=cash_usdt,
            equity_usdt=equity_usdt,
            inventory_quantity=inventory_quantity,
            inventory_cost_basis_usdt=max(inventory_cost_basis, ZERO),
            realized_pnl_usdt=portfolio.realized_pnl_usdt + realized_pnl_delta,
            unrealized_pnl_usdt=unrealized_pnl,
            fees_paid_usdt=portfolio.fees_paid_usdt + fee_delta,
            high_watermark_usdt=high_watermark,
            max_drawdown_ratio=max(portfolio.max_drawdown_ratio, drawdown),
            current_open_risk_usdt=max(
                position_after.remaining_quantity
                * max(position_after.entry_price - position_after.stop_loss, ZERO),
                ZERO,
            ),
            consecutive_losses=(
                portfolio.consecutive_losses + 1
                if position_after.status is VirtualPositionLifecycleStatus.CLOSED
                and position_after.realized_pnl_usdt < ZERO
                else (
                    0
                    if position_after.status is VirtualPositionLifecycleStatus.CLOSED
                    else portfolio.consecutive_losses
                )
            ),
            open_position_count=(
                0
                if position_after.status is VirtualPositionLifecycleStatus.CLOSED
                else portfolio.open_position_count
            ),
        )

    @staticmethod
    def _closed_trade_record(
        position_before: VirtualManagedPosition,
        position_after: VirtualManagedPosition,
    ) -> VirtualClosedTradeRecord:
        exits = position_after.exits
        last_exit = exits[-1]
        quantity = position_before.initial_quantity
        direction_sign = (
            ONE if position_before.position_side is VirtualPositionSide.LONG else -ONE
        )
        execution_pnl = sum(
            (
                (exit.price - position_before.entry_price)
                * exit.quantity
                * direction_sign
                for exit in exits
            ),
            ZERO,
        )
        total_exit_fees = sum((exit.fee_usdt for exit in exits), ZERO)
        total_fees = position_before.entry_fee_usdt + total_exit_fees
        total_slippage = position_before.entry_slippage_cost_usdt + sum(
            (exit.slippage_cost_usdt for exit in exits),
            ZERO,
        )
        gross_pnl = execution_pnl + total_slippage
        risk_at_entry = quantity * abs(
            position_before.entry_price - position_before.stop_loss
        )
        realized_r = (
            ZERO
            if risk_at_entry <= ZERO
            else position_after.realized_pnl_usdt / risk_at_entry
        )
        protective_exit = last_exit.reason in {
            BacktestExitReason.HARD_STOP,
            BacktestExitReason.TRAILING_STOP,
        }
        false_breakout = protective_exit and any(
            "BREAKOUT" in code for code in position_before.entry_reason
        )
        return VirtualClosedTradeRecord(
            trade_id=position_before.position_id,
            attribution=ClosedTradeAttribution(
                strategy_id=position_before.strategy_id,
                strategy_version=position_before.strategy_version,
                strategy_config_version=position_before.strategy_config_version,
                strategy_config_hash=position_before.strategy_config_hash,
                market=position_before.market,
                symbol=position_before.symbol,
                regime=position_before.regime,
                timeframe=position_before.timeframe,
                snapshot_id=position_before.snapshot_id,
                decision_id=position_before.decision_id,
                opportunity_id=position_before.opportunity_id,
            ),
            direction=TradeDirection(position_before.position_side.value),
            entry_time=position_before.opened_at,
            exit_time=last_exit.timestamp,
            entry_price=position_before.entry_price,
            exit_price=last_exit.price,
            quantity=quantity,
            risk_at_entry=risk_at_entry,
            entry_reason=position_before.entry_reason,
            exit_reason=last_exit.reason,
            dge_decision=position_before.dge_decision,
            risk_policy_version=position_before.risk_policy_version,
            validation_version=position_before.validation_version,
            gross_pnl_usdt=gross_pnl,
            fee_cost_usdt=total_fees,
            slippage_cost_usdt=total_slippage,
            funding_cost_usdt=position_after.funding_cost_usdt,
            net_pnl_usdt=position_after.realized_pnl_usdt,
            realized_r_multiple=realized_r,
            maximum_favorable_excursion=position_after.maximum_favorable_excursion_usdt,
            maximum_adverse_excursion=(
                position_after.maximum_adverse_excursion_usdt
                or abs(position_before.entry_price - position_before.stop_loss)
                * quantity
            ),
            false_breakout=false_breakout,
        )

    @staticmethod
    def build_trade_attribution_ledger(
        closed_trades: tuple[VirtualClosedTradeRecord, ...],
    ) -> VirtualTradeAttributionLedger:
        return build_virtual_trade_attribution_ledger(closed_trades)

    @staticmethod
    def build_research_evidence_surface(
        *,
        session_id: str,
        portfolio_id: str,
        generation: int,
        configured_start_at: datetime,
        feature_warmup_start: datetime,
        last_replayed_at: datetime,
        market: str,
        timeframe: str,
        portfolio_performance: VirtualPortfolioPerformance,
        attribution_ledger: VirtualTradeAttributionLedger,
        walk_forward_report: WalkForwardReport | None,
        robustness_report: BacktestRobustnessReport | None,
        dge_metrics: DgeEffectivenessMetrics,
        replay_state_hash: str,
        observed_at: datetime,
        peak_margin_utilization: Decimal | None = None,
        critical_data_gaps: int = 0,
        critical_data_quality_failure: bool = False,
        applied_duplicate_economic_events: int = 0,
        lookahead_violations: int = 0,
        liquidation_events: int = 0,
        decision_reproducibility_rate: Decimal = ONE,
        evidence_blockers: tuple[str, ...] = (),
    ) -> VirtualResearchEvidenceSurface:
        _require_unique_nonblank_or_empty(
            "virtual research evidence blockers",
            evidence_blockers,
        )
        market_evidence = VirtualMarketRuntime._market_performance_evidence(
            session_id=session_id,
            portfolio_id=portfolio_id,
            generation=generation,
            configured_start_at=configured_start_at,
            feature_warmup_start=feature_warmup_start,
            last_replayed_at=last_replayed_at,
            market=market,
            timeframe=timeframe,
            portfolio_performance=portfolio_performance,
            attribution_ledger=attribution_ledger,
            walk_forward_report=walk_forward_report,
            robustness_report=robustness_report,
            replay_state_hash=replay_state_hash,
            peak_margin_utilization=peak_margin_utilization,
            critical_data_gaps=critical_data_gaps,
            critical_data_quality_failure=critical_data_quality_failure,
            applied_duplicate_economic_events=applied_duplicate_economic_events,
            lookahead_violations=lookahead_violations,
            liquidation_events=liquidation_events,
            decision_reproducibility_rate=decision_reproducibility_rate,
        )
        profitability_evidence = evaluate_two_stage_profitability_evidence(
            market_evidence
        )
        improvement_candidates = VirtualMarketRuntime._improvement_candidates(
            attribution_ledger=attribution_ledger,
            market=market,
            snapshot_id=session_id,
            modeled_cost_expectancy_usdt=market_evidence.modeled_cost_expectancy_usdt,
            oos_expectancy_usdt=market_evidence.oos_expectancy_usdt,
            walk_forward_report=walk_forward_report,
            robustness_report=robustness_report,
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *profitability_evidence.research_candidate.blockers,
                    *profitability_evidence.final_acceptance.blockers,
                    *getattr(walk_forward_report, "blockers", ()),
                    *getattr(robustness_report, "blockers", ()),
                    *evidence_blockers,
                )
            )
        )
        snapshot = build_performance_evidence_snapshot(
            decision_input=DecisionInputRecord(
                cycle_id=f"cycle:{session_id}",
                snapshot_id=session_id,
                observed_at=observed_at,
                source_data_ids=(replay_state_hash,),
                feature_versions={"timeframe": timeframe},
                evidence_ids=tuple(
                    dict.fromkeys(
                        (
                            replay_state_hash,
                            session_id,
                            getattr(walk_forward_report, "report_id", "WF_MISSING"),
                            *(
                                result.scenario.name
                                for result in getattr(
                                    robustness_report, "stress_results", ()
                                )
                            ),
                        )
                    )
                ),
                policy_versions={
                    "research_acceptance": profitability_evidence.final_acceptance.policy_id,
                },
            ),
            decision_process=DecisionProcessRecord(
                decision_id=session_id,
                risk_assessment_id=f"risk:{session_id}",
                validation_id=f"validation:{session_id}",
                governance_evidence_ids=tuple(
                    dict.fromkeys(
                        (
                            profitability_evidence.research_candidate.policy_id,
                            profitability_evidence.final_acceptance.policy_id,
                            getattr(walk_forward_report, "report_id", "WF_MISSING"),
                        )
                    )
                ),
                advisory_signal_refs=tuple(
                    trade.trade_id for trade in attribution_ledger.closed_trades
                )
                or (f"virtual:{portfolio_id}",),
                blockers=blockers,
                decision_state="VIRTUAL_RESEARCH",
            ),
            decision_outcome=DecisionOutcomeRecord(
                outcome_id=f"outcome:{session_id}",
                decision_id=session_id,
                observed_at=observed_at,
                decision_state="VIRTUAL_RESEARCH",
                execution_status="VIRTUAL_EVIDENCE_SURFACED",
                observation_window_minutes=max(
                    1,
                    int((last_replayed_at - configured_start_at).total_seconds() / 60),
                ),
                realized_pnl_usdt=(
                    portfolio_performance.ending_equity_usdt
                    - portfolio_performance.starting_equity_usdt
                ),
                max_favorable_move_usdt=max(
                    (
                        trade.maximum_favorable_excursion
                        for trade in attribution_ledger.closed_trades
                    ),
                    default=ZERO,
                ),
                max_adverse_move_usdt=max(
                    (
                        trade.maximum_adverse_excursion
                        for trade in attribution_ledger.closed_trades
                    ),
                    default=ZERO,
                ),
                counterfactual_return_usdt=dge_metrics.counterfactual_expectancy_delta_usdt,
                no_trade_reason="DGE virtual counterfactual effectiveness snapshot.",
            ),
            dge_metrics=dge_metrics,
            counterfactuals=VirtualMarketRuntime._dge_counterfactuals(
                session_id=session_id,
                blockers=blockers,
                observed_at=observed_at,
                dge_metrics=dge_metrics,
            ),
            attributions=VirtualMarketRuntime._outcome_attributions(
                session_id=session_id,
                market=market,
                attribution_ledger=attribution_ledger,
                dge_metrics=dge_metrics,
            ),
            blocker_effectiveness=VirtualMarketRuntime._blocker_effectiveness_records(
                session_id=session_id,
                blockers=blockers,
                dge_metrics=dge_metrics,
            ),
            decision_effectiveness=VirtualMarketRuntime._decision_effectiveness_records(
                session_id=session_id,
                market=market,
                blockers=blockers,
                dge_metrics=dge_metrics,
            ),
            telemetry_snapshot=VirtualMarketRuntime._canonical_telemetry_snapshot(
                snapshot_id=session_id,
                observed_at=observed_at,
                market=market,
                market_evidence=market_evidence,
                attribution_ledger=attribution_ledger,
                dge_metrics=dge_metrics,
                blockers=blockers,
                gate_eligible=not blockers,
            ),
            acceptance_results=(
                VirtualMarketRuntime._acceptance_result(
                    snapshot_id=session_id,
                    market=market,
                    profitability_evidence=profitability_evidence,
                    walk_forward_report=walk_forward_report,
                    robustness_report=robustness_report,
                    blockers=blockers,
                ),
            ),
            improvement_candidates=improvement_candidates,
            observed_at=observed_at,
        )
        return VirtualResearchEvidenceSurface(
            attribution_ledger=attribution_ledger,
            market_performance=market_evidence,
            profitability_evidence=profitability_evidence,
            performance_snapshot=snapshot,
            improvement_candidates=improvement_candidates,
            blockers=blockers,
        )

    @staticmethod
    def build_no_trade_evidence_surface(
        *,
        session_id: str,
        request: VirtualRuntimeRequest,
        blockers: tuple[str, ...],
        observed_at: datetime,
        replay_state_hash: str,
        dge_metrics: DgeEffectivenessMetrics,
        counterfactual_trade: VirtualClosedTradeRecord | None = None,
    ) -> VirtualNoTradeEvidenceSurface:
        missed_opportunity = VirtualMarketRuntime._missed_opportunity_record(
            request=request,
            blockers=blockers,
            observed_at=observed_at,
            counterfactual_trade=counterfactual_trade,
        )
        ledger = MissedOpportunityLedger(records=(missed_opportunity,))
        improvement_candidates = VirtualMarketRuntime._missed_opportunity_candidates(
            session_id=session_id,
            market=request.market,
            missed_opportunity=missed_opportunity,
        )
        counterfactuals = VirtualMarketRuntime._no_trade_counterfactuals(
            session_id=session_id,
            blockers=blockers,
            missed_opportunity=missed_opportunity,
        )
        blocker_effectiveness = VirtualMarketRuntime._no_trade_blocker_effectiveness(
            session_id=session_id,
            blockers=blockers,
            missed_opportunity=missed_opportunity,
        )
        decision_effectiveness = VirtualMarketRuntime._no_trade_decision_effectiveness(
            session_id=session_id,
            market=request.market,
            missed_opportunity=missed_opportunity,
        )
        attributions = VirtualMarketRuntime._no_trade_attributions(
            session_id=session_id,
            market=request.market,
            missed_opportunity=missed_opportunity,
        )
        snapshot = build_performance_evidence_snapshot(
            decision_input=DecisionInputRecord(
                cycle_id=f"cycle:{session_id}",
                snapshot_id=session_id,
                observed_at=observed_at,
                source_data_ids=(replay_state_hash,),
                feature_versions={"timeframe": request.timeframe},
                evidence_ids=(replay_state_hash, session_id),
                policy_versions={
                    "risk": request.risk_policy_version,
                    "validation": request.validation_version,
                },
            ),
            decision_process=DecisionProcessRecord(
                decision_id=session_id,
                risk_assessment_id=f"risk:{session_id}",
                validation_id=f"validation:{session_id}",
                governance_evidence_ids=tuple(
                    dict.fromkeys(
                        (
                            request.risk_policy_version,
                            request.validation_version,
                            request.dge_decision,
                        )
                    )
                ),
                advisory_signal_refs=(request.candidate_id,),
                blockers=blockers,
                decision_state="NO_TRADE",
            ),
            decision_outcome=DecisionOutcomeRecord(
                outcome_id=f"outcome:{session_id}",
                decision_id=session_id,
                observed_at=observed_at,
                decision_state="NO_TRADE",
                execution_status="NO_ACTION",
                observation_window_minutes=60,
                realized_pnl_usdt=ZERO,
                max_favorable_move_usdt=(
                    counterfactual_trade.maximum_favorable_excursion
                    if counterfactual_trade is not None
                    else ZERO
                ),
                max_adverse_move_usdt=(
                    counterfactual_trade.maximum_adverse_excursion
                    if counterfactual_trade is not None
                    else ZERO
                ),
                counterfactual_return_usdt=(
                    counterfactual_trade.net_pnl_usdt
                    if counterfactual_trade is not None
                    else ZERO
                ),
                no_trade_reason=(
                    "NO_TRADE: " + ", ".join(blockers)
                    if blockers
                    else "NO_TRADE: blocker evidence unavailable."
                ),
            ),
            dge_metrics=dge_metrics,
            counterfactuals=counterfactuals,
            attributions=attributions,
            blocker_effectiveness=blocker_effectiveness,
            decision_effectiveness=decision_effectiveness,
            telemetry_snapshot=VirtualMarketRuntime._no_trade_telemetry_snapshot(
                snapshot_id=session_id,
                observed_at=observed_at,
                market=request.market,
                missed_opportunity=missed_opportunity,
                blockers=blockers,
            ),
            improvement_candidates=improvement_candidates,
            observed_at=observed_at,
        )
        return VirtualNoTradeEvidenceSurface(
            missed_opportunity_ledger=ledger,
            performance_snapshot=snapshot,
            improvement_candidates=improvement_candidates,
            blockers=blockers,
        )

    @staticmethod
    def adapt_evidence_surface(
        surface: VirtualResearchEvidenceSurface | VirtualNoTradeEvidenceSurface,
    ) -> VirtualEvidenceSurfaceAdapter:
        snapshot = surface.performance_snapshot
        telemetry = snapshot.telemetry_snapshot
        if telemetry is None:
            raise ValueError(
                "virtual evidence surface requires telemetry for adaptation"
            )
        if isinstance(surface, VirtualResearchEvidenceSurface):
            final_acceptance = surface.profitability_evidence.final_acceptance
            market_acceptance = MarketAcceptanceResult(
                market=final_acceptance.market,
                status=(
                    final_acceptance.status
                    if final_acceptance.status is not AcceptanceStatus.PASS
                    or not surface.blockers
                    else AcceptanceStatus.INSUFFICIENT_EVIDENCE
                ),
                blockers=surface.blockers,
                evidence_refs=final_acceptance.evidence_refs,
                policy_id=final_acceptance.policy_id,
            )
            return VirtualEvidenceSurfaceAdapter(
                surface_kind="RESEARCH",
                market=surface.market_performance.market.value,
                performance_snapshot=snapshot,
                telemetry_snapshot=telemetry,
                acceptance_results=snapshot.acceptance_results,
                improvement_candidates=surface.improvement_candidates,
                blockers=surface.blockers,
                market_acceptance_result=market_acceptance,
            )
        market_type = telemetry.market_type
        acceptance = VirtualMarketRuntime._no_trade_acceptance_result(
            snapshot=snapshot,
            market_type=market_type,
            blockers=surface.blockers,
        )
        return VirtualEvidenceSurfaceAdapter(
            surface_kind="NO_TRADE",
            market=telemetry.market_type.value,
            performance_snapshot=snapshot,
            telemetry_snapshot=telemetry,
            acceptance_results=(acceptance,),
            improvement_candidates=surface.improvement_candidates,
            blockers=surface.blockers,
        )

    @staticmethod
    def evidence_surface_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> dict[str, object]:
        snapshot = adapter.performance_snapshot
        gpu_telemetry_assessment = snapshot.gpu_telemetry_assessment
        telemetry_metric_summary = {
            metric.metric_id: {
                "value": str(metric.value),
                "unit": metric.unit,
            }
            for metric in adapter.telemetry_snapshot.metrics
        }
        return {
            "surface_kind": adapter.surface_kind,
            "market": adapter.market,
            "snapshot_id": adapter.snapshot_id,
            "status": snapshot.status.value,
            "telemetry_id": adapter.telemetry_snapshot.telemetry_id,
            "market_type": adapter.telemetry_snapshot.market_type.value,
            "telemetry_gate_eligible": adapter.telemetry_snapshot.gate_eligible,
            "telemetry_blockers": adapter.telemetry_snapshot.blockers,
            "telemetry_metric_summary": telemetry_metric_summary,
            "gpu_telemetry_assessment": (
                gpu_telemetry_assessment.to_payload()
                if gpu_telemetry_assessment is not None
                else None
            ),
            "acceptance_results": tuple(
                {
                    "result_id": result.result_id,
                    "status": result.status.value,
                    "gate_eligible": result.gate_eligible,
                    "blockers": result.blockers,
                }
                for result in adapter.acceptance_results
            ),
            "market_acceptance_result": (
                adapter.market_acceptance_result.to_payload()
                if adapter.market_acceptance_result is not None
                else None
            ),
            "acceptance_policy_id": (
                adapter.market_acceptance_result.policy_id
                if adapter.market_acceptance_result is not None
                else None
            ),
            "dge_effectiveness": snapshot.dge_metrics.to_payload(),
            "improvement_candidate_ids": tuple(
                candidate.candidate_id for candidate in adapter.improvement_candidates
            ),
            "blockers": adapter.blockers,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @staticmethod
    def render_evidence_surface_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        snapshot = adapter.performance_snapshot
        telemetry = adapter.telemetry_snapshot
        gpu_telemetry_assessment = snapshot.gpu_telemetry_assessment
        acceptance_lines = tuple(
            f"- `{result.result_id}`: `{result.status.value}`"
            for result in adapter.acceptance_results
        )
        telemetry_lines = tuple(
            f"- `{metric.metric_id}`: `{metric.value}` {metric.unit}"
            for metric in telemetry.metrics
        )
        gpu_lines = (
            (
                f"- Source: `{gpu_telemetry_assessment.source_label}`"
                if gpu_telemetry_assessment is not None
                else "- Source: `-`"
            ),
            (
                f"- Healthy: `{gpu_telemetry_assessment.healthy}`"
                if gpu_telemetry_assessment is not None
                else "- Healthy: `-`"
            ),
            (
                "- Blockers: `" + ", ".join(gpu_telemetry_assessment.blockers) + "`"
                if gpu_telemetry_assessment is not None
                else "- Blockers: `-`"
            ),
        )
        learning_lines = tuple(
            f"- `{candidate.candidate_id}`"
            for candidate in adapter.improvement_candidates
        )
        return render_professional_summary(
            title=f"Virtual Evidence Surface {adapter.surface_kind}",
            observed_at=snapshot.observed_at.isoformat(),
            status=snapshot.status.value,
            summary=(
                "This local virtual-evidence publication packages research or "
                "measurable NO_TRADE evidence for downstream consumers without "
                "granting execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Snapshot id: `{adapter.snapshot_id}`",
                        f"- Surface kind: `{adapter.surface_kind}`",
                        f"- Market: `{adapter.market}`",
                        f"- Telemetry id: `{telemetry.telemetry_id}`",
                    ),
                ),
                ("Acceptance", acceptance_lines),
                ("Telemetry", telemetry_lines),
                ("GPU Governance", gpu_lines),
                ("Learning", learning_lines),
            ),
            blockers=adapter.blockers,
        )

    @staticmethod
    def publish_evidence_surface(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        report_type = "virtual_evidence"
        file_stem = f"virtual_{adapter.surface_kind.lower()}_evidence"
        paths = user_report_paths(root, report_type, stamp, file_stem=file_stem)
        write_user_report_files(
            paths,
            VirtualMarketRuntime.evidence_surface_payload(adapter),
            VirtualMarketRuntime.render_evidence_surface_markdown(adapter),
        )
        market_file_stem = (
            f"virtual_{adapter.surface_kind.lower()}_{adapter.market.lower()}_evidence"
        )
        if market_file_stem != file_stem:
            market_paths = user_report_paths(
                root,
                report_type,
                stamp,
                file_stem=market_file_stem,
                latest_stem=f"{market_file_stem}_latest",
            )
            write_user_report_files(
                market_paths,
                VirtualMarketRuntime.evidence_surface_payload(adapter),
                VirtualMarketRuntime.render_evidence_surface_markdown(adapter),
            )
        return paths

    @staticmethod
    def system_acceptance_payload(
        acceptance: SystemResearchAcceptance,
    ) -> dict[str, object]:
        return acceptance.to_payload()

    @staticmethod
    def render_system_acceptance_markdown(
        acceptance: SystemResearchAcceptance,
    ) -> str:
        return render_system_acceptance_markdown(acceptance)

    @staticmethod
    def publish_system_acceptance_report(
        acceptance: SystemResearchAcceptance,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        paths = user_report_paths(
            root,
            "virtual_system_acceptance",
            stamp,
            file_stem="virtual_system_acceptance",
        )
        write_user_report_files(
            paths,
            VirtualMarketRuntime.system_acceptance_payload(acceptance),
            VirtualMarketRuntime.render_system_acceptance_markdown(acceptance),
        )
        return paths

    @staticmethod
    def loss_streak_halt_review_payload(
        review: VirtualLossStreakHaltReview,
    ) -> dict[str, object]:
        return review.to_payload()

    @staticmethod
    def render_loss_streak_halt_review_markdown(
        review: VirtualLossStreakHaltReview,
    ) -> str:
        candidate_lines = tuple(
            f"- `{candidate.candidate_id}`"
            for candidate in review.improvement_candidates
        )
        return render_professional_summary(
            title=f"Virtual Loss Streak Halt Review {review.market}",
            observed_at=review.snapshot_id,
            status=review.status.value,
            summary=(
                "This local halt review freezes bounded virtual-market autonomy "
                "after a governed loss streak and stages research-only follow-up "
                "work without granting execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Review id: `{review.review_id}`",
                        f"- Halt scope: `{review.halt_scope}`",
                        (
                            f"- Loss streak: `{review.consecutive_losses}/{review.maximum_consecutive_losses}`"
                        ),
                    ),
                ),
                ("Findings", tuple(f"- {line}" for line in review.findings)),
                (
                    "Root Cause",
                    (
                        f"- Summary: `{review.root_cause_summary}`",
                        ("- Tags: `" + ", ".join(review.root_cause_tags) + "`"),
                        (
                            f"- Next bounded experiment: `{review.next_bounded_experiment}`"
                        ),
                    ),
                ),
                (
                    "Reset Criteria",
                    tuple(f"- {line}" for line in review.reset_criteria),
                ),
                ("Improvement Candidates", candidate_lines),
            ),
            blockers=(review.trigger_blocker,),
        )

    @staticmethod
    def _compact_halt_review_registry_history(path: Path, *, keep_last: int) -> None:
        if keep_last < 1 or not path.exists():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        valid_lines = [line for line in lines if line.strip()]
        if len(valid_lines) <= keep_last:
            return
        seen_review_refs: set[str] = set()
        selected_indexes: list[int] = []
        for index in range(len(valid_lines) - 1, -1, -1):
            if len(selected_indexes) == keep_last:
                break
            try:
                payload = json.loads(valid_lines[index])
            except json.JSONDecodeError:
                selected_indexes.append(index)
                continue
            review_ref = str(payload.get("review_ref", "")).strip()
            if review_ref and review_ref in seen_review_refs:
                continue
            selected_indexes.append(index)
            if review_ref:
                seen_review_refs.add(review_ref)
        trimmed = [valid_lines[index] for index in sorted(selected_indexes)]
        path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")

    @staticmethod
    def publish_loss_streak_halt_review(
        review: VirtualLossStreakHaltReview,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        paths = user_report_paths(
            root,
            "virtual_loss_streak_halt_review",
            stamp,
            file_stem="virtual_loss_streak_halt_review",
        )
        write_user_report_files(
            paths,
            VirtualMarketRuntime.loss_streak_halt_review_payload(review),
            VirtualMarketRuntime.render_loss_streak_halt_review_markdown(review),
        )
        registry_path = (
            root
            / "runtime"
            / "artifacts"
            / "user_reports"
            / "virtual_loss_streak_halt_review"
            / "review_registry_latest.json"
        )
        registry_history_path = (
            root
            / "runtime"
            / "artifacts"
            / "user_reports"
            / "virtual_loss_streak_halt_review"
            / "review_registry.jsonl"
        )
        registry_payload = {
            "review_ref": review.review_id,
            "artifact_path": str(paths.json_path.relative_to(root)).replace("\\", "/"),
            "latest_artifact_path": str(
                paths.latest_json_path.relative_to(root)
            ).replace(
                "\\",
                "/",
            ),
            "generated_at": stamp,
            "status": review.status.value,
        }
        registry_path.write_text(
            json.dumps(registry_payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        with registry_history_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(registry_payload, ensure_ascii=False, sort_keys=True) + "\n"
            )
        VirtualMarketRuntime._compact_halt_review_registry_history(
            registry_history_path,
            keep_last=VirtualMarketRuntime._HALT_REVIEW_REGISTRY_HISTORY_LIMIT,
        )
        return paths

    @staticmethod
    def stage_improvement_candidates(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> tuple[VirtualStagedImprovementCandidate, ...]:
        VirtualMarketRuntime._require_improvement_publish_readiness(adapter)
        return tuple(
            VirtualMarketRuntime._stage_improvement_candidate(adapter, candidate)
            for candidate in adapter.improvement_candidates
        )

    @staticmethod
    def _require_improvement_publish_readiness(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> None:
        if adapter.telemetry_snapshot is None:
            raise ValueError(
                "virtual improvement publishing requires canonical telemetry"
            )
        if not adapter.performance_snapshot.lineage.complete:
            raise ValueError("virtual improvement publishing requires complete lineage")
        if not adapter.improvement_candidates:
            raise ValueError(
                "virtual improvement publishing requires improvement candidates"
            )

    @staticmethod
    def staged_improvement_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> dict[str, object]:
        staged_candidates = VirtualMarketRuntime.stage_improvement_candidates(adapter)
        return {
            "surface_kind": adapter.surface_kind,
            "snapshot_id": adapter.snapshot_id,
            "staged_candidate_count": len(staged_candidates),
            "staged_candidates": tuple(
                candidate.to_payload() for candidate in staged_candidates
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @staticmethod
    def render_staged_improvement_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        staged_candidates = VirtualMarketRuntime.stage_improvement_candidates(adapter)
        staged_lines = tuple(
            (
                f"- `{item.stage_id}`: `{item.promotion_status.value}` for `{item.candidate.candidate_id}`"
            )
            for item in staged_candidates
        )
        return render_professional_summary(
            title=f"Virtual Improvement Candidate Staging {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=adapter.performance_snapshot.status.value,
            summary=(
                "This local report stages virtual-market improvement candidates "
                "for further research review without granting paper or live "
                "execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Snapshot id: `{adapter.snapshot_id}`",
                        f"- Surface kind: `{adapter.surface_kind}`",
                        f"- Candidate count: `{len(staged_candidates)}`",
                    ),
                ),
                ("Staged Candidates", staged_lines),
            ),
            blockers=tuple(
                dict.fromkeys(
                    blocker for item in staged_candidates for blocker in item.blockers
                )
            ),
        )

    @staticmethod
    def publish_staged_improvement_candidates(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        paths = user_report_paths(
            root,
            "virtual_improvement_candidates",
            stamp,
            file_stem=f"virtual_{adapter.surface_kind.lower()}_improvement_candidates",
        )
        write_user_report_files(
            paths,
            VirtualMarketRuntime.staged_improvement_payload(adapter),
            VirtualMarketRuntime.render_staged_improvement_markdown(adapter),
        )
        return paths

    @staticmethod
    def build_improvement_research_queue(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchQueue:
        VirtualMarketRuntime._require_improvement_publish_readiness(adapter)
        staged_candidates = tuple(
            sorted(
                VirtualMarketRuntime.stage_improvement_candidates(adapter),
                key=VirtualMarketRuntime._improvement_research_order_key,
            )
        )
        triage_reason = VirtualMarketRuntime._improvement_queue_triage_reason(adapter)
        items = tuple(
            VirtualMarketRuntime._improvement_research_work_item(
                item,
                triage_reason=triage_reason,
            )
            for item in staged_candidates
        )
        blockers = tuple(
            dict.fromkeys(blocker for item in items for blocker in item.blockers)
        )
        return VirtualImprovementResearchQueue(
            queue_id=f"virtual-improvement-queue:{adapter.snapshot_id}",
            snapshot_id=adapter.snapshot_id,
            surface_kind=adapter.surface_kind,
            items=items,
            assurance_artifact_refs=VirtualMarketRuntime._improvement_queue_assurance_artifact_refs(
                adapter.surface_kind
            ),
            blockers=blockers,
            triage_reason=triage_reason,
            status="READY" if not blockers else "QUEUED_WITH_BLOCKERS",
        )

    @staticmethod
    def render_improvement_research_queue_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        queue_lines = tuple(
            (f"- `{item.work_id}`: `{item.priority}` for `{item.candidate_id}`")
            for item in queue.items
        )
        return render_professional_summary(
            title=f"Virtual Improvement Research Queue {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=queue.status,
            summary=(
                "This local queue hands staged virtual improvement candidates to "
                "research and governance consumers without granting paper or "
                "live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Queue id: `{queue.queue_id}`",
                        f"- Snapshot id: `{queue.snapshot_id}`",
                        f"- Item count: `{len(queue.items)}`",
                        f"- Triage reason: `{queue.triage_reason}`",
                    ),
                ),
                ("Queued Items", queue_lines),
            ),
            blockers=queue.blockers,
        )

    @staticmethod
    def publish_improvement_research_queue(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        paths = user_report_paths(
            root,
            "virtual_improvement_queue",
            stamp,
            file_stem=f"virtual_{adapter.surface_kind.lower()}_improvement_queue",
        )
        write_user_report_files(
            paths,
            queue.to_payload(),
            VirtualMarketRuntime.render_improvement_research_queue_markdown(adapter),
        )
        return paths

    @staticmethod
    def build_improvement_research_queue_assurance_bundle(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> TrustAssuranceBundle:
        VirtualMarketRuntime._require_improvement_publish_readiness(adapter)
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        policy_evaluations = tuple(
            VirtualMarketRuntime._improvement_queue_policy_evaluation(queue, item)
            for item in queue.items
        )
        uncertainty = VirtualMarketRuntime._improvement_queue_uncertainty(
            queue=queue,
            policy_evaluations=policy_evaluations,
        )
        provenance = VirtualMarketRuntime._improvement_queue_provenance(
            queue=queue,
            policy_evaluations=policy_evaluations,
            uncertainty=uncertainty,
            observed_at=adapter.performance_snapshot.observed_at,
        )
        semantic_contracts = (
            SemanticContractRecord(
                contract_id=f"contract:{queue.queue_id}",
                subject="VirtualImprovementResearchHandoff",
                required_fields=(
                    "context_refs",
                    "evidence_refs",
                    "governance_refs",
                    "policy_version_refs",
                    "required_output_fields",
                ),
                forbidden_fields=(
                    "execution_allowed=true",
                    "promotion_status=PAPER_APPROVED",
                    "live_eligibility_status=READY",
                ),
                validation_status=(
                    TrustAssuranceResult.PASSED
                    if queue.status == "READY"
                    else TrustAssuranceResult.WARN
                ),
            ),
        )
        evidence_graph = VirtualMarketRuntime._improvement_queue_evidence_graph(queue)
        return TrustAssuranceBundle(
            bundle_id=f"assurance:{queue.queue_id}",
            provenance=provenance,
            policy_evaluations=policy_evaluations,
            uncertainty=uncertainty,
            semantic_contracts=semantic_contracts,
            evidence_graph=evidence_graph,
        )

    @staticmethod
    def render_improvement_research_queue_assurance_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        bundle = VirtualMarketRuntime.build_improvement_research_queue_assurance_bundle(
            adapter
        )
        payload = bundle.to_payload()
        policy_lines = tuple(
            (
                f"- `{evaluation.policy_id}` -> `{evaluation.result.value}` for `{evaluation.evaluation_id}`"
            )
            for evaluation in bundle.policy_evaluations
        )
        contract_lines = tuple(
            (
                f"- `{contract.subject}`: `{contract.validation_status.value}` "
                f"with forbidden `{', '.join(contract.forbidden_fields)}`"
            )
            for contract in bundle.semantic_contracts
        )
        return render_professional_summary(
            title=(f"Virtual Improvement Queue Assurance {adapter.surface_kind}"),
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=bundle.provenance.final_action,
            summary=(
                "This local assurance report packages the virtual improvement "
                "queue as governed research evidence without granting paper or "
                "live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Queue decision id: `{bundle.provenance.decision_id}`",
                        f"- Bundle id: `{bundle.bundle_id}`",
                        f"- Framework: `{payload['framework']}`",
                    ),
                ),
                (
                    "Policy Evaluations",
                    policy_lines,
                ),
                (
                    "Semantic Contracts",
                    contract_lines,
                ),
                (
                    "Uncertainty",
                    (
                        f"- Level: `{bundle.uncertainty.level.value}`",
                        (
                            f"- Reasons: `{', '.join(bundle.uncertainty.reasons) or '-'}`"
                        ),
                    ),
                ),
            ),
            blockers=bundle.provenance.blockers,
        )

    @staticmethod
    def publish_improvement_research_queue_assurance(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        bundle = VirtualMarketRuntime.build_improvement_research_queue_assurance_bundle(
            adapter
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_queue_assurance",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_queue_assurance"
            ),
        )
        write_user_report_files(
            paths,
            bundle.to_payload(),
            VirtualMarketRuntime.render_improvement_research_queue_assurance_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_review_results(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> tuple[VirtualImprovementReviewResult, ...]:
        VirtualMarketRuntime._require_improvement_publish_readiness(adapter)
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        return tuple(
            build_virtual_improvement_review_result(
                consume_virtual_improvement_review_handoff(
                    item.normalized_handoff_payload()
                )
            )
            for item in queue.items
        )

    @staticmethod
    def improvement_review_results_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> dict[str, object]:
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        results = VirtualMarketRuntime.build_improvement_review_results(adapter)
        return {
            "queue_id": queue.queue_id,
            "snapshot_id": queue.snapshot_id,
            "surface_kind": queue.surface_kind,
            "status": (
                "READY_FOR_EXPERIMENT_PROPOSAL"
                if all(not result.blockers for result in results)
                else "INVESTIGATION_REQUIRED"
            ),
            "review_result_count": len(results),
            "review_results": [result.to_payload() for result in results],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @staticmethod
    def render_improvement_review_results_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        payload = VirtualMarketRuntime.improvement_review_results_payload(adapter)
        review_results = VirtualMarketRuntime.build_improvement_review_results(adapter)
        review_lines = tuple(
            (
                f"- `{result.review_id}`: `{result.outcome.value}` with gap `{result.evidence_gap_assessment}`"
            )
            for result in review_results
        )
        return render_professional_summary(
            title=f"Virtual Improvement Review Results {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=str(payload["status"]),
            summary=(
                "This local review-result report turns the governed queue and "
                "assurance pair into research-only follow-up actions without "
                "granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Queue id: `{payload['queue_id']}`",
                        f"- Snapshot id: `{payload['snapshot_id']}`",
                        f"- Review result count: `{payload['review_result_count']}`",
                    ),
                ),
                ("Review Results", review_lines),
            ),
            blockers=tuple(
                dict.fromkeys(
                    blocker for result in review_results for blocker in result.blockers
                )
            ),
        )

    @staticmethod
    def publish_improvement_review_results(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        paths = user_report_paths(
            root,
            "virtual_improvement_reviews",
            stamp,
            file_stem=f"virtual_{adapter.surface_kind.lower()}_improvement_reviews",
        )
        write_user_report_files(
            paths,
            VirtualMarketRuntime.improvement_review_results_payload(adapter),
            VirtualMarketRuntime.render_improvement_review_results_markdown(adapter),
        )
        return paths

    @staticmethod
    def build_improvement_experiment_proposals(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> tuple[VirtualImprovementExperimentProposal, ...]:
        return tuple(
            build_virtual_improvement_experiment_proposal(result)
            for result in VirtualMarketRuntime.build_improvement_review_results(adapter)
        )

    @staticmethod
    def improvement_experiment_proposals_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> dict[str, object]:
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        proposals = VirtualMarketRuntime.build_improvement_experiment_proposals(adapter)
        return {
            "queue_id": queue.queue_id,
            "snapshot_id": queue.snapshot_id,
            "surface_kind": queue.surface_kind,
            "status": (
                "READY_FOR_BOUNDED_EXPERIMENT"
                if all(not proposal.blockers for proposal in proposals)
                else "BLOCKED_PENDING_EVIDENCE"
            ),
            "proposal_count": len(proposals),
            "proposals": [proposal.to_payload() for proposal in proposals],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @staticmethod
    def render_improvement_experiment_proposals_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        payload = VirtualMarketRuntime.improvement_experiment_proposals_payload(adapter)
        proposals = VirtualMarketRuntime.build_improvement_experiment_proposals(adapter)
        proposal_lines = tuple(
            (
                f"- `{proposal.proposal_id}`: `{proposal.priority}` with gap `{proposal.evidence_gap_assessment}`"
            )
            for proposal in proposals
        )
        return render_professional_summary(
            title=f"Virtual Improvement Experiment Proposals {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=str(payload["status"]),
            summary=(
                "This local dossier packages the next bounded research experiment "
                "from review-result evidence without granting paper or live "
                "execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Queue id: `{payload['queue_id']}`",
                        f"- Snapshot id: `{payload['snapshot_id']}`",
                        f"- Proposal count: `{payload['proposal_count']}`",
                    ),
                ),
                ("Proposals", proposal_lines),
            ),
            blockers=tuple(
                dict.fromkeys(
                    blocker for proposal in proposals for blocker in proposal.blockers
                )
            ),
        )

    @staticmethod
    def publish_improvement_experiment_proposals(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        paths = user_report_paths(
            root,
            "virtual_improvement_experiments",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_experiments"
            ),
        )
        write_user_report_files(
            paths,
            VirtualMarketRuntime.improvement_experiment_proposals_payload(adapter),
            VirtualMarketRuntime.render_improvement_experiment_proposals_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_experiment_tasks(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> tuple[VirtualImprovementExperimentTaskRecord, ...]:
        return tuple(
            build_virtual_improvement_experiment_task(proposal)
            for proposal in VirtualMarketRuntime.build_improvement_experiment_proposals(
                adapter
            )
        )

    @staticmethod
    def improvement_experiment_tasks_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> dict[str, object]:
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        tasks = VirtualMarketRuntime.build_improvement_experiment_tasks(adapter)
        return {
            "queue_id": queue.queue_id,
            "snapshot_id": queue.snapshot_id,
            "surface_kind": queue.surface_kind,
            "status": (
                "TASKS_READY_FOR_RESEARCH"
                if all(not task.blockers for task in tasks)
                else "TASKS_PENDING_EVIDENCE"
            ),
            "task_count": len(tasks),
            "tasks": [task.to_payload() for task in tasks],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @staticmethod
    def render_improvement_experiment_tasks_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        payload = VirtualMarketRuntime.improvement_experiment_tasks_payload(adapter)
        tasks = VirtualMarketRuntime.build_improvement_experiment_tasks(adapter)
        task_lines = tuple(
            (
                f"- `{task.task_id}`: `{task.status.value}` with priority `{task.priority}`"
            )
            for task in tasks
        )
        return render_professional_summary(
            title=f"Virtual Improvement Experiment Tasks {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=str(payload["status"]),
            summary=(
                "This local task queue turns bounded experiment proposals into "
                "traceable research work items without granting paper or live "
                "execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Queue id: `{payload['queue_id']}`",
                        f"- Snapshot id: `{payload['snapshot_id']}`",
                        f"- Task count: `{payload['task_count']}`",
                    ),
                ),
                ("Tasks", task_lines),
            ),
            blockers=tuple(
                dict.fromkeys(blocker for task in tasks for blocker in task.blockers)
            ),
        )

    @staticmethod
    def publish_improvement_experiment_tasks(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        paths = user_report_paths(
            root,
            "virtual_improvement_tasks",
            stamp,
            file_stem=f"virtual_{adapter.surface_kind.lower()}_improvement_tasks",
        )
        write_user_report_files(
            paths,
            VirtualMarketRuntime.improvement_experiment_tasks_payload(adapter),
            VirtualMarketRuntime.render_improvement_experiment_tasks_markdown(adapter),
        )
        return paths

    @staticmethod
    def build_improvement_experiment_task_queue(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementExperimentTaskQueue:
        queue = VirtualMarketRuntime.build_improvement_research_queue(adapter)
        tasks = VirtualMarketRuntime.build_improvement_experiment_tasks(adapter)
        return build_virtual_improvement_experiment_task_queue(
            queue_id=f"virtual-improvement-task-queue:{queue.queue_id}",
            snapshot_id=queue.snapshot_id,
            surface_kind=queue.surface_kind,
            tasks=tasks,
        )

    @staticmethod
    def render_improvement_experiment_task_queue_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        queue = VirtualMarketRuntime.build_improvement_experiment_task_queue(adapter)
        task_lines = tuple(
            (f"- `{task.task_id}`: `{task.status.value}` priority `{task.priority}`")
            for task in queue.tasks
        )
        return render_professional_summary(
            title=f"Virtual Improvement Task Queue {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=queue.status,
            summary=(
                "This local task-queue snapshot gives research consumers one "
                "bounded entry point for ready versus evidence-pending virtual "
                "improvement work without granting execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Queue id: `{queue.queue_id}`",
                        f"- Snapshot id: `{queue.snapshot_id}`",
                        f"- Ready task count: `{queue.ready_task_count}`",
                        (
                            f"- Evidence-pending task count: `{queue.evidence_pending_task_count}`"
                        ),
                    ),
                ),
                ("Tasks", task_lines),
            ),
            blockers=tuple(
                dict.fromkeys(
                    blocker for task in queue.tasks for blocker in task.blockers
                )
            ),
        )

    @staticmethod
    def publish_improvement_experiment_task_queue(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        queue = VirtualMarketRuntime.build_improvement_experiment_task_queue(adapter)
        paths = user_report_paths(
            root,
            "virtual_improvement_task_queue",
            stamp,
            file_stem=f"virtual_{adapter.surface_kind.lower()}_improvement_task_queue",
        )
        write_user_report_files(
            paths,
            queue.to_payload(),
            VirtualMarketRuntime.render_improvement_experiment_task_queue_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_work_planner(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchWorkPlanner:
        queue = VirtualMarketRuntime.build_improvement_experiment_task_queue(adapter)
        return build_virtual_improvement_research_work_planner(queue)

    @staticmethod
    def render_improvement_research_work_planner_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        planner = VirtualMarketRuntime.build_improvement_research_work_planner(adapter)
        action_lines = tuple(f"- `{action}`" for action in planner.next_safe_actions)
        return render_professional_summary(
            title=f"Virtual Improvement Research Planner {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=planner.status,
            summary=(
                "This local planner turns the task queue into ordered next-safe "
                "actions for operator or research follow-up without granting "
                "paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Planner id: `{planner.planner_id}`",
                        f"- Queue id: `{planner.queue_id}`",
                        f"- Ready selections: `{len(planner.selected_ready_task_ids)}`",
                        f"- Escalations: `{len(planner.escalated_task_ids)}`",
                    ),
                ),
                ("Next Safe Actions", action_lines),
            ),
            blockers=tuple(
                []
                if not planner.escalated_task_ids
                else ("EVIDENCE_ESCALATION_REQUIRED",)
            ),
        )

    @staticmethod
    def publish_improvement_research_work_planner(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        planner = VirtualMarketRuntime.build_improvement_research_work_planner(adapter)
        paths = user_report_paths(
            root,
            "virtual_improvement_work_planner",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_work_planner"
            ),
        )
        write_user_report_files(
            paths,
            planner.to_payload(),
            VirtualMarketRuntime.render_improvement_research_work_planner_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_operator_handoff_summary(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementOperatorHandoffSummary:
        queue = VirtualMarketRuntime.build_improvement_experiment_task_queue(adapter)
        planner = VirtualMarketRuntime.build_improvement_research_work_planner(adapter)
        return build_virtual_improvement_operator_handoff_summary(
            queue=queue,
            planner=planner,
        )

    @staticmethod
    def render_improvement_operator_handoff_summary_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        summary = VirtualMarketRuntime.build_improvement_operator_handoff_summary(
            adapter
        )
        selected_lines = tuple(f"- `{item}`" for item in summary.selected_task_briefs)
        escalated_lines = tuple(
            f"- `{item}`" for item in summary.escalated_blocker_briefs
        )
        action_lines = tuple(f"- `{item}`" for item in summary.next_safe_actions)
        return render_professional_summary(
            title=f"Virtual Improvement Operator Handoff {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=summary.status,
            summary=(
                "This local operator handoff condenses the planner into a "
                "single human-review page with ready work, escalations, and "
                "ordered next-safe actions while keeping execution blocked."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Summary id: `{summary.summary_id}`",
                        f"- Planner id: `{summary.planner_id}`",
                        f"- Queue id: `{summary.queue_id}`",
                    ),
                ),
                ("Selected Tasks", selected_lines),
                ("Escalated Blockers", escalated_lines),
                ("Next Safe Actions", action_lines),
            ),
            blockers=tuple(
                []
                if not summary.escalated_blocker_briefs
                else ("EVIDENCE_ESCALATION_REQUIRED",)
            ),
        )

    @staticmethod
    def publish_improvement_operator_handoff_summary(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        summary = VirtualMarketRuntime.build_improvement_operator_handoff_summary(
            adapter
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_operator_handoff",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_operator_handoff"
            ),
        )
        write_user_report_files(
            paths,
            summary.to_payload(),
            VirtualMarketRuntime.render_improvement_operator_handoff_summary_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_execution_inbox(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchExecutionInbox:
        summary = VirtualMarketRuntime.build_improvement_operator_handoff_summary(
            adapter
        )
        return build_virtual_improvement_research_execution_inbox(summary)

    @staticmethod
    def render_improvement_research_execution_inbox_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        inbox = VirtualMarketRuntime.build_improvement_research_execution_inbox(adapter)
        ready_lines = tuple(f"- `{item}`" for item in inbox.ready_work_items)
        escalation_lines = tuple(f"- `{item}`" for item in inbox.escalation_items)
        action_lines = tuple(f"- `{item}`" for item in inbox.next_safe_actions)
        return render_professional_summary(
            title=f"Virtual Improvement Research Inbox {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=inbox.status,
            summary=(
                "This local inbox is the single what-to-do-now artifact for "
                "bounded research follow-up on Tuesday, August 25, 2026, "
                "without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Inbox id: `{inbox.inbox_id}`",
                        f"- Summary id: `{inbox.summary_id}`",
                        f"- Queue id: `{inbox.queue_id}`",
                    ),
                ),
                ("Ready Work", ready_lines),
                ("Escalations", escalation_lines),
                ("Next Safe Actions", action_lines),
            ),
            blockers=tuple(
                [] if not inbox.escalation_items else ("EVIDENCE_ESCALATION_REQUIRED",)
            ),
        )

    @staticmethod
    def publish_improvement_research_execution_inbox(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        inbox = VirtualMarketRuntime.build_improvement_research_execution_inbox(adapter)
        paths = user_report_paths(
            root,
            "virtual_improvement_research_inbox",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_research_inbox"
            ),
        )
        write_user_report_files(
            paths,
            inbox.to_payload(),
            VirtualMarketRuntime.render_improvement_research_execution_inbox_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_execution_session_manifest(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchExecutionSessionManifest:
        inbox = VirtualMarketRuntime.build_improvement_research_execution_inbox(adapter)
        return build_virtual_improvement_research_execution_session_manifest(inbox)

    @staticmethod
    def render_improvement_research_execution_session_manifest_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        manifest = (
            VirtualMarketRuntime.build_improvement_research_execution_session_manifest(
                adapter
            )
        )
        action_lines = tuple(f"- `{item}`" for item in manifest.action_order)
        artifact_lines = tuple(f"- `{item}`" for item in manifest.artifact_refs)
        return render_professional_summary(
            title=f"Virtual Improvement Session Manifest {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=manifest.status,
            summary=(
                "This local session manifest defines the bounded research "
                "execution plan for Tuesday, August 25, 2026, including the "
                "chosen ready item, escalations, action order, and artifact "
                "references, without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Manifest id: `{manifest.manifest_id}`",
                        f"- Inbox id: `{manifest.inbox_id}`",
                        f"- Chosen ready item: `{manifest.chosen_ready_item or '-'}`",
                    ),
                ),
                ("Action Order", action_lines),
                ("Artifact Refs", artifact_lines),
            ),
            blockers=tuple(
                []
                if not manifest.escalation_items
                else ("EVIDENCE_ESCALATION_REQUIRED",)
            ),
        )

    @staticmethod
    def publish_improvement_research_execution_session_manifest(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        manifest = (
            VirtualMarketRuntime.build_improvement_research_execution_session_manifest(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_session_manifest",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_session_manifest"
            ),
        )
        write_user_report_files(
            paths,
            manifest.to_payload(),
            VirtualMarketRuntime.render_improvement_research_execution_session_manifest_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_session_journal(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchSessionJournal:
        manifest = (
            VirtualMarketRuntime.build_improvement_research_execution_session_manifest(
                adapter
            )
        )
        return build_virtual_improvement_research_session_journal(manifest)

    @staticmethod
    def render_improvement_research_session_journal_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        journal = VirtualMarketRuntime.build_improvement_research_session_journal(
            adapter
        )
        action_lines = tuple(f"- `{item}`" for item in journal.consumed_action_order)
        artifact_lines = tuple(f"- `{item}`" for item in journal.artifact_refs)
        return render_professional_summary(
            title=f"Virtual Improvement Session Journal {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=journal.status,
            summary=(
                "This local session journal records the bounded research "
                "execution trail for Tuesday, August 25, 2026, including the "
                "chosen ready item, consumed action order, escalation state, "
                "and closure result, without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Journal id: `{journal.journal_id}`",
                        f"- Manifest id: `{journal.manifest_id}`",
                        f"- Closure result: `{journal.closure_result}`",
                    ),
                ),
                ("Consumed Action Order", action_lines),
                ("Artifact Refs", artifact_lines),
            ),
            blockers=tuple(
                []
                if not journal.escalation_items
                else ("EVIDENCE_ESCALATION_REQUIRED",)
            ),
        )

    @staticmethod
    def publish_improvement_research_session_journal(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        journal = VirtualMarketRuntime.build_improvement_research_session_journal(
            adapter
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_session_journal",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_session_journal"
            ),
        )
        write_user_report_files(
            paths,
            journal.to_payload(),
            VirtualMarketRuntime.render_improvement_research_session_journal_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_session_closure_record(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchSessionClosureRecord:
        journal = VirtualMarketRuntime.build_improvement_research_session_journal(
            adapter
        )
        return build_virtual_improvement_research_session_closure_record(journal)

    @staticmethod
    def render_improvement_research_session_closure_record_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        closure = (
            VirtualMarketRuntime.build_improvement_research_session_closure_record(
                adapter
            )
        )
        action_lines = tuple(f"- `{item}`" for item in closure.completed_actions)
        artifact_lines = tuple(f"- `{item}`" for item in closure.produced_artifact_refs)
        return render_professional_summary(
            title=f"Virtual Improvement Session Closure {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=closure.status,
            summary=(
                "This local session closure record finalizes the bounded "
                "research execution trail for Tuesday, August 25, 2026, "
                "including completed actions, produced artifacts, escalation "
                "state, and closure reason, without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Closure id: `{closure.closure_id}`",
                        f"- Journal id: `{closure.journal_id}`",
                        f"- Closure reason: `{closure.closure_reason}`",
                    ),
                ),
                ("Completed Actions", action_lines),
                ("Produced Artifact Refs", artifact_lines),
            ),
            blockers=tuple(
                []
                if not closure.escalation_items
                else ("EVIDENCE_ESCALATION_REQUIRED",)
            ),
        )

    @staticmethod
    def publish_improvement_research_session_closure_record(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        closure = (
            VirtualMarketRuntime.build_improvement_research_session_closure_record(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_session_closure",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_session_closure"
            ),
        )
        write_user_report_files(
            paths,
            closure.to_payload(),
            VirtualMarketRuntime.render_improvement_research_session_closure_record_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_session_artifact_bundle(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchSessionArtifactBundle:
        manifest = (
            VirtualMarketRuntime.build_improvement_research_execution_session_manifest(
                adapter
            )
        )
        journal = VirtualMarketRuntime.build_improvement_research_session_journal(
            adapter
        )
        closure = (
            VirtualMarketRuntime.build_improvement_research_session_closure_record(
                adapter
            )
        )
        return build_virtual_improvement_research_session_artifact_bundle(
            manifest=manifest,
            journal=journal,
            closure=closure,
        )

    @staticmethod
    def render_improvement_research_session_artifact_bundle_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        bundle = (
            VirtualMarketRuntime.build_improvement_research_session_artifact_bundle(
                adapter
            )
        )
        required_lines = tuple(f"- `{item}`" for item in bundle.required_artifact_refs)
        produced_lines = tuple(f"- `{item}`" for item in bundle.produced_artifact_refs)
        missing_lines = tuple(
            f"- `{item}`" for item in bundle.missing_artifact_refs
        ) or ("- `NONE`",)
        return render_professional_summary(
            title=f"Virtual Improvement Session Bundle {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=bundle.status,
            summary=(
                "This local session artifact bundle consolidates the bounded "
                "research evidence for Tuesday, August 25, 2026, comparing "
                "required versus produced artifact references and preserving "
                "escalation visibility without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Bundle id: `{bundle.bundle_id}`",
                        f"- Closure id: `{bundle.closure_id}`",
                        f"- Missing artifact count: `{len(bundle.missing_artifact_refs)}`",
                    ),
                ),
                ("Required Artifact Refs", required_lines),
                ("Produced Artifact Refs", produced_lines),
                ("Missing Artifact Refs", missing_lines),
            ),
            blockers=tuple(
                dict.fromkeys(
                    (
                        *(
                            ()
                            if not bundle.escalation_items
                            else ("EVIDENCE_ESCALATION_REQUIRED",)
                        ),
                        *(
                            ()
                            if not bundle.missing_artifact_refs
                            else ("SESSION_ARTIFACT_GAP_REMAINING",)
                        ),
                    )
                )
            ),
        )

    @staticmethod
    def publish_improvement_research_session_artifact_bundle(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        bundle = (
            VirtualMarketRuntime.build_improvement_research_session_artifact_bundle(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_session_bundle",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_session_bundle"
            ),
        )
        write_user_report_files(
            paths,
            bundle.to_payload(),
            VirtualMarketRuntime.render_improvement_research_session_artifact_bundle_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_research_session_readiness_summary(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementResearchSessionReadinessSummary:
        bundle = (
            VirtualMarketRuntime.build_improvement_research_session_artifact_bundle(
                adapter
            )
        )
        return build_virtual_improvement_research_session_readiness_summary(bundle)

    @staticmethod
    def render_improvement_research_session_readiness_summary_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        summary = (
            VirtualMarketRuntime.build_improvement_research_session_readiness_summary(
                adapter
            )
        )
        blocker_lines = tuple(f"- `{item}`" for item in summary.blocker_codes) or (
            "- `NONE`",
        )
        return render_professional_summary(
            title=f"Virtual Improvement Session Readiness {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=summary.status,
            summary=(
                "This local readiness summary condenses the bounded research "
                "session verdict for Tuesday, August 25, 2026, mapping bundle "
                "completeness, escalation state, and next safe handoff into a "
                "single research-only operator view without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Summary id: `{summary.summary_id}`",
                        f"- Verdict: `{summary.verdict}`",
                        f"- Next safe handoff: `{summary.next_safe_handoff}`",
                    ),
                ),
                ("Blocker Codes", blocker_lines),
            ),
            blockers=summary.blocker_codes,
        )

    @staticmethod
    def publish_improvement_research_session_readiness_summary(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        summary = (
            VirtualMarketRuntime.build_improvement_research_session_readiness_summary(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_session_readiness",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_session_readiness"
            ),
        )
        write_user_report_files(
            paths,
            summary.to_payload(),
            VirtualMarketRuntime.render_improvement_research_session_readiness_summary_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_next_candidate_intake_handoff(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementNextCandidateIntakeHandoff:
        summary = (
            VirtualMarketRuntime.build_improvement_research_session_readiness_summary(
                adapter
            )
        )
        return build_virtual_improvement_next_candidate_intake_handoff(summary)

    @staticmethod
    def render_improvement_next_candidate_intake_handoff_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        handoff = VirtualMarketRuntime.build_improvement_next_candidate_intake_handoff(
            adapter
        )
        blocker_lines = tuple(f"- `{item}`" for item in handoff.blocker_codes) or (
            "- `NONE`",
        )
        return render_professional_summary(
            title=f"Virtual Improvement Next Candidate Intake {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=handoff.status,
            summary=(
                "This local next-candidate intake handoff applies the bounded "
                "research readiness verdict for Tuesday, August 25, 2026, "
                "deciding whether the next virtual improvement candidate may be "
                "opened or must remain held without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Handoff id: `{handoff.handoff_id}`",
                        f"- Intake decision: `{handoff.intake_decision}`",
                        f"- Required follow-up: `{handoff.required_follow_up}`",
                    ),
                ),
                ("Blocker Codes", blocker_lines),
            ),
            blockers=handoff.blocker_codes,
        )

    @staticmethod
    def publish_improvement_next_candidate_intake_handoff(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        handoff = VirtualMarketRuntime.build_improvement_next_candidate_intake_handoff(
            adapter
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_next_candidate_intake",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_next_candidate_intake"
            ),
        )
        write_user_report_files(
            paths,
            handoff.to_payload(),
            VirtualMarketRuntime.render_improvement_next_candidate_intake_handoff_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_next_candidate_registration_packet(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementNextCandidateRegistrationPacket:
        handoff = VirtualMarketRuntime.build_improvement_next_candidate_intake_handoff(
            adapter
        )
        return build_virtual_improvement_next_candidate_registration_packet(handoff)

    @staticmethod
    def render_improvement_next_candidate_registration_packet_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        packet = (
            VirtualMarketRuntime.build_improvement_next_candidate_registration_packet(
                adapter
            )
        )
        provenance_lines = tuple(f"- `{item}`" for item in packet.provenance_refs)
        return render_professional_summary(
            title=f"Virtual Improvement Registration Packet {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=packet.status,
            summary=(
                "This local next-candidate registration packet records the "
                "ready bounded research handoff for Tuesday, August 25, 2026, "
                "including candidate reference and provenance without granting "
                "paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Packet id: `{packet.packet_id}`",
                        f"- Candidate reference: `{packet.candidate_reference}`",
                        f"- Queue id: `{packet.queue_id}`",
                    ),
                ),
                ("Provenance Refs", provenance_lines),
            ),
            blockers=(),
        )

    @staticmethod
    def publish_improvement_next_candidate_registration_packet(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        packet = (
            VirtualMarketRuntime.build_improvement_next_candidate_registration_packet(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_next_candidate_registration",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_next_candidate_registration"
            ),
        )
        write_user_report_files(
            paths,
            packet.to_payload(),
            VirtualMarketRuntime.render_improvement_next_candidate_registration_packet_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_next_candidate_refusal_artifact(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementNextCandidateRefusalArtifact:
        handoff = VirtualMarketRuntime.build_improvement_next_candidate_intake_handoff(
            adapter
        )
        return build_virtual_improvement_next_candidate_refusal_artifact(handoff)

    @staticmethod
    def render_improvement_next_candidate_refusal_artifact_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        artifact = (
            VirtualMarketRuntime.build_improvement_next_candidate_refusal_artifact(
                adapter
            )
        )
        blocker_lines = tuple(f"- `{item}`" for item in artifact.blocker_codes)
        return render_professional_summary(
            title=f"Virtual Improvement Refusal Artifact {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=artifact.status,
            summary=(
                "This local next-candidate refusal artifact records the "
                "blocked bounded research handoff for Tuesday, August 25, 2026, "
                "including blocker codes and required follow-up without granting "
                "paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Artifact id: `{artifact.artifact_id}`",
                        f"- Refusal reason: `{artifact.refusal_reason}`",
                        f"- Required follow-up: `{artifact.required_follow_up}`",
                    ),
                ),
                ("Blocker Codes", blocker_lines),
            ),
            blockers=artifact.blocker_codes,
        )

    @staticmethod
    def publish_improvement_next_candidate_refusal_artifact(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        artifact = (
            VirtualMarketRuntime.build_improvement_next_candidate_refusal_artifact(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_next_candidate_refusal",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_next_candidate_refusal"
            ),
        )
        write_user_report_files(
            paths,
            artifact.to_payload(),
            VirtualMarketRuntime.render_improvement_next_candidate_refusal_artifact_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_candidate_registry_entry(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementCandidateRegistryEntry:
        packet = (
            VirtualMarketRuntime.build_improvement_next_candidate_registration_packet(
                adapter
            )
        )
        return build_virtual_improvement_candidate_registry_entry(packet)

    @staticmethod
    def render_improvement_candidate_registry_entry_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        entry = VirtualMarketRuntime.build_improvement_candidate_registry_entry(adapter)
        provenance_lines = tuple(f"- `{item}`" for item in entry.provenance_refs)
        return render_professional_summary(
            title=f"Virtual Improvement Candidate Registry {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=entry.status,
            summary=(
                "This local candidate registry entry appends the ready bounded "
                "research candidate record for Tuesday, August 25, 2026, "
                "including candidate reference and provenance without granting "
                "paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Entry id: `{entry.entry_id}`",
                        f"- Packet id: `{entry.packet_id}`",
                        f"- Candidate reference: `{entry.candidate_reference}`",
                    ),
                ),
                ("Provenance Refs", provenance_lines),
            ),
            blockers=(),
        )

    @staticmethod
    def publish_improvement_candidate_registry_entry(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        entry = VirtualMarketRuntime.build_improvement_candidate_registry_entry(adapter)
        paths = user_report_paths(
            root,
            "virtual_improvement_candidate_registry",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_candidate_registry"
            ),
        )
        write_user_report_files(
            paths,
            entry.to_payload(),
            VirtualMarketRuntime.render_improvement_candidate_registry_entry_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_refusal_ledger_entry(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementRefusalLedgerEntry:
        artifact = (
            VirtualMarketRuntime.build_improvement_next_candidate_refusal_artifact(
                adapter
            )
        )
        return build_virtual_improvement_refusal_ledger_entry(artifact)

    @staticmethod
    def render_improvement_refusal_ledger_entry_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        entry = VirtualMarketRuntime.build_improvement_refusal_ledger_entry(adapter)
        blocker_lines = tuple(f"- `{item}`" for item in entry.blocker_codes)
        return render_professional_summary(
            title=f"Virtual Improvement Refusal Ledger {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=entry.status,
            summary=(
                "This local refusal ledger entry appends the blocked bounded "
                "research candidate record for Tuesday, August 25, 2026, "
                "including blocker codes and required follow-up without granting "
                "paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Entry id: `{entry.entry_id}`",
                        f"- Artifact id: `{entry.artifact_id}`",
                        f"- Required follow-up: `{entry.required_follow_up}`",
                    ),
                ),
                ("Blocker Codes", blocker_lines),
            ),
            blockers=entry.blocker_codes,
        )

    @staticmethod
    def publish_improvement_refusal_ledger_entry(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        entry = VirtualMarketRuntime.build_improvement_refusal_ledger_entry(adapter)
        paths = user_report_paths(
            root,
            "virtual_improvement_refusal_ledger",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_refusal_ledger"
            ),
        )
        write_user_report_files(
            paths,
            entry.to_payload(),
            VirtualMarketRuntime.render_improvement_refusal_ledger_entry_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_candidate_lifecycle_snapshot(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementCandidateLifecycleSnapshot:
        entry = VirtualMarketRuntime.build_improvement_refusal_ledger_entry(adapter)
        return build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal(
            entry
        )

    @staticmethod
    def render_improvement_candidate_lifecycle_snapshot_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        snapshot = VirtualMarketRuntime.build_improvement_candidate_lifecycle_snapshot(
            adapter
        )
        provenance_lines = tuple(f"- `{item}`" for item in snapshot.provenance_refs)
        blocker_lines = tuple(f"- `{item}`" for item in snapshot.blocker_codes) or (
            "- `NONE`",
        )
        return render_professional_summary(
            title=f"Virtual Improvement Lifecycle Snapshot {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=snapshot.lifecycle_state,
            summary=(
                "This local lifecycle snapshot condenses the latest bounded "
                "virtual improvement outcome for Tuesday, August 25, 2026, "
                "showing whether the candidate cycle was registered or refused "
                "without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Snapshot id: `{snapshot.snapshot_id}`",
                        f"- Source kind: `{snapshot.source_kind}`",
                        f"- Required follow-up: `{snapshot.required_follow_up}`",
                    ),
                ),
                ("Provenance Refs", provenance_lines),
                ("Blocker Codes", blocker_lines),
            ),
            blockers=snapshot.blocker_codes,
        )

    @staticmethod
    def publish_improvement_candidate_lifecycle_snapshot(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        snapshot = VirtualMarketRuntime.build_improvement_candidate_lifecycle_snapshot(
            adapter
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_candidate_lifecycle",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_candidate_lifecycle"
            ),
        )
        write_user_report_files(
            paths,
            snapshot.to_payload(),
            VirtualMarketRuntime.render_improvement_candidate_lifecycle_snapshot_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_candidate_outcome_dashboard_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementCandidateOutcomeDashboardPayload:
        snapshot = VirtualMarketRuntime.build_improvement_candidate_lifecycle_snapshot(
            adapter
        )
        return build_virtual_improvement_candidate_outcome_dashboard_payload(snapshot)

    @staticmethod
    def render_improvement_candidate_outcome_dashboard_payload_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        dashboard = (
            VirtualMarketRuntime.build_improvement_candidate_outcome_dashboard_payload(
                adapter
            )
        )
        return render_professional_summary(
            title=f"Virtual Improvement Outcome Dashboard {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=dashboard.outcome_state,
            summary=(
                "This local outcome dashboard condenses the latest bounded "
                "virtual improvement cycle for Tuesday, August 25, 2026, "
                "including outcome state, blocker load, provenance depth, and "
                "follow-up category without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Overview",
                    (
                        f"- Dashboard id: `{dashboard.dashboard_id}`",
                        f"- Outcome state: `{dashboard.outcome_state}`",
                        f"- Follow-up category: `{dashboard.follow_up_category}`",
                    ),
                ),
                (
                    "Metrics",
                    (
                        f"- Blocker count: `{dashboard.blocker_count}`",
                        f"- Provenance count: `{dashboard.provenance_count}`",
                        f"- Subject reference: `{dashboard.subject_reference}`",
                    ),
                ),
            ),
            blockers=(
                ("SESSION_OUTCOME_BLOCKERS_PRESENT",)
                if dashboard.blocker_count > 0
                else ()
            ),
        )

    @staticmethod
    def publish_improvement_candidate_outcome_dashboard_payload(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        dashboard = (
            VirtualMarketRuntime.build_improvement_candidate_outcome_dashboard_payload(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_outcome_dashboard",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_outcome_dashboard"
            ),
        )
        write_user_report_files(
            paths,
            dashboard.to_payload(),
            VirtualMarketRuntime.render_improvement_candidate_outcome_dashboard_payload_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def build_improvement_candidate_cycle_executive_summary(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> VirtualImprovementCandidateCycleExecutiveSummary:
        dashboard = (
            VirtualMarketRuntime.build_improvement_candidate_outcome_dashboard_payload(
                adapter
            )
        )
        return build_virtual_improvement_candidate_cycle_executive_summary(dashboard)

    @staticmethod
    def render_improvement_candidate_cycle_executive_summary_markdown(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        summary = (
            VirtualMarketRuntime.build_improvement_candidate_cycle_executive_summary(
                adapter
            )
        )
        return render_professional_summary(
            title=f"Virtual Improvement Executive Summary {adapter.surface_kind}",
            observed_at=adapter.performance_snapshot.observed_at.isoformat(),
            status=summary.outcome_state,
            summary=(
                "This local executive summary condenses the latest bounded "
                "virtual improvement cycle for Tuesday, August 25, 2026, into "
                "one governed management line without granting paper or live execution authority."
            ),
            sections=(
                (
                    "Summary",
                    (
                        f"- Summary line: `{summary.summary_line}`",
                        f"- Next action: `{summary.next_action}`",
                        f"- Blocker count: `{summary.blocker_count}`",
                    ),
                ),
            ),
            blockers=(
                ("SESSION_EXECUTIVE_BLOCKERS_PRESENT",)
                if summary.blocker_count > 0
                else ()
            ),
        )

    @staticmethod
    def publish_improvement_candidate_cycle_executive_summary(
        adapter: VirtualEvidenceSurfaceAdapter,
        *,
        root: Path,
        stamp: str,
    ) -> UserReportPaths:
        summary = (
            VirtualMarketRuntime.build_improvement_candidate_cycle_executive_summary(
                adapter
            )
        )
        paths = user_report_paths(
            root,
            "virtual_improvement_executive_summary",
            stamp,
            file_stem=(
                f"virtual_{adapter.surface_kind.lower()}_improvement_executive_summary"
            ),
        )
        write_user_report_files(
            paths,
            summary.to_payload(),
            VirtualMarketRuntime.render_improvement_candidate_cycle_executive_summary_markdown(
                adapter
            ),
        )
        return paths

    @staticmethod
    def _market_performance_evidence(
        *,
        session_id: str,
        portfolio_id: str,
        generation: int,
        configured_start_at: datetime,
        feature_warmup_start: datetime,
        last_replayed_at: datetime,
        market: str,
        timeframe: str,
        portfolio_performance: VirtualPortfolioPerformance,
        attribution_ledger: VirtualTradeAttributionLedger,
        walk_forward_report: WalkForwardReport | None,
        robustness_report: BacktestRobustnessReport | None,
        replay_state_hash: str,
        peak_margin_utilization: Decimal | None,
        critical_data_gaps: int,
        critical_data_quality_failure: bool,
        applied_duplicate_economic_events: int,
        lookahead_violations: int,
        liquidation_events: int,
        decision_reproducibility_rate: Decimal,
    ) -> MarketPerformanceEvidence:
        closed_trades = attribution_ledger.closed_trades
        observation_days = max(
            0,
            int((last_replayed_at - configured_start_at).total_seconds() // 86_400),
        )
        return MarketPerformanceEvidence(
            market=VirtualMarketRuntime._virtual_market(market),
            session_id=session_id,
            portfolio_id=portfolio_id,
            generation=generation,
            configured_start_at=configured_start_at,
            feature_warmup_start=feature_warmup_start,
            last_replayed_at=last_replayed_at,
            initial_equity_usdt=portfolio_performance.starting_equity_usdt,
            ending_equity_usdt=portfolio_performance.ending_equity_usdt,
            net_return=portfolio_performance.net_return,
            max_drawdown=portfolio_performance.max_drawdown,
            daily_sharpe=(
                portfolio_performance.portfolio_sharpe
                if portfolio_performance.sample_period_seconds == 86_400
                else None
            ),
            profit_factor=VirtualMarketRuntime._profit_factor(closed_trades),
            completed_trades=len(closed_trades),
            observation_days=observation_days,
            modeled_cost_expectancy_usdt=VirtualMarketRuntime._modeled_cost_expectancy(
                robustness_report
            ),
            oos_expectancy_usdt=VirtualMarketRuntime._oos_expectancy(
                walk_forward_report
            ),
            critical_data_gaps=critical_data_gaps,
            critical_data_quality_failure=critical_data_quality_failure,
            applied_duplicate_economic_events=applied_duplicate_economic_events,
            lookahead_violations=lookahead_violations,
            liquidation_events=liquidation_events,
            fragile_edge=bool(
                getattr(walk_forward_report, "blockers", ())
                or getattr(robustness_report, "blockers", ())
            ),
            cost_stress_evidence=VirtualMarketRuntime._cost_stress_evidence(
                robustness_report
            ),
            regime_attribution=VirtualMarketRuntime._regime_attribution(
                attribution_ledger
            ),
            peak_margin_utilization=peak_margin_utilization,
            replay_state_hash=replay_state_hash,
            decision_reproducibility_rate=decision_reproducibility_rate,
        )

    @staticmethod
    def _canonical_telemetry_snapshot(
        *,
        snapshot_id: str,
        observed_at: datetime,
        market: str,
        market_evidence: MarketPerformanceEvidence,
        attribution_ledger: VirtualTradeAttributionLedger,
        dge_metrics: DgeEffectivenessMetrics,
        blockers: tuple[str, ...],
        gate_eligible: bool,
    ) -> CanonicalTelemetrySnapshot:
        false_breakout_rate = ZERO
        if attribution_ledger.closed_trades:
            false_breakout_rate = Decimal(
                str(
                    sum(
                        1
                        for trade in attribution_ledger.closed_trades
                        if trade.false_breakout
                    )
                    / len(attribution_ledger.closed_trades)
                )
            )
        quality = (
            EvidenceQuality.SUFFICIENT if not blockers else EvidenceQuality.PARTIAL
        )
        metrics = [
            MetricEvidence(
                metric_id="virtual.net_return",
                domain=TelemetryDomain.TRADING_PERFORMANCE,
                value=market_evidence.net_return,
                unit="ratio",
                evidence_refs=(
                    market_evidence.session_id,
                    market_evidence.replay_state_hash,
                ),
            ),
            MetricEvidence(
                metric_id="virtual.max_drawdown",
                domain=TelemetryDomain.RISK_EFFECTIVENESS,
                value=market_evidence.max_drawdown,
                unit="ratio",
                evidence_refs=(
                    market_evidence.session_id,
                    market_evidence.replay_state_hash,
                ),
            ),
            MetricEvidence(
                metric_id="virtual.oos_expectancy_usdt",
                domain=TelemetryDomain.VALIDATION_EFFECTIVENESS,
                value=market_evidence.oos_expectancy_usdt,
                unit="USDT",
                evidence_refs=(
                    market_evidence.session_id,
                    market_evidence.replay_state_hash,
                ),
            ),
            MetricEvidence(
                metric_id="virtual.false_breakout_rate",
                domain=TelemetryDomain.LEARNING_EFFECTIVENESS,
                value=false_breakout_rate,
                unit="ratio",
                evidence_refs=(
                    market_evidence.session_id,
                    market_evidence.replay_state_hash,
                ),
            ),
            MetricEvidence(
                metric_id="virtual.dge_net_protection_value_usdt",
                domain=TelemetryDomain.DGE_EFFECTIVENESS,
                value=dge_metrics.net_protection_value_usdt,
                unit="USDT",
                evidence_refs=(
                    market_evidence.session_id,
                    market_evidence.replay_state_hash,
                ),
            ),
            MetricEvidence(
                metric_id="virtual.completed_trades",
                domain=TelemetryDomain.TRADING_PERFORMANCE,
                value=Decimal(market_evidence.completed_trades),
                unit="count",
                evidence_refs=(
                    market_evidence.session_id,
                    market_evidence.replay_state_hash,
                ),
            ),
        ]
        if market_evidence.daily_sharpe is not None:
            metrics.append(
                MetricEvidence(
                    metric_id="virtual.daily_sharpe",
                    domain=TelemetryDomain.TRADING_PERFORMANCE,
                    value=market_evidence.daily_sharpe,
                    unit="ratio",
                    evidence_refs=(
                        market_evidence.session_id,
                        market_evidence.replay_state_hash,
                    ),
                )
            )
        if market_evidence.profit_factor is not None:
            metrics.append(
                MetricEvidence(
                    metric_id="virtual.profit_factor",
                    domain=TelemetryDomain.TRADING_PERFORMANCE,
                    value=market_evidence.profit_factor,
                    unit="ratio",
                    evidence_refs=(
                        market_evidence.session_id,
                        market_evidence.replay_state_hash,
                    ),
                )
            )
        win_rate = VirtualMarketRuntime._win_rate(attribution_ledger.closed_trades)
        if win_rate is not None:
            metrics.append(
                MetricEvidence(
                    metric_id="virtual.win_rate",
                    domain=TelemetryDomain.TRADING_PERFORMANCE,
                    value=win_rate,
                    unit="ratio",
                    evidence_refs=(
                        market_evidence.session_id,
                        market_evidence.replay_state_hash,
                    ),
                )
            )
        average_r = VirtualMarketRuntime._average_realized_r(
            attribution_ledger.closed_trades
        )
        if average_r is not None:
            metrics.append(
                MetricEvidence(
                    metric_id="virtual.average_r",
                    domain=TelemetryDomain.TRADING_PERFORMANCE,
                    value=average_r,
                    unit="R",
                    evidence_refs=(
                        market_evidence.session_id,
                        market_evidence.replay_state_hash,
                    ),
                )
            )
        return CanonicalTelemetrySnapshot(
            telemetry_id=snapshot_id,
            observed_at=observed_at,
            market_type=VirtualMarketRuntime._market_type(market),
            metrics=tuple(metrics),
            lineage_complete=True,
            evidence_quality=quality,
            blockers=blockers,
            gate_eligible=gate_eligible,
        )

    @staticmethod
    def _dge_counterfactuals(
        *,
        session_id: str,
        blockers: tuple[str, ...],
        observed_at: datetime,
        dge_metrics: DgeEffectivenessMetrics,
    ) -> tuple[CounterfactualOutcome, ...]:
        if dge_metrics.intervention_count < 1:
            return ()
        return (
            CounterfactualOutcome(
                counterfactual_id=f"cf-no-dge:{session_id}",
                counterfactual_type=CounterfactualType.NO_DGE_INTERVENTION,
                originating_decision_id=session_id,
                snapshot_id=session_id,
                changed_dimension="DGE_INTERVENTION",
                retained_safety_controls=(
                    "VIRTUAL_MARKET_ONLY",
                    "RESEARCH_ONLY",
                    "LIVE_ORDER_BLOCKED",
                ),
                hypothetical_decision_state="VIRTUAL_RESEARCH_NO_DGE",
                hypothetical_economic_outcome_usdt=(
                    dge_metrics.counterfactual_expectancy_delta_usdt
                ),
                methodology=(
                    "Virtual-market DGE shadow comparison against the no-intervention path."
                ),
                assumptions=tuple(
                    dict.fromkeys(
                        (
                            "counterfactual evidence is advisory, not execution authority",
                            "capital protection remains research-only",
                            *(f"blocker:{blocker}" for blocker in blockers),
                        )
                    )
                ),
                evidence_quality=(
                    EvidenceQuality.SUFFICIENT
                    if dge_metrics.sample_size >= 5
                    else EvidenceQuality.PARTIAL
                ),
                confidence=min(ONE, Decimal(dge_metrics.sample_size) / Decimal("10")),
                changed_rule_id="DGE_PROTECTIVE_BLOCK",
            ),
        )

    @staticmethod
    def _blocker_effectiveness_records(
        *,
        session_id: str,
        blockers: tuple[str, ...],
        dge_metrics: DgeEffectivenessMetrics,
    ) -> tuple[BlockerEffectivenessRecord, ...]:
        if dge_metrics.intervention_count < 1:
            return ()
        outcome_class = (
            BlockerOutcome.PROTECTIVE_BLOCK
            if dge_metrics.net_protection_value_usdt > ZERO
            else (
                BlockerOutcome.FALSE_BLOCK
                if dge_metrics.false_block_count > 0
                else BlockerOutcome.NEUTRAL_BLOCK
            )
        )
        blocker_id = next(
            (blocker for blocker in blockers if "DGE" in blocker),
            "DGE_PROTECTIVE_BLOCK",
        )
        return (
            BlockerEffectivenessRecord(
                blocker_id=blocker_id,
                blocker_type="DGE",
                policy_id="virtual-dge-counterfactual-v1",
                decision_id=session_id,
                outcome_class=outcome_class,
                evaluation_horizon_minutes=max(1, dge_metrics.sample_size * 60),
                evidence_quality=(
                    EvidenceQuality.SUFFICIENT
                    if dge_metrics.sample_size >= 5
                    else EvidenceQuality.PARTIAL
                ),
                counterfactual_id=f"cf-no-dge:{session_id}",
                avoided_loss_usdt=dge_metrics.loss_avoided_usdt,
                foregone_profit_usdt=dge_metrics.profit_missed_usdt,
                changed_rule_id="DGE_PROTECTIVE_BLOCK",
            ),
        )

    @staticmethod
    def _outcome_attributions(
        *,
        session_id: str,
        market: str,
        attribution_ledger: VirtualTradeAttributionLedger,
        dge_metrics: DgeEffectivenessMetrics,
    ) -> tuple[OutcomeAttribution, ...]:
        closed_trades = attribution_ledger.closed_trades
        if not closed_trades:
            return ()
        market_effect = sum((trade.net_pnl_usdt for trade in closed_trades), ZERO)
        fee_effect = sum((trade.fee_cost_usdt for trade in closed_trades), ZERO)
        slippage_effect = sum(
            (trade.slippage_cost_usdt for trade in closed_trades),
            ZERO,
        )
        funding_effect = sum(
            (trade.funding_cost_usdt for trade in closed_trades),
            ZERO,
        )
        strategy_effect = sum(
            (
                view.expectancy_usdt * Decimal(view.trade_count)
                for view in attribution_ledger.by_strategy_regime
                if view.average_realized_r_multiple > ZERO
            ),
            ZERO,
        )
        governance_effect = dge_metrics.net_protection_value_usdt
        opportunity_cost = dge_metrics.profit_missed_usdt
        avoided_loss = dge_metrics.loss_avoided_usdt
        return (
            OutcomeAttribution(
                attribution_id=f"attribution:execution-quality:{session_id}",
                decision_id=session_id,
                market_type=VirtualMarketRuntime._market_type(market),
                attribution_method=AttributionMethod.OBSERVATIONAL_ESTIMATE,
                evidence_quality=EvidenceQuality.PARTIAL,
                confidence=min(ONE, Decimal(len(closed_trades)) / Decimal("10")),
                assumptions=(
                    "virtual closed-trade costs are modeled evidence",
                    "execution effects are research-only and non-causal",
                ),
                opportunity_cost_type=OpportunityCostType.EXECUTION,
                market_effect_usdt=market_effect,
                execution_effect_usdt=-(fee_effect + slippage_effect + funding_effect),
                fee_effect_usdt=-fee_effect,
                slippage_effect_usdt=-slippage_effect,
                funding_effect_usdt=-funding_effect,
                opportunity_cost_usdt=fee_effect + slippage_effect + funding_effect,
            ),
            OutcomeAttribution(
                attribution_id=f"attribution:governance:{session_id}",
                decision_id=session_id,
                market_type=VirtualMarketRuntime._market_type(market),
                attribution_method=AttributionMethod.COUNTERFACTUAL_DELTA,
                evidence_quality=(
                    EvidenceQuality.SUFFICIENT
                    if dge_metrics.sample_size >= 5
                    else EvidenceQuality.PARTIAL
                ),
                confidence=min(ONE, Decimal(dge_metrics.sample_size) / Decimal("10")),
                assumptions=(
                    "DGE attribution uses no-intervention virtual counterfactual",
                    "governance effects remain advisory evidence",
                ),
                opportunity_cost_type=OpportunityCostType.BLOCKER,
                strategy_effect_usdt=strategy_effect,
                governance_effect_usdt=governance_effect,
                decision_effect_usdt=dge_metrics.counterfactual_expectancy_delta_usdt,
                avoided_loss_usdt=avoided_loss,
                foregone_profit_usdt=opportunity_cost,
                opportunity_cost_usdt=opportunity_cost,
            ),
        )

    @staticmethod
    def _decision_effectiveness_records(
        *,
        session_id: str,
        market: str,
        blockers: tuple[str, ...],
        dge_metrics: DgeEffectivenessMetrics,
    ) -> tuple[DecisionEffectivenessRecord, ...]:
        if dge_metrics.intervention_count < 1:
            return ()
        effectiveness = (
            DecisionEffectivenessClass.BLOCKED_AVOIDED_LOSS
            if dge_metrics.net_protection_value_usdt > ZERO
            else (
                DecisionEffectivenessClass.BLOCKED_FOREGONE_PROFIT
                if dge_metrics.false_block_count > 0
                else DecisionEffectivenessClass.INDETERMINATE
            )
        )
        return (
            DecisionEffectivenessRecord(
                decision_id=session_id,
                market_type=VirtualMarketRuntime._market_type(market),
                effectiveness_class=effectiveness,
                evidence_quality=(
                    EvidenceQuality.SUFFICIENT
                    if dge_metrics.sample_size >= 5
                    else EvidenceQuality.PARTIAL
                ),
                observation_window_minutes=max(1, dge_metrics.sample_size * 60),
                counterfactual_refs=(f"cf-no-dge:{session_id}",),
                attribution_refs=(),
            ),
        )

    @staticmethod
    def _missed_opportunity_record(
        *,
        request: VirtualRuntimeRequest,
        blockers: tuple[str, ...],
        observed_at: datetime,
        counterfactual_trade: VirtualClosedTradeRecord | None,
    ) -> MissedOpportunityRecord:
        if counterfactual_trade is None:
            return MissedOpportunityRecord(
                signal_id=request.candidate_id,
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                regime=request.regime,
                symbol=request.symbol,
                market=request.market,
                direction=TradeDirection(
                    (request.position_side or VirtualPositionSide.LONG).value
                ),
                rejected_at=observed_at,
                blockers=blockers,
                entry_reason=request.entry_reason,
                dge_status=request.dge_decision,
                pre_veto_observation_id=(
                    f"pre-veto:{request.market.lower()}:{request.snapshot_id}:"
                    f"{request.candidate_id}"
                ),
                counterfactual_result=MissedOpportunityCategory.INSUFFICIENT_EVIDENCE,
            )
        category = VirtualMarketRuntime._missed_opportunity_category(
            counterfactual_trade
        )
        improvement_candidate_id = (
            f"improvement:{request.strategy_id.lower()}:{request.regime.lower()}:{request.candidate_id.lower()}"
            if category is MissedOpportunityCategory.BAD_BLOCK
            else None
        )
        return MissedOpportunityRecord(
            signal_id=request.candidate_id,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            regime=request.regime,
            symbol=request.symbol,
            market=request.market,
            direction=counterfactual_trade.direction,
            rejected_at=observed_at,
            blockers=blockers,
            entry_reason=request.entry_reason,
            dge_status=request.dge_decision,
            pre_veto_observation_id=(
                f"pre-veto:{request.market.lower()}:{request.snapshot_id}:"
                f"{request.candidate_id}"
            ),
            counterfactual_result=category,
            forward_trade_outcome=VirtualMarketRuntime._trade_outcome(
                counterfactual_trade
            ),
            forward_realized_r=counterfactual_trade.realized_r_multiple,
            forward_net_pnl=counterfactual_trade.net_pnl_usdt,
            improvement_candidate_id=improvement_candidate_id,
        )

    @staticmethod
    def _missed_opportunity_category(
        counterfactual_trade: VirtualClosedTradeRecord,
    ) -> MissedOpportunityCategory:
        if counterfactual_trade.realized_r_multiple > ZERO:
            return MissedOpportunityCategory.BAD_BLOCK
        if counterfactual_trade.realized_r_multiple < ZERO:
            return MissedOpportunityCategory.GOOD_BLOCK
        return MissedOpportunityCategory.NEUTRAL_BLOCK

    @staticmethod
    def _trade_outcome(counterfactual_trade: VirtualClosedTradeRecord) -> TradeOutcome:
        return TradeOutcome(
            trade_id=counterfactual_trade.trade_id,
            strategy_id=counterfactual_trade.attribution.strategy_id,
            strategy_version=counterfactual_trade.attribution.strategy_version,
            regime=counterfactual_trade.attribution.regime,
            symbol=counterfactual_trade.attribution.symbol,
            market=counterfactual_trade.attribution.market,
            direction=counterfactual_trade.direction,
            entry_time=counterfactual_trade.entry_time,
            exit_time=counterfactual_trade.exit_time,
            entry_price=counterfactual_trade.entry_price,
            exit_price=counterfactual_trade.exit_price,
            risk_at_entry=counterfactual_trade.risk_at_entry,
            planned_rr=ZERO,
            realized_rr=counterfactual_trade.realized_r_multiple,
            gross_pnl=counterfactual_trade.gross_pnl_usdt,
            fee_cost=counterfactual_trade.fee_cost_usdt,
            slippage_cost=counterfactual_trade.slippage_cost_usdt,
            funding_cost=counterfactual_trade.funding_cost_usdt,
            net_pnl=counterfactual_trade.net_pnl_usdt,
            mfe=counterfactual_trade.maximum_favorable_excursion,
            mae=counterfactual_trade.maximum_adverse_excursion,
            dge_status=counterfactual_trade.dge_decision,
            entry_reason=counterfactual_trade.entry_reason,
            exit_reason=counterfactual_trade.exit_reason,
            blocker_history=(),
        )

    @staticmethod
    def _missed_opportunity_candidates(
        *,
        session_id: str,
        market: str,
        missed_opportunity: MissedOpportunityRecord,
    ) -> tuple[ImprovementCandidate, ...]:
        if (
            missed_opportunity.counterfactual_result
            is not MissedOpportunityCategory.BAD_BLOCK
            or missed_opportunity.forward_net_pnl is None
            or missed_opportunity.improvement_candidate_id is None
        ):
            return ()
        return (
            ImprovementCandidate(
                candidate_id=missed_opportunity.improvement_candidate_id,
                originating_findings=(f"missed-opportunity:{session_id}",),
                affected_component="VIRTUAL_MARKET_NO_TRADE_GATE",
                affected_markets=(VirtualMarketRuntime._market_type(market),),
                affected_regimes=(missed_opportunity.regime,),
                baseline_metrics=(
                    MetricEvidence(
                        metric_id="baseline.no_trade_counterfactual_pnl",
                        domain=TelemetryDomain.OPPORTUNITY_COST,
                        value=missed_opportunity.forward_net_pnl,
                        unit="USDT",
                        evidence_refs=(session_id,),
                    ),
                ),
                observed_metrics=(
                    MetricEvidence(
                        metric_id="observed.no_trade_realized_pnl",
                        domain=TelemetryDomain.OPPORTUNITY_COST,
                        value=ZERO,
                        unit="USDT",
                        evidence_refs=(session_id,),
                    ),
                ),
                sample_size=1,
                evidence_quality=EvidenceQuality.PARTIAL,
                confidence=Decimal("0.55"),
                hypothesis=(
                    f"Blocked {missed_opportunity.strategy_id} signal in "
                    f"{missed_opportunity.regime} may represent a false veto."
                ),
                proposed_experiment=(
                    "Replay the blocked setup, inspect blocker lineage, and rerun "
                    "bounded virtual validation before any promotion."
                ),
                opportunity_cost_delta_usdt=missed_opportunity.forward_net_pnl,
            ),
        )

    @staticmethod
    def _no_trade_counterfactuals(
        *,
        session_id: str,
        blockers: tuple[str, ...],
        missed_opportunity: MissedOpportunityRecord,
    ) -> tuple[CounterfactualOutcome, ...]:
        if missed_opportunity.forward_net_pnl is None:
            return ()
        return (
            CounterfactualOutcome(
                counterfactual_id=f"cf-blocker-ablation:{session_id}",
                counterfactual_type=CounterfactualType.BLOCKER_ABLATION,
                originating_decision_id=session_id,
                snapshot_id=session_id,
                changed_dimension="BLOCKER_RESOLUTION",
                retained_safety_controls=(
                    "VIRTUAL_MARKET_ONLY",
                    "RESEARCH_ONLY",
                    "LIVE_ORDER_BLOCKED",
                ),
                hypothetical_decision_state="VIRTUAL_ENTRY_ALLOWED",
                hypothetical_economic_outcome_usdt=missed_opportunity.forward_net_pnl,
                methodology="Virtual missed-opportunity replay under blocker ablation.",
                assumptions=tuple(
                    dict.fromkeys(
                        (
                            "counterfactual blocker removal is advisory evidence",
                            *(f"blocker:{blocker}" for blocker in blockers),
                        )
                    )
                ),
                evidence_quality=EvidenceQuality.PARTIAL,
                confidence=Decimal("0.55"),
                changed_rule_id=blockers[0] if blockers else "UNKNOWN_BLOCKER",
            ),
        )

    @staticmethod
    def _no_trade_blocker_effectiveness(
        *,
        session_id: str,
        blockers: tuple[str, ...],
        missed_opportunity: MissedOpportunityRecord,
    ) -> tuple[BlockerEffectivenessRecord, ...]:
        blocker_id = blockers[0] if blockers else "UNKNOWN_BLOCKER"
        category = missed_opportunity.counterfactual_result
        outcome_class = {
            MissedOpportunityCategory.BAD_BLOCK: BlockerOutcome.FALSE_BLOCK,
            MissedOpportunityCategory.GOOD_BLOCK: BlockerOutcome.PROTECTIVE_BLOCK,
            MissedOpportunityCategory.NEUTRAL_BLOCK: BlockerOutcome.NEUTRAL_BLOCK,
            MissedOpportunityCategory.INSUFFICIENT_EVIDENCE: BlockerOutcome.INSUFFICIENT_EVIDENCE,
        }[category]
        return (
            BlockerEffectivenessRecord(
                blocker_id=blocker_id,
                blocker_type="NO_TRADE",
                policy_id="virtual-no-trade-opportunity-v1",
                decision_id=session_id,
                outcome_class=outcome_class,
                evaluation_horizon_minutes=60,
                evidence_quality=(
                    EvidenceQuality.PARTIAL
                    if category is not MissedOpportunityCategory.INSUFFICIENT_EVIDENCE
                    else EvidenceQuality.INSUFFICIENT
                ),
                counterfactual_id=f"cf-blocker-ablation:{session_id}",
                avoided_loss_usdt=(
                    abs(missed_opportunity.forward_net_pnl)
                    if category is MissedOpportunityCategory.GOOD_BLOCK
                    and missed_opportunity.forward_net_pnl is not None
                    else None
                ),
                foregone_profit_usdt=(
                    missed_opportunity.forward_net_pnl
                    if category is MissedOpportunityCategory.BAD_BLOCK
                    and missed_opportunity.forward_net_pnl is not None
                    else None
                ),
                changed_rule_id=blocker_id,
            ),
        )

    @staticmethod
    def _no_trade_decision_effectiveness(
        *,
        session_id: str,
        market: str,
        missed_opportunity: MissedOpportunityRecord,
    ) -> tuple[DecisionEffectivenessRecord, ...]:
        category = missed_opportunity.counterfactual_result
        effectiveness = {
            MissedOpportunityCategory.BAD_BLOCK: DecisionEffectivenessClass.REJECTED_WOULD_PROFIT,
            MissedOpportunityCategory.GOOD_BLOCK: DecisionEffectivenessClass.REJECTED_WOULD_LOSE,
            MissedOpportunityCategory.NEUTRAL_BLOCK: DecisionEffectivenessClass.INDETERMINATE,
            MissedOpportunityCategory.INSUFFICIENT_EVIDENCE: DecisionEffectivenessClass.INDETERMINATE,
        }[category]
        refs = (
            (f"cf-blocker-ablation:{session_id}",)
            if missed_opportunity.forward_net_pnl is not None
            else ()
        )
        return (
            DecisionEffectivenessRecord(
                decision_id=session_id,
                market_type=VirtualMarketRuntime._market_type(market),
                effectiveness_class=effectiveness,
                evidence_quality=(
                    EvidenceQuality.PARTIAL
                    if category is not MissedOpportunityCategory.INSUFFICIENT_EVIDENCE
                    else EvidenceQuality.INSUFFICIENT
                ),
                observation_window_minutes=60,
                counterfactual_refs=refs or (f"cf-blocker-ablation:{session_id}",),
                attribution_refs=(),
            ),
        )

    @staticmethod
    def _no_trade_attributions(
        *,
        session_id: str,
        market: str,
        missed_opportunity: MissedOpportunityRecord,
    ) -> tuple[OutcomeAttribution, ...]:
        if missed_opportunity.forward_net_pnl is None:
            return ()
        cost_type = OpportunityCostType.BLOCKER
        first_blocker = next(iter(missed_opportunity.blockers), "")
        if "RISK" in first_blocker:
            cost_type = OpportunityCostType.RISK_VETO
        elif "VALIDATION" in first_blocker or "OOS" in first_blocker:
            cost_type = OpportunityCostType.VALIDATION_VETO
        elif "GOV" in first_blocker or "DGE" in first_blocker:
            cost_type = OpportunityCostType.GOVERNANCE_VETO
        pnl = missed_opportunity.forward_net_pnl
        return (
            OutcomeAttribution(
                attribution_id=f"attribution:no-trade:{session_id}",
                decision_id=session_id,
                market_type=VirtualMarketRuntime._market_type(market),
                attribution_method=AttributionMethod.COUNTERFACTUAL_DELTA,
                evidence_quality=EvidenceQuality.PARTIAL,
                confidence=Decimal("0.55"),
                assumptions=(
                    "no-trade attribution is derived from virtual counterfactual replay",
                    "veto opportunity cost remains research-only evidence",
                ),
                opportunity_cost_type=cost_type,
                market_effect_usdt=pnl,
                decision_effect_usdt=pnl,
                opportunity_cost_usdt=(pnl if pnl > ZERO else abs(pnl)),
                avoided_loss_usdt=(abs(pnl) if pnl < ZERO else None),
                foregone_profit_usdt=(pnl if pnl > ZERO else None),
            ),
        )

    @staticmethod
    def _no_trade_telemetry_snapshot(
        *,
        snapshot_id: str,
        observed_at: datetime,
        market: str,
        missed_opportunity: MissedOpportunityRecord,
        blockers: tuple[str, ...],
    ) -> CanonicalTelemetrySnapshot:
        counterfactual_pnl = missed_opportunity.forward_net_pnl or ZERO
        return CanonicalTelemetrySnapshot(
            telemetry_id=snapshot_id,
            observed_at=observed_at,
            market_type=VirtualMarketRuntime._market_type(market),
            metrics=(
                MetricEvidence(
                    metric_id="virtual.no_trade_counterfactual_pnl_usdt",
                    domain=TelemetryDomain.OPPORTUNITY_COST,
                    value=counterfactual_pnl,
                    unit="USDT",
                    evidence_refs=(snapshot_id,),
                ),
                MetricEvidence(
                    metric_id="virtual.no_trade_counterfactual_r",
                    domain=TelemetryDomain.DECISION_EFFECTIVENESS,
                    value=missed_opportunity.forward_realized_r or ZERO,
                    unit="R",
                    evidence_refs=(snapshot_id,),
                ),
            ),
            lineage_complete=True,
            evidence_quality=(
                EvidenceQuality.PARTIAL
                if missed_opportunity.counterfactual_result
                is not MissedOpportunityCategory.INSUFFICIENT_EVIDENCE
                else EvidenceQuality.INSUFFICIENT
            ),
            blockers=blockers,
            gate_eligible=False,
        )

    @staticmethod
    def _acceptance_result(
        *,
        snapshot_id: str,
        market: str,
        profitability_evidence: TwoStageProfitabilityEvidence,
        walk_forward_report: WalkForwardReport | None,
        robustness_report: BacktestRobustnessReport | None,
        blockers: tuple[str, ...],
    ) -> PerformanceAcceptanceResult:
        wf_status = (
            AcceptanceGateStatus.PASS
            if walk_forward_report is not None
            and not getattr(walk_forward_report, "blockers", ())
            else AcceptanceGateStatus.BLOCKED
        )
        robustness_status = (
            AcceptanceGateStatus.PASS
            if robustness_report is not None
            and not getattr(robustness_report, "blockers", ())
            else AcceptanceGateStatus.BLOCKED
        )
        return PerformanceAcceptanceResult(
            result_id=f"acceptance:{snapshot_id}",
            market_type=VirtualMarketRuntime._market_type(market),
            gate_results={
                "RESEARCH_CANDIDATE": VirtualMarketRuntime._acceptance_gate_status(
                    profitability_evidence.research_candidate.status
                ),
                "FINAL_ACCEPTANCE": VirtualMarketRuntime._acceptance_gate_status(
                    profitability_evidence.final_acceptance.status
                ),
                "WALK_FORWARD": wf_status,
                "ROBUSTNESS": robustness_status,
            },
            evidence_refs=tuple(
                dict.fromkeys(
                    (
                        *profitability_evidence.research_candidate.evidence_refs,
                        *profitability_evidence.final_acceptance.evidence_refs,
                        getattr(walk_forward_report, "report_id", "WF_MISSING"),
                    )
                )
            ),
            blockers=blockers,
            gate_eligible=not blockers,
        )

    @staticmethod
    def _no_trade_acceptance_result(
        *,
        snapshot: PerformanceEvidenceSnapshot,
        market_type: MarketType,
        blockers: tuple[str, ...],
    ) -> PerformanceAcceptanceResult:
        outcome = snapshot.decision_outcome
        missed_opportunity_evaluated = bool(snapshot.counterfactuals)
        blocker_effective = bool(snapshot.blocker_effectiveness)
        measurable = outcome.measurable_no_trade
        return PerformanceAcceptanceResult(
            result_id=f"acceptance:{snapshot.snapshot_id}:no-trade",
            market_type=market_type,
            gate_results={
                "NO_TRADE_MEASUREMENT": (
                    AcceptanceGateStatus.PASS
                    if measurable
                    else AcceptanceGateStatus.BLOCKED
                ),
                "MISSED_OPPORTUNITY": (
                    AcceptanceGateStatus.PASS
                    if missed_opportunity_evaluated
                    else AcceptanceGateStatus.BLOCKED
                ),
                "BLOCKER_EFFECTIVENESS": (
                    AcceptanceGateStatus.PASS
                    if blocker_effective
                    else AcceptanceGateStatus.BLOCKED
                ),
            },
            evidence_refs=tuple(
                dict.fromkeys(
                    (
                        snapshot.snapshot_id,
                        *(
                            counterfactual.counterfactual_id
                            for counterfactual in snapshot.counterfactuals
                        ),
                    )
                )
            ),
            blockers=blockers,
            gate_eligible=False,
        )

    @staticmethod
    def _acceptance_gate_status(status: AcceptanceStatus) -> AcceptanceGateStatus:
        if status is AcceptanceStatus.PASS:
            return AcceptanceGateStatus.PASS
        if status is AcceptanceStatus.NOT_EVALUATED:
            return AcceptanceGateStatus.INFORMATIONAL_ONLY
        if status in {
            AcceptanceStatus.DATA_UNAVAILABLE,
            AcceptanceStatus.NON_REPRODUCIBLE,
        }:
            return AcceptanceGateStatus.BLOCKED
        return AcceptanceGateStatus.FAIL

    @staticmethod
    def _stage_improvement_candidate(
        adapter: VirtualEvidenceSurfaceAdapter,
        candidate: ImprovementCandidate,
    ) -> VirtualStagedImprovementCandidate:
        blockers = VirtualMarketRuntime._improvement_staging_blockers(candidate)
        promotion_status = (
            ValidationStatus.STAGED_CANDIDATE
            if not blockers
            else ValidationStatus.RESEARCH_ONLY
        )
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    adapter.snapshot_id,
                    adapter.telemetry_snapshot.telemetry_id,
                    *(result.result_id for result in adapter.acceptance_results),
                    candidate.candidate_id,
                )
            )
        )
        return VirtualStagedImprovementCandidate(
            stage_id=(
                f"virtual-improvement-stage:{adapter.snapshot_id}:{candidate.candidate_id}"
            ),
            snapshot_id=adapter.snapshot_id,
            surface_kind=adapter.surface_kind,
            candidate=candidate,
            evidence_refs=evidence_refs,
            assurance_artifact_refs=VirtualMarketRuntime._improvement_queue_assurance_artifact_refs(
                adapter.surface_kind
            ),
            blockers=blockers,
            promotion_status=promotion_status,
        )

    @staticmethod
    def _improvement_research_work_item(
        staged_candidate: VirtualStagedImprovementCandidate,
        *,
        triage_reason: str,
    ) -> VirtualImprovementResearchWorkItem:
        candidate = staged_candidate.candidate
        return VirtualImprovementResearchWorkItem(
            work_id=f"virtual-improvement-work:{staged_candidate.stage_id}",
            stage_id=staged_candidate.stage_id,
            candidate_id=candidate.candidate_id,
            snapshot_id=staged_candidate.snapshot_id,
            surface_kind=staged_candidate.surface_kind,
            affected_component=candidate.affected_component,
            assurance_artifact_refs=staged_candidate.assurance_artifact_refs,
            required_artifacts=(
                "runtime/artifacts/user_reports/virtual_evidence/"
                f"virtual_{staged_candidate.surface_kind.lower()}_evidence_latest.json",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_candidates/"
                    f"virtual_{staged_candidate.surface_kind.lower()}_improvement_candidates_latest.json"
                ),
            ),
            blockers=staged_candidate.blockers,
            triage_reason=triage_reason,
            priority=(
                "P0"
                if staged_candidate.promotion_status
                is ValidationStatus.STAGED_CANDIDATE
                else "P1"
            ),
        )

    @staticmethod
    def _improvement_queue_triage_reason(
        adapter: VirtualEvidenceSurfaceAdapter,
    ) -> str:
        blockers = tuple(
            dict.fromkeys(
                (
                    *adapter.blockers,
                    *(
                        blocker
                        for result in adapter.acceptance_results
                        for blocker in result.blockers
                    ),
                )
            )
        )
        metric_ids = {metric.metric_id for metric in adapter.telemetry_snapshot.metrics}
        return derive_virtual_runtime_priority_signal(
            surface_kind=adapter.surface_kind,
            status=adapter.performance_snapshot.status.value,
            blockers=blockers,
            has_counterfactual_pnl="virtual.no_trade_counterfactual_pnl_usdt"
            in metric_ids,
            has_counterfactual_r="virtual.no_trade_counterfactual_r" in metric_ids,
            has_net_return="virtual.net_return" in metric_ids,
            has_max_drawdown="virtual.max_drawdown" in metric_ids,
            has_oos_expectancy="virtual.oos_expectancy_usdt" in metric_ids,
        )

    @staticmethod
    def _improvement_research_order_key(
        staged_candidate: VirtualStagedImprovementCandidate,
    ) -> tuple[int, Decimal, Decimal, int, str]:
        candidate = staged_candidate.candidate
        priority_rank = (
            0
            if staged_candidate.promotion_status is ValidationStatus.STAGED_CANDIDATE
            else 1
        )
        opportunity_cost = candidate.opportunity_cost_delta_usdt or ZERO
        confidence = candidate.confidence
        sample_size = candidate.sample_size
        return (
            priority_rank,
            -opportunity_cost,
            -confidence,
            -sample_size,
            candidate.candidate_id,
        )

    @staticmethod
    def _improvement_queue_assurance_artifact_refs(
        surface_kind: str,
    ) -> tuple[str, ...]:
        normalized_surface_kind = surface_kind.lower()
        return (
            (
                "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                f"virtual_{normalized_surface_kind}_improvement_queue_assurance_latest.json"
            ),
            (
                "runtime/reports/virtual_improvement_queue_assurance/"
                f"virtual_{normalized_surface_kind}_improvement_queue_assurance_latest.md"
            ),
        )

    @staticmethod
    def _improvement_queue_policy_evaluation(
        queue: VirtualImprovementResearchQueue,
        item: VirtualImprovementResearchWorkItem,
    ) -> PolicyEvaluationRecord:
        handoff = item.normalized_handoff_payload()
        blockers = tuple(
            str(value) for value in cast(tuple[object, ...], handoff["blocker_refs"])
        )
        evidence_refs = cast(tuple[object, ...], handoff["evidence_refs"])
        return PolicyEvaluationRecord(
            evaluation_id=f"evaluation:{item.work_id}",
            policy_id="virtual_improvement_research_queue",
            policy_version="virtual-runtime-improvement-queue/v1",
            result=(
                TrustAssuranceResult.PASSED
                if not blockers
                else TrustAssuranceResult.WARN
            ),
            evidence_refs=tuple(str(value) for value in evidence_refs),
            blockers=blockers,
            action_refs=(
                f"review:{item.candidate_id}",
                f"queue:{queue.queue_id}",
            ),
            review_required=True,
        )

    @staticmethod
    def _improvement_queue_uncertainty(
        *,
        queue: VirtualImprovementResearchQueue,
        policy_evaluations: tuple[PolicyEvaluationRecord, ...],
    ) -> UncertaintyAssessmentRecord:
        reasons = (
            ("ASSURANCE_READY_FOR_RESEARCH_REVIEW",)
            if queue.status == "READY"
            else ("ASSURANCE_BLOCKERS_REQUIRE_RESEARCH_REVIEW",)
        )
        evidence_refs = tuple(
            dict.fromkeys(
                ref
                for evaluation in policy_evaluations
                for ref in evaluation.evidence_refs
            )
        )
        return UncertaintyAssessmentRecord(
            assessment_id=f"uncertainty:{queue.queue_id}",
            level=(
                UncertaintyLevel.LOW
                if queue.status == "READY"
                else UncertaintyLevel.MEDIUM
            ),
            reasons=reasons,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _improvement_queue_provenance(
        *,
        queue: VirtualImprovementResearchQueue,
        policy_evaluations: tuple[PolicyEvaluationRecord, ...],
        uncertainty: UncertaintyAssessmentRecord,
        observed_at: datetime,
    ) -> DecisionProvenanceRecord:
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    queue.queue_id,
                    queue.snapshot_id,
                    *(
                        ref
                        for evaluation in policy_evaluations
                        for ref in evaluation.evidence_refs
                    ),
                )
            )
        )
        return DecisionProvenanceRecord(
            decision_id=f"decision:{queue.queue_id}",
            decision_kind="VIRTUAL_IMPROVEMENT_RESEARCH_QUEUE",
            observed_at=observed_at,
            final_action=queue.status,
            evidence_refs=evidence_refs,
            policy_evaluation_refs=tuple(
                evaluation.evaluation_id for evaluation in policy_evaluations
            ),
            uncertainty_ref=uncertainty.assessment_id,
            blockers=queue.blockers,
        )

    @staticmethod
    def _improvement_queue_evidence_graph(
        queue: VirtualImprovementResearchQueue,
    ) -> EvidenceGraphLiteRecord:
        nodes = [
            EvidenceGraphNode(
                node_id=f"queue:{queue.queue_id}",
                node_type="QUEUE",
                ref=queue.queue_id,
            )
        ]
        edges: list[EvidenceGraphEdge] = []
        for item in queue.items:
            work_node_id = f"work:{item.work_id}"
            nodes.append(
                EvidenceGraphNode(
                    node_id=work_node_id,
                    node_type="WORK_ITEM",
                    ref=item.work_id,
                )
            )
            edges.append(
                EvidenceGraphEdge(
                    source=f"queue:{queue.queue_id}",
                    relation="QUEUES",
                    target=work_node_id,
                )
            )
            for index, ref in enumerate(
                cast(
                    tuple[object, ...],
                    item.normalized_handoff_payload()["evidence_refs"],
                )
            ):
                evidence_ref = str(ref)
                node_id = f"evidence:{item.work_id}:{index}"
                nodes.append(
                    EvidenceGraphNode(
                        node_id=node_id,
                        node_type="EVIDENCE_REF",
                        ref=evidence_ref,
                    )
                )
                edges.append(
                    EvidenceGraphEdge(
                        source=work_node_id,
                        relation="SUPPORTS",
                        target=node_id,
                    )
                )
        return EvidenceGraphLiteRecord(
            graph_id=f"graph:{queue.queue_id}",
            nodes=tuple(nodes),
            edges=tuple(edges),
        )

    @staticmethod
    def _improvement_staging_blockers(
        candidate: ImprovementCandidate,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if candidate.evidence_quality is EvidenceQuality.INSUFFICIENT:
            blockers.append("IMPROVEMENT_EVIDENCE_INSUFFICIENT")
        if candidate.sample_size < 1:
            blockers.append("IMPROVEMENT_SAMPLE_INVALID")
        return tuple(dict.fromkeys(blockers))

    @staticmethod
    def _improvement_candidates(
        *,
        attribution_ledger: VirtualTradeAttributionLedger,
        market: str,
        snapshot_id: str,
        modeled_cost_expectancy_usdt: Decimal,
        oos_expectancy_usdt: Decimal,
        walk_forward_report: WalkForwardReport | None,
        robustness_report: BacktestRobustnessReport | None,
    ) -> tuple[ImprovementCandidate, ...]:
        if walk_forward_report is None or robustness_report is None:
            return ()
        version_by_strategy = {
            trade.attribution.strategy_id: trade.attribution.strategy_version
            for trade in attribution_ledger.closed_trades
        }
        grouped: dict[str, list[VirtualTradeAttributionAggregate]] = {}
        for view in attribution_ledger.by_strategy_regime:
            if view.strategy_id is None or view.regime is None:
                continue
            grouped.setdefault(view.strategy_id, []).append(view)
        candidates: list[ImprovementCandidate] = []
        market_type = VirtualMarketRuntime._market_type(market)
        for strategy_id in sorted(grouped):
            views = grouped[strategy_id]
            positive = [
                view for view in views if view.average_realized_r_multiple > ZERO
            ]
            negative = [
                view for view in views if view.average_realized_r_multiple < ZERO
            ]
            if not positive or not negative:
                continue
            reference = max(
                positive,
                key=lambda item: (
                    item.average_realized_r_multiple,
                    item.trade_count,
                    item.regime or "",
                ),
            )
            strategy_version = version_by_strategy.get(strategy_id, "1")
            for underperforming in sorted(negative, key=lambda item: item.regime or ""):
                regime = underperforming.regime or "UNKNOWN"
                reference_regime = reference.regime or "UNKNOWN"
                sample_size = underperforming.trade_count
                confidence = min(ONE, Decimal(sample_size) / Decimal("10"))
                candidates.append(
                    ImprovementCandidate(
                        candidate_id=(
                            f"improvement:{strategy_id.lower()}:{strategy_version.lower()}:{regime.lower()}"
                        ),
                        originating_findings=(
                            getattr(walk_forward_report, "report_id", "WF_MISSING"),
                            f"robustness:{getattr(robustness_report.bootstrap, 'seed', 0)}",
                        ),
                        affected_component="VIRTUAL_MARKET_STRATEGY_RUNTIME",
                        affected_rule="STRATEGY_REGIME_GATING",
                        affected_markets=(market_type,),
                        affected_regimes=(regime, reference_regime),
                        baseline_metrics=(
                            MetricEvidence(
                                metric_id="baseline.expectancy_usdt",
                                domain=TelemetryDomain.TRADING_PERFORMANCE,
                                value=underperforming.expectancy_usdt,
                                unit="USDT",
                                evidence_refs=(snapshot_id,),
                            ),
                            MetricEvidence(
                                metric_id="baseline.average_r",
                                domain=TelemetryDomain.STRATEGY_DRIFT,
                                value=underperforming.average_realized_r_multiple,
                                unit="R",
                                evidence_refs=(snapshot_id,),
                            ),
                        ),
                        observed_metrics=(
                            MetricEvidence(
                                metric_id="observed.reference_expectancy_usdt",
                                domain=TelemetryDomain.REGIME_DEGRADATION,
                                value=reference.expectancy_usdt,
                                unit="USDT",
                                evidence_refs=(snapshot_id,),
                            ),
                            MetricEvidence(
                                metric_id="observed.oos_expectancy_usdt",
                                domain=TelemetryDomain.VALIDATION_EFFECTIVENESS,
                                value=oos_expectancy_usdt,
                                unit="USDT",
                                evidence_refs=(snapshot_id,),
                            ),
                            MetricEvidence(
                                metric_id="observed.modeled_cost_expectancy_usdt",
                                domain=TelemetryDomain.EXECUTION_QUALITY,
                                value=modeled_cost_expectancy_usdt,
                                unit="USDT",
                                evidence_refs=(snapshot_id,),
                            ),
                        ),
                        sample_size=sample_size,
                        evidence_quality=EvidenceQuality.PARTIAL,
                        confidence=confidence,
                        hypothesis=(
                            f"{strategy_id} underperforms in {regime} versus "
                            f"{reference_regime}; validate a regime-gated variant."
                        ),
                        proposed_experiment=(
                            f"Replay {strategy_id} with {regime} gating, rerun "
                            "walk-forward and OOS, and compare against the "
                            f"{reference_regime} reference regime."
                        ),
                        opportunity_cost_delta_usdt=(
                            reference.expectancy_usdt - underperforming.expectancy_usdt
                        ),
                    )
                )
        return tuple(candidates)

    @staticmethod
    def _virtual_market(market: str) -> VirtualMarket:
        normalized = market.strip().upper()
        if normalized == "SPOT":
            return VirtualMarket.SPOT
        if normalized == "USD_M_FUTURES":
            return VirtualMarket.USD_M_FUTURES
        raise ValueError("virtual market evidence supports only SPOT or USD_M_FUTURES")

    @staticmethod
    def _market_type(market: str) -> MarketType:
        return (
            MarketType.SPOT
            if VirtualMarketRuntime._virtual_market(market) is VirtualMarket.SPOT
            else MarketType.FUTURES
        )

    @staticmethod
    def _profit_factor(
        closed_trades: tuple[VirtualClosedTradeRecord, ...],
    ) -> Decimal | None:
        wins = [
            trade.net_pnl_usdt for trade in closed_trades if trade.net_pnl_usdt > ZERO
        ]
        losses = [
            trade.net_pnl_usdt for trade in closed_trades if trade.net_pnl_usdt < ZERO
        ]
        gross_loss = abs(sum(losses, ZERO))
        if not closed_trades or gross_loss == ZERO:
            return None
        return sum(wins, ZERO) / gross_loss

    @staticmethod
    def _win_rate(
        closed_trades: tuple[VirtualClosedTradeRecord, ...],
    ) -> Decimal | None:
        if not closed_trades:
            return None
        wins = sum(1 for trade in closed_trades if trade.net_pnl_usdt > ZERO)
        return Decimal(wins) / Decimal(len(closed_trades))

    @staticmethod
    def _average_realized_r(
        closed_trades: tuple[VirtualClosedTradeRecord, ...],
    ) -> Decimal | None:
        if not closed_trades:
            return None
        return sum(
            (trade.realized_r_multiple for trade in closed_trades), ZERO
        ) / Decimal(len(closed_trades))

    @staticmethod
    def _modeled_cost_expectancy(
        robustness_report: BacktestRobustnessReport | None,
    ) -> Decimal:
        if robustness_report is None or not robustness_report.stress_results:
            return ZERO
        return min(
            Decimal(str(result.expectancy_usdt))
            for result in robustness_report.stress_results
        )

    @staticmethod
    def _oos_expectancy(walk_forward_report: WalkForwardReport | None) -> Decimal:
        if walk_forward_report is None:
            return ZERO
        pnl: list[Decimal] = []
        for fold in getattr(walk_forward_report, "folds", ()):
            for trade in getattr(getattr(fold, "oos_result", None), "trades", ()):
                pnl.append(cast(Decimal, getattr(trade, "net_pnl_usdt", ZERO)))
        if not pnl:
            return ZERO
        return sum(pnl, ZERO) / Decimal(len(pnl))

    @staticmethod
    def _cost_stress_evidence(
        robustness_report: BacktestRobustnessReport | None,
    ) -> tuple[CostStressScenarioEvidence, ...]:
        if robustness_report is None:
            return ()
        return tuple(
            CostStressScenarioEvidence(
                scenario=result.scenario.name,
                expectancy_after_costs_usdt=Decimal(str(result.expectancy_usdt)),
            )
            for result in robustness_report.stress_results
        )

    @staticmethod
    def _regime_attribution(
        attribution_ledger: VirtualTradeAttributionLedger,
    ) -> tuple[RegimeAttribution, ...]:
        return tuple(
            RegimeAttribution(
                regime=view.regime or "UNKNOWN",
                trade_count=view.trade_count,
                expectancy_usdt=view.expectancy_usdt,
            )
            for view in attribution_ledger.by_regime
        )


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _require_unique_nonblank_or_empty(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _virtual_exit(exit_event: LifecycleExit) -> VirtualPositionExit:
    return VirtualPositionExit(
        timestamp=exit_event.timestamp,
        reason=_canonical_backtest_reason(exit_event.reason),
        price=exit_event.price,
        quantity=exit_event.quantity,
        fee_usdt=exit_event.fee_usdt,
        net_pnl_usdt=exit_event.net_pnl_usdt,
    )


def _paper_exit_reason(reason: BacktestExitReason) -> ExitReason:
    from ai4binance.execution.paper import ExitReason

    if reason is BacktestExitReason.HARD_STOP:
        return ExitReason.STOP_LOSS_EXIT
    if reason is BacktestExitReason.TRAILING_STOP:
        return ExitReason.TRAILING_STOP_EXIT
    return ExitReason.TAKE_PROFIT_EXIT


def _canonical_backtest_reason(reason: ExitReason) -> BacktestExitReason:
    from ai4binance.execution.paper import ExitReason

    if reason is ExitReason.STOP_LOSS_EXIT:
        return BacktestExitReason.HARD_STOP
    if reason is ExitReason.TRAILING_STOP_EXIT:
        return BacktestExitReason.TRAILING_STOP
    return BacktestExitReason.TARGET


class _ClosureReviewLike(Protocol):
    exit_reason: BacktestExitReason | str
    lifecycle_error: str | None
    stop_quality: str
    trailing_quality: str
    ignored_signals: int
    htf_weakness: bool
    volatility_expansion: bool
    level_break: bool
    staged_exit_alternative: str
    lesson_candidate: str


def _virtual_closure_review(review: object) -> VirtualClosureReview:
    review_like = cast(_ClosureReviewLike, review)
    exit_reason = review_like.exit_reason
    if not isinstance(exit_reason, BacktestExitReason):
        exit_reason = _canonical_backtest_reason(cast(Any, exit_reason))
    return VirtualClosureReview(
        exit_reason=exit_reason,
        lifecycle_error=review_like.lifecycle_error,
        stop_quality=review_like.stop_quality,
        trailing_quality=review_like.trailing_quality,
        ignored_signals=review_like.ignored_signals,
        htf_weakness=review_like.htf_weakness,
        volatility_expansion=review_like.volatility_expansion,
        level_break=review_like.level_break,
        staged_exit_alternative=review_like.staged_exit_alternative,
        lesson_candidate=review_like.lesson_candidate,
    )


def _paper_closure_review(review: VirtualClosureReview) -> PaperClosureReview:
    from ai4binance.execution.lifecycle import PaperClosureReview

    return PaperClosureReview(
        exit_reason=_paper_exit_reason(review.exit_reason),
        lifecycle_error=review.lifecycle_error,
        stop_quality=review.stop_quality,
        trailing_quality=review.trailing_quality,
        ignored_signals=review.ignored_signals,
        htf_weakness=review.htf_weakness,
        volatility_expansion=review.volatility_expansion,
        level_break=review.level_break,
        staged_exit_alternative=review.staged_exit_alternative,
        lesson_candidate=review.lesson_candidate,
    )


def _virtual_review(
    *,
    reason: BacktestExitReason,
    context: VirtualExitContext,
    staged_exit_used: bool,
) -> VirtualClosureReview:
    trailing = reason is BacktestExitReason.TRAILING_STOP
    liquidated = reason is BacktestExitReason.LIQUIDATION
    return VirtualClosureReview(
        exit_reason=reason,
        lifecycle_error=None,
        stop_quality=(
            "LIQUIDATED"
            if liquidated
            else "PROTECTIVE"
            if "STOP" in reason.value
            else "NOT_TRIGGERED"
        ),
        trailing_quality="PROTECTIVE" if trailing else "NOT_TRIGGERED",
        ignored_signals=context.ignored_signals,
        htf_weakness=context.htf_weakness,
        volatility_expansion=context.volatility_expansion,
        level_break=context.level_break,
        staged_exit_alternative=("USED" if staged_exit_used else "NOT_USED_REVIEW"),
        lesson_candidate=(
            "REVIEW_LIQUIDATION_BUFFER"
            if liquidated
            else "REVIEW_PREMATURE_TRAILING"
            if trailing
            else "REVIEW_EXIT_CONTEXT"
        ),
    )


__all__ = (
    "IndependentVirtualPortfolios",
    "VirtualAutonomyHaltStatus",
    "VirtualClosedTradeRecord",
    "VirtualClosureReview",
    "VirtualEvidenceSurfaceAdapter",
    "VirtualExitContext",
    "VirtualFillPreview",
    "VirtualFuturesPositionContext",
    "VirtualImprovementResearchQueue",
    "VirtualImprovementResearchWorkItem",
    "VirtualLossStreakHaltReview",
    "VirtualManagedPosition",
    "VirtualMarketRuntime",
    "VirtualNoTradeEvidenceSurface",
    "VirtualPortfolioPerformance",
    "VirtualPortfolioRiskGovernor",
    "VirtualPortfolioState",
    "VirtualPositionExit",
    "VirtualPositionLifecycleStatus",
    "VirtualPositionSide",
    "VirtualPositionUpdateDecision",
    "VirtualResearchEvidenceSurface",
    "VirtualRuntimeDecision",
    "VirtualRuntimeDecisionStatus",
    "VirtualRuntimeRequest",
    "VirtualStagedImprovementCandidate",
    "VirtualTradeAttributionAggregate",
    "VirtualTradeAttributionLedger",
    "VirtualTradeIntent",
)

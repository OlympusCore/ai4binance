"""Research run cards, hypothesis lifecycle and demotion-only decay governance."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

from ai4binance.domain.research.governance import (
    _ALLOWED_TRANSITIONS as _ALLOWED_TRANSITIONS,
)
from ai4binance.domain.research.governance import (
    _BLOCKER_GUIDANCE as _BLOCKER_GUIDANCE,
)
from ai4binance.domain.research.governance import (
    DecayDecision as DecayDecision,
)
from ai4binance.domain.research.governance import (
    DecayPolicy as DecayPolicy,
)
from ai4binance.domain.research.governance import (
    HypothesisStatus as HypothesisStatus,
)
from ai4binance.domain.research.governance import (
    ResearchBlockerAction as ResearchBlockerAction,
)
from ai4binance.domain.research.governance import (
    ResearchBlockerDashboard as ResearchBlockerDashboard,
)
from ai4binance.domain.research.governance import (
    ResearchBlockerObservation as ResearchBlockerObservation,
)
from ai4binance.domain.research.governance import (
    ResearchHypothesis as ResearchHypothesis,
)
from ai4binance.domain.research.governance import (
    ResearchRunCard as ResearchRunCard,
)
from ai4binance.domain.research.governance import (
    StrategyDecayEvaluator as StrategyDecayEvaluator,
)
from ai4binance.domain.research.governance import (
    StrategyHealthSnapshot as StrategyHealthSnapshot,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementCandidateCycleExecutiveSummary as VirtualImprovementCandidateCycleExecutiveSummary,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementCandidateLifecycleSnapshot as VirtualImprovementCandidateLifecycleSnapshot,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementCandidateOutcomeDashboardPayload as VirtualImprovementCandidateOutcomeDashboardPayload,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementCandidateRegistryEntry as VirtualImprovementCandidateRegistryEntry,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementExperimentProposal as VirtualImprovementExperimentProposal,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementExperimentTaskQueue as VirtualImprovementExperimentTaskQueue,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementExperimentTaskRecord as VirtualImprovementExperimentTaskRecord,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementExperimentTaskStatus as VirtualImprovementExperimentTaskStatus,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementNextCandidateIntakeHandoff as VirtualImprovementNextCandidateIntakeHandoff,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementNextCandidateRefusalArtifact as VirtualImprovementNextCandidateRefusalArtifact,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementNextCandidateRegistrationPacket as VirtualImprovementNextCandidateRegistrationPacket,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementOperatorHandoffSummary as VirtualImprovementOperatorHandoffSummary,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementRefusalLedgerEntry as VirtualImprovementRefusalLedgerEntry,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchExecutionInbox as VirtualImprovementResearchExecutionInbox,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchExecutionSessionManifest as VirtualImprovementResearchExecutionSessionManifest,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchSessionArtifactBundle as VirtualImprovementResearchSessionArtifactBundle,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchSessionClosureRecord as VirtualImprovementResearchSessionClosureRecord,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchSessionJournal as VirtualImprovementResearchSessionJournal,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchSessionReadinessSummary as VirtualImprovementResearchSessionReadinessSummary,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementResearchWorkPlanner as VirtualImprovementResearchWorkPlanner,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementReviewInput as VirtualImprovementReviewInput,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementReviewOutcome as VirtualImprovementReviewOutcome,
)
from ai4binance.domain.research.governance import (
    VirtualImprovementReviewResult as VirtualImprovementReviewResult,
)
from ai4binance.domain.research.governance import (
    _build_blocker_action as _build_blocker_action,
)
from ai4binance.domain.research.governance import (
    _require_aware as _require_aware,
)
from ai4binance.domain.research.governance import (
    _require_identity as _require_identity,
)
from ai4binance.domain.research.governance import (
    _tuple_of_text as _tuple_of_text,
)
from ai4binance.domain.research.governance import (
    build_research_blocker_dashboard as build_research_blocker_dashboard,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_candidate_cycle_executive_summary as build_virtual_improvement_candidate_cycle_executive_summary,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal as build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_candidate_lifecycle_snapshot_from_registry as build_virtual_improvement_candidate_lifecycle_snapshot_from_registry,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_candidate_outcome_dashboard_payload as build_virtual_improvement_candidate_outcome_dashboard_payload,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_candidate_registry_entry as build_virtual_improvement_candidate_registry_entry,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_experiment_proposal as build_virtual_improvement_experiment_proposal,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_experiment_task as build_virtual_improvement_experiment_task,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_experiment_task_queue as build_virtual_improvement_experiment_task_queue,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_next_candidate_intake_handoff as build_virtual_improvement_next_candidate_intake_handoff,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_next_candidate_refusal_artifact as build_virtual_improvement_next_candidate_refusal_artifact,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_next_candidate_registration_packet as build_virtual_improvement_next_candidate_registration_packet,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_operator_handoff_summary as build_virtual_improvement_operator_handoff_summary,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_refusal_ledger_entry as build_virtual_improvement_refusal_ledger_entry,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_execution_inbox as build_virtual_improvement_research_execution_inbox,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_execution_session_manifest as build_virtual_improvement_research_execution_session_manifest,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_session_artifact_bundle as build_virtual_improvement_research_session_artifact_bundle,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_session_closure_record as build_virtual_improvement_research_session_closure_record,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_session_journal as build_virtual_improvement_research_session_journal,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_session_readiness_summary as build_virtual_improvement_research_session_readiness_summary,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_research_work_planner as build_virtual_improvement_research_work_planner,
)
from ai4binance.domain.research.governance import (
    build_virtual_improvement_review_result as build_virtual_improvement_review_result,
)
from ai4binance.domain.research.governance import (
    consume_virtual_improvement_review_handoff as consume_virtual_improvement_review_handoff,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified


@dataclass(frozen=True, slots=True)
class VirtualImprovementReviewResultWriter:
    """Atomically persist a virtual improvement review result and append an audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, result: VirtualImprovementReviewResult) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(result)),
            blocker="VIRTUAL_IMPROVEMENT_REVIEW_RESULT_DESTINATION_VERIFY_FAILED",
            subject_id=result.review_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="VIRTUAL_IMPROVEMENT_REVIEW_RESULT_WRITTEN",
                    timestamp=datetime.now().astimezone(),
                    payload={"review_result": result},
                )
            )


@dataclass(frozen=True, slots=True)
class HypothesisRegistry:
    """Immutable registry; persistence is append-only through an optional ledger."""

    hypotheses: tuple[ResearchHypothesis, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(self, hypothesis: ResearchHypothesis) -> HypothesisRegistry:
        if any(
            item.hypothesis_id == hypothesis.hypothesis_id for item in self.hypotheses
        ):
            raise ValueError("hypothesis ID already exists")
        self._record("HYPOTHESIS_CREATED", hypothesis)
        return HypothesisRegistry((*self.hypotheses, hypothesis), self.ledger)

    def update(self, hypothesis: ResearchHypothesis) -> HypothesisRegistry:
        matches = tuple(
            index
            for index, item in enumerate(self.hypotheses)
            if item.hypothesis_id == hypothesis.hypothesis_id
        )
        if len(matches) != 1:
            raise KeyError(hypothesis.hypothesis_id)
        items = list(self.hypotheses)
        items[matches[0]] = hypothesis
        self._record("HYPOTHESIS_TRANSITIONED", hypothesis)
        return HypothesisRegistry(tuple(items), self.ledger)

    def get(self, hypothesis_id: str) -> ResearchHypothesis:
        matches = tuple(
            item for item in self.hypotheses if item.hypothesis_id == hypothesis_id
        )
        if len(matches) != 1:
            raise KeyError(hypothesis_id)
        return matches[0]

    def _record(self, event_type: str, hypothesis: ResearchHypothesis) -> None:
        if self.ledger is None:
            return
        self.ledger.append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=hypothesis.updated_at,
                payload={"hypothesis": hypothesis},
            )
        )


@dataclass(frozen=True, slots=True)
class VirtualImprovementExperimentTaskRegistry:
    """Immutable append/update registry for bounded virtual improvement tasks."""

    tasks: tuple[VirtualImprovementExperimentTaskRecord, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(
        self,
        task: VirtualImprovementExperimentTaskRecord,
    ) -> VirtualImprovementExperimentTaskRegistry:
        if any(item.task_id == task.task_id for item in self.tasks):
            raise ValueError("virtual improvement experiment task ID already exists")
        self._record("VIRTUAL_IMPROVEMENT_EXPERIMENT_TASK_CREATED", task)
        return VirtualImprovementExperimentTaskRegistry(
            (*self.tasks, task), self.ledger
        )

    def get(self, task_id: str) -> VirtualImprovementExperimentTaskRecord:
        matches = tuple(item for item in self.tasks if item.task_id == task_id)
        if len(matches) != 1:
            raise KeyError(task_id)
        return matches[0]

    def _record(
        self,
        event_type: str,
        task: VirtualImprovementExperimentTaskRecord,
    ) -> None:
        if self.ledger is None:
            return
        self.ledger.append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=datetime.now().astimezone(),
                payload={"task": task},
            )
        )


@dataclass(frozen=True, slots=True)
class ResearchRunCardWriter:
    """Atomically persist a run card and optionally append its audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, card: ResearchRunCard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(card)),
            blocker="RESEARCH_RUN_CARD_DESTINATION_VERIFY_FAILED",
            subject_id=card.run_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="RESEARCH_RUN_CARD_WRITTEN",
                    timestamp=card.created_at,
                    payload={"run_card": card},
                )
            )


@dataclass(frozen=True, slots=True)
class ResearchBlockerDashboardWriter:
    """Atomically persist a blocker dashboard and append an audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, dashboard: ResearchBlockerDashboard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(dashboard)),
            blocker="RESEARCH_BLOCKER_DASHBOARD_DESTINATION_VERIFY_FAILED",
            subject_id=dashboard.dashboard_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="RESEARCH_BLOCKER_DASHBOARD_WRITTEN",
                    timestamp=dashboard.created_at,
                    payload={"dashboard": dashboard},
                )
            )

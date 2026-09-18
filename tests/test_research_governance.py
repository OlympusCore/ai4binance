"""Research run-card, hypothesis and decay lifecycle tests."""

# ruff: noqa: E501

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance import research_governance as governance
from ai4binance.research_governance import (
    DecayPolicy,
    HypothesisRegistry,
    HypothesisStatus,
    ResearchBlockerDashboardWriter,
    ResearchBlockerObservation,
    ResearchHypothesis,
    ResearchRunCard,
    ResearchRunCardWriter,
    StrategyDecayEvaluator,
    StrategyHealthSnapshot,
    VirtualImprovementCandidateCycleExecutiveSummary,
    VirtualImprovementCandidateLifecycleSnapshot,
    VirtualImprovementCandidateOutcomeDashboardPayload,
    VirtualImprovementCandidateRegistryEntry,
    VirtualImprovementExperimentProposal,
    VirtualImprovementExperimentTaskQueue,
    VirtualImprovementExperimentTaskRegistry,
    VirtualImprovementExperimentTaskStatus,
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
    VirtualImprovementReviewResultWriter,
    build_research_blocker_dashboard,
    build_virtual_improvement_candidate_cycle_executive_summary,
    build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal,
    build_virtual_improvement_candidate_lifecycle_snapshot_from_registry,
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
from ai4binance.storage import JsonlAuditStore

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
DIGEST = sha256(b"evidence").hexdigest()


def hypothesis() -> ResearchHypothesis:
    return ResearchHypothesis(
        hypothesis_id="hyp:breakout-retest",
        title="Breakout retest continuation",
        thesis="Validated retests may improve OOS expectancy.",
        symbol="HOTUSDT",
        timeframe="1h",
        invalidation_conditions=(
            "OOS expectancy is non-positive",
            "Edge fails cost stress",
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def test_hypothesis_registry_records_explicit_forward_transitions(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "hypotheses.jsonl"
    registry = HypothesisRegistry(ledger=JsonlAuditStore(ledger_path)).add(hypothesis())
    research = registry.get("hyp:breakout-retest").transition(
        HypothesisStatus.RESEARCH,
        updated_at=NOW + timedelta(minutes=1),
        artifact_ids=("run:1",),
    )
    registry = registry.update(research)

    assert registry.get(research.hypothesis_id).artifact_ids == ("run:1",)
    events = [
        json.loads(line)["event_type"] for line in ledger_path.read_text().splitlines()
    ]
    assert events == ["HYPOTHESIS_CREATED", "HYPOTHESIS_TRANSITIONED"]

    with pytest.raises(ValueError, match="invalid hypothesis transition"):
        research.transition(HypothesisStatus.PAPER_APPROVED, updated_at=NOW)
    with pytest.raises(ValueError, match="already exists"):
        registry.add(research)
    with pytest.raises(KeyError):
        registry.get("missing")


def test_run_card_is_hash_linked_atomic_and_live_blocked(tmp_path: Path) -> None:
    card = ResearchRunCard(
        run_id="run:1",
        created_at=NOW,
        symbol="HOTUSDT",
        timeframe="1h",
        hypothesis_id="hyp:breakout-retest",
        dataset_sha256=DIGEST,
        config_sha256=ResearchRunCard.hash_json({"fee": 0.001}),
        strategy_sha256=DIGEST,
        code_revision="working-tree:2026-07-13",
        random_seed=42,
        fee_rate=0.001,
        slippage_rate=0.0005,
        metrics=(("net_return", 0.02), ("max_drawdown", 0.01)),
        artifact_sha256=(("walk-forward.json", DIGEST),),
        blockers=("MULTI_REGIME_EVIDENCE_INCOMPLETE",),
    )
    path = tmp_path / "run-card.json"
    ledger = JsonlAuditStore(tmp_path / "run-cards.jsonl")
    ResearchRunCardWriter(path, ledger).write(card)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["run_id"] == "run:1"
    assert stored["execution_allowed"] is False
    assert not path.with_suffix(".json.tmp").exists()
    assert "RESEARCH_RUN_CARD_WRITTEN" in ledger.path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="staged run card"):
        replace(card, promotion_status="STAGED_CANDIDATE")
    with pytest.raises(ValueError, match="hashes"):
        replace(card, dataset_sha256="bad")


def test_blocker_dashboard_groups_actions_and_remains_live_blocked(
    tmp_path: Path,
) -> None:
    dashboard = build_research_blocker_dashboard(
        dashboard_id="dashboard:HOTUSDT:validation",
        created_at=NOW,
        symbol="hotusdt",
        observations=(
            ResearchBlockerObservation(
                symbol="HOTUSDT",
                timeframe="1h",
                playbook="breakout_retest",
                blocker="COST_STRESS_RETURN_NOT_POSITIVE",
                count=2,
            ),
            ResearchBlockerObservation(
                symbol="HOTUSDT",
                timeframe="4h",
                playbook="support_reclaim",
                blocker="COST_STRESS_RETURN_NOT_POSITIVE",
            ),
        ),
    )

    path = tmp_path / "blocker-dashboard.json"
    ledger = JsonlAuditStore(tmp_path / "blocker-dashboards.jsonl")
    ResearchBlockerDashboardWriter(path, ledger).write(dashboard)
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert stored["execution_allowed"] is False
    assert stored["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert stored["promotion_status"] == "RESEARCH_ONLY"
    assert stored["actions"][0]["occurrences"] == 3
    assert stored["actions"][0]["affected_timeframes"] == ["1h", "4h"]
    assert "slippage" in stored["actions"][0]["recommended_experiment"].lower()
    assert "RESEARCH_BLOCKER_DASHBOARD_WRITTEN" in ledger.path.read_text(
        encoding="utf-8"
    )


def health(
    index: int,
    *,
    healthy: bool = False,
) -> StrategyHealthSnapshot:
    return StrategyHealthSnapshot(
        strategy_id="breakout-retest:v1",
        observed_at=NOW + timedelta(days=index),
        oos_trade_count=30 if healthy else 4,
        expectancy=0.02 if healthy else -0.01,
        profit_factor=1.4 if healthy else 0.7,
        max_drawdown=0.10 if healthy else 0.35,
        turnover=0.10 if healthy else 0.40,
        regime_count=3 if healthy else 1,
    )


def test_decay_evaluator_only_demotes_after_consecutive_evidence() -> None:
    evaluator = StrategyDecayEvaluator(DecayPolicy())
    missing = evaluator.evaluate(HypothesisStatus.PAPER_APPROVED, ())
    assert missing.recommended_status is HypothesisStatus.PAPER_APPROVED
    assert missing.reason_codes == ("STRATEGY_HEALTH_EVIDENCE_MISSING",)

    one_weak = evaluator.evaluate(HypothesisStatus.PAPER_APPROVED, (health(1),))
    assert one_weak.recommended_status is HypothesisStatus.PAPER_APPROVED

    monitoring = evaluator.evaluate(
        HypothesisStatus.PAPER_APPROVED,
        (health(1), health(2)),
    )
    assert monitoring.recommended_status is HypothesisStatus.MONITORING
    assert monitoring.auto_promotion_allowed is False
    assert "DECAY_EXPECTANCY" in monitoring.reason_codes

    decayed = evaluator.evaluate(
        HypothesisStatus.MONITORING,
        (health(1), health(2)),
    )
    assert decayed.recommended_status is HypothesisStatus.DECAYED

    disabled = evaluator.evaluate(
        HypothesisStatus.DECAYED,
        (health(1), health(2), health(3)),
    )
    assert disabled.recommended_status is HypothesisStatus.DISABLED

    recovered = evaluator.evaluate(
        HypothesisStatus.MONITORING,
        (health(1), health(2, healthy=True)),
    )
    assert recovered.recommended_status is HypothesisStatus.MONITORING


def test_virtual_improvement_review_consumer_requires_assurance_pair() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:1",
            "snapshot_id": "snapshot:queue:review:1",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:1",
                "candidate:1",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )

    assert review_input.assurance_artifact_refs[0].endswith(
        "virtual_research_improvement_queue_assurance_latest.json"
    )
    assert review_input.required_output_fields == (
        "review_outcome",
        "recommended_experiment",
        "evidence_gap_assessment",
    )
    assert review_input.execution_allowed is False


def test_virtual_improvement_review_consumer_rejects_missing_assurance_refs() -> None:
    with pytest.raises(ValueError, match="requires assurance artifact refs"):
        consume_virtual_improvement_review_handoff(
            {
                "schema_version": "VirtualImprovementResearchHandoff/v1",
                "handoff_id": "virtual-improvement-work:2",
                "snapshot_id": "snapshot:queue:review:2",
                "surface_kind": "RESEARCH",
                "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
                "objective": "Review the staged virtual improvement candidate.",
                "evidence_refs": (
                    "snapshot:queue:review:2",
                    "candidate:2",
                    "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
                ),
                "governance_refs": (
                    "ValidationStatus.RESEARCH_ONLY",
                    "LIVE_ORDER_BLOCKED",
                    "VirtualImprovementResearchQueue",
                ),
                "required_output_fields": (
                    "review_outcome",
                    "recommended_experiment",
                    "evidence_gap_assessment",
                ),
                "blocker_refs": (),
                "priority": "P1",
                "status": "QUEUED_RESEARCH_ONLY",
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )


def test_virtual_improvement_review_result_builds_experiment_proposal(
    tmp_path: Path,
) -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:3",
            "snapshot_id": "snapshot:queue:review:3",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:3",
                "candidate:3",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    result = build_virtual_improvement_review_result(review_input)

    path = tmp_path / "virtual-review.json"
    ledger = JsonlAuditStore(tmp_path / "virtual-review.jsonl")
    VirtualImprovementReviewResultWriter(path, ledger).write(result)
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert stored["outcome"] == "EXPERIMENT_PROPOSAL"
    assert stored["execution_allowed"] is False
    assert stored["evidence_gap_assessment"] == (
        "ASSURANCE_BASELINE_READY_FOR_BOUNDED_EXPERIMENT"
    )
    assert stored["follow_up_artifact_refs"][0].endswith(
        "research_virtual_improvement_review_latest.json"
    )
    assert "VIRTUAL_IMPROVEMENT_REVIEW_RESULT_WRITTEN" in ledger.path.read_text(
        encoding="utf-8"
    )


def test_virtual_improvement_review_result_builds_investigation_for_blockers() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:4",
            "snapshot_id": "snapshot:queue:review:4",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:4",
                "candidate:4",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    result = build_virtual_improvement_review_result(review_input)

    assert result.outcome.value == "INVESTIGATION_REQUIRED"
    assert result.blockers == ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",)
    assert result.evidence_gap_assessment == "ASSURANCE_AND_INPUT_BLOCKERS_PRESENT"
    assert "research-only" in result.recommended_experiment.lower()


def test_virtual_improvement_experiment_proposal_builds_from_review_result() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:5",
            "snapshot_id": "snapshot:queue:review:5",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:5",
                "candidate:5",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    result = build_virtual_improvement_review_result(review_input)
    proposal = build_virtual_improvement_experiment_proposal(result)

    assert isinstance(proposal, VirtualImprovementExperimentProposal)
    assert proposal.priority == "P0"
    assert proposal.execution_allowed is False
    assert proposal.source_artifact_refs[0].endswith(
        "virtual_research_improvement_queue_assurance_latest.json"
    )


def test_virtual_improvement_experiment_proposal_inherits_blockers() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:6",
            "snapshot_id": "snapshot:queue:review:6",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:6",
                "candidate:6",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    result = build_virtual_improvement_review_result(review_input)
    proposal = build_virtual_improvement_experiment_proposal(result)

    assert proposal.priority == "P1"
    assert proposal.blockers == ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",)
    assert proposal.required_data[-1].startswith("Missing or insufficient evidence")


def test_virtual_improvement_experiment_task_builds_ready_registry_record(
    tmp_path: Path,
) -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:7",
            "snapshot_id": "snapshot:queue:review:7",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:7",
                "candidate:7",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    proposal = build_virtual_improvement_experiment_proposal(
        build_virtual_improvement_review_result(review_input)
    )
    task = build_virtual_improvement_experiment_task(proposal)
    ledger = JsonlAuditStore(tmp_path / "virtual-improvement-tasks.jsonl")
    registry = VirtualImprovementExperimentTaskRegistry(ledger=ledger).add(task)

    assert task.status is VirtualImprovementExperimentTaskStatus.READY_FOR_RESEARCH
    assert registry.get(task.task_id).proposal_id == proposal.proposal_id
    assert "VIRTUAL_IMPROVEMENT_EXPERIMENT_TASK_CREATED" in ledger.path.read_text(
        encoding="utf-8"
    )


def test_virtual_improvement_experiment_task_builds_evidence_pending_record() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:8",
            "snapshot_id": "snapshot:queue:review:8",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:8",
                "candidate:8",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    proposal = build_virtual_improvement_experiment_proposal(
        build_virtual_improvement_review_result(review_input)
    )
    task = build_virtual_improvement_experiment_task(proposal)

    assert task.status is VirtualImprovementExperimentTaskStatus.EVIDENCE_PENDING
    assert task.blockers == ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",)


def test_virtual_improvement_experiment_task_queue_rolls_up_task_status() -> None:
    ready_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:9",
            "snapshot_id": "snapshot:queue:review:9",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:9",
                "candidate:9",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    pending_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:10",
            "snapshot_id": "snapshot:queue:review:9",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:9",
                "candidate:10",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    ready_task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(ready_input)
        )
    )
    pending_task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(pending_input)
        )
    )

    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:1",
        snapshot_id="snapshot:queue:review:9",
        surface_kind="RESEARCH",
        tasks=(ready_task, pending_task),
    )

    assert isinstance(queue, VirtualImprovementExperimentTaskQueue)
    assert queue.ready_task_count == 1
    assert queue.evidence_pending_task_count == 1
    assert queue.status == "EVIDENCE_PENDING"


def test_virtual_improvement_research_work_planner_orders_ready_actions() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:11",
            "snapshot_id": "snapshot:queue:review:11",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:11",
                "candidate:11",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:ready",
        snapshot_id="snapshot:queue:review:11",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)

    assert isinstance(planner, VirtualImprovementResearchWorkPlanner)
    assert planner.status == "READY_PLAN"
    assert planner.selected_ready_task_ids == (task.task_id,)
    assert planner.next_safe_actions[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_improvement_research_work_planner_escalates_evidence_pending() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:12",
            "snapshot_id": "snapshot:queue:review:12",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:12",
                "candidate:12",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:pending",
        snapshot_id="snapshot:queue:review:12",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)

    assert planner.status == "EVIDENCE_ESCALATION_REQUIRED"
    assert planner.escalated_task_ids == (task.task_id,)
    assert "ESCALATE_MISSING_EVIDENCE" in planner.next_safe_actions


def test_virtual_improvement_operator_handoff_summary_condenses_planner() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:13",
            "snapshot_id": "snapshot:queue:review:13",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:13",
                "candidate:13",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:handoff",
        snapshot_id="snapshot:queue:review:13",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )

    assert isinstance(summary, VirtualImprovementOperatorHandoffSummary)
    assert summary.status == "READY_HANDOFF"
    assert summary.selected_task_briefs
    assert summary.next_safe_actions[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_improvement_operator_handoff_summary_marks_escalation() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:14",
            "snapshot_id": "snapshot:queue:review:14",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:14",
                "candidate:14",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:handoff-pending",
        snapshot_id="snapshot:queue:review:14",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )

    assert summary.status == "ESCALATION_HANDOFF"
    assert summary.escalated_blocker_briefs
    assert "IMPROVEMENT_EVIDENCE_INSUFFICIENT" in summary.escalated_blocker_briefs[0]


def test_virtual_improvement_research_execution_inbox_ready_state() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:15",
            "snapshot_id": "snapshot:queue:review:15",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:15",
                "candidate:15",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:inbox-ready",
        snapshot_id="snapshot:queue:review:15",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)

    assert isinstance(inbox, VirtualImprovementResearchExecutionInbox)
    assert inbox.status == "READY_INBOX"
    assert inbox.ready_work_items
    assert inbox.next_safe_actions[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_improvement_research_execution_inbox_escalation_state() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:16",
            "snapshot_id": "snapshot:queue:review:16",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:16",
                "candidate:16",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:inbox-pending",
        snapshot_id="snapshot:queue:review:16",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)

    assert inbox.status == "ESCALATION_INBOX"
    assert inbox.escalation_items
    assert "ESCALATE_MISSING_EVIDENCE" in inbox.next_safe_actions


def test_virtual_improvement_session_manifest_selects_ready_item() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:17",
            "snapshot_id": "snapshot:queue:review:17",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:17",
                "candidate:17",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-ready",
        snapshot_id="snapshot:queue:review:17",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)

    assert isinstance(manifest, VirtualImprovementResearchExecutionSessionManifest)
    assert manifest.status == "READY_SESSION"
    assert manifest.chosen_ready_item is not None
    assert manifest.action_order[0] == "START_BOUNDED_RESEARCH_EXPERIMENT"


def test_virtual_improvement_session_manifest_blocks_ready_item_during_escalation() -> (
    None
):
    ready_review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:17a",
            "snapshot_id": "snapshot:queue:review:17a",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:17a",
                "candidate:17a",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    blocked_review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:17b",
            "snapshot_id": "snapshot:queue:review:17b",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:17b",
                "candidate:17b",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    ready_task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(ready_review_input)
        )
    )
    blocked_task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(blocked_review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-mixed",
        snapshot_id="snapshot:queue:review:17a",
        surface_kind="RESEARCH",
        tasks=(ready_task, blocked_task),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)

    assert manifest.status == "ESCALATION_SESSION"
    assert manifest.chosen_ready_item is None
    assert manifest.escalation_items


def test_virtual_improvement_session_manifest_keeps_escalation_items() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:18",
            "snapshot_id": "snapshot:queue:review:18",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Review the staged virtual improvement candidate.",
            "evidence_refs": (
                "snapshot:queue:review:18",
                "candidate:18",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-pending",
        snapshot_id="snapshot:queue:review:18",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)

    assert manifest.status == "ESCALATION_SESSION"
    assert manifest.chosen_ready_item is None
    assert manifest.escalation_items


def test_virtual_improvement_session_journal_records_ready_execution_trail() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:19",
            "snapshot_id": "snapshot:queue:review:19",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Journal the selected bounded research session.",
            "evidence_refs": (
                "snapshot:queue:review:19",
                "candidate:19",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-journal-ready",
        snapshot_id="snapshot:queue:review:19",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)

    assert isinstance(journal, VirtualImprovementResearchSessionJournal)
    assert journal.status == "READY_JOURNAL"
    assert journal.chosen_ready_item == manifest.chosen_ready_item
    assert journal.closure_result == "READY_ITEM_SELECTED_FOR_RESEARCH"
    assert journal.consumed_action_order == manifest.action_order


def test_virtual_improvement_session_journal_preserves_escalation_state() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:20",
            "snapshot_id": "snapshot:queue:review:20",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Journal the escalated bounded research session.",
            "evidence_refs": (
                "snapshot:queue:review:20",
                "candidate:20",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-journal-escalation",
        snapshot_id="snapshot:queue:review:20",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)

    assert journal.status == "ESCALATION_JOURNAL"
    assert journal.chosen_ready_item is None
    assert journal.escalation_items == manifest.escalation_items
    assert journal.closure_result == "ESCALATION_REQUIRED_BEFORE_RESEARCH"


def test_virtual_improvement_session_closure_records_completed_research_only() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:21",
            "snapshot_id": "snapshot:queue:review:21",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Close the bounded research session after journaling.",
            "evidence_refs": (
                "snapshot:queue:review:21",
                "candidate:21",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-closure-ready",
        snapshot_id="snapshot:queue:review:21",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)
    closure = build_virtual_improvement_research_session_closure_record(journal)

    assert isinstance(closure, VirtualImprovementResearchSessionClosureRecord)
    assert closure.status == "COMPLETED_RESEARCH_ONLY"
    assert closure.chosen_ready_item == journal.chosen_ready_item
    assert closure.completed_actions == journal.consumed_action_order
    assert closure.closure_reason == "BOUNDED_RESEARCH_SESSION_RECORDED"


def test_virtual_improvement_session_closure_preserves_escalation_state() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:22",
            "snapshot_id": "snapshot:queue:review:22",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Close the escalated research session after journaling.",
            "evidence_refs": (
                "snapshot:queue:review:22",
                "candidate:22",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-closure-escalation",
        snapshot_id="snapshot:queue:review:22",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)
    closure = build_virtual_improvement_research_session_closure_record(journal)

    assert closure.status == "ESCALATED_RESEARCH_ONLY"
    assert closure.chosen_ready_item is None
    assert closure.escalation_items == journal.escalation_items
    assert closure.closure_reason == "EVIDENCE_ESCALATION_RECORDED"


def test_virtual_improvement_session_artifact_bundle_reports_missing_refs() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:23",
            "snapshot_id": "snapshot:queue:review:23",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Bundle the bounded session artifacts.",
            "evidence_refs": (
                "snapshot:queue:review:23",
                "candidate:23",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-bundle-ready",
        snapshot_id="snapshot:queue:review:23",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)
    closure = build_virtual_improvement_research_session_closure_record(journal)
    bundle = build_virtual_improvement_research_session_artifact_bundle(
        manifest=manifest,
        journal=journal,
        closure=closure,
    )

    assert isinstance(bundle, VirtualImprovementResearchSessionArtifactBundle)
    assert bundle.status == "INCOMPLETE_BUNDLE"
    assert bundle.missing_artifact_refs
    assert "research-inbox:" in bundle.missing_artifact_refs[0]


def test_virtual_improvement_session_artifact_bundle_preserves_escalation_state() -> (
    None
):
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:24",
            "snapshot_id": "snapshot:queue:review:24",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Bundle the escalated bounded session artifacts.",
            "evidence_refs": (
                "snapshot:queue:review:24",
                "candidate:24",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": ("IMPROVEMENT_EVIDENCE_INSUFFICIENT",),
            "priority": "P1",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-bundle-escalation",
        snapshot_id="snapshot:queue:review:24",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)
    closure = build_virtual_improvement_research_session_closure_record(journal)
    bundle = build_virtual_improvement_research_session_artifact_bundle(
        manifest=manifest,
        journal=journal,
        closure=closure,
    )

    assert bundle.status == "INCOMPLETE_BUNDLE"
    assert bundle.escalation_items == closure.escalation_items
    assert bundle.missing_artifact_refs


def test_virtual_improvement_session_readiness_summary_reports_evidence_gap() -> None:
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:25",
            "snapshot_id": "snapshot:queue:review:25",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Summarize readiness after bundling.",
            "evidence_refs": (
                "snapshot:queue:review:25",
                "candidate:25",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:session-readiness-gap",
        snapshot_id="snapshot:queue:review:25",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)
    closure = build_virtual_improvement_research_session_closure_record(journal)
    bundle = build_virtual_improvement_research_session_artifact_bundle(
        manifest=manifest,
        journal=journal,
        closure=closure,
    )
    readiness = build_virtual_improvement_research_session_readiness_summary(bundle)

    assert isinstance(readiness, VirtualImprovementResearchSessionReadinessSummary)
    assert readiness.verdict == "EVIDENCE_GAP_REMAINING"
    assert readiness.status == "BLOCKED_SUMMARY"
    assert (
        readiness.next_safe_handoff
        == "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE"
    )


def test_virtual_improvement_session_readiness_summary_reports_ready_verdict() -> None:
    bundle = VirtualImprovementResearchSessionArtifactBundle(
        bundle_id="virtual-improvement-session-bundle:ready",
        manifest_id="manifest:ready",
        journal_id="journal:ready",
        closure_id="closure:ready",
        queue_id="queue:ready",
        snapshot_id="snapshot:ready",
        surface_kind="RESEARCH",
        status="COMPLETE_BUNDLE",
        required_artifact_refs=(
            "research-session-manifest:manifest:ready",
            "research-session-journal:journal:ready",
            "research-session-closure:closure:ready",
        ),
        produced_artifact_refs=(
            "research-session-manifest:manifest:ready",
            "research-session-journal:journal:ready",
            "research-session-closure:closure:ready",
        ),
        missing_artifact_refs=(),
        escalation_items=(),
    )

    readiness = build_virtual_improvement_research_session_readiness_summary(bundle)

    assert readiness.verdict == "READY_FOR_NEXT_CANDIDATE"
    assert readiness.status == "READY_SUMMARY"
    assert readiness.blocker_codes == ()
    assert readiness.next_safe_handoff == "STAGE_NEXT_VIRTUAL_IMPROVEMENT_CANDIDATE"


def test_virtual_improvement_next_candidate_intake_handoff_blocks_until_gaps_close() -> (
    None
):
    review_input = consume_virtual_improvement_review_handoff(
        {
            "schema_version": "VirtualImprovementResearchHandoff/v1",
            "handoff_id": "virtual-improvement-work:26",
            "snapshot_id": "snapshot:queue:review:26",
            "surface_kind": "RESEARCH",
            "task_type": "VIRTUAL_IMPROVEMENT_REVIEW",
            "objective": "Prepare the next candidate intake handoff.",
            "evidence_refs": (
                "snapshot:queue:review:26",
                "candidate:26",
                (
                    "runtime/artifacts/user_reports/virtual_improvement_queue_assurance/"
                    "virtual_research_improvement_queue_assurance_latest.json"
                ),
                (
                    "runtime/reports/virtual_improvement_queue_assurance/virtual_research_improvement_queue_assurance_latest.md"
                ),
                "runtime/artifacts/user_reports/virtual_evidence/virtual_research_evidence_latest.json",
            ),
            "governance_refs": (
                "ValidationStatus.RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "VirtualImprovementResearchQueue",
            ),
            "required_output_fields": (
                "review_outcome",
                "recommended_experiment",
                "evidence_gap_assessment",
            ),
            "blocker_refs": (),
            "priority": "P0",
            "status": "QUEUED_RESEARCH_ONLY",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    task = build_virtual_improvement_experiment_task(
        build_virtual_improvement_experiment_proposal(
            build_virtual_improvement_review_result(review_input)
        )
    )
    queue = build_virtual_improvement_experiment_task_queue(
        queue_id="virtual-improvement-task-queue:next-intake-blocked",
        snapshot_id="snapshot:queue:review:26",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = build_virtual_improvement_research_work_planner(queue)
    summary = build_virtual_improvement_operator_handoff_summary(
        queue=queue,
        planner=planner,
    )
    inbox = build_virtual_improvement_research_execution_inbox(summary)
    manifest = build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = build_virtual_improvement_research_session_journal(manifest)
    closure = build_virtual_improvement_research_session_closure_record(journal)
    bundle = build_virtual_improvement_research_session_artifact_bundle(
        manifest=manifest,
        journal=journal,
        closure=closure,
    )
    readiness = build_virtual_improvement_research_session_readiness_summary(bundle)
    handoff = build_virtual_improvement_next_candidate_intake_handoff(readiness)

    assert isinstance(handoff, VirtualImprovementNextCandidateIntakeHandoff)
    assert handoff.status == "BLOCKED_INTAKE"
    assert handoff.intake_decision == "HOLD_CURRENT_CYCLE"
    assert "SESSION_ARTIFACT_GAP_REMAINING" in handoff.blocker_codes
    assert (
        handoff.required_follow_up
        == "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE"
    )


def test_virtual_improvement_next_candidate_intake_handoff_opens_ready_cycle() -> None:
    readiness = VirtualImprovementResearchSessionReadinessSummary(
        summary_id="summary:ready",
        bundle_id="bundle:ready",
        closure_id="closure:ready",
        queue_id="queue:ready",
        snapshot_id="snapshot:ready",
        surface_kind="RESEARCH",
        verdict="READY_FOR_NEXT_CANDIDATE",
        status="READY_SUMMARY",
        blocker_codes=(),
        next_safe_handoff="STAGE_NEXT_VIRTUAL_IMPROVEMENT_CANDIDATE",
    )

    handoff = build_virtual_improvement_next_candidate_intake_handoff(readiness)

    assert handoff.status == "READY_INTAKE"
    assert handoff.intake_decision == "OPEN_NEXT_CANDIDATE"
    assert handoff.blocker_codes == ()
    assert handoff.required_follow_up == "REGISTER_NEXT_VIRTUAL_CANDIDATE"


def test_virtual_improvement_next_candidate_registration_packet_requires_ready_intake() -> (
    None
):
    handoff = VirtualImprovementNextCandidateIntakeHandoff(
        handoff_id="handoff:ready",
        summary_id="summary:ready",
        bundle_id="bundle:ready",
        queue_id="queue:ready",
        snapshot_id="snapshot:ready",
        surface_kind="RESEARCH",
        status="READY_INTAKE",
        intake_decision="OPEN_NEXT_CANDIDATE",
        blocker_codes=(),
        required_follow_up="REGISTER_NEXT_VIRTUAL_CANDIDATE",
    )

    packet = build_virtual_improvement_next_candidate_registration_packet(handoff)

    assert isinstance(packet, VirtualImprovementNextCandidateRegistrationPacket)
    assert packet.status == "REGISTER_NEXT_CANDIDATE"
    assert packet.candidate_reference == "next-candidate:snapshot:ready"
    assert packet.provenance_refs[0] == "next-candidate-intake:handoff:ready"


def test_virtual_improvement_next_candidate_refusal_artifact_requires_blocked_intake() -> (
    None
):
    handoff = VirtualImprovementNextCandidateIntakeHandoff(
        handoff_id="handoff:blocked",
        summary_id="summary:blocked",
        bundle_id="bundle:blocked",
        queue_id="queue:blocked",
        snapshot_id="snapshot:blocked",
        surface_kind="RESEARCH",
        status="BLOCKED_INTAKE",
        intake_decision="HOLD_CURRENT_CYCLE",
        blocker_codes=("SESSION_ARTIFACT_GAP_REMAINING",),
        required_follow_up="CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
    )

    artifact = build_virtual_improvement_next_candidate_refusal_artifact(handoff)

    assert isinstance(artifact, VirtualImprovementNextCandidateRefusalArtifact)
    assert artifact.status == "REFUSE_NEXT_CANDIDATE"
    assert artifact.refusal_reason == "NEXT_CANDIDATE_NOT_READY"
    assert (
        artifact.required_follow_up
        == "CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE"
    )


def test_virtual_improvement_candidate_registry_entry_appends_ready_packet() -> None:
    packet = VirtualImprovementNextCandidateRegistrationPacket(
        packet_id="packet:ready",
        handoff_id="handoff:ready",
        summary_id="summary:ready",
        bundle_id="bundle:ready",
        queue_id="queue:ready",
        snapshot_id="snapshot:ready",
        surface_kind="RESEARCH",
        status="REGISTER_NEXT_CANDIDATE",
        candidate_reference="next-candidate:snapshot:ready",
        provenance_refs=(
            "next-candidate-intake:handoff:ready",
            "session-readiness:summary:ready",
        ),
    )

    entry = build_virtual_improvement_candidate_registry_entry(packet)

    assert isinstance(entry, VirtualImprovementCandidateRegistryEntry)
    assert entry.status == "CANDIDATE_REGISTERED"
    assert entry.candidate_reference == packet.candidate_reference
    assert entry.provenance_refs == packet.provenance_refs


def test_virtual_improvement_refusal_ledger_entry_appends_blocked_artifact() -> None:
    artifact = VirtualImprovementNextCandidateRefusalArtifact(
        artifact_id="artifact:blocked",
        handoff_id="handoff:blocked",
        summary_id="summary:blocked",
        bundle_id="bundle:blocked",
        queue_id="queue:blocked",
        snapshot_id="snapshot:blocked",
        surface_kind="RESEARCH",
        status="REFUSE_NEXT_CANDIDATE",
        blocker_codes=("SESSION_ARTIFACT_GAP_REMAINING",),
        refusal_reason="NEXT_CANDIDATE_NOT_READY",
        required_follow_up="CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
    )

    entry = build_virtual_improvement_refusal_ledger_entry(artifact)

    assert isinstance(entry, VirtualImprovementRefusalLedgerEntry)
    assert entry.status == "REFUSAL_RECORDED"
    assert entry.blocker_codes == artifact.blocker_codes
    assert entry.required_follow_up == artifact.required_follow_up


def test_virtual_improvement_candidate_lifecycle_snapshot_uses_registry_entry() -> None:
    entry = VirtualImprovementCandidateRegistryEntry(
        entry_id="registry:ready",
        packet_id="packet:ready",
        queue_id="queue:ready",
        snapshot_id="snapshot:ready",
        surface_kind="RESEARCH",
        status="CANDIDATE_REGISTERED",
        candidate_reference="next-candidate:snapshot:ready",
        provenance_refs=("session-readiness:summary:ready",),
    )

    snapshot = build_virtual_improvement_candidate_lifecycle_snapshot_from_registry(
        entry
    )

    assert isinstance(snapshot, VirtualImprovementCandidateLifecycleSnapshot)
    assert snapshot.lifecycle_state == "REGISTERED"
    assert snapshot.source_kind == "REGISTRY"
    assert snapshot.required_follow_up == "MONITOR_REGISTERED_CANDIDATE"


def test_virtual_improvement_candidate_lifecycle_snapshot_uses_refusal_entry() -> None:
    entry = VirtualImprovementRefusalLedgerEntry(
        entry_id="ledger:blocked",
        artifact_id="artifact:blocked",
        queue_id="queue:blocked",
        snapshot_id="snapshot:blocked",
        surface_kind="RESEARCH",
        status="REFUSAL_RECORDED",
        blocker_codes=("SESSION_ARTIFACT_GAP_REMAINING",),
        refusal_reason="NEXT_CANDIDATE_NOT_READY",
        required_follow_up="CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
    )

    snapshot = build_virtual_improvement_candidate_lifecycle_snapshot_from_refusal(
        entry
    )

    assert snapshot.lifecycle_state == "REFUSED"
    assert snapshot.source_kind == "REFUSAL_LEDGER"
    assert snapshot.blocker_codes == ("SESSION_ARTIFACT_GAP_REMAINING",)


def test_virtual_improvement_candidate_outcome_dashboard_payload_summarizes_registered() -> (
    None
):
    snapshot = VirtualImprovementCandidateLifecycleSnapshot(
        snapshot_id="lifecycle:ready",
        queue_id="queue:ready",
        source_kind="REGISTRY",
        surface_kind="RESEARCH",
        lifecycle_state="REGISTERED",
        subject_reference="next-candidate:snapshot:ready",
        provenance_refs=("session-readiness:summary:ready",),
        blocker_codes=(),
        required_follow_up="MONITOR_REGISTERED_CANDIDATE",
    )

    dashboard = build_virtual_improvement_candidate_outcome_dashboard_payload(snapshot)

    assert isinstance(dashboard, VirtualImprovementCandidateOutcomeDashboardPayload)
    assert dashboard.outcome_state == "REGISTERED"
    assert dashboard.blocker_count == 0
    assert dashboard.follow_up_category == "MONITORING"


def test_virtual_improvement_candidate_outcome_dashboard_payload_summarizes_refused() -> (
    None
):
    snapshot = VirtualImprovementCandidateLifecycleSnapshot(
        snapshot_id="lifecycle:blocked",
        queue_id="queue:blocked",
        source_kind="REFUSAL_LEDGER",
        surface_kind="RESEARCH",
        lifecycle_state="REFUSED",
        subject_reference="artifact:blocked",
        provenance_refs=("refusal-ledger:ledger:blocked",),
        blocker_codes=("SESSION_ARTIFACT_GAP_REMAINING",),
        required_follow_up="CLOSE_SESSION_ARTIFACT_GAPS_BEFORE_NEXT_CANDIDATE",
    )

    dashboard = build_virtual_improvement_candidate_outcome_dashboard_payload(snapshot)

    assert dashboard.outcome_state == "REFUSED"
    assert dashboard.blocker_count == 1
    assert dashboard.follow_up_category == "ARTIFACT_GAP_CLOSURE"


def test_virtual_improvement_candidate_cycle_executive_summary_summarizes_registered() -> (
    None
):
    dashboard = VirtualImprovementCandidateOutcomeDashboardPayload(
        dashboard_id="dashboard:ready",
        lifecycle_snapshot_id="lifecycle:ready",
        queue_id="queue:ready",
        surface_kind="RESEARCH",
        outcome_state="REGISTERED",
        blocker_count=0,
        provenance_count=2,
        follow_up_category="MONITORING",
        subject_reference="next-candidate:snapshot:ready",
    )

    summary = build_virtual_improvement_candidate_cycle_executive_summary(dashboard)

    assert isinstance(summary, VirtualImprovementCandidateCycleExecutiveSummary)
    assert summary.outcome_state == "REGISTERED"
    assert summary.next_action == "MONITOR_REGISTERED_CANDIDATE"
    assert summary.blocker_count == 0


def test_virtual_improvement_candidate_cycle_executive_summary_summarizes_refused() -> (
    None
):
    dashboard = VirtualImprovementCandidateOutcomeDashboardPayload(
        dashboard_id="dashboard:blocked",
        lifecycle_snapshot_id="lifecycle:blocked",
        queue_id="queue:blocked",
        surface_kind="RESEARCH",
        outcome_state="REFUSED",
        blocker_count=1,
        provenance_count=1,
        follow_up_category="ARTIFACT_GAP_CLOSURE",
        subject_reference="artifact:blocked",
    )

    summary = build_virtual_improvement_candidate_cycle_executive_summary(dashboard)

    assert summary.outcome_state == "REFUSED"
    assert summary.next_action == "CLOSE_ARTIFACT_GAPS_OR_REVIEW_ESCALATIONS"
    assert summary.blocker_count == 1


@pytest.mark.parametrize(
    ("refused", "overrides", "message"),
    [
        (False, {"surface_kind": "LIVE"}, "surface kind is invalid"),
        (False, {"source_kind": "UNKNOWN"}, "source kind is invalid"),
        (False, {"lifecycle_state": "PENDING"}, "state is invalid"),
        (False, {"provenance_refs": ("ref", "ref")}, "provenance refs"),
        (True, {"blocker_codes": ("BLOCKED", "BLOCKED")}, "blocker codes"),
        (False, {"provenance_refs": ()}, "requires provenance refs"),
        (False, {"lifecycle_state": "REFUSED"}, "registry lifecycle"),
        (False, {"blocker_codes": ("BLOCKED",)}, "cannot contain blockers"),
        (False, {"required_follow_up": "REVIEW"}, "follow-up is invalid"),
        (True, {"lifecycle_state": "REGISTERED"}, "refusal lifecycle"),
        (True, {"blocker_codes": ()}, "requires blockers"),
        (True, {"required_follow_up": "MONITOR"}, "follow-up is invalid"),
        (False, {"execution_allowed": True}, "cannot authorize trading"),
    ],
)
def test_virtual_improvement_lifecycle_snapshot_rejects_invalid_policy_states(
    refused: bool,
    overrides: dict[str, object],
    message: str,
) -> None:
    snapshot = VirtualImprovementCandidateLifecycleSnapshot(
        snapshot_id="lifecycle:test",
        queue_id="queue:test",
        source_kind="REFUSAL_LEDGER" if refused else "REGISTRY",
        surface_kind="RESEARCH",
        lifecycle_state="REFUSED" if refused else "REGISTERED",
        subject_reference="candidate:test",
        provenance_refs=("evidence:test",),
        blocker_codes=("BLOCKED",) if refused else (),
        required_follow_up=(
            "REVIEW_ESCALATIONS_BEFORE_NEXT_CANDIDATE"
            if refused
            else "MONITOR_REGISTERED_CANDIDATE"
        ),
    )
    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(snapshot, **overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"hypothesis_id": " "}, "identity fields cannot be empty"),
        ({"created_at": datetime(2026, 1, 1)}, "created_at must be timezone-aware"),
        ({"updated_at": datetime(2026, 1, 1)}, "updated_at must be timezone-aware"),
        ({"invalidation_conditions": ()}, "requires explicit invalidation"),
        ({"invalidation_conditions": (" ",)}, "requires explicit invalidation"),
        ({"artifact_ids": ("a", "a")}, "artifact IDs must be unique"),
        ({"execution_allowed": True}, "cannot grant execution authority"),
    ],
)
def test_research_hypothesis_rejects_invalid_policy_states(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(hypothesis(), **overrides)


def test_research_hypothesis_transition_requires_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        hypothesis().transition(
            HypothesisStatus.RESEARCH,
            updated_at=datetime(2026, 1, 1),
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"items": "text"}, "must be a sequence"),
        ({"items": []}, "must not be empty"),
        ({"items": ["ok", " "]}, "must not contain blank"),
        ({"items": ["same", "same"]}, "must contain unique"),
    ],
)
def test_tuple_of_text_rejects_ambiguous_evidence_lists(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        governance._tuple_of_text(payload, "items")


def test_tuple_of_text_allows_explicit_empty_list() -> None:
    assert governance._tuple_of_text({"items": []}, "items", allow_empty=True) == ()

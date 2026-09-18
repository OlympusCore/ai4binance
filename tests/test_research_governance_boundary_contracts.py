"""Reject forged authority and contradictory evidence across research handoffs."""

from dataclasses import replace
from typing import Any

import pytest

from ai4binance import research_governance as g


@pytest.fixture
def stages() -> dict[str, Any]:
    review = g.VirtualImprovementReviewInput(
        handoff_id="handoff:test",
        snapshot_id="snapshot:test",
        surface_kind="RESEARCH",
        objective="Validate a bounded research candidate.",
        assurance_artifact_refs=("virtual_improvement_queue_assurance.json",),
        evidence_refs=("virtual_improvement_queue_assurance.json",),
        governance_refs=("VirtualImprovementResearchQueue",),
        required_output_fields=(
            "review_outcome",
            "recommended_experiment",
            "evidence_gap_assessment",
        ),
    )
    result = g.build_virtual_improvement_review_result(review)
    proposal = g.build_virtual_improvement_experiment_proposal(result)
    task = g.build_virtual_improvement_experiment_task(proposal)
    queue = g.build_virtual_improvement_experiment_task_queue(
        queue_id="queue:test",
        snapshot_id="snapshot:test",
        surface_kind="RESEARCH",
        tasks=(task,),
    )
    planner = g.build_virtual_improvement_research_work_planner(queue)
    handoff = g.build_virtual_improvement_operator_handoff_summary(
        queue=queue, planner=planner
    )
    inbox = g.build_virtual_improvement_research_execution_inbox(handoff)
    manifest = g.build_virtual_improvement_research_execution_session_manifest(inbox)
    journal = g.build_virtual_improvement_research_session_journal(manifest)
    closure = g.build_virtual_improvement_research_session_closure_record(journal)
    bundle = g.build_virtual_improvement_research_session_artifact_bundle(
        manifest=manifest, journal=journal, closure=closure
    )
    readiness = g.build_virtual_improvement_research_session_readiness_summary(bundle)
    intake = g.build_virtual_improvement_next_candidate_intake_handoff(readiness)
    refusal = g.build_virtual_improvement_next_candidate_refusal_artifact(intake)
    ledger = g.build_virtual_improvement_refusal_ledger_entry(refusal)
    ready = g.VirtualImprovementResearchSessionReadinessSummary(
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
    ready_intake = g.build_virtual_improvement_next_candidate_intake_handoff(ready)
    packet = g.build_virtual_improvement_next_candidate_registration_packet(
        ready_intake
    )
    registry = g.build_virtual_improvement_candidate_registry_entry(packet)
    snapshot = g.build_virtual_improvement_candidate_lifecycle_snapshot_from_registry(
        registry
    )
    dashboard = g.build_virtual_improvement_candidate_outcome_dashboard_payload(
        snapshot
    )
    executive = g.build_virtual_improvement_candidate_cycle_executive_summary(dashboard)
    return locals()


STAGES = (
    "review",
    "result",
    "proposal",
    "task",
    "queue",
    "planner",
    "handoff",
    "inbox",
    "manifest",
    "journal",
    "closure",
    "bundle",
    "readiness",
    "intake",
    "refusal",
    "ledger",
    "packet",
    "registry",
    "dashboard",
    "executive",
)


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("execution_allowed", True, "cannot authorize trading"),
        ("promotion_status", "LIVE", "cannot authorize trading"),
        ("live_eligibility_status", "LIVE_ALLOWED", "cannot authorize trading"),
        ("surface_kind", "LIVE", "surface kind is invalid"),
    ],
)
def test_research_stage_cannot_grant_authority(
    stages: dict[str, Any], stage: str, field: str, value: object, message: str
) -> None:
    original = stages[stage]
    payload = original.to_payload()
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match=message):
        replace(original, **{field: value})


@pytest.mark.parametrize(
    ("stage", "field"),
    [
        ("result", "assurance_artifact_refs"),
        ("result", "evidence_refs"),
        ("result", "follow_up_artifact_refs"),
        ("proposal", "required_data"),
        ("proposal", "source_artifact_refs"),
        ("task", "required_data"),
        ("task", "source_artifact_refs"),
        ("planner", "selected_ready_task_ids"),
        ("planner", "escalated_task_ids"),
        ("planner", "next_safe_actions"),
        ("handoff", "selected_task_briefs"),
        ("handoff", "escalated_blocker_briefs"),
        ("handoff", "next_safe_actions"),
        ("inbox", "ready_work_items"),
        ("inbox", "escalation_items"),
        ("inbox", "next_safe_actions"),
        ("manifest", "escalation_items"),
        ("manifest", "action_order"),
        ("manifest", "artifact_refs"),
        ("journal", "escalation_items"),
        ("journal", "consumed_action_order"),
        ("journal", "artifact_refs"),
        ("closure", "escalation_items"),
        ("closure", "completed_actions"),
        ("closure", "produced_artifact_refs"),
        ("bundle", "required_artifact_refs"),
        ("bundle", "produced_artifact_refs"),
        ("bundle", "missing_artifact_refs"),
        ("bundle", "escalation_items"),
        ("readiness", "blocker_codes"),
        ("intake", "blocker_codes"),
        ("packet", "provenance_refs"),
        ("refusal", "blocker_codes"),
        ("registry", "provenance_refs"),
        ("ledger", "blocker_codes"),
    ],
)
def test_research_evidence_and_actions_cannot_be_double_counted(
    stages: dict[str, Any], stage: str, field: str
) -> None:
    with pytest.raises(ValueError, match="unique"):
        replace(stages[stage], **{field: ("duplicate", "duplicate")})


@pytest.mark.parametrize(
    "stage",
    [
        "review",
        "queue",
        "planner",
        "handoff",
        "inbox",
        "manifest",
        "journal",
        "closure",
        "bundle",
        "readiness",
        "intake",
        "packet",
        "refusal",
        "registry",
        "ledger",
    ],
)
def test_research_stage_rejects_unknown_status(
    stages: dict[str, Any], stage: str
) -> None:
    with pytest.raises(ValueError, match="status"):
        replace(stages[stage], status="UNRECOGNIZED")


@pytest.mark.parametrize(
    ("stage", "overrides", "message"),
    [
        ("review", {"priority": "P9"}, "priority"),
        ("review", {"review_required": False}, "explicit review"),
        ("review", {"governance_refs": ()}, "queue governance"),
        ("review", {"evidence_refs": ()}, "part of evidence"),
        ("review", {"required_output_fields": ()}, "output contract"),
        ("result", {"outcome": "UNKNOWN"}, "outcome"),
        ("result", {"evidence_refs": ()}, "part of evidence"),
        (
            "result",
            {"outcome": g.VirtualImprovementReviewOutcome.INVESTIGATION_REQUIRED},
            "blockers",
        ),
        ("proposal", {"priority": "P9"}, "priority"),
        ("proposal", {"required_data": ()}, "requires data"),
        ("task", {"priority": "P9"}, "priority"),
        ("task", {"required_data": ()}, "requires data"),
        (
            "task",
            {"status": g.VirtualImprovementExperimentTaskStatus.QUEUED},
            "inconsistent",
        ),
        ("queue", {"tasks": ()}, "requires tasks"),
        ("queue", {"ready_task_count": -1}, "negative"),
        ("queue", {"ready_task_count": 3}, "inconsistent"),
        ("planner", {"next_safe_actions": ()}, "requires next safe actions"),
        ("planner", {"status": "EVIDENCE_ESCALATION_REQUIRED"}, "inconsistent"),
        ("handoff", {"status": "ESCALATION_HANDOFF"}, "inconsistent"),
        ("inbox", {"status": "ESCALATION_INBOX"}, "inconsistent"),
        ("inbox", {"next_safe_actions": ()}, "requires next safe actions"),
        ("manifest", {"chosen_ready_item": " "}, "ready item"),
        ("manifest", {"chosen_ready_item": None}, "chosen ready item"),
        ("manifest", {"action_order": ()}, "requires actions"),
        ("manifest", {"status": "ESCALATION_SESSION"}, "inconsistent"),
        ("journal", {"chosen_ready_item": " "}, "ready item"),
        ("journal", {"chosen_ready_item": None}, "chosen ready item"),
        ("journal", {"consumed_action_order": ()}, "requires actions"),
        ("journal", {"status": "ESCALATION_JOURNAL"}, "inconsistent"),
        ("journal", {"closure_result": "INVALID"}, "closure result"),
        ("closure", {"chosen_ready_item": " "}, "ready item"),
        ("closure", {"chosen_ready_item": None}, "chosen ready item"),
        ("closure", {"completed_actions": ()}, "requires actions"),
        ("closure", {"status": "ESCALATED_RESEARCH_ONLY"}, "inconsistent"),
        ("closure", {"closure_reason": "INVALID"}, "reason"),
        ("bundle", {"required_artifact_refs": ()}, "requires required"),
        ("bundle", {"missing_artifact_refs": ("unrelated",)}, "subset"),
        ("readiness", {"verdict": "UNKNOWN"}, "verdict"),
        ("readiness", {"status": "READY_SUMMARY"}, "inconsistent"),
        ("intake", {"intake_decision": "UNKNOWN"}, "decision"),
        ("intake", {"status": "READY_INTAKE"}, "blocked next candidate"),
        ("intake", {"blocker_codes": ()}, "requires blockers"),
        ("intake", {"required_follow_up": "TRADE"}, "follow-up"),
        ("ready_intake", {"status": "BLOCKED_INTAKE"}, "ready next candidate"),
        ("ready_intake", {"blocker_codes": ("GAP",)}, "cannot contain blockers"),
        ("ready_intake", {"required_follow_up": "TRADE"}, "follow-up"),
        ("packet", {"provenance_refs": ()}, "requires provenance"),
        ("registry", {"provenance_refs": ()}, "requires provenance"),
        ("refusal", {"blocker_codes": ()}, "requires blockers"),
        ("refusal", {"required_follow_up": "TRADE"}, "follow-up"),
        ("refusal", {"refusal_reason": "UNKNOWN"}, "reason"),
        ("ledger", {"blocker_codes": ()}, "requires blockers"),
        ("ledger", {"required_follow_up": "TRADE"}, "follow-up"),
        ("ledger", {"refusal_reason": "UNKNOWN"}, "reason"),
        ("dashboard", {"outcome_state": "UNKNOWN"}, "state"),
        ("dashboard", {"follow_up_category": "UNKNOWN"}, "category"),
        ("dashboard", {"blocker_count": -1}, "counts"),
        ("dashboard", {"follow_up_category": "ESCALATION_REVIEW"}, "inconsistent"),
        ("dashboard", {"blocker_count": 1}, "cannot report blockers"),
        ("executive", {"outcome_state": "UNKNOWN"}, "state"),
        ("executive", {"blocker_count": -1}, "count"),
        ("executive", {"next_action": "TRADE"}, "inconsistent"),
        ("executive", {"blocker_count": 1}, "cannot report blockers"),
    ],
)
def test_research_stage_rejects_contradictory_handoffs(
    stages: dict[str, Any], stage: str, overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(stages[stage], **overrides)

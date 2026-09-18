from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from ai4binance.events import (
    CanonicalTraceJournal,
    ConsequentialTraceKind,
    TraceabilityRequirement,
    TraceabilityStatus,
    canonical_trace_journal_path,
)
from ai4binance.ops.continuous_assurance import (
    AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF,
    EAACIE_INSTRUCTION_REF,
    EAACIE_INSTRUCTION_REFS,
    SECURITY_AUDIT_CONTROL_PROFILE,
    AuditDomain,
    AuditObservedEntity,
    AuditRouteDecision,
    AuditStateComparison,
    AuditStormPolicy,
    AuditStormStatus,
    AuditTriggerMode,
    AuditTriggerSeverity,
    AuditTriggerSignal,
    AuditTriggerType,
    AuditWorkflowPattern,
    CentralAuditTriggerEngine,
    ContinuousAssurancePlan,
    ContinuousAuditEvent,
    HybridTriggerClass,
    SecurityAuditTriggerType,
    SecurityDomain,
    SemanticContractRecord,
    TrustAssuranceResult,
    UncertaintyAssessmentRecord,
    UncertaintyLevel,
    build_continuous_assurance_plan,
    build_trust_assurance_bundle,
    events_from_auto_audit_cycle,
    security_audit_event,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def test_trigger_router_maps_privacy_event_to_human_reviewed_assurance() -> None:
    event = ContinuousAuditEvent(
        event_id="privacy-leak-1",
        trigger_type=AuditTriggerType.PRIVACY_OR_LEAKAGE,
        entity_type="PUBLIC_REPORT",
        entity_id="reports/ykb/YKB_REPORT.md",
        observed_at=NOW,
        evidence_refs=("privacy-boundary",),
        root_cause_key="privacy-leakage",
    )

    plan = build_continuous_assurance_plan((event,))
    decision = plan.route_decisions[0]

    assert plan.workflow_pattern == "ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP"
    assert decision.storm_status is AuditStormStatus.ACCEPTED
    assert decision.domains == (
        AuditDomain.PRIVACY_KVKK,
        AuditDomain.CYBERSECURITY,
        AuditDomain.DGE_ASSURANCE,
    )
    assert decision.hybrid_trigger_classes == (
        HybridTriggerClass.RISK,
        HybridTriggerClass.EVIDENCE,
    )
    assert AuditWorkflowPattern.HUMAN_IN_THE_LOOP in decision.workflow_patterns
    assert decision.review_required is True
    assert decision.execution_allowed is False
    assert decision.promotion_status == "RESEARCH_ONLY"
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "HUMAN_REVIEW_REQUIRED" in decision.blockers
    assert "run:privacy-boundary" in decision.action_refs
    assert plan.to_payload()["instruction_ref"] == AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF
    assert plan.to_payload()["instruction_refs"] == list(EAACIE_INSTRUCTION_REFS)
    assert decision.to_payload()["instruction_ref"] == (
        AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF
    )
    assert decision.to_payload()["instruction_refs"] == list(EAACIE_INSTRUCTION_REFS)


def test_audit_storm_guard_suppresses_duplicate_events_inside_cooldown() -> None:
    first = ContinuousAuditEvent(
        event_id="runtime-drift-1",
        trigger_type=AuditTriggerType.PERFORMANCE_DRIFT,
        entity_type="BLOCKER",
        entity_id="runtime:RUNTIME_DEGRADED",
        observed_at=NOW,
        evidence_refs=("system-report",),
        root_cause_key="runtime:RUNTIME_DEGRADED",
    )
    duplicate = replace(
        first,
        event_id="runtime-drift-2",
        observed_at=NOW + timedelta(seconds=60),
    )

    plan = build_continuous_assurance_plan(
        (first, duplicate),
        policy=AuditStormPolicy(cooldown_seconds=900),
    )

    assert plan.accepted_count == 1
    assert plan.suppressed_count == 1
    assert plan.route_decisions[1].storm_status is AuditStormStatus.SUPPRESSED_COOLDOWN
    assert "AUDIT_COOLDOWN_ACTIVE" in plan.route_decisions[1].blockers
    assert plan.execution_allowed is False


def test_auto_audit_cycle_events_route_blockers_to_expected_domains() -> None:
    events = events_from_auto_audit_cycle(
        observed_at=NOW,
        system_status="RUNNING_WITH_BLOCKERS",
        blockers=("runtime:RUNTIME_DEGRADED", "validation:OOS_APPROVAL_MISSING"),
        new_blockers=("validation:OOS_APPROVAL_MISSING",),
        resolved_blockers=("opportunities:NO_READY_CANDIDATE",),
        privacy_leak_status="CLEAR",
    )

    plan = build_continuous_assurance_plan(events)
    routes = {
        decision.trigger_type: decision.domains for decision in plan.route_decisions
    }

    assert (
        AuditDomain.PARAMETER_GOVERNANCE in routes[AuditTriggerType.PARAMETER_PROMOTION]
    )
    assert AuditDomain.DGE_ASSURANCE in routes[AuditTriggerType.DECISION_AUDIT]
    assert "VALIDATION_EVIDENCE_REQUIRED" in plan.blockers
    assert plan.promotion_status == "RESEARCH_ONLY"
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_continuous_assurance_rejects_hidden_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize trading"):
        ContinuousAuditEvent(
            event_id="bad-authority",
            trigger_type=AuditTriggerType.EXECUTION_AUDIT,
            entity_type="ORDER",
            entity_id="HOTUSDT",
            observed_at=NOW,
            evidence_refs=("test",),
            execution_allowed=True,
        )


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: AuditStormPolicy(cooldown_seconds=-1), "cooldown"),
        (lambda: AuditStormPolicy(correlation_window_seconds=0), "correlation"),
        (lambda: AuditStormPolicy(max_parallel_audits=0), "parallel"),
        (lambda: AuditStormPolicy(max_recursion_depth=-1), "recursion"),
    ],
)
def test_audit_storm_policy_rejects_invalid_limits(
    build: Callable[[], AuditStormPolicy],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda event: replace(event, event_id=""), "audit event id"),
        (lambda event: replace(event, entity_type=""), "audit event entity"),
        (lambda event: replace(event, entity_id=""), "audit event entity"),
        (lambda event: replace(event, evidence_refs=()), "requires evidence"),
        (
            lambda event: replace(event, evidence_refs=("a", "a")),
            "must be unique",
        ),
        (lambda event: replace(event, evidence_refs=(" ",)), "cannot be blank"),
        (lambda event: replace(event, recursion_depth=-1), "recursion depth"),
    ],
)
def test_audit_event_validates_identity_and_evidence(
    mutate: Callable[[ContinuousAuditEvent], ContinuousAuditEvent],
    message: str,
) -> None:
    event = _event(AuditTriggerType.MANUAL_AUDIT, event_id="event-1")

    with pytest.raises(ValueError, match=message):
        mutate(event)


def test_audit_event_requires_timezone_aware_observation() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ContinuousAuditEvent(
            event_id="naive-time",
            trigger_type=AuditTriggerType.MANUAL_AUDIT,
            entity_type="SYSTEM",
            entity_id="AI4BINANCE",
            observed_at=datetime(2026, 8, 9, 12, 0),
            evidence_refs=("manual",),
        )


def test_route_and_plan_contracts_reject_invalid_or_promoted_state() -> None:
    event = _event(AuditTriggerType.MANUAL_AUDIT)
    route = build_continuous_assurance_plan((event,)).route_decisions[0]

    with pytest.raises(ValueError, match="event id"):
        replace(route, event_id="")
    with pytest.raises(ValueError, match="at least one domain"):
        replace(route, domains=())
    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(route, promotion_status="APPROVED")
    with pytest.raises(ValueError, match="plan id"):
        ContinuousAssurancePlan(
            plan_id="",
            observed_at=NOW,
            workflow_pattern="ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP",
            route_decisions=(route,),
            accepted_count=1,
            suppressed_count=0,
            blockers=("LIVE_ORDER_BLOCKED",),
        )
    with pytest.raises(ValueError, match="requires route decisions"):
        ContinuousAssurancePlan(
            plan_id="plan",
            observed_at=NOW,
            workflow_pattern="ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP",
            route_decisions=(),
            accepted_count=1,
            suppressed_count=0,
            blockers=("LIVE_ORDER_BLOCKED",),
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(route, execution_allowed=True)


def test_continuous_plan_rejects_empty_events_and_invalid_counts() -> None:
    with pytest.raises(ValueError, match="requires events"):
        build_continuous_assurance_plan(())

    route = build_continuous_assurance_plan(
        (_event(AuditTriggerType.SCHEDULED_AUDIT),)
    ).route_decisions[0]
    with pytest.raises(ValueError, match="counts"):
        ContinuousAssurancePlan(
            plan_id="plan",
            observed_at=NOW,
            workflow_pattern="ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP",
            route_decisions=(route,),
            accepted_count=-1,
            suppressed_count=0,
            blockers=("LIVE_ORDER_BLOCKED",),
        )


def test_continuous_plan_requires_aware_time_and_rejects_authority() -> None:
    route = build_continuous_assurance_plan(
        (_event(AuditTriggerType.SCHEDULED_AUDIT),)
    ).route_decisions[0]

    with pytest.raises(ValueError, match="timestamp"):
        ContinuousAssurancePlan(
            plan_id="plan",
            observed_at=datetime(2026, 8, 9, 12, 0),
            workflow_pattern="ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP",
            route_decisions=(route,),
            accepted_count=1,
            suppressed_count=0,
            blockers=("LIVE_ORDER_BLOCKED",),
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        ContinuousAssurancePlan(
            plan_id="plan",
            observed_at=NOW,
            workflow_pattern="ROUTING_EVALUATOR_OPTIMIZER_HUMAN_IN_THE_LOOP",
            route_decisions=(route,),
            accepted_count=1,
            suppressed_count=0,
            blockers=("LIVE_ORDER_BLOCKED",),
            execution_allowed=True,
        )


def test_same_root_cause_merge_and_recursion_guard_are_report_only() -> None:
    first = _event(
        AuditTriggerType.SYSTEM_BLOCKER,
        event_id="root-1",
        entity_id="blocker-a",
        root_cause_key="same-root",
    )
    same_root = _event(
        AuditTriggerType.SYSTEM_BLOCKER,
        event_id="root-2",
        entity_id="blocker-b",
        root_cause_key="same-root",
        observed_at=NOW + timedelta(seconds=901),
    )
    recursive = _event(
        AuditTriggerType.SYSTEM_BLOCKER,
        event_id="recursive",
        entity_id="loop",
        recursion_depth=4,
        observed_at=NOW + timedelta(seconds=902),
    )

    plan = build_continuous_assurance_plan((first, same_root, recursive))

    assert plan.route_decisions[1].storm_status is (
        AuditStormStatus.MERGED_SAME_ROOT_CAUSE
    )
    assert "AUDIT_SAME_ROOT_CAUSE_MERGED" in plan.route_decisions[1].blockers
    assert plan.route_decisions[2].storm_status is (
        AuditStormStatus.BLOCKED_RECURSION_DEPTH
    )
    assert "AUDIT_RECURSION_DEPTH_EXCEEDED" in plan.route_decisions[2].blockers
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "trigger_type",
    tuple(AuditTriggerType),
)
def test_all_trigger_types_have_a_deterministic_route(
    trigger_type: AuditTriggerType,
) -> None:
    plan = build_continuous_assurance_plan((_event(trigger_type),))
    decision = plan.route_decisions[0]

    assert decision.trigger_type is trigger_type
    assert decision.hybrid_trigger_classes
    assert decision.domains
    assert AuditWorkflowPattern.ROUTING in decision.workflow_patterns
    assert AuditWorkflowPattern.EVALUATOR_OPTIMIZER in decision.workflow_patterns
    assert decision.scope_refs[0].startswith("entity:")
    assert decision.to_payload()["execution_allowed"] is False


def test_hybrid_trigger_model_covers_all_channels() -> None:
    plan = build_continuous_assurance_plan(
        (
            _event(AuditTriggerType.STATE_TRANSITION, event_id="event"),
            _event(AuditTriggerType.CODE_CHANGE, event_id="change"),
            _event(AuditTriggerType.PERFORMANCE_DRIFT, event_id="drift"),
            _event(AuditTriggerType.SCHEDULED_AUDIT, event_id="schedule"),
            _event(AuditTriggerType.PRIVACY_OR_LEAKAGE, event_id="risk"),
            _event(AuditTriggerType.DATA_QUALITY, event_id="evidence"),
            _event(AuditTriggerType.MANUAL_AUDIT, event_id="manual"),
        )
    )

    assert set(plan.hybrid_trigger_classes) == set(HybridTriggerClass)
    assert plan.hybrid_class_counts["EVENT"] >= 1
    assert plan.hybrid_class_counts["CHANGE"] >= 1
    assert plan.hybrid_class_counts["DRIFT"] >= 1
    assert plan.hybrid_class_counts["SCHEDULE"] >= 1
    assert plan.hybrid_class_counts["RISK"] >= 1
    assert plan.hybrid_class_counts["EVIDENCE"] >= 1
    assert plan.hybrid_class_counts["MANUAL"] >= 1
    payload = plan.to_payload()
    trigger_classes = cast(list[str], payload["hybrid_trigger_classes"])
    class_counts = cast(dict[str, int], payload["hybrid_class_counts"])
    assert set(trigger_classes) == {
        "EVENT",
        "CHANGE",
        "DRIFT",
        "SCHEDULE",
        "RISK",
        "EVIDENCE",
        "MANUAL",
    }
    assert class_counts["MANUAL"] == 1


def test_central_audit_trigger_engine_covers_required_trigger_modes() -> None:
    engine = CentralAuditTriggerEngine()
    plan = engine.build_plan(
        (
            _signal(
                "event",
                AuditObservedEntity.DECISION,
                (AuditTriggerMode.EVENT_DRIVEN,),
            ),
            _signal(
                "risk",
                AuditObservedEntity.CONFIGURATION,
                (AuditTriggerMode.RISK_DRIVEN,),
                risk_score=90,
            ),
            _signal(
                "scheduled",
                AuditObservedEntity.SYSTEM_BEHAVIOR,
                (AuditTriggerMode.SCHEDULED,),
                comparisons=(),
            ),
            _signal(
                "anomaly",
                AuditObservedEntity.DATA,
                (AuditTriggerMode.ANOMALY_DRIVEN,),
            ),
            _signal(
                "lifecycle",
                AuditObservedEntity.OPERATION,
                (AuditTriggerMode.LIFECYCLE_DRIVEN,),
            ),
        )
    )

    assert set(plan.trigger_modes) == set(AuditTriggerMode)
    assert plan.trigger_mode_counts["EVENT_DRIVEN"] >= 1
    assert plan.trigger_mode_counts["RISK_DRIVEN"] >= 1
    assert plan.trigger_mode_counts["SCHEDULED"] >= 1
    assert plan.trigger_mode_counts["ANOMALY_DRIVEN"] >= 1
    assert plan.trigger_mode_counts["LIFECYCLE_DRIVEN"] >= 1
    payload = plan.to_payload()
    assert set(cast(list[str], payload["trigger_modes"])) == {
        "EVENT_DRIVEN",
        "RISK_DRIVEN",
        "SCHEDULED",
        "ANOMALY_DRIVEN",
        "LIFECYCLE_DRIVEN",
    }
    assert plan.execution_allowed is False
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_central_audit_trigger_engine_audits_expected_state_deviation() -> None:
    engine = CentralAuditTriggerEngine()
    events = engine.events_from_signals(
        (
            _signal("state", AuditObservedEntity.STATE),
            _signal("decision", AuditObservedEntity.DECISION),
            _signal("data", AuditObservedEntity.DATA),
            _signal("config", AuditObservedEntity.CONFIGURATION),
            _signal("model", AuditObservedEntity.MODEL),
            _signal("operation", AuditObservedEntity.OPERATION),
            _signal("system", AuditObservedEntity.SYSTEM_BEHAVIOR),
        )
    )
    plan = build_continuous_assurance_plan(events)

    assert {event.trigger_type for event in events} == {
        AuditTriggerType.STATE_TRANSITION,
        AuditTriggerType.DECISION_AUDIT,
        AuditTriggerType.DATA_QUALITY,
        AuditTriggerType.CONFIGURATION_CHANGE,
        AuditTriggerType.PARAMETER_PROMOTION,
        AuditTriggerType.EXECUTION_AUDIT,
        AuditTriggerType.SYSTEM_BLOCKER,
    }
    assert plan.accepted_count == 7
    assert "LIVE_ORDER_BLOCKED" in plan.blockers


def test_central_audit_trigger_engine_ignores_allowed_non_risk_state() -> None:
    engine = CentralAuditTriggerEngine()
    signal = _signal(
        "allowed",
        AuditObservedEntity.STATE,
        comparisons=(
            AuditStateComparison(
                field="execution_allowed",
                observed="false",
                allowed_values=("false",),
            ),
        ),
        risk_score=10,
    )

    assert signal.audit_required is False
    assert engine.events_from_signals((signal,)) == ()
    with pytest.raises(ValueError, match="no audit-triggering deviations"):
        engine.build_plan((signal,))


def test_central_audit_trigger_engine_routes_lifecycle_state_deviation() -> None:
    engine = CentralAuditTriggerEngine()
    events = engine.events_from_signals(
        (
            _signal(
                "lifecycle-state",
                AuditObservedEntity.STATE,
                (AuditTriggerMode.LIFECYCLE_DRIVEN,),
            ),
        )
    )

    assert events[0].trigger_type is AuditTriggerType.STATE_TRANSITION
    assert events[0].trigger_modes == (AuditTriggerMode.LIFECYCLE_DRIVEN,)


def test_central_audit_trigger_signal_high_risk_and_payload_contract() -> None:
    comparison = AuditStateComparison(
        field="mode",
        expected="paper",
        observed="paper",
    )
    signal = _signal(
        "p1-risk",
        AuditObservedEntity.SYSTEM_BEHAVIOR,
        comparisons=(comparison,),
        risk_score=10,
    )
    p1_signal = replace(signal, severity=AuditTriggerSeverity.P1)

    assert comparison.to_payload()["deviates"] is False
    assert signal.audit_required is False
    assert p1_signal.audit_required is True
    assert p1_signal.to_payload()["audit_required"] is True
    assert p1_signal.to_payload()["instruction_ref"] == (
        AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF
    )
    assert p1_signal.to_payload()["instruction_refs"] == list(EAACIE_INSTRUCTION_REFS)


def test_continuous_plan_embeds_tiaf_lite_trust_assurance_bundle() -> None:
    event = _event(
        AuditTriggerType.DECISION_AUDIT,
        event_id="decision-audit",
        entity_id="decision:HOTUSDT:cycle-1",
    )

    plan = build_continuous_assurance_plan((event,))
    payload = plan.to_payload()
    trust = cast(dict[str, object], payload["trust_assurance"])
    provenance = cast(dict[str, object], trust["provenance"])
    uncertainty = cast(dict[str, object], trust["uncertainty"])
    evaluations = cast(list[dict[str, object]], trust["policy_evaluations"])
    graph = cast(dict[str, object], trust["evidence_graph"])
    governance_plane = cast(dict[str, object], trust["governance_plane"])

    assert trust["framework"] == "AI4BINANCE_TIAF_LITE"
    assert governance_plane["framework"] == (
        "AI4BINANCE_TRUST_ASSURANCE_GOVERNANCE_PLANE"
    )
    assert governance_plane["external_services_enabled"] is False
    assert governance_plane["priority_counts"] == {"P0": 9, "P1": 0, "P2": 0}
    assert governance_plane["conditional_layer_counts"] == {
        "NOT_REQUESTED": 11,
        "EVIDENCE_REQUIRED": 0,
        "STAGED_RESEARCH_ONLY": 0,
    }
    assert trust["instruction_refs"] == list(EAACIE_INSTRUCTION_REFS)
    assert provenance["decision_kind"] == "CONTINUOUS_ASSURANCE_PLAN"
    assert provenance["final_action"] == "AUDIT_ROUTE_ONLY"
    assert provenance["execution_allowed"] is False
    assert provenance["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert isinstance(provenance["provenance_hash"], str)
    provenance_hash = provenance["provenance_hash"]
    assert len(provenance_hash) == 64
    assert evaluations[0]["policy_id"] == "eaacie.route.decision_audit"
    assert evaluations[0]["result"] == TrustAssuranceResult.BLOCKED.value
    assert uncertainty["level"] == UncertaintyLevel.HIGH.value
    assert uncertainty["abstention_required"] is True
    assert "DETERMINISTIC_CORE_RETAINS_EXECUTION_AUTHORITY" in cast(
        list[str],
        uncertainty["reasons"],
    )
    assert trust["execution_allowed"] is False
    assert trust["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert isinstance(trust["bundle_hash"], str)
    bundle_hash = trust["bundle_hash"]
    assert len(bundle_hash) == 64
    node_types = {
        node["node_type"] for node in cast(list[dict[str, str]], graph["nodes"])
    }
    edge_relations = {
        edge["relation"] for edge in cast(list[dict[str, str]], graph["edges"])
    }
    assert {
        "DECISION",
        "POLICY_EVALUATION",
        "UNCERTAINTY",
        "EVIDENCE_REF",
        "BLOCKER",
        "SEMANTIC_CONTRACT",
    }.issubset(node_types)
    assert {"EVALUATED_BY", "EVIDENCED_BY", "BLOCKED_BY", "GOVERNED_BY"}.issubset(
        edge_relations
    )


def test_continuous_plan_records_policy_and_decision_trace_records(
    tmp_path: Path,
) -> None:
    event = _event(
        AuditTriggerType.DECISION_AUDIT,
        event_id="decision-audit",
        entity_id="decision:HOTUSDT:cycle-1",
    )
    plan = build_continuous_assurance_plan((event,))
    trace_journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))

    bundle = build_trust_assurance_bundle(plan, trace_journal=trace_journal)
    build_trust_assurance_bundle(plan, trace_journal=trace_journal)
    audit = trace_journal.audit(
        (
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.DECISION,
                subject_ref=bundle.provenance.decision_id,
                event_name="DECISION_PROVENANCE_RECORDED",
                subject_type="DECISION_PROVENANCE_RECORD",
            ),
            *tuple(
                TraceabilityRequirement(
                    trace_kind=ConsequentialTraceKind.POLICY_EVALUATION,
                    subject_ref=evaluation.evaluation_id,
                    event_name="POLICY_EVALUATION_RECORDED",
                    subject_type="POLICY_EVALUATION_RECORD",
                )
                for evaluation in bundle.policy_evaluations
            ),
        )
    )

    assert audit.status is TraceabilityStatus.PASS
    assert audit.record_count == len(bundle.policy_evaluations) + 1
    assert {record.trace_kind for record in trace_journal.records()} == {
        ConsequentialTraceKind.DECISION,
        ConsequentialTraceKind.POLICY_EVALUATION,
    }


def test_tiaf_lite_payload_is_deterministic_for_same_plan(tmp_path: Path) -> None:
    plan = build_continuous_assurance_plan(
        (_event(AuditTriggerType.DATA_QUALITY),),
        repository_root=tmp_path,
    )

    assert plan.trust_assurance_payload == plan.trust_assurance_payload


def test_tiaf_lite_security_plan_includes_security_evidence_contract(
    tmp_path: Path,
) -> None:
    event = security_audit_event(
        SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK,
        observed_at=NOW,
        evidence_refs=("security-evidence",),
    )

    trust = build_continuous_assurance_plan(
        (event,),
        repository_root=tmp_path,
    ).trust_assurance_payload
    contracts = cast(list[dict[str, object]], trust["semantic_contracts"])

    assert "contract:security-assurance-evidence" in {
        contract["contract_id"] for contract in contracts
    }
    assert all(
        contract["authority_boundary"] == "REPORT_ONLY" for contract in contracts
    )


def test_continuous_plan_writes_canonical_trace_records_without_manual_injection(
    tmp_path: Path,
) -> None:
    event = _event(
        AuditTriggerType.DECISION_AUDIT,
        event_id="decision-audit",
        entity_id="decision:HOTUSDT:cycle-1",
    )
    plan = build_continuous_assurance_plan((event,), repository_root=tmp_path)

    _ = plan.trust_assurance_payload
    journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))

    assert {record.trace_kind for record in journal.records()} == {
        ConsequentialTraceKind.DECISION,
        ConsequentialTraceKind.POLICY_EVALUATION,
    }


def test_tiaf_lite_records_reject_authority_or_weak_contracts() -> None:
    with pytest.raises(ValueError, match="preserve abstention"):
        UncertaintyAssessmentRecord(
            assessment_id="uncertainty",
            level=UncertaintyLevel.LOW,
            reasons=("baseline",),
            evidence_refs=("evidence",),
            abstention_required=False,
        )
    with pytest.raises(ValueError, match="cannot widen audit authority"):
        SemanticContractRecord(
            contract_id="contract",
            subject="Decision",
            required_fields=("decision_id",),
            forbidden_fields=("secret",),
            authority_boundary="EXECUTION_ALLOWED",
        )


def test_eaacie_and_audit_trigger_instructions_exist_and_cross_link() -> None:
    eaacie_text = Path(EAACIE_INSTRUCTION_REF).read_text(encoding="utf-8")
    trigger_text = Path(AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF).read_text(
        encoding="utf-8"
    )
    trust_plane_text = Path(
        "docs/governance/framework_trust_assurance_governance_plane.md"
    ).read_text(encoding="utf-8")

    assert "AI4B-EAACIE-001" in eaacie_text
    assert "AI4B-AUDIT-TRIGGER-ENGINE-001" in trigger_text
    assert AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF in eaacie_text
    assert EAACIE_INSTRUCTION_REF in trigger_text
    assert "`instruction_refs`" in eaacie_text
    assert f"instruction_ref: {AUDIT_TRIGGER_ENGINE_INSTRUCTION_REF}" in trigger_text
    assert "`EVENT_DRIVEN`" in trigger_text
    assert "`RISK_DRIVEN`" in trigger_text
    assert "`SCHEDULED`" in trigger_text
    assert "`ANOMALY_DRIVEN`" in trigger_text
    assert "`LIFECYCLE_DRIVEN`" in trigger_text
    for entity in AuditObservedEntity:
        assert f"`{entity.value}`" in trigger_text
    assert "Evidence is required for audit conclusion." in eaacie_text
    assert "No promotion without OOS evidence." in eaacie_text
    assert "No execution eligibility without risk approval." in eaacie_text
    assert "AI4BINANCE_TIAF_LITE" in eaacie_text
    assert (
        "docs/governance/framework_trust_assurance_governance_plane.md" in eaacie_text
    )
    assert "Trust Plane instruction" in trigger_text
    assert "TrustAssuranceBundle" in trigger_text
    assert "TrustPlaneAssessment" in trigger_text
    assert "trust_assurance.framework: AI4BINANCE_TIAF_LITE" in trigger_text
    assert "AI4BINANCE_TRUST_ASSURANCE_GOVERNANCE_PLANE" in trust_plane_text
    assert "ISO/IEC 42001" in trust_plane_text
    assert "NIST AI RMF" in trust_plane_text
    assert "LIVE_ORDER_BLOCKED" in eaacie_text
    for domain in SecurityDomain:
        assert f"`{domain.value}`" in eaacie_text
        assert f"`{domain.value}`" in trigger_text
    for trigger_type in SecurityAuditTriggerType:
        assert f"`{trigger_type.value}`" in trigger_text
    for control_name in SECURITY_AUDIT_CONTROL_PROFILE.to_payload():
        assert f"{control_name}: true" in eaacie_text


def test_security_control_profile_is_small_default_on_and_report_only() -> None:
    payload = SECURITY_AUDIT_CONTROL_PROFILE.to_payload()

    assert payload == {
        "privacy": True,
        "access_control": True,
        "secrets_scan": True,
        "dependency_scan": True,
        "dlp_scan": True,
        "audit_integrity": True,
        "backup_health": True,
        "incident_detection": True,
    }


@pytest.mark.parametrize(
    ("trigger_type", "expected_domains"),
    [
        (
            SecurityAuditTriggerType.CODE_CHANGE,
            {
                SecurityDomain.APPSEC,
                SecurityDomain.SECRETS,
                SecurityDomain.DLP,
                SecurityDomain.AUDIT,
            },
        ),
        (
            SecurityAuditTriggerType.CONFIG_CHANGE,
            {
                SecurityDomain.ACCESS,
                SecurityDomain.SECRETS,
                SecurityDomain.APPSEC,
                SecurityDomain.DLP,
                SecurityDomain.AUDIT,
                SecurityDomain.RECOVERY,
            },
        ),
        (
            SecurityAuditTriggerType.DEPENDENCY_CHANGE,
            {
                SecurityDomain.APPSEC,
                SecurityDomain.VULNERABILITY,
                SecurityDomain.AUDIT,
            },
        ),
        (
            SecurityAuditTriggerType.CREDENTIAL_SECRET_EVENT,
            {
                SecurityDomain.ACCESS,
                SecurityDomain.SECRETS,
                SecurityDomain.DLP,
                SecurityDomain.AUDIT,
                SecurityDomain.RECOVERY,
            },
        ),
        (
            SecurityAuditTriggerType.GIT_CLOUD_EVENT,
            {
                SecurityDomain.PRIVACY,
                SecurityDomain.SECRETS,
                SecurityDomain.DLP,
                SecurityDomain.AUDIT,
            },
        ),
        (SecurityAuditTriggerType.SECURITY_INCIDENT, set(SecurityDomain)),
        (SecurityAuditTriggerType.SCHEDULED_DAILY_QUICK, set(SecurityDomain)),
        (SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP, set(SecurityDomain)),
    ],
)
def test_security_triggers_route_to_bounded_eaacie_domains(
    trigger_type: SecurityAuditTriggerType,
    expected_domains: set[SecurityDomain],
) -> None:
    engine = CentralAuditTriggerEngine()
    event = engine.security_event(
        trigger_type,
        observed_at=NOW,
        evidence_refs=("security-evidence",),
    )
    plan = engine.build_security_plan((event,))
    decision = plan.route_decisions[0]
    payload = plan.to_payload()["security_audit"]

    assert set(decision.security_domains) == expected_domains
    assert decision.security_trigger_type is trigger_type
    assert decision.review_required is True
    assert "HUMAN_REVIEW_REQUIRED" in decision.blockers
    assert "SECURITY_AUDIT_REPORT_ONLY" in decision.blockers
    assert "run:security-core-audit" in decision.action_refs
    assert isinstance(payload, dict)
    assert payload["enabled"] is True
    assert set(cast(list[str], payload["domains"])) == {
        domain.value for domain in expected_domains
    }
    assert payload["automatic_remediation"] is False
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_security_routing_rejects_partial_domains_and_nonsecurity_plan() -> None:
    event = security_audit_event(
        SecurityAuditTriggerType.SECURITY_INCIDENT,
        observed_at=NOW,
        evidence_refs=("incident",),
    )
    with pytest.raises(ValueError, match="do not match trigger policy"):
        replace(event, security_domains=(SecurityDomain.AUDIT,))
    with pytest.raises(ValueError, match="requires security trigger events"):
        CentralAuditTriggerEngine().build_security_plan(
            (_event(AuditTriggerType.CODE_CHANGE),)
        )


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: AuditStateComparison(field=""),
            "field is required",
        ),
        (
            lambda: AuditStateComparison(
                field="status",
                observed="READY",
                allowed_values=("READY", "READY"),
            ),
            "allowed values must be unique",
        ),
        (
            lambda: AuditStateComparison(
                field="status",
                observed="READY",
                allowed_values=(" ",),
            ),
            "allowed values cannot contain blanks",
        ),
    ],
)
def test_audit_state_comparison_validates_contract(
    build: Callable[[], AuditStateComparison],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda signal: replace(signal, signal_id=""), "signal id"),
        (lambda signal: replace(signal, entity_id=""), "entity id"),
        (
            lambda signal: replace(
                signal,
                observed_at=datetime(2026, 8, 9, 12, 0),
            ),
            "timezone-aware",
        ),
        (lambda signal: replace(signal, trigger_modes=()), "requires trigger modes"),
        (
            lambda signal: replace(
                signal,
                trigger_modes=(
                    AuditTriggerMode.EVENT_DRIVEN,
                    AuditTriggerMode.EVENT_DRIVEN,
                ),
            ),
            "modes must be unique",
        ),
        (
            lambda signal: replace(
                signal,
                comparisons=(
                    AuditStateComparison(field="status"),
                    AuditStateComparison(field="status"),
                ),
            ),
            "comparison fields must be unique",
        ),
        (lambda signal: replace(signal, evidence_refs=()), "requires evidence"),
        (
            lambda signal: replace(signal, evidence_refs=(" ",)),
            "evidence refs cannot contain blanks",
        ),
        (lambda signal: replace(signal, confidence=1.1), "confidence"),
        (lambda signal: replace(signal, risk_score=101), "risk score"),
        (lambda signal: replace(signal, recursion_depth=-1), "recursion depth"),
    ],
)
def test_central_audit_trigger_signal_validates_contract(
    mutate: Callable[[AuditTriggerSignal], AuditTriggerSignal],
    message: str,
) -> None:
    signal = _signal("contract", AuditObservedEntity.STATE)

    with pytest.raises(ValueError, match=message):
        mutate(signal)


def test_central_audit_trigger_signal_rejects_hidden_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize trading"):
        _signal(
            "bad-authority",
            AuditObservedEntity.OPERATION,
            execution_allowed=True,
        )


def test_change_and_parameter_triggers_expose_required_governance_actions() -> None:
    plan = build_continuous_assurance_plan(
        (
            _event(AuditTriggerType.CODE_CHANGE, event_id="code"),
            _event(
                AuditTriggerType.AUTO_LEARN_OUTCOME,
                event_id="learn",
                entity_id="lesson-candidate",
            ),
        )
    )
    code_route, learn_route = plan.route_decisions

    assert "OEK_GAP_ANALYSIS_REQUIRED" in code_route.blockers
    assert "run:repository-cleanup-audit" in code_route.action_refs
    assert "VALIDATION_EVIDENCE_REQUIRED" in learn_route.blockers
    assert "run:validate-research" in learn_route.action_refs


def test_auto_audit_cycle_event_builder_classifies_privacy_runtime_and_data() -> None:
    events = events_from_auto_audit_cycle(
        observed_at=NOW,
        system_status="READY",
        blockers=("privacy:KVKK_PUBLIC_PRIVACY_LEAK",),
        new_blockers=(
            "privacy:KVKK_PUBLIC_PRIVACY_LEAK",
            "runtime:RUNTIME_DEGRADED",
            "DATA_QUALITY_GATE_FAILED",
        ),
        resolved_blockers=(),
        privacy_leak_status="BLOCKED",
    )
    plan = build_continuous_assurance_plan(events)
    trigger_types = {decision.trigger_type for decision in plan.route_decisions}

    assert AuditTriggerType.PRIVACY_OR_LEAKAGE in trigger_types
    assert AuditTriggerType.PERFORMANCE_DRIFT in trigger_types
    assert AuditTriggerType.DATA_QUALITY in trigger_types


def test_route_decision_rejects_duplicate_scope_and_blank_action() -> None:
    with pytest.raises(ValueError, match="scope refs must be unique"):
        AuditRouteDecision(
            event_id="route",
            trigger_type=AuditTriggerType.MANUAL_AUDIT,
            hybrid_trigger_classes=(HybridTriggerClass.MANUAL,),
            storm_status=AuditStormStatus.ACCEPTED,
            domains=(AuditDomain.GAP_ANALYSIS,),
            workflow_patterns=(AuditWorkflowPattern.ROUTING,),
            scope_refs=("a", "a"),
            review_required=False,
            blockers=("LIVE_ORDER_BLOCKED",),
            action_refs=("route:manual",),
        )
    with pytest.raises(ValueError, match="action refs cannot contain blanks"):
        AuditRouteDecision(
            event_id="route",
            trigger_type=AuditTriggerType.MANUAL_AUDIT,
            hybrid_trigger_classes=(HybridTriggerClass.MANUAL,),
            storm_status=AuditStormStatus.ACCEPTED,
            domains=(AuditDomain.GAP_ANALYSIS,),
            workflow_patterns=(AuditWorkflowPattern.ROUTING,),
            scope_refs=("a",),
            review_required=False,
            blockers=("LIVE_ORDER_BLOCKED",),
            action_refs=(" ",),
        )


def test_route_decision_rejects_duplicate_hybrid_trigger_classes() -> None:
    with pytest.raises(ValueError, match="hybrid trigger classes must be unique"):
        AuditRouteDecision(
            event_id="route",
            trigger_type=AuditTriggerType.MANUAL_AUDIT,
            hybrid_trigger_classes=(
                HybridTriggerClass.MANUAL,
                HybridTriggerClass.MANUAL,
            ),
            storm_status=AuditStormStatus.ACCEPTED,
            domains=(AuditDomain.GAP_ANALYSIS,),
            workflow_patterns=(AuditWorkflowPattern.ROUTING,),
            scope_refs=("a",),
            review_required=False,
            blockers=("LIVE_ORDER_BLOCKED",),
            action_refs=("route:manual",),
        )


def _event(
    trigger_type: AuditTriggerType,
    *,
    event_id: str | None = None,
    entity_id: str = "AI4BINANCE",
    root_cause_key: str = "",
    observed_at: datetime = NOW,
    recursion_depth: int = 0,
) -> ContinuousAuditEvent:
    return ContinuousAuditEvent(
        event_id=event_id or trigger_type.value.lower(),
        trigger_type=trigger_type,
        entity_type="SYSTEM",
        entity_id=entity_id,
        observed_at=observed_at,
        evidence_refs=("test",),
        root_cause_key=root_cause_key,
        recursion_depth=recursion_depth,
    )


def _signal(
    signal_id: str,
    entity_kind: AuditObservedEntity,
    trigger_modes: tuple[AuditTriggerMode, ...] = (AuditTriggerMode.EVENT_DRIVEN,),
    *,
    comparisons: tuple[AuditStateComparison, ...] | None = None,
    risk_score: int = 0,
    execution_allowed: bool = False,
) -> AuditTriggerSignal:
    return AuditTriggerSignal(
        signal_id=signal_id,
        entity_kind=entity_kind,
        entity_id=f"{entity_kind.value}:{signal_id}",
        observed_at=NOW,
        trigger_modes=trigger_modes,
        comparisons=(
            comparisons
            if comparisons is not None
            else (
                AuditStateComparison(
                    field="status",
                    expected="EXPECTED",
                    observed="DEVIATED",
                ),
            )
        ),
        evidence_refs=(f"evidence:{signal_id}",),
        severity=AuditTriggerSeverity.P2,
        confidence=1.0,
        risk_score=risk_score,
        execution_allowed=execution_allowed,
    )

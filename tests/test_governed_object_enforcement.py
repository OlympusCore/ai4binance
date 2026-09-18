"""Tests for the universal governed-object enforcement fabric."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.governance.enforcement.adapters import (
    envelope_from_execution_authority_profile,
    envelope_from_governed_knowledge,
    envelope_from_policy_document,
    envelope_from_repository_artifact,
    envelope_from_tool_policy_document,
)
from ai4binance.governance.enforcement.contracts import (
    AttestationResult,
    AuditReceipt,
    BlockerSnapshot,
    EnforcementDecision,
    EnforcementGate,
    EnforcementOutcome,
    EnforcementRequest,
    GovernedObjectEnvelope,
    VerificationAttestation,
    VerifiedApprovalSet,
)
from ai4binance.governance.enforcement.engine import DeterministicEnforcementEngine
from ai4binance.governance.enforcement.inventory import (
    EnforcementCoverageState,
    EnforcementInventory,
    EnforcementInventoryEntry,
    RequirementTraceStatus,
    bypassable_consequential_entrypoint_ids,
    consequential_entrypoint_ids,
    inventory_entrypoint_ids,
    inventory_scope_families,
    load_enforcement_inventory,
    required_scope_families,
    routed_or_explicitly_blocked_entrypoint_ids,
    uncovered_consequential_entrypoint_ids,
)
from ai4binance.governance.enforcement.registry import (
    expected_governed_object_types,
    load_enforcement_profile_registry,
)
from ai4binance.governance.execution_authority import VIRTUAL_MARKET_AUTO_PROFILE
from ai4binance.governance.policy_as_code import (
    PolicyAsCodeDocument,
    PolicyAsCodeEngine,
    PolicyAsCodeRule,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
)
from ai4binance.governance.repository_validator import (
    GovernedKnowledgeObject,
    KnowledgeAuthorityEffect,
    KnowledgeAuthorityLevel,
    KnowledgeClassification,
    KnowledgeContentRole,
    KnowledgeLifecycleStatus,
    KnowledgeObjectType,
    RepositoryArtifact,
    RepositoryArtifactClass,
    RepositoryArtifactLifecycle,
    RepositoryArtifactType,
)
from ai4binance.governance.tool_policy import ToolPolicyDocument

pytestmark = [
    pytest.mark.contract,
    pytest.mark.governance,
]


def _knowledge_object(
    *,
    knowledge_type: KnowledgeObjectType = KnowledgeObjectType.POLICY,
    lifecycle_status: KnowledgeLifecycleStatus = KnowledgeLifecycleStatus.ACTIVE,
) -> GovernedKnowledgeObject:
    return GovernedKnowledgeObject(
        knowledge_id="AI4B-GOV-STD-999",
        knowledge_type=knowledge_type,
        title="Governed Policy",
        version="1.0.0",
        lifecycle_status=lifecycle_status,
        authority_level=KnowledgeAuthorityLevel.NORMATIVE,
        authority_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        authority_effect=KnowledgeAuthorityEffect.NORMATIVE_CONSTRAINT,
        content_role=KnowledgeContentRole.AUTHORITATIVE,
        owner="Enterprise Governance",
        source_of_truth=True,
        machine_enforceable=True,
        audit_required=True,
        classification=KnowledgeClassification.INTERNAL,
        path="docs/governance/policy_example.md",
        canonical_path="docs/governance/policy_example.md",
        authority_scope="enterprise_governance",
        source_of_truth_scope="canonical",
    )


def _repository_artifact() -> RepositoryArtifact:
    return RepositoryArtifact(
        artifact_id="artifact-1",
        artifact_type=RepositoryArtifactType.SCHEMA,
        artifact_class=RepositoryArtifactClass.GOVERNANCE,
        domain="Governance",
        owner="Enterprise Governance",
        canonical_path="schemas/governance/repository_artifact.schema.json",
        filename="repository_artifact.schema.json",
        schema_version="1.0.0",
        lifecycle_status=RepositoryArtifactLifecycle.ACTIVE,
        generated=False,
        immutable=True,
        sensitive=False,
        git_tracked=True,
        checksum="a" * 64,
        path="schemas/governance/repository_artifact.schema.json",
        mime_type="application/json",
        size=1024,
        modified_time="2026-08-31T12:00:00+00:00",
        authority_layer="L3_CANONICAL_CONTRACTS_SCHEMAS",
        authority_effect=KnowledgeAuthorityEffect.NORMATIVE_CONSTRAINT,
        authority_scope="repository_artifact_schema",
        observed_expected_layer="L3_CANONICAL_CONTRACTS_SCHEMAS",
        authority_basis=("canonical_path:verified",),
        action="NO_CHANGE",
        result="COMPLIANT",
        source_of_truth=True,
        machine_enforceable=True,
        audit_required=True,
        classification=KnowledgeClassification.INTERNAL,
    )


def _attestation(
    gate: EnforcementGate,
    subject_hash: str,
    *,
    result: AttestationResult = AttestationResult.VERIFIED,
    evaluated_at: str = "2026-08-31T09:00:00Z",
    valid_until: str = "2099-01-01T00:00:00Z",
) -> VerificationAttestation:
    return VerificationAttestation(
        attestation_id=f"{gate.value.lower()}-attestation",
        gate=gate,
        subject_hash=subject_hash,
        provider_id="test-provider",
        provider_version="1.0.0",
        policy_version="1.0.0",
        evaluated_at=evaluated_at,
        valid_until=valid_until,
        evidence_refs=(f"{gate.value.lower()}-proof",),
        evidence_hash="b" * 64,
        result=result,
        reason_codes=(f"{gate.value}_VERIFIED",),
    )


def _gate_attestations(
    subject_hash: str,
    *gates: EnforcementGate,
) -> dict[EnforcementGate, VerificationAttestation]:
    return {gate: _attestation(gate, subject_hash) for gate in gates}


def _blocker_snapshot(subject_id: str, *active_blockers: str) -> BlockerSnapshot:
    return BlockerSnapshot(
        blocker_snapshot_id="blocker-snapshot-1",
        blocker_registry_hash="c" * 64,
        active_blockers=active_blockers,
        resolved_blockers=(),
        evaluated_at="2026-08-31T09:00:00Z",
        subject_id=subject_id,
    )


def _audit_receipt(subject_hash: str) -> AuditReceipt:
    return AuditReceipt(
        receipt_id="audit-receipt-1",
        subject_hash=subject_hash,
        audit_log_ref="runtime/artifacts/audit/test.jsonl",
        commit_hash="d" * 64,
        recorded_at="2026-08-31T09:00:00Z",
    )


def _approval_set(
    engine: DeterministicEnforcementEngine,
    envelope: GovernedObjectEnvelope,
    request: EnforcementRequest,
    *,
    change_class: str,
) -> VerifiedApprovalSet:
    profile = engine.registry.profile_for_object_type(envelope.object_type)
    assert profile is not None
    return VerifiedApprovalSet(
        approval_set_id="approval-set-1",
        subject_hash=envelope.object_hash,
        scope_hash=engine._scope_hash(envelope, request, profile),
        change_class=change_class,
        required_roles=("GovernanceOwner",),
        satisfied_roles=("GovernanceOwner",),
        principal_ids=("principal-1",),
        approval_ids=("approval-1",),
        evidence_hash="e" * 64,
        verified_at="2026-08-31T09:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        verification_policy_hash="f" * 64,
    )


def test_enforcement_profile_registry_covers_all_governed_object_types() -> None:
    registry = load_enforcement_profile_registry()

    registry.assert_full_coverage(expected_governed_object_types())
    assert registry.profile_for_object_type("REPOSITORY_ARTIFACT") is not None
    assert (
        registry.profile_for_object_type(KnowledgeObjectType.RISK_MODEL.value)
        is not None
    )


def test_governed_object_enforcement_schema_contains_canonical_contracts() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "governance"
        / "governed_object_enforcement.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["required"] == [
        "governed_object_envelope",
        "enforcement_request",
        "enforcement_profile",
        "enforcement_decision",
    ]
    assert "GovernedObjectEnvelope" in schema["$defs"]
    assert "EnforcementRequest" in schema["$defs"]
    assert "EnforcementProfile" in schema["$defs"]
    assert "EnforcementDecision" in schema["$defs"]


def test_enforcement_inventory_tracks_current_enforcers_and_bypass_surfaces() -> None:
    inventory = load_enforcement_inventory()
    profile_registry = load_enforcement_profile_registry()

    inventory.assert_profile_registry_alignment(profile_registry)
    inventory.assert_required_scope_families_covered()
    inventory.assert_non_consequential_examples_excluded()
    repository_entry = inventory.entry_for_entrypoint("repository_artifact_update")
    tool_entry = inventory.entry_for_entrypoint("tool_permission_grant")
    execution_entry = inventory.entry_for_entrypoint("execution_profile_evaluate")
    routed_strategy = inventory.entry_for_entrypoint(
        "strategy_definition_profile_contract"
    )
    pending_strategy = inventory.entry_for_entrypoint("tuning_strategy_promotion_board")
    governance_change_entry = inventory.entry_for_entrypoint(
        "governance_control_plane_update"
    )
    blocked_execution_intent = inventory.entry_for_entrypoint(
        "live_order_execution_intent"
    )
    blocked_approval_state = inventory.entry_for_entrypoint(
        "approval_record_runtime_mutation"
    )
    snapshot_validation = inventory.entry_for_entrypoint(
        "market_snapshot_wire_validation"
    )
    memory_intake = inventory.entry_for_entrypoint("governed_memory_candidate_intake")

    assert repository_entry is not None
    assert repository_entry.current_enforcer == "repository_validator"
    assert repository_entry.coverage_state is EnforcementCoverageState.ROUTED
    assert repository_entry.bypass_possible is False
    assert tool_entry is not None
    assert tool_entry.current_enforcer.endswith("ToolGateway")
    assert tool_entry.coverage_state is EnforcementCoverageState.ROUTED
    assert tool_entry.bypass_possible is False
    assert execution_entry is not None
    assert execution_entry.policy_source.endswith("execution_authority.py")
    assert execution_entry.coverage_state is EnforcementCoverageState.ROUTED
    assert execution_entry.bypass_possible is False
    assert routed_strategy is not None
    assert routed_strategy.coverage_state is EnforcementCoverageState.ROUTED
    assert pending_strategy is not None
    assert pending_strategy.coverage_state is EnforcementCoverageState.BLOCKED
    assert governance_change_entry is not None
    assert governance_change_entry.scope_family == "governance_changes"
    assert governance_change_entry.coverage_state is EnforcementCoverageState.BLOCKED
    assert blocked_execution_intent is not None
    assert blocked_execution_intent.coverage_state is EnforcementCoverageState.BLOCKED
    assert blocked_execution_intent.bypass_possible is False
    assert blocked_approval_state is not None
    assert blocked_approval_state.coverage_state is EnforcementCoverageState.BLOCKED
    assert blocked_approval_state.bypass_possible is False
    assert snapshot_validation is not None
    assert (
        snapshot_validation.coverage_state
        is EnforcementCoverageState.PURE_DETERMINISTIC
    )
    assert snapshot_validation.consequential is False
    assert memory_intake is not None
    assert memory_intake.coverage_state is EnforcementCoverageState.PURE_DETERMINISTIC
    assert memory_intake.consequential is False


def test_enforcement_inventory_loads_typed_fail_closed_requirement_traceability() -> (
    None
):
    inventory = load_enforcement_inventory()
    traceability = inventory.requirement_traceability

    assert traceability is not None
    assert len(traceability.entries) == 20
    assert traceability.converged_count == 17
    assert traceability.invariants.execution_allowed is False
    assert traceability.invariants.promotion_status == "RESEARCH_ONLY"
    assert traceability.invariants.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    rq_013 = next(
        entry for entry in traceability.entries if entry.requirement_id == "RQ-013"
    )
    rq_014 = next(
        entry for entry in traceability.entries if entry.requirement_id == "RQ-014"
    )
    rq_015 = next(
        entry for entry in traceability.entries if entry.requirement_id == "RQ-015"
    )
    rq_016 = next(
        entry for entry in traceability.entries if entry.requirement_id == "RQ-016"
    )
    assert rq_013.trace_status is RequirementTraceStatus.AUDIT_VERIFIED
    assert rq_013.is_converged is False
    assert rq_013.blocker_codes == (
        "RQ-013:CONVERGENCE_BLOCKED_BY_OOS_PROMOTION_EVIDENCE",
    )
    assert rq_014.trace_status is RequirementTraceStatus.AUDIT_VERIFIED
    assert rq_014.is_converged is True
    assert rq_014.blocker_codes == ()
    assert rq_015.trace_status is RequirementTraceStatus.AUDIT_VERIFIED
    assert rq_015.is_converged is False
    assert rq_015.blocker_codes == (
        "RQ-015:CONVERGENCE_BLOCKED_BY_EXTERNAL_SECURITY_EVIDENCE",
    )
    assert rq_016.trace_status is RequirementTraceStatus.AUDIT_VERIFIED
    assert rq_016.is_converged is False
    assert rq_016.blocker_codes == (
        "RQ-016:CONVERGENCE_BLOCKED_BY_COMPATIBILITY_EVIDENCE",
    )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(traceability.invariants, execution_allowed=True)


def test_enforcement_inventory_distinguishes_profile_vs_entrypoint_gaps() -> None:
    inventory = load_enforcement_inventory()

    strategy_entries = inventory.entries_for_object_type_action(
        "STRATEGY_DEFINITION",
        "PROMOTE",
    )
    workflow_entries = inventory.entries_for_object_type_action("WORKFLOW", "ACTIVATE")
    governance_entries = inventory.entries_for_scope_family("governance_changes")
    routed = inventory.entries_for_coverage_state(EnforcementCoverageState.ROUTED)
    adapter_required = inventory.entries_for_coverage_state(
        EnforcementCoverageState.ADAPTER_REQUIRED
    )
    report_only = inventory.entries_for_coverage_state(
        EnforcementCoverageState.REPORT_ONLY
    )
    blocked = inventory.entries_for_coverage_state(EnforcementCoverageState.BLOCKED)

    assert len(strategy_entries) == 2
    assert {entry.entrypoint_id for entry in strategy_entries} == {
        "strategy_definition_profile_contract",
        "tuning_strategy_promotion_board",
    }
    assert len(workflow_entries) == 3
    assert {entry.entrypoint_id for entry in workflow_entries} == {
        "workflow_job_admission",
        "development_run_card_completion",
        "graph_workflow_manifest_admission",
    }
    assert {entry.entrypoint_id for entry in governance_entries} == {
        "policy_document_update",
        "governance_control_plane_update",
    }
    assert adapter_required == ()
    assert report_only == ()
    assert "provider_model_selection_decision" in {
        entry.entrypoint_id for entry in routed
    }
    assert "strategy_definition_profile_contract" in {
        entry.entrypoint_id for entry in routed
    }
    assert {entry.entrypoint_id for entry in blocked} == {
        "tuning_strategy_promotion_board",
        "governed_parameter_activation",
        "governed_lesson_activation",
        "development_run_card_completion",
        "strategy_registry_mutation_write",
        "model_adaptation_candidate_review",
        "graph_workflow_manifest_admission",
        "governance_control_plane_update",
        "live_order_execution_intent",
        "approval_record_runtime_mutation",
    }
    with pytest.raises(ValueError, match="multiple entrypoints"):
        inventory.entry_for("STRATEGY_DEFINITION", "PROMOTE")


def test_enforcement_inventory_requires_unique_entrypoint_ids() -> None:
    entry = EnforcementInventoryEntry(
        entrypoint_id="duplicate-entrypoint",
        scope_family="governance_changes",
        object_type="POLICY",
        action="UPDATE",
        integration_surface="policy_as_code",
        current_enforcer="DeterministicEnforcementEngine+PolicyAsCodeEngine",
        coverage_state=EnforcementCoverageState.ROUTED,
        status_rationale="This surface is already routed.",
        authority_source="docs/standards/standard_governed_object_enforcement.md",
        policy_source="src/ai4binance/governance/policy_as_code.py",
        blocker_source="config/governance/blocker_registry.yaml",
        tests=("tests/test_governed_object_enforcement.py",),
        bypass_possible=True,
        consequential=True,
    )

    with pytest.raises(ValueError, match="entrypoint IDs must be unique"):
        EnforcementInventory(version="1.1.0", entries=(entry, entry))


def test_enforcement_inventory_exports_stable_entrypoint_ids() -> None:
    inventory = load_enforcement_inventory()

    assert inventory_entrypoint_ids(inventory) == (
        "repository_artifact_update",
        "policy_document_update",
        "tool_permission_grant",
        "execution_profile_evaluate",
        "strategy_definition_profile_contract",
        "tuning_strategy_promotion_board",
        "governed_parameter_activation",
        "workflow_job_admission",
        "governed_lesson_activation",
        "development_run_card_completion",
        "strategy_registry_mutation_write",
        "model_adaptation_candidate_review",
        "graph_workflow_manifest_admission",
        "governance_control_plane_update",
        "provider_model_selection_decision",
        "live_order_execution_intent",
        "approval_record_runtime_mutation",
        "market_snapshot_wire_validation",
        "governed_memory_candidate_intake",
    )
    assert inventory_scope_families(inventory) == (
        "repository_artifact_mutation",
        "governance_changes",
        "provider_tool_side_effects",
        "execution_boundary_evaluation",
        "strategy_promotion",
        "parameter_promotion",
        "unattended_jobs",
        "lesson_promotion",
        "workflow_admission",
        "registry_mutations",
        "model_adaptation",
        "execution_intents",
        "approval_state_changes",
        "snapshot_integrity",
        "memory_authority",
    )


def test_enforcement_inventory_reports_uncovered_consequential_gap_set() -> None:
    inventory = load_enforcement_inventory()

    assert consequential_entrypoint_ids(inventory) == tuple(
        entry.entrypoint_id for entry in inventory.entries if entry.consequential
    )
    assert "market_snapshot_wire_validation" not in consequential_entrypoint_ids(
        inventory
    )
    assert "governed_memory_candidate_intake" not in consequential_entrypoint_ids(
        inventory
    )
    assert routed_or_explicitly_blocked_entrypoint_ids(inventory) == (
        "repository_artifact_update",
        "policy_document_update",
        "tool_permission_grant",
        "execution_profile_evaluate",
        "strategy_definition_profile_contract",
        "tuning_strategy_promotion_board",
        "governed_parameter_activation",
        "workflow_job_admission",
        "governed_lesson_activation",
        "development_run_card_completion",
        "strategy_registry_mutation_write",
        "model_adaptation_candidate_review",
        "graph_workflow_manifest_admission",
        "governance_control_plane_update",
        "provider_model_selection_decision",
        "live_order_execution_intent",
        "approval_record_runtime_mutation",
    )
    assert uncovered_consequential_entrypoint_ids(inventory) == ()
    assert "calculate_rsi" not in consequential_entrypoint_ids(inventory)
    assert "calculate_atr" not in consequential_entrypoint_ids(inventory)
    assert "score_evidence" not in consequential_entrypoint_ids(inventory)
    assert "risk_math" not in consequential_entrypoint_ids(inventory)
    assert required_scope_families() == (
        "registry_mutations",
        "strategy_promotion",
        "parameter_promotion",
        "model_adaptation",
        "workflow_admission",
        "lesson_promotion",
        "unattended_jobs",
        "provider_tool_side_effects",
        "execution_intents",
        "governance_changes",
        "approval_state_changes",
    )
    inventory.assert_exit_invariant()


def test_enforcement_engine_denies_unknown_profile_fail_closed() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = GovernedObjectEnvelope(
        object_id="x-1",
        object_type="UNKNOWN_OBJECT",
        version="1.0.0",
        lifecycle_state="ACTIVE",
        owner="Enterprise Governance",
        authority_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="enterprise_governance",
        source_of_truth=True,
        canonical_ref="docs/example.md",
        schema_ref="schemas/example.json",
        content_hash="a" * 64,
    )
    request = EnforcementRequest(
        request_id="req-1",
        actor="codex",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("enterprise_governance",),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert "UNMANAGED_GOVERNED_OBJECT" in decision.blockers
    assert "UNKNOWN_ENFORCEMENT_PROFILE" in decision.reason_codes


def test_enforcement_engine_requires_evidence_and_approval_for_policy_change() -> None:
    registry = load_enforcement_profile_registry()
    policy_doc = PolicyAsCodeDocument(
        policy_id="policy-1",
        version="1.0.0",
        rules=(
            PolicyAsCodeRule(
                rule_id="policy-update-needs-approval",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                resource_types=("POLICY",),
                actions=("UPDATE",),
                conditions=(
                    PolicyCondition(
                        key="change_scope",
                        operator=PolicyConditionOperator.EQUALS,
                        values=("governed",),
                    ),
                ),
                reason_code="POLICY_UPDATE_APPROVAL_REQUIRED",
            ),
        ),
    )
    engine = DeterministicEnforcementEngine(
        registry=registry,
        policy_engine=PolicyAsCodeEngine(policy_doc),
    )
    envelope = envelope_from_governed_knowledge(_knowledge_object())
    request = EnforcementRequest(
        request_id="req-2",
        actor="codex",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("enterprise_governance",),
        evidence_refs=("quality_gate_evidence",),
        policy_facts={"change_scope": "governed"},
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.EVIDENCE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.REQUIRE_APPROVAL
    assert "POLICY_UPDATE_APPROVAL_REQUIRED" in decision.reason_codes
    assert "1.0.0" in decision.policy_versions


def test_enforcement_engine_denies_missing_required_evidence() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_governed_knowledge(
        _knowledge_object(knowledge_type=KnowledgeObjectType.RISK_MODEL)
    )
    request = EnforcementRequest(
        request_id="req-3",
        actor="risk-bot",
        action="CHANGE_RISK",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("risk_governance",),
        requested_transition="ACTIVE",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert "REQUIRED_EVIDENCE_MISSING" in decision.reason_codes
    assert "EVIDENCE_MISSING:risk_validation" in decision.blockers


def test_enforcement_engine_denies_active_blockers_before_consequence() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = GovernedObjectEnvelope(
        object_id="strategy-1",
        object_type=KnowledgeObjectType.STRATEGY_DEFINITION.value,
        version="1.0.0",
        lifecycle_state="OOS_VALIDATED",
        owner="Enterprise Governance",
        authority_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        authority_effect="NORMATIVE_CONSTRAINT",
        authority_scope="strategy_governance",
        source_of_truth=True,
        canonical_ref="docs/governance/strategy_example.md",
        schema_ref="schemas/governance/strategy_example.schema.json",
        content_hash="a" * 64,
        policy_refs=("docs/standards/standard_governed_object_enforcement.md",),
    )
    request = EnforcementRequest(
        request_id="req-4",
        actor="strategy-bot",
        action="PROMOTE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("strategy_governance",),
        evidence_refs=("oos_validation", "walk_forward_validation", "paper_readiness"),
        requested_transition="PAPER_APPROVED",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.EVIDENCE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(
            envelope.object_id, "GOV.AUTHORITY_CONFLICT"
        ),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert decision.blockers == ("GOV.AUTHORITY_CONFLICT",)
    assert "ACTIVE_BLOCKERS_PRESENT" in decision.reason_codes


def test_enforcement_engine_denies_invalid_lifecycle_transition() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_governed_knowledge(
        _knowledge_object(
            knowledge_type=KnowledgeObjectType.PARAMETER_SET,
            lifecycle_status=KnowledgeLifecycleStatus.ACTIVE,
        )
    )
    request = EnforcementRequest(
        request_id="req-5",
        actor="parameter-bot",
        action="CHANGE_PARAMETER",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("parameter_governance",),
        evidence_refs=("parameter_validation", "quality_gate_evidence"),
        requested_transition="LIVE_APPROVED",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.EVIDENCE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert "LIFECYCLE_TRANSITION_FORBIDDEN" in decision.reason_codes


def test_enforcement_adapters_preserve_existing_governed_metadata() -> None:
    knowledge = envelope_from_governed_knowledge(_knowledge_object())
    artifact = envelope_from_repository_artifact(_repository_artifact())
    policy = envelope_from_policy_document(
        PolicyAsCodeDocument(policy_id="policy-2", version="1.0.0")
    )
    tool = envelope_from_tool_policy_document(
        ToolPolicyDocument(policy_id="tool-policy-1", version="1.0.0")
    )
    execution = envelope_from_execution_authority_profile(VIRTUAL_MARKET_AUTO_PROFILE)

    assert knowledge.object_type == "POLICY"
    assert knowledge.authority_scope == "enterprise_governance"
    assert knowledge.classification == "INTERNAL"
    assert artifact.object_type == "REPOSITORY_ARTIFACT"
    assert artifact.schema_ref == "schemas/governance/repository_artifact.schema.json"
    assert artifact.source_of_truth is True
    assert policy.content_hash is not None
    assert policy.canonical_ref == "policy_as_code:policy-2"
    assert tool.object_type == "TOOL_CONTRACT"
    assert tool.permission_profile_ref == "tool-policy-1"
    assert execution.object_type == "EXECUTION_PROFILE"
    assert execution.permission_profile_ref == "VIRTUAL_AUTONOMOUS_SIMULATION_V1"


def test_enforcement_replay_fingerprint_is_deterministic() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_repository_artifact(_repository_artifact())
    request = EnforcementRequest(
        request_id="req-6",
        actor="repo-bot",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("repository_governance",),
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    first = engine.evaluate(envelope, request)
    second = engine.evaluate(envelope, request)

    assert isinstance(first, EnforcementDecision)
    assert first.replay_fingerprint == second.replay_fingerprint
    assert first.outcome is second.outcome
    assert len(first.scope_hash) == 64


def test_enforcement_engine_requires_approval_for_tool_permission_grant() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(
        registry=registry,
        policy_engine=PolicyAsCodeEngine(
            PolicyAsCodeDocument(
                policy_id="tool-policy",
                version="1.0.0",
                rules=(
                    PolicyAsCodeRule(
                        rule_id="tool-grant-allowed",
                        effect=PolicyEffect.ALLOW,
                        resource_types=("TOOL_CONTRACT",),
                        actions=("GRANT_PERMISSION",),
                    ),
                ),
            )
        ),
    )
    envelope = envelope_from_tool_policy_document(
        ToolPolicyDocument(policy_id="tool-policy-2", version="1.0.0")
    )
    request = EnforcementRequest(
        request_id="req-7",
        actor="tool-admin",
        action="GRANT_PERMISSION",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("tool_governance",),
        evidence_refs=("tool_policy_validation", "quality_gate_evidence"),
        requested_transition="ACTIVE",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.EVIDENCE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)
    approved_request = EnforcementRequest(
        request_id="req-8",
        actor="tool-admin",
        action="GRANT_PERMISSION",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("tool_governance",),
        evidence_refs=("tool_policy_validation", "quality_gate_evidence"),
        requested_transition="ACTIVE",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.EVIDENCE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )
    approved_request = replace(
        approved_request,
        verified_approval_set=_approval_set(
            engine,
            envelope,
            approved_request,
            change_class="CONSEQUENTIAL_PROMOTION",
        ),
    )
    approved = engine.evaluate(
        envelope,
        approved_request,
    )

    assert decision.outcome is EnforcementOutcome.REQUIRE_APPROVAL
    assert "HUMAN_APPROVAL_REQUIRED" in decision.reason_codes
    assert approved.outcome is EnforcementOutcome.ALLOW


def test_enforcement_engine_evaluates_execution_profile_via_universal_contract() -> (
    None
):
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(
        registry=registry,
        policy_engine=PolicyAsCodeEngine(
            PolicyAsCodeDocument(
                policy_id="execution-policy",
                version="1.0.0",
                rules=(
                    PolicyAsCodeRule(
                        rule_id="execution-evaluate-allowed",
                        effect=PolicyEffect.ALLOW,
                        resource_types=("EXECUTION_PROFILE",),
                        actions=("EXECUTE",),
                    ),
                ),
            )
        ),
    )
    envelope = envelope_from_execution_authority_profile(VIRTUAL_MARKET_AUTO_PROFILE)
    request = EnforcementRequest(
        request_id="req-9",
        actor="execution-admin",
        action="EXECUTE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("execution_governance",),
        evidence_refs=("execution_readiness", "quality_gate_evidence"),
        requested_transition="ACTIVE",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.EVIDENCE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )
    request = replace(
        request,
        verified_approval_set=_approval_set(
            engine,
            envelope,
            request,
            change_class="CONSEQUENTIAL_PROMOTION",
        ),
    )

    decision = engine.evaluate(
        envelope,
        request,
        execution_profile=VIRTUAL_MARKET_AUTO_PROFILE,
    )

    assert decision.outcome is EnforcementOutcome.ALLOW
    assert decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_enforcement_inventory_reports_bypassable_routed_paths() -> None:
    inventory = load_enforcement_inventory()

    assert bypassable_consequential_entrypoint_ids(inventory) == ()


def test_enforcement_engine_denies_stale_identity_attestation() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_repository_artifact(_repository_artifact())
    request = EnforcementRequest(
        request_id="req-stale",
        actor="repo-bot",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("repository_governance",),
        gate_attestations={
            EnforcementGate.IDENTITY: _attestation(
                EnforcementGate.IDENTITY,
                envelope.object_hash,
                evaluated_at="2026-08-29T00:00:00Z",
                valid_until="2026-08-30T00:00:00Z",
            )
        },
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert "IDENTITY_ATTESTATION_STALE" in decision.reason_codes


def test_enforcement_engine_denies_missing_blocker_snapshot() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_repository_artifact(_repository_artifact())
    request = EnforcementRequest(
        request_id="req-blocker",
        actor="repo-bot",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("repository_governance",),
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.LINEAGE,
        ),
        audit_receipt=_audit_receipt(envelope.object_hash),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert "BLOCKER_SNAPSHOT_MISSING" in decision.reason_codes


def test_enforcement_engine_denies_missing_audit_receipt() -> None:
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_repository_artifact(_repository_artifact())
    request = EnforcementRequest(
        request_id="req-audit",
        actor="repo-bot",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("repository_governance",),
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.IDENTITY,
            EnforcementGate.SCHEMA,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
            EnforcementGate.LINEAGE,
        ),
        blocker_snapshot=_blocker_snapshot(envelope.object_id),
    )

    decision = engine.evaluate(envelope, request)

    assert decision.outcome is EnforcementOutcome.DENY
    assert "AUDIT_RECEIPT_MISSING" in decision.reason_codes


def test_enforcement_internal_guards_reject_mismatched_evidence() -> None:
    """Attestations, approvals, and receipts remain exact-subject bound."""
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_tool_policy_document(
        ToolPolicyDocument(policy_id="tool-policy-guard", version="1.0.0")
    )
    request = EnforcementRequest(
        request_id="req-internal-guard",
        actor="tool-admin",
        action="GRANT_PERMISSION",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("tool_governance",),
    )
    profile = registry.profile_for_object_type(envelope.object_type)
    assert profile is not None
    approval = _approval_set(
        engine,
        envelope,
        request,
        change_class=profile.human_approval_class,
    )

    subject_error = engine._attestation_error(
        replace(
            _attestation(EnforcementGate.IDENTITY, envelope.object_hash),
            subject_hash="a" * 64,
        ),
        envelope,
    )
    status_error = engine._attestation_error(
        replace(
            _attestation(EnforcementGate.IDENTITY, envelope.object_hash),
            result=AttestationResult.DENIED,
        ),
        envelope,
    )
    assert subject_error == "IDENTITY_ATTESTATION_SUBJECT_MISMATCH"
    assert status_error == "IDENTITY_ATTESTATION_NOT_VERIFIED"

    subject_result = engine._validate_approval_set(
        replace(approval, subject_hash="a" * 64), envelope, request, profile
    )
    scope_result = engine._validate_approval_set(
        replace(approval, scope_hash="a" * 64), envelope, request, profile
    )
    change_class_result = engine._validate_approval_set(
        replace(approval, change_class="OTHER"), envelope, request, profile
    )
    stale_approval = replace(
        approval,
        verified_at="2020-01-01T00:00:00Z",
        expires_at="2021-01-01T00:00:00Z",
    )
    stale_result = engine._validate_approval_set(
        stale_approval, envelope, request, profile
    )
    assert subject_result is not None
    assert scope_result is not None
    assert change_class_result is not None
    assert stale_result is not None
    assert subject_result.reason_codes == ("APPROVAL_SUBJECT_MISMATCH",)
    assert scope_result.reason_codes == ("APPROVAL_SCOPE_MISMATCH",)
    assert change_class_result.reason_codes == ("APPROVAL_CHANGE_CLASS_MISMATCH",)
    assert stale_result.reason_codes == ("APPROVAL_STALE",)

    audit_result = engine._validate_audit_receipt(
        replace(_audit_receipt(envelope.object_hash), subject_hash="a" * 64),
        envelope,
    )
    assert audit_result.reason_codes == ("AUDIT_RECEIPT_SUBJECT_MISMATCH",)


def test_enforcement_gate_branches_remain_fail_closed() -> None:
    """Direct gate checks preserve every guarded denial and read-only path."""
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_tool_policy_document(
        ToolPolicyDocument(policy_id="tool-policy-branches", version="1.0.0")
    )
    profile = registry.profile_for_object_type(envelope.object_type)
    assert profile is not None
    base_request = EnforcementRequest(
        request_id="req-gate-branches",
        actor="tool-admin",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        requested_transition="FORBIDDEN",
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.LIFECYCLE,
        ),
    )

    lifecycle = engine._evaluate_gate(
        EnforcementGate.LIFECYCLE,
        envelope,
        base_request,
        profile,
        execution_profile=None,
    )
    assert lifecycle.reason_codes == ("LIFECYCLE_TRANSITION_FORBIDDEN",)

    policy_unavailable = engine._evaluate_gate(
        EnforcementGate.POLICY,
        envelope,
        base_request,
        profile,
        execution_profile=None,
    )
    assert policy_unavailable.reason_codes == ("POLICY_ENGINE_UNAVAILABLE",)

    denied_policy_engine = DeterministicEnforcementEngine(
        registry=registry,
        policy_engine=PolicyAsCodeEngine(
            PolicyAsCodeDocument(
                policy_id="deny-tool-update",
                version="1.0.0",
                rules=(
                    PolicyAsCodeRule(
                        rule_id="deny-update",
                        effect=PolicyEffect.DENY,
                        resource_types=(envelope.object_type,),
                        actions=(base_request.action,),
                        reason_code="UPDATE_DENIED",
                    ),
                ),
            )
        ),
    )
    policy_denied = denied_policy_engine._evaluate_gate(
        EnforcementGate.POLICY,
        envelope,
        base_request,
        profile,
        execution_profile=None,
    )
    assert policy_denied.reason_codes == ("POLICY_RULE:deny-update", "POLICY_DENY")

    lineage = engine._evaluate_gate(
        EnforcementGate.LINEAGE,
        replace(envelope, policy_refs=()),
        base_request,
        profile,
        execution_profile=None,
    )
    assert lineage.reason_codes == ("POLICY_LINEAGE_MISSING",)

    blocker_request = replace(
        base_request,
        blocker_snapshot=_blocker_snapshot("different-object"),
    )
    blocker = engine._evaluate_gate(
        EnforcementGate.BLOCKER,
        envelope,
        blocker_request,
        profile,
        execution_profile=None,
    )
    assert blocker.reason_codes == ("BLOCKER_SUBJECT_MISMATCH",)

    read_only_request = replace(base_request, action="READ")
    read_only_profile = replace(profile, side_effect_class="NONE")
    execution = engine._evaluate_gate(
        EnforcementGate.EXECUTION,
        envelope,
        read_only_request,
        read_only_profile,
        execution_profile=None,
    )
    assert execution.reason_codes == ("EXECUTION_GATE_NOT_APPLICABLE",)

    audit = engine._evaluate_gate(
        EnforcementGate.AUDIT,
        envelope,
        read_only_request,
        read_only_profile,
        execution_profile=None,
    )
    assert audit.reason_codes == ("AUDIT_NOT_REQUIRED",)


def test_enforcement_precondition_gates_reject_incomplete_context() -> None:
    """Schema, authority, and lifecycle preconditions reject incomplete input."""
    registry = load_enforcement_profile_registry()
    engine = DeterministicEnforcementEngine(registry=registry)
    envelope = envelope_from_tool_policy_document(
        ToolPolicyDocument(policy_id="tool-policy-preconditions", version="1.0.0")
    )
    profile = registry.profile_for_object_type(envelope.object_type)
    assert profile is not None
    request = EnforcementRequest(
        request_id="req-preconditions",
        actor="tool-admin",
        action="UPDATE",
        environment="LOCAL",
        execution_mode="IMPLEMENT",
        authorities=("tool_governance",),
        gate_attestations=_gate_attestations(
            envelope.object_hash,
            EnforcementGate.AUTHORITY,
            EnforcementGate.LIFECYCLE,
        ),
    )

    schema = engine._evaluate_gate(
        EnforcementGate.SCHEMA,
        replace(envelope, schema_ref=None),
        request,
        profile,
        execution_profile=None,
    )
    assert schema.reason_codes == ("SCHEMA_REFERENCE_MISSING",)

    no_scope = engine._evaluate_gate(
        EnforcementGate.AUTHORITY,
        replace(envelope, authority_scope=None),
        request,
        profile,
        execution_profile=None,
    )
    no_authorities = engine._evaluate_gate(
        EnforcementGate.AUTHORITY,
        envelope,
        replace(request, authorities=()),
        profile,
        execution_profile=None,
    )
    insufficient = engine._evaluate_gate(
        EnforcementGate.AUTHORITY,
        envelope,
        replace(request, authorities=("other_governance",)),
        profile,
        execution_profile=None,
    )
    assert no_scope.reason_codes == ("AUTHORITY_CONTEXT_MISSING",)
    assert no_authorities.reason_codes == ("AUTHORITY_CONTEXT_MISSING",)
    assert insufficient.reason_codes == ("AUTHORITY_NOT_GRANTED",)

    action_forbidden = engine._evaluate_gate(
        EnforcementGate.LIFECYCLE,
        envelope,
        replace(request, action="UNSUPPORTED"),
        profile,
        execution_profile=None,
    )
    grant_without_transition = engine._evaluate_gate(
        EnforcementGate.LIFECYCLE,
        envelope,
        replace(request, action="GRANT_PERMISSION"),
        profile,
        execution_profile=None,
    )
    assert action_forbidden.reason_codes == ("ACTION_NOT_ALLOWED",)
    assert grant_without_transition.reason_codes == ("LIFECYCLE_TRANSITION_REQUIRED",)

    allowed_update = engine._evaluate_gate(
        EnforcementGate.LIFECYCLE,
        envelope,
        replace(request, requested_transition="SUPERSEDED"),
        profile,
        execution_profile=None,
    )
    assert allowed_update.reason_codes == (
        "LIFECYCLE_TRANSITION_ALLOWED",
        "LIFECYCLE_ATTESTATION_VERIFIED",
    )

    missing_attestation = engine._verified_attestation_gate(
        EnforcementGate.IDENTITY,
        envelope,
        request,
        missing_reason="IDENTITY_ATTESTATION_MISSING",
        success_reason="IDENTITY_ATTESTATION_VERIFIED",
    )
    assert missing_attestation.reason_codes == ("IDENTITY_ATTESTATION_MISSING",)
    assert engine._consequence("READ", profile) == profile.side_effect_class
    assert engine._consequence("READ", replace(profile, side_effect_class="NONE")) == (
        "READ_ONLY"
    )

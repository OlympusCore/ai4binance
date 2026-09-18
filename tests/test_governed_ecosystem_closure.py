"""Regression tests for the governed ecosystem closure contracts."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.application.orchestration import (
    CycleLifecycleReceipt as ApplicationCycleLifecycleReceipt,
)
from ai4binance.domain.research import (
    CanonicalCycleEnvelope,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
    CycleLifecycleReceipt,
    LearningValidationResult,
    MemoryDisposition,
)
from ai4binance.governance.audit_checkpoint import (
    AuditAnchorStatus,
    AuditRetentionDirective,
    checkpoint_audit_chain,
    verify_audit_checkpoint,
)
from ai4binance.governance.authority import (
    ExternalApplicabilityStatus,
    ExternalAuthorityEffect,
    ExternalSourceStatus,
    detect_authority_conflicts,
    load_authority_graph,
    load_external_authority_registry,
)
from ai4binance.governance.capability_store import CapabilityLease, CapabilityStore
from ai4binance.governance.enforcement import (
    EnforcementDecision,
    EnforcementOutcome,
    PolicyEnforcementStatus,
    build_policy_enforcement_receipt,
)
from ai4binance.governance.risk_assessment import (
    RiskAssessmentV2Contract,
    RiskAssessmentV2Result,
    RiskControlEffectiveness,
    RiskControlStatus,
    RiskEvidenceStatus,
    RiskRating,
)
from ai4binance.governance.tool_policy import (
    ToolDescriptor,
    ToolPermission,
    ToolSideEffect,
)
from ai4binance.schema_validation import (
    CONTRACT_SCHEMA_MAPPINGS,
    OfflineSchemaRegistry,
    SchemaValidationError,
    validate_contract_schema_mappings,
)
from ai4binance.storage import AuditEvent, JsonlAuditStore

ROOT = Path(__file__).parents[1]
SCHEMA_ROOT = ROOT / "schemas"
NOW = datetime(2026, 9, 13, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _artifact(identifier: str, kind: CycleArtifactKind) -> CycleArtifactRef:
    return CycleArtifactRef(
        artifact_id=identifier,
        artifact_kind=kind,
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        payload_sha256=hashlib.sha256(identifier.encode()).hexdigest(),
    )


def _cycle() -> CanonicalCycleEnvelope:
    return CanonicalCycleEnvelope(
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        created_at=NOW,
        execution_surface=CycleExecutionSurface.VIRTUAL_MARKET,
        governance_status=CycleGovernanceStatus.NO_TRADE,
        canonical_snapshot=_artifact("snapshot", CycleArtifactKind.CANONICAL_SNAPSHOT),
        shared_state=_artifact("state", CycleArtifactKind.SHARED_STATE),
        observations=(_artifact("observation", CycleArtifactKind.OBSERVATION),),
        decision=_artifact("decision", CycleArtifactKind.DECISION),
        risk_assessment=_artifact("risk", CycleArtifactKind.RISK_ASSESSMENT),
        governance_result=_artifact("governance", CycleArtifactKind.GOVERNANCE_RESULT),
        execution_plan=None,
        audit_trail=_artifact("audit", CycleArtifactKind.AUDIT_TRAIL),
        blockers=("NO_TRADE",),
    )


def _enforcement_decision(
    outcome: EnforcementOutcome = EnforcementOutcome.ALLOW,
) -> EnforcementDecision:
    blockers = () if outcome is EnforcementOutcome.ALLOW else ("POLICY_DENIED",)
    return EnforcementDecision(
        decision_id="decision-1",
        outcome=outcome,
        evaluated_controls=(),
        blockers=blockers,
        reason_codes=("POLICY_ALLOW",) if not blockers else blockers,
        policy_versions=("1.0.0",),
        object_hash=SHA_A,
        evidence_hash=SHA_B,
        authority_snapshot_hash=SHA_C,
        enforcement_profile_version="1.0.0",
        enforcement_profile_hash=SHA_A,
        approval_set_hash=SHA_B,
        blocker_snapshot_hash=SHA_C,
        audit_receipt_hash=SHA_A,
        consequence="CONTINUE" if not blockers else "BLOCK",
        replay_fingerprint=SHA_B,
        scope_hash=SHA_C,
    )


def test_external_authority_registry_distinguishes_effect_and_applicability() -> None:
    registry = load_external_authority_registry(
        ROOT / "config/governance/external_authorities.yaml",
        schema_root=SCHEMA_ROOT,
    )
    graph = load_authority_graph(
        ROOT / "docs/registries/registry_authority_graph.yaml",
        schema_root=SCHEMA_ROOT,
    )

    eu_ai_act = next(
        entry for entry in registry.entries if entry.authority_id == "EU_AI_ACT"
    )
    nist = next(
        entry for entry in registry.entries if entry.authority_id == "NIST_AI_RMF_1_0"
    )
    assert eu_ai_act.effect is ExternalAuthorityEffect.MANDATORY
    assert eu_ai_act.applicability_status is ExternalApplicabilityStatus.REVIEW_REQUIRED
    assert nist.effect is ExternalAuthorityEffect.GUIDANCE
    assert nist.applicability_status is ExternalApplicabilityStatus.ADOPTED_INTERNAL
    assert registry.applicability_blockers(as_of=date(2026, 9, 13)) == (
        "EXTERNAL_AUTHORITY_REVIEW_REQUIRED:EU_AI_ACT",
        "EXTERNAL_AUTHORITY_REVIEW_REQUIRED:EU_GDPR",
    )
    external_node = next(
        node for node in graph.nodes if node.node_id == "external-authority-registry"
    )
    assert external_node.authority_layer == "L0_EXTERNAL_MANDATORY_CONSTRAINTS"
    assert external_node.source_of_truth is False
    assert graph.execution_allowed is False
    assert detect_authority_conflicts(graph) == ()


def test_external_authority_registry_reports_overdue_review() -> None:
    registry = load_external_authority_registry(
        ROOT / "config/governance/external_authorities.yaml",
        schema_root=SCHEMA_ROOT,
    )
    blockers = registry.applicability_blockers(as_of=date(2027, 1, 1))
    assert "EXTERNAL_AUTHORITY_REVIEW_OVERDUE:EU_AI_ACT" in blockers
    assert "EXTERNAL_AUTHORITY_REVIEW_OVERDUE:NIST_AI_RMF_1_0" in blockers


def test_external_authority_registry_fails_closed_for_unusable_sources() -> None:
    registry = load_external_authority_registry()
    adopted = next(
        entry
        for entry in registry.entries
        if entry.applicability_status is ExternalApplicabilityStatus.ADOPTED_INTERNAL
    )
    unusable = replace(adopted, source_status=ExternalSourceStatus.REPEALED)
    future = replace(adopted, effective_from=date(2027, 1, 1))

    assert (
        f"EXTERNAL_AUTHORITY_SOURCE_UNUSABLE:{adopted.authority_id}:REPEALED"
        in replace(registry, entries=(unusable,)).applicability_blockers(
            as_of=date(2026, 9, 13)
        )
    )
    assert f"EXTERNAL_AUTHORITY_NOT_YET_EFFECTIVE:{adopted.authority_id}" in replace(
        registry, entries=(future,)
    ).applicability_blockers(as_of=date(2026, 9, 13))


def test_risk_v2_binds_residual_risk_controls_ownership_and_schema() -> None:
    assessment = RiskAssessmentV2Contract(
        assessment_id="risk-1",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        decision_id="decision-1",
        assessed_at=NOW,
        owner_id="risk-owner",
        reviewer_id="independent-reviewer",
        affected_parties=("research-operator",),
        risk_register_ref="runtime/artifacts/risk/register.json",
        inherent_risk=RiskRating(4, 5),
        current_risk=RiskRating(3, 4),
        residual_risk=RiskRating(2, 3),
        appetite_threshold=6,
        controls=(
            RiskControlEffectiveness(
                control_id="max-risk-per-trade",
                effectiveness_bps=7000,
                evidence_sha256=SHA_A,
                status=RiskControlStatus.VERIFIED,
            ),
        ),
        evidence_status=RiskEvidenceStatus.VERIFIED,
        result=RiskAssessmentV2Result.PASS,
    )
    payload = assessment.to_payload()
    registry = OfflineSchemaRegistry.from_directory(SCHEMA_ROOT)
    registry.validate("urn:ai4binance:schema:risk:risk-assessment:2.0.0", payload)
    validate_contract_schema_mappings(registry)

    assert payload["residual_risk"] == {"likelihood": 2, "impact": 3, "score": 6}
    assert payload["execution_allowed"] is False
    assert any(
        mapping.python_contract.endswith("RiskAssessmentV2Contract")
        for mapping in CONTRACT_SCHEMA_MAPPINGS
    )


def test_risk_v1_wire_contract_remains_readable() -> None:
    OfflineSchemaRegistry.from_directory(SCHEMA_ROOT).validate(
        "urn:ai4binance:schema:risk:risk-assessment:1.0.0",
        {
            "schema_version": "1.0.0",
            "assessment_id": "risk-v1",
            "snapshot_id": "snapshot-1",
            "status": "BLOCKED",
            "blockers": ["RISK_DATA_UNAVAILABLE"],
            "reason_codes": ["RISK_DATA_UNAVAILABLE"],
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )


def test_risk_v2_rejects_unverified_or_over_appetite_pass() -> None:
    base = RiskAssessmentV2Contract(
        assessment_id="risk-1",
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        decision_id="decision-1",
        assessed_at=NOW,
        owner_id="risk-owner",
        reviewer_id="reviewer",
        affected_parties=("operator",),
        risk_register_ref="risk-register:risk-1",
        inherent_risk=RiskRating(5, 5),
        current_risk=RiskRating(4, 4),
        residual_risk=RiskRating(2, 2),
        appetite_threshold=4,
        controls=(
            RiskControlEffectiveness(
                "control-1", 9000, SHA_A, RiskControlStatus.VERIFIED
            ),
        ),
        evidence_status=RiskEvidenceStatus.VERIFIED,
        result=RiskAssessmentV2Result.PASS,
    )
    with pytest.raises(ValueError, match="within appetite"):
        replace(base, residual_risk=RiskRating(3, 2))
    with pytest.raises(ValueError, match="verified evidence"):
        replace(base, evidence_status=RiskEvidenceStatus.UNKNOWN)
    payload = base.to_payload()
    payload["blockers"] = ["RISK_DATA_UNAVAILABLE"]
    with pytest.raises(SchemaValidationError, match="validation failed"):
        OfflineSchemaRegistry.from_directory(SCHEMA_ROOT).validate(
            "urn:ai4binance:schema:risk:risk-assessment:2.0.0", payload
        )


def test_cycle_lifecycle_admits_only_independently_validated_learning() -> None:
    receipt = CycleLifecycleReceipt.bind(
        receipt_id="lifecycle-1",
        cycle=_cycle(),
        created_at=NOW + timedelta(minutes=1),
        outcome=_artifact("outcome", CycleArtifactKind.OUTCOME),
        learning_proposal=_artifact("learning", CycleArtifactKind.LEARNING_PROPOSAL),
        validation_result=_artifact("validation", CycleArtifactKind.VALIDATION_RESULT),
        memory_disposition_artifact=_artifact(
            "memory", CycleArtifactKind.MEMORY_DISPOSITION
        ),
        validation_status=LearningValidationResult.PASS,
        memory_disposition=MemoryDisposition.ADMIT,
        learning_producer_id="learning-producer",
        validator_id="independent-validator",
    )

    assert receipt.canonical_cycle_sha256 == _cycle().semantic_sha256
    assert ApplicationCycleLifecycleReceipt is CycleLifecycleReceipt
    assert receipt.to_payload()["execution_allowed"] is False
    with pytest.raises(ValueError, match="requires independent validation PASS"):
        replace(
            receipt,
            validation_status=LearningValidationResult.REJECT,
        )
    with pytest.raises(ValueError, match="validator must be independent"):
        replace(receipt, validator_id="learning-producer")


def test_policy_enforcement_receipt_requires_registered_consumed_capability(
    tmp_path: Path,
) -> None:
    store = CapabilityStore(tmp_path, clock=lambda: NOW + timedelta(seconds=1))
    lease = store.issue(
        run_id="run-1",
        project="ai4binance",
        descriptor=ToolDescriptor(
            "local-read",
            "Read a local governed artifact",
            ("ai4binance",),
            ToolSideEffect.READ_LOCAL,
        ),
        permission=ToolPermission.READ_ONLY,
        policy_hash=SHA_A,
        scope_hash=SHA_C,
    )
    lease = store.consume(lease, execution_id="enforcement-1")
    receipt = build_policy_enforcement_receipt(
        receipt_id="pep-receipt-1",
        decision=_enforcement_decision(),
        pep_id="local-tool-pep",
        enforcement_id="enforcement-1",
        enforced_at=NOW + timedelta(seconds=2),
        capability_lease=lease,
        capability_store=store,
        outcome_sha256=SHA_B,
    )

    assert receipt.status is PolicyEnforcementStatus.ENFORCED
    assert receipt.capability_lease_id == lease.lease_id
    assert receipt.execution_allowed is False
    with pytest.raises(PermissionError, match="PEP_CAPABILITY_NOT_CONSUMED"):
        build_policy_enforcement_receipt(
            receipt_id="pep-receipt-2",
            decision=_enforcement_decision(),
            pep_id="local-tool-pep",
            enforcement_id="other-enforcement",
            enforced_at=NOW,
            capability_lease=lease,
            capability_store=store,
            outcome_sha256=SHA_B,
        )


def test_policy_enforcement_receipt_rejects_unregistered_or_wrong_scope_lease(
    tmp_path: Path,
) -> None:
    lease = CapabilityLease(
        run_id="run-1",
        project="ai4binance",
        tool_name="local-read",
        permission=ToolPermission.READ_ONLY,
        policy_hash=SHA_A,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
        consumed_at=NOW + timedelta(seconds=1),
        execution_id="enforcement-1",
        scope_hash=SHA_C,
    )
    with pytest.raises(PermissionError, match="NOT_REGISTERED"):
        build_policy_enforcement_receipt(
            receipt_id="pep-unregistered",
            decision=_enforcement_decision(),
            pep_id="local-tool-pep",
            enforcement_id="enforcement-1",
            enforced_at=NOW + timedelta(seconds=2),
            capability_lease=lease,
            capability_store=CapabilityStore(tmp_path),
            outcome_sha256=SHA_B,
        )


def test_policy_enforcement_receipt_preserves_denial_without_capability() -> None:
    receipt = build_policy_enforcement_receipt(
        receipt_id="pep-denial-1",
        decision=_enforcement_decision(EnforcementOutcome.DENY),
        pep_id="local-tool-pep",
        enforcement_id="enforcement-denied",
        enforced_at=NOW,
    )
    assert receipt.status is PolicyEnforcementStatus.DENIED
    assert receipt.blockers == ("POLICY_DENIED",)
    assert receipt.capability_lease_id is None


def test_audit_checkpoint_binds_chain_head_and_retention(tmp_path: Path) -> None:
    store = JsonlAuditStore(tmp_path / "audit.jsonl", tamper_evident=True)
    store.append(AuditEvent("FIRST_EVENT", NOW, {"value": 1}))
    checkpoint = checkpoint_audit_chain(
        store,
        checkpoint_id="checkpoint-1",
        journal_ref="runtime/audit/example.jsonl",
        created_at=NOW,
        retention=AuditRetentionDirective(
            retention_class="AUDIT_CRITICAL",
            retain_until=date(2033, 9, 13),
            legal_hold=False,
            disposition_authority="Enterprise Governance",
        ),
    )

    assert checkpoint.anchor_status is AuditAnchorStatus.LOCAL_ONLY
    assert verify_audit_checkpoint(store, checkpoint) is True
    store.append(AuditEvent("SECOND_EVENT", NOW, {"value": 2}))
    assert verify_audit_checkpoint(store, checkpoint) is True
    assert checkpoint.to_payload()["execution_allowed"] is False
    other_store = JsonlAuditStore(tmp_path / "other.jsonl", tamper_evident=True)
    other_store.append(AuditEvent("FIRST_EVENT", NOW, {"value": 1}))
    assert verify_audit_checkpoint(other_store, checkpoint) is False


def test_audit_checkpoint_does_not_claim_partial_external_anchor(
    tmp_path: Path,
) -> None:
    store = JsonlAuditStore(tmp_path / "audit.jsonl", tamper_evident=True)
    store.append(AuditEvent("FIRST_EVENT", NOW, {"value": 1}))
    with pytest.raises(ValueError, match="binding must be complete"):
        checkpoint_audit_chain(
            store,
            checkpoint_id="checkpoint-1",
            journal_ref="runtime/audit/example.jsonl",
            created_at=NOW,
            retention=AuditRetentionDirective(
                retention_class="AUDIT_CRITICAL",
                retain_until=None,
                legal_hold=True,
                disposition_authority="Legal",
            ),
            external_anchor_ref="external-ledger:1",
        )

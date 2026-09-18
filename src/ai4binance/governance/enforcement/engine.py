"""Deterministic fail-closed enforcement engine for governed objects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from ai4binance.governance.enforcement.contracts import (
    AuditReceipt,
    BlockerSnapshot,
    EnforcementControlResult,
    EnforcementDecision,
    EnforcementGate,
    EnforcementOutcome,
    EnforcementProfile,
    EnforcementRequest,
    GovernedObjectEnvelope,
    VerificationAttestation,
    VerifiedApprovalSet,
)
from ai4binance.governance.enforcement.registry import EnforcementProfileRegistry
from ai4binance.governance.execution_authority import (
    VIRTUAL_MARKET_AUTO_PROFILE,
    ExecutionAuthorityProfile,
)
from ai4binance.governance.policy_as_code import (
    PolicyAsCodeEngine,
    PolicyEffect,
    PolicyRequest,
)

CONSEQUENTIAL_ACTIONS = frozenset(
    {
        "ACTIVATE",
        "DEACTIVATE",
        "PROMOTE",
        "SUPERSEDE",
        "WAIVE",
        "GRANT_PERMISSION",
        "CHANGE_PARAMETER",
        "CHANGE_RISK",
        "DEPLOY",
        "EXECUTE",
        "UPDATE",
    }
)
CONSEQENTIAL_ACTIONS = CONSEQUENTIAL_ACTIONS


def _sha256(payload: object) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DeterministicEnforcementEngine:
    registry: EnforcementProfileRegistry
    policy_engine: PolicyAsCodeEngine | None = None

    def evaluate(
        self,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
        *,
        execution_profile: ExecutionAuthorityProfile | None = None,
    ) -> EnforcementDecision:
        profile = self.registry.profile_for_object_type(envelope.object_type)
        if profile is None:
            return self._deny_without_profile(envelope, request)

        controls: list[EnforcementControlResult] = []
        for gate in self._ordered_gates(profile.required_gates):
            control = self._evaluate_gate(
                gate,
                envelope,
                request,
                profile,
                execution_profile=execution_profile,
            )
            controls.append(control)
            if control.outcome is EnforcementOutcome.DENY:
                return self._decision(
                    envelope,
                    request,
                    profile,
                    tuple(controls),
                    EnforcementOutcome.DENY,
                    consequence=self._consequence(request.action, profile),
                )
            if control.outcome in {
                EnforcementOutcome.REQUIRE_APPROVAL,
                EnforcementOutcome.QUARANTINE,
            }:
                return self._decision(
                    envelope,
                    request,
                    profile,
                    tuple(controls),
                    control.outcome,
                    consequence=self._consequence(request.action, profile),
                )

        return self._decision(
            envelope,
            request,
            profile,
            tuple(controls),
            EnforcementOutcome.ALLOW,
            consequence=self._consequence(request.action, profile),
        )

    def _evaluate_gate(
        self,
        gate: EnforcementGate,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
        profile: EnforcementProfile,
        *,
        execution_profile: ExecutionAuthorityProfile | None,
    ) -> EnforcementControlResult:
        if gate is EnforcementGate.IDENTITY:
            return self._verified_attestation_gate(
                gate,
                envelope,
                request,
                missing_reason="IDENTITY_ATTESTATION_MISSING",
                success_reason="IDENTITY_ATTESTATION_VERIFIED",
            )
        if gate is EnforcementGate.SCHEMA:
            if not envelope.schema_ref:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("SCHEMA_REFERENCE_MISSING",),
                    blockers=("SCHEMA_REFERENCE_MISSING",),
                )
            return self._verified_attestation_gate(
                gate,
                envelope,
                request,
                missing_reason="SCHEMA_ATTESTATION_MISSING",
                success_reason="SCHEMA_ATTESTATION_VERIFIED",
                details={"schema_ref": envelope.schema_ref},
            )
        if gate is EnforcementGate.AUTHORITY:
            if not envelope.authority_scope or not request.authorities:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("AUTHORITY_CONTEXT_MISSING",),
                    blockers=("AUTHORITY_CONTEXT_MISSING",),
                )
            attestation_result = self._verified_attestation_gate(
                gate,
                envelope,
                request,
                missing_reason="AUTHORITY_ATTESTATION_MISSING",
                success_reason="AUTHORITY_ATTESTATION_VERIFIED",
            )
            if attestation_result.outcome is not EnforcementOutcome.ALLOW:
                return attestation_result
            if profile.required_authorities and not set(
                profile.required_authorities
            ).issubset(set(request.authorities)):
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("AUTHORITY_NOT_GRANTED",),
                    blockers=("AUTHORITY_NOT_GRANTED",),
                )
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.ALLOW,
                reason_codes=("AUTHORITY_VERIFIED", "AUTHORITY_ATTESTATION_VERIFIED"),
            )
        if gate is EnforcementGate.LIFECYCLE:
            if request.action not in profile.allowed_actions:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("ACTION_NOT_ALLOWED",),
                    blockers=("ACTION_NOT_ALLOWED",),
                )
            attestation_result = self._verified_attestation_gate(
                gate,
                envelope,
                request,
                missing_reason="LIFECYCLE_ATTESTATION_MISSING",
                success_reason="LIFECYCLE_ATTESTATION_VERIFIED",
            )
            if attestation_result.outcome is not EnforcementOutcome.ALLOW:
                return attestation_result
            action_rule = profile.action_transition_rules.get(request.action)
            if action_rule is not None and action_rule.transition_required:
                if request.requested_transition is None:
                    return EnforcementControlResult(
                        gate=gate,
                        outcome=EnforcementOutcome.DENY,
                        reason_codes=("LIFECYCLE_TRANSITION_REQUIRED",),
                        blockers=("LIFECYCLE_TRANSITION_REQUIRED",),
                    )
                if envelope.lifecycle_state not in action_rule.allowed_from:
                    return EnforcementControlResult(
                        gate=gate,
                        outcome=EnforcementOutcome.DENY,
                        reason_codes=("LIFECYCLE_SOURCE_STATE_FORBIDDEN",),
                        blockers=("LIFECYCLE_SOURCE_STATE_FORBIDDEN",),
                    )
                if request.requested_transition not in action_rule.allowed_to:
                    return EnforcementControlResult(
                        gate=gate,
                        outcome=EnforcementOutcome.DENY,
                        reason_codes=("LIFECYCLE_TRANSITION_FORBIDDEN",),
                        blockers=("LIFECYCLE_TRANSITION_FORBIDDEN",),
                    )
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.ALLOW,
                    reason_codes=(
                        "LIFECYCLE_TRANSITION_ALLOWED",
                        "LIFECYCLE_ATTESTATION_VERIFIED",
                    ),
                )
            if request.requested_transition is None:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.ALLOW,
                    reason_codes=(
                        "NO_TRANSITION_REQUIRED",
                        "LIFECYCLE_ATTESTATION_VERIFIED",
                    ),
                )
            allowed_targets = profile.allowed_lifecycle_transitions.get(
                envelope.lifecycle_state,
                (),
            )
            if request.requested_transition not in allowed_targets:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("LIFECYCLE_TRANSITION_FORBIDDEN",),
                    blockers=("LIFECYCLE_TRANSITION_FORBIDDEN",),
                )
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.ALLOW,
                reason_codes=(
                    "LIFECYCLE_TRANSITION_ALLOWED",
                    "LIFECYCLE_ATTESTATION_VERIFIED",
                ),
            )
        if gate is EnforcementGate.POLICY:
            if self.policy_engine is None:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("POLICY_ENGINE_UNAVAILABLE",),
                    blockers=("POLICY_ENGINE_UNAVAILABLE",),
                )
            evaluation = self.policy_engine.evaluate(
                PolicyRequest(
                    resource_type=envelope.object_type,
                    action=request.action,
                    facts=request.policy_facts,
                    approved=request.verified_approval_set is not None,
                )
            )
            if evaluation.effect is PolicyEffect.DENY:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=(evaluation.reason_codes[0], "POLICY_DENY"),
                    blockers=("POLICY_DENY",),
                    details={"policy_version": evaluation.policy_version},
                )
            if evaluation.effect is PolicyEffect.REQUIRE_APPROVAL:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.REQUIRE_APPROVAL,
                    reason_codes=evaluation.reason_codes,
                    details={"policy_version": evaluation.policy_version},
                )
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.ALLOW,
                reason_codes=evaluation.reason_codes,
                details={"policy_version": evaluation.policy_version},
            )
        if gate is EnforcementGate.EVIDENCE:
            available_evidence = set(envelope.evidence_refs) | set(
                request.evidence_refs
            )
            missing = tuple(
                evidence_id
                for evidence_id in profile.required_evidence
                if evidence_id not in available_evidence
            )
            if missing:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("REQUIRED_EVIDENCE_MISSING",),
                    blockers=tuple(f"EVIDENCE_MISSING:{item}" for item in missing),
                )
            return self._verified_attestation_gate(
                gate,
                envelope,
                request,
                missing_reason="EVIDENCE_ATTESTATION_MISSING",
                success_reason="REQUIRED_EVIDENCE_VERIFIED",
            )
        if gate is EnforcementGate.LINEAGE:
            if envelope.source_of_truth and not envelope.policy_refs:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("POLICY_LINEAGE_MISSING",),
                    blockers=("POLICY_LINEAGE_MISSING",),
                )
            return self._verified_attestation_gate(
                gate,
                envelope,
                request,
                missing_reason="LINEAGE_ATTESTATION_MISSING",
                success_reason="LINEAGE_ATTESTATION_VERIFIED",
            )
        if gate is EnforcementGate.BLOCKER:
            if request.blocker_snapshot is None:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("BLOCKER_SNAPSHOT_MISSING",),
                    blockers=("BLOCKER_SNAPSHOT_MISSING",),
                )
            if request.blocker_snapshot.subject_id != envelope.object_id:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("BLOCKER_SUBJECT_MISMATCH",),
                    blockers=("BLOCKER_SUBJECT_MISMATCH",),
                )
            if request.blocker_snapshot.active_blockers:
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("ACTIVE_BLOCKERS_PRESENT",),
                    blockers=request.blocker_snapshot.active_blockers,
                )
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.ALLOW,
                reason_codes=("NO_ACTIVE_BLOCKERS",),
            )
        if gate is EnforcementGate.EXECUTION:
            if (
                request.action not in CONSEQUENTIAL_ACTIONS
                and profile.side_effect_class == "NONE"
            ):
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.ALLOW,
                    reason_codes=("EXECUTION_GATE_NOT_APPLICABLE",),
                )
            profile_to_use = execution_profile or VIRTUAL_MARKET_AUTO_PROFILE
            if (
                request.action in {"DEPLOY", "EXECUTE"}
                and profile_to_use.execution_allowed
            ):
                return EnforcementControlResult(
                    gate=gate,
                    outcome=EnforcementOutcome.DENY,
                    reason_codes=("LIVE_EXECUTION_AUTHORITY_FORBIDDEN",),
                    blockers=("EXECUTION_AUTHORITY_INVALID",),
                )
            if profile.human_approval_class != "NONE":
                approval_result = self._validate_approval_set(
                    request.verified_approval_set,
                    envelope,
                    request,
                    profile,
                )
                if approval_result is not None:
                    return approval_result
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.ALLOW,
                reason_codes=("EXECUTION_CONSEQUENCE_GUARDED",),
            )
        if gate is EnforcementGate.AUDIT:
            if self._requires_audit_receipt(request, profile):
                return self._validate_audit_receipt(request.audit_receipt, envelope)
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.ALLOW,
                reason_codes=("AUDIT_NOT_REQUIRED",),
            )
        raise AssertionError(f"unsupported enforcement gate: {gate}")

    def _ordered_gates(
        self,
        gates: tuple[EnforcementGate, ...],
    ) -> tuple[EnforcementGate, ...]:
        order = {
            EnforcementGate.IDENTITY: 0,
            EnforcementGate.SCHEMA: 1,
            EnforcementGate.AUTHORITY: 2,
            EnforcementGate.LIFECYCLE: 3,
            EnforcementGate.EVIDENCE: 4,
            EnforcementGate.LINEAGE: 5,
            EnforcementGate.BLOCKER: 6,
            EnforcementGate.POLICY: 7,
            EnforcementGate.EXECUTION: 8,
            EnforcementGate.AUDIT: 9,
        }
        return tuple(sorted(gates, key=lambda gate: (order[gate], gate.value)))

    def _decision(
        self,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
        profile: EnforcementProfile,
        controls: tuple[EnforcementControlResult, ...],
        outcome: EnforcementOutcome,
        *,
        consequence: str,
    ) -> EnforcementDecision:
        blockers = tuple(
            dict.fromkeys(
                blocker for control in controls for blocker in control.blockers
            )
        )
        reason_codes = tuple(
            dict.fromkeys(code for control in controls for code in control.reason_codes)
        )
        policy_versions = tuple(
            dict.fromkeys(
                detail["policy_version"]
                for control in controls
                for detail in (control.details,)
                if "policy_version" in detail
            )
        ) or ("NO_POLICY_VERSION",)
        evidence_hash = _sha256(
            {
                "envelope": envelope.evidence_refs,
                "request": request.evidence_refs,
                "attestations": {
                    gate.value: attestation.content_hash
                    for gate, attestation in request.gate_attestations.items()
                },
            }
        )
        authority_snapshot_hash = _sha256(
            {
                "actor": request.actor,
                "authorities": request.authorities,
                "authority_effect": envelope.authority_effect,
                "authority_layer": envelope.authority_layer,
                "authority_scope": envelope.authority_scope,
                "authority_attestation": (
                    None
                    if request.gate_attestations.get(EnforcementGate.AUTHORITY) is None
                    else request.gate_attestations[
                        EnforcementGate.AUTHORITY
                    ].content_hash
                ),
            }
        )
        replay_fingerprint = _sha256(
            {
                "action": request.action,
                "authority_snapshot_hash": authority_snapshot_hash,
                "audit_receipt_hash": self._audit_receipt_hash(request.audit_receipt),
                "blocker_snapshot_hash": self._blocker_snapshot_hash(
                    request.blocker_snapshot
                ),
                "context_hash": request.context_hash,
                "evidence_hash": evidence_hash,
                "gate_attestations": {
                    gate.value: attestation.content_hash
                    for gate, attestation in request.gate_attestations.items()
                },
                "object_hash": envelope.object_hash,
                "outcome": outcome.value,
                "profile_content_sha256": profile.content_hash,
                "profile_version": profile.profile_version,
                "reason_codes": reason_codes,
                "requested_transition": request.requested_transition,
                "verified_approval_hash": self._approval_hash(
                    request.verified_approval_set
                ),
            }
        )
        decision_id = _sha256(
            {
                "request_id": request.request_id,
                "replay_fingerprint": replay_fingerprint,
            }
        )
        return EnforcementDecision(
            decision_id=decision_id,
            outcome=outcome,
            evaluated_controls=controls,
            blockers=blockers,
            reason_codes=reason_codes,
            policy_versions=policy_versions,
            object_hash=envelope.object_hash,
            evidence_hash=evidence_hash,
            authority_snapshot_hash=authority_snapshot_hash,
            enforcement_profile_version=profile.profile_version,
            enforcement_profile_hash=profile.content_hash,
            approval_set_hash=self._approval_hash(request.verified_approval_set),
            blocker_snapshot_hash=self._blocker_snapshot_hash(request.blocker_snapshot),
            audit_receipt_hash=self._audit_receipt_hash(request.audit_receipt),
            consequence=consequence,
            replay_fingerprint=replay_fingerprint,
            scope_hash=self._scope_hash(envelope, request, profile),
        )

    def _deny_without_profile(
        self,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
    ) -> EnforcementDecision:
        pseudo_profile = EnforcementProfile(
            profile_id="UNKNOWN_PROFILE",
            profile_version="0.0.0",
            object_type=envelope.object_type,
            allowed_actions=(request.action,),
            required_gates=(EnforcementGate.IDENTITY,),
        )
        control = EnforcementControlResult(
            gate=EnforcementGate.IDENTITY,
            outcome=EnforcementOutcome.DENY,
            reason_codes=("UNKNOWN_ENFORCEMENT_PROFILE",),
            blockers=("UNMANAGED_GOVERNED_OBJECT",),
        )
        return self._decision(
            envelope,
            request,
            pseudo_profile,
            (control,),
            EnforcementOutcome.DENY,
            consequence="BLOCK",
        )

    def _consequence(self, action: str, profile: EnforcementProfile) -> str:
        if action in CONSEQUENTIAL_ACTIONS:
            return "CONSEQUENTIAL_ACTION"
        if profile.side_effect_class != "NONE":
            return profile.side_effect_class
        return "READ_ONLY"

    def _verified_attestation_gate(
        self,
        gate: EnforcementGate,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
        *,
        missing_reason: str,
        success_reason: str,
        details: dict[str, str] | None = None,
    ) -> EnforcementControlResult:
        attestation = request.gate_attestations.get(gate)
        if attestation is None:
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.DENY,
                reason_codes=(missing_reason,),
                blockers=(missing_reason,),
            )
        error = self._attestation_error(attestation, envelope)
        if error is not None:
            return EnforcementControlResult(
                gate=gate,
                outcome=EnforcementOutcome.DENY,
                reason_codes=(error,),
                blockers=(error,),
            )
        return EnforcementControlResult(
            gate=gate,
            outcome=EnforcementOutcome.ALLOW,
            reason_codes=(success_reason,),
            details=details or {},
        )

    def _attestation_error(
        self,
        attestation: VerificationAttestation,
        envelope: GovernedObjectEnvelope,
    ) -> str | None:
        if attestation.subject_hash != envelope.object_hash:
            return f"{attestation.gate.value}_ATTESTATION_SUBJECT_MISMATCH"
        if not attestation.is_verified:
            return f"{attestation.gate.value}_ATTESTATION_NOT_VERIFIED"
        if _parse_timestamp(attestation.valid_until) < _utcnow():
            return f"{attestation.gate.value}_ATTESTATION_STALE"
        return None

    def _validate_approval_set(
        self,
        approval_set: VerifiedApprovalSet | None,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
        profile: EnforcementProfile,
    ) -> EnforcementControlResult | None:
        if approval_set is None:
            return EnforcementControlResult(
                gate=EnforcementGate.EXECUTION,
                outcome=EnforcementOutcome.REQUIRE_APPROVAL,
                reason_codes=("HUMAN_APPROVAL_REQUIRED",),
            )
        if approval_set.subject_hash != envelope.object_hash:
            return EnforcementControlResult(
                gate=EnforcementGate.EXECUTION,
                outcome=EnforcementOutcome.DENY,
                reason_codes=("APPROVAL_SUBJECT_MISMATCH",),
                blockers=("APPROVAL_SUBJECT_MISMATCH",),
            )
        if approval_set.scope_hash != self._scope_hash(envelope, request, profile):
            return EnforcementControlResult(
                gate=EnforcementGate.EXECUTION,
                outcome=EnforcementOutcome.DENY,
                reason_codes=("APPROVAL_SCOPE_MISMATCH",),
                blockers=("APPROVAL_SCOPE_MISMATCH",),
            )
        if approval_set.change_class != profile.human_approval_class:
            return EnforcementControlResult(
                gate=EnforcementGate.EXECUTION,
                outcome=EnforcementOutcome.DENY,
                reason_codes=("APPROVAL_CHANGE_CLASS_MISMATCH",),
                blockers=("APPROVAL_CHANGE_CLASS_MISMATCH",),
            )
        if _parse_timestamp(approval_set.expires_at) < _utcnow():
            return EnforcementControlResult(
                gate=EnforcementGate.EXECUTION,
                outcome=EnforcementOutcome.DENY,
                reason_codes=("APPROVAL_STALE",),
                blockers=("APPROVAL_STALE",),
            )
        return None

    def _validate_audit_receipt(
        self,
        audit_receipt: AuditReceipt | None,
        envelope: GovernedObjectEnvelope,
    ) -> EnforcementControlResult:
        if audit_receipt is None:
            return EnforcementControlResult(
                gate=EnforcementGate.AUDIT,
                outcome=EnforcementOutcome.DENY,
                reason_codes=("AUDIT_RECEIPT_MISSING",),
                blockers=("AUDIT_RECEIPT_MISSING",),
            )
        if audit_receipt.subject_hash != envelope.object_hash:
            return EnforcementControlResult(
                gate=EnforcementGate.AUDIT,
                outcome=EnforcementOutcome.DENY,
                reason_codes=("AUDIT_RECEIPT_SUBJECT_MISMATCH",),
                blockers=("AUDIT_RECEIPT_SUBJECT_MISMATCH",),
            )
        return EnforcementControlResult(
            gate=EnforcementGate.AUDIT,
            outcome=EnforcementOutcome.ALLOW,
            reason_codes=("AUDIT_COMMIT_RECEIPT_VERIFIED",),
            details={"audit_log_ref": audit_receipt.audit_log_ref},
        )

    def _requires_audit_receipt(
        self,
        request: EnforcementRequest,
        profile: EnforcementProfile,
    ) -> bool:
        return (
            request.action in CONSEQUENTIAL_ACTIONS
            or profile.side_effect_class != "NONE"
        )

    def _scope_hash(
        self,
        envelope: GovernedObjectEnvelope,
        request: EnforcementRequest,
        profile: EnforcementProfile,
    ) -> str:
        return _sha256(
            {
                "action": request.action,
                "authority_scope": envelope.authority_scope,
                "environment": request.environment,
                "execution_mode": request.execution_mode,
                "object_type": envelope.object_type,
                "profile_id": profile.profile_id,
                "requested_transition": request.requested_transition,
            }
        )

    def _approval_hash(self, approval_set: VerifiedApprovalSet | None) -> str:
        return (
            approval_set.content_hash
            if approval_set is not None
            else _sha256("NO_VERIFIED_APPROVAL_SET")
        )

    def _blocker_snapshot_hash(self, blocker_snapshot: BlockerSnapshot | None) -> str:
        if blocker_snapshot is None:
            return _sha256("NO_BLOCKER_SNAPSHOT")
        return blocker_snapshot.content_hash

    def _audit_receipt_hash(self, audit_receipt: AuditReceipt | None) -> str:
        if audit_receipt is None:
            return _sha256("NO_AUDIT_RECEIPT")
        return audit_receipt.content_hash

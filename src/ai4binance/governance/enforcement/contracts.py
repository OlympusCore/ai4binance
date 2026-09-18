"""Canonical contracts for universal governed-object enforcement."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType


class EnforcementOutcome(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    QUARANTINE = "QUARANTINE"


class EnforcementGate(StrEnum):
    IDENTITY = "IDENTITY"
    SCHEMA = "SCHEMA"
    AUTHORITY = "AUTHORITY"
    LIFECYCLE = "LIFECYCLE"
    POLICY = "POLICY"
    EVIDENCE = "EVIDENCE"
    LINEAGE = "LINEAGE"
    BLOCKER = "BLOCKER"
    EXECUTION = "EXECUTION"
    AUDIT = "AUDIT"


class AttestationResult(StrEnum):
    VERIFIED = "VERIFIED"
    DENIED = "DENIED"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


def _require_unique_nonblank(name: str, values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not value.strip() for value in normalized):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    return normalized


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_sha256(name: str, value: str | None) -> None:
    if value is None or len(value) != 64:
        raise ValueError(f"{name} must be a SHA-256 hex digest")


def _require_timestamp(name: str, value: str) -> datetime:
    _require_non_empty(name, value)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class VerificationAttestation:
    attestation_id: str
    gate: EnforcementGate
    subject_hash: str
    provider_id: str
    provider_version: str
    policy_version: str
    evaluated_at: str
    valid_until: str
    evidence_refs: tuple[str, ...]
    evidence_hash: str
    result: AttestationResult
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "attestation_id",
            "provider_id",
            "provider_version",
            "policy_version",
            "evaluated_at",
            "valid_until",
        ):
            _require_non_empty(name, str(getattr(self, name)))
        _require_sha256("subject_hash", self.subject_hash)
        _require_sha256("evidence_hash", self.evidence_hash)
        _require_unique_nonblank("attestation evidence_refs", self.evidence_refs)
        _require_unique_nonblank("attestation reason_codes", self.reason_codes)
        evaluated_at = _require_timestamp("evaluated_at", self.evaluated_at)
        valid_until = _require_timestamp("valid_until", self.valid_until)
        if valid_until < evaluated_at:
            raise ValueError("valid_until cannot be earlier than evaluated_at")

    @property
    def is_verified(self) -> bool:
        return self.result is AttestationResult.VERIFIED

    @property
    def content_hash(self) -> str:
        return _canonical_sha256(
            {
                "attestation_id": self.attestation_id,
                "gate": self.gate.value,
                "subject_hash": self.subject_hash,
                "provider_id": self.provider_id,
                "provider_version": self.provider_version,
                "policy_version": self.policy_version,
                "evaluated_at": self.evaluated_at,
                "valid_until": self.valid_until,
                "evidence_refs": self.evidence_refs,
                "evidence_hash": self.evidence_hash,
                "result": self.result.value,
                "reason_codes": self.reason_codes,
            }
        )


@dataclass(frozen=True, slots=True)
class VerifiedApprovalSet:
    approval_set_id: str
    subject_hash: str
    scope_hash: str
    change_class: str
    required_roles: tuple[str, ...]
    satisfied_roles: tuple[str, ...]
    principal_ids: tuple[str, ...]
    approval_ids: tuple[str, ...]
    evidence_hash: str
    verified_at: str
    expires_at: str
    verification_policy_hash: str

    def __post_init__(self) -> None:
        for name in ("approval_set_id", "change_class", "verified_at", "expires_at"):
            _require_non_empty(name, str(getattr(self, name)))
        for name in (
            "subject_hash",
            "scope_hash",
            "evidence_hash",
            "verification_policy_hash",
        ):
            _require_sha256(name, str(getattr(self, name)))
        _require_unique_nonblank("required_roles", self.required_roles)
        _require_unique_nonblank("satisfied_roles", self.satisfied_roles)
        _require_unique_nonblank("principal_ids", self.principal_ids)
        _require_unique_nonblank("approval_ids", self.approval_ids)
        missing_roles = set(self.required_roles) - set(self.satisfied_roles)
        if missing_roles:
            raise ValueError("verified approval set is missing required roles")
        verified_at = _require_timestamp("verified_at", self.verified_at)
        expires_at = _require_timestamp("expires_at", self.expires_at)
        if expires_at < verified_at:
            raise ValueError("expires_at cannot be earlier than verified_at")

    @property
    def content_hash(self) -> str:
        return _canonical_sha256(
            {
                "approval_set_id": self.approval_set_id,
                "subject_hash": self.subject_hash,
                "scope_hash": self.scope_hash,
                "change_class": self.change_class,
                "required_roles": self.required_roles,
                "satisfied_roles": self.satisfied_roles,
                "principal_ids": self.principal_ids,
                "approval_ids": self.approval_ids,
                "evidence_hash": self.evidence_hash,
                "verified_at": self.verified_at,
                "expires_at": self.expires_at,
                "verification_policy_hash": self.verification_policy_hash,
            }
        )


@dataclass(frozen=True, slots=True)
class BlockerSnapshot:
    blocker_snapshot_id: str
    blocker_registry_hash: str
    active_blockers: tuple[str, ...]
    resolved_blockers: tuple[str, ...]
    evaluated_at: str
    subject_id: str

    def __post_init__(self) -> None:
        _require_non_empty("blocker_snapshot_id", self.blocker_snapshot_id)
        _require_sha256("blocker_registry_hash", self.blocker_registry_hash)
        _require_non_empty("subject_id", self.subject_id)
        _require_timestamp("evaluated_at", self.evaluated_at)
        _require_unique_nonblank("active_blockers", self.active_blockers)
        _require_unique_nonblank("resolved_blockers", self.resolved_blockers)

    @property
    def content_hash(self) -> str:
        return _canonical_sha256(
            {
                "blocker_snapshot_id": self.blocker_snapshot_id,
                "blocker_registry_hash": self.blocker_registry_hash,
                "active_blockers": self.active_blockers,
                "resolved_blockers": self.resolved_blockers,
                "evaluated_at": self.evaluated_at,
                "subject_id": self.subject_id,
            }
        )


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    receipt_id: str
    subject_hash: str
    audit_log_ref: str
    commit_hash: str
    recorded_at: str

    def __post_init__(self) -> None:
        _require_non_empty("receipt_id", self.receipt_id)
        _require_non_empty("audit_log_ref", self.audit_log_ref)
        _require_sha256("subject_hash", self.subject_hash)
        _require_sha256("commit_hash", self.commit_hash)
        _require_timestamp("recorded_at", self.recorded_at)

    @property
    def content_hash(self) -> str:
        return _canonical_sha256(
            {
                "receipt_id": self.receipt_id,
                "subject_hash": self.subject_hash,
                "audit_log_ref": self.audit_log_ref,
                "commit_hash": self.commit_hash,
                "recorded_at": self.recorded_at,
            }
        )


@dataclass(frozen=True, slots=True)
class ActionTransitionRule:
    action: str
    transition_required: bool
    allowed_from: tuple[str, ...]
    allowed_to: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty("action", self.action)
        _require_unique_nonblank("allowed_from", self.allowed_from)
        _require_unique_nonblank("allowed_to", self.allowed_to)
        if self.transition_required and (not self.allowed_from or not self.allowed_to):
            raise ValueError(
                "transition-required action rules must declare "
                "allowed_from and allowed_to"
            )


@dataclass(frozen=True, slots=True)
class GovernedObjectEnvelope:
    object_id: str
    object_type: str
    version: str
    lifecycle_state: str
    owner: str
    authority_layer: str
    authority_effect: str | None
    authority_scope: str | None
    source_of_truth: bool
    canonical_ref: str
    schema_ref: str | None
    content_hash: str | None
    policy_refs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    permission_profile_ref: str | None = None
    classification: str = "INTERNAL"

    def __post_init__(self) -> None:
        for name in (
            "object_id",
            "object_type",
            "version",
            "lifecycle_state",
            "owner",
            "authority_layer",
            "canonical_ref",
            "classification",
        ):
            _require_non_empty(name, str(getattr(self, name)))
        _require_unique_nonblank("policy_refs", self.policy_refs)
        _require_unique_nonblank("dependencies", self.dependencies)
        _require_unique_nonblank("evidence_refs", self.evidence_refs)
        if self.schema_ref is not None:
            _require_non_empty("schema_ref", self.schema_ref)
        if self.content_hash is not None:
            _require_sha256("content_hash", self.content_hash)

    @property
    def object_hash(self) -> str:
        return _canonical_sha256(
            {
                "authority_effect": self.authority_effect,
                "authority_layer": self.authority_layer,
                "authority_scope": self.authority_scope,
                "canonical_ref": self.canonical_ref,
                "classification": self.classification,
                "content_hash": self.content_hash,
                "dependencies": self.dependencies,
                "evidence_refs": self.evidence_refs,
                "lifecycle_state": self.lifecycle_state,
                "object_id": self.object_id,
                "object_type": self.object_type,
                "owner": self.owner,
                "permission_profile_ref": self.permission_profile_ref,
                "policy_refs": self.policy_refs,
                "schema_ref": self.schema_ref,
                "source_of_truth": self.source_of_truth,
                "version": self.version,
            }
        )


@dataclass(frozen=True, slots=True)
class EnforcementRequest:
    request_id: str
    actor: str
    action: str
    environment: str
    execution_mode: str
    requested_transition: str | None = None
    evidence_refs: tuple[str, ...] = ()
    authorities: tuple[str, ...] = ()
    correlation_id: str = ""
    context_hash: str | None = None
    policy_facts: Mapping[str, str] = field(default_factory=dict)
    gate_attestations: Mapping[EnforcementGate, VerificationAttestation] = field(
        default_factory=dict
    )
    blocker_snapshot: BlockerSnapshot | None = None
    verified_approval_set: VerifiedApprovalSet | None = None
    audit_receipt: AuditReceipt | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "actor", "action", "environment", "execution_mode"):
            _require_non_empty(name, str(getattr(self, name)))
        _require_unique_nonblank("evidence_refs", self.evidence_refs)
        _require_unique_nonblank("authorities", self.authorities)
        if self.correlation_id:
            _require_non_empty("correlation_id", self.correlation_id)
        if self.context_hash is not None:
            _require_sha256("context_hash", self.context_hash)
        if any(
            not key.strip() or not value.strip()
            for key, value in self.policy_facts.items()
        ):
            raise ValueError("policy_facts must be non-empty strings")
        if any(
            gate != attestation.gate
            for gate, attestation in self.gate_attestations.items()
        ):
            raise ValueError("gate_attestations keys must match attestation gates")
        object.__setattr__(
            self, "policy_facts", MappingProxyType(dict(self.policy_facts))
        )
        object.__setattr__(
            self,
            "gate_attestations",
            MappingProxyType(dict(self.gate_attestations)),
        )


@dataclass(frozen=True, slots=True)
class EnforcementControlResult:
    gate: EnforcementGate
    outcome: EnforcementOutcome
    reason_codes: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    details: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_unique_nonblank("control reason_codes", self.reason_codes)
        _require_unique_nonblank("control blockers", self.blockers)
        if any(
            not key.strip() or not value.strip() for key, value in self.details.items()
        ):
            raise ValueError("control details must use non-empty strings")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True, slots=True)
class EnforcementProfile:
    profile_id: str
    profile_version: str
    object_type: str
    allowed_actions: tuple[str, ...]
    required_gates: tuple[EnforcementGate, ...]
    required_evidence: tuple[str, ...] = ()
    required_authorities: tuple[str, ...] = ()
    allowed_lifecycle_transitions: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    action_transition_rules: Mapping[str, ActionTransitionRule] = field(
        default_factory=dict
    )
    side_effect_class: str = "NONE"
    human_approval_class: str = "NONE"

    def __post_init__(self) -> None:
        for name in (
            "profile_id",
            "profile_version",
            "object_type",
            "side_effect_class",
            "human_approval_class",
        ):
            _require_non_empty(name, str(getattr(self, name)))
        _require_unique_nonblank("allowed_actions", self.allowed_actions)
        gate_names = tuple(gate.value for gate in self.required_gates)
        _require_unique_nonblank("required_gates", gate_names)
        _require_unique_nonblank("required_evidence", self.required_evidence)
        _require_unique_nonblank("required_authorities", self.required_authorities)
        normalized: dict[str, tuple[str, ...]] = {}
        for source, targets in self.allowed_lifecycle_transitions.items():
            _require_non_empty("allowed_lifecycle_transitions source", source)
            normalized[source] = _require_unique_nonblank(
                f"allowed_lifecycle_transitions[{source}]",
                targets,
            )
        object.__setattr__(
            self,
            "allowed_lifecycle_transitions",
            MappingProxyType(normalized),
        )
        normalized_rules: dict[str, ActionTransitionRule] = {}
        for action, rule in self.action_transition_rules.items():
            _require_non_empty("action_transition_rules key", action)
            if action != rule.action:
                raise ValueError("action transition rule key must match rule.action")
            normalized_rules[action] = rule
        object.__setattr__(
            self,
            "action_transition_rules",
            MappingProxyType(normalized_rules),
        )

    @property
    def content_hash(self) -> str:
        return _canonical_sha256(
            {
                "profile_id": self.profile_id,
                "profile_version": self.profile_version,
                "object_type": self.object_type,
                "allowed_actions": self.allowed_actions,
                "required_gates": tuple(gate.value for gate in self.required_gates),
                "required_evidence": self.required_evidence,
                "required_authorities": self.required_authorities,
                "allowed_lifecycle_transitions": dict(
                    self.allowed_lifecycle_transitions
                ),
                "action_transition_rules": {
                    action: {
                        "transition_required": rule.transition_required,
                        "allowed_from": rule.allowed_from,
                        "allowed_to": rule.allowed_to,
                    }
                    for action, rule in self.action_transition_rules.items()
                },
                "side_effect_class": self.side_effect_class,
                "human_approval_class": self.human_approval_class,
            }
        )


@dataclass(frozen=True, slots=True)
class EnforcementDecision:
    decision_id: str
    outcome: EnforcementOutcome
    evaluated_controls: tuple[EnforcementControlResult, ...]
    blockers: tuple[str, ...]
    reason_codes: tuple[str, ...]
    policy_versions: tuple[str, ...]
    object_hash: str
    evidence_hash: str
    authority_snapshot_hash: str
    enforcement_profile_version: str
    enforcement_profile_hash: str
    approval_set_hash: str
    blocker_snapshot_hash: str
    audit_receipt_hash: str
    consequence: str
    replay_fingerprint: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    scope_hash: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("decision_id", self.decision_id)
        _require_unique_nonblank("decision blockers", self.blockers)
        _require_unique_nonblank("decision reason_codes", self.reason_codes)
        _require_unique_nonblank("policy_versions", self.policy_versions)
        for name in (
            "object_hash",
            "evidence_hash",
            "authority_snapshot_hash",
            "enforcement_profile_version",
            "enforcement_profile_hash",
            "approval_set_hash",
            "blocker_snapshot_hash",
            "audit_receipt_hash",
            "consequence",
            "replay_fingerprint",
        ):
            _require_non_empty(name, str(getattr(self, name)))
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("enforcement decision cannot authorize execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("enforcement decision must keep live execution blocked")
        if self.scope_hash:
            _require_sha256("scope_hash", self.scope_hash)

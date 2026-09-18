"""PDP-to-PEP consumption receipt for an already evaluated policy decision."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ai4binance.governance.capability_store import CapabilityLease, CapabilityStore
from ai4binance.governance.enforcement.contracts import (
    EnforcementDecision,
    EnforcementOutcome,
)


class PolicyEnforcementStatus(StrEnum):
    ENFORCED = "ENFORCED"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class PolicyEnforcementReceipt:
    receipt_id: str
    decision_id: str
    decision_sha256: str
    subject_hash: str
    scope_hash: str
    approval_set_hash: str
    pep_id: str
    enforcement_id: str
    enforced_at: datetime
    status: PolicyEnforcementStatus
    blockers: tuple[str, ...]
    capability_lease_id: str | None = None
    capability_policy_hash: str | None = None
    capability_scope_hash: str | None = None
    capability_run_id: str | None = None
    capability_project: str | None = None
    capability_tool_name: str | None = None
    outcome_sha256: str | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not isinstance(self.status, PolicyEnforcementStatus):
            raise ValueError("policy enforcement status is invalid")
        for name in (
            "receipt_id",
            "decision_id",
            "pep_id",
            "enforcement_id",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"policy enforcement {name} is required")
        for name in (
            "decision_sha256",
            "subject_hash",
            "scope_hash",
            "approval_set_hash",
        ):
            _require_sha256(name, str(getattr(self, name)))
        if (
            self.enforced_at.tzinfo is None
            or self.enforced_at.utcoffset() != UTC.utcoffset(self.enforced_at)
        ):
            raise ValueError("policy enforcement enforced_at must be UTC")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("policy enforcement blockers cannot contain blanks")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("policy enforcement blockers must be unique")
        capability_fields = (
            self.capability_lease_id,
            self.capability_policy_hash,
            self.capability_scope_hash,
            self.capability_run_id,
            self.capability_project,
            self.capability_tool_name,
        )
        if any(value is None for value in capability_fields) != all(
            value is None for value in capability_fields
        ):
            raise ValueError("policy enforcement capability binding must be complete")
        if self.capability_policy_hash is not None:
            _require_sha256("capability_policy_hash", self.capability_policy_hash)
            _require_sha256("capability_scope_hash", str(self.capability_scope_hash))
            if self.capability_lease_id is None or not self.capability_lease_id.strip():
                raise ValueError("policy enforcement capability lease_id is required")
        if self.outcome_sha256 is not None:
            _require_sha256("outcome_sha256", self.outcome_sha256)
        if self.status is PolicyEnforcementStatus.ENFORCED:
            if self.blockers:
                raise ValueError("enforced policy receipt cannot contain blockers")
            if self.capability_lease_id is None or self.outcome_sha256 is None:
                raise ValueError(
                    "enforced policy receipt requires capability and outcome"
                )
        elif not self.blockers:
            raise ValueError("denied policy receipt requires blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("policy enforcement receipt cannot grant live authority")

    @property
    def semantic_sha256(self) -> str:
        payload = json.dumps(
            self.to_payload(include_semantic_hash=False),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_payload(self, *, include_semantic_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "receipt_id": self.receipt_id,
            "decision_id": self.decision_id,
            "decision_sha256": self.decision_sha256,
            "subject_hash": self.subject_hash,
            "scope_hash": self.scope_hash,
            "approval_set_hash": self.approval_set_hash,
            "pep_id": self.pep_id,
            "enforcement_id": self.enforcement_id,
            "enforced_at": self.enforced_at.isoformat().replace("+00:00", "Z"),
            "status": self.status.value,
            "blockers": list(self.blockers),
            "capability_lease_id": self.capability_lease_id,
            "capability_policy_hash": self.capability_policy_hash,
            "capability_scope_hash": self.capability_scope_hash,
            "capability_run_id": self.capability_run_id,
            "capability_project": self.capability_project,
            "capability_tool_name": self.capability_tool_name,
            "outcome_sha256": self.outcome_sha256,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        if include_semantic_hash:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload


def build_policy_enforcement_receipt(
    *,
    receipt_id: str,
    decision: EnforcementDecision,
    pep_id: str,
    enforcement_id: str,
    enforced_at: datetime,
    capability_lease: CapabilityLease | None = None,
    capability_store: CapabilityStore | None = None,
    outcome_sha256: str | None = None,
) -> PolicyEnforcementReceipt:
    """Bind an ALLOW decision to a consumed capability, or record a denial."""
    if not decision.scope_hash:
        raise ValueError("PEP decision scope_hash is required")
    decision_sha256 = _decision_sha256(decision)
    if decision.outcome is EnforcementOutcome.ALLOW:
        if capability_lease is None:
            raise PermissionError("PEP_CAPABILITY_REQUIRED")
        if capability_store is None:
            raise PermissionError("PEP_CAPABILITY_STORE_REQUIRED")
        if (
            capability_lease.consumed_at is None
            or capability_lease.execution_id != enforcement_id
        ):
            raise PermissionError("PEP_CAPABILITY_NOT_CONSUMED")
        if (
            not capability_lease.scope_hash
            or capability_lease.scope_hash != decision.scope_hash
        ):
            raise PermissionError("PEP_CAPABILITY_SCOPE_MISMATCH")
        if capability_lease.policy_hash != decision.enforcement_profile_hash:
            raise PermissionError("PEP_CAPABILITY_POLICY_MISMATCH")
        capability_store.verify_consumed(
            capability_lease,
            execution_id=enforcement_id,
            enforced_at=enforced_at,
        )
        if outcome_sha256 is None:
            raise ValueError("PEP outcome_sha256 is required")
        return PolicyEnforcementReceipt(
            receipt_id=receipt_id,
            decision_id=decision.decision_id,
            decision_sha256=decision_sha256,
            subject_hash=decision.object_hash,
            scope_hash=decision.scope_hash,
            approval_set_hash=decision.approval_set_hash,
            pep_id=pep_id,
            enforcement_id=enforcement_id,
            enforced_at=enforced_at,
            status=PolicyEnforcementStatus.ENFORCED,
            blockers=(),
            capability_lease_id=capability_lease.lease_id,
            capability_policy_hash=capability_lease.policy_hash,
            capability_scope_hash=capability_lease.scope_hash,
            capability_run_id=capability_lease.run_id,
            capability_project=capability_lease.project,
            capability_tool_name=capability_lease.tool_name,
            outcome_sha256=outcome_sha256,
        )
    blockers = decision.blockers or decision.reason_codes
    return PolicyEnforcementReceipt(
        receipt_id=receipt_id,
        decision_id=decision.decision_id,
        decision_sha256=decision_sha256,
        subject_hash=decision.object_hash,
        scope_hash=decision.scope_hash,
        approval_set_hash=decision.approval_set_hash,
        pep_id=pep_id,
        enforcement_id=enforcement_id,
        enforced_at=enforced_at,
        status=PolicyEnforcementStatus.DENIED,
        blockers=blockers,
    )


def _decision_sha256(decision: EnforcementDecision) -> str:
    payload = {
        "decision_id": decision.decision_id,
        "outcome": decision.outcome.value,
        "evaluated_controls": tuple(
            {
                "gate": control.gate.value,
                "outcome": control.outcome.value,
                "reason_codes": control.reason_codes,
                "blockers": control.blockers,
                "details": dict(control.details),
            }
            for control in decision.evaluated_controls
        ),
        "blockers": decision.blockers,
        "reason_codes": decision.reason_codes,
        "policy_versions": decision.policy_versions,
        "object_hash": decision.object_hash,
        "evidence_hash": decision.evidence_hash,
        "authority_snapshot_hash": decision.authority_snapshot_hash,
        "enforcement_profile_version": decision.enforcement_profile_version,
        "enforcement_profile_hash": decision.enforcement_profile_hash,
        "approval_set_hash": decision.approval_set_hash,
        "blocker_snapshot_hash": decision.blocker_snapshot_hash,
        "audit_receipt_hash": decision.audit_receipt_hash,
        "consequence": decision.consequence,
        "replay_fingerprint": decision.replay_fingerprint,
        "scope_hash": decision.scope_hash,
        "execution_allowed": decision.execution_allowed,
        "promotion_status": decision.promotion_status,
        "live_eligibility_status": decision.live_eligibility_status,
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


__all__ = (
    "PolicyEnforcementReceipt",
    "PolicyEnforcementStatus",
    "build_policy_enforcement_receipt",
)

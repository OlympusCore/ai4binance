"""Approval verification service for governed memory promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ai4binance.core.contracts.memory import (
    MemoryCandidate,
    MemoryPromotionApprovalRecord,
    MemoryPromotionVerificationRecord,
    MemoryPromotionVerificationResult,
    MemoryRecord,
)
from ai4binance.domain.memory import GovernedMemoryFabric


class MemoryAdmissionStore(Protocol):
    def append(self, record: MemoryRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class MemoryPromotionRequest:
    candidate: MemoryCandidate
    approval_record: MemoryPromotionApprovalRecord
    verification_record: MemoryPromotionVerificationRecord
    requested_at: datetime
    policy_version: str

    def __post_init__(self) -> None:
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("memory promotion request time must be timezone-aware")
        if not self.policy_version.strip():
            raise ValueError("memory promotion policy version is required")


@dataclass(frozen=True, slots=True)
class MemoryApprovalVerificationService:
    """Verify approval and independent verification before memory activation."""

    def admit(
        self, request: MemoryPromotionRequest, *, store: MemoryAdmissionStore
    ) -> MemoryRecord:
        """Reverify supplied current approval evidence and persist only on success."""
        result = self.verify(request)
        record = GovernedMemoryFabric().validate_candidate(
            request.candidate,
            promotion_verification=result,
            at=request.requested_at,
            policy_version=request.policy_version,
        )
        store.append(record)
        return record

    def verify(
        self,
        request: MemoryPromotionRequest,
    ) -> MemoryPromotionVerificationResult:
        blockers: list[str] = []
        candidate_record = request.candidate.record
        approval = request.approval_record
        verification = request.verification_record
        requested_at = request.requested_at.astimezone(UTC)

        if approval.status != "APPROVED":
            blockers.append("MEMORY_APPROVAL_NOT_APPROVED")
        if approval.revoked_at is not None:
            blockers.append("MEMORY_APPROVAL_REVOKED")
        if approval.expires_at is not None and approval.expires_at <= requested_at:
            blockers.append("MEMORY_APPROVAL_EXPIRED")
        if approval.policy_version != request.policy_version:
            blockers.append("MEMORY_APPROVAL_POLICY_MISMATCH")
        if verification.policy_version != request.policy_version:
            blockers.append("MEMORY_VERIFICATION_POLICY_MISMATCH")
        if approval.candidate_memory_id != candidate_record.memory_id:
            blockers.append("MEMORY_APPROVAL_SUBJECT_MISMATCH")
        if verification.candidate_memory_id != candidate_record.memory_id:
            blockers.append("MEMORY_VERIFICATION_SUBJECT_MISMATCH")
        if approval.candidate_content_hash != candidate_record.content_hash:
            blockers.append("MEMORY_APPROVAL_HASH_MISMATCH")
        if verification.candidate_content_hash != candidate_record.content_hash:
            blockers.append("MEMORY_VERIFICATION_HASH_MISMATCH")
        if verification.approval_record_id != approval.approval_record_id:
            blockers.append("MEMORY_VERIFICATION_APPROVAL_MISMATCH")
        if verification.status != "VERIFIED":
            blockers.append("MEMORY_VERIFICATION_NOT_VERIFIED")
        if approval.approver_ref == verification.verifier_ref:
            blockers.append("MEMORY_APPROVAL_SEPARATION_OF_DUTIES_FAILED")
        if approval.approved_at > requested_at:
            blockers.append("MEMORY_APPROVAL_FROM_FUTURE")
        if verification.verified_at > requested_at:
            blockers.append("MEMORY_VERIFICATION_FROM_FUTURE")
        if verification.verified_at < approval.approved_at:
            blockers.append("MEMORY_VERIFICATION_PRECEDES_APPROVAL")

        unique_blockers = tuple(dict.fromkeys(blockers))
        return MemoryPromotionVerificationResult(
            approval_record_id=approval.approval_record_id,
            verification_record_id=verification.verification_record_id,
            verified=not unique_blockers,
            blockers=unique_blockers,
            candidate_memory_id=candidate_record.memory_id,
            candidate_content_hash=candidate_record.content_hash,
            policy_version=request.policy_version,
            checked_at=requested_at,
            expires_at=approval.expires_at,
            candidate_binding_hash=request.candidate.binding_sha256,
        )

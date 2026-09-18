"""Deterministic claim verification reducer."""

from __future__ import annotations

from ai4binance.external_intel.core.enums import VerificationStatus
from ai4binance.external_intel.core.models import ExternalClaim, ExternalEvidence
from ai4binance.external_intel.evidence.original_source import assess_original_sources


def verify_claim(
    claim: ExternalClaim,
    evidence: tuple[ExternalEvidence, ...],
) -> VerificationStatus:
    linked = tuple(
        item for item in evidence if item.evidence_id in claim.source_evidence_ids
    )
    if not linked:
        return VerificationStatus.DATA_UNAVAILABLE
    assessment = assess_original_sources(linked)
    if assessment.independent_source_count >= 2 and any(
        item.reliability >= 0.8 for item in linked
    ):
        return VerificationStatus.VERIFIED
    if assessment.independent_source_count >= 2:
        return VerificationStatus.PARTIALLY_VERIFIED
    return VerificationStatus.UNVERIFIED

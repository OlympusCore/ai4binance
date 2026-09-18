"""Immutable contracts for evidence-backed social content drafts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ComplianceStatus(StrEnum):
    """Machine-verifiable content policy result."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


class DraftQueueStatus(StrEnum):
    """Local review states; none of them imply publishing authority."""

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ContentSource:
    """Provenance for the one evidence artifact used by a draft."""

    artifact_type: str
    source_artifact: str
    source_sha256: str
    evidence_timestamp: datetime
    freshness_status: str

    def __post_init__(self) -> None:
        if not self.artifact_type.strip() or not self.source_artifact.strip():
            raise ValueError("content source identity cannot be empty")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("content source hash is invalid")
        if (
            self.evidence_timestamp.tzinfo is None
            or self.evidence_timestamp.utcoffset() is None
        ):
            raise ValueError("content source timestamp must be timezone-aware")
        if self.freshness_status != "FRESH":
            raise ValueError("content drafts require fresh evidence")


@dataclass(frozen=True, slots=True)
class ContentClaim:
    """One bounded statement and the exact artifact field supporting it."""

    text: str
    source_field: str

    def __post_init__(self) -> None:
        if not self.text.strip() or not self.source_field.strip():
            raise ValueError("content claim and source field cannot be empty")
        if len(self.text) > 160 or len(self.source_field) > 80:
            raise ValueError("content claim exceeds bounded size")


@dataclass(frozen=True, slots=True)
class ContentDraft:
    """Verified X draft that cannot publish or affect trading decisions."""

    draft_id: str
    created_at: datetime
    content: str
    source: ContentSource
    claims: tuple[ContentClaim, ...]
    compliance_status: ComplianceStatus
    blockers: tuple[str, ...] = field(default_factory=tuple)
    platform: str = "X"
    template_version: str = "market-outlook-v1"
    queue_status: DraftQueueStatus = DraftQueueStatus.REVIEW_REQUIRED
    publish_allowed: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if len(self.draft_id) != 64 or any(
            character not in "0123456789abcdef" for character in self.draft_id
        ):
            raise ValueError("draft id must be a SHA-256 digest")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("draft timestamp must be timezone-aware")
        if not self.content.strip() or len(self.content) > 280:
            raise ValueError("X draft must contain 1-280 characters")
        if not self.claims:
            raise ValueError("content draft requires sourced claims")
        if self.compliance_status is not ComplianceStatus.PASSED or self.blockers:
            raise ValueError("only compliant drafts may enter the approval queue")
        if self.queue_status is not DraftQueueStatus.REVIEW_REQUIRED:
            raise ValueError("new content drafts must require review")
        if self.publish_allowed or self.execution_allowed:
            raise ValueError("draft-only content cannot publish or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("content workflow must remain live blocked")

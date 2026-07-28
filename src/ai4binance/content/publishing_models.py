"""Typed contracts for explicitly approved social publishing."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from ai4binance.content.models import ContentDraft


class SocialPlatform(StrEnum):
    """Supported text publishing destinations."""

    X = "X"
    TELEGRAM = "TELEGRAM"
    LINKEDIN = "LINKEDIN"


class PublishStatus(StrEnum):
    """Outcome of one guarded publish request."""

    BLOCKED = "BLOCKED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class PublishingConfig:
    """Default-deny runtime publishing policy without credential values."""

    enabled_platforms: frozenset[SocialPlatform] = field(default_factory=frozenset)
    request_timeout_seconds: float = 10.0
    minimum_publish_interval: timedelta = timedelta(minutes=1)
    maximum_draft_age: timedelta = timedelta(hours=2)
    maximum_response_bytes: int = 65_536

    def __post_init__(self) -> None:
        if self.request_timeout_seconds <= 0:
            raise ValueError("publishing timeout must be positive")
        if self.minimum_publish_interval < timedelta(0):
            raise ValueError("publishing interval cannot be negative")
        if self.maximum_draft_age <= timedelta(0):
            raise ValueError("maximum draft age must be positive")
        if self.maximum_response_bytes <= 0:
            raise ValueError("maximum response bytes must be positive")


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """One platform-specific explicit user publishing instruction."""

    draft: ContentDraft
    platform: SocialPlatform
    requested_by: str
    confirmation: str

    def __post_init__(self) -> None:
        if not self.requested_by.strip() or len(self.requested_by) > 80:
            raise ValueError("publishing requester is invalid")
        if not self.confirmation.strip() or len(self.confirmation) > 160:
            raise ValueError("publishing confirmation is invalid")

    @property
    def required_confirmation(self) -> str:
        return f"PUBLISH_{self.platform.value}:{self.draft.draft_id}"


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    """Secret-free, append-only compatible publish outcome."""

    request_id: str
    draft_id: str
    platform: SocialPlatform
    requested_by: str
    requested_at: datetime
    status: PublishStatus
    blockers: tuple[str, ...]
    remote_post_id: str | None = None
    http_status: int | None = None
    publish_authority_used: bool = False
    trading_execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for digest in (self.request_id, self.draft_id):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("publishing receipt identity is invalid")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("publishing receipt timestamp must be timezone-aware")
        if self.status is PublishStatus.PUBLISHED:
            if (
                self.blockers
                or not self.remote_post_id
                or not self.publish_authority_used
            ):
                raise ValueError("published receipt requires remote evidence")
        elif not self.blockers or self.remote_post_id is not None:
            raise ValueError("non-published receipt requires blockers only")
        if self.trading_execution_allowed:
            raise ValueError("social publishing cannot grant trading execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("social publishing cannot change live trading status")

"""Immutable social-account, post, event and contradiction contracts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ai4binance.whale_fusion.models import Provenance, SocialEventType

ZERO = Decimal("0")
ONE = Decimal("1")


class AccountCategory(StrEnum):
    PROJECT_FOUNDER = "PROJECT_FOUNDER"
    FOUNDATION_OR_PROJECT_TEAM = "FOUNDATION_OR_PROJECT_TEAM"
    FUND_MANAGER = "FUND_MANAGER"
    MARKET_MAKER_EXECUTIVE = "MARKET_MAKER_EXECUTIVE"
    KNOWN_WHALE = "KNOWN_WHALE"
    ONCHAIN_ANALYST = "ONCHAIN_ANALYST"
    EXCHANGE = "EXCHANGE"
    REGULATOR = "REGULATOR"
    SECURITY_RESEARCHER = "SECURITY_RESEARCHER"
    TOKEN_UNLOCK_OR_GOVERNANCE = "TOKEN_UNLOCK_OR_GOVERNANCE"  # noqa: S105  # nosec B105


class SocialPlatform(StrEnum):
    X = "X"
    TELEGRAM = "TELEGRAM"
    REDDIT = "REDDIT"
    OFFICIAL_BLOG = "OFFICIAL_BLOG"
    GOVERNANCE_FORUM = "GOVERNANCE_FORUM"
    OTHER = "OTHER"


class SocialStance(StrEnum):
    SUPPORTIVE = "SUPPORTIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    DENIAL = "DENIAL"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class SocialAccount:
    account_id: str
    platform: SocialPlatform
    handle: str
    category: AccountCategory
    verified: bool
    confidence: Decimal
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.account_id.strip() or not self.handle.strip():
            raise ValueError("social account requires account_id and handle")
        if not ZERO <= self.confidence <= ONE:
            raise ValueError("social account confidence must be within zero and one")


@dataclass(frozen=True, slots=True)
class SocialPost:
    post_id: str
    platform: SocialPlatform
    account_id: str
    timestamp: datetime
    text: str
    event_type: SocialEventType
    stance: SocialStance
    assets: tuple[str, ...]
    source_confidence: Decimal
    provenance: Provenance

    def __post_init__(self) -> None:
        if (
            not self.post_id.strip()
            or not self.account_id.strip()
            or not self.text.strip()
        ):
            raise ValueError("social post requires identity and text")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("social post timestamp must be timezone-aware")
        if not ZERO <= self.source_confidence <= ONE:
            raise ValueError("source confidence must be within zero and one")
        normalized_assets = tuple(
            dict.fromkeys(
                asset.strip().upper() for asset in self.assets if asset.strip()
            )
        )
        object.__setattr__(self, "assets", normalized_assets)


@dataclass(frozen=True, slots=True)
class SocialEvent:
    event_id: str
    post_id: str
    account_id: str
    timestamp: datetime
    event_type: SocialEventType
    stance: SocialStance
    assets: tuple[str, ...]
    confidence: Decimal
    provenance: tuple[Provenance, ...]
    reason_codes: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.post_id.strip() or not self.provenance:
            raise ValueError("social event requires identity and provenance")
        if not ZERO <= self.confidence <= ONE:
            raise ValueError("social event confidence must be within zero and one")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("social events cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class SocialClassification:
    post_id: str
    events: tuple[SocialEvent, ...]
    blockers: tuple[str, ...]
    duplicate: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.post_id.strip() or (self.events and self.blockers):
            raise ValueError("social classification is inconsistent")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("social classification cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class SocialContradiction:
    contradiction_id: str
    asset: str
    first_event_id: str
    second_event_id: str
    detected_at: datetime
    reason_code: str = "OPPOSING_SOCIAL_STANCE"
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.contradiction_id.strip() or not self.asset.strip():
            raise ValueError("social contradiction requires identity and asset")
        if self.detected_at.tzinfo is None or self.detected_at.utcoffset() is None:
            raise ValueError("contradiction timestamp must be timezone-aware")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("social contradiction cannot grant execution authority")

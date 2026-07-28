"""Deterministic social validation, deduplication and contradiction detection."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from ai4binance.whale_fusion.social.models import (
    SocialClassification,
    SocialContradiction,
    SocialEvent,
    SocialPost,
    SocialStance,
)
from ai4binance.whale_fusion.social.registry import SocialAccountRegistry


@dataclass(frozen=True, slots=True)
class SocialIntelligenceEngine:
    registry: SocialAccountRegistry
    maximum_age: timedelta = timedelta(hours=24)
    minimum_confidence: Decimal = Decimal("0.5")
    contradiction_window: timedelta = timedelta(hours=48)

    def __post_init__(self) -> None:
        if self.maximum_age <= timedelta(0) or self.contradiction_window <= timedelta(
            0
        ):
            raise ValueError("social time windows must be positive")
        if not Decimal("0") <= self.minimum_confidence <= Decimal("1"):
            raise ValueError("minimum social confidence must be within zero and one")

    def evaluate(
        self,
        post: SocialPost,
        *,
        as_of: datetime,
        seen_post_ids: frozenset[str] = frozenset(),
    ) -> SocialClassification:
        blockers: list[str] = []
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("social evaluation as_of must be timezone-aware")
        if post.post_id in seen_post_ids:
            return SocialClassification(
                post.post_id, (), ("DUPLICATE_SOCIAL_POST",), duplicate=True
            )
        account = self.registry.get(post.platform, post.account_id)
        if account is None:
            blockers.append("SOCIAL_ACCOUNT_NOT_ALLOWLISTED")
        elif not account.verified:
            blockers.append("SOCIAL_ACCOUNT_UNVERIFIED")
        if post.timestamp > as_of:
            blockers.append("SOCIAL_POST_FROM_FUTURE")
        elif as_of - post.timestamp > self.maximum_age:
            blockers.append("SOCIAL_POST_STALE")
        if not post.assets:
            blockers.append("SOCIAL_ASSET_CONTEXT_MISSING")
        confidence = post.source_confidence * (
            account.confidence if account is not None else Decimal("0")
        )
        if confidence < self.minimum_confidence:
            blockers.append("SOCIAL_CONFIDENCE_BELOW_MINIMUM")
        if blockers:
            return SocialClassification(
                post.post_id, (), tuple(dict.fromkeys(blockers))
            )
        if account is None:
            raise RuntimeError("validated social account unexpectedly missing")
        event = SocialEvent(
            event_id=self._event_id(post),
            post_id=post.post_id,
            account_id=post.account_id,
            timestamp=post.timestamp,
            event_type=post.event_type,
            stance=post.stance,
            assets=post.assets,
            confidence=confidence,
            provenance=(post.provenance, account.provenance),
            reason_codes=("ALLOWLISTED_VERIFIED_ACCOUNT", "EXPLICIT_EVENT_TAG"),
        )
        return SocialClassification(post.post_id, (event,), ())

    def contradictions(
        self, events: tuple[SocialEvent, ...]
    ) -> tuple[SocialContradiction, ...]:
        ordered = sorted(events, key=lambda item: (item.timestamp, item.event_id))
        results: list[SocialContradiction] = []
        seen: set[tuple[str, str, str]] = set()
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                if second.timestamp - first.timestamp > self.contradiction_window:
                    break
                for asset in sorted(set(first.assets) & set(second.assets)):
                    if not self._opposed(first.stance, second.stance):
                        continue
                    key = (asset, first.event_id, second.event_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        SocialContradiction(
                            contradiction_id=self._contradiction_id(*key),
                            asset=asset,
                            first_event_id=first.event_id,
                            second_event_id=second.event_id,
                            detected_at=second.timestamp,
                        )
                    )
        return tuple(results)

    @staticmethod
    def _opposed(first: SocialStance, second: SocialStance) -> bool:
        positive = {SocialStance.SUPPORTIVE}
        negative = {SocialStance.NEGATIVE, SocialStance.DENIAL}
        return (first in positive and second in negative) or (
            first in negative and second in positive
        )

    @staticmethod
    def _event_id(post: SocialPost) -> str:
        payload = f"{post.platform.value}|{post.account_id}|{post.post_id}"
        return "social:" + sha256(payload.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _contradiction_id(asset: str, first_id: str, second_id: str) -> str:
        payload = f"{asset}|{first_id}|{second_id}"
        return "contradiction:" + sha256(payload.encode("utf-8")).hexdigest()[:20]

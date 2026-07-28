"""Strict canonical social payload normalizer for provider adapters."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TypeVar

from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.whale_fusion.models import Provenance, SocialEventType
from ai4binance.whale_fusion.social.models import (
    SocialPlatform,
    SocialPost,
    SocialStance,
)

EnumT = TypeVar("EnumT", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class CanonicalSocialPostNormalizer:
    """Normalize explicit provider output without free-form event inference."""

    def normalize(
        self, payload: Mapping[str, object], *, provenance: Provenance
    ) -> SocialPost:
        return SocialPost(
            post_id=self._text(payload.get("post_id"), "post_id"),
            platform=self._enum(SocialPlatform, payload.get("platform"), "platform"),
            account_id=self._text(payload.get("account_id"), "account_id"),
            timestamp=self._timestamp(payload.get("timestamp")),
            text=self._text(payload.get("text"), "text"),
            event_type=self._enum(
                SocialEventType, payload.get("event_type"), "event_type"
            ),
            stance=self._enum(SocialStance, payload.get("stance"), "stance"),
            assets=self._assets(payload.get("assets", ())),
            source_confidence=self._decimal(
                payload.get("source_confidence"), "source_confidence"
            ),
            provenance=provenance,
        )

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ExchangePayloadError(f"canonical social {name} must be text")
        return value.strip()

    @staticmethod
    def _timestamp(value: object) -> datetime:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExchangePayloadError("canonical social timestamp must be integer")
        return datetime.fromtimestamp(value / 1000, tz=UTC)

    @staticmethod
    def _enum(enum_type: type[EnumT], value: object, name: str) -> EnumT:
        if not isinstance(value, str):
            raise ExchangePayloadError(f"canonical social {name} must be text")
        try:
            return enum_type(value.upper())
        except ValueError:
            raise ExchangePayloadError(f"canonical social {name} is invalid") from None

    @staticmethod
    def _assets(value: object) -> tuple[str, ...]:
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise ExchangePayloadError("canonical social assets must be an array")
        if any(not isinstance(item, str) for item in value):
            raise ExchangePayloadError("canonical social assets must contain strings")
        return tuple(item for item in value if isinstance(item, str))

    @staticmethod
    def _decimal(value: object, name: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ExchangePayloadError(f"canonical social {name} must be decimal")
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            raise ExchangePayloadError(
                f"canonical social {name} must be decimal"
            ) from None
        if not parsed.is_finite():
            raise ExchangePayloadError(f"canonical social {name} must be finite")
        return parsed

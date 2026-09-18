"""Immutable platform-aware social account registry."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ai4binance.whale_fusion.social.models import SocialAccount, SocialPlatform


@dataclass(frozen=True, slots=True)
class SocialAccountRegistry:
    accounts: tuple[SocialAccount, ...]
    _by_key: Mapping[tuple[SocialPlatform, str], SocialAccount] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        indexed: dict[tuple[SocialPlatform, str], SocialAccount] = {}
        for account in self.accounts:
            key = (account.platform, account.account_id.strip().lower())
            if key in indexed:
                raise ValueError("social accounts must be unique per platform")
            indexed[key] = account
        object.__setattr__(self, "_by_key", MappingProxyType(indexed))

    @classmethod
    def from_accounts(
        cls, accounts: Iterable[SocialAccount]
    ) -> "SocialAccountRegistry":
        return cls(tuple(accounts))

    def get(self, platform: SocialPlatform, account_id: str) -> SocialAccount | None:
        return self._by_key.get((platform, account_id.strip().lower()))

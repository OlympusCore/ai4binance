"""Immutable chain-aware wallet label registry."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ai4binance.whale_fusion.onchain.models import (
    AddressRole,
    Chain,
    WalletLabel,
)


@dataclass(frozen=True, slots=True)
class WalletRegistry:
    labels: tuple[WalletLabel, ...]
    _by_key: Mapping[tuple[Chain, str], WalletLabel] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        indexed: dict[tuple[Chain, str], WalletLabel] = {}
        for label in self.labels:
            key = (label.chain, label.address)
            if key in indexed:
                raise ValueError("wallet registry labels must be unique per chain")
            indexed[key] = label
        object.__setattr__(self, "_by_key", MappingProxyType(indexed))

    @classmethod
    def from_labels(cls, labels: Iterable[WalletLabel]) -> "WalletRegistry":
        return cls(tuple(labels))

    def get(self, chain: Chain, address: str) -> WalletLabel | None:
        return self._by_key.get((chain, address.strip().lower()))

    def role(self, chain: Chain, address: str) -> AddressRole:
        label = self.get(chain, address)
        return label.role if label is not None else AddressRole.UNKNOWN

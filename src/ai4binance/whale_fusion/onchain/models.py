"""Immutable contracts for normalized on-chain transfers and whale events."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from ai4binance.whale_fusion.models import Provenance, WhaleEventType

ZERO = Decimal("0")
ONE = Decimal("1")


class Chain(StrEnum):
    ETHEREUM = "ETHEREUM"
    BNB_SMART_CHAIN = "BNB_SMART_CHAIN"
    ARBITRUM = "ARBITRUM"
    OPTIMISM = "OPTIMISM"
    BASE = "BASE"
    POLYGON = "POLYGON"
    SOLANA = "SOLANA"
    OTHER = "OTHER"


class AddressRole(StrEnum):
    WHALE = "WHALE"
    BINANCE = "BINANCE"
    OTHER_EXCHANGE = "OTHER_EXCHANGE"
    DEX = "DEX"
    BRIDGE = "BRIDGE"
    STAKING = "STAKING"
    TOKEN_UNLOCK = "TOKEN_UNLOCK"  # noqa: S105  # nosec B105
    MARKET_MAKER = "MARKET_MAKER"
    PROJECT_TREASURY = "PROJECT_TREASURY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class WalletLabel:
    chain: Chain
    address: str
    label: str
    role: AddressRole
    confidence: Decimal
    provenance: Provenance

    def __post_init__(self) -> None:
        address = self.address.strip().lower()
        if not address or not self.label.strip():
            raise ValueError("wallet label requires address and label")
        if not ZERO <= self.confidence <= ONE:
            raise ValueError("wallet label confidence must be within zero and one")
        object.__setattr__(self, "address", address)


@dataclass(frozen=True, slots=True)
class OnChainTransfer:
    transfer_id: str
    chain: Chain
    timestamp: datetime
    tx_hash: str
    from_address: str
    to_address: str
    asset: str
    amount: Decimal
    usd_value: Decimal | None
    provenance: Provenance
    is_stablecoin: bool = False
    from_is_new_wallet: bool = False
    to_is_new_wallet: bool = False
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("transfer timestamp must be timezone-aware")
        if not self.transfer_id.strip() or not self.tx_hash.strip():
            raise ValueError("transfer requires transfer_id and tx_hash")
        if not self.from_address.strip() or not self.to_address.strip():
            raise ValueError("transfer requires source and destination addresses")
        if not self.asset.strip() or self.amount <= ZERO:
            raise ValueError("transfer asset and positive amount are required")
        if self.usd_value is not None and self.usd_value < ZERO:
            raise ValueError("transfer usd_value cannot be negative")
        object.__setattr__(self, "from_address", self.from_address.strip().lower())
        object.__setattr__(self, "to_address", self.to_address.strip().lower())
        object.__setattr__(self, "asset", self.asset.strip().upper())
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True, slots=True)
class WhaleEvent:
    event_id: str
    event_type: WhaleEventType
    chain: Chain
    timestamp: datetime
    asset: str
    amount: Decimal
    usd_value: Decimal
    transfer_ids: tuple[str, ...]
    confidence: Decimal
    provenance: tuple[Provenance, ...]
    reason_codes: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.transfer_ids or not self.provenance:
            raise ValueError("whale event requires identity, transfers and provenance")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("whale event timestamp must be timezone-aware")
        if self.amount <= ZERO or self.usd_value < ZERO:
            raise ValueError("whale event amounts are invalid")
        if not ZERO <= self.confidence <= ONE:
            raise ValueError("whale event confidence must be within zero and one")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("on-chain events cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class OnChainClassification:
    transfer_id: str
    events: tuple[WhaleEvent, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.transfer_id.strip():
            raise ValueError("classification transfer_id cannot be empty")
        if self.events and self.blockers:
            raise ValueError("classified events cannot contain blockers")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("on-chain classification cannot grant execution authority")

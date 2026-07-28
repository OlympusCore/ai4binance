"""Deterministic wallet-role classification and split-transfer detection."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256

from ai4binance.whale_fusion.models import WhaleEventType
from ai4binance.whale_fusion.onchain.models import (
    AddressRole,
    OnChainClassification,
    OnChainTransfer,
    WhaleEvent,
)
from ai4binance.whale_fusion.onchain.registry import WalletRegistry


@dataclass(frozen=True, slots=True)
class OnChainClassifierConfig:
    minimum_whale_usd: Decimal = Decimal("1000000")
    split_minimum_count: int = 3
    split_window: timedelta = timedelta(minutes=30)

    def __post_init__(self) -> None:
        if self.minimum_whale_usd <= Decimal("0"):
            raise ValueError("minimum_whale_usd must be positive")
        if self.split_minimum_count < 2 or self.split_window <= timedelta(0):
            raise ValueError("split-transfer configuration is invalid")


@dataclass(frozen=True, slots=True)
class OnChainClassifier:
    registry: WalletRegistry
    config: OnChainClassifierConfig = OnChainClassifierConfig()

    def classify(self, transfer: OnChainTransfer) -> tuple[WhaleEvent, ...]:
        """Classify one transfer, returning no event when evidence is insufficient."""
        return self.evaluate(transfer).events

    def evaluate(self, transfer: OnChainTransfer) -> OnChainClassification:
        """Return events or explicit audit blockers for one transfer."""
        if transfer.usd_value is None:
            return OnChainClassification(
                transfer.transfer_id, (), ("USD_VALUE_UNKNOWN",)
            )
        if transfer.usd_value < self.config.minimum_whale_usd:
            return OnChainClassification(
                transfer.transfer_id, (), ("BELOW_WHALE_THRESHOLD",)
            )
        source = self.registry.role(transfer.chain, transfer.from_address)
        target = self.registry.role(transfer.chain, transfer.to_address)
        event_type, reason = self._primary_event(transfer, source, target)
        events = [self._event(event_type, transfer, reason)]
        if transfer.from_is_new_wallet or transfer.to_is_new_wallet:
            events.append(
                self._event(WhaleEventType.NEW_WALLET, transfer, "NEW_WALLET_FLAG")
            )
        return OnChainClassification(transfer.transfer_id, tuple(events), ())

    def detect_split_transfers(
        self, transfers: tuple[OnChainTransfer, ...]
    ) -> tuple[WhaleEvent, ...]:
        """Detect same-source, same-asset whale transfers fragmented in time."""
        grouped: dict[tuple[object, str, str], list[OnChainTransfer]] = defaultdict(
            list
        )
        for transfer in sorted(transfers, key=lambda item: item.timestamp):
            grouped[(transfer.chain, transfer.from_address, transfer.asset)].append(
                transfer
            )
        events: list[WhaleEvent] = []
        for group in grouped.values():
            for start in range(len(group)):
                window = tuple(
                    item
                    for item in group[start:]
                    if item.timestamp - group[start].timestamp
                    <= self.config.split_window
                )
                if len(window) < self.config.split_minimum_count:
                    continue
                if any(item.usd_value is None for item in window):
                    continue
                total_usd = sum(
                    (item.usd_value or Decimal("0") for item in window), Decimal("0")
                )
                if total_usd < self.config.minimum_whale_usd:
                    continue
                events.append(self._split_event(window, total_usd))
                break
        return tuple(events)

    @staticmethod
    def _primary_event(
        transfer: OnChainTransfer,
        source: AddressRole,
        target: AddressRole,
    ) -> tuple[WhaleEventType, str]:
        if source is AddressRole.TOKEN_UNLOCK:
            return WhaleEventType.TOKEN_UNLOCK_MOVEMENT, "TOKEN_UNLOCK_SOURCE"
        if source is AddressRole.STAKING:
            return WhaleEventType.STAKING_EXIT, "STAKING_SOURCE"
        if AddressRole.BRIDGE in {source, target}:
            return WhaleEventType.BRIDGE_TRANSFER, "BRIDGE_ADDRESS_MATCH"
        if AddressRole.MARKET_MAKER in {source, target}:
            return WhaleEventType.MARKET_MAKER_MOVEMENT, "MARKET_MAKER_ADDRESS_MATCH"
        if target is AddressRole.BINANCE:
            if transfer.is_stablecoin:
                return (
                    WhaleEventType.STABLECOIN_EXCHANGE_DEPOSIT,
                    "STABLECOIN_TO_BINANCE",
                )
            return WhaleEventType.WHALE_TO_BINANCE, "DESTINATION_BINANCE"
        if source is AddressRole.BINANCE:
            return WhaleEventType.BINANCE_TO_WHALE, "SOURCE_BINANCE"
        if target is AddressRole.DEX:
            return WhaleEventType.WHALE_TO_DEX, "DESTINATION_DEX"
        if transfer.is_stablecoin and target is AddressRole.WHALE:
            return WhaleEventType.STABLECOIN_ACCUMULATION, "STABLECOIN_TO_WHALE"
        if target in {AddressRole.WHALE, AddressRole.PROJECT_TREASURY}:
            return WhaleEventType.TOKEN_ACCUMULATION, "TOKEN_TO_TRACKED_WALLET"
        return WhaleEventType.TOKEN_DISTRIBUTION, "LARGE_UNCLASSIFIED_DISTRIBUTION"

    def _event(
        self,
        event_type: WhaleEventType,
        transfer: OnChainTransfer,
        reason: str,
    ) -> WhaleEvent:
        usd_value = transfer.usd_value
        if usd_value is None:
            raise ValueError("classified transfer must have usd_value")
        return WhaleEvent(
            event_id=self._event_id(event_type, (transfer.transfer_id,)),
            event_type=event_type,
            chain=transfer.chain,
            timestamp=transfer.timestamp,
            asset=transfer.asset,
            amount=transfer.amount,
            usd_value=usd_value,
            transfer_ids=(transfer.transfer_id,),
            confidence=Decimal("0.8"),
            provenance=(transfer.provenance,),
            reason_codes=(reason,),
        )

    def _split_event(
        self, transfers: tuple[OnChainTransfer, ...], total_usd: Decimal
    ) -> WhaleEvent:
        first = transfers[0]
        transfer_ids = tuple(item.transfer_id for item in transfers)
        return WhaleEvent(
            event_id=self._event_id(WhaleEventType.SPLIT_TRANSFER, transfer_ids),
            event_type=WhaleEventType.SPLIT_TRANSFER,
            chain=first.chain,
            timestamp=transfers[-1].timestamp,
            asset=first.asset,
            amount=sum((item.amount for item in transfers), Decimal("0")),
            usd_value=total_usd,
            transfer_ids=transfer_ids,
            confidence=Decimal("0.7"),
            provenance=tuple(item.provenance for item in transfers),
            reason_codes=("SAME_SOURCE_ASSET_TIME_CLUSTER",),
        )

    @staticmethod
    def _event_id(event_type: WhaleEventType, transfer_ids: tuple[str, ...]) -> str:
        payload = f"{event_type.value}|{'|'.join(transfer_ids)}"
        return "whale:" + sha256(payload.encode("utf-8")).hexdigest()[:20]

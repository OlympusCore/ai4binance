"""Snapshot-bound WHALE-FUSION envelope and immutable attachment adapter."""

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from ai4binance.reporting import to_primitive
from ai4binance.schemas import MarketSnapshot
from ai4binance.whale_fusion.fusion import FusionResult


@dataclass(frozen=True, slots=True)
class WhaleFusionEnvelope:
    snapshot_id: str
    symbol: str
    result: FusionResult

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()
        if not self.snapshot_id.strip():
            raise ValueError("fusion envelope snapshot_id cannot be empty")
        if normalized_symbol != self.result.symbol:
            raise ValueError("fusion envelope and result symbols must match")
        object.__setattr__(self, "symbol", normalized_symbol)

    def to_mapping(self) -> MappingProxyType[str, object]:
        primitive = to_primitive(self.result)
        if not isinstance(primitive, dict):
            raise TypeError("fusion result serialization must produce an object")
        return MappingProxyType(
            {
                "snapshot_id": self.snapshot_id,
                "symbol": self.symbol,
                **cast(dict[str, object], primitive),
            }
        )


def attach_fusion_result(
    snapshot: MarketSnapshot, envelope: WhaleFusionEnvelope
) -> MarketSnapshot:
    """Return a new immutable snapshot carrying snapshot-consistent fusion data."""
    if envelope.snapshot_id != snapshot.snapshot_id:
        raise ValueError("fusion envelope and market snapshot IDs must match")
    if envelope.symbol != snapshot.symbol:
        raise ValueError("fusion envelope and market snapshot symbols must match")
    if envelope.result.as_of > snapshot.created_at:
        raise ValueError("fusion result cannot be newer than market snapshot")
    onchain = dict(snapshot.onchain_snapshot)
    onchain["whale_fusion"] = dict(envelope.to_mapping())
    return replace(snapshot, onchain_snapshot=onchain)

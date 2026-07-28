"""Strict normalizer for provider adapters emitting the canonical transfer schema."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.whale_fusion.models import Provenance
from ai4binance.whale_fusion.onchain.models import Chain, OnChainTransfer


@dataclass(frozen=True, slots=True)
class CanonicalTransferNormalizer:
    """Normalize an adapter payload; does not call arbitrary provider URLs."""

    stablecoins: frozenset[str] = frozenset(
        {"USDT", "USDC", "FDUSD", "DAI", "TUSD", "USDE"}
    )

    def normalize(
        self,
        payload: Mapping[str, object],
        *,
        provenance: Provenance,
    ) -> OnChainTransfer:
        chain_raw = self._text(payload.get("chain"), "chain").upper()
        try:
            chain = Chain(chain_raw)
        except ValueError:
            chain = Chain.OTHER
        asset = self._text(payload.get("asset"), "asset").upper()
        return OnChainTransfer(
            transfer_id=self._text(payload.get("transfer_id"), "transfer_id"),
            chain=chain,
            timestamp=self._timestamp(payload.get("timestamp")),
            tx_hash=self._text(payload.get("tx_hash"), "tx_hash"),
            from_address=self._text(payload.get("from_address"), "from_address"),
            to_address=self._text(payload.get("to_address"), "to_address"),
            asset=asset,
            amount=self._decimal(payload.get("amount"), "amount"),
            usd_value=self._optional_decimal(payload.get("usd_value"), "usd_value"),
            provenance=provenance,
            is_stablecoin=asset in self.stablecoins,
            from_is_new_wallet=self._boolean(
                payload.get("from_is_new_wallet", False), "from_is_new_wallet"
            ),
            to_is_new_wallet=self._boolean(
                payload.get("to_is_new_wallet", False), "to_is_new_wallet"
            ),
            attributes=self._attributes(payload.get("attributes", {})),
        )

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ExchangePayloadError(f"canonical transfer {name} must be text")
        return value.strip()

    @staticmethod
    def _timestamp(value: object) -> datetime:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExchangePayloadError("canonical transfer timestamp must be integer")
        return datetime.fromtimestamp(value / 1000, tz=UTC)

    @staticmethod
    def _decimal(value: object, name: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ExchangePayloadError(f"canonical transfer {name} must be decimal")
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            raise ExchangePayloadError(
                f"canonical transfer {name} must be decimal"
            ) from None
        if not parsed.is_finite():
            raise ExchangePayloadError(f"canonical transfer {name} must be finite")
        return parsed

    @classmethod
    def _optional_decimal(cls, value: object, name: str) -> Decimal | None:
        return None if value is None else cls._decimal(value, name)

    @staticmethod
    def _boolean(value: object, name: str) -> bool:
        if not isinstance(value, bool):
            raise ExchangePayloadError(f"canonical transfer {name} must be boolean")
        return value

    @staticmethod
    def _attributes(value: object) -> Mapping[str, str]:
        if not isinstance(value, Mapping):
            raise ExchangePayloadError(
                "canonical transfer attributes must be an object"
            )
        raw = cast(Mapping[object, object], value)
        if any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in raw.items()
        ):
            raise ExchangePayloadError("canonical transfer attributes must be strings")
        return cast(Mapping[str, str], raw)

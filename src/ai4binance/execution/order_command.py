"""Canonical immutable Spot order command contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SpotOrderCommand:
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    client_order_id: str
    price: Decimal | None = None
    time_in_force: str | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        side = self.side.strip().upper()
        order_type = self.order_type.strip().upper()
        client_id = self.client_order_id.strip()
        if not symbol.isascii() or not symbol.isalnum():
            raise ValueError("order symbol must be ASCII alphanumeric")
        if side not in {"BUY", "SELL"} or order_type not in {"LIMIT", "MARKET"}:
            raise ValueError("unsupported Spot order side or type")
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("order quantity must be finite and positive")
        if not client_id or len(client_id) > 36 or not client_id.isascii():
            raise ValueError("client order ID is invalid")
        if order_type == "LIMIT" and (
            self.price is None
            or not self.price.is_finite()
            or self.price <= 0
            or self.time_in_force not in {"GTC", "IOC", "FOK"}
        ):
            raise ValueError("LIMIT order requires valid price and time-in-force")
        if order_type == "MARKET" and (
            self.price is not None or self.time_in_force is not None
        ):
            raise ValueError("MARKET order cannot contain price or time-in-force")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "order_type", order_type)
        object.__setattr__(self, "client_order_id", client_id)

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "quantity": str(self.quantity),
            "newClientOrderId": self.client_order_id,
            "newOrderRespType": "FULL",
        }
        if self.price is not None:
            payload["price"] = str(self.price)
        if self.time_in_force is not None:
            payload["timeInForce"] = self.time_in_force
        return payload

    @property
    def preview_hash(self) -> str:
        encoded = json.dumps(
            self.payload(), separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


__all__ = ("SpotOrderCommand",)

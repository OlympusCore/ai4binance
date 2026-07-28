"""Normalized read-only exchange open orders for management review."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class AccountOpenOrder:
    market: str
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    price: Decimal
    original_quantity: Decimal
    executed_quantity: Decimal

    def __post_init__(self) -> None:
        if self.market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError("open-order market is invalid")
        identities = (
            self.order_id,
            self.client_order_id,
            self.symbol,
            self.side,
            self.order_type,
            self.status,
        )
        if any(not value.strip() for value in identities):
            raise ValueError("open-order identity is required")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("open-order side is invalid")
        values = (self.price, self.original_quantity, self.executed_quantity)
        if min(values) < 0 or self.executed_quantity > self.original_quantity:
            raise ValueError("open-order quantities are invalid")

    @property
    def remaining_quantity(self) -> Decimal:
        return self.original_quantity - self.executed_quantity


def normalize_open_order(
    payload: Mapping[str, object], *, market: str
) -> AccountOpenOrder:
    """Normalize Spot or USD-M order payload without exposing mutation methods."""
    return AccountOpenOrder(
        market=market,
        order_id=_text(payload.get("orderId"), "orderId"),
        client_order_id=_text(payload.get("clientOrderId"), "clientOrderId"),
        symbol=_text(payload.get("symbol"), "symbol").upper(),
        side=_text(payload.get("side"), "side").upper(),
        order_type=_text(payload.get("type"), "type").upper(),
        status=_text(payload.get("status"), "status").upper(),
        price=_decimal(payload.get("price"), "price"),
        original_quantity=_decimal(payload.get("origQty"), "origQty"),
        executed_quantity=_decimal(payload.get("executedQty"), "executedQty"),
    )


def _text(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be text-compatible")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} cannot be empty")
    return normalized


def _decimal(value: object, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be decimal-compatible") from None
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed

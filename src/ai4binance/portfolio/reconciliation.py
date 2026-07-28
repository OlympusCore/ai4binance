"""Read-only local/exchange open-order reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OpenOrderView:
    client_order_id: str
    symbol: str
    remaining_quantity: Decimal

    def __post_init__(self) -> None:
        if not self.client_order_id.strip() or not self.symbol.strip():
            raise ValueError("open-order identity is required")
        if self.remaining_quantity <= 0:
            raise ValueError("open-order remaining quantity must be positive")


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    local_count: int
    exchange_count: int
    missing_on_exchange: tuple[str, ...]
    unknown_on_exchange: tuple[str, ...]
    quantity_mismatches: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if min(self.local_count, self.exchange_count) < 0:
            raise ValueError("reconciliation counts cannot be negative")
        if self.execution_allowed:
            raise ValueError("reconciliation cannot authorize execution")


def reconcile_open_orders(
    local_orders: tuple[OpenOrderView, ...],
    exchange_orders: tuple[OpenOrderView, ...],
) -> ReconciliationReport:
    """Compare explicit client-order identities without mutating either side."""
    local = _index(local_orders, "local")
    exchange = _index(exchange_orders, "exchange")
    missing = tuple(sorted(set(local) - set(exchange)))
    unknown = tuple(sorted(set(exchange) - set(local)))
    mismatches = tuple(
        sorted(
            order_id
            for order_id in set(local) & set(exchange)
            if local[order_id].symbol.upper() != exchange[order_id].symbol.upper()
            or local[order_id].remaining_quantity
            != exchange[order_id].remaining_quantity
        )
    )
    blockers: list[str] = []
    if missing:
        blockers.append("LOCAL_ORDER_MISSING_ON_EXCHANGE")
    if unknown:
        blockers.append("UNKNOWN_EXCHANGE_OPEN_ORDER")
    if mismatches:
        blockers.append("OPEN_ORDER_STATE_MISMATCH")
    return ReconciliationReport(
        len(local),
        len(exchange),
        missing,
        unknown,
        mismatches,
        tuple(blockers),
    )


def _index(orders: tuple[OpenOrderView, ...], source: str) -> dict[str, OpenOrderView]:
    indexed = {item.client_order_id: item for item in orders}
    if len(indexed) != len(orders):
        raise ValueError(f"{source} open orders must have unique identities")
    return indexed

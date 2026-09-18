"""Conservative aggregate-trade queue and partial-fill replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from ai4binance.data.aggtrades import AggregateTrade
from ai4binance.exchange.order_book import BookLevel


class RestingSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class QueueFillRequest:
    side: RestingSide
    limit_price: Decimal
    quantity: Decimal
    accepted_at: datetime

    def __post_init__(self) -> None:
        if self.limit_price <= 0 or self.quantity <= 0:
            raise ValueError("queue fill request values must be positive")
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() is None:
            raise ValueError("queue fill request timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class QueueFillReport:
    requested_quantity: Decimal
    initial_queue_ahead: Decimal
    consumed_queue_ahead: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    fill_ratio: Decimal
    first_fill_at: datetime | None
    last_fill_at: datetime | None
    blockers: tuple[str, ...]
    model_name: str = "RISK_ADVERSE_AGGTRADE_QUEUE"
    status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.filled_quantity > self.requested_quantity:
            raise ValueError("queue fill cannot exceed requested quantity")
        if self.remaining_quantity != self.requested_quantity - self.filled_quantity:
            raise ValueError("queue fill remaining quantity is inconsistent")
        if self.execution_allowed or self.status != "RESEARCH_ONLY":
            raise ValueError("queue fill replay cannot grant execution authority")


def replay_conservative_queue_fill(
    request: QueueFillRequest,
    *,
    initial_levels: tuple[BookLevel, ...],
    trades: tuple[AggregateTrade, ...],
) -> QueueFillReport:
    """Consume visible queue first; cancellations never improve our position."""
    if len({item.price for item in initial_levels}) != len(initial_levels):
        raise ValueError("initial queue levels must have unique prices")
    queue_ahead = next(
        (item.quantity for item in initial_levels if item.price == request.limit_price),
        Decimal("0"),
    )
    has_gap = any(
        right.aggregate_trade_id != left.aggregate_trade_id + 1
        for left, right in pairwise(trades)
    )
    if has_gap:
        return _report(
            request,
            queue_ahead,
            Decimal("0"),
            Decimal("0"),
            (),
            ("AGGREGATE_TRADE_SEQUENCE_GAP",),
        )
    relevant: list[AggregateTrade] = []
    for trade in trades:
        if trade.timestamp < request.accepted_at:
            continue
        consumes_side = (
            request.side is RestingSide.BUY
            and trade.buyer_is_maker
            and trade.price <= request.limit_price
        ) or (
            request.side is RestingSide.SELL
            and not trade.buyer_is_maker
            and trade.price >= request.limit_price
        )
        if consumes_side:
            relevant.append(trade)

    remaining_queue = queue_ahead
    remaining_order = request.quantity
    fill_times: list[datetime] = []
    for trade in relevant:
        available = trade.quantity
        consumed = min(remaining_queue, available)
        remaining_queue -= consumed
        available -= consumed
        if available > 0 and remaining_queue == 0 and remaining_order > 0:
            filled = min(remaining_order, available)
            remaining_order -= filled
            fill_times.append(trade.timestamp)
        if remaining_order == 0:
            break
    filled_quantity = request.quantity - remaining_order
    blockers: list[str] = []
    if not relevant:
        blockers.append("NO_MARKETABLE_AGGREGATE_TRADES")
    if filled_quantity < request.quantity:
        blockers.append("ORDER_NOT_FULLY_FILLED")
    return _report(
        request,
        queue_ahead,
        queue_ahead - remaining_queue,
        filled_quantity,
        tuple(fill_times),
        tuple(blockers),
    )


def _report(
    request: QueueFillRequest,
    initial_queue: Decimal,
    consumed_queue: Decimal,
    filled: Decimal,
    fill_times: tuple[datetime, ...],
    blockers: tuple[str, ...],
) -> QueueFillReport:
    return QueueFillReport(
        requested_quantity=request.quantity,
        initial_queue_ahead=initial_queue,
        consumed_queue_ahead=consumed_queue,
        filled_quantity=filled,
        remaining_quantity=request.quantity - filled,
        fill_ratio=filled / request.quantity,
        first_fill_at=fill_times[0] if fill_times else None,
        last_fill_at=fill_times[-1] if fill_times else None,
        blockers=blockers,
    )

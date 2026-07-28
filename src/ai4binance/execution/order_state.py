"""Deterministic Spot order state reduction with partial-fill support."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from ai4binance.domain import Action
from ai4binance.events import DomainEvent

ZERO = Decimal("0")


class OrderStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class OrderState:
    """Replayable aggregate state; it has no exchange write authority."""

    order_id: str
    symbol: str
    action: Action
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_fill_price: Decimal
    status: OrderStatus
    last_sequence: int

    @property
    def remaining_quantity(self) -> Decimal:
        return self.requested_quantity - self.filled_quantity


class OrderStateMachine:
    """Reduce canonical order events using explicit legal transitions."""

    @classmethod
    def replay(cls, events: tuple[DomainEvent, ...]) -> OrderState:
        if not events:
            raise ValueError("order replay requires events")
        state: OrderState | None = None
        for event in events:
            state = cls.apply(state, event)
        if state is None:
            raise RuntimeError("order replay did not produce state")
        return state

    @classmethod
    def apply(cls, state: OrderState | None, event: DomainEvent) -> OrderState:
        payload = event.payload_dict()
        if state is None:
            if event.event_type != "ORDER_SUBMITTED":
                raise ValueError("first order event must be ORDER_SUBMITTED")
            quantity = cls._positive_decimal(payload.get("quantity"), "quantity")
            try:
                action = Action(payload.get("action", ""))
            except ValueError:
                raise ValueError("order action is invalid") from None
            symbol = payload.get("symbol", "").strip().upper()
            if not symbol:
                raise ValueError("order symbol is required")
            return OrderState(
                order_id=event.aggregate_id,
                symbol=symbol,
                action=action,
                requested_quantity=quantity,
                filled_quantity=ZERO,
                average_fill_price=ZERO,
                status=OrderStatus.SUBMITTED,
                last_sequence=event.sequence,
            )
        cls._validate_identity_and_sequence(state, event)
        if event.event_type == "ORDER_ACCEPTED":
            cls._require_status(state, {OrderStatus.SUBMITTED})
            return cls._with_status(state, OrderStatus.ACCEPTED, event.sequence)
        if event.event_type == "ORDER_REJECTED":
            cls._require_status(state, {OrderStatus.SUBMITTED})
            return cls._with_status(state, OrderStatus.REJECTED, event.sequence)
        if event.event_type == "ORDER_CANCELLED":
            cls._require_status(
                state,
                {
                    OrderStatus.SUBMITTED,
                    OrderStatus.ACCEPTED,
                    OrderStatus.PARTIALLY_FILLED,
                    OrderStatus.PENDING_CANCEL,
                },
            )
            return cls._with_status(state, OrderStatus.CANCELLED, event.sequence)
        if event.event_type == "ORDER_CANCEL_REQUESTED":
            cls._require_status(
                state,
                {OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED},
            )
            return cls._with_status(state, OrderStatus.PENDING_CANCEL, event.sequence)
        if event.event_type in {"ORDER_PARTIALLY_FILLED", "ORDER_FILLED"}:
            return cls._apply_fill(state, event, payload)
        raise ValueError("unsupported order event type")

    @classmethod
    def _apply_fill(
        cls, state: OrderState, event: DomainEvent, payload: dict[str, str]
    ) -> OrderState:
        cls._require_status(
            state,
            {
                OrderStatus.ACCEPTED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.PENDING_CANCEL,
            },
        )
        quantity = cls._positive_decimal(payload.get("fill_quantity"), "fill_quantity")
        price = cls._positive_decimal(payload.get("fill_price"), "fill_price")
        new_quantity = state.filled_quantity + quantity
        if new_quantity > state.requested_quantity:
            raise ValueError("order fill exceeds requested quantity")
        is_complete = new_quantity == state.requested_quantity
        if (event.event_type == "ORDER_FILLED") != is_complete:
            raise ValueError("fill event type and cumulative quantity disagree")
        previous_value = state.average_fill_price * state.filled_quantity
        average = (previous_value + price * quantity) / new_quantity
        return OrderState(
            order_id=state.order_id,
            symbol=state.symbol,
            action=state.action,
            requested_quantity=state.requested_quantity,
            filled_quantity=new_quantity,
            average_fill_price=average,
            status=(
                OrderStatus.FILLED if is_complete else OrderStatus.PARTIALLY_FILLED
            ),
            last_sequence=event.sequence,
        )

    @staticmethod
    def _with_status(
        state: OrderState, status: OrderStatus, sequence: int
    ) -> OrderState:
        return OrderState(
            order_id=state.order_id,
            symbol=state.symbol,
            action=state.action,
            requested_quantity=state.requested_quantity,
            filled_quantity=state.filled_quantity,
            average_fill_price=state.average_fill_price,
            status=status,
            last_sequence=sequence,
        )

    @staticmethod
    def _validate_identity_and_sequence(state: OrderState, event: DomainEvent) -> None:
        if event.aggregate_id != state.order_id:
            raise ValueError("order event aggregate identity mismatch")
        if event.sequence != state.last_sequence + 1:
            raise ValueError("order event sequence is not contiguous")

    @staticmethod
    def _require_status(state: OrderState, allowed: set[OrderStatus]) -> None:
        if state.status not in allowed:
            raise ValueError("illegal order state transition")

    @staticmethod
    def _positive_decimal(value: str | None, name: str) -> Decimal:
        try:
            parsed = Decimal(value or "")
        except InvalidOperation:
            raise ValueError(f"{name} must be decimal-compatible") from None
        if not parsed.is_finite() or parsed <= ZERO:
            raise ValueError(f"{name} must be positive")
        return parsed

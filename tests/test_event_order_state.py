"""Deterministic event journal and partial-fill order state tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.events import (
    DeterministicEventBus,
    DomainEvent,
    SimulatedClock,
    SystemClock,
)
from ai4binance.execution.order_state import OrderStateMachine, OrderStatus

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def event(
    sequence: int,
    event_type: str,
    payload: tuple[tuple[str, str], ...] = (),
    *,
    previous_hash: str = "GENESIS",
) -> DomainEvent:
    return DomainEvent.create(
        event_id=f"event-{sequence}",
        aggregate_id="order-1",
        event_type=event_type,
        sequence=sequence,
        occurred_at=NOW + timedelta(seconds=sequence),
        payload=payload,
        previous_hash=previous_hash,
    )


def order_events() -> tuple[DomainEvent, ...]:
    submitted = event(
        1,
        "ORDER_SUBMITTED",
        (("symbol", "HOTUSDT"), ("action", "BUY"), ("quantity", "2")),
    )
    accepted = event(2, "ORDER_ACCEPTED", previous_hash=submitted.event_hash)
    partial = event(
        3,
        "ORDER_PARTIALLY_FILLED",
        (("fill_quantity", "0.5"), ("fill_price", "100")),
        previous_hash=accepted.event_hash,
    )
    filled = event(
        4,
        "ORDER_FILLED",
        (("fill_quantity", "1.5"), ("fill_price", "102")),
        previous_hash=partial.event_hash,
    )
    return submitted, accepted, partial, filled


def test_event_bus_validates_hash_sequence_and_replays_deterministically() -> None:
    observed: list[str] = []
    bus = DeterministicEventBus()
    bus.subscribe(lambda item: observed.append(item.event_id))
    bus.replay(order_events())

    assert observed == ["event-1", "event-2", "event-3", "event-4"]
    assert bus.snapshot() == order_events()
    with pytest.raises(ValueError, match="duplicate"):
        bus.publish(order_events()[-1])


def test_order_state_replay_handles_partial_fill_and_weighted_price() -> None:
    state = OrderStateMachine.replay(order_events())
    assert state.status is OrderStatus.FILLED
    assert state.filled_quantity == Decimal("2.0")
    assert state.remaining_quantity == Decimal("0.0")
    assert state.average_fill_price == Decimal("101.5")


def test_order_state_replay_binds_transition_reducer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding_count = 0
    original_apply = OrderStateMachine.apply

    class CountingApplyDescriptor:
        def __get__(
            self,
            instance: object,
            owner: type[OrderStateMachine],
        ) -> object:
            nonlocal binding_count
            binding_count += 1
            return original_apply

    monkeypatch.setattr(OrderStateMachine, "apply", CountingApplyDescriptor())

    state = OrderStateMachine.replay(order_events())

    assert state.status is OrderStatus.FILLED
    assert binding_count == 1


def test_order_state_rejects_illegal_or_excessive_fill() -> None:
    submitted, accepted, _partial, _filled = order_events()
    with pytest.raises(ValueError, match="first order event"):
        OrderStateMachine.replay((accepted,))
    state = OrderStateMachine.replay((submitted, accepted))
    excessive = event(
        3,
        "ORDER_FILLED",
        (("fill_quantity", "3"), ("fill_price", "100")),
        previous_hash=accepted.event_hash,
    )
    with pytest.raises(ValueError, match="exceeds"):
        OrderStateMachine.apply(state, excessive)
    with pytest.raises(ValueError, match="illegal"):
        OrderStateMachine.apply(
            OrderStateMachine.apply(state, event(3, "ORDER_CANCELLED")),
            event(4, "ORDER_ACCEPTED"),
        )


def test_simulated_clock_is_monotonic() -> None:
    clock = SimulatedClock(NOW)
    assert clock.advance(timedelta(seconds=1)) == NOW + timedelta(seconds=1)
    with pytest.raises(ValueError, match="backwards"):
        clock.set(NOW)
    with pytest.raises(ValueError, match="positive"):
        clock.advance(timedelta(0))


def test_event_contract_rejects_tampering_and_broken_chain() -> None:
    first = order_events()[0]
    with pytest.raises(ValueError, match="content hash"):
        DomainEvent(
            first.event_id,
            first.aggregate_id,
            first.event_type,
            first.sequence,
            first.occurred_at,
            first.payload,
            first.previous_hash,
            "bad",
        )
    bus = DeterministicEventBus()
    bus.publish(first)
    with pytest.raises(ValueError, match="hash chain"):
        bus.publish(event(2, "ORDER_ACCEPTED", previous_hash="wrong"))


def test_event_bus_rejects_capacity_sequence_time_and_duplicate_subscriber() -> None:
    bus = DeterministicEventBus(capacity=1)

    def subscriber(_item: DomainEvent) -> None:
        return None

    bus.subscribe(subscriber)
    with pytest.raises(ValueError, match="already registered"):
        bus.subscribe(subscriber)
    bus.publish(order_events()[0])
    with pytest.raises(OverflowError, match="capacity"):
        bus.publish(order_events()[1])

    sequence_bus = DeterministicEventBus()
    with pytest.raises(ValueError, match="sequence"):
        sequence_bus.publish(event(2, "ORDER_ACCEPTED"))
    first = order_events()[0]
    sequence_bus.publish(first)
    backwards = DomainEvent.create(
        event_id="backwards",
        aggregate_id="order-1",
        event_type="ORDER_ACCEPTED",
        sequence=2,
        occurred_at=NOW,
        previous_hash=first.event_hash,
    )
    with pytest.raises(ValueError, match="time"):
        sequence_bus.publish(backwards)
    with pytest.raises(ValueError, match="capacity"):
        DeterministicEventBus(capacity=0)


def test_order_state_covers_rejection_cancellation_and_contract_errors() -> None:
    submitted, accepted, partial, _filled = order_events()
    rejected = event(2, "ORDER_REJECTED", previous_hash=submitted.event_hash)
    assert (
        OrderStateMachine.replay((submitted, rejected)).status is OrderStatus.REJECTED
    )
    cancelled = event(4, "ORDER_CANCELLED", previous_hash=partial.event_hash)
    assert (
        OrderStateMachine.replay((submitted, accepted, partial, cancelled)).status
        is OrderStatus.CANCELLED
    )
    state = OrderStateMachine.replay((submitted, accepted))
    wrong_kind = event(
        3,
        "ORDER_PARTIALLY_FILLED",
        (("fill_quantity", "2"), ("fill_price", "100")),
        previous_hash=accepted.event_hash,
    )
    with pytest.raises(ValueError, match="disagree"):
        OrderStateMachine.apply(state, wrong_kind)
    with pytest.raises(ValueError, match="unsupported"):
        OrderStateMachine.apply(state, event(3, "UNKNOWN"))
    with pytest.raises(ValueError, match="aggregate"):
        OrderStateMachine.apply(
            state,
            DomainEvent.create(
                event_id="wrong-order",
                aggregate_id="other",
                event_type="ORDER_CANCELLED",
                sequence=3,
                occurred_at=NOW + timedelta(seconds=3),
            ),
        )


def test_clock_and_event_models_reject_invalid_contracts() -> None:
    assert SystemClock().now().tzinfo is not None
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulatedClock(NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="identity"):
        DomainEvent.create(
            event_id=" ",
            aggregate_id="order",
            event_type="TYPE",
            sequence=1,
            occurred_at=NOW,
        )
    with pytest.raises(ValueError, match="action"):
        OrderStateMachine.replay(
            (
                event(
                    1,
                    "ORDER_SUBMITTED",
                    (("symbol", "HOTUSDT"), ("action", "SHORT"), ("quantity", "1")),
                ),
            )
        )

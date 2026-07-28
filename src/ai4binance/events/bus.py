"""In-memory deterministic event journal and replay bus."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from ai4binance.events.models import DomainEvent

EventSubscriber = Callable[[DomainEvent], None]


@dataclass(slots=True)
class DeterministicEventBus:
    """Validate sequence/hash/time before committing events to a bounded journal."""

    capacity: int = 100_000
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _event_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _subscribers: list[EventSubscriber] = field(
        default_factory=list, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if not 1 <= self.capacity <= 1_000_000:
            raise ValueError("event bus capacity must be between 1 and 1000000")

    def subscribe(self, subscriber: EventSubscriber) -> None:
        if subscriber in self._subscribers:
            raise ValueError("event subscriber is already registered")
        self._subscribers.append(subscriber)

    def publish(self, event: DomainEvent) -> None:
        if len(self._events) >= self.capacity:
            raise OverflowError("event journal capacity exceeded")
        if event.event_id in self._event_ids:
            raise ValueError("duplicate event identity")
        expected_sequence = len(self._events) + 1
        expected_hash = self._events[-1].event_hash if self._events else "GENESIS"
        if event.sequence != expected_sequence:
            raise ValueError("event sequence is not contiguous")
        if event.previous_hash != expected_hash:
            raise ValueError("event hash chain is broken")
        if self._events and event.occurred_at < self._events[-1].occurred_at:
            raise ValueError("event time cannot move backwards")
        self._events.append(event)
        self._event_ids.add(event.event_id)
        for subscriber in tuple(self._subscribers):
            subscriber(event)

    def replay(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            self.publish(event)

    def snapshot(self) -> tuple[DomainEvent, ...]:
        return tuple(self._events)

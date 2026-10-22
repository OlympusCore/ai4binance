"""Dependency-neutral observation port; no policy, persistence or authority."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from typing import Protocol


class CoreOutputObserver(Protocol):
    """Observe a producer/consumer handoff through an injected implementation."""

    def consume[T, U](
        self,
        interface_id: str,
        *,
        inputs: object,
        produce: Callable[[], T],
        consume: Callable[[T], U],
    ) -> U: ...


type CoreObservationFactory = Callable[
    [str], AbstractContextManager[CoreOutputObserver]
]

_CURRENT_OBSERVER: ContextVar[CoreOutputObserver | None] = ContextVar(
    "ai4binance_core_output_observer", default=None
)


def current_core_output_observer() -> CoreOutputObserver | None:
    return _CURRENT_OBSERVER.get()


@contextmanager
def use_core_output_observer(
    observer: CoreOutputObserver,
) -> Iterator[CoreOutputObserver]:
    """Bind an observer to the caller's context without granting permissions."""
    token = _CURRENT_OBSERVER.set(observer)
    try:
        yield observer
    finally:
        _CURRENT_OBSERVER.reset(token)


def consume_core_output[T, U](
    interface_id: str,
    *,
    inputs: object,
    produce: Callable[[], T],
    consume: Callable[[T], U],
) -> U:
    """Dispatch evidence only; the existing producer and consumer retain control."""
    observer = _CURRENT_OBSERVER.get()
    if observer is None:
        return consume(produce())
    return observer.consume(
        interface_id, inputs=inputs, produce=produce, consume=consume
    )

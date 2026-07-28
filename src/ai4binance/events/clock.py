"""Injectable clocks for deterministic research and paper workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Minimal time source."""

    def now(self) -> datetime:
        """Return a timezone-aware timestamp."""


@dataclass(frozen=True, slots=True)
class SystemClock:
    """UTC wall clock for external boundaries."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(slots=True)
class SimulatedClock:
    """Monotonic manually advanced clock for replay and tests."""

    current: datetime

    def __post_init__(self) -> None:
        self._validate(self.current)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        if delta <= timedelta(0):
            raise ValueError("simulated clock advance must be positive")
        self.current += delta
        return self.current

    def set(self, timestamp: datetime) -> datetime:
        self._validate(timestamp)
        if timestamp < self.current:
            raise ValueError("simulated clock cannot move backwards")
        self.current = timestamp
        return self.current

    @staticmethod
    def _validate(timestamp: datetime) -> None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("clock timestamp must be timezone-aware")

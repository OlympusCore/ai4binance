"""Bounded agent execution telemetry that never changes trading decisions."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from ai4binance.schemas import AgentStatus


@dataclass(frozen=True, slots=True)
class AgentExecutionMetric:
    """One low-cardinality measurement for a deterministic agent call."""

    cycle_id: str
    snapshot_id: str
    agent_name: str
    elapsed_ms: float
    status: AgentStatus
    blocker_count: int
    latency_budget_exceeded: bool

    def __post_init__(self) -> None:
        if not self.cycle_id.strip() or not self.snapshot_id.strip():
            raise ValueError("agent metric requires cycle and snapshot identity")
        if not self.agent_name.strip() or self.elapsed_ms < 0.0:
            raise ValueError("agent metric name and elapsed time are invalid")
        if self.blocker_count < 0:
            raise ValueError("agent metric blocker count cannot be negative")


class AgentTelemetrySink(Protocol):
    """Minimal sink contract; implementations must be safe for concurrent use."""

    def record(self, metric: AgentExecutionMetric) -> None:
        """Persist or aggregate one execution metric."""


class InMemoryAgentTelemetry:
    """Thread-safe bounded test and local-diagnostics sink."""

    def __init__(self, *, capacity: int = 4096) -> None:
        if not 1 <= capacity <= 100_000:
            raise ValueError("telemetry capacity must be between 1 and 100000")
        self._capacity = capacity
        self._records: list[AgentExecutionMetric] = []
        self._lock = Lock()

    def record(self, metric: AgentExecutionMetric) -> None:
        with self._lock:
            self._records.append(metric)
            overflow = len(self._records) - self._capacity
            if overflow > 0:
                del self._records[:overflow]

    def snapshot(self) -> tuple[AgentExecutionMetric, ...]:
        """Return a stable copy without exposing mutable internal state."""
        with self._lock:
            return tuple(self._records)

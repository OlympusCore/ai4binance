"""Bounded agent execution telemetry that never changes trading decisions."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol, runtime_checkable

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


@dataclass(frozen=True, slots=True)
class OrchestrationCycleMetric:
    """Baseline timing and scheduler counts for one deterministic analysis cycle."""

    cycle_id: str
    snapshot_id: str
    cycle_wall_ms: float
    specialist_wall_ms: float
    scheduler_overhead_ms: float
    scheduled_capability_count: int
    executed_capability_count: int
    skipped_capability_count: int
    scheduled_bundle_count: int = 0
    skipped_bundle_count: int = 0
    bundle_task_count: int = 0

    def __post_init__(self) -> None:
        if not self.cycle_id.strip() or not self.snapshot_id.strip():
            raise ValueError("cycle metric requires cycle and snapshot identity")
        if any(
            value < 0.0
            for value in (
                self.cycle_wall_ms,
                self.specialist_wall_ms,
                self.scheduler_overhead_ms,
            )
        ):
            raise ValueError("cycle metric timings cannot be negative")
        if any(
            value < 0
            for value in (
                self.scheduled_capability_count,
                self.executed_capability_count,
                self.skipped_capability_count,
                self.scheduled_bundle_count,
                self.skipped_bundle_count,
                self.bundle_task_count,
            )
        ):
            raise ValueError("cycle metric capability counts cannot be negative")
        if self.executed_capability_count > self.scheduled_capability_count:
            raise ValueError("executed capability count cannot exceed scheduled count")
        if self.bundle_task_count > self.executed_capability_count:
            raise ValueError(
                "bundle task count cannot exceed executed capability count"
            )
        if (
            self.scheduled_capability_count - self.executed_capability_count
            != self.skipped_capability_count
        ):
            raise ValueError(
                "skipped capability count must match scheduled minus executed"
            )


class AgentTelemetrySink(Protocol):
    """Minimal sink contract; implementations must be safe for concurrent use."""

    def record(self, metric: AgentExecutionMetric) -> None:
        """Persist or aggregate one execution metric."""


@runtime_checkable
class CycleTelemetrySink(Protocol):
    """Optional sink extension for one aggregate orchestration-cycle metric."""

    def record_cycle(self, metric: OrchestrationCycleMetric) -> None:
        """Persist or aggregate one orchestration-cycle metric."""


class InMemoryAgentTelemetry:
    """Thread-safe bounded test and local-diagnostics sink."""

    def __init__(self, *, capacity: int = 4096) -> None:
        if not 1 <= capacity <= 100_000:
            raise ValueError("telemetry capacity must be between 1 and 100000")
        self._capacity = capacity
        self._records: list[AgentExecutionMetric] = []
        self._cycle_records: list[OrchestrationCycleMetric] = []
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

    def record_cycle(self, metric: OrchestrationCycleMetric) -> None:
        """Store a bounded aggregate timing record for one analysis cycle."""
        with self._lock:
            self._cycle_records.append(metric)
            overflow = len(self._cycle_records) - self._capacity
            if overflow > 0:
                del self._cycle_records[:overflow]

    def cycle_snapshot(self) -> tuple[OrchestrationCycleMetric, ...]:
        """Return a stable copy of aggregate orchestration-cycle records."""
        with self._lock:
            return tuple(self._cycle_records)

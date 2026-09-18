"""Runtime metrics for governed memory operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from statistics import median
from typing import Protocol


class MemoryRuntimeOperation(StrEnum):
    CANDIDATE_INTAKE = "CANDIDATE_INTAKE"
    RETRIEVAL = "RETRIEVAL"
    CONTEXT_COMPILE = "CONTEXT_COMPILE"
    STORE_APPEND = "STORE_APPEND"


@dataclass(frozen=True, slots=True)
class MemoryRuntimeMetricEvent:
    operation: MemoryRuntimeOperation
    latency_ms: float = 0.0
    compiled_context_bytes: int = 0
    compiled_context_token_estimate: int = 0
    active_memory_count: int = 0
    candidate_memory_count: int = 0
    stale_memory_count: int = 0
    conflict_count: int = 0
    duplicate_rejection_count: int = 0
    promotion_rejection_count: int = 0

    def __post_init__(self) -> None:
        if self.operation not in set(MemoryRuntimeOperation):
            raise ValueError("memory runtime operation is invalid")
        if self.latency_ms < 0.0:
            raise ValueError("memory runtime latency cannot be negative")
        for field_name in (
            "compiled_context_bytes",
            "compiled_context_token_estimate",
            "active_memory_count",
            "candidate_memory_count",
            "stale_memory_count",
            "conflict_count",
            "duplicate_rejection_count",
            "promotion_rejection_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")


@dataclass(frozen=True, slots=True)
class MemoryRuntimeMetricsSnapshot:
    memory_compile_latency_p50: float | None
    memory_compile_latency_p95: float | None
    memory_retrieval_latency_p95: float | None
    compiled_context_bytes: int
    compiled_context_token_estimate: int
    active_memory_count: int
    candidate_memory_count: int
    memory_conflict_rate: float
    stale_memory_rate: float
    duplicate_rejection_rate: float
    promotion_rejection_rate: float
    event_count: int
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in (
            "compiled_context_bytes",
            "compiled_context_token_estimate",
            "active_memory_count",
            "candidate_memory_count",
            "event_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")
        for field_name in (
            "memory_conflict_rate",
            "stale_memory_rate",
            "duplicate_rejection_rate",
            "promotion_rejection_rate",
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory runtime metrics cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "memory_compile_latency_p50": self.memory_compile_latency_p50,
            "memory_compile_latency_p95": self.memory_compile_latency_p95,
            "memory_retrieval_latency_p95": self.memory_retrieval_latency_p95,
            "compiled_context_bytes": self.compiled_context_bytes,
            "compiled_context_token_estimate": self.compiled_context_token_estimate,
            "active_memory_count": self.active_memory_count,
            "candidate_memory_count": self.candidate_memory_count,
            "memory_conflict_rate": self.memory_conflict_rate,
            "stale_memory_rate": self.stale_memory_rate,
            "duplicate_rejection_rate": self.duplicate_rejection_rate,
            "promotion_rejection_rate": self.promotion_rejection_rate,
            "event_count": self.event_count,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


class MemoryRuntimeMetricsRecorder(Protocol):
    def record(self, event: MemoryRuntimeMetricEvent) -> None: ...


@dataclass(slots=True)
class InMemoryMemoryRuntimeMetricsRecorder:
    events: list[MemoryRuntimeMetricEvent] = field(default_factory=list)

    def record(self, event: MemoryRuntimeMetricEvent) -> None:
        self.events.append(event)

    def snapshot(self) -> MemoryRuntimeMetricsSnapshot:
        compile_latencies = tuple(
            event.latency_ms
            for event in self.events
            if event.operation is MemoryRuntimeOperation.CONTEXT_COMPILE
        )
        retrieval_latencies = tuple(
            event.latency_ms
            for event in self.events
            if event.operation is MemoryRuntimeOperation.RETRIEVAL
        )
        store_events = tuple(
            event
            for event in self.events
            if event.operation is MemoryRuntimeOperation.STORE_APPEND
        )
        candidate_events = tuple(
            event
            for event in self.events
            if event.operation is MemoryRuntimeOperation.CANDIDATE_INTAKE
        )
        stale_count = sum(event.stale_memory_count for event in self.events)
        observed_memory_count = sum(
            event.active_memory_count
            + event.candidate_memory_count
            + event.stale_memory_count
            for event in self.events
        )
        conflict_count = sum(event.conflict_count for event in candidate_events)
        duplicate_rejection_count = sum(
            event.duplicate_rejection_count for event in store_events
        )
        promotion_rejection_count = sum(
            event.promotion_rejection_count for event in candidate_events
        )
        return MemoryRuntimeMetricsSnapshot(
            memory_compile_latency_p50=_percentile(compile_latencies, 50),
            memory_compile_latency_p95=_percentile(compile_latencies, 95),
            memory_retrieval_latency_p95=_percentile(retrieval_latencies, 95),
            compiled_context_bytes=max(
                (event.compiled_context_bytes for event in self.events),
                default=0,
            ),
            compiled_context_token_estimate=max(
                (event.compiled_context_token_estimate for event in self.events),
                default=0,
            ),
            active_memory_count=max(
                (event.active_memory_count for event in self.events),
                default=0,
            ),
            candidate_memory_count=max(
                (event.candidate_memory_count for event in self.events),
                default=0,
            ),
            memory_conflict_rate=_rate(conflict_count, len(candidate_events)),
            stale_memory_rate=_rate(stale_count, observed_memory_count),
            duplicate_rejection_rate=_rate(
                duplicate_rejection_count,
                len(store_events),
            ),
            promotion_rejection_rate=_rate(
                promotion_rejection_count,
                len(candidate_events),
            ),
            event_count=len(self.events),
        )


def _percentile(values: tuple[float, ...], percentile: int) -> float | None:
    if not values:
        return None
    if percentile == 50:
        return float(median(values))
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile / 100) * len(ordered)) - 1))
    return ordered[index]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)

"""Deterministic exchange health gates with no order-write capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    used_weight: int
    remaining_weight: int
    retry_after_seconds: float
    blockers: tuple[str, ...]


@dataclass(slots=True)
class RateLimitBudget:
    """Fixed-window request-weight guard driven by an injected timestamp."""

    maximum_weight: int
    window: timedelta
    _window_started_at: datetime | None = None
    _used_weight: int = 0

    def __post_init__(self) -> None:
        if self.maximum_weight < 1 or self.window <= timedelta(0):
            raise ValueError("rate-limit budget and window must be positive")

    def consume(self, weight: int, now: datetime) -> RateLimitDecision:
        if weight < 1 or weight > self.maximum_weight:
            raise ValueError("request weight must fit within the configured budget")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("rate-limit timestamp must be timezone-aware")
        if self._window_started_at is not None and now < self._window_started_at:
            raise ValueError("rate-limit time cannot move backwards")
        if (
            self._window_started_at is None
            or now - self._window_started_at >= self.window
        ):
            self._window_started_at = now
            self._used_weight = 0
        projected = self._used_weight + weight
        if projected > self.maximum_weight:
            elapsed = now - self._window_started_at
            retry_after = max(0.0, (self.window - elapsed).total_seconds())
            return RateLimitDecision(
                False,
                self._used_weight,
                self.maximum_weight - self._used_weight,
                retry_after,
                ("EXCHANGE_RATE_LIMIT_BUDGET_EXHAUSTED",),
            )
        self._used_weight = projected
        return RateLimitDecision(
            True,
            self._used_weight,
            self.maximum_weight - self._used_weight,
            0.0,
            (),
        )


@dataclass(frozen=True, slots=True)
class ServerTimeAssessment:
    drift_ms: int
    acceptable: bool
    blockers: tuple[str, ...]


def assess_server_time(
    local_time_ms: int, server_time_ms: int, *, maximum_drift_ms: int = 1_000
) -> ServerTimeAssessment:
    """Block signed operations when local and exchange time diverge."""
    if min(local_time_ms, server_time_ms) < 0 or maximum_drift_ms < 1:
        raise ValueError("server-time values and threshold are invalid")
    drift = abs(local_time_ms - server_time_ms)
    blockers = ("EXCHANGE_SERVER_TIME_DRIFT",) if drift > maximum_drift_ms else ()
    return ServerTimeAssessment(drift, not blockers, blockers)

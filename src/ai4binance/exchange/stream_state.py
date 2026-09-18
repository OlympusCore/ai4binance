"""Deterministic public stream gap, backfill, and reconnect state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class StreamState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    SYNCING_SNAPSHOT = "SYNCING_SNAPSHOT"
    LIVE = "LIVE"
    GAP_DETECTED = "GAP_DETECTED"
    BACKFILLING = "BACKFILLING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class StreamRecoveryPolicy:
    max_reconnect_attempts: int = 5
    maximum_sequence_gap: int = 10_000
    maximum_queue_depth: int = 50_000
    stale_after: timedelta = timedelta(seconds=30)
    base_retry_seconds: float = 1.0
    maximum_retry_seconds: float = 30.0
    maximum_connection_age: timedelta = timedelta(hours=23, minutes=55)

    def __post_init__(self) -> None:
        counts = (
            self.max_reconnect_attempts,
            self.maximum_sequence_gap,
            self.maximum_queue_depth,
        )
        if (
            min(counts) < 1
            or self.stale_after <= timedelta(0)
            or self.maximum_connection_age <= timedelta(0)
            or self.base_retry_seconds <= 0.0
            or self.maximum_retry_seconds < self.base_retry_seconds
        ):
            raise ValueError("stream recovery policy is invalid")


@dataclass(frozen=True, slots=True)
class StreamTransition:
    state: StreamState
    accepted: bool
    last_sequence: int | None
    retry_after_seconds: float
    blockers: tuple[str, ...]
    execution_allowed: bool = False


@dataclass(slots=True)
class PublicStreamRecovery:
    """Track public sequence continuity without opening a network connection."""

    policy: StreamRecoveryPolicy = StreamRecoveryPolicy()
    state: StreamState = StreamState.DISCONNECTED
    last_sequence: int | None = None
    reconnect_attempts: int = 0
    last_event_at: datetime | None = None
    connected_at: datetime | None = None

    def start(self) -> StreamTransition:
        self._require_state({StreamState.DISCONNECTED})
        self.state = StreamState.CONNECTING
        return self._result(True)

    def connected(self, observed_at: datetime | None = None) -> StreamTransition:
        self._require_state({StreamState.CONNECTING})
        if observed_at is not None:
            self._require_aware(observed_at)
        self.connected_at = observed_at
        self.state = StreamState.SYNCING_SNAPSHOT
        return self._result(True)

    def apply_snapshot(self, sequence: int, observed_at: datetime) -> StreamTransition:
        self._require_state({StreamState.SYNCING_SNAPSHOT, StreamState.BACKFILLING})
        self._validate_sequence_and_time(sequence, observed_at)
        self.last_sequence = sequence
        self.last_event_at = observed_at
        self.reconnect_attempts = 0
        self.state = StreamState.LIVE
        return self._result(True)

    def apply_update(
        self,
        first_sequence: int,
        last_sequence: int,
        observed_at: datetime,
        *,
        queue_depth: int = 0,
    ) -> StreamTransition:
        self._require_state({StreamState.LIVE})
        self._validate_sequence_and_time(last_sequence, observed_at)
        if first_sequence < 1 or first_sequence > last_sequence or queue_depth < 0:
            raise ValueError("stream update sequence or queue depth is invalid")
        if queue_depth > self.policy.maximum_queue_depth:
            self.state = StreamState.DEGRADED
            return self._result(False, "STREAM_BACKPRESSURE_LIMIT_EXCEEDED")
        if self.last_sequence is None:
            raise RuntimeError("live stream is missing its snapshot sequence")
        expected = self.last_sequence + 1
        if last_sequence < expected:
            return self._result(False)
        if first_sequence > expected:
            gap = first_sequence - expected
            self.state = (
                StreamState.DEGRADED
                if gap > self.policy.maximum_sequence_gap
                else StreamState.GAP_DETECTED
            )
            blocker = (
                "STREAM_SEQUENCE_GAP_EXCEEDS_LIMIT"
                if self.state is StreamState.DEGRADED
                else "STREAM_SEQUENCE_GAP"
            )
            return self._result(False, blocker)
        self.last_sequence = last_sequence
        self.last_event_at = observed_at
        return self._result(True)

    def begin_backfill(self) -> StreamTransition:
        self._require_state({StreamState.GAP_DETECTED})
        self.state = StreamState.BACKFILLING
        return self._result(True, "REST_BACKFILL_IN_PROGRESS")

    def reject_unsequenced_update(self) -> StreamTransition:
        """Reject an update whose exchange sequence cannot be verified."""
        self._require_state({StreamState.LIVE})
        return self._result(False, "KLINE_TRADE_SEQUENCE_UNAVAILABLE")

    def disconnected(self) -> StreamTransition:
        self._require_state(
            {
                StreamState.CONNECTING,
                StreamState.SYNCING_SNAPSHOT,
                StreamState.LIVE,
                StreamState.GAP_DETECTED,
                StreamState.BACKFILLING,
            }
        )
        self.reconnect_attempts += 1
        if self.reconnect_attempts > self.policy.max_reconnect_attempts:
            self.state = StreamState.DEGRADED
            return self._result(False, "STREAM_RECONNECT_CIRCUIT_OPEN")
        self.state = StreamState.DISCONNECTED
        exponent = self.reconnect_attempts - 1
        retry = min(
            self.policy.maximum_retry_seconds,
            self.policy.base_retry_seconds * (2**exponent),
        )
        return self._result(False, "PUBLIC_STREAM_DISCONNECTED", retry=retry)

    def server_shutdown(self) -> StreamTransition:
        """Handle Binance's explicit pre-shutdown event as a planned reconnect."""
        self._require_state(
            {
                StreamState.SYNCING_SNAPSHOT,
                StreamState.LIVE,
                StreamState.GAP_DETECTED,
                StreamState.BACKFILLING,
            }
        )
        self.state = StreamState.DISCONNECTED
        self.connected_at = None
        return self._result(False, "STREAM_SERVER_SHUTDOWN")

    def check_connection_rollover(self, now: datetime) -> StreamTransition:
        """Require a planned reconnect before Binance's 24-hour disconnect."""
        self._require_state({StreamState.LIVE})
        self._require_aware(now)
        if self.connected_at is None or now < self.connected_at:
            raise ValueError("stream connection age is unavailable or invalid")
        if now - self.connected_at >= self.policy.maximum_connection_age:
            self.state = StreamState.DISCONNECTED
            self.connected_at = None
            return self._result(False, "STREAM_CONNECTION_ROLLOVER_REQUIRED")
        return self._result(True)

    def check_staleness(self, now: datetime) -> StreamTransition:
        self._require_state({StreamState.LIVE})
        self._require_aware(now)
        if self.last_event_at is None or now < self.last_event_at:
            raise ValueError("stream staleness time is invalid")
        if now - self.last_event_at > self.policy.stale_after:
            self.state = StreamState.DEGRADED
            return self._result(False, "PUBLIC_STREAM_STALE")
        return self._result(True)

    def stop(self) -> StreamTransition:
        if self.state is StreamState.STOPPED:
            raise ValueError("stream is already stopped")
        self.state = StreamState.STOPPED
        return self._result(True)

    def _validate_sequence_and_time(self, sequence: int, observed_at: datetime) -> None:
        if sequence < 1:
            raise ValueError("stream sequence must be positive")
        self._require_aware(observed_at)
        if self.last_event_at is not None and observed_at < self.last_event_at:
            raise ValueError("stream event time cannot move backwards")

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("stream timestamp must be timezone-aware")

    def _require_state(self, allowed: set[StreamState]) -> None:
        if self.state not in allowed:
            raise ValueError(f"invalid stream transition from {self.state}")

    def _result(
        self,
        accepted: bool,
        *blockers: str,
        retry: float = 0.0,
    ) -> StreamTransition:
        return StreamTransition(
            self.state,
            accepted,
            self.last_sequence,
            retry,
            tuple(blockers),
        )

"""Read-only connector readiness and public stream recovery tests."""

from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.exchange import (
    ConnectorReadinessInput,
    PublicStreamRecovery,
    StreamRecoveryPolicy,
    StreamState,
    assess_connector_readiness,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def ready_input(**overrides: bool) -> ConnectorReadinessInput:
    values = {
        "api_reachable": True,
        "server_time_synchronized": True,
        "exchange_info_fresh": True,
        "trading_rules_loaded": True,
        "order_book_snapshot_ready": True,
        "stream_connected": True,
        "sequence_contiguous": True,
        "rest_backfill_complete": True,
    }
    values.update(overrides)
    return ConnectorReadinessInput(**values)


def live_stream(policy: StreamRecoveryPolicy | None = None) -> PublicStreamRecovery:
    stream = PublicStreamRecovery(policy or StreamRecoveryPolicy())
    assert stream.start().state is StreamState.CONNECTING
    assert stream.connected().state is StreamState.SYNCING_SNAPSHOT
    assert stream.apply_snapshot(100, NOW).state is StreamState.LIVE
    return stream


def test_public_readiness_passes_without_private_state_or_execution() -> None:
    result = assess_connector_readiness(ready_input())
    assert result.ready_for_research is True
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    private = assess_connector_readiness(ready_input(private_state_required=True))
    assert private.ready_for_research is False
    assert private.blockers == (
        "WALLET_STATE_UNKNOWN",
        "OPEN_ORDERS_NOT_RECONCILED",
    )


def test_readiness_lists_every_public_blocker_deterministically() -> None:
    result = assess_connector_readiness(
        ConnectorReadinessInput(False, False, False, False, False, False, False, False)
    )
    assert result.ready_for_research is False
    assert len(result.blockers) == 8
    with pytest.raises(ValueError, match="disagree"):
        type(result)(True, ("BLOCKER",))


def test_stream_accepts_overlap_ignores_old_and_recovers_gap() -> None:
    stream = live_stream()
    assert stream.apply_update(100, 101, NOW + timedelta(seconds=1)).accepted is True
    assert stream.apply_update(99, 100, NOW + timedelta(seconds=2)).accepted is False
    gap = stream.apply_update(103, 104, NOW + timedelta(seconds=3))
    assert gap.state is StreamState.GAP_DETECTED
    assert gap.blockers == ("STREAM_SEQUENCE_GAP",)
    assert stream.begin_backfill().state is StreamState.BACKFILLING
    recovered = stream.apply_snapshot(104, NOW + timedelta(seconds=4))
    assert recovered.state is StreamState.LIVE
    assert recovered.last_sequence == 104


def test_stream_degrades_on_gap_backpressure_staleness_and_reconnects() -> None:
    policy = StreamRecoveryPolicy(
        max_reconnect_attempts=1,
        maximum_sequence_gap=2,
        maximum_queue_depth=2,
        stale_after=timedelta(seconds=2),
    )
    stream = live_stream(policy)
    large_gap = stream.apply_update(105, 106, NOW + timedelta(seconds=1))
    assert large_gap.state is StreamState.DEGRADED
    assert large_gap.execution_allowed is False

    queued = live_stream(policy)
    assert (
        queued.apply_update(101, 101, NOW, queue_depth=3).state is StreamState.DEGRADED
    )
    stale = live_stream(policy)
    assert (
        stale.check_staleness(NOW + timedelta(seconds=3)).state is StreamState.DEGRADED
    )

    reconnecting = live_stream(policy)
    first = reconnecting.disconnected()
    assert first.retry_after_seconds == 1.0
    reconnecting.start()
    second = reconnecting.disconnected()
    assert second.blockers == ("STREAM_RECONNECT_CIRCUIT_OPEN",)


def test_stream_contract_rejects_invalid_transitions_and_inputs() -> None:
    stream = PublicStreamRecovery()
    with pytest.raises(ValueError, match="invalid stream transition"):
        stream.connected()
    stream.start()
    stream.connected()
    with pytest.raises(ValueError, match="positive"):
        stream.apply_snapshot(0, NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        stream.apply_snapshot(1, NOW.replace(tzinfo=None))
    stream.apply_snapshot(1, NOW)
    with pytest.raises(ValueError, match="queue depth"):
        stream.apply_update(3, 2, NOW)
    with pytest.raises(ValueError, match="backwards"):
        stream.apply_update(2, 2, NOW - timedelta(seconds=1))
    assert stream.stop().state is StreamState.STOPPED
    with pytest.raises(ValueError, match="already stopped"):
        stream.stop()
    with pytest.raises(ValueError, match="policy"):
        StreamRecoveryPolicy(max_reconnect_attempts=0)

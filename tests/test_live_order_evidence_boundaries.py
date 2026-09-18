"""Local event replay validates exchange evidence without sending orders."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.execution import live_order_lifecycle as lifecycle
from ai4binance.execution.live_spot import (
    LiveCommandResult,
    LiveCommandStatus,
    SpotOrderCommand,
)
from tests.test_live_order_lifecycle import NOW, _event, _filled_record


def _command() -> SpotOrderCommand:
    return SpotOrderCommand(
        "HOTUSDT", "BUY", "LIMIT", Decimal("5"), "live-order-1", Decimal("10"), "GTC"
    )


def _result(
    status: str | None, snapshot: dict[str, object] | None
) -> LiveCommandResult:
    return LiveCommandResult(
        LiveCommandStatus.SUBMITTED,
        (),
        "live-order-1",
        exchange_order_id="99",
        preview_hash=_command().preview_hash,
        exchange_order_status=status,
        exchange_order_snapshot=snapshot,
        authorization_id="authorization-1",
        authorization_envelope_sha256="a" * 64,
        approval_id="approval-1",
    )


@pytest.mark.parametrize(
    ("status", "snapshot", "stage"),
    [
        ("NEW", {}, "ACCEPTED"),
        ("FILLED", {"executedQty": "5", "avgPrice": "10"}, "FILLED"),
        (None, {"status": "FILLED", "executed_qty": "5", "cumQuote": "50"}, "FILLED"),
        ("EXPIRED", {}, "EXPIRED"),
        ("REJECTED", {}, "REJECTED"),
        (None, None, "SUBMITTED"),
        (" ", {}, "SUBMITTED"),
    ],
)
def test_journal_records_verified_terminal_and_pending_outcomes(
    tmp_path: Path, status: str | None, snapshot: dict[str, object] | None, stage: str
) -> None:
    journal = lifecycle.LiveOrderLifecycleJournal(tmp_path / "events.jsonl")
    record = journal.append_place_result(
        _command(), result=_result(status, snapshot), observed_at=NOW
    )
    assert record is not None
    assert record.stage.name == stage
    assert record.execution_allowed is False
    assert record.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert journal.path.stat().st_size > 0


def test_blocked_result_never_appends_journal(tmp_path: Path) -> None:
    journal = lifecycle.LiveOrderLifecycleJournal(tmp_path / "events.jsonl")
    blocked = LiveCommandResult(
        LiveCommandStatus.BLOCKED, ("NO_AUTHORITY",), "live-order-1"
    )
    assert (
        journal.append_place_result(_command(), result=blocked, observed_at=NOW) is None
    )
    assert not journal.path.exists()
    with pytest.raises(ValueError, match="unsupported live order place result"):
        lifecycle.build_place_events(
            _command(),
            result=replace(_result(None, None), status=LiveCommandStatus.BLOCKED),
            observed_at=NOW,
        )


@pytest.mark.parametrize(
    ("snapshot", "message"),
    [
        (None, "executedQty evidence"),
        ({}, "executedQty evidence"),
        ({"executedQty": "bad"}, "decimal-compatible"),
        ({"executedQty": "NaN"}, "positive"),
        ({"executedQty": "0"}, "positive"),
        ({"executedQty": "5"}, "fill price evidence"),
    ],
)
def test_fill_requires_finite_complete_exchange_evidence(
    snapshot: dict[str, object] | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        lifecycle.build_place_events(
            _command(), result=_result("FILLED", snapshot), observed_at=NOW
        )


@pytest.mark.parametrize(
    ("event_type", "quantity", "message"),
    [
        (lifecycle.LiveOrderLifecycleEvent.FILLED, "6", "exceeds"),
        (lifecycle.LiveOrderLifecycleEvent.FILLED, "4", "match requested"),
        (lifecycle.LiveOrderLifecycleEvent.PARTIALLY_FILLED, "5", "cannot complete"),
    ],
)
def test_fill_transition_rejects_quantity_drift(
    event_type: lifecycle.LiveOrderLifecycleEvent, quantity: str, message: str
) -> None:
    state = lifecycle.LiveOrderLifecycleStateMachine.replay(
        lifecycle.build_place_events(
            _command(), result=_result("NEW", {}), observed_at=NOW
        )
    )
    with pytest.raises(ValueError, match=message):
        lifecycle.LiveOrderLifecycleStateMachine.apply(
            state,
            _event(
                state.last_sequence + 1,
                event_type,
                {"fill_quantity": quantity, "fill_price": "10"},
            ),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("authorization_id", "different", "authorization ID"),
        ("authorization_envelope_sha256", "b" * 64, "authorization envelope"),
    ],
)
def test_event_cannot_change_consumed_authorization(
    field: str, value: str, message: str
) -> None:
    state = lifecycle.LiveOrderLifecycleStateMachine.replay(
        lifecycle.build_place_events(
            _command(), result=_result("NEW", {}), observed_at=NOW
        )
    )
    with pytest.raises(ValueError, match=message):
        lifecycle.LiveOrderLifecycleStateMachine.apply(
            state,
            _event(
                state.last_sequence + 1,
                lifecycle.LiveOrderLifecycleEvent.CANCEL_REQUESTED,
                {field: value},
            ),
        )


def test_cancel_requested_replays_to_cancelled() -> None:
    state = lifecycle.LiveOrderLifecycleStateMachine.replay(
        lifecycle.build_place_events(
            _command(), result=_result("NEW", {}), observed_at=NOW
        )
    )
    state = lifecycle.LiveOrderLifecycleStateMachine.apply(
        state,
        _event(
            state.last_sequence + 1,
            lifecycle.LiveOrderLifecycleEvent.CANCEL_REQUESTED,
            {},
        ),
    )
    assert state.stage is lifecycle.LiveOrderLifecycleStage.CANCEL_REQUESTED
    state = lifecycle.LiveOrderLifecycleStateMachine.apply(
        state,
        _event(
            state.last_sequence + 1, lifecycle.LiveOrderLifecycleEvent.CANCELLED, {}
        ),
    )
    assert state.stage is lifecycle.LiveOrderLifecycleStage.CANCELLED
    assert state.execution_allowed is False


def test_record_requires_acceptance_authorization_and_fill_price() -> None:
    events = lifecycle.build_place_events(
        _command(), result=_result("CANCELED", {}), observed_at=NOW
    )
    with pytest.raises(ValueError, match="acceptance evidence"):
        lifecycle.LiveOrderLifecycleStateMachine.replay(events)
    with pytest.raises(ValueError, match="exact authorization"):
        replace(
            _filled_record(), authorization_id=None, authorization_envelope_sha256=None
        )
    with pytest.raises(ValueError, match="fill price evidence"):
        lifecycle._snapshot_fill_price(None, Decimal("1"))
    draft = lifecycle.LiveOrderLifecycleRecord(
        "draft", "HOTUSDT", lifecycle.LiveOrderLifecycleStage.DRAFT, "hash"
    )
    assert draft.execution_allowed is False

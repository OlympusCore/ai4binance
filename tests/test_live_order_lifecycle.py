"""Live-order lifecycle contracts stay fail-closed and authority-free."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.events import DomainEvent
from ai4binance.execution.live_order_lifecycle import (
    LiveOrderLifecycleEvent,
    LiveOrderLifecycleRecord,
    LiveOrderLifecycleStage,
    LiveOrderLifecycleStateMachine,
    build_place_events,
)
from ai4binance.execution.live_spot import (
    LiveCommandResult,
    LiveCommandStatus,
    SpotOrderCommand,
)

NOW = datetime(2026, 7, 28, tzinfo=UTC)


def _filled_record() -> LiveOrderLifecycleRecord:
    return LiveOrderLifecycleRecord(
        order_id="live-order-complete",
        symbol="HOTUSDT",
        stage=LiveOrderLifecycleStage.FILLED,
        preview_hash="preview-hash",
        promotion_status=ValidationStatus.LIVE_ELIGIBLE,
        requested_quantity=Decimal("5"),
        approval_id="approval-1",
        authorization_id="authorization-1",
        authorization_envelope_sha256="a" * 64,
        promoted_at=NOW,
        human_approval_requested_at=NOW,
        human_approved_at=NOW,
        submission_attempted_at=NOW,
        submitted_at=NOW,
        accepted_at=NOW,
        filled_quantity=Decimal("5"),
        average_fill_price=Decimal("10"),
        last_sequence=8,
    )


def test_live_order_lifecycle_normalizes_identity_and_stays_blocked() -> None:
    record = LiveOrderLifecycleRecord(
        order_id=" live-order-1 ",
        symbol="hotusdt",
        stage=LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
        preview_hash="preview-hash",
        promotion_status=ValidationStatus.PAPER_APPROVED,
        promoted_at=NOW,
        human_approval_requested_at=NOW,
        human_approved_at=NOW,
        authorization_id="authorization-1",
        authorization_envelope_sha256="a" * 64,
    )

    assert record.symbol == "HOTUSDT"
    assert record.execution_allowed is False
    assert record.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_live_order_lifecycle_rejects_authority_grants() -> None:
    with pytest.raises(ValueError, match="cannot grant execution authority"):
        LiveOrderLifecycleRecord(
            order_id="live-order-1",
            symbol="HOTUSDT",
            stage=LiveOrderLifecycleStage.DRAFT,
            preview_hash="preview-hash",
            execution_allowed=True,
        )


def test_live_order_lifecycle_requires_submission_and_acceptance_evidence() -> None:
    with pytest.raises(ValueError, match="submission timestamp"):
        LiveOrderLifecycleRecord(
            order_id="live-order-2",
            symbol="HOTUSDT",
            stage=LiveOrderLifecycleStage.SUBMITTED,
            preview_hash="preview-hash",
            promoted_at=NOW,
            human_approval_requested_at=NOW,
            human_approved_at=NOW,
            authorization_id="authorization-1",
            authorization_envelope_sha256="a" * 64,
        )

    with pytest.raises(ValueError, match="acceptance evidence"):
        LiveOrderLifecycleRecord(
            order_id="live-order-3",
            symbol="HOTUSDT",
            stage=LiveOrderLifecycleStage.ACCEPTED,
            preview_hash="preview-hash",
            promoted_at=NOW,
            human_approval_requested_at=NOW,
            human_approved_at=NOW,
            submitted_at=NOW,
            authorization_id="authorization-1",
            authorization_envelope_sha256="a" * 64,
        )


def test_live_order_lifecycle_rejects_negative_fill_state() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        LiveOrderLifecycleRecord(
            order_id="live-order-4",
            symbol="HOTUSDT",
            stage=LiveOrderLifecycleStage.FILLED,
            preview_hash="preview-hash",
            submitted_at=NOW,
            accepted_at=NOW,
            filled_quantity=Decimal("-1"),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"order_id": " "}, "identity is required"),
        ({"requested_quantity": Decimal("0")}, "requested_quantity must be positive"),
        ({"average_fill_price": Decimal("-1")}, "fill evidence cannot be negative"),
        ({"last_sequence": -1}, "sequence cannot be negative"),
        ({"authorization_id": None}, "authorization evidence must be complete"),
        ({"execution_allowed": True}, "cannot grant execution authority"),
        ({"live_eligibility_status": "LIVE"}, "cannot grant execution authority"),
        ({"promotion_status": "INVALID"}, "promotion status is invalid"),
        ({"promoted_at": None}, "require promotion evidence"),
        ({"human_approval_requested_at": None}, "require request evidence"),
        ({"human_approved_at": None}, "require approval evidence"),
        (
            {"authorization_envelope_sha256": None},
            "authorization evidence must be complete",
        ),
        ({"submitted_at": None}, "require a submission timestamp"),
        ({"accepted_at": None}, "require acceptance evidence"),
        ({"requested_quantity": None}, "require requested quantity evidence"),
        ({"requested_quantity": Decimal("4")}, "fills cannot exceed requested"),
        ({"filled_quantity": Decimal("4")}, "must match requested quantity"),
        ({"stage": LiveOrderLifecycleStage.ACCEPTED}, "only allowed after submission"),
    ],
)
def test_live_order_lifecycle_rejects_incomplete_or_unsafe_state(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(_filled_record(), **overrides)


def test_failed_submission_state_requires_attempt_timestamp() -> None:
    with pytest.raises(ValueError, match="require an attempt timestamp"):
        replace(
            _filled_record(),
            stage=LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED,
            submission_attempted_at=None,
            submitted_at=None,
            accepted_at=None,
            filled_quantity=Decimal("0"),
            average_fill_price=Decimal("0"),
        )


def test_live_order_replay_requires_at_least_one_event() -> None:
    with pytest.raises(ValueError, match="requires events"):
        LiveOrderLifecycleStateMachine.replay(())


def test_live_order_state_machine_replays_ordered_transitions() -> None:
    previewed = _event(
        1,
        LiveOrderLifecycleEvent.PREVIEWED,
        {
            "symbol": "HOTUSDT",
            "preview_hash": "preview-hash",
            "requested_quantity": "5",
        },
    )
    promotion_requested = _event(2, LiveOrderLifecycleEvent.PROMOTION_REQUESTED, {})
    approval_requested = _event(
        3,
        LiveOrderLifecycleEvent.HUMAN_APPROVAL_REQUESTED,
        {},
    )
    approved = _event(
        4,
        LiveOrderLifecycleEvent.HUMAN_APPROVED,
        {
            "approval_id": "approval-1",
            "authorization_id": "authorization-1",
            "authorization_envelope_sha256": "a" * 64,
        },
    )
    submitted = _event(5, LiveOrderLifecycleEvent.SUBMITTED, {})
    accepted = _event(6, LiveOrderLifecycleEvent.ACCEPTED, {})
    partially_filled = _event(
        7,
        LiveOrderLifecycleEvent.PARTIALLY_FILLED,
        {"fill_quantity": "2", "fill_price": "100"},
    )
    filled = _event(
        8,
        LiveOrderLifecycleEvent.FILLED,
        {"fill_quantity": "3", "fill_price": "101"},
    )

    state = LiveOrderLifecycleStateMachine.replay(
        (
            previewed,
            promotion_requested,
            approval_requested,
            approved,
            submitted,
            accepted,
            partially_filled,
            filled,
        )
    )

    assert state.stage is LiveOrderLifecycleStage.FILLED
    assert state.symbol == "HOTUSDT"
    assert state.approval_id == "approval-1"
    assert state.authorization_id == "authorization-1"
    assert state.authorization_envelope_sha256 == "a" * 64
    assert state.requested_quantity == Decimal("5")
    assert state.filled_quantity == Decimal("5")
    assert state.execution_allowed is False
    assert state.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_live_order_state_machine_rejects_illegal_transition() -> None:
    previewed = _event(
        1,
        LiveOrderLifecycleEvent.PREVIEWED,
        {"symbol": "HOTUSDT", "preview_hash": "preview-hash"},
    )
    submitted = _event(2, LiveOrderLifecycleEvent.SUBMITTED, {})

    with pytest.raises(ValueError, match="illegal live order state transition"):
        LiveOrderLifecycleStateMachine.replay((previewed, submitted))


def test_live_order_state_machine_rejects_non_preview_first_event() -> None:
    with pytest.raises(ValueError, match="first live order event"):
        LiveOrderLifecycleStateMachine.apply(
            None,
            _event(1, LiveOrderLifecycleEvent.SUBMITTED, {}),
        )


@pytest.mark.parametrize(
    ("sequence", "event_type", "payload", "message"),
    [
        (2, LiveOrderLifecycleEvent.PREVIEWED, {}, "only be recorded once"),
        (3, LiveOrderLifecycleEvent.PROMOTION_REQUESTED, {}, "not contiguous"),
        (
            2,
            LiveOrderLifecycleEvent.PROMOTION_REQUESTED,
            {"symbol": "OTHERUSDT"},
            "symbol mismatch",
        ),
        (
            2,
            LiveOrderLifecycleEvent.PROMOTION_REQUESTED,
            {"preview_hash": "other-hash"},
            "preview hash mismatch",
        ),
    ],
)
def test_live_order_state_machine_rejects_event_chain_drift(
    sequence: int,
    event_type: LiveOrderLifecycleEvent,
    payload: dict[str, str],
    message: str,
) -> None:
    state = LiveOrderLifecycleStateMachine.apply(
        None,
        _event(
            1,
            LiveOrderLifecycleEvent.PREVIEWED,
            {"symbol": "HOTUSDT", "preview_hash": "preview-hash"},
        ),
    )
    with pytest.raises(ValueError, match=message):
        LiveOrderLifecycleStateMachine.apply(
            state,
            _event(sequence, event_type, payload),
        )


def test_live_order_state_machine_rejects_aggregate_drift() -> None:
    state = LiveOrderLifecycleStateMachine.apply(
        None,
        _event(
            1,
            LiveOrderLifecycleEvent.PREVIEWED,
            {"symbol": "HOTUSDT", "preview_hash": "preview-hash"},
        ),
    )
    drifted = DomainEvent.create(
        event_id="event-drifted",
        aggregate_id="another-order",
        event_type=LiveOrderLifecycleEvent.PROMOTION_REQUESTED.value,
        sequence=2,
        occurred_at=NOW,
        payload=(),
        previous_hash="hash-1",
    )

    with pytest.raises(ValueError, match="aggregate identity mismatch"):
        LiveOrderLifecycleStateMachine.apply(state, drifted)


def test_live_order_state_machine_rejects_unknown_event_type() -> None:
    state = LiveOrderLifecycleStateMachine.apply(
        None,
        _event(
            1,
            LiveOrderLifecycleEvent.PREVIEWED,
            {"symbol": "HOTUSDT", "preview_hash": "preview-hash"},
        ),
    )
    unknown = DomainEvent.create(
        event_id="event-unknown",
        aggregate_id=state.order_id,
        event_type="LIVE_ORDER_UNKNOWN",
        sequence=2,
        occurred_at=NOW,
        payload=(),
        previous_hash="hash-1",
    )

    with pytest.raises(ValueError, match="unsupported live order event type"):
        LiveOrderLifecycleStateMachine.apply(state, unknown)


def test_live_order_place_events_extend_from_verified_snapshot() -> None:
    command = SpotOrderCommand(
        "HOTUSDT",
        "BUY",
        "LIMIT",
        Decimal("5"),
        "live-order-1",
        Decimal("10"),
        "GTC",
    )
    events = build_place_events(
        command,
        result=LiveCommandResult(
            LiveCommandStatus.SUBMITTED,
            (),
            command.client_order_id,
            exchange_order_id="99",
            preview_hash=command.preview_hash,
            exchange_order_status="PARTIALLY_FILLED",
            exchange_order_snapshot={
                "status": "PARTIALLY_FILLED",
                "executedQty": "2",
                "cummulativeQuoteQty": "20",
            },
            authorization_id="authorization-1",
            authorization_envelope_sha256="a" * 64,
            approval_id="approval-1",
        ),
        observed_at=NOW,
    )

    assert [event.event_type for event in events] == [
        "LIVE_ORDER_PREVIEWED",
        "LIVE_ORDER_PROMOTION_REQUESTED",
        "LIVE_ORDER_HUMAN_APPROVAL_REQUESTED",
        "LIVE_ORDER_HUMAN_APPROVED",
        "LIVE_ORDER_SUBMITTED",
        "LIVE_ORDER_ACCEPTED",
        "LIVE_ORDER_PARTIALLY_FILLED",
    ]
    state = LiveOrderLifecycleStateMachine.replay(events)
    assert state.stage is LiveOrderLifecycleStage.PARTIALLY_FILLED
    assert state.filled_quantity == Decimal("2")
    assert state.average_fill_price == Decimal("10")


def test_failed_submission_attempt_records_review_required_provenance() -> None:
    command = SpotOrderCommand(
        "HOTUSDT",
        "BUY",
        "LIMIT",
        Decimal("5"),
        "live-order-1",
        Decimal("10"),
        "GTC",
    )
    events = build_place_events(
        command,
        result=LiveCommandResult(
            LiveCommandStatus.ATTEMPT_FAILED,
            ("LIVE_ORDER_ATTEMPT_OUTCOME_UNVERIFIED",),
            command.client_order_id,
            preview_hash=command.preview_hash,
            authorization_id="authorization-1",
            authorization_envelope_sha256="a" * 64,
            approval_id="approval-1",
        ),
        observed_at=NOW,
    )

    assert [event.event_type for event in events] == [
        "LIVE_ORDER_PREVIEWED",
        "LIVE_ORDER_PROMOTION_REQUESTED",
        "LIVE_ORDER_HUMAN_APPROVAL_REQUESTED",
        "LIVE_ORDER_HUMAN_APPROVED",
        "LIVE_ORDER_SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED",
    ]
    state = LiveOrderLifecycleStateMachine.replay(events)
    assert (
        state.stage is LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED
    )
    assert state.submission_attempted_at == NOW
    assert state.submitted_at is None
    assert state.authorization_id == "authorization-1"
    assert state.authorization_envelope_sha256 == "a" * 64
    assert state.execution_allowed is False
    assert state.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def _event(
    sequence: int,
    event_type: LiveOrderLifecycleEvent,
    payload: dict[str, str],
) -> DomainEvent:
    previous_hash = "GENESIS" if sequence == 1 else f"hash-{sequence - 1}"
    return DomainEvent.create(
        event_id=f"event-{sequence}",
        aggregate_id="live-order-1",
        event_type=event_type.value,
        sequence=sequence,
        occurred_at=NOW,
        payload=tuple(sorted(payload.items())),
        previous_hash=previous_hash,
    )

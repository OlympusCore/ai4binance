"""Fail-closed coverage for manual financial approval contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.execution.manual_approval import (
    ApprovalQueueRecord,
    ApprovalRequest,
    LocalApprovalQueue,
    ManualActionProposal,
    ManualActionType,
)

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def action(**overrides: object) -> ManualActionProposal:
    values: dict[str, object] = {
        "action_id": "action-1",
        "action_type": ManualActionType.PLACE_SPOT_ORDER,
        "asset_or_symbol": "BTCUSDT",
        "suggested_notional_usdt": Decimal("10"),
        "reason": "Risk reviewed.",
        "expected_effect": "Paper-only proposal.",
        "risk": "Manual approval required.",
    }
    values.update(overrides)
    return ManualActionProposal(**values)  # type: ignore[arg-type]


def approval(**overrides: object) -> ApprovalRequest:
    values: dict[str, object] = {
        "approval_id": "approval-1",
        "action_id": "action-1",
        "action_type": ManualActionType.PLACE_SPOT_ORDER,
    }
    values.update(overrides)
    return ApprovalRequest(**values)  # type: ignore[arg-type]


def test_manual_approval_contracts_reject_missing_or_authorizing_values() -> None:
    for overrides, message in (
        ({"action_id": " "}, "identity is required"),
        ({"suggested_notional_usdt": Decimal("-1")}, "must be non-negative"),
        ({"blockers": (" ",)}, "cannot be empty"),
        ({"execution_allowed": True}, "cannot grant execution authority"),
    ):
        with pytest.raises(ValueError, match=message):
            action(**overrides)
    for overrides, message in (
        ({"approval_id": " "}, "identity is required"),
        ({"execution_allowed": True}, "cannot grant execution authority"),
    ):
        with pytest.raises(ValueError, match=message):
            approval(**overrides)


def test_approval_queue_record_rejects_mismatched_or_unauthorized_binding() -> None:
    base_action = action()
    base_approval = approval()
    record = ApprovalQueueRecord(base_action, base_approval, NOW)
    assert record.approval == base_approval
    with pytest.raises(ValueError, match="timezone-aware"):
        ApprovalQueueRecord(base_action, base_approval, datetime(2026, 9, 15))
    with pytest.raises(ValueError, match="action IDs must match"):
        ApprovalQueueRecord(base_action, approval(action_id="other"), NOW)
    with pytest.raises(ValueError, match="action types must match"):
        ApprovalQueueRecord(
            base_action,
            approval(action_type=ManualActionType.CANCEL_ORDER),
            NOW,
        )


def test_local_approval_queue_persists_idempotently_and_rejects_invalid_records(
    tmp_path: Path,
) -> None:
    queue = LocalApprovalQueue(tmp_path / "approvals.jsonl")
    assert queue.records() == ()
    assert queue.by_action_id("action-1") is None
    assert queue.resolve_execution_authorization(" ") is None

    first = queue.enqueue(action(), created_at=NOW)
    assert queue.enqueue(action(), created_at=NOW) == first
    assert queue.by_action_id(" action-1 ") == first
    assert queue.resolve_execution_authorization("unknown") is None

    with pytest.raises(ValueError, match="must be an object"):
        queue._record(())
    with pytest.raises(ValueError, match="payload is invalid"):
        queue._record({"action": {}, "approval": ()})

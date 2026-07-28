"""Paper restart reconciliation and proposal-only risk-flow tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.events import DiskEventJournal, DomainEvent
from ai4binance.execution import assess_pending_cancel, recover_paper_orders
from ai4binance.execution.order_state import OrderStateMachine, OrderStatus
from ai4binance.portfolio import RiskFlowPolicy, RiskFlowSnapshot, assess_risk_flow
from ai4binance.portfolio.reconciliation import OpenOrderView

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def order_journal(path: Path, order_id: str = "paper-1") -> DiskEventJournal:
    journal = DiskEventJournal(path, durable=False)
    submitted = DomainEvent.create(
        event_id=f"{order_id}-1",
        aggregate_id=order_id,
        event_type="ORDER_SUBMITTED",
        sequence=1,
        occurred_at=NOW,
        payload=(("action", "BUY"), ("quantity", "2"), ("symbol", "HOTUSDT")),
    )
    accepted = DomainEvent.create(
        event_id=f"{order_id}-2",
        aggregate_id=order_id,
        event_type="ORDER_ACCEPTED",
        sequence=2,
        occurred_at=NOW + timedelta(seconds=1),
        previous_hash=submitted.event_hash,
    )
    journal.append(submitted)
    journal.append(accepted)
    return journal


def test_paper_orders_restart_and_reconcile_read_only_snapshot(tmp_path: Path) -> None:
    journal = order_journal(tmp_path / "paper-1.jsonl")
    report = recover_paper_orders(
        (journal,),
        exchange_open_orders=(OpenOrderView("paper-1", "HOTUSDT", Decimal("2")),),
    )
    assert report.recovery_complete is True
    assert report.orders[0].status is OrderStatus.ACCEPTED
    assert report.reconciliation is not None
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_paper_recovery_quarantines_unknown_and_missing_evidence(
    tmp_path: Path,
) -> None:
    journal = order_journal(tmp_path / "paper-1.jsonl")
    missing_snapshot = recover_paper_orders((journal,))
    assert missing_snapshot.blockers == ("EXCHANGE_OPEN_ORDER_SNAPSHOT_NOT_SUPPLIED",)
    unknown = recover_paper_orders(
        (journal,),
        exchange_open_orders=(OpenOrderView("unknown", "HOTUSDT", Decimal("1")),),
    )
    assert unknown.quarantined_order_ids == ("unknown",)
    assert "UNKNOWN_EXCHANGE_OPEN_ORDER" in unknown.blockers

    invalid = DiskEventJournal(tmp_path / "invalid.jsonl", durable=False)
    invalid.path.write_text("broken\n", encoding="utf-8")
    degraded = recover_paper_orders((invalid,))
    assert degraded.blockers == ("PAPER_ORDER_JOURNAL_INVALID",)


def test_pending_cancel_transition_timeout_and_late_fill(tmp_path: Path) -> None:
    journal = order_journal(tmp_path / "paper-1.jsonl")
    accepted = journal.load()[-1]
    requested = DomainEvent.create(
        event_id="paper-1-3",
        aggregate_id="paper-1",
        event_type="ORDER_CANCEL_REQUESTED",
        sequence=3,
        occurred_at=NOW + timedelta(seconds=2),
        previous_hash=accepted.event_hash,
    )
    state = OrderStateMachine.apply(OrderStateMachine.replay(journal.load()), requested)
    assert state.status is OrderStatus.PENDING_CANCEL
    pending = assess_pending_cancel(
        state,
        cancel_requested_at=NOW + timedelta(seconds=2),
        observed_at=NOW + timedelta(seconds=40),
    )
    assert pending.blockers == ("PENDING_CANCEL_TIMEOUT",)
    late_fill = DomainEvent.create(
        event_id="paper-1-4",
        aggregate_id="paper-1",
        event_type="ORDER_FILLED",
        sequence=4,
        occurred_at=NOW + timedelta(seconds=41),
        payload=(("fill_price", "100"), ("fill_quantity", "2")),
        previous_hash=requested.event_hash,
    )
    assert OrderStateMachine.apply(state, late_fill).status is OrderStatus.FILLED


def test_risk_flow_allows_small_proposal_and_blocks_every_limit() -> None:
    allowed = assess_risk_flow(
        RiskFlowSnapshot(NOW),
        setup_id="support-reclaim",
        proposed_notional_usdt=Decimal("50"),
    )
    assert allowed.approved_for_proposal is True
    assert allowed.execution_allowed is False

    policy = RiskFlowPolicy(
        maximum_proposals_per_minute=1,
        maximum_active_orders=1,
        maximum_cancellations_per_hour=1,
        maximum_consecutive_rejections=1,
        maximum_daily_turnover_usdt=Decimal("100"),
        same_setup_cooldown=timedelta(minutes=15),
    )
    blocked = assess_risk_flow(
        RiskFlowSnapshot(
            NOW,
            proposal_times=(NOW,),
            cancellation_times=(NOW,),
            consecutive_rejections=1,
            active_order_count=1,
            daily_turnover_usdt=Decimal("90"),
            last_setup_times=(("support-reclaim", NOW),),
        ),
        setup_id="support-reclaim",
        proposed_notional_usdt=Decimal("20"),
        policy=policy,
    )
    assert len(blocked.blockers) == 6


def test_recovery_and_risk_flow_contracts_reject_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="policy"):
        RiskFlowPolicy(maximum_active_orders=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        RiskFlowSnapshot(NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="notional"):
        assess_risk_flow(
            RiskFlowSnapshot(NOW),
            setup_id="setup",
            proposed_notional_usdt=Decimal("0"),
        )
    journal = order_journal(tmp_path / "paper-1.jsonl")
    state = OrderStateMachine.replay(journal.load())
    with pytest.raises(ValueError, match="chronology"):
        assess_pending_cancel(
            state,
            cancel_requested_at=NOW,
            observed_at=NOW - timedelta(seconds=1),
        )

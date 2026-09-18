"""Fail-closed paper-order restart recovery and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ai4binance.events import DiskEventJournal, EventJournalCorruptionError
from ai4binance.execution.order_state import OrderState, OrderStateMachine, OrderStatus
from ai4binance.portfolio.reconciliation import (
    OpenOrderView,
    ReconciliationReport,
    reconcile_open_orders,
)

_OPEN_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTED,
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.PENDING_CANCEL,
    }
)


@dataclass(frozen=True, slots=True)
class PaperOrderRecoveryReport:
    """Restart result that quarantines unknown evidence and grants no authority."""

    orders: tuple[OrderState, ...]
    reconciliation: ReconciliationReport | None
    quarantined_order_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    recovery_complete: bool
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.recovery_complete and self.blockers:
            raise ValueError("complete paper recovery cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("paper recovery cannot authorize execution")


@dataclass(frozen=True, slots=True)
class PendingCancelAssessment:
    timed_out: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False


def recover_paper_orders(
    journals: tuple[DiskEventJournal, ...],
    *,
    exchange_open_orders: tuple[OpenOrderView, ...] | None = None,
) -> PaperOrderRecoveryReport:
    """Rebuild one aggregate per journal and compare an optional read-only snapshot."""
    orders: list[OrderState] = []
    quarantined: list[str] = []
    blockers: list[str] = []
    identities: set[str] = set()
    for journal in journals:
        try:
            events = journal.load()
            if not events:
                blockers.append("PAPER_ORDER_JOURNAL_EMPTY")
                continue
            aggregate_ids = {event.aggregate_id for event in events}
            if len(aggregate_ids) != 1:
                raise ValueError("paper order journal must contain one aggregate")
            state = OrderStateMachine.replay(events)
            if state.order_id in identities:
                quarantined.append(state.order_id)
                blockers.append("DUPLICATE_PAPER_ORDER_IDENTITY")
                continue
            identities.add(state.order_id)
            orders.append(state)
        except (EventJournalCorruptionError, ValueError):
            blockers.append("PAPER_ORDER_JOURNAL_INVALID")

    reconciliation: ReconciliationReport | None = None
    local_open = tuple(
        OpenOrderView(state.order_id, state.symbol, state.remaining_quantity)
        for state in orders
        if state.status in _OPEN_STATUSES
    )
    if exchange_open_orders is None:
        if local_open:
            blockers.append("EXCHANGE_OPEN_ORDER_SNAPSHOT_NOT_SUPPLIED")
    else:
        reconciliation = reconcile_open_orders(local_open, exchange_open_orders)
        blockers.extend(reconciliation.blockers)
        quarantined.extend(reconciliation.unknown_on_exchange)
    unique_blockers = tuple(dict.fromkeys(blockers))
    return PaperOrderRecoveryReport(
        tuple(sorted(orders, key=lambda item: item.order_id)),
        reconciliation,
        tuple(sorted(set(quarantined))),
        unique_blockers,
        not unique_blockers,
    )


def assess_pending_cancel(
    state: OrderState,
    *,
    cancel_requested_at: datetime,
    observed_at: datetime,
    timeout: timedelta = timedelta(seconds=30),
) -> PendingCancelAssessment:
    """Flag a cancel request that remained unresolved beyond its bounded timeout."""
    for value in (cancel_requested_at, observed_at):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("pending-cancel timestamps must be timezone-aware")
    if timeout <= timedelta(0) or observed_at < cancel_requested_at:
        raise ValueError("pending-cancel timeout or chronology is invalid")
    if state.status is not OrderStatus.PENDING_CANCEL:
        return PendingCancelAssessment(False, ())
    timed_out = observed_at - cancel_requested_at > timeout
    return PendingCancelAssessment(
        timed_out,
        ("PENDING_CANCEL_TIMEOUT",) if timed_out else (),
    )

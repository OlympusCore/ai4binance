"""Typed connector readiness gates with no exchange-write authority."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConnectorReadinessInput:
    """Point-in-time evidence required before research may trust a connector."""

    api_reachable: bool
    server_time_synchronized: bool
    exchange_info_fresh: bool
    trading_rules_loaded: bool
    order_book_snapshot_ready: bool
    stream_connected: bool
    sequence_contiguous: bool
    rest_backfill_complete: bool
    private_state_required: bool = False
    wallet_known: bool = False
    open_orders_reconciled: bool = False


@dataclass(frozen=True, slots=True)
class ConnectorReadinessAssessment:
    """Fail-closed readiness result; it cannot authorize an order."""

    ready_for_research: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.ready_for_research == bool(self.blockers):
            raise ValueError("connector readiness and blockers disagree")
        if self.execution_allowed:
            raise ValueError("connector readiness cannot authorize execution")


def assess_connector_readiness(
    evidence: ConnectorReadinessInput,
) -> ConnectorReadinessAssessment:
    """Evaluate public readiness and optional private-state completeness."""
    checks = (
        (evidence.api_reachable, "CONNECTOR_API_UNREACHABLE"),
        (evidence.server_time_synchronized, "CONNECTOR_TIME_UNSYNCHRONIZED"),
        (evidence.exchange_info_fresh, "EXCHANGE_INFO_STALE"),
        (evidence.trading_rules_loaded, "TRADING_RULES_UNAVAILABLE"),
        (evidence.order_book_snapshot_ready, "ORDER_BOOK_SNAPSHOT_UNAVAILABLE"),
        (evidence.stream_connected, "PUBLIC_STREAM_DISCONNECTED"),
        (evidence.sequence_contiguous, "STREAM_SEQUENCE_GAP"),
        (evidence.rest_backfill_complete, "REST_BACKFILL_INCOMPLETE"),
    )
    blockers = [code for passed, code in checks if not passed]
    if evidence.private_state_required:
        if not evidence.wallet_known:
            blockers.append("WALLET_STATE_UNKNOWN")
        if not evidence.open_orders_reconciled:
            blockers.append("OPEN_ORDERS_NOT_RECONCILED")
    return ConnectorReadinessAssessment(not blockers, tuple(blockers))

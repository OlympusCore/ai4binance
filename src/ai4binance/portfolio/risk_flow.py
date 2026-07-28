"""Proposal-only activity, cancellation, rejection, and cooldown risk gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RiskFlowPolicy:
    maximum_proposals_per_minute: int = 10
    maximum_active_orders: int = 5
    maximum_cancellations_per_hour: int = 20
    maximum_consecutive_rejections: int = 3
    maximum_daily_turnover_usdt: Decimal = Decimal("1000")
    same_setup_cooldown: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        counts = (
            self.maximum_proposals_per_minute,
            self.maximum_active_orders,
            self.maximum_cancellations_per_hour,
            self.maximum_consecutive_rejections,
        )
        if (
            min(counts) < 1
            or self.maximum_daily_turnover_usdt <= ZERO
            or self.same_setup_cooldown <= timedelta(0)
        ):
            raise ValueError("risk-flow policy is invalid")


@dataclass(frozen=True, slots=True)
class RiskFlowSnapshot:
    observed_at: datetime
    proposal_times: tuple[datetime, ...] = ()
    cancellation_times: tuple[datetime, ...] = ()
    consecutive_rejections: int = 0
    active_order_count: int = 0
    daily_turnover_usdt: Decimal = ZERO
    last_setup_times: tuple[tuple[str, datetime], ...] = ()

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("risk-flow observed_at must be timezone-aware")
        timestamps = (
            *self.proposal_times,
            *self.cancellation_times,
            *(value for _key, value in self.last_setup_times),
        )
        if any(
            value.tzinfo is None
            or value.utcoffset() is None
            or value > self.observed_at
            for value in timestamps
        ):
            raise ValueError("risk-flow timestamps are invalid")
        if (
            min(self.consecutive_rejections, self.active_order_count) < 0
            or self.daily_turnover_usdt < ZERO
        ):
            raise ValueError("risk-flow counters are invalid")
        keys = tuple(key for key, _value in self.last_setup_times)
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("risk-flow setup identities must be unique")


@dataclass(frozen=True, slots=True)
class RiskFlowAssessment:
    setup_id: str
    approved_for_proposal: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False


def assess_risk_flow(
    snapshot: RiskFlowSnapshot,
    *,
    setup_id: str,
    proposed_notional_usdt: Decimal,
    policy: RiskFlowPolicy | None = None,
) -> RiskFlowAssessment:
    """Reject excessive activity without mutating counters or risk limits."""
    if not setup_id.strip() or proposed_notional_usdt <= ZERO:
        raise ValueError("risk-flow proposal identity and notional are required")
    active_policy = policy or RiskFlowPolicy()
    now = snapshot.observed_at
    recent_proposals = sum(
        value >= now - timedelta(minutes=1) for value in snapshot.proposal_times
    )
    recent_cancellations = sum(
        value >= now - timedelta(hours=1) for value in snapshot.cancellation_times
    )
    last_setups = dict(snapshot.last_setup_times)
    last_setup = last_setups.get(setup_id)
    checks = (
        (
            recent_proposals >= active_policy.maximum_proposals_per_minute,
            "PROPOSAL_RATE_LIMIT_EXCEEDED",
        ),
        (
            snapshot.active_order_count >= active_policy.maximum_active_orders,
            "ACTIVE_ORDER_LIMIT_EXCEEDED",
        ),
        (
            recent_cancellations >= active_policy.maximum_cancellations_per_hour,
            "CANCEL_RATE_LIMIT_EXCEEDED",
        ),
        (
            snapshot.consecutive_rejections
            >= active_policy.maximum_consecutive_rejections,
            "REPEATED_ORDER_REJECTION_CIRCUIT_OPEN",
        ),
        (
            snapshot.daily_turnover_usdt + proposed_notional_usdt
            > active_policy.maximum_daily_turnover_usdt,
            "DAILY_TURNOVER_LIMIT_EXCEEDED",
        ),
        (
            last_setup is not None
            and now - last_setup < active_policy.same_setup_cooldown,
            "SAME_SETUP_COOLDOWN_ACTIVE",
        ),
    )
    blockers = tuple(code for failed, code in checks if failed)
    return RiskFlowAssessment(setup_id, not blockers, blockers)

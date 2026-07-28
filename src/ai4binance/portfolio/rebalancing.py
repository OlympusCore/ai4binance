"""Immutable proposal-only Spot inventory bucket and rebalancing policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")
ONE = Decimal("1")


class RebalanceAction(StrEnum):
    HOLD = "HOLD_REVIEW"
    SELL = "SELL_REVIEW"
    BUY = "REBUY_REVIEW"
    BLOCKED = "REBALANCE_BLOCKED"


@dataclass(frozen=True, slots=True)
class InventoryBuckets:
    core_units: Decimal
    strategic_units: Decimal
    tactical_units: Decimal
    cash_quote: Decimal
    reserved_cash_quote: Decimal = ZERO
    pending_rebuy_cash_quote: Decimal = ZERO
    last_stage: int = 0
    last_side: str = "NONE"
    last_stage_clock: int = -1_000_000

    def __post_init__(self) -> None:
        values = (
            self.core_units,
            self.strategic_units,
            self.tactical_units,
            self.cash_quote,
            self.reserved_cash_quote,
            self.pending_rebuy_cash_quote,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("inventory bucket values must be finite and non-negative")
        if self.reserved_cash_quote > self.cash_quote:
            raise ValueError("reserved cash cannot exceed cash balance")
        if self.last_stage < 0 or self.last_side not in {"NONE", "BUY", "SELL"}:
            raise ValueError("inventory stage state is invalid")

    @property
    def total_units(self) -> Decimal:
        return self.core_units + self.strategic_units + self.tactical_units

    @property
    def rotation_units(self) -> Decimal:
        return self.strategic_units + self.tactical_units

    @property
    def available_cash_quote(self) -> Decimal:
        return self.cash_quote - self.reserved_cash_quote


@dataclass(frozen=True, slots=True)
class RebalancePolicy:
    target_asset_ratio: Decimal
    hysteresis_ratio: Decimal = Decimal("0.02")
    minimum_notional_quote: Decimal = Decimal("10")
    minimum_core_ratio: Decimal = Decimal("0.60")
    maximum_trade_ratio: Decimal = Decimal("0.15")
    fee_ratio: Decimal = Decimal("0.001")
    cooldown_candles: int = 4
    maximum_stage_jump: int = 1

    def __post_init__(self) -> None:
        ratios = (
            self.target_asset_ratio,
            self.hysteresis_ratio,
            self.minimum_core_ratio,
            self.maximum_trade_ratio,
            self.fee_ratio,
        )
        if any(not value.is_finite() or value < ZERO for value in ratios):
            raise ValueError("rebalance ratios must be finite and non-negative")
        if not ZERO <= self.target_asset_ratio <= ONE:
            raise ValueError("target asset ratio must be between zero and one")
        if not ZERO <= self.minimum_core_ratio <= ONE:
            raise ValueError("minimum core ratio must be between zero and one")
        if not ZERO < self.maximum_trade_ratio <= ONE:
            raise ValueError("maximum trade ratio must be positive and at most one")
        if self.minimum_notional_quote <= ZERO:
            raise ValueError("minimum notional must be positive")
        if self.cooldown_candles < 0 or self.maximum_stage_jump < 0:
            raise ValueError("stage policy bounds are invalid")


@dataclass(frozen=True, slots=True)
class RebalanceProposal:
    action: RebalanceAction
    current_asset_ratio: Decimal
    target_asset_ratio: Decimal
    proposed_units: Decimal
    proposed_notional_quote: Decimal
    estimated_fee_quote: Decimal
    stage: int
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        values = (
            self.current_asset_ratio,
            self.target_asset_ratio,
            self.proposed_units,
            self.proposed_notional_quote,
            self.estimated_fee_quote,
        )
        if (
            any(not value.is_finite() or value < ZERO for value in values)
            or self.current_asset_ratio > ONE
            or self.target_asset_ratio > ONE
            or self.stage < 0
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("rebalance proposal is invalid")


@dataclass(frozen=True, slots=True)
class RebalanceProposalEngine:
    """Calculate one review proposal without changing wallet or bucket state."""

    def propose(
        self,
        buckets: InventoryBuckets,
        policy: RebalancePolicy,
        *,
        price_quote: Decimal,
        clock_index: int,
        requested_stage: int,
        risk_blockers: tuple[str, ...] = (),
    ) -> RebalanceProposal:
        if not price_quote.is_finite() or price_quote <= ZERO:
            raise ValueError("rebalance price must be finite and positive")
        if clock_index < 0 or requested_stage < 0:
            raise ValueError("rebalance clock and stage must be non-negative")
        asset_value = buckets.total_units * price_quote
        total_value = asset_value + buckets.cash_quote
        current_ratio = asset_value / total_value if total_value > ZERO else ZERO
        delta_ratio = policy.target_asset_ratio - current_ratio
        blockers = list(risk_blockers)
        if total_value <= ZERO:
            blockers.append("PORTFOLIO_VALUE_UNAVAILABLE")
        if abs(delta_ratio) <= policy.hysteresis_ratio:
            return self._result(
                RebalanceAction.HOLD,
                current_ratio,
                policy,
                requested_stage,
                blockers or ["REBALANCE_HYSTERESIS_BAND"],
            )
        elapsed = clock_index - buckets.last_stage_clock
        if elapsed < policy.cooldown_candles:
            blockers.append("REBALANCE_COOLDOWN_ACTIVE")
        if abs(requested_stage - buckets.last_stage) > policy.maximum_stage_jump:
            blockers.append("REBALANCE_STAGE_JUMP_BLOCKED")
        side = "BUY" if delta_ratio > ZERO else "SELL"
        if buckets.last_side not in {"NONE", side} and requested_stage > 1:
            blockers.append("REBALANCE_SIDE_TRANSITION_BLOCKED")
        if blockers:
            return self._result(
                RebalanceAction.BLOCKED,
                current_ratio,
                policy,
                requested_stage,
                blockers,
            )
        desired_notional = abs(delta_ratio) * total_value
        maximum_notional = policy.maximum_trade_ratio * total_value
        notional = min(desired_notional, maximum_notional)
        if side == "SELL":
            notional = min(notional, buckets.rotation_units * price_quote)
        else:
            notional = min(notional, buckets.available_cash_quote)
        if notional < policy.minimum_notional_quote:
            return self._result(
                RebalanceAction.BLOCKED,
                current_ratio,
                policy,
                requested_stage,
                ["REBALANCE_MINIMUM_NOTIONAL_BLOCKED"],
            )
        units = notional / price_quote
        return RebalanceProposal(
            action=(RebalanceAction.BUY if side == "BUY" else RebalanceAction.SELL),
            current_asset_ratio=current_ratio,
            target_asset_ratio=policy.target_asset_ratio,
            proposed_units=units,
            proposed_notional_quote=notional,
            estimated_fee_quote=notional * policy.fee_ratio,
            stage=requested_stage,
            blockers=(),
        )

    @staticmethod
    def _result(
        action: RebalanceAction,
        current_ratio: Decimal,
        policy: RebalancePolicy,
        stage: int,
        blockers: list[str],
    ) -> RebalanceProposal:
        return RebalanceProposal(
            action=action,
            current_asset_ratio=current_ratio,
            target_asset_ratio=policy.target_asset_ratio,
            proposed_units=ZERO,
            proposed_notional_quote=ZERO,
            estimated_fee_quote=ZERO,
            stage=stage,
            blockers=tuple(dict.fromkeys(blockers)),
        )

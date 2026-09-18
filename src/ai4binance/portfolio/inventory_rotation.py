"""Proposal-only Spot inventory SELL/rebuy lifecycle state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ai4binance.portfolio.rebalancing import InventoryBuckets

ZERO = Decimal("0")
ONE = Decimal("1")


class InventoryRotationPhase(StrEnum):
    IDLE = "IDLE"
    SELL_PROPOSED = "SELL_PROPOSED"
    AWAITING_REBUY = "AWAITING_REBUY"
    REBUY_PROPOSED = "REBUY_PROPOSED"
    CLOSED = "CLOSED"


class InventoryRotationAction(StrEnum):
    HOLD = "HOLD_REVIEW"
    SELL = "SELL_REVIEW"
    REBUY = "REBUY_REVIEW"
    BLOCKED = "ROTATION_BLOCKED"


@dataclass(frozen=True, slots=True)
class InventoryRotationState:
    cycle_id: str
    phase: InventoryRotationPhase
    updated_at: datetime
    stage: int = 0
    sold_units: Decimal = ZERO
    proceeds_quote: Decimal = ZERO
    remaining_rebuy_quote: Decimal = ZERO
    pending_units: Decimal = ZERO
    pending_notional_quote: Decimal = ZERO
    reference_sell_price: Decimal | None = None
    reference_rebuy_price: Decimal | None = None
    average_rotation_cost_quote: Decimal | None = None
    rebuy_band_lower_quote: Decimal | None = None
    rebuy_band_upper_quote: Decimal | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        if not self.cycle_id.strip():
            raise ValueError("inventory rotation cycle identity is required")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("inventory rotation timestamp must be timezone-aware")
        numeric = (
            self.sold_units,
            self.proceeds_quote,
            self.remaining_rebuy_quote,
            self.pending_units,
            self.pending_notional_quote,
        )
        if any(not value.is_finite() or value < ZERO for value in numeric):
            raise ValueError("inventory rotation state values must be non-negative")
        if self.stage < 0 or self.revision < 0:
            raise ValueError("inventory rotation counters cannot be negative")
        if self.remaining_rebuy_quote > self.proceeds_quote:
            raise ValueError("remaining rebuy cash cannot exceed realized proceeds")
        optional_prices = (
            self.reference_sell_price,
            self.reference_rebuy_price,
            self.average_rotation_cost_quote,
            self.rebuy_band_lower_quote,
            self.rebuy_band_upper_quote,
        )
        if any(value is not None and value <= ZERO for value in optional_prices):
            raise ValueError("inventory rotation reference prices must be positive")
        if (
            self.rebuy_band_lower_quote is not None
            and self.rebuy_band_upper_quote is not None
            and self.rebuy_band_lower_quote >= self.rebuy_band_upper_quote
        ):
            raise ValueError("inventory rebuy band is invalid")

    @classmethod
    def new(cls, cycle_id: str, timestamp: datetime) -> InventoryRotationState:
        return cls(cycle_id, InventoryRotationPhase.IDLE, timestamp)


@dataclass(frozen=True, slots=True)
class InventoryRotationPolicy:
    maximum_sell_ratio_of_rotation: Decimal = Decimal("0.25")
    maximum_rebuy_ratio_per_stage: Decimal = Decimal("0.50")
    minimum_notional_quote: Decimal = Decimal("10")
    fee_ratio: Decimal = Decimal("0.001")
    resistance_tolerance_ratio: Decimal = Decimal("0.01")
    support_tolerance_ratio: Decimal = Decimal("0.01")
    minimum_sell_profit_ratio: Decimal = Decimal("0.03")
    minimum_rebuy_discount_ratio: Decimal = Decimal("0.05")
    maximum_rebuy_discount_ratio: Decimal = Decimal("0.30")

    def __post_init__(self) -> None:
        ratios = (
            self.maximum_sell_ratio_of_rotation,
            self.maximum_rebuy_ratio_per_stage,
            self.fee_ratio,
            self.resistance_tolerance_ratio,
            self.support_tolerance_ratio,
            self.minimum_sell_profit_ratio,
            self.minimum_rebuy_discount_ratio,
            self.maximum_rebuy_discount_ratio,
        )
        if any(not value.is_finite() or value < ZERO for value in ratios):
            raise ValueError(
                "inventory rotation ratios must be finite and non-negative"
            )
        if not ZERO < self.maximum_sell_ratio_of_rotation <= ONE:
            raise ValueError("inventory sell ratio must be in (0, 1]")
        if not ZERO < self.maximum_rebuy_ratio_per_stage <= ONE:
            raise ValueError("inventory rebuy ratio must be in (0, 1]")
        if self.minimum_notional_quote <= ZERO:
            raise ValueError("inventory rotation minimum notional must be positive")
        if not (
            ZERO
            < self.minimum_rebuy_discount_ratio
            < self.maximum_rebuy_discount_ratio
            < ONE
        ):
            raise ValueError("inventory rebuy discount band is invalid")


@dataclass(frozen=True, slots=True)
class InventoryRotationContext:
    price_quote: Decimal
    resistance_quote: Decimal
    support_quote: Decimal
    sell_trigger_confirmed: bool
    support_reclaimed: bool
    average_rotation_cost_quote: Decimal | None = None
    risk_blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        prices = (self.price_quote, self.resistance_quote, self.support_quote)
        if any(not value.is_finite() or value <= ZERO for value in prices):
            raise ValueError("inventory rotation prices must be finite and positive")
        if self.support_quote >= self.resistance_quote:
            raise ValueError("rotation support must be below resistance")
        if self.average_rotation_cost_quote is not None and (
            not self.average_rotation_cost_quote.is_finite()
            or self.average_rotation_cost_quote <= ZERO
        ):
            raise ValueError("rotation cost basis must be finite and positive")


@dataclass(frozen=True, slots=True)
class InventoryRotationProposal:
    action: InventoryRotationAction
    proposed_units: Decimal
    proposed_notional_quote: Decimal
    estimated_fee_quote: Decimal
    current_state: InventoryRotationState
    next_state: InventoryRotationState
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("inventory rotation proposal cannot authorize execution")
        if (
            self.action
            in {
                InventoryRotationAction.SELL,
                InventoryRotationAction.REBUY,
            }
            and self.blockers
        ):
            raise ValueError("actionable review proposal cannot contain blockers")


@dataclass(frozen=True, slots=True)
class InventoryRotationProposalEngine:
    """Propose one bounded lifecycle transition without changing a wallet."""

    def review(
        self,
        state: InventoryRotationState,
        buckets: InventoryBuckets,
        context: InventoryRotationContext,
        *,
        policy: InventoryRotationPolicy | None = None,
    ) -> InventoryRotationProposal:
        selected_policy = policy or InventoryRotationPolicy()
        if context.risk_blockers:
            return self._blocked(state, context.risk_blockers)
        if state.phase in {
            InventoryRotationPhase.SELL_PROPOSED,
            InventoryRotationPhase.REBUY_PROPOSED,
        }:
            return self._hold(state, ("MANUAL_FILL_CONFIRMATION_REQUIRED",))
        if state.phase is InventoryRotationPhase.CLOSED:
            return self._hold(state, ("ROTATION_CYCLE_CLOSED",))
        if state.phase is InventoryRotationPhase.IDLE:
            return self._sell_review(state, buckets, context, selected_policy)
        return self._rebuy_review(state, buckets, context, selected_policy)

    def _sell_review(
        self,
        state: InventoryRotationState,
        buckets: InventoryBuckets,
        context: InventoryRotationContext,
        policy: InventoryRotationPolicy,
    ) -> InventoryRotationProposal:
        blockers: list[str] = []
        if not context.sell_trigger_confirmed:
            blockers.append("INVENTORY_SELL_TRIGGER_NOT_CONFIRMED")
        minimum_price = context.resistance_quote * (
            ONE - policy.resistance_tolerance_ratio
        )
        if context.price_quote < minimum_price:
            blockers.append("INVENTORY_RESISTANCE_NOT_REACHED")
        if buckets.rotation_units <= ZERO:
            blockers.append("ROTATION_INVENTORY_UNAVAILABLE")
        if context.average_rotation_cost_quote is None:
            blockers.append("ROTATION_COST_BASIS_UNAVAILABLE")
        elif context.price_quote < context.average_rotation_cost_quote * (
            ONE + policy.minimum_sell_profit_ratio
        ):
            blockers.append("ROTATION_SELL_BELOW_COST_PROFIT_FLOOR")
        if blockers:
            return self._hold(state, tuple(blockers))
        units = buckets.rotation_units * policy.maximum_sell_ratio_of_rotation
        notional = units * context.price_quote
        if notional < policy.minimum_notional_quote:
            return self._blocked(state, ("ROTATION_MINIMUM_NOTIONAL_BLOCKED",))
        next_state = replace(
            state,
            phase=InventoryRotationPhase.SELL_PROPOSED,
            pending_units=units,
            pending_notional_quote=notional,
            reference_sell_price=context.price_quote,
            average_rotation_cost_quote=context.average_rotation_cost_quote,
            revision=state.revision + 1,
        )
        return InventoryRotationProposal(
            InventoryRotationAction.SELL,
            units,
            notional,
            notional * policy.fee_ratio,
            state,
            next_state,
            (),
        )

    def _rebuy_review(
        self,
        state: InventoryRotationState,
        buckets: InventoryBuckets,
        context: InventoryRotationContext,
        policy: InventoryRotationPolicy,
    ) -> InventoryRotationProposal:
        blockers: list[str] = []
        if not context.support_reclaimed:
            blockers.append("INVENTORY_REBUY_RECLAIM_NOT_CONFIRMED")
        maximum_price = context.support_quote * (ONE + policy.support_tolerance_ratio)
        if context.price_quote > maximum_price:
            blockers.append("INVENTORY_REBUY_PRICE_ABOVE_SUPPORT_BAND")
        if state.rebuy_band_lower_quote is None or state.rebuy_band_upper_quote is None:
            blockers.append("INVENTORY_REBUY_BAND_UNAVAILABLE")
        elif context.price_quote < state.rebuy_band_lower_quote:
            blockers.append("INVENTORY_REBUY_PRICE_BELOW_BAND")
        elif context.price_quote > state.rebuy_band_upper_quote:
            blockers.append("INVENTORY_REBUY_PRICE_ABOVE_SELL_DISCOUNT_BAND")
        available = min(state.remaining_rebuy_quote, buckets.available_cash_quote)
        if available <= ZERO:
            blockers.append("INVENTORY_REBUY_CASH_UNAVAILABLE")
        if blockers:
            return self._hold(state, tuple(blockers))
        notional = available * policy.maximum_rebuy_ratio_per_stage
        if notional < policy.minimum_notional_quote:
            return self._blocked(state, ("ROTATION_MINIMUM_NOTIONAL_BLOCKED",))
        units = notional / context.price_quote
        next_state = replace(
            state,
            phase=InventoryRotationPhase.REBUY_PROPOSED,
            pending_units=units,
            pending_notional_quote=notional,
            reference_rebuy_price=context.price_quote,
            revision=state.revision + 1,
        )
        return InventoryRotationProposal(
            InventoryRotationAction.REBUY,
            units,
            notional,
            notional * policy.fee_ratio,
            state,
            next_state,
            (),
        )

    @staticmethod
    def confirm_sell(
        state: InventoryRotationState,
        *,
        filled_units: Decimal,
        realized_proceeds_quote: Decimal,
        confirmed_at: datetime,
        policy: InventoryRotationPolicy | None = None,
    ) -> InventoryRotationState:
        if state.phase is not InventoryRotationPhase.SELL_PROPOSED:
            raise ValueError("sell confirmation requires a pending sell proposal")
        if not ZERO < filled_units <= state.pending_units:
            raise ValueError("confirmed sell units exceed the proposal")
        if not ZERO < realized_proceeds_quote <= state.pending_notional_quote:
            raise ValueError("confirmed sell proceeds exceed the proposal")
        selected_policy = policy or InventoryRotationPolicy()
        average_sell_price = realized_proceeds_quote / filled_units
        return replace(
            state,
            phase=InventoryRotationPhase.AWAITING_REBUY,
            updated_at=confirmed_at,
            sold_units=filled_units,
            proceeds_quote=realized_proceeds_quote,
            remaining_rebuy_quote=realized_proceeds_quote,
            reference_sell_price=average_sell_price,
            rebuy_band_lower_quote=average_sell_price
            * (ONE - selected_policy.maximum_rebuy_discount_ratio),
            rebuy_band_upper_quote=average_sell_price
            * (ONE - selected_policy.minimum_rebuy_discount_ratio),
            pending_units=ZERO,
            pending_notional_quote=ZERO,
            stage=1,
            revision=state.revision + 1,
        )

    @staticmethod
    def confirm_rebuy(
        state: InventoryRotationState,
        *,
        quote_spent: Decimal,
        confirmed_at: datetime,
    ) -> InventoryRotationState:
        if state.phase is not InventoryRotationPhase.REBUY_PROPOSED:
            raise ValueError("rebuy confirmation requires a pending proposal")
        if (
            not ZERO
            < quote_spent
            <= min(state.pending_notional_quote, state.remaining_rebuy_quote)
        ):
            raise ValueError("confirmed rebuy spend exceeds available proposal cash")
        remaining = state.remaining_rebuy_quote - quote_spent
        phase = (
            InventoryRotationPhase.CLOSED
            if remaining == ZERO
            else InventoryRotationPhase.AWAITING_REBUY
        )
        return replace(
            state,
            phase=phase,
            updated_at=confirmed_at,
            remaining_rebuy_quote=remaining,
            pending_units=ZERO,
            pending_notional_quote=ZERO,
            stage=state.stage + 1,
            revision=state.revision + 1,
        )

    @staticmethod
    def _hold(
        state: InventoryRotationState, blockers: tuple[str, ...]
    ) -> InventoryRotationProposal:
        return InventoryRotationProposal(
            InventoryRotationAction.HOLD,
            ZERO,
            ZERO,
            ZERO,
            state,
            state,
            blockers,
        )

    @staticmethod
    def _blocked(
        state: InventoryRotationState, blockers: tuple[str, ...]
    ) -> InventoryRotationProposal:
        return InventoryRotationProposal(
            InventoryRotationAction.BLOCKED,
            ZERO,
            ZERO,
            ZERO,
            state,
            state,
            blockers,
        )

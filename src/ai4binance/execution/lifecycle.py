"""Persistent paper-position lifecycle with staged exits and closure review."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ai4binance.execution.paper import ExitReason, PaperOrder, PaperOrderStatus
from ai4binance.execution.trailing import update_long_trailing_stop
from ai4binance.schemas import OHLCVCandle

ZERO = Decimal("0")
ONE = Decimal("1")


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class StagedExitPlan:
    targets: tuple[Decimal, ...]
    quantity_ratios: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        if not self.targets or len(self.targets) != len(self.quantity_ratios):
            raise ValueError("staged targets and ratios must be non-empty and aligned")
        if any(value <= ZERO for value in (*self.targets, *self.quantity_ratios)):
            raise ValueError("staged exit values must be positive")
        if tuple(sorted(self.targets)) != self.targets or len(set(self.targets)) != len(
            self.targets
        ):
            raise ValueError("staged targets must be strictly ascending")
        if sum(self.quantity_ratios) > ONE:
            raise ValueError("staged exit ratios cannot exceed one")


@dataclass(frozen=True, slots=True)
class LifecycleExit:
    timestamp: datetime
    reason: ExitReason
    price: Decimal
    quantity: Decimal
    fee_usdt: Decimal
    net_pnl_usdt: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("lifecycle exit timestamp must be timezone-aware")
        if min(self.price, self.quantity, self.fee_usdt) < ZERO:
            raise ValueError("lifecycle exit values cannot be negative")


@dataclass(frozen=True, slots=True)
class ClosureContext:
    ignored_signals: int = 0
    htf_weakness: bool = False
    volatility_expansion: bool = False
    level_break: bool = False

    def __post_init__(self) -> None:
        if self.ignored_signals < 0:
            raise ValueError("ignored signal count cannot be negative")


@dataclass(frozen=True, slots=True)
class PaperClosureReview:
    exit_reason: ExitReason
    lifecycle_error: str | None
    stop_quality: str
    trailing_quality: str
    ignored_signals: int
    htf_weakness: bool
    volatility_expansion: bool
    level_break: bool
    staged_exit_alternative: str
    lesson_candidate: str


@dataclass(frozen=True, slots=True)
class LifecyclePosition:
    position_id: str
    candidate_id: str
    symbol: str
    opened_at: datetime
    entry_price: Decimal
    entry_fee_usdt: Decimal
    initial_quantity: Decimal
    remaining_quantity: Decimal
    stop_loss: Decimal
    trailing_stop: Decimal
    atr: Decimal
    plan: StagedExitPlan
    status: PositionStatus = PositionStatus.OPEN
    next_target_index: int = 0
    realized_pnl_usdt: Decimal = ZERO
    exits: tuple[LifecycleExit, ...] = field(default_factory=tuple)
    closure_review: PaperClosureReview | None = None

    def __post_init__(self) -> None:
        if not self.position_id.strip() or not self.candidate_id.strip():
            raise ValueError("position identity is required")
        if not self.symbol.strip():
            raise ValueError("position symbol is required")
        if self.opened_at.tzinfo is None or self.opened_at.utcoffset() is None:
            raise ValueError("position timestamp must be timezone-aware")
        if (
            min(
                self.entry_price,
                self.entry_fee_usdt,
                self.initial_quantity,
                self.stop_loss,
                self.trailing_stop,
                self.atr,
            )
            < ZERO
            or min(
                self.entry_price,
                self.initial_quantity,
                self.stop_loss,
                self.trailing_stop,
                self.atr,
            )
            == ZERO
        ):
            raise ValueError("position values must be positive except zero fee")
        if not ZERO <= self.remaining_quantity <= self.initial_quantity:
            raise ValueError("remaining quantity is invalid")
        if self.status is PositionStatus.CLOSED and self.remaining_quantity != ZERO:
            raise ValueError("closed position cannot retain quantity")
        if self.status is not PositionStatus.CLOSED and self.remaining_quantity == ZERO:
            raise ValueError("active position must retain quantity")


@dataclass(frozen=True, slots=True)
class PaperLifecycleEngine:
    fee_ratio: Decimal = Decimal("0.001")
    slippage_ratio: Decimal = Decimal("0.0005")
    trailing_multiplier: Decimal = Decimal("1.5")
    tick_size: Decimal = Decimal("0.00000001")

    def __post_init__(self) -> None:
        if not ZERO <= self.fee_ratio <= Decimal("0.01"):
            raise ValueError("fee_ratio must be between zero and 0.01")
        if not ZERO <= self.slippage_ratio <= Decimal("0.02"):
            raise ValueError("slippage_ratio must be between zero and 0.02")
        if min(self.trailing_multiplier, self.tick_size) <= ZERO:
            raise ValueError("trailing multiplier and tick size must be positive")

    def open_position(
        self,
        order: PaperOrder,
        *,
        stop_loss: Decimal,
        atr: Decimal,
        plan: StagedExitPlan,
    ) -> LifecyclePosition:
        if order.status is not PaperOrderStatus.FILLED:
            raise ValueError("only filled paper orders can open positions")
        if order.action.value != "BUY":
            raise ValueError("paper lifecycle currently supports Spot BUY positions")
        if stop_loss >= order.fill_price:
            raise ValueError("long stop loss must remain below entry")
        if any(target <= order.fill_price for target in plan.targets):
            raise ValueError("long staged targets must remain above entry")
        return LifecyclePosition(
            position_id=f"paper:{order.candidate_id}",
            candidate_id=order.candidate_id,
            symbol=order.symbol,
            opened_at=order.timestamp,
            entry_price=order.fill_price,
            entry_fee_usdt=order.fee_usdt,
            initial_quantity=order.quantity,
            remaining_quantity=order.quantity,
            stop_loss=stop_loss,
            trailing_stop=stop_loss,
            atr=atr,
            plan=plan,
        )

    def process_candle(
        self,
        position: LifecyclePosition,
        candle: OHLCVCandle,
        context: ClosureContext | None = None,
    ) -> LifecyclePosition:
        closure_context = context or ClosureContext()
        if position.status is PositionStatus.CLOSED:
            raise ValueError("closed paper position cannot process candles")
        if candle.timestamp < position.opened_at:
            raise ValueError("paper candle cannot precede position open time")
        effective_stop = max(position.stop_loss, position.trailing_stop)
        if candle.low <= effective_stop:
            reason = (
                ExitReason.TRAILING_STOP_EXIT
                if position.trailing_stop > position.stop_loss
                else ExitReason.STOP_LOSS_EXIT
            )
            price = min(candle.open, effective_stop) * (ONE - self.slippage_ratio)
            return self._close_remaining(
                position,
                candle.timestamp,
                reason,
                price,
                closure_context,
            )

        updated = position
        while updated.next_target_index < len(updated.plan.targets):
            index = updated.next_target_index
            target = updated.plan.targets[index]
            if candle.high < target:
                break
            planned_quantity = (
                updated.initial_quantity * updated.plan.quantity_ratios[index]
            )
            quantity = min(planned_quantity, updated.remaining_quantity)
            updated = self._apply_exit(
                updated,
                candle.timestamp,
                ExitReason.TAKE_PROFIT_EXIT,
                target * (ONE - self.slippage_ratio),
                quantity,
                closure_context,
                next_target_index=index + 1,
            )
            if updated.status is PositionStatus.CLOSED:
                return updated

        trailing = update_long_trailing_stop(
            updated.trailing_stop,
            candle.close,
            updated.atr,
            multiplier=self.trailing_multiplier,
            tick_size=self.tick_size,
        ).new_stop
        return replace(updated, trailing_stop=trailing)

    def _close_remaining(
        self,
        position: LifecyclePosition,
        timestamp: datetime,
        reason: ExitReason,
        price: Decimal,
        context: ClosureContext,
    ) -> LifecyclePosition:
        return self._apply_exit(
            position,
            timestamp,
            reason,
            price,
            position.remaining_quantity,
            context,
            next_target_index=position.next_target_index,
        )

    def _apply_exit(
        self,
        position: LifecyclePosition,
        timestamp: datetime,
        reason: ExitReason,
        price: Decimal,
        quantity: Decimal,
        context: ClosureContext,
        *,
        next_target_index: int,
    ) -> LifecyclePosition:
        fee = price * quantity * self.fee_ratio
        allocated_entry_fee = (
            position.entry_fee_usdt * quantity / position.initial_quantity
        )
        pnl = (price - position.entry_price) * quantity - fee - allocated_entry_fee
        remaining = position.remaining_quantity - quantity
        status = (
            PositionStatus.CLOSED
            if remaining == ZERO
            else PositionStatus.PARTIALLY_CLOSED
        )
        exit_event = LifecycleExit(timestamp, reason, price, quantity, fee, pnl)
        review = (
            self._review(
                reason,
                context,
                bool(position.exits) or reason is ExitReason.TAKE_PROFIT_EXIT,
            )
            if remaining == ZERO
            else None
        )
        return replace(
            position,
            remaining_quantity=remaining,
            status=status,
            next_target_index=next_target_index,
            realized_pnl_usdt=position.realized_pnl_usdt + pnl,
            exits=(*position.exits, exit_event),
            closure_review=review,
        )

    @staticmethod
    def _review(
        reason: ExitReason,
        context: ClosureContext,
        staged_exit_used: bool,
    ) -> PaperClosureReview:
        trailing = reason is ExitReason.TRAILING_STOP_EXIT
        return PaperClosureReview(
            exit_reason=reason,
            lifecycle_error=None,
            stop_quality="PROTECTIVE" if "STOP" in reason.value else "NOT_TRIGGERED",
            trailing_quality="PROTECTIVE" if trailing else "NOT_TRIGGERED",
            ignored_signals=context.ignored_signals,
            htf_weakness=context.htf_weakness,
            volatility_expansion=context.volatility_expansion,
            level_break=context.level_break,
            staged_exit_alternative=("USED" if staged_exit_used else "NOT_USED_REVIEW"),
            lesson_candidate=(
                "REVIEW_PREMATURE_TRAILING" if trailing else "REVIEW_EXIT_CONTEXT"
            ),
        )

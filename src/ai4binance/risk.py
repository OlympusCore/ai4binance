"""Deterministic capital-protection and position-sizing engine."""

from dataclasses import dataclass
from decimal import Decimal

from ai4binance.domain import (
    Action,
    CandidateStatus,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.schemas import MarketSnapshot

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_risk_per_trade: Decimal = Decimal("0.01")
    max_trade_usdt: Decimal = Decimal("100")
    daily_loss_limit_ratio: Decimal = Decimal("0.03")
    max_open_position_size_usdt: Decimal = Decimal("500")
    max_inventory_allocation_ratio: Decimal = Decimal("0.25")
    minimum_risk_reward: Decimal = Decimal("2")
    maximum_spread_ratio: Decimal = Decimal("0.005")
    maximum_slippage_ratio: Decimal = Decimal("0.003")
    repeated_loss_limit: int = 3

    def __post_init__(self) -> None:
        ratio_fields = (
            self.max_risk_per_trade,
            self.daily_loss_limit_ratio,
            self.max_inventory_allocation_ratio,
            self.maximum_spread_ratio,
            self.maximum_slippage_ratio,
        )
        if any(value <= ZERO or value > Decimal("1") for value in ratio_fields):
            raise ValueError("risk ratios must be within zero and one")
        if (
            min(
                self.max_trade_usdt,
                self.max_open_position_size_usdt,
                self.minimum_risk_reward,
            )
            <= ZERO
        ):
            raise ValueError("risk limits must be positive")
        if self.repeated_loss_limit < 1:
            raise ValueError("repeated_loss_limit must be positive")


@dataclass(frozen=True, slots=True)
class RiskContext:
    equity_usdt: Decimal | None = None
    current_exposure_usdt: Decimal = ZERO
    inventory_quantity: Decimal | None = None
    daily_loss_usdt: Decimal = ZERO
    estimated_slippage_ratio: Decimal = ZERO
    consecutive_losses: int = 0
    cooldown_active: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "current_exposure_usdt",
            "daily_loss_usdt",
            "estimated_slippage_ratio",
        ):
            if getattr(self, field_name) < ZERO:
                raise ValueError(f"{field_name} cannot be negative")
        if self.equity_usdt is not None and self.equity_usdt <= ZERO:
            raise ValueError("equity_usdt must be positive when known")
        if self.inventory_quantity is not None and self.inventory_quantity < ZERO:
            raise ValueError("inventory_quantity cannot be negative")
        if self.consecutive_losses < 0:
            raise ValueError("consecutive_losses cannot be negative")


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    candidate_id: str
    approved: bool
    size_usdt: Decimal = ZERO
    quantity: Decimal = ZERO
    risk_amount_usdt: Decimal = ZERO
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id cannot be empty")
        if min(self.size_usdt, self.quantity, self.risk_amount_usdt) < ZERO:
            raise ValueError("risk assessment values cannot be negative")
        if self.approved and self.blockers:
            raise ValueError("approved risk assessment cannot contain blockers")
        if (
            self.approved
            and min(
                self.size_usdt,
                self.quantity,
                self.risk_amount_usdt,
            )
            <= ZERO
        ):
            raise ValueError("approved risk assessment values must be positive")


@dataclass(frozen=True, slots=True)
class RiskEngine:
    config: RiskConfig = RiskConfig()

    def evaluate_many(
        self,
        candidates: tuple[TradeCandidate, ...],
        snapshot: MarketSnapshot,
        context: RiskContext,
        filters: SymbolFilters,
        *,
        limit: int = 5,
    ) -> tuple[RiskAssessment, ...]:
        """Evaluate at most the first five already-arbitrated candidates."""
        if not 1 <= limit <= 5:
            raise ValueError("risk candidate limit must be between one and five")
        return tuple(
            self.evaluate(candidate, snapshot, context, filters)
            for candidate in candidates[:limit]
        )

    def evaluate(
        self,
        candidate: TradeCandidate,
        snapshot: MarketSnapshot,
        context: RiskContext,
        filters: SymbolFilters,
    ) -> RiskAssessment:
        """Evaluate a candidate and calculate a safely rounded position preview."""
        blockers = list(candidate.blockers)
        if candidate.status is not CandidateStatus.READY_FOR_RISK:
            blockers.append("CANDIDATE_NOT_READY_FOR_RISK")
        if candidate.promotion_status not in {
            ValidationStatus.PAPER_APPROVED,
            ValidationStatus.LIVE_ELIGIBLE,
        }:
            blockers.append("STRATEGY_NOT_PROMOTED")
        if context.equity_usdt is None:
            blockers.append("EQUITY_UNKNOWN")
        if context.cooldown_active:
            blockers.append("STOP_LOSS_COOLDOWN_ACTIVE")
        if context.consecutive_losses >= self.config.repeated_loss_limit:
            blockers.append("REPEATED_LOSS_CIRCUIT_BREAKER")
        if context.equity_usdt is not None and context.daily_loss_usdt >= (
            context.equity_usdt * self.config.daily_loss_limit_ratio
        ):
            blockers.append("DAILY_LOSS_LIMIT_REACHED")
        if context.estimated_slippage_ratio > self.config.maximum_slippage_ratio:
            blockers.append("SLIPPAGE_EXCEEDS_LIMIT")
        if snapshot.latest_price is None or snapshot.latest_price <= ZERO:
            blockers.append("LATEST_PRICE_INVALID")
        elif (
            snapshot.spread is None
            or (snapshot.spread / snapshot.latest_price)
            > self.config.maximum_spread_ratio
        ):
            blockers.append("SPREAD_EXCEEDS_LIMIT")
        if candidate.risk_reward < self.config.minimum_risk_reward:
            blockers.append("RISK_REWARD_BELOW_MINIMUM")

        entry = candidate.entry_price
        stop_distance = abs(entry - candidate.stop_loss)
        if stop_distance <= ZERO:
            blockers.append("STOP_DISTANCE_INVALID")
        if candidate.action is Action.SELL and context.inventory_quantity is None:
            blockers.append("INVENTORY_UNKNOWN_FOR_SPOT_SELL")

        quantity = ZERO
        size_usdt = ZERO
        risk_amount = ZERO
        if context.equity_usdt is not None and stop_distance > ZERO:
            risk_amount = context.equity_usdt * self.config.max_risk_per_trade
            quantity = risk_amount / stop_distance
            size_usdt = quantity * entry
            available_exposure = max(
                ZERO,
                self.config.max_open_position_size_usdt - context.current_exposure_usdt,
            )
            notional_cap = min(self.config.max_trade_usdt, available_exposure)
            if size_usdt > notional_cap and entry > ZERO:
                size_usdt = notional_cap
                quantity = size_usdt / entry
            if (
                candidate.action is Action.SELL
                and context.inventory_quantity is not None
            ):
                quantity = min(quantity, context.inventory_quantity)
                size_usdt = quantity * entry
            quantity = filters.lot_size.round_down(quantity)
            size_usdt = quantity * entry
            risk_amount = quantity * stop_distance
            blockers.extend(filters.validate_order(entry, quantity))
            if quantity <= ZERO:
                blockers.append("ROUNDED_QUANTITY_IS_ZERO")
            if size_usdt + context.current_exposure_usdt > (
                context.equity_usdt * self.config.max_inventory_allocation_ratio
            ):
                blockers.append("MAX_INVENTORY_ALLOCATION_EXCEEDED")

        unique_blockers = tuple(dict.fromkeys(blockers))
        return RiskAssessment(
            candidate_id=candidate.candidate_id,
            approved=not unique_blockers,
            size_usdt=size_usdt,
            quantity=quantity,
            risk_amount_usdt=risk_amount,
            blockers=unique_blockers,
        )

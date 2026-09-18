"""Deterministic capital-protection and position-sizing engine."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from ai4binance.core.contracts.risk import (
    RiskConfig as RiskConfig,
)
from ai4binance.core.contracts.risk import (
    VirtualMarketPositionSizingPolicy as VirtualMarketPositionSizingPolicy,
)
from ai4binance.domain import (
    Action,
    CandidateStatus,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.schemas import AgentResult, MarketSnapshot

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RiskContext:
    equity_usdt: Decimal | None = None
    current_exposure_usdt: Decimal = ZERO
    open_risk_usdt: Decimal = ZERO
    open_position_count: int = 0
    inventory_quantity: Decimal | None = None
    daily_loss_usdt: Decimal = ZERO
    estimated_slippage_ratio: Decimal = ZERO
    consecutive_losses: int = 0
    cooldown_active: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "current_exposure_usdt",
            "open_risk_usdt",
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
        if self.open_position_count < 0:
            raise ValueError("open_position_count cannot be negative")


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

    @classmethod
    def from_agent_result(cls, result: AgentResult | object) -> "RiskAssessment | None":
        """Recover the canonical sizing output from risk-agent metadata."""
        agent_name = getattr(result, "agent_name", "risk")
        if agent_name != "risk":
            return None
        metadata = getattr(result, "calculation_metadata", {})
        if not isinstance(metadata, Mapping):
            return None
        candidate_id = metadata.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            return None
        approved = metadata.get("approved") is True
        size_usdt = _metadata_decimal(metadata.get("size_usdt"))
        quantity = _metadata_decimal(metadata.get("quantity"))
        risk_amount = _metadata_decimal(metadata.get("risk_amount_usdt"))
        if size_usdt is None or quantity is None or risk_amount is None:
            return None
        blockers = getattr(result, "blockers", ())
        if not isinstance(blockers, tuple):
            return None
        try:
            return cls(
                candidate_id=candidate_id,
                approved=approved,
                size_usdt=size_usdt,
                quantity=quantity,
                risk_amount_usdt=risk_amount,
                blockers=blockers,
            )
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class RiskEngine:
    config: RiskConfig = field(default_factory=RiskConfig)

    def evaluate_many(
        self,
        candidates: tuple[TradeCandidate, ...],
        snapshot: MarketSnapshot,
        context: RiskContext,
        filters: SymbolFilters,
        *,
        limit: int = 5,
        execution_surface: ExecutionSurface = ExecutionSurface.BINANCE_MARKET,
    ) -> tuple[RiskAssessment, ...]:
        """Evaluate at most the first five already-arbitrated candidates."""
        if not 1 <= limit <= 5:
            raise ValueError("risk candidate limit must be between one and five")
        return tuple(
            self.evaluate(
                candidate,
                snapshot,
                context,
                filters,
                execution_surface=execution_surface,
            )
            for candidate in candidates[:limit]
        )

    def evaluate(
        self,
        candidate: TradeCandidate,
        snapshot: MarketSnapshot,
        context: RiskContext,
        filters: SymbolFilters,
        *,
        execution_surface: ExecutionSurface = ExecutionSurface.BINANCE_MARKET,
    ) -> RiskAssessment:
        """Evaluate a candidate and calculate a safely rounded position preview."""
        blockers = list(candidate.blockers)
        if candidate.status is not CandidateStatus.READY_FOR_RISK:
            blockers.append("CANDIDATE_NOT_READY_FOR_RISK")
        if (
            execution_surface is ExecutionSurface.BINANCE_MARKET
            and candidate.promotion_status
            not in {
                ValidationStatus.PAPER_APPROVED,
                ValidationStatus.LIVE_ELIGIBLE,
            }
        ):
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
        if context.open_position_count >= self.config.virtual_market.maximum_positions:
            blockers.append("MAX_OPEN_POSITIONS_EXCEEDED")

        entry = candidate.entry_price
        stop_distance = abs(entry - candidate.invalidation_level)
        if stop_distance <= ZERO:
            blockers.append("STOP_DISTANCE_INVALID")
        if candidate.action is Action.SELL and context.inventory_quantity is None:
            blockers.append("INVENTORY_UNKNOWN_FOR_SPOT_SELL")

        quantity = ZERO
        size_usdt = ZERO
        risk_amount = ZERO
        if context.equity_usdt is not None and stop_distance > ZERO:
            risk_amount = (
                context.equity_usdt * self.config.virtual_market.risk_per_trade_ratio
            )
            quantity = risk_amount / stop_distance
            size_usdt = quantity * entry
            available_exposure = max(
                ZERO,
                self.config.max_open_position_size_usdt - context.current_exposure_usdt,
            )
            notional_cap = (
                min(self.config.max_trade_usdt, available_exposure)
                if (
                    execution_surface is ExecutionSurface.BINANCE_MARKET
                    and candidate.promotion_status is ValidationStatus.LIVE_ELIGIBLE
                )
                else available_exposure
            )
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
            if context.equity_usdt is not None and (
                context.open_risk_usdt + risk_amount
            ) > (
                context.equity_usdt * self.config.virtual_market.maximum_open_risk_ratio
            ):
                blockers.append("MAX_OPEN_RISK_EXCEEDED")
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


def _metadata_decimal(value: object) -> Decimal | None:
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None

"""Deterministic virtual-market fills and conservative long-position lifecycle."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
)
from ai4binance.domain import (
    Action,
    CandidateStatus,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.governance.execution_authority import (
    ExecutionSurface,
)
from ai4binance.governance.execution_envelope import (
    execution_envelope_for_surface,
)
from ai4binance.risk import RiskAssessment
from ai4binance.schemas import OHLCVCandle

ZERO = Decimal("0")
ONE = Decimal("1")


class PaperOrderStatus(StrEnum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"


class ExitReason(StrEnum):
    STOP_LOSS_EXIT = "STOP_LOSS_EXIT"
    TRAILING_STOP_EXIT = "TRAILING_STOP_EXIT"
    TAKE_PROFIT_EXIT = "TAKE_PROFIT_EXIT"


@dataclass(frozen=True, slots=True)
class PaperOrder:
    candidate_id: str
    timestamp: datetime
    symbol: str
    action: Action
    status: PaperOrderStatus
    quantity: Decimal
    requested_price: Decimal
    fill_price: Decimal
    fee_usdt: Decimal
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("paper order timestamp must be timezone-aware")
        if (
            min(self.quantity, self.requested_price, self.fill_price, self.fee_usdt)
            < ZERO
        ):
            raise ValueError("paper order numeric values cannot be negative")
        if self.status is PaperOrderStatus.FILLED and self.blockers:
            raise ValueError("filled paper order cannot contain blockers")


@dataclass(frozen=True, slots=True)
class PaperPosition:
    candidate_id: str
    symbol: str
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    trailing_stop: Decimal
    take_profit_levels: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        if (
            min(
                self.entry_price,
                self.quantity,
                self.stop_loss,
                self.trailing_stop,
            )
            <= ZERO
        ):
            raise ValueError("paper position values must be positive")
        if self.stop_loss >= self.entry_price:
            raise ValueError("long paper stop loss must remain below entry")
        if not self.take_profit_levels or any(
            target <= self.entry_price for target in self.take_profit_levels
        ):
            raise ValueError("long paper targets must remain above entry")


@dataclass(frozen=True, slots=True)
class PaperExit:
    candidate_id: str
    reason: ExitReason
    price: Decimal


@dataclass(frozen=True, slots=True)
class PaperBroker:
    fee_ratio: Decimal = Decimal("0.001")
    slippage_ratio: Decimal = Decimal("0.0005")
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        if not ZERO <= self.fee_ratio <= Decimal("0.01"):
            raise ValueError("fee_ratio must be between zero and 0.01")
        if not ZERO <= self.slippage_ratio <= Decimal("0.02"):
            raise ValueError("slippage_ratio must be between zero and 0.02")
        execution_envelope_for_surface(self.execution_surface)

    def submit(
        self,
        candidate: TradeCandidate,
        assessment: RiskAssessment,
        timestamp: datetime,
        *,
        virtual_eligibility: VirtualSimulationEligibility | None = None,
    ) -> PaperOrder:
        blockers = list(assessment.blockers)
        authority_envelope = execution_envelope_for_surface(self.execution_surface)
        if not assessment.approved:
            blockers.append("RISK_NOT_APPROVED")
        if assessment.quantity <= ZERO or assessment.size_usdt <= ZERO:
            blockers.append("INVALID_PAPER_QUANTITY")
        if candidate.status is not CandidateStatus.READY_FOR_RISK:
            blockers.append("CANDIDATE_NOT_READY")
        if (
            virtual_eligibility is None
            and candidate.promotion_status is not ValidationStatus.PAPER_APPROVED
        ):
            blockers.append("SIMULATION_PROMOTION_REQUIRED")
        if virtual_eligibility is not None:
            if not virtual_eligibility.eligible:
                blockers.extend(virtual_eligibility.blockers)
            if virtual_eligibility.binance_order_allowed:
                blockers.append("BINANCE_ORDER_AUTHORITY_LEAK")
            if virtual_eligibility.live_order_allowed:
                blockers.append("LIVE_ORDER_AUTHORITY_LEAK")
            if not virtual_eligibility.virtual_simulation_allowed:
                blockers.append("VIRTUAL_SIMULATION_NOT_ALLOWED")
        if not authority_envelope.paper_execution_allowed:
            blockers.append("SIMULATED_EXECUTION_PROFILE_BLOCKED")
        if authority_envelope.manual_confirmation_required:
            blockers.append("HUMAN_HAND_MANUAL_EXECUTION_REQUIRED")
        if not authority_envelope.auto_simulation_allowed:
            blockers.append("AUTO_SIMULATION_NOT_ALLOWED")
        unique_blockers = tuple(dict.fromkeys(blockers))
        requested_price = candidate.entry_price
        if unique_blockers:
            return PaperOrder(
                candidate_id=candidate.candidate_id,
                timestamp=timestamp,
                symbol=candidate.symbol,
                action=candidate.action,
                status=PaperOrderStatus.REJECTED,
                quantity=assessment.quantity,
                requested_price=requested_price,
                fill_price=ZERO,
                fee_usdt=ZERO,
                blockers=unique_blockers,
            )
        slippage = (
            ONE + self.slippage_ratio
            if candidate.action is Action.BUY
            else ONE - self.slippage_ratio
        )
        fill_price = requested_price * slippage
        fee = fill_price * assessment.quantity * self.fee_ratio
        return PaperOrder(
            candidate_id=candidate.candidate_id,
            timestamp=timestamp,
            symbol=candidate.symbol,
            action=candidate.action,
            status=PaperOrderStatus.FILLED,
            quantity=assessment.quantity,
            requested_price=requested_price,
            fill_price=fill_price,
            fee_usdt=fee,
        )

    @staticmethod
    def evaluate_long_exit(
        position: PaperPosition,
        candle: OHLCVCandle,
    ) -> PaperExit | None:
        """Use pessimistic stop-first ordering when stop and target share a bar."""
        effective_stop = max(position.stop_loss, position.trailing_stop)
        if candle.low <= effective_stop:
            reason = (
                ExitReason.TRAILING_STOP_EXIT
                if position.trailing_stop > position.stop_loss
                else ExitReason.STOP_LOSS_EXIT
            )
            return PaperExit(
                position.candidate_id,
                reason,
                min(candle.open, effective_stop),
            )
        first_target = position.take_profit_levels[0]
        if candle.high >= first_target:
            return PaperExit(
                position.candidate_id,
                ExitReason.TAKE_PROFIT_EXIT,
                first_target,
            )
        return None

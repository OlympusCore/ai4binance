"""Immutable simulated order contracts without execution authority."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ai4binance.domain import Action
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeDecisionEvidence,
    TradeParameterMethods,
)

ZERO = Decimal("0")


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
    stop_loss: Decimal | None = None
    take_profit_levels: tuple[Decimal, ...] = ()
    leverage: int | None = None
    planned_rr: Decimal | None = None
    net_pnl: Decimal | None = None
    decision_evidence: TradeDecisionEvidence = field(
        default_factory=TradeDecisionEvidence
    )
    parameter_methods: TradeParameterMethods = field(
        default_factory=TradeParameterMethods
    )

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

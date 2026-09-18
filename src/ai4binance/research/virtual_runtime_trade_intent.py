"""Deterministic virtual-runtime trade-intent contract."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ai4binance.domain import Action
from ai4binance.research.virtual_runtime_portfolio_state import VirtualPositionSide

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class VirtualTradeIntent:
    """Deterministic virtual-market trade intent without external side effects."""

    snapshot_id: str
    decision_id: str
    candidate_id: str
    symbol: str
    market: str
    action: Action
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_levels: tuple[Decimal, ...]
    reason_codes: tuple[str, ...]
    opportunity_id: str = "UNKNOWN_OPPORTUNITY"
    position_side: VirtualPositionSide | None = None
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.snapshot_id,
            self.decision_id,
            self.candidate_id,
            self.symbol,
            self.market,
            self.opportunity_id,
        ):
            if not value.strip():
                raise ValueError("virtual trade intent identity is required")
        _require_unique_nonblank("virtual trade intent reason codes", self.reason_codes)
        _require_unique_nonblank("virtual trade intent blockers", self.blockers)
        if self.action not in {Action.BUY, Action.SELL}:
            raise ValueError("virtual trade intent action must be BUY or SELL")
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError(
                "virtual trade intent market must be SPOT or USD_M_FUTURES"
            )
        object.__setattr__(self, "market", normalized_market)
        if normalized_market == "USD_M_FUTURES" and self.position_side is None:
            raise ValueError("futures virtual trade intent requires explicit direction")
        if not self.blockers and (
            self.quantity <= ZERO
            or self.entry_price <= ZERO
            or self.stop_loss <= ZERO
            or not self.take_profit_levels
        ):
            raise ValueError("fillable virtual trade intent requires positive geometry")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

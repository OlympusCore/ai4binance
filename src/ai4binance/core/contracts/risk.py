"""Canonical immutable risk-policy contracts shared across layers."""

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class VirtualMarketPositionSizingPolicy:
    """Configurable invalidation-first sizing policy for bounded simulation."""

    risk_per_trade_ratio: Decimal = Decimal("0.005")
    maximum_open_risk_ratio: Decimal = Decimal("0.02")
    maximum_positions: int = 4

    def __post_init__(self) -> None:
        ratio_fields = (
            self.risk_per_trade_ratio,
            self.maximum_open_risk_ratio,
        )
        if any(value <= ZERO or value > Decimal("1") for value in ratio_fields):
            raise ValueError("virtual market risk ratios must be within zero and one")
        if self.maximum_positions < 1:
            raise ValueError("virtual market maximum_positions must be positive")


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Deterministic capital-protection configuration contract."""

    max_risk_per_trade: Decimal = Decimal("0.01")
    max_trade_usdt: Decimal = Decimal("100")
    daily_loss_limit_ratio: Decimal = Decimal("0.03")
    max_open_position_size_usdt: Decimal = Decimal("500")
    max_inventory_allocation_ratio: Decimal = Decimal("0.25")
    minimum_risk_reward: Decimal = Decimal("2")
    maximum_spread_ratio: Decimal = Decimal("0.005")
    maximum_slippage_ratio: Decimal = Decimal("0.003")
    repeated_loss_limit: int = 3
    virtual_market: VirtualMarketPositionSizingPolicy = field(
        default_factory=VirtualMarketPositionSizingPolicy
    )

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


__all__ = ("RiskConfig", "VirtualMarketPositionSizingPolicy")

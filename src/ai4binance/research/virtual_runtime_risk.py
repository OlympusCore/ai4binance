"""Deterministic virtual-runtime portfolio risk contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ai4binance.portfolio.risk_budget import PortfolioRiskPolicy

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class VirtualPortfolioRiskGovernor:
    """Deterministic portfolio-level veto policy for virtual-market entries."""

    exposure_policy: PortfolioRiskPolicy = field(
        default_factory=lambda: PortfolioRiskPolicy(
            maximum_gross_usdt=Decimal("5000"),
            maximum_symbol_usdt=Decimal("2500"),
            maximum_correlation_group_usdt=Decimal("3000"),
            maximum_strategy_usdt=Decimal("2500"),
        )
    )
    maximum_risk_per_trade_usdt: Decimal = Decimal("250")
    maximum_open_risk_usdt: Decimal = Decimal("500")
    maximum_drawdown_ratio: Decimal = Decimal("0.15")
    maximum_consecutive_losses: int = 3
    maximum_margin_utilization_ratio: Decimal = Decimal("0.60")
    maximum_futures_leverage: int = 5

    def __post_init__(self) -> None:
        if (
            min(
                self.maximum_risk_per_trade_usdt,
                self.maximum_open_risk_usdt,
                self.maximum_margin_utilization_ratio,
            )
            <= ZERO
        ):
            raise ValueError("virtual portfolio governor limits must be positive")
        if not ZERO < self.maximum_drawdown_ratio <= ONE:
            raise ValueError(
                "virtual portfolio drawdown limit must stay within zero and one"
            )
        if not ZERO < self.maximum_margin_utilization_ratio <= ONE:
            raise ValueError(
                "virtual portfolio margin utilization limit must stay within "
                "zero and one"
            )
        if self.maximum_consecutive_losses < 0:
            raise ValueError(
                "virtual portfolio consecutive loss limit cannot be negative"
            )
        if self.maximum_futures_leverage < 1:
            raise ValueError(
                "virtual portfolio futures leverage limit must be positive"
            )

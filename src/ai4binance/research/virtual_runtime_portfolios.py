"""Independent virtual portfolio boundary contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.research.virtual_runtime_portfolio_state import (
    VirtualPortfolioState,
)


@dataclass(frozen=True, slots=True)
class IndependentVirtualPortfolios:
    """Explicitly separate Spot and Futures capital without cross-market masking."""

    spot: VirtualPortfolioState
    futures: VirtualPortfolioState

    def __post_init__(self) -> None:
        if self.spot.market != "SPOT":
            raise ValueError("independent virtual portfolios require a SPOT portfolio")
        if self.futures.market != "USD_M_FUTURES":
            raise ValueError(
                "independent virtual portfolios require a USD_M_FUTURES portfolio"
            )
        if self.spot.portfolio_id == self.futures.portfolio_id:
            raise ValueError(
                "Spot and Futures virtual portfolios must stay independent"
            )

"""Fail-closed coverage for independent virtual market portfolios."""

from decimal import Decimal

import pytest

from ai4binance.research.virtual_runtime_portfolio_state import VirtualPortfolioState
from ai4binance.research.virtual_runtime_portfolios import IndependentVirtualPortfolios


def portfolio(*, portfolio_id: str, market: str) -> VirtualPortfolioState:
    return VirtualPortfolioState(
        portfolio_id=portfolio_id,
        market=market,
        cash_usdt=Decimal("1000"),
        equity_usdt=Decimal("1000"),
    )


def test_independent_portfolios_reject_wrong_market_boundaries() -> None:
    spot = portfolio(portfolio_id="virtual:spot", market="SPOT")
    futures = portfolio(portfolio_id="virtual:futures", market="USD_M_FUTURES")
    assert IndependentVirtualPortfolios(spot=spot, futures=futures).spot is spot

    with pytest.raises(ValueError, match="SPOT portfolio"):
        IndependentVirtualPortfolios(spot=futures, futures=futures)
    with pytest.raises(ValueError, match="USD_M_FUTURES portfolio"):
        IndependentVirtualPortfolios(spot=spot, futures=spot)

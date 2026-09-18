"""Canonical virtual portfolio performance calculations for bounded runtime use."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from importlib import import_module
from typing import Protocol

_equity_metrics = import_module("ai4binance.research.equity_metrics")

calculate_annualized_return = _equity_metrics.calculate_annualized_return
calculate_equity_max_drawdown = _equity_metrics.calculate_equity_max_drawdown
calculate_equity_returns = _equity_metrics.calculate_equity_returns
calculate_periodic_sharpe = _equity_metrics.calculate_periodic_sharpe
calculate_periodic_sortino = _equity_metrics.calculate_periodic_sortino
calculate_regular_sample_seconds = _equity_metrics.calculate_regular_sample_seconds


class EquityObservation(Protocol):
    """Structural contract for a single virtual equity observation."""

    timestamp: datetime
    equity_usdt: Decimal


ZERO = Decimal("0")
ONE = Decimal("1")
_SUPPORTED_MARKETS = {"SPOT", "USD_M_FUTURES"}


def _normalize_market(market: str) -> str:
    normalized = market.strip().upper()
    if normalized not in _SUPPORTED_MARKETS:
        raise ValueError(
            "virtual portfolio performance market must be SPOT or USD_M_FUTURES"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class VirtualPortfolioPerformanceMetrics:
    """Portable metrics bundle used to build virtual portfolio performance results."""

    market: str
    starting_equity_usdt: Decimal
    ending_equity_usdt: Decimal
    observation_count: int
    sample_period_seconds: int
    net_return: Decimal
    annualized_return: Decimal | None
    max_drawdown: Decimal
    portfolio_sharpe: Decimal | None
    portfolio_sortino: Decimal | None


def calculate_virtual_portfolio_performance_metrics(
    *,
    market: str,
    equity_curve: Sequence[EquityObservation],
) -> VirtualPortfolioPerformanceMetrics:
    """Calculate canonical performance metrics from a validated equity curve."""

    if not equity_curve:
        raise ValueError("virtual portfolio performance requires equity observations")
    normalized_market = _normalize_market(market)
    if len(equity_curve) == 1:
        only = equity_curve[0]
        return VirtualPortfolioPerformanceMetrics(
            market=normalized_market,
            starting_equity_usdt=only.equity_usdt,
            ending_equity_usdt=only.equity_usdt,
            observation_count=1,
            sample_period_seconds=0,
            net_return=ZERO,
            annualized_return=None,
            max_drawdown=ZERO,
            portfolio_sharpe=None,
            portfolio_sortino=None,
        )
    step_seconds = calculate_regular_sample_seconds(equity_curve)
    returns = calculate_equity_returns(equity_curve)
    annualized_return = calculate_annualized_return(
        equity_curve[0].equity_usdt,
        equity_curve[-1].equity_usdt,
        duration_seconds=int(
            (equity_curve[-1].timestamp - equity_curve[0].timestamp).total_seconds()
        ),
    )
    daily_sharpe = (
        calculate_periodic_sharpe(returns, periods_per_year=365.0)
        if step_seconds == 86_400
        else None
    )
    return VirtualPortfolioPerformanceMetrics(
        market=normalized_market,
        starting_equity_usdt=equity_curve[0].equity_usdt,
        ending_equity_usdt=equity_curve[-1].equity_usdt,
        observation_count=len(equity_curve),
        sample_period_seconds=step_seconds,
        net_return=equity_curve[-1].equity_usdt / equity_curve[0].equity_usdt - ONE,
        annualized_return=annualized_return,
        max_drawdown=calculate_equity_max_drawdown(equity_curve),
        portfolio_sharpe=(
            daily_sharpe
            if daily_sharpe is not None
            else calculate_periodic_sharpe(
                returns,
                periods_per_year=(365 * 24 * 60 * 60) / step_seconds,
            )
        ),
        portfolio_sortino=calculate_periodic_sortino(
            returns,
            periods_per_year=(365 * 24 * 60 * 60) / step_seconds,
        ),
    )

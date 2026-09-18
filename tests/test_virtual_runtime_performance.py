from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from ai4binance.application import (
    VirtualMarketRuntime,
    VirtualPortfolioPerformanceMetrics,
    calculate_virtual_portfolio_performance_metrics,
)
from ai4binance.research.equity_metrics import (
    EquityObservation,
    calculate_annualized_return,
    calculate_equity_max_drawdown,
    calculate_equity_returns,
    calculate_periodic_sharpe,
    calculate_periodic_sortino,
    calculate_regular_sample_seconds,
)
from ai4binance.research.virtual_market import DailyEquityPoint

NOW = datetime(2026, 3, 1, tzinfo=UTC)


def equity_point(offset_days: int, equity: str) -> DailyEquityPoint:
    return DailyEquityPoint(NOW + timedelta(days=offset_days), Decimal(equity))


def test_application_exports_virtual_performance_helper() -> None:
    assert VirtualPortfolioPerformanceMetrics.__name__ == (
        "VirtualPortfolioPerformanceMetrics"
    )
    assert callable(calculate_virtual_portfolio_performance_metrics)


def test_virtual_market_equity_metrics_helpers_match_runtime_calculations() -> None:
    curve = (
        equity_point(0, "1000"),
        equity_point(1, "1010"),
        equity_point(2, "1005"),
        equity_point(3, "1030"),
    )
    equity_curve = cast(Sequence[EquityObservation], curve)
    returns = calculate_equity_returns(equity_curve)

    assert calculate_regular_sample_seconds(equity_curve) == 86400
    assert returns == (
        Decimal("0.01"),
        Decimal("-0.004950495049504950495049505"),
        Decimal("0.02487562189054726368159204"),
    )
    assert calculate_equity_max_drawdown(equity_curve) == Decimal(
        "0.004950495049504950495049504950"
    )
    assert calculate_periodic_sharpe(returns, periods_per_year=365.0) is not None
    assert calculate_periodic_sortino(returns, periods_per_year=365.0) is not None
    assert (
        calculate_annualized_return(
            curve[0].equity_usdt,
            curve[-1].equity_usdt,
            duration_seconds=86400 * 3,
        )
        is not None
    )


def test_virtual_market_performance_helper_matches_runtime_calculations() -> None:
    curve = (
        equity_point(0, "1000"),
        equity_point(1, "1010"),
        equity_point(2, "1005"),
        equity_point(3, "1030"),
    )
    helper_metrics = calculate_virtual_portfolio_performance_metrics(
        market="SPOT",
        equity_curve=cast(Sequence[EquityObservation], curve),
    )
    runtime_metrics = VirtualMarketRuntime.calculate_portfolio_performance(
        market="SPOT",
        equity_curve=curve,
    )

    assert isinstance(helper_metrics, VirtualPortfolioPerformanceMetrics)
    assert helper_metrics.market == runtime_metrics.market
    assert helper_metrics.starting_equity_usdt == runtime_metrics.starting_equity_usdt
    assert helper_metrics.ending_equity_usdt == runtime_metrics.ending_equity_usdt
    assert helper_metrics.observation_count == runtime_metrics.observation_count
    assert helper_metrics.sample_period_seconds == runtime_metrics.sample_period_seconds
    assert helper_metrics.net_return == runtime_metrics.net_return
    assert helper_metrics.annualized_return == runtime_metrics.annualized_return
    assert helper_metrics.max_drawdown == runtime_metrics.max_drawdown
    assert helper_metrics.portfolio_sharpe == runtime_metrics.portfolio_sharpe
    assert helper_metrics.portfolio_sortino == runtime_metrics.portfolio_sortino


def test_virtual_portfolio_performance_helper_rejects_invalid_inputs() -> None:
    with pytest.raises(
        ValueError,
        match="virtual portfolio performance requires equity observations",
    ):
        calculate_virtual_portfolio_performance_metrics(
            market="SPOT",
            equity_curve=cast(Sequence[EquityObservation], ()),
        )

    with pytest.raises(
        ValueError,
        match="virtual portfolio performance market must be SPOT or USD_M_FUTURES",
    ):
        calculate_virtual_portfolio_performance_metrics(
            market="OPTIONS",
            equity_curve=cast(Sequence[EquityObservation], (equity_point(0, "1000"),)),
        )

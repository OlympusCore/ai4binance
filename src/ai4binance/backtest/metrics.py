"""Deterministic fee-aware backtest performance calculations."""

from math import sqrt

from ai4binance.backtest.models import BacktestMetrics, TradeRecord


def calculate_metrics(
    trades: tuple[TradeRecord, ...],
    initial_cash: float,
    buy_and_hold_return: float,
    equity_observations: tuple[float, ...] = (),
) -> BacktestMetrics:
    """Calculate closed-trade metrics without inventing missing observations."""
    pnl = [float(trade.net_pnl_usdt) for trade in trades]
    total_pnl = sum(pnl)
    net_return = total_pnl / initial_cash
    wins = [value for value in pnl if value > 0.0]
    losses = [value for value in pnl if value < 0.0]
    gross_loss = abs(sum(losses))
    profit_factor = sum(wins) / gross_loss if gross_loss > 0.0 else None
    expectancy = total_pnl / len(pnl) if pnl else 0.0
    win_rate = len(wins) / len(pnl) if pnl else 0.0
    sharpe = _sample_sharpe(pnl)

    equity_values = equity_observations or _closed_trade_equity(pnl, initial_cash)
    max_drawdown = _max_drawdown(equity_values)

    return BacktestMetrics(
        net_return=net_return,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        expectancy_usdt=expectancy,
        sharpe=sharpe,
        win_rate=win_rate,
        trade_count=len(trades),
        buy_and_hold_return=buy_and_hold_return,
    )


def _closed_trade_equity(pnl: list[float], initial_cash: float) -> tuple[float, ...]:
    equity = initial_cash
    values = [equity]
    for trade_pnl in pnl:
        equity += trade_pnl
        values.append(equity)
    return tuple(values)


def _max_drawdown(equity_values: tuple[float, ...]) -> float:
    peak = equity_values[0] if equity_values else 0.0
    max_drawdown = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        if peak > 0.0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown


def _sample_sharpe(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance == 0.0:
        return None
    return mean / sqrt(variance) * sqrt(len(values))

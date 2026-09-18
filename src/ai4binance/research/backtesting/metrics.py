"""Deterministic fee-aware backtest performance calculations."""

from math import sqrt

from ai4binance.research.backtesting.models import (
    BacktestMetrics,
    MissedOpportunityCategory,
    MissedOpportunityLedger,
    TradeRecord,
)


def calculate_metrics(
    trades: tuple[TradeRecord, ...],
    initial_cash: float,
    buy_and_hold_return: float,
    equity_observations: tuple[float, ...] = (),
    *,
    market: str = "SPOT",
    backtest_duration_seconds: int = 0,
    missed_opportunity_ledger: MissedOpportunityLedger | None = None,
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
    sortino = _sortino(pnl)

    equity_values = equity_observations or _closed_trade_equity(pnl, initial_cash)
    max_drawdown = _max_drawdown(equity_values)
    expectancy_r = _average_realized_r(trades)
    average_win = sum(wins) / len(wins) if wins else None
    average_loss = sum(losses) / len(losses) if losses else None
    exposure_ratio = _exposure_ratio(trades, backtest_duration_seconds)
    turnover_ratio = _turnover_ratio(trades, initial_cash)
    fee_drag_ratio = _drag_ratio(
        sum(float(trade.fee_cost_usdt) for trade in trades),
        initial_cash,
    )
    slippage_drag_ratio = _drag_ratio(
        sum(float(trade.slippage_cost_usdt) for trade in trades),
        initial_cash,
    )
    average_mae_r = _average_excursion_r(trades, favorable=False)
    average_mfe_capture = _average_mfe_capture(trades)
    max_consecutive_losses = _max_consecutive_losses(pnl)
    time_under_water_seconds = _time_under_water_seconds(
        equity_values, backtest_duration_seconds
    )
    dge_saved_loss_usdt = 0.0
    dge_missed_profit_usdt = 0.0
    if missed_opportunity_ledger is not None:
        dge_saved_loss_usdt = sum(
            abs(float(record.forward_net_pnl or 0.0))
            for record in missed_opportunity_ledger.records
            if record.counterfactual_result is MissedOpportunityCategory.GOOD_BLOCK
        )
        dge_missed_profit_usdt = sum(
            max(float(record.forward_net_pnl or 0.0), 0.0)
            for record in missed_opportunity_ledger.records
            if record.counterfactual_result is MissedOpportunityCategory.BAD_BLOCK
        )

    return BacktestMetrics(
        net_return=net_return,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        expectancy_usdt=expectancy,
        sharpe=sharpe,
        win_rate=win_rate,
        trade_count=len(trades),
        buy_and_hold_return=buy_and_hold_return,
        market=market,
        sortino=sortino,
        expectancy_r=expectancy_r,
        average_win_usdt=average_win,
        average_loss_usdt=average_loss,
        exposure_ratio=exposure_ratio,
        turnover_ratio=turnover_ratio,
        fee_drag_ratio=fee_drag_ratio,
        slippage_drag_ratio=slippage_drag_ratio,
        average_mae_r=average_mae_r,
        average_mfe_capture=average_mfe_capture,
        max_consecutive_losses=max_consecutive_losses,
        time_under_water_seconds=time_under_water_seconds,
        dge_saved_loss_usdt=dge_saved_loss_usdt,
        dge_missed_profit_usdt=dge_missed_profit_usdt,
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


def _sortino(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    downside = [min(0.0, value) for value in values]
    downside_variance = sum(value * value for value in downside) / len(downside)
    if downside_variance == 0.0:
        return None
    return mean / sqrt(downside_variance) * sqrt(len(values))


def _average_realized_r(trades: tuple[TradeRecord, ...]) -> float | None:
    if not trades:
        return None
    return sum(float(trade.realized_r_multiple) for trade in trades) / len(trades)


def _exposure_ratio(
    trades: tuple[TradeRecord, ...],
    backtest_duration_seconds: int,
) -> float:
    if backtest_duration_seconds <= 0:
        return 0.0
    exposed = sum(trade.holding_time for trade in trades)
    return min(exposed / backtest_duration_seconds, 1.0)


def _turnover_ratio(trades: tuple[TradeRecord, ...], initial_cash: float) -> float:
    if initial_cash <= 0.0:
        return 0.0
    turnover = sum(
        float((trade.entry_price + trade.exit_price) * trade.quantity)
        for trade in trades
    )
    return turnover / initial_cash


def _drag_ratio(cost: float, initial_cash: float) -> float:
    if initial_cash <= 0.0:
        return 0.0
    return cost / initial_cash


def _average_excursion_r(
    trades: tuple[TradeRecord, ...],
    *,
    favorable: bool,
) -> float | None:
    values: list[float] = []
    for trade in trades:
        risk = float(trade.risk_at_entry)
        if risk <= 0.0:
            continue
        excursion = (
            float(trade.maximum_favorable_excursion)
            if favorable
            else float(trade.maximum_adverse_excursion)
        )
        values.append(excursion / risk)
    if not values:
        return None
    return sum(values) / len(values)


def _average_mfe_capture(trades: tuple[TradeRecord, ...]) -> float | None:
    values: list[float] = []
    for trade in trades:
        risk = float(trade.risk_at_entry)
        if risk <= 0.0:
            continue
        mfe_r = float(trade.maximum_favorable_excursion) / risk
        if mfe_r <= 0.0:
            continue
        values.append(float(trade.realized_r_multiple) / mfe_r)
    if not values:
        return None
    return sum(values) / len(values)


def _max_consecutive_losses(values: list[float]) -> int:
    streak = 0
    worst = 0
    for value in values:
        if value < 0.0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def _time_under_water_seconds(
    equity_values: tuple[float, ...],
    backtest_duration_seconds: int,
) -> int:
    if len(equity_values) < 2 or backtest_duration_seconds <= 0:
        return 0
    step_seconds = backtest_duration_seconds // max(len(equity_values) - 1, 1)
    peak = equity_values[0]
    under_water = 0
    for equity in equity_values[1:]:
        peak = max(peak, equity)
        if equity < peak:
            under_water += step_seconds
    return under_water

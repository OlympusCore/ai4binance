"""Canonical equity-curve metric helpers for virtual research runtimes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from math import isfinite, sqrt
from typing import Protocol

ZERO = Decimal("0")
ONE = Decimal("1")


class EquityObservation(Protocol):
    """Minimal equity observation interface used by canonical metric helpers."""

    timestamp: datetime
    equity_usdt: Decimal


def calculate_equity_returns(
    equity_curve: Sequence[EquityObservation],
) -> tuple[Decimal, ...]:
    """Calculate consecutive equity return ratios from validated observations."""

    if len(equity_curve) < 2:
        return ()
    returns: list[Decimal] = []
    for previous, current in pairwise(equity_curve):
        if current.timestamp <= previous.timestamp:
            raise ValueError("equity observations must be strictly increasing")
        returns.append(current.equity_usdt / previous.equity_usdt - ONE)
    return tuple(returns)


def calculate_regular_sample_seconds(
    equity_curve: Sequence[EquityObservation],
) -> int:
    """Return the uniform spacing in seconds for a regularly sampled curve."""

    if len(equity_curve) < 2:
        return 0
    previous = equity_curve[0]
    deltas: list[int] = []
    for current in equity_curve[1:]:
        delta = int((current.timestamp - previous.timestamp).total_seconds())
        if delta <= 0:
            raise ValueError("equity observations must be strictly increasing")
        deltas.append(delta)
        previous = current
    if len(set(deltas)) != 1:
        raise ValueError("equity observations must use a regular sampling interval")
    return deltas[0]


def calculate_equity_max_drawdown(
    equity_curve: Sequence[EquityObservation],
) -> Decimal:
    """Calculate maximum drawdown from an equity curve."""

    if not equity_curve:
        return ZERO
    peak = equity_curve[0].equity_usdt
    max_drawdown = ZERO
    for point in equity_curve:
        peak = max(peak, point.equity_usdt)
        if peak > ZERO:
            max_drawdown = max(max_drawdown, (peak - point.equity_usdt) / peak)
    return max_drawdown


def calculate_annualized_return(
    starting_equity: Decimal,
    ending_equity: Decimal,
    *,
    duration_seconds: int,
) -> Decimal | None:
    """Calculate an annualized return from a bounded duration."""

    if duration_seconds < 86_400:
        return None
    years = Decimal(duration_seconds) / Decimal(str(365 * 24 * 60 * 60))
    if years <= ZERO:
        return None
    annualized = float(ending_equity / starting_equity) ** (1.0 / float(years)) - 1.0
    return Decimal(str(annualized))


def calculate_periodic_sharpe(
    returns: Sequence[Decimal],
    *,
    periods_per_year: float,
) -> Decimal | None:
    """Calculate an annualized Sharpe ratio from periodic return observations."""

    if len(returns) < 2:
        return None
    values = [float(value) for value in returns]
    if any(not isfinite(value) for value in values):
        raise ValueError("equity returns must be finite")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance == 0.0:
        return None
    return Decimal(str((mean / sqrt(variance)) * sqrt(periods_per_year)))


def calculate_periodic_sortino(
    returns: Sequence[Decimal],
    *,
    periods_per_year: float,
) -> Decimal | None:
    """Calculate an annualized Sortino ratio from periodic return observations."""

    if len(returns) < 2:
        return None
    values = [float(value) for value in returns]
    if any(not isfinite(value) for value in values):
        raise ValueError("equity returns must be finite")
    mean = sum(values) / len(values)
    downside = [min(0.0, value) for value in values]
    downside_variance = sum(value * value for value in downside) / len(downside)
    if downside_variance == 0.0:
        return None
    return Decimal(str((mean / sqrt(downside_variance)) * sqrt(periods_per_year)))

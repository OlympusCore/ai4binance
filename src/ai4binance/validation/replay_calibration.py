"""Causal forecast capture and censored labels from canonical replay trades."""

from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    BacktestResult,
    TradeDirection,
    TradeRecord,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.overfit import OosProbabilityObservation


@dataclass(frozen=True, slots=True)
class ReplayForecast:
    """Pre-outcome geometry score, explicitly not a calibrated probability."""

    signal_id: str
    model_id: str
    trained_through: datetime
    predicted_at: datetime
    horizon_end: datetime
    stop_loss: Decimal
    take_profit: Decimal
    reference_price: Decimal
    direction: TradeDirection
    regime: str

    def __post_init__(self) -> None:
        if not self.signal_id or not self.model_id or not self.regime:
            raise ValueError("replay forecast identity is required")
        if (
            any(
                t.utcoffset() is None
                for t in (self.trained_through, self.predicted_at, self.horizon_end)
            )
            or not self.trained_through < self.predicted_at < self.horizon_end
        ):
            raise ValueError("replay forecast chronology is invalid")
        levels = (self.stop_loss, self.reference_price, self.take_profit)
        if any(not p.is_finite() or p <= 0 for p in levels):
            raise ValueError("replay forecast prices are invalid")
        ordered = levels if self.direction is TradeDirection.LONG else levels[::-1]
        if not ordered[0] < ordered[1] < ordered[2]:
            raise ValueError("replay forecast geometry is invalid")

    @property
    def raw_score(self) -> float:
        """Geometry baseline for empirical fitting; no confidence substitution."""
        risk = abs(self.reference_price - self.stop_loss)
        reward = abs(self.take_profit - self.reference_price)
        return float(risk / (risk + reward))


@dataclass(frozen=True, slots=True)
class ReplayCalibrationCohort:
    observations: tuple[OosProbabilityObservation, ...]
    censor_counts: tuple[tuple[str, int], ...]
    forecast_count: int
    completed_trade_count: int


def _resolved_barrier(
    forecast: ReplayForecast,
    trade: TradeRecord,
    path: tuple[OHLCVCandle, ...],
    interval: timedelta,
) -> tuple[datetime | None, bool, str]:
    if trade.exit_reason in {
        BacktestExitReason.LIQUIDATION,
        BacktestExitReason.END_OF_DATA,
    }:
        return None, False, trade.exit_reason.value
    for candle in path:
        closed_at = candle.timestamp + interval
        if closed_at > forecast.horizon_end:
            break
        if forecast.direction is TradeDirection.LONG:
            stopped = candle.low <= forecast.stop_loss
            targeted = candle.high >= forecast.take_profit
        else:
            stopped = candle.high >= forecast.stop_loss
            targeted = candle.low <= forecast.take_profit
        if stopped and targeted:
            return None, False, "SIMULTANEOUS_BARRIER_TOUCH"
        if stopped or targeted:
            return closed_at, targeted, ""
    return None, False, "BARRIER_NOT_RESOLVED_BEFORE_EXIT"


def replay_calibration_cohort(
    result: BacktestResult,
    forecasts: tuple[ReplayForecast, ...],
    candles: tuple[OHLCVCandle, ...],
    *,
    interval: timedelta,
    fold_id: str,
) -> ReplayCalibrationCohort:
    """Join actually filled trades to pre-outcome forecasts; retain censor counts.

    Rejected opportunities are not filled trades. Censored trades remain in the
    economic replay, including every liquidation and cost. This projection may
    only assess probability calibration, never replace the performance ledger.
    """
    if interval <= timedelta(0) or not candles or not fold_id:
        raise ValueError("replay label interval and fold are required")
    stamps = tuple(c.timestamp for c in candles)
    if any(b - a != interval for a, b in pairwise(stamps)):
        raise ValueError("replay labels require a contiguous closed candle path")
    by_signal = {f.signal_id: f for f in forecasts}
    if len(by_signal) != len(forecasts):
        raise ValueError("duplicate replay forecast identity")
    censored: Counter[str] = Counter()
    observations: list[OosProbabilityObservation] = []
    for trade in result.trades:
        forecast = by_signal.get(trade.signal_id)
        if forecast is None or forecast.direction is not trade.direction:
            raise ValueError("filled replay trade has no matching frozen forecast")
        if forecast.predicted_at > trade.entry_timestamp:
            raise ValueError("forecast became available after the entry")
        start = bisect_left(stamps, trade.entry_timestamp)
        end = bisect_left(stamps, trade.exit_timestamp)
        if (
            start >= len(stamps)
            or end >= len(stamps)
            or (
                stamps[start] != trade.entry_timestamp
                or stamps[end] != trade.exit_timestamp
            )
        ):
            raise ValueError("replay trade lies outside the bound candle path")
        resolved, targeted, reason = _resolved_barrier(
            forecast, trade, candles[start : end + 1], interval
        )
        if resolved is None:
            censored[reason] += 1
            continue
        observations.append(
            OosProbabilityObservation(
                observation_id=f"{result.symbol}:{trade.trade_id}",
                model_id=forecast.model_id,
                fold_id=fold_id,
                regime=forecast.regime,
                trained_through=forecast.trained_through,
                predicted_at=forecast.predicted_at,
                resolved_at=resolved,
                horizon_end=forecast.horizon_end,
                probability=forecast.raw_score,
                target_first=targeted,
                net_r=float(trade.realized_r_multiple),
            )
        )
    return ReplayCalibrationCohort(
        tuple(observations),
        tuple(sorted(censored.items())),
        len(forecasts),
        len(result.trades),
    )

"""Transparent deterministic indicator primitives using closed candles only."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from ai4binance.schemas import OHLCVCandle

HUNDRED = Decimal("100")
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SupertrendPoint:
    """One closed-candle Supertrend observation."""

    timestamp: datetime
    direction: int
    band: Decimal
    atr: Decimal


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """A pivot confirmed after its right-hand window has closed."""

    index: int
    timestamp: datetime
    price: Decimal
    kind: str


def ema(values: Sequence[Decimal], period: int) -> Decimal:
    """Return the latest EMA seeded by the first period's simple mean."""
    _require_period(values, period)
    period_decimal = Decimal(period)
    current = sum(values[:period], ZERO) / period_decimal
    alpha = Decimal("2") / Decimal(period + 1)
    for value in values[period:]:
        current = ((value - current) * alpha) + current
    return current


def ema_series(values: Sequence[Decimal], period: int) -> tuple[Decimal, ...]:
    """Return EMA values from the seeded candle onward."""
    _require_period(values, period)
    current = sum(values[:period], ZERO) / Decimal(period)
    output = [current]
    alpha = Decimal("2") / Decimal(period + 1)
    for value in values[period:]:
        current = ((value - current) * alpha) + current
        output.append(current)
    return tuple(output)


def cross_over(
    previous_left: Decimal,
    previous_right: Decimal,
    current_left: Decimal,
    current_right: Decimal,
) -> bool:
    """Return true only for a newly confirmed upward cross."""
    return previous_left <= previous_right and current_left > current_right


def cross_under(
    previous_left: Decimal,
    previous_right: Decimal,
    current_left: Decimal,
    current_right: Decimal,
) -> bool:
    """Return true only for a newly confirmed downward cross."""
    return previous_left >= previous_right and current_left < current_right


def ohlc4(candle: OHLCVCandle) -> Decimal:
    """Return the auditable OHLC4 source for one closed candle."""
    return (candle.open + candle.high + candle.low + candle.close) / Decimal("4")


def atr(candles: Sequence[OHLCVCandle], period: int = 14) -> Decimal:
    """Return Wilder ATR from chronological closed candles."""
    if period < 1 or len(candles) < period + 1:
        raise ValueError("ATR requires at least period + 1 candles")
    true_ranges: list[Decimal] = []
    for previous, current in pairwise(candles):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    period_decimal = Decimal(period)
    current_atr = sum(true_ranges[:period], ZERO) / period_decimal
    for true_range in true_ranges[period:]:
        current_atr = (
            (current_atr * Decimal(period - 1)) + true_range
        ) / period_decimal
    return current_atr


def supertrend(
    candles: Sequence[OHLCVCandle],
    period: int = 14,
    multiplier: Decimal = Decimal("2"),
) -> tuple[SupertrendPoint, ...]:
    """Return deterministic Supertrend using Wilder ATR and OHLC4."""
    if multiplier <= ZERO:
        raise ValueError("Supertrend multiplier must be positive")
    atr_values = _wilder_atr_series(candles, period)
    first_index = period
    upper: Decimal | None = None
    lower: Decimal | None = None
    active_band: Decimal | None = None
    output: list[SupertrendPoint] = []
    for offset, current_atr in enumerate(atr_values):
        index = first_index + offset
        candle = candles[index]
        source = ohlc4(candle)
        basic_upper = source + (multiplier * current_atr)
        basic_lower = source - (multiplier * current_atr)
        if index == first_index:
            upper = basic_upper
            lower = basic_lower
            direction = 1 if candle.close >= source else -1
            active_band = lower if direction == 1 else upper
        else:
            previous = candles[index - 1]
            if upper is None or lower is None or active_band is None:
                raise RuntimeError("Supertrend state initialization failed")
            previous_upper = upper
            previous_lower = lower
            upper = (
                basic_upper
                if basic_upper < previous_upper or previous.close > previous_upper
                else previous_upper
            )
            lower = (
                basic_lower
                if basic_lower > previous_lower or previous.close < previous_lower
                else previous_lower
            )
            if active_band == previous_upper:
                direction = 1 if candle.close > upper else -1
            else:
                direction = -1 if candle.close < lower else 1
            active_band = lower if direction == 1 else upper
        output.append(
            SupertrendPoint(candle.timestamp, direction, active_band, current_atr)
        )
    return tuple(output)


def confirmed_swings(
    candles: Sequence[OHLCVCandle],
    left: int = 2,
    right: int = 2,
) -> tuple[SwingPoint, ...]:
    """Return unique pivots without provisional right-edge points."""
    if left < 1 or right < 1:
        raise ValueError("swing windows must be positive")
    if len(candles) < left + right + 1:
        raise ValueError("confirmed swings require left + right + 1 candles")
    output: list[SwingPoint] = []
    for index in range(left, len(candles) - right):
        window = candles[index - left : index + right + 1]
        high = candles[index].high
        low = candles[index].low
        if (
            high == max(item.high for item in window)
            and sum(item.high == high for item in window) == 1
        ):
            output.append(SwingPoint(index, candles[index].timestamp, high, "HIGH"))
        if (
            low == min(item.low for item in window)
            and sum(item.low == low for item in window) == 1
        ):
            output.append(SwingPoint(index, candles[index].timestamp, low, "LOW"))
    return tuple(output)


def rsi(values: Sequence[Decimal], period: int = 14) -> Decimal:
    """Return Wilder RSI bounded to zero through 100."""
    if period < 1 or len(values) < period + 1:
        raise ValueError("RSI requires at least period + 1 values")
    changes = [current - previous for previous, current in pairwise(values)]
    gains = [max(change, ZERO) for change in changes]
    losses = [max(-change, ZERO) for change in changes]
    period_decimal = Decimal(period)
    average_gain = sum(gains[:period], ZERO) / period_decimal
    average_loss = sum(losses[:period], ZERO) / period_decimal
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        average_gain = ((average_gain * Decimal(period - 1)) + gain) / period_decimal
        average_loss = ((average_loss * Decimal(period - 1)) + loss) / period_decimal
    if average_gain == ZERO and average_loss == ZERO:
        return Decimal("50")
    if average_loss == ZERO:
        return HUNDRED
    relative_strength = average_gain / average_loss
    return HUNDRED - (HUNDRED / (Decimal("1") + relative_strength))


def relative_volume(candles: Sequence[OHLCVCandle], window: int = 20) -> Decimal:
    """Compare latest volume against the preceding fixed window."""
    if window < 1 or len(candles) < window + 1:
        raise ValueError("relative volume requires window + 1 candles")
    baseline = sum(
        (item.volume for item in candles[-(window + 1) : -1]), ZERO
    ) / Decimal(window)
    if baseline == ZERO:
        return ZERO
    return candles[-1].volume / baseline


def session_vwap(candles: Sequence[OHLCVCandle], session_start: datetime) -> Decimal:
    """Return HLC3 volume-weighted price from an explicit session boundary."""
    if session_start.tzinfo is None or session_start.utcoffset() is None:
        raise ValueError("session_start must be timezone-aware")
    session_candles = tuple(
        candle for candle in candles if candle.timestamp >= session_start
    )
    if not session_candles:
        raise ValueError("session VWAP requires candles in the selected session")
    cumulative_volume = sum((candle.volume for candle in session_candles), ZERO)
    if cumulative_volume <= ZERO:
        raise ValueError("session VWAP requires positive cumulative volume")
    weighted_price = sum(
        (
            ((candle.high + candle.low + candle.close) / Decimal("3")) * candle.volume
            for candle in session_candles
        ),
        ZERO,
    )
    return weighted_price / cumulative_volume


def closes(candles: Sequence[OHLCVCandle]) -> tuple[Decimal, ...]:
    return tuple(item.close for item in candles)


def clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))


def _require_period(values: Sequence[Decimal], period: int) -> None:
    if period < 1 or len(values) < period:
        raise ValueError("indicator requires at least period values")


def _wilder_atr_series(
    candles: Sequence[OHLCVCandle], period: int
) -> tuple[Decimal, ...]:
    if period < 1 or len(candles) < period + 1:
        raise ValueError("ATR requires at least period + 1 candles")
    true_ranges = tuple(
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in pairwise(candles)
    )
    current = sum(true_ranges[:period], ZERO) / Decimal(period)
    output = [current]
    for true_range in true_ranges[period:]:
        current = ((current * Decimal(period - 1)) + true_range) / Decimal(period)
        output.append(current)
    return tuple(output)

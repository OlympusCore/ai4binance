"""Monotonic ATR trailing-stop updates."""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

DEFAULT_TRAILING_MULTIPLIER = Decimal("1.5")


@dataclass(frozen=True, slots=True)
class TrailingStopUpdate:
    previous_stop: Decimal
    new_stop: Decimal
    moved: bool


def update_long_trailing_stop(
    previous_stop: Decimal,
    current_price: Decimal,
    current_atr: Decimal,
    *,
    multiplier: Decimal = DEFAULT_TRAILING_MULTIPLIER,
    tick_size: Decimal,
) -> TrailingStopUpdate:
    """Move a long trailing stop upward only and round down to tick size."""
    if min(previous_stop, current_price, current_atr, multiplier, tick_size) <= Decimal(
        "0"
    ):
        raise ValueError("trailing-stop inputs must be positive")
    if previous_stop >= current_price:
        raise ValueError("previous_stop must remain below current_price")
    candidate = current_price - (multiplier * current_atr)
    units = (candidate / tick_size).to_integral_value(rounding=ROUND_DOWN)
    rounded_candidate = units * tick_size
    new_stop = max(previous_stop, rounded_candidate)
    return TrailingStopUpdate(
        previous_stop=previous_stop,
        new_stop=new_stop,
        moved=new_stop > previous_stop,
    )

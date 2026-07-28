"""Bounded candle-volume liquidity and partial-fill stress decisions."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")
ONE = Decimal("1")


class FillSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class LiquidityStressConfig:
    """Explicit research-only assumptions for candle-volume fill capacity."""

    max_volume_participation: Decimal = Decimal("0.01")
    minimum_fill_ratio: Decimal = Decimal("0.25")
    impact_ratio: Decimal = Decimal("0.001")
    maximum_impact_ratio: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        values = (
            self.max_volume_participation,
            self.minimum_fill_ratio,
            self.impact_ratio,
            self.maximum_impact_ratio,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("liquidity stress ratios must be finite and non-negative")
        if not ZERO < self.max_volume_participation <= ONE:
            raise ValueError("maximum volume participation must be in (0, 1]")
        if not ZERO < self.minimum_fill_ratio <= ONE:
            raise ValueError("minimum fill ratio must be in (0, 1]")
        if self.impact_ratio > self.maximum_impact_ratio:
            raise ValueError("base impact cannot exceed maximum impact")


@dataclass(frozen=True, slots=True)
class LiquidityFillDecision:
    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    fill_ratio: Decimal
    price_impact_ratio: Decimal
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("liquidity stress evidence cannot authorize execution")


def assess_liquidity_fill(
    *,
    requested_quantity: Decimal,
    candle_volume: Decimal,
    config: LiquidityStressConfig,
) -> LiquidityFillDecision:
    """Cap one simulated fill by base-volume participation and add impact."""
    if not requested_quantity.is_finite() or requested_quantity <= ZERO:
        raise ValueError("requested fill quantity must be finite and positive")
    if not candle_volume.is_finite() or candle_volume < ZERO:
        raise ValueError("candle volume must be finite and non-negative")
    capacity = candle_volume * config.max_volume_participation
    filled = min(requested_quantity, capacity)
    ratio = filled / requested_quantity
    blockers: list[str] = []
    if filled <= ZERO:
        blockers.append("LIQUIDITY_FILL_UNAVAILABLE")
    elif ratio < config.minimum_fill_ratio:
        blockers.append("LIQUIDITY_PARTIAL_FILL_BELOW_MINIMUM")
    utilization = filled / capacity if capacity > ZERO else ZERO
    impact = min(
        config.maximum_impact_ratio,
        config.impact_ratio * utilization,
    )
    return LiquidityFillDecision(
        requested_quantity=requested_quantity,
        filled_quantity=filled,
        remaining_quantity=requested_quantity - filled,
        fill_ratio=ratio,
        price_impact_ratio=impact,
        blockers=tuple(blockers),
    )

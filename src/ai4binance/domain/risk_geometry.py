"""Shared deterministic structural margin-loss geometry."""

from decimal import Decimal


def structural_margin_loss_per_unit(
    entry: Decimal,
    stop: Decimal,
    mark_price: Decimal,
    cost_and_funding_ratio: Decimal,
    mark_stress_ratio: Decimal,
) -> tuple[Decimal, Decimal]:
    """Share the same conservative loss geometry between sizing and margin veto."""
    sign = Decimal("1") if stop < entry else Decimal("-1")
    stressed_stop = stop - sign * (abs(mark_price - entry) + entry * mark_stress_ratio)
    loss = abs(entry - stressed_stop) + entry * cost_and_funding_ratio
    return stressed_stop, loss

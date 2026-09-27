"""Dependency-neutral execution-surface identity; this grants no authority."""

from enum import StrEnum


class ExecutionSurface(StrEnum):
    """Canonical execution surfaces with distinct authority envelopes."""

    BINANCE_MARKET = "BINANCE_MARKET"
    VIRTUAL_MARKET = "VIRTUAL_MARKET"

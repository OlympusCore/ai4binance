"""Canonical market identifiers for Spot and derivatives boundaries."""

from enum import StrEnum


class CapitalMarket(StrEnum):
    """Supported capital-market boundaries."""

    SPOT = "SPOT"
    USD_M_FUTURES = "USD_M_FUTURES"

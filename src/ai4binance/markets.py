"""Shared market identifiers for Spot and derivatives account boundaries."""

from enum import StrEnum


class CapitalMarket(StrEnum):
    SPOT = "SPOT"
    USD_M_FUTURES = "USD_M_FUTURES"

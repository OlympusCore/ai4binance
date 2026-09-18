"""Canonical fail-closed error contracts."""

from ai4binance.core.errors.exchange import (
    ExchangeError,
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeRateLimitError,
    ExchangeTransportError,
)

__all__ = (
    "ExchangeError",
    "ExchangeHttpError",
    "ExchangePayloadError",
    "ExchangeRateLimitError",
    "ExchangeTransportError",
)

"""Compatibility facade for the canonical exchange error contracts."""

from ai4binance.core.errors import (
    ExchangeError,
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeTransportError,
)

__all__ = (
    "ExchangeError",
    "ExchangeHttpError",
    "ExchangePayloadError",
    "ExchangeTransportError",
)

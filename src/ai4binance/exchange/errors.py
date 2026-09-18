"""Legacy exchange exception re-exports."""

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

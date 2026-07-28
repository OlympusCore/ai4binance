"""Sanitized exchange-boundary exceptions."""


class ExchangeError(RuntimeError):
    """Base error that never contains credentials or query parameters."""


class ExchangeTransportError(ExchangeError):
    """Network or timeout failure after bounded retries."""


class ExchangeHttpError(ExchangeError):
    """Unexpected HTTP response from a public endpoint."""


class ExchangePayloadError(ExchangeError):
    """Malformed or contract-incompatible exchange payload."""

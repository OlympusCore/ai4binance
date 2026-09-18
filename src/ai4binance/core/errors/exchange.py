"""Canonical sanitized exchange-boundary exceptions."""


class ExchangeError(RuntimeError):
    """Base error that never contains credentials or query parameters."""


class ExchangeTransportError(ExchangeError):
    """Network or timeout failure after bounded retries."""


class ExchangeHttpError(ExchangeError):
    """Unexpected HTTP response from a public endpoint."""


class ExchangeRateLimitError(ExchangeHttpError):
    """Sanitized 429/418 response with a bounded provider retry delay."""

    def __init__(
        self,
        status_code: int,
        retry_after_seconds: float | None,
        path: str,
    ) -> None:
        super().__init__(f"public exchange HTTP {status_code} at {path}")
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class ExchangePayloadError(ExchangeError):
    """Malformed or contract-incompatible exchange payload."""


__all__ = (
    "ExchangeError",
    "ExchangeHttpError",
    "ExchangePayloadError",
    "ExchangeRateLimitError",
    "ExchangeTransportError",
)

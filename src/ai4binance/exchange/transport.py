"""Bounded, read-only JSON transport for Binance public endpoints."""

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai4binance.core.errors import (
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeRateLimitError,
    ExchangeTransportError,
)


@dataclass(frozen=True, slots=True)
class UrllibJsonTransport:
    """HTTPS GET-only transport with retry, backoff and response limits."""

    base_url: str = "https://data-api.binance.vision"
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    max_response_bytes: int = 8_000_000
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    response_headers_observer: Callable[[Mapping[str, str]], None] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        normalized_url = self.base_url.rstrip("/")
        if not normalized_url.startswith("https://"):
            raise ValueError("public exchange base_url must use HTTPS")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.backoff_seconds < 0 or self.max_backoff_seconds <= 0:
            raise ValueError("backoff values must be non-negative and bounded")
        if self.max_response_bytes < 1024:
            raise ValueError("max_response_bytes is too small")
        object.__setattr__(self, "base_url", normalized_url)

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        """Fetch one public API path and return decoded JSON."""
        if not path.startswith("/api/v3/") or "?" in path or "#" in path:
            raise ValueError("only normalized Binance public API v3 paths are allowed")
        query = urlencode(sorted((params or {}).items()))
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._request_once(url, path)
            except HTTPError as error:
                if error.code in {418, 429}:
                    raise ExchangeRateLimitError(
                        error.code,
                        self._parse_retry_after(error.headers.get("Retry-After")),
                        path,
                    ) from None
                retryable = 500 <= error.code <= 599
                if not retryable or attempt == self.max_attempts:
                    raise ExchangeHttpError(
                        f"public exchange HTTP {error.code} at {path}"
                    ) from None
                self.sleeper(
                    self._retry_delay(attempt, error.headers.get("Retry-After"))
                )
            except (TimeoutError, URLError, OSError):
                if attempt == self.max_attempts:
                    raise ExchangeTransportError(
                        f"public exchange request failed at {path}"
                    ) from None
                self.sleeper(self._retry_delay(attempt, None))
        raise ExchangeTransportError(f"public exchange request failed at {path}")

    def _request_once(self, url: str, path: str) -> object:
        # The base URL is HTTPS-only and the path is restricted to /api/v3/.
        request = Request(  # noqa: S310  # nosec B310
            url,
            headers={"Accept": "application/json", "User-Agent": "AI4Binance/0.1"},
            method="GET",
        )
        with urlopen(  # noqa: S310  # nosec B310
            request,
            timeout=self.timeout_seconds,
        ) as response:
            payload = response.read(self.max_response_bytes + 1)
            if self.response_headers_observer is not None:
                self.response_headers_observer(dict(response.headers.items()))
        if len(payload) > self.max_response_bytes:
            raise ExchangePayloadError(f"public exchange payload too large at {path}")
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, JSONDecodeError):
            raise ExchangePayloadError(
                f"invalid public exchange JSON at {path}"
            ) from None

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                parsed = max(0.0, float(retry_after))
            except ValueError:
                parsed = 0.0
            if parsed > 0:
                return min(parsed, self.max_backoff_seconds)
        exponential = self.backoff_seconds * float(2 ** (attempt - 1))
        return float(min(exponential, self.max_backoff_seconds))

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None

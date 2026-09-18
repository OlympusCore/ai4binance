"""Bounded HTTPS transport for fixed social publishing endpoints."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

_ALLOWED_HOSTS = frozenset({"api.x.com", "api.telegram.org", "api.linkedin.com"})


class PublishTransportError(RuntimeError):
    """Sanitized external transport failure."""


@dataclass(frozen=True, slots=True)
class HttpPublishRequest:
    """One bounded request to an allowlisted social API host."""

    url: str
    headers: dict[str, str]
    body: bytes
    timeout_seconds: float
    maximum_response_bytes: int

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise ValueError("social publishing endpoint is not allowlisted")
        if self.timeout_seconds <= 0 or self.maximum_response_bytes <= 0:
            raise ValueError("social publishing transport bounds are invalid")
        if not self.body or len(self.body) > 16_384:
            raise ValueError("social publishing request body is invalid")


@dataclass(frozen=True, slots=True)
class HttpPublishResponse:
    """Bounded response required for provider receipt validation."""

    status_code: int
    headers: dict[str, str]
    body: bytes


class PublishingTransport(Protocol):
    """Injectable network boundary for deterministic tests."""

    def send(self, request: HttpPublishRequest) -> HttpPublishResponse:
        """Send exactly one request without automatic retries."""


@dataclass(frozen=True, slots=True)
class UrllibPublishingTransport:
    """Standard-library HTTPS adapter with bounded response reads."""

    def send(self, request: HttpPublishRequest) -> HttpPublishResponse:
        outbound = urllib.request.Request(  # noqa: S310  # nosec B310
            request.url,
            data=request.body,
            headers=request.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310  # nosec B310
                outbound, timeout=request.timeout_seconds
            ) as response:
                body = response.read(request.maximum_response_bytes + 1)
                if len(body) > request.maximum_response_bytes:
                    raise PublishTransportError("social response exceeded size limit")
                headers = {
                    key.casefold(): value for key, value in response.headers.items()
                }
                return HttpPublishResponse(response.status, headers, body)
        except urllib.error.HTTPError as error:
            body = error.read(request.maximum_response_bytes + 1)
            if len(body) > request.maximum_response_bytes:
                body = b""
            headers = {key.casefold(): value for key, value in error.headers.items()}
            return HttpPublishResponse(error.code, headers, body)
        except (OSError, urllib.error.URLError) as error:
            raise PublishTransportError("social publishing transport failed") from error

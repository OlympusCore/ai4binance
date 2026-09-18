"""Bounded HTTPS-only transport with redirect, robots, and SSRF gates."""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message
from hashlib import sha256
from http.client import HTTPResponse
from typing import IO, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener
from urllib.robotparser import RobotFileParser

from ai4binance.external_intel.normalization.urls import UrlPolicy

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_DEFAULT_CONTENT_TYPES = frozenset(
    {
        "application/atom+xml",
        "application/rss+xml",
        "application/xml",
        "text/html",
        "text/plain",
        "text/xml",
    }
)


class OpenWebFetchError(RuntimeError):
    """Safe, code-only retrieval error without response content leakage."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> Request | None:
        del req, fp, code, msg, headers, newurl
        return None


def _resolve_public_host(host: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(item[4][0])
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        )
    )


@dataclass(frozen=True, slots=True)
class FetchedResource:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    retrieved_at: datetime
    content_sha256: str
    redirect_chain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status_code != 200 or not self.body:
            raise ValueError("fetched resource must contain a successful response")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("fetched resource timestamp must be timezone-aware")
        if sha256(self.body).hexdigest() != self.content_sha256:
            raise ValueError("fetched resource content hash is invalid")


@dataclass(slots=True)
class UrlFetcher:
    policy: UrlPolicy
    timeout_seconds: float = 10.0
    # Modern allowlisted publisher pages regularly exceed 1 MiB because their
    # markup includes first-party structured data.  Keep the default at the
    # independently validated hard ceiling rather than silently dropping those
    # documents; _request still reads one byte past this bound and rejects it.
    max_response_bytes: int = 2_000_000
    max_redirects: int = 3
    user_agent: str = "AI4BINANCE-Open-Web-Radar/1.0"
    respect_robots: bool = True
    resolver: Callable[[str], tuple[str, ...]] = _resolve_public_host
    opener: OpenerDirector = field(
        default_factory=lambda: build_opener(_NoRedirectHandler())
    )
    _robots_cache: dict[str, bool] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0.1 <= self.timeout_seconds <= 30.0:
            raise ValueError("open-web timeout must be between 0.1 and 30 seconds")
        if not 1_024 <= self.max_response_bytes <= 2_000_000:
            raise ValueError("open-web response limit is outside the safe range")
        if not 0 <= self.max_redirects <= 5:
            raise ValueError("open-web redirect limit is outside the safe range")

    def fetch(
        self,
        url: str,
        *,
        allowed_content_types: frozenset[str] = _DEFAULT_CONTENT_TYPES,
        robots_required: bool = True,
    ) -> FetchedResource:
        canonical = self._validate_with_dns(url)
        if (
            self.respect_robots
            and robots_required
            and not self._robots_allowed(canonical)
        ):
            raise OpenWebFetchError("ROBOTS_DISALLOWED_OR_UNAVAILABLE")
        return self._fetch_chain(
            canonical,
            allowed_content_types=allowed_content_types,
            maximum_bytes=self.max_response_bytes,
        )

    def _robots_allowed(self, url: str) -> bool:
        hostname = urlsplit(url).hostname or ""
        cached = self._robots_cache.get(hostname)
        if cached is not None:
            return cached
        robots_url = urlunsplit(("https", hostname, "/robots.txt", "", ""))
        try:
            resource = self._fetch_chain(
                robots_url,
                allowed_content_types=frozenset({"text/plain"}),
                maximum_bytes=64_000,
                allow_not_found=True,
            )
        except OpenWebFetchError:
            self._robots_cache[hostname] = False
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(resource.body.decode("utf-8", errors="replace").splitlines())
        allowed = parser.can_fetch(self.user_agent, url)
        self._robots_cache[hostname] = allowed
        return allowed

    def _fetch_chain(
        self,
        url: str,
        *,
        allowed_content_types: frozenset[str],
        maximum_bytes: int,
        allow_not_found: bool = False,
    ) -> FetchedResource:
        requested = url
        current = url
        redirects: list[str] = []
        for redirect_index in range(self.max_redirects + 1):
            current = self._validate_with_dns(current)
            status, headers, body = self._request(current, maximum_bytes)
            if status in _REDIRECT_STATUSES:
                if redirect_index >= self.max_redirects:
                    raise OpenWebFetchError("REDIRECT_LIMIT_EXCEEDED")
                location = headers.get("Location", "").strip()
                if not location:
                    raise OpenWebFetchError("REDIRECT_LOCATION_MISSING")
                current = urljoin(current, location)
                redirects.append(current)
                continue
            if status == 404 and allow_not_found:
                no_rules = b"User-agent: *\nAllow: /\n"
                return FetchedResource(
                    requested,
                    current,
                    200,
                    "text/plain",
                    no_rules,
                    datetime.now(UTC),
                    sha256(no_rules).hexdigest(),
                    tuple(redirects),
                )
            if status != 200:
                raise OpenWebFetchError(f"HTTP_STATUS_{status}")
            content_type = headers.get_content_type().casefold()
            if content_type not in allowed_content_types:
                raise OpenWebFetchError("CONTENT_TYPE_NOT_ALLOWED")
            encoding = headers.get("Content-Encoding", "identity").casefold()
            if encoding not in {"", "identity"}:
                raise OpenWebFetchError("CONTENT_ENCODING_NOT_ALLOWED")
            if not body:
                raise OpenWebFetchError("EMPTY_RESPONSE")
            return FetchedResource(
                requested,
                current,
                status,
                content_type,
                body,
                datetime.now(UTC),
                sha256(body).hexdigest(),
                tuple(redirects),
            )
        raise OpenWebFetchError("REDIRECT_LIMIT_EXCEEDED")

    def _request(self, url: str, maximum_bytes: int) -> tuple[int, Message, bytes]:
        request = Request(  # noqa: S310 - URL policy enforces allowlisted HTTPS.
            url,
            headers={"User-Agent": self.user_agent},
            method="GET",
        )
        headers: Message
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                typed = cast(HTTPResponse, response)
                body = typed.read(maximum_bytes + 1)
                status = typed.status
                headers = typed.headers
        except HTTPError as error:
            status = error.code
            headers = error.headers
            body = error.read(maximum_bytes + 1)
        except (OSError, TimeoutError, URLError) as error:
            raise OpenWebFetchError("PROVIDER_UNAVAILABLE") from error
        if len(body) > maximum_bytes:
            raise OpenWebFetchError("RESPONSE_TOO_LARGE")
        return status, headers, body

    def _validate_with_dns(self, url: str) -> str:
        preliminary = self.policy.validate(url)
        hostname = urlsplit(preliminary).hostname
        if hostname is None:
            raise OpenWebFetchError("HOSTNAME_UNAVAILABLE")
        try:
            addresses = self.resolver(hostname)
        except OSError as error:
            raise OpenWebFetchError("DNS_RESOLUTION_FAILED") from error
        if not addresses:
            raise OpenWebFetchError("DNS_RESOLUTION_EMPTY")
        try:
            return self.policy.validate(preliminary, resolved_addresses=addresses)
        except ValueError as error:
            raise OpenWebFetchError("URL_POLICY_BLOCKED") from error

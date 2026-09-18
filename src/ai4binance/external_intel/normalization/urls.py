"""Canonical URL handling and SSRF preflight for Open Web inputs."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "source",
    }
)


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("open-web URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("open-web URL cannot contain credentials")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise ValueError("open-web hostname is invalid") from error
    port = parsed.port
    if port not in {None, 443}:
        raise ValueError("open-web URL cannot use a non-HTTPS port")
    netloc = hostname
    path = parsed.path or "/"
    pairs = tuple(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in _TRACKING_KEYS
    )
    return urlunsplit(("https", netloc, path, urlencode(sorted(pairs)), ""))


@dataclass(frozen=True, slots=True)
class UrlPolicy:
    allowed_hosts: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized = tuple(host.strip().casefold() for host in self.allowed_hosts)
        if not normalized or any(not host or "/" in host for host in normalized):
            raise ValueError("URL policy requires normalized allowed hosts")
        if len(normalized) != len(set(normalized)) or normalized != self.allowed_hosts:
            raise ValueError("URL policy hosts must be normalized and unique")

    def validate(
        self,
        value: str,
        *,
        resolved_addresses: tuple[str, ...] = (),
    ) -> str:
        canonical = canonicalize_url(value)
        hostname = urlsplit(canonical).hostname
        if hostname not in self.allowed_hosts:
            raise ValueError("open-web URL host is not allowlisted")
        for address in resolved_addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as error:
                raise ValueError(
                    "open-web resolver returned an invalid address"
                ) from error
            if not parsed.is_global:
                raise ValueError("open-web URL resolved to a non-public address")
        return canonical

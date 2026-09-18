"""Deterministic URL routing without executing specialist radars."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from ai4binance.external_intel.normalization.urls import UrlPolicy


class UrlRouteKind(StrEnum):
    OPEN_WEB = "OPEN_WEB"
    OFFICIAL_EXCHANGE = "OFFICIAL_EXCHANGE"
    GITHUB_RADAR = "GITHUB_RADAR"
    RESEARCH_DOCUMENT = "RESEARCH_DOCUMENT"
    REDIRECT_DISCOVERY = "REDIRECT_DISCOVERY"


@dataclass(frozen=True, slots=True)
class UrlRoute:
    canonical_url: str
    host: str
    route: UrlRouteKind


def route_url(url: str, policy: UrlPolicy) -> UrlRoute:
    canonical = policy.validate(url)
    host = urlsplit(canonical).hostname or ""
    if host == "github.com":
        route = UrlRouteKind.GITHUB_RADAR
    elif host == "arxiv.org":
        route = UrlRouteKind.RESEARCH_DOCUMENT
    elif host == "www.binance.com":
        route = UrlRouteKind.OFFICIAL_EXCHANGE
    elif host == "t.co":
        route = UrlRouteKind.REDIRECT_DISCOVERY
    else:
        route = UrlRouteKind.OPEN_WEB
    return UrlRoute(canonical, host, route)

"""Credentialless, bounded Open Web retrieval primitives."""

from ai4binance.external_intel.retrieval.feeds import FeedEntry, parse_feed
from ai4binance.external_intel.retrieval.source_config import (
    OpenWebPolicy,
    OpenWebSource,
    load_open_web_policy,
)
from ai4binance.external_intel.retrieval.transport import (
    FetchedResource,
    OpenWebFetchError,
    UrlFetcher,
)

__all__ = [
    "FeedEntry",
    "FetchedResource",
    "OpenWebFetchError",
    "OpenWebPolicy",
    "OpenWebSource",
    "UrlFetcher",
    "load_open_web_policy",
    "parse_feed",
]

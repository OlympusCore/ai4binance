"""Bounded RSS and Atom parsing shared by runtime and EIEF."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from defusedxml import ElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

from ai4binance.external_intel.normalization.urls import canonicalize_url


@dataclass(frozen=True, slots=True)
class FeedEntry:
    title: str
    source_url: str
    published_at: datetime


def parse_feed(
    payload: bytes,
    *,
    maximum: int,
    retrieved_at: datetime | None = None,
) -> tuple[FeedEntry, ...]:
    if not 1 <= maximum <= 100:
        raise ValueError("feed maximum must be between 1 and 100")
    if not payload or len(payload) > 2_000_000:
        raise ValueError("feed payload is empty or unbounded")
    observed_at = retrieved_at or datetime.now(UTC)
    try:
        root = ElementTree.fromstring(payload)
    except (ElementTree.ParseError, DefusedXmlException) as error:
        raise ValueError("feed XML is invalid or unsafe") from error
    candidates = _parse_rss(root, observed_at)
    if not candidates:
        candidates = _parse_atom(root, observed_at)
    deduped: dict[str, FeedEntry] = {}
    for item in candidates:
        deduped.setdefault(item.source_url, item)
    return tuple(list(deduped.values())[:maximum])


def _parse_rss(root: ElementTree.Element, fallback: datetime) -> tuple[FeedEntry, ...]:
    items: list[FeedEntry] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        source_url = _safe_url((item.findtext("link") or "").strip())
        if not title or source_url is None:
            continue
        published = _timestamp((item.findtext("pubDate") or "").strip()) or fallback
        items.append(FeedEntry(title, source_url, published))
    return tuple(items)


def _parse_atom(root: ElementTree.Element, fallback: datetime) -> tuple[FeedEntry, ...]:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    items: list[FeedEntry] = []
    for entry in root.findall("./atom:entry", namespace):
        title = (
            entry.findtext("atom:title", default="", namespaces=namespace) or ""
        ).strip()
        source_url = _atom_url(entry, namespace)
        updated = (
            entry.findtext("atom:updated", default="", namespaces=namespace)
            or entry.findtext("atom:published", default="", namespaces=namespace)
            or ""
        ).strip()
        if not title or source_url is None:
            continue
        items.append(FeedEntry(title, source_url, _timestamp(updated) or fallback))
    return tuple(items)


def _atom_url(entry: ElementTree.Element, namespace: dict[str, str]) -> str | None:
    for link in entry.findall("atom:link", namespace):
        href = (link.attrib.get("href") or "").strip()
        rel = (link.attrib.get("rel") or "alternate").strip().casefold()
        if rel == "alternate":
            resolved = _safe_url(href)
            if resolved is not None:
                return resolved
    return None


def _safe_url(value: str) -> str | None:
    try:
        return canonicalize_url(value)
    except ValueError:
        return None


def _timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def feed_host(entry: FeedEntry) -> str:
    return urlsplit(entry.source_url).hostname or ""

"""Deterministic bounded HTML metadata and excerpt extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.models import RetrievedDocument
from ai4binance.external_intel.normalization.urls import canonicalize_url
from ai4binance.external_intel.retrieval.transport import FetchedResource

_TEXT_LIMIT = 8_000


class _ArticleParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.author = "UNKNOWN"
        self.language = "UNKNOWN"
        self.published_at: datetime | None = None
        self.headings: list[str] = []
        self.references: list[str] = []
        self.text_parts: list[str] = []
        self._capture_title = False
        self._capture_heading = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        normalized = tag.casefold()
        if normalized == "html" and attributes.get("lang"):
            self.language = attributes["lang"][:40]
        if normalized in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
            return
        if normalized == "title":
            self._capture_title = True
        if normalized in {"h1", "h2", "h3"}:
            self._capture_heading = True
        if normalized == "meta":
            key = (
                attributes.get("property") or attributes.get("name") or ""
            ).casefold()
            content = attributes.get("content", "").strip()
            if key in {"author", "article:author"} and content:
                self.author = content[:500]
            if key in {"article:published_time", "date", "datepublished"}:
                self.published_at = _datetime(content)
            if key in {"og:title", "twitter:title"} and content and not self.title:
                self.title = content[:1_000]
        if normalized == "a" and attributes.get("href"):
            reference = _safe_reference(self.base_url, attributes["href"])
            if reference is not None and reference not in self.references:
                self.references.append(reference)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript", "svg"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        if normalized == "title":
            self._capture_title = False
        if normalized in {"h1", "h2", "h3"}:
            self._capture_heading = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_title and not self.title:
            self.title = text[:1_000]
        if self._capture_heading and text not in self.headings:
            self.headings.append(text[:500])
        if sum(len(part) for part in self.text_parts) < _TEXT_LIMIT:
            self.text_parts.append(text)


def extract_html_document(
    resource: FetchedResource,
    *,
    observation_id: str,
) -> RetrievedDocument:
    if resource.content_type != "text/html":
        raise ValueError("HTML extraction requires text/html content")
    parser = _ArticleParser(resource.final_url)
    parser.feed(resource.body.decode("utf-8", errors="replace"))
    parser.close()
    title = parser.title.strip() or (urlsplit(resource.final_url).hostname or "UNKNOWN")
    excerpt = " ".join(parser.text_parts)[:_TEXT_LIMIT]
    return RetrievedDocument(
        document_id=eief_id("webdoc", resource.final_url, resource.content_sha256),
        observation_id=observation_id,
        canonical_uri=resource.final_url,
        content_sha256=resource.content_sha256,
        title=title,
        retrieved_at=resource.retrieved_at,
        content_type=resource.content_type,
        byte_count=len(resource.body),
        text_excerpt=excerpt,
        author_or_origin=parser.author,
        published_at=parser.published_at,
        language=parser.language,
        headings=tuple(parser.headings[:50]),
        references=tuple(parser.references[:100]),
    )


def _safe_reference(base_url: str, href: str) -> str | None:
    candidate = urljoin(base_url, href.strip())
    try:
        return canonicalize_url(candidate)
    except ValueError:
        return None


def _datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

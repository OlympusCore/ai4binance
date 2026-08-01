"""Credential-free GitHub discovery boundary for Agent Skill candidates."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from ai4binance.skills.continuous_discovery import DiscoveryCandidate

DEFAULT_DISCOVERY_QUERIES: tuple[str, ...] = (
    "agent framework OR langgraph OR mcp OR multi-agent",
    "python agent workflow",
    "agent skill automation",
)


class CandidateScout(Protocol):
    def discover(
        self,
        *,
        queries: Sequence[str],
        max_candidates: int,
        now: datetime,
    ) -> tuple[DiscoveryCandidate, ...]: ...


@dataclass(frozen=True, slots=True)
class GitHubSearchScout:
    """Search GitHub repositories without credentials or install authority."""

    api_base_url: str = "https://api.github.com"
    timeout_seconds: float = 10.0
    maximum_payload_bytes: int = 1_000_000
    user_agent: str = "ai4binance-skill-discovery"

    def __post_init__(self) -> None:
        if not self.api_base_url.startswith("https://") or "@" in self.api_base_url:
            raise ValueError("GitHub API URL must be credential-free HTTPS")
        if not 0.1 <= self.timeout_seconds <= 30.0:
            raise ValueError("GitHub timeout is invalid")
        if not 10_000 <= self.maximum_payload_bytes <= 5_000_000:
            raise ValueError("GitHub payload limit is invalid")

    def discover(
        self,
        *,
        queries: Sequence[str],
        max_candidates: int,
        now: datetime,
    ) -> tuple[DiscoveryCandidate, ...]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("discovery timestamp must be timezone-aware")
        if not 1 <= max_candidates <= 100:
            raise ValueError("max_candidates must be between 1 and 100")
        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        per_page = min(max_candidates, 50)
        for query in queries:
            if len(candidates) >= max_candidates:
                break
            for item in self._search(query, per_page=per_page):
                candidate = _candidate_from_api_item(item, now)
                if candidate.repository in seen:
                    continue
                candidates.append(candidate)
                seen.add(candidate.repository)
                if len(candidates) >= max_candidates:
                    break
        return tuple(candidates)

    def _search(self, query: str, *, per_page: int) -> tuple[dict[str, object], ...]:
        normalized = query.strip()
        if not normalized:
            return ()
        encoded_query = quote_plus(normalized)
        url = (
            f"{self.api_base_url.rstrip('/')}/search/repositories?"
            f"q={encoded_query}&sort=updated&order=desc&per_page={per_page}"
        )
        request = Request(url, headers={"User-Agent": self.user_agent})  # noqa: S310
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310  # nosec B310
            payload = response.read(self.maximum_payload_bytes + 1)
        if len(payload) > self.maximum_payload_bytes:
            raise ValueError("GitHub response exceeded configured payload limit")
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("GitHub response must be a JSON object")
        raw_items = decoded.get("items", ())
        if not isinstance(raw_items, list):
            raise ValueError("GitHub response items must be a list")
        return tuple(item for item in raw_items if isinstance(item, dict))


def _candidate_from_api_item(
    item: dict[str, object],
    now: datetime,
) -> DiscoveryCandidate:
    pushed_at = _parse_github_datetime(str(item.get("pushed_at", "")))
    topics = item.get("topics", ())
    return DiscoveryCandidate(
        repository=str(item.get("full_name", "")).strip(),
        source_url=str(item.get("html_url", "")).strip(),
        description=str(item.get("description") or ""),
        stars=_int_value(item.get("stargazers_count")),
        language=str(item.get("language") or "Unknown").strip() or "Unknown",
        archived=bool(item.get("archived", False)),
        pushed_at=pushed_at,
        discovered_at=now,
        default_branch=str(item.get("default_branch") or "main").strip() or "main",
        topics=(
            tuple(str(topic).strip() for topic in topics if str(topic).strip())
            if isinstance(topics, list)
            else ()
        ),
    )


def _parse_github_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _int_value(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return 0

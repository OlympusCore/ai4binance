"""Explicit, provenance-first market-context provider governance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urlparse

_PROVIDER_FAILURES = (RuntimeError, OSError, TimeoutError, ValueError)


class ProviderHealthStatus(StrEnum):
    """Operational state of one read-only context provider."""

    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    """Immutable provider declaration with an explicit host allowlist."""

    provider_id: str
    categories: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    provider_revision: str
    license_id: str
    max_event_age: timedelta
    official_source: bool = False
    requires_credentials: bool = False

    def __post_init__(self) -> None:
        if (
            not self.provider_id.strip()
            or not self.categories
            or not self.provider_revision.strip()
            or not self.license_id.strip()
        ):
            raise ValueError("provider capability requires identity and categories")
        if any(not item.strip() for item in (*self.categories, *self.allowed_hosts)):
            raise ValueError("provider capability values cannot be empty")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("provider categories must be unique")
        if len(set(self.allowed_hosts)) != len(self.allowed_hosts):
            raise ValueError("provider hosts must be unique")
        if any(
            host != host.lower() or urlparse(f"https://{host}").hostname != host
            for host in self.allowed_hosts
        ):
            raise ValueError("provider hosts must be normalized hostnames")
        if self.max_event_age <= timedelta(0):
            raise ValueError("provider maximum event age must be positive")


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """One provider health result without secret or exception detail leakage."""

    provider_id: str
    checked_at: datetime
    status: ProviderHealthStatus
    active_backend: str | None = None
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider health requires identity")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("provider health timestamp must be timezone-aware")
        if self.status is ProviderHealthStatus.AVAILABLE and self.blockers:
            raise ValueError("available provider cannot contain blockers")
        if self.status is not ProviderHealthStatus.AVAILABLE and not self.blockers:
            raise ValueError("degraded provider requires explicit blockers")


@dataclass(frozen=True, slots=True)
class MarketContextRequest:
    """Bounded provider request tied to one immutable market snapshot."""

    snapshot_id: str
    symbol: str
    requested_at: datetime
    categories: tuple[str, ...] = ("macro_calendar", "exchange_announcement")

    def __post_init__(self) -> None:
        if (
            not self.snapshot_id.strip()
            or not self.symbol.strip()
            or not self.categories
        ):
            raise ValueError("market-context request is incomplete")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("market-context request timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MarketContextEvent:
    """Normalized high-impact event with no free-form instruction payload."""

    event_id: str
    provider_id: str
    title: str
    scheduled_at: datetime
    retrieved_at: datetime
    impact: str
    category: str
    source_url: str
    content_hash: str

    def __post_init__(self) -> None:
        required = (
            self.event_id,
            self.provider_id,
            self.title,
            self.category,
            self.source_url,
            self.content_hash,
        )
        if any(not item.strip() for item in required):
            raise ValueError("market-context event fields cannot be empty")
        for name, value in (
            ("scheduled_at", self.scheduled_at),
            ("retrieved_at", self.retrieved_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise ValueError("market-context source must be credential-free HTTPS")
        if self.impact not in {"HIGH", "CRITICAL"}:
            raise ValueError("market-context impact must be HIGH or CRITICAL")
        if len(self.content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.content_hash
        ):
            raise ValueError("market-context content hash must be lowercase SHA-256")

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        provider_id: str,
        title: str,
        scheduled_at: datetime,
        retrieved_at: datetime,
        impact: str,
        category: str,
        source_url: str,
    ) -> MarketContextEvent:
        normalized = "|".join(
            (
                event_id.strip(),
                provider_id.strip(),
                title.strip(),
                scheduled_at.isoformat(),
                impact.strip().upper(),
                category.strip(),
                source_url.strip(),
            )
        )
        return cls(
            event_id=event_id.strip(),
            provider_id=provider_id.strip(),
            title=title.strip(),
            scheduled_at=scheduled_at,
            retrieved_at=retrieved_at,
            impact=impact.strip().upper(),
            category=category.strip(),
            source_url=source_url.strip(),
            content_hash=sha256(normalized.encode("utf-8")).hexdigest(),
        )


class MarketContextProvider(Protocol):
    """Read-only adapter contract; no provider may own signal authority."""

    @property
    def capability(self) -> ProviderCapability:
        """Describe supported categories and trusted hosts."""

    def health(self, checked_at: datetime) -> ProviderHealth:
        """Probe actual provider readiness without returning credentials."""

    def fetch(self, request: MarketContextRequest) -> tuple[MarketContextEvent, ...]:
        """Return normalized events for one explicit request."""


@dataclass(frozen=True, slots=True)
class MarketContextBatch:
    """Deterministic provider aggregation with explicit degraded state."""

    snapshot_id: str
    events: tuple[MarketContextEvent, ...]
    provider_health: tuple[ProviderHealth, ...]
    provider_capabilities: tuple[ProviderCapability, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("market-context batch requires snapshot identity")
        if self.execution_allowed:
            raise ValueError("market context cannot grant execution authority")

    def as_news_snapshot(self) -> Mapping[str, object]:
        """Expose only the strict event fields consumed by Market Outlook."""
        events = tuple(
            {
                "event_id": item.event_id,
                "title": item.title,
                "scheduled_at": item.scheduled_at,
                "impact": item.impact,
                "source": item.provider_id,
                "source_url": item.source_url,
                "content_hash": item.content_hash,
            }
            for item in self.events
        )
        return MappingProxyType(
            {
                "high_impact_events": events,
                "provider_blockers": self.blockers,
                "provider_health": tuple(self.provider_health),
                "provider_provenance": tuple(
                    {
                        "provider_id": item.provider_id,
                        "provider_revision": item.provider_revision,
                        "license_id": item.license_id,
                        "official_source": item.official_source,
                    }
                    for item in self.provider_capabilities
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class MarketContextRegistry:
    """Explicit provider registry; it never performs a silent fallback."""

    providers: tuple[MarketContextProvider, ...]
    _by_id: Mapping[str, MarketContextProvider] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        by_id = {
            provider.capability.provider_id: provider for provider in self.providers
        }
        if len(by_id) != len(self.providers):
            raise ValueError("market-context provider IDs must be unique")
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def collect(
        self,
        request: MarketContextRequest,
        provider_ids: tuple[str, ...],
    ) -> MarketContextBatch:
        """Collect only explicitly selected providers in stable order."""
        if not provider_ids or len(set(provider_ids)) != len(provider_ids):
            raise ValueError("explicit unique market-context provider IDs are required")
        health_results: list[ProviderHealth] = []
        events: list[MarketContextEvent] = []
        blockers: list[str] = []
        capabilities: list[ProviderCapability] = []
        for provider_id in provider_ids:
            provider = self._by_id.get(provider_id)
            if provider is None:
                blockers.append(f"MARKET_CONTEXT_PROVIDER_UNKNOWN:{provider_id}")
                continue
            capabilities.append(provider.capability)
            health = self._safe_health(provider, request.requested_at)
            health_results.append(health)
            if health.status is not ProviderHealthStatus.AVAILABLE:
                blockers.extend(health.blockers)
                continue
            try:
                fetched = provider.fetch(request)
            except _PROVIDER_FAILURES:
                blockers.append(f"MARKET_CONTEXT_FETCH_FAILED:{provider_id}")
                continue
            for event in fetched:
                validation_blocker = self._event_blocker(
                    provider.capability, event, request
                )
                if validation_blocker is not None:
                    blockers.append(validation_blocker)
                    continue
                events.append(event)
        unique_events = {event.event_id: event for event in events}
        ordered_events = tuple(
            sorted(
                unique_events.values(),
                key=lambda item: (item.scheduled_at, item.event_id),
            )
        )
        return MarketContextBatch(
            snapshot_id=request.snapshot_id,
            events=ordered_events,
            provider_health=tuple(health_results),
            provider_capabilities=tuple(capabilities),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _safe_health(
        provider: MarketContextProvider,
        checked_at: datetime,
    ) -> ProviderHealth:
        try:
            health = provider.health(checked_at)
        except _PROVIDER_FAILURES:
            return ProviderHealth(
                provider_id=provider.capability.provider_id,
                checked_at=checked_at,
                status=ProviderHealthStatus.UNAVAILABLE,
                blockers=(
                    f"MARKET_CONTEXT_HEALTH_FAILED:{provider.capability.provider_id}",
                ),
            )
        if health.provider_id != provider.capability.provider_id:
            return ProviderHealth(
                provider_id=provider.capability.provider_id,
                checked_at=checked_at,
                status=ProviderHealthStatus.UNAVAILABLE,
                blockers=("MARKET_CONTEXT_PROVIDER_IDENTITY_MISMATCH",),
            )
        return health

    @staticmethod
    def _event_blocker(
        capability: ProviderCapability,
        event: MarketContextEvent,
        request: MarketContextRequest,
    ) -> str | None:
        if event.provider_id != capability.provider_id:
            return f"MARKET_CONTEXT_EVENT_PROVIDER_MISMATCH:{capability.provider_id}"
        hostname = urlparse(event.source_url).hostname
        if hostname not in capability.allowed_hosts:
            return f"MARKET_CONTEXT_SOURCE_NOT_ALLOWED:{capability.provider_id}"
        if event.category not in capability.categories:
            return f"MARKET_CONTEXT_CATEGORY_NOT_ALLOWED:{capability.provider_id}"
        if event.category not in request.categories:
            return f"MARKET_CONTEXT_CATEGORY_NOT_REQUESTED:{capability.provider_id}"
        if event.retrieved_at > request.requested_at:
            return f"MARKET_CONTEXT_EVENT_TIMESTAMP_INVALID:{capability.provider_id}"
        if request.requested_at - event.retrieved_at > capability.max_event_age:
            return f"MARKET_CONTEXT_EVENT_STALE:{capability.provider_id}"
        expected = MarketContextEvent.create(
            event_id=event.event_id,
            provider_id=event.provider_id,
            title=event.title,
            scheduled_at=event.scheduled_at,
            retrieved_at=event.retrieved_at,
            impact=event.impact,
            category=event.category,
            source_url=event.source_url,
        ).content_hash
        if event.content_hash != expected:
            return f"MARKET_CONTEXT_CONTENT_HASH_INVALID:{capability.provider_id}"
        return None

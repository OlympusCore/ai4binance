"""Strict JSON configuration for credentialless Open Web sources."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.external_intel.core.enums import MissionName, SourceType
from ai4binance.external_intel.core.validation import (
    require_text,
    require_unique_text,
    require_unit_interval,
)
from ai4binance.external_intel.normalization.urls import canonicalize_url

MAX_CONFIG_BYTES = 256_000
_NETWORK_MODE = "ALLOWLISTED_PUBLIC_WEB"
_SEARCH_MODE = "DIRECT_SOURCES_ONLY"
_LLM_MODES = frozenset({"DISABLED", "LOCAL_QWEN_OPTIONAL"})


@dataclass(frozen=True, slots=True)
class OpenWebSource:
    source_id: str
    feed_url: str
    allowed_hosts: tuple[str, ...]
    mission: MissionName
    source_type: SourceType
    source_tier: str
    reliability: float
    enabled: bool
    required: bool
    robots_required: bool
    max_items: int

    def __post_init__(self) -> None:
        require_text("open-web source id", self.source_id, maximum=100)
        if canonicalize_url(self.feed_url) != self.feed_url:
            raise ValueError("open-web feed URL must already be canonical")
        require_unique_text(
            "open-web allowed hosts", self.allowed_hosts, allow_empty=False
        )
        if any(host != host.casefold() or "/" in host for host in self.allowed_hosts):
            raise ValueError("open-web hosts must be normalized hostnames")
        if self.source_tier not in {f"TIER_{index}" for index in range(5)}:
            raise ValueError("open-web source tier is invalid")
        require_unit_interval("open-web source reliability", self.reliability)
        if not 1 <= self.max_items <= 20:
            raise ValueError("open-web source max_items must be between 1 and 20")
        if self.required and not self.enabled:
            raise ValueError("required open-web sources cannot be disabled")


@dataclass(frozen=True, slots=True)
class OpenWebPolicy:
    schema_version: str
    network_mode: str
    search_mode: str
    llm_mode: str
    cloud_llm_allowed: bool
    credentialed_provider_allowed: bool
    persist_full_article_text: bool
    seed_allowed_hosts: tuple[str, ...]
    sources: tuple[OpenWebSource, ...]

    def __post_init__(self) -> None:
        require_text("open-web schema version", self.schema_version, maximum=40)
        if self.network_mode != _NETWORK_MODE or self.search_mode != _SEARCH_MODE:
            raise ValueError(
                "open-web policy must remain direct-source and allowlisted"
            )
        if self.llm_mode not in _LLM_MODES:
            raise ValueError("open-web LLM mode is invalid")
        if (
            self.cloud_llm_allowed
            or self.credentialed_provider_allowed
            or self.persist_full_article_text
        ):
            raise ValueError("open-web default policy cannot enable external authority")
        require_unique_text(
            "open-web seed hosts", self.seed_allowed_hosts, allow_empty=False
        )
        source_ids = tuple(source.source_id for source in self.sources)
        require_unique_text("open-web source ids", source_ids, allow_empty=False)

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self.seed_allowed_hosts,
                    *(host for source in self.sources for host in source.allowed_hosts),
                )
            )
        )


def default_open_web_policy_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "research" / "open_web_sources.json"


def load_open_web_policy(path: Path | None = None) -> OpenWebPolicy:
    resolved = (path or default_open_web_policy_path()).resolve()
    if resolved.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("open-web policy exceeds bounded size")
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    payload = _mapping(raw, "open-web policy")
    _require_keys(
        payload,
        {
            "schema_version",
            "network_mode",
            "search_mode",
            "llm_mode",
            "cloud_llm_allowed",
            "credentialed_provider_allowed",
            "persist_full_article_text",
            "seed_allowed_hosts",
            "sources",
        },
        "open-web policy",
    )
    sources = tuple(_source(item) for item in _sequence(payload["sources"], "sources"))
    return OpenWebPolicy(
        schema_version=str(payload["schema_version"]),
        network_mode=str(payload["network_mode"]),
        search_mode=str(payload["search_mode"]),
        llm_mode=str(payload["llm_mode"]),
        cloud_llm_allowed=_boolean(payload["cloud_llm_allowed"], "cloud LLM"),
        credentialed_provider_allowed=_boolean(
            payload["credentialed_provider_allowed"], "credentialed provider"
        ),
        persist_full_article_text=_boolean(
            payload["persist_full_article_text"], "full article persistence"
        ),
        seed_allowed_hosts=_strings(payload["seed_allowed_hosts"], "seed hosts"),
        sources=sources,
    )


def _source(value: object) -> OpenWebSource:
    payload = _mapping(value, "source")
    _require_keys(
        payload,
        {
            "source_id",
            "feed_url",
            "allowed_hosts",
            "mission",
            "source_type",
            "source_tier",
            "reliability",
            "enabled",
            "required",
            "robots_required",
            "max_items",
        },
        "open-web source",
    )
    reliability = payload["reliability"]
    max_items = payload["max_items"]
    if isinstance(reliability, bool) or not isinstance(reliability, (int, float)):
        raise ValueError("source reliability must be numeric")
    if isinstance(max_items, bool) or not isinstance(max_items, int):
        raise ValueError("source max_items must be an integer")
    return OpenWebSource(
        source_id=str(payload["source_id"]),
        feed_url=str(payload["feed_url"]),
        allowed_hosts=_strings(payload["allowed_hosts"], "source hosts"),
        mission=MissionName(str(payload["mission"])),
        source_type=SourceType(str(payload["source_type"])),
        source_tier=str(payload["source_tier"]),
        reliability=float(reliability),
        enabled=_boolean(payload["enabled"], "source enabled"),
        required=_boolean(payload["required"], "source required"),
        robots_required=_boolean(payload["robots_required"], "robots required"),
        max_items=max_items,
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    return cast(Sequence[object], value)


def _strings(value: object, name: str) -> tuple[str, ...]:
    result = tuple(str(item) for item in _sequence(value, name))
    require_unique_text(name, result, allow_empty=False)
    return result


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _require_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{name} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )

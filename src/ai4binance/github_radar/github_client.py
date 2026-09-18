"""Bounded read-only GitHub API client for Radar discovery."""

from __future__ import annotations

import base64
import http.client
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, cast
from urllib.parse import quote, urlencode

from ai4binance.github_radar.models import (
    FetchedDocument,
    GitHubRepository,
    RepositorySource,
)

MAX_RESPONSE_BYTES = 2_000_000
MAX_DOCUMENT_BYTES = 256_000
_ALLOWED_ROOT_FILES = frozenset(
    {"pyproject.toml", "requirements.txt", "requirements-dev.txt"}
)
_ALLOWED_PREFIXES = ("docs/", "examples/", "tests/")


class GitHubApiTransport(Protocol):
    def get_json(
        self, path: str, parameters: Mapping[str, str] | None = None
    ) -> object: ...


class GitHubDiscoveryClient(Protocol):
    def search_repositories(
        self, query: str, *, limit: int
    ) -> tuple[GitHubRepository, ...]: ...

    def resolve_source(self, repository: GitHubRepository) -> RepositorySource: ...

    def fetch_documents(
        self, source: RepositorySource, *, maximum: int
    ) -> tuple[FetchedDocument, ...]: ...


class HttpsGitHubTransport:
    """GET-only transport pinned to api.github.com."""

    def __init__(
        self, token: str | None = None, *, timeout_seconds: float = 10.0
    ) -> None:
        if token is not None and not token.strip():
            raise ValueError("GitHub token cannot be blank")
        if not 1.0 <= timeout_seconds <= 30.0:
            raise ValueError("GitHub timeout must be between 1 and 30 seconds")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def get_json(
        self, path: str, parameters: Mapping[str, str] | None = None
    ) -> object:
        if not path.startswith("/") or "//" in path or ".." in path:
            raise ValueError("GitHub API path is invalid")
        query = f"?{urlencode(parameters)}" if parameters else ""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AI4BINANCE-GitHub-Radar/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        connection = http.client.HTTPSConnection(
            "api.github.com", timeout=self._timeout_seconds
        )
        try:
            connection.request("GET", f"{path}{query}", headers=headers)
            response = connection.getresponse()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("GitHub API response exceeds bounded size")
            if response.status != 200:
                raise RuntimeError(
                    f"GitHub API GET failed with status {response.status}"
                )
            return json.loads(body.decode("utf-8"))
        finally:
            connection.close()


class PublicGitHubClient:
    def __init__(self, transport: GitHubApiTransport) -> None:
        self._transport = transport

    def search_repositories(
        self, query: str, *, limit: int = 5
    ) -> tuple[GitHubRepository, ...]:
        if not query.strip() or not 1 <= limit <= 10:
            raise ValueError("GitHub search query or limit is invalid")
        payload = _mapping(
            self._transport.get_json(
                "/search/repositories",
                {
                    "q": query,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": str(limit),
                },
            ),
            "search response",
        )
        items = _sequence(payload.get("items"), "search items")
        repositories: list[GitHubRepository] = []
        for raw in items[:limit]:
            item = _mapping(raw, "repository")
            owner = _mapping(item.get("owner"), "owner")
            repositories.append(
                GitHubRepository(
                    owner=str(owner.get("login", "")),
                    name=str(item.get("name", "")),
                    url=str(item.get("html_url", "")),
                    default_branch=str(item.get("default_branch", "")),
                    stars=int(str(item.get("stargazers_count", 0))),
                    pushed_at=_datetime(str(item.get("pushed_at", ""))),
                )
            )
        return tuple(repositories)

    def resolve_source(self, repository: GitHubRepository) -> RepositorySource:
        owner = quote(repository.owner, safe="")
        name = quote(repository.name, safe="")
        branch = quote(repository.default_branch, safe="")
        commit = _mapping(
            self._transport.get_json(f"/repos/{owner}/{name}/commits/{branch}"),
            "commit response",
        )
        license_payload = _mapping(
            self._transport.get_json(f"/repos/{owner}/{name}/license"),
            "license response",
        )
        license_item = _mapping(license_payload.get("license"), "license")
        return RepositorySource(
            repository=f"{repository.owner}/{repository.name}",
            url=repository.url,
            pinned_revision=str(commit.get("sha", "")),
            license_id=str(license_item.get("spdx_id", "UNKNOWN")),
            language="UNKNOWN",
        )

    def fetch_documents(
        self, source: RepositorySource, *, maximum: int = 20
    ) -> tuple[FetchedDocument, ...]:
        if not 1 <= maximum <= 50:
            raise ValueError("GitHub document maximum must be between 1 and 50")
        owner, name = _owner_name(source.repository)
        tree = _mapping(
            self._transport.get_json(
                f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/git/trees/"
                f"{source.pinned_revision}",
                {"recursive": "1"},
            ),
            "tree response",
        )
        if bool(tree.get("truncated", False)):
            raise ValueError("GitHub tree response is truncated")
        entries = _sequence(tree.get("tree"), "tree entries")
        selected: list[str] = []
        for raw in entries:
            item = _mapping(raw, "tree item")
            path = str(item.get("path", ""))
            size = int(str(item.get("size", 0)))
            if (
                item.get("type") == "blob"
                and 0 < size <= MAX_DOCUMENT_BYTES
                and _allowed_path(path)
            ):
                selected.append(path)
        documents: list[FetchedDocument] = []
        for path in sorted(selected)[:maximum]:
            encoded_path = quote(path, safe="/")
            payload = _mapping(
                self._transport.get_json(
                    f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/contents/"
                    f"{encoded_path}",
                    {"ref": source.pinned_revision},
                ),
                "content response",
            )
            encoded = str(payload.get("content", "")).replace("\n", "")
            content = base64.b64decode(encoded, validate=True).decode(
                "utf-8", errors="replace"
            )
            documents.append(FetchedDocument(path, content))
        return tuple(documents)


def _allowed_path(path: str) -> bool:
    lowered = path.lower()
    root_name = lowered.rsplit("/", maxsplit=1)[-1]
    return (
        (
            "/" not in lowered
            and (root_name.startswith("readme") or root_name.startswith("license"))
        )
        or lowered in _ALLOWED_ROOT_FILES
        or lowered.startswith(_ALLOWED_PREFIXES)
    )


def _owner_name(repository: str) -> tuple[str, str]:
    parts = repository.split("/")
    if len(parts) != 2 or any(not item.strip() for item in parts):
        raise ValueError("GitHub repository must use owner/name")
    return parts[0], parts[1]


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"GitHub {name} must be a mapping")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"GitHub {name} must be a list")
    return value


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("GitHub timestamp must be timezone-aware")
    return parsed

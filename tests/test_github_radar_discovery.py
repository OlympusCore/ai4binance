"""Bounded read-only GitHub discovery tests."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import UTC, datetime

from ai4binance.github_radar.discovery import discover_candidates
from ai4binance.github_radar.github_client import PublicGitHubClient
from ai4binance.github_radar.local_baseline import build_local_capability_baseline
from ai4binance.github_radar.models import (
    FetchedDocument,
    GitHubRepository,
    RepositorySource,
)
from ai4binance.github_radar.ontology import load_default_ontology
from ai4binance.github_radar.query_planner import RadarQuery, plan_queries
from ai4binance.github_radar.reporting import discovery_payload


class FakeApiTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, str] | None]] = []

    def get_json(
        self, path: str, parameters: Mapping[str, str] | None = None
    ) -> object:
        self.calls.append((path, parameters))
        if path == "/search/repositories":
            return {
                "items": [
                    {
                        "name": "research-engine",
                        "html_url": "https://github.com/example/research-engine",
                        "default_branch": "main",
                        "stargazers_count": 12,
                        "pushed_at": "2026-08-08T12:00:00Z",
                        "owner": {"login": "example"},
                    }
                ]
            }
        if path.endswith("/commits/main"):
            return {"sha": "0123456789abcdef0123456789abcdef01234567"}
        if path.endswith("/license"):
            return {"license": {"spdx_id": "MIT"}}
        if "/git/trees/" in path:
            return {
                "truncated": False,
                "tree": [
                    {"path": "README.md", "type": "blob", "size": 30},
                    {"path": "src/live.py", "type": "blob", "size": 30},
                    {"path": "tests/test_fill.py", "type": "blob", "size": 50},
                ],
            }
        if "/contents/README.md" in path:
            return {"content": _encoded("Deterministic realistic fill model")}
        if "/contents/tests/test_fill.py" in path:
            return {"content": _encoded("future = values.shift(-1)")}
        raise AssertionError(path)


class FakeDiscoveryClient:
    def search_repositories(
        self, query: str, *, limit: int
    ) -> tuple[GitHubRepository, ...]:
        assert query
        assert limit == 1
        return (
            GitHubRepository(
                owner="example",
                name="research-engine",
                url="https://github.com/example/research-engine",
                default_branch="main",
                stars=12,
                pushed_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
        )

    def resolve_source(self, repository: GitHubRepository) -> RepositorySource:
        return RepositorySource(
            repository=f"{repository.owner}/{repository.name}",
            url=repository.url,
            pinned_revision="0123456789abcdef0123456789abcdef01234567",
            license_id="MIT",
            language="Python",
        )

    def fetch_documents(
        self, source: RepositorySource, *, maximum: int
    ) -> tuple[FetchedDocument, ...]:
        assert maximum == 2
        return (
            FetchedDocument("README.md", "Deterministic realistic fill model"),
            FetchedDocument("tests/test_fill.py", "future = values.shift(-1)"),
        )


def test_public_client_resolves_revision_and_reads_only_allowed_surfaces() -> None:
    transport = FakeApiTransport()
    client = PublicGitHubClient(transport)

    repository = client.search_repositories("realistic fills", limit=1)[0]
    source = client.resolve_source(repository)
    documents = client.fetch_documents(source, maximum=5)

    assert source.pinned_revision == "0123456789abcdef0123456789abcdef01234567"
    assert source.license_id == "MIT"
    assert {item.path for item in documents} == {"README.md", "tests/test_fill.py"}
    assert all(call[0].startswith("/") for call in transport.calls)
    assert not any("src/live.py" in call[0] for call in transport.calls)


def test_discovery_maps_repository_to_atomic_capability_and_blocks_execution() -> None:
    query = RadarQuery(
        capability_id="R26-C01",
        query="realistic fill model language:Python archived:false",
        local_status=build_local_capability_baseline()[0].status,
    )

    candidates = discover_candidates(
        FakeDiscoveryClient(),
        (query,),
        repositories_per_query=1,
        documents_per_repository=2,
    )

    candidate = candidates[0]
    assert candidate.capability_id == "R26-C01"
    assert len(candidate.evidence) == 2
    assert any(
        item.startswith("POSSIBLE_FUTURE_INDEX_ACCESS:") for item in candidate.risks
    )
    assert "HUMAN_RATINGS_REQUIRED" in candidate.blockers
    assert "EXTERNAL_CODE_EXECUTION_BLOCKED" in candidate.blockers
    assert candidate.execution_allowed is False
    assert candidate.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    payload = discovery_payload(candidates)
    serialized_candidates = payload["candidates"]
    topics = payload["research_topics"]
    assert isinstance(serialized_candidates, tuple)
    assert isinstance(topics, tuple)
    serialized_candidate = serialized_candidates[0]
    assert isinstance(serialized_candidate, dict)
    assessment = serialized_candidate["research_assessment"]
    assert isinstance(assessment, dict)
    assert assessment["recommended_action"] in {
        "IGNORE",
        "WATCH",
        "RESEARCH",
        "PROTOTYPE",
        "VALIDATE",
        "ADOPT_CANDIDATE",
        "REJECT",
    }
    assert assessment["execution_allowed"] is False
    assert assessment["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert len(topics) == 14


def test_query_planner_prioritizes_local_gaps_and_accepts_explicit_scope() -> None:
    ontology = load_default_ontology()
    baseline = build_local_capability_baseline(ontology=ontology)

    planned = plan_queries(
        ontology,
        baseline,
        capability_ids=("R26-C01", "R30-C02"),
        maximum=2,
    )

    assert {item.capability_id for item in planned} == {"R26-C01", "R30-C02"}
    assert all("language:Python archived:false" in item.query for item in planned)


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")

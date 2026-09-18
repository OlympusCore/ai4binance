"""Bounded discovery that maps repositories to atomic capability gaps."""

from __future__ import annotations

from ai4binance.github_radar.evidence_extractor import extract_evidence
from ai4binance.github_radar.github_client import GitHubDiscoveryClient
from ai4binance.github_radar.models import DiscoveryCandidate
from ai4binance.github_radar.query_planner import RadarQuery
from ai4binance.github_radar.static_risk import scan_static_risks


def discover_candidates(
    client: GitHubDiscoveryClient,
    queries: tuple[RadarQuery, ...],
    *,
    repositories_per_query: int = 3,
    documents_per_repository: int = 20,
) -> tuple[DiscoveryCandidate, ...]:
    if not 1 <= repositories_per_query <= 5:
        raise ValueError("repositories per query must be between 1 and 5")
    if not 1 <= documents_per_repository <= 50:
        raise ValueError("documents per repository must be between 1 and 50")
    candidates: list[DiscoveryCandidate] = []
    identities: set[tuple[str, str, str]] = set()
    for query in queries:
        repositories = client.search_repositories(
            query.query, limit=repositories_per_query
        )
        for repository in repositories:
            source = client.resolve_source(repository)
            identity = (
                query.capability_id,
                source.repository,
                source.pinned_revision,
            )
            if identity in identities:
                continue
            documents = client.fetch_documents(source, maximum=documents_per_repository)
            evidence = extract_evidence(source, documents)
            risks = scan_static_risks(documents)
            blockers = tuple(
                dict.fromkeys(
                    (
                        "HUMAN_RATINGS_REQUIRED",
                        "LOCAL_REPRODUCTION_PENDING",
                        "STATIC_FINDINGS_REQUIRE_REVIEW",
                        *(
                            ("LICENSE_UNKNOWN_REUSE_BLOCKED",)
                            if source.license_id.upper()
                            in {"UNKNOWN", "NOASSERTION", "NONE"}
                            else ()
                        ),
                        *(f"RISK_REVIEW_REQUIRED:{risk}" for risk in risks),
                        "EXTERNAL_CODE_INSTALL_BLOCKED",
                        "EXTERNAL_CODE_EXECUTION_BLOCKED",
                        "LIVE_ORDER_BLOCKED",
                    )
                )
            )
            candidates.append(
                DiscoveryCandidate(
                    capability_id=query.capability_id,
                    query=query.query,
                    source=source,
                    evidence=evidence,
                    risks=risks,
                    blockers=blockers,
                )
            )
            identities.add(identity)
    return tuple(candidates)

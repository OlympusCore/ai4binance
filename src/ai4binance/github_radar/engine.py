"""Capability-first GitHub Radar orchestration without clone or execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai4binance.github_radar.catalog_adapter import to_research_catalog_entry
from ai4binance.github_radar.discovery import discover_candidates
from ai4binance.github_radar.github_client import GitHubDiscoveryClient
from ai4binance.github_radar.local_baseline import build_local_capability_baseline
from ai4binance.github_radar.models import (
    DiscoveryCandidate,
    LocalCapabilityAssessment,
    RepositoryEvidence,
    ResearchOntology,
    ResearchUnitEvaluation,
)
from ai4binance.github_radar.ontology import load_default_ontology
from ai4binance.github_radar.query_planner import plan_queries
from ai4binance.github_radar.scoring import ScoringPolicy, evaluate_repository_evidence
from ai4binance.research_catalog import ResearchCatalog, ResearchCatalogEntry


@dataclass(frozen=True, slots=True)
class RadarAssessment:
    evaluation: ResearchUnitEvaluation
    catalog_entry: ResearchCatalogEntry
    catalog: ResearchCatalog

    def __post_init__(self) -> None:
        if self.catalog_entry.entry_id != self.evaluation.research_id:
            raise ValueError("Radar evaluation and catalog identity must match")
        if self.catalog.entries[-1] != self.catalog_entry:
            raise ValueError("Radar catalog connection is incomplete")


@dataclass(frozen=True, slots=True)
class GitHubRadarEngine:
    repository_root: Path
    ontology: ResearchOntology
    policy: ScoringPolicy | None = None

    @classmethod
    def from_repository(
        cls,
        repository_root: Path | None = None,
        *,
        policy: ScoringPolicy | None = None,
    ) -> GitHubRadarEngine:
        root = (repository_root or Path.cwd()).resolve()
        return cls(root, load_default_ontology(root), policy)

    def local_baseline(self) -> tuple[LocalCapabilityAssessment, ...]:
        return build_local_capability_baseline(self.repository_root, self.ontology)

    def discover(
        self,
        client: GitHubDiscoveryClient,
        *,
        capability_ids: tuple[str, ...] = (),
        maximum_queries: int = 20,
        repositories_per_query: int = 3,
        documents_per_repository: int = 20,
    ) -> tuple[DiscoveryCandidate, ...]:
        queries = plan_queries(
            self.ontology,
            self.local_baseline(),
            capability_ids=capability_ids,
            maximum=maximum_queries,
        )
        return discover_candidates(
            client,
            queries,
            repositories_per_query=repositories_per_query,
            documents_per_repository=documents_per_repository,
        )

    def assess(
        self,
        evidence: RepositoryEvidence,
        *,
        observed_at: datetime,
        catalog: ResearchCatalog | None = None,
    ) -> RadarAssessment:
        if evidence.capability_id not in self.ontology.by_capability_id:
            raise ValueError("repository evidence capability is not in the ontology")
        evaluation = evaluate_repository_evidence(evidence, self.policy)
        entry = to_research_catalog_entry(evaluation, observed_at=observed_at)
        updated_catalog = (catalog or ResearchCatalog()).add(entry)
        return RadarAssessment(evaluation, entry, updated_catalog)

"""Governed, capability-first GitHub research radar."""

from ai4binance.github_radar.catalog_adapter import to_research_catalog_entry
from ai4binance.github_radar.local_baseline import build_local_capability_baseline
from ai4binance.github_radar.models import (
    RecommendationAction,
    RepositoryEvidence,
    RepositorySource,
    ResearchUnitEvaluation,
)
from ai4binance.github_radar.ontology import load_default_ontology
from ai4binance.github_radar.scoring import evaluate_repository_evidence

__all__ = (
    "RecommendationAction",
    "RepositoryEvidence",
    "RepositorySource",
    "ResearchUnitEvaluation",
    "build_local_capability_baseline",
    "evaluate_repository_evidence",
    "load_default_ontology",
    "to_research_catalog_entry",
)

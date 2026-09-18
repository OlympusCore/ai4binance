"""Negative-path tests for immutable GitHub Radar authority contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.github_radar.__main__ import _load_repository_evidence
from ai4binance.github_radar.evidence_extractor import extract_evidence
from ai4binance.github_radar.local_baseline import build_local_capability_baseline
from ai4binance.github_radar.models import (
    DimensionRating,
    DiscoveryCandidate,
    EvidenceFragment,
    FetchedDocument,
    GitHubRepository,
    LocalCapabilityStatus,
    RecommendationAction,
    RepositorySource,
    ResearchDomain,
    ResearchOntology,
    ResearchUnitEvaluation,
    VerificationProfile,
    _require_unique,
)
from ai4binance.github_radar.ontology import load_default_ontology
from ai4binance.github_radar.query_planner import plan_queries
from ai4binance.github_radar.scoring import evaluate_repository_evidence


def source() -> RepositorySource:
    return RepositorySource(
        repository="example/research-engine",
        url="https://github.com/example/research-engine",
        pinned_revision="0123456789abcdef0123456789abcdef01234567",
        license_id="MIT",
        language="Python",
    )


def evaluation() -> ResearchUnitEvaluation:
    evidence = _load_repository_evidence(
        Path("tests/fixtures/github_radar/repository_evidence.json")
    )
    return evaluate_repository_evidence(evidence)


def test_unique_and_identity_guards_reject_malformed_taxonomy() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        _require_unique("items", (), allow_empty=False)
    with pytest.raises(ValueError, match="bounded and unique"):
        _require_unique("items", ("duplicate", "duplicate"))
    with pytest.raises(ValueError, match="invalid value"):
        _require_unique("items", (" ",))
    with pytest.raises(ValueError, match="domain identity"):
        ResearchDomain("R31", "Invalid")
    with pytest.raises(ValueError, match="profile identity"):
        VerificationProfile("V13", "Invalid")


def test_atomic_capability_rejects_invalid_identity_targets_and_profile() -> None:
    valid = load_default_ontology().capabilities[0]
    with pytest.raises(ValueError, match="identity"):
        replace(valid, capability_id="bad")
    with pytest.raises(ValueError, match="domain"):
        replace(valid, domain_id="R31")
    with pytest.raises(ValueError, match="encoded domain"):
        replace(valid, domain_id="R01")
    with pytest.raises(ValueError, match="title and query"):
        replace(valid, title="")
    with pytest.raises(ValueError, match="profile"):
        replace(valid, verification_profiles=("V13",))


def test_ontology_rejects_unknown_references_and_authority_escalation() -> None:
    ontology = load_default_ontology()
    with pytest.raises(ValueError, match="identity"):
        replace(ontology, ontology_id="")
    with pytest.raises(ValueError, match="unknown domain"):
        replace(ontology, domains=ontology.domains[1:])
    with pytest.raises(ValueError, match="unknown verification"):
        replace(ontology, verification_profiles=ontology.verification_profiles[1:])
    with pytest.raises(ValueError, match="trading authority"):
        replace(ontology, execution_allowed=True)


def test_source_evidence_and_rating_guards_reject_untrusted_shapes() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(source(), url="https://user:secret@github.com/example/repo")
    with pytest.raises(ValueError, match="pinned 40-char"):
        replace(source(), pinned_revision="main")
    with pytest.raises(ValueError, match="license and language"):
        replace(source(), license_id="")

    fragment = EvidenceFragment("TEST", "tests/test.py", "claim", "a" * 64)
    with pytest.raises(ValueError, match="non-empty and bounded"):
        replace(fragment, claim="")
    with pytest.raises(ValueError, match="SHA-256"):
        replace(fragment, content_sha256="bad")
    with pytest.raises(ValueError, match="zero and one"):
        DimensionRating("tests", 1.1, "invalid")
    with pytest.raises(ValueError, match="rationale"):
        DimensionRating("tests", 1.0, "")


def test_research_unit_rejects_invalid_score_reuse_blockers_and_authority() -> None:
    valid = evaluation()
    with pytest.raises(ValueError, match="identity"):
        replace(valid, research_id="bad")
    with pytest.raises(ValueError, match="one hundred"):
        replace(valid, total_score=101.0)
    with pytest.raises(ValueError, match="hard blockers"):
        replace(valid, blockers=("BLOCKED",))
    with pytest.raises(ValueError, match="reuse mode"):
        replace(valid, reuse_mode="COPY_CODE")
    with pytest.raises(ValueError, match="trading authority"):
        replace(valid, execution_allowed=True)


def test_local_github_document_and_discovery_contracts_fail_closed() -> None:
    baseline = build_local_capability_baseline()[0]
    with pytest.raises(ValueError, match="capability"):
        replace(baseline, capability_id="bad")
    with pytest.raises(ValueError, match="trading authority"):
        replace(baseline, execution_allowed=True)

    repository = GitHubRepository(
        "example",
        "repo",
        "https://github.com/example/repo",
        "main",
        1,
        datetime(2026, 8, 9, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="identity"):
        replace(repository, owner="")
    with pytest.raises(ValueError, match=r"github\.com HTTPS"):
        replace(repository, url="https://example.com/repo")
    with pytest.raises(ValueError, match="negative"):
        replace(repository, stars=-1)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(repository, pushed_at=datetime(2026, 8, 9))

    document = FetchedDocument("README.md", "evidence")
    with pytest.raises(ValueError, match="path"):
        replace(document, path="")
    with pytest.raises(ValueError, match="empty or unbounded"):
        replace(document, content="")

    candidate = DiscoveryCandidate(
        capability_id="R26-C01",
        query="realistic fill",
        source=source(),
        evidence=(),
        risks=(),
        blockers=("HUMAN_RATINGS_REQUIRED",),
    )
    with pytest.raises(ValueError, match="identity"):
        replace(candidate, query="")
    with pytest.raises(ValueError, match="cannot be empty"):
        replace(candidate, blockers=())
    with pytest.raises(ValueError, match="unbounded"):
        replace(candidate, evidence=tuple([evaluation().evidence[0]] * 101))
    with pytest.raises(ValueError, match="trading authority"):
        replace(candidate, execution_allowed=True)


def test_explicit_research_status_values_remain_non_executable() -> None:
    assert LocalCapabilityStatus.RESEARCH_GAP.value == "RESEARCH_GAP"
    assert RecommendationAction.ADOPT_IDEA.value == "ADOPT_IDEA"
    assert ResearchOntology.__dataclass_fields__["execution_allowed"].default is False


def test_evidence_extractor_classifies_benchmark_license_and_dependency_files() -> None:
    fragments = extract_evidence(
        source(),
        (
            FetchedDocument("benchmarks/result.md", "benchmark"),
            FetchedDocument("LICENSE", "license"),
            FetchedDocument("requirements.txt", "deps"),
        ),
    )

    assert tuple(item.evidence_type for item in fragments) == (
        "BENCHMARK",
        "LICENSE",
        "DEPENDENCY_MANIFEST",
    )
    assert fragments[0].reference.endswith("/benchmarks/result.md")
    assert fragments[2].claim == "Pinned dependency_manifest surface: requirements.txt"


def test_query_planner_rejects_invalid_limits_and_unknown_capabilities() -> None:
    ontology = load_default_ontology()
    baseline = build_local_capability_baseline()

    with pytest.raises(ValueError, match="maximum"):
        plan_queries(ontology, baseline, maximum=0)
    with pytest.raises(ValueError, match="unknown Radar capabilities"):
        plan_queries(ontology, baseline, capability_ids=("R99-C99",))

    planned = plan_queries(ontology, baseline, maximum=3)

    assert len(planned) == 3
    assert planned[0].query.endswith("language:Python archived:false")

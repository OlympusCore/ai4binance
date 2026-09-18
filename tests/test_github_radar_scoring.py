"""Fail-closed GitHub Radar scoring tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from ai4binance.github_radar import scoring
from ai4binance.github_radar.models import (
    DimensionRating,
    EvidenceFragment,
    RecommendationAction,
    RepositoryEvidence,
    RepositorySource,
)
from ai4binance.github_radar.scoring import (
    ScoringPolicy,
    evaluate_repository_evidence,
    load_scoring_policy,
)

DIMENSIONS = (
    "capability_fit",
    "determinism",
    "tests",
    "lookahead_leakage",
    "oos_evidence",
    "data_correctness",
    "maintenance",
    "license",
    "security",
    "performance",
    "modularity",
    "auditability",
)


def repository_evidence(*, license_id: str = "MIT") -> RepositoryEvidence:
    policy = load_scoring_policy()
    return RepositoryEvidence(
        capability_id="R26-C01",
        source=RepositorySource(
            repository="example/research-engine",
            url="https://github.com/example/research-engine",
            pinned_revision="0123456789abcdef0123456789abcdef01234567",
            license_id=license_id,
            language="Python",
        ),
        evidence=(
            EvidenceFragment(
                evidence_type="TEST",
                reference="tests/test_fills.py",
                claim="Pinned test evidence covers realistic fills.",
                content_sha256="a" * 64,
            ),
        ),
        risks=("LOCAL_REPRODUCTION_PENDING",),
        ratings=tuple(
            DimensionRating(item, 0.95, f"Evidence for {item} is pinned.")
            for item in DIMENSIONS
        ),
        passed_gates=policy.hard_gates,
    )


def test_scoring_is_per_capability_and_adopts_only_the_idea() -> None:
    result = evaluate_repository_evidence(repository_evidence())

    assert result.total_score == 95.0
    assert result.recommendation is RecommendationAction.ADOPT_IDEA
    assert result.reuse_mode == "LOCAL_REIMPLEMENTATION_ONLY"
    assert result.blockers == ()
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_missing_hard_gate_rejects_before_score_interpretation() -> None:
    candidate = repository_evidence()
    candidate = replace(candidate, passed_gates=candidate.passed_gates[:-1])

    result = evaluate_repository_evidence(candidate)

    assert result.total_score == 95.0
    assert result.recommendation is RecommendationAction.REJECT
    assert result.blockers == ("HARD_GATE_FAILED:LICENSE_REVIEW_REQUIRED",)


def test_unknown_license_caps_recommendation_at_research() -> None:
    result = evaluate_repository_evidence(repository_evidence(license_id="UNKNOWN"))

    assert result.recommendation is RecommendationAction.RESEARCH
    assert result.reuse_mode == "NONE"
    assert "LICENSE_UNKNOWN_REUSE_BLOCKED" in result.blockers


def test_policy_weights_total_one_hundred() -> None:
    assert sum(load_scoring_policy().weight_map.values()) == 100


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        (0.85, RecommendationAction.POC),
        (0.70, RecommendationAction.RESEARCH),
        (0.55, RecommendationAction.WATCH),
        (0.10, RecommendationAction.REJECT),
    ],
)
def test_score_thresholds_are_explicit(
    rating: float, expected: RecommendationAction
) -> None:
    candidate = repository_evidence()
    candidate = replace(
        candidate,
        ratings=tuple(replace(item, rating=rating) for item in candidate.ratings),
    )

    assert evaluate_repository_evidence(candidate).recommendation is expected


def test_rating_dimensions_must_match_policy_exactly() -> None:
    candidate = repository_evidence()
    candidate = replace(candidate, ratings=candidate.ratings[:-1])

    with pytest.raises(ValueError, match="dimensions mismatch"):
        evaluate_repository_evidence(candidate)


@pytest.mark.parametrize(
    "policy",
    [
        ScoringPolicy(
            weights=(("a", 100),),
            thresholds=(),
            hard_gates=("gate",),
            max_action_without_known_license=RecommendationAction.RESEARCH,
        ),
    ],
)
def test_policy_properties_return_stable_mappings(policy: ScoringPolicy) -> None:
    assert policy.threshold_map == {}
    assert policy.weight_map == {"a": 100}


def test_invalid_policy_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="total 100"):
        ScoringPolicy(
            weights=(("a", 99),),
            thresholds=(),
            hard_gates=("gate",),
            max_action_without_known_license=RecommendationAction.RESEARCH,
        )
    with pytest.raises(ValueError, match="unique"):
        ScoringPolicy(
            weights=(("a", 50), ("a", 50)),
            thresholds=(),
            hard_gates=("gate",),
            max_action_without_known_license=RecommendationAction.RESEARCH,
        )
    with pytest.raises(ValueError, match="positive"):
        ScoringPolicy(
            weights=(("a", 101), ("b", -1)),
            thresholds=(),
            hard_gates=("gate",),
            max_action_without_known_license=RecommendationAction.RESEARCH,
        )
    with pytest.raises(ValueError, match="hard gates"):
        ScoringPolicy(
            weights=(("a", 100),),
            thresholds=(),
            hard_gates=(),
            max_action_without_known_license=RecommendationAction.RESEARCH,
        )


def test_scoring_policy_loader_rejects_unbounded_and_unsafe_yaml(
    tmp_path: Path,
) -> None:
    oversized = tmp_path / "oversized.yaml"
    oversized.write_text("x" * 512_001, encoding="utf-8")
    with pytest.raises(ValueError, match="bounded size"):
        load_scoring_policy(oversized)

    sequence = tmp_path / "sequence.yaml"
    sequence.write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_scoring_policy(sequence)

    payload = yaml.safe_load(Path("config/research/research_scoring.yaml").read_text())
    payload["authority"]["dependency_install_allowed"] = True
    unsafe = tmp_path / "unsafe.yaml"
    unsafe.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot grant"):
        load_scoring_policy(unsafe)

    with pytest.raises(ValueError, match="must be a mapping"):
        scoring._mapping([], "weights")
    with pytest.raises(ValueError, match="must be a sequence"):
        scoring._strings("gate", "hard_gates")

from __future__ import annotations

from datetime import UTC, datetime

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    RadarName,
    TechnologyRecommendation,
    VerificationStatus,
)
from ai4binance.external_intel.radars.github_radar.adapter import (
    finding_from_evaluation,
    technology_candidate_from_evaluation,
)
from ai4binance.github_radar.models import (
    EvidenceFragment,
    RecommendationAction,
    RepositorySource,
    ResearchUnitEvaluation,
    WeightedScore,
)


def _github_evaluation() -> ResearchUnitEvaluation:
    return ResearchUnitEvaluation(
        research_id="GR-0123456789abcdefabcd",
        capability_id="R01-C01",
        source=RepositorySource(
            repository="owner/repo",
            url="https://github.com/owner/repo",
            pinned_revision="a" * 40,
            license_id="MIT",
            language="Python",
        ),
        evidence=(
            EvidenceFragment(
                evidence_type="README",
                reference="README.md",
                claim="Repository documents deterministic backtesting ideas.",
                content_sha256="b" * 64,
            ),
        ),
        risks=("REIMPLEMENTATION_REQUIRED",),
        scores=(
            WeightedScore(
                dimension="relevance",
                rating=0.7,
                weight=10,
                points=7.0,
                rationale="Maps to a research gap.",
            ),
        ),
        total_score=70.0,
        recommendation=RecommendationAction.WATCH,
        blockers=("LICENSE_REVIEW_REQUIRED",),
        reuse_mode="LOCAL_REIMPLEMENTATION_ONLY",
    )


def _github_evaluation_with(
    recommendation: RecommendationAction,
    *,
    blockers: tuple[str, ...] = ("LICENSE_REVIEW_REQUIRED",),
    risks: tuple[str, ...] = ("REIMPLEMENTATION_REQUIRED",),
    license_id: str = "MIT",
) -> ResearchUnitEvaluation:
    base = _github_evaluation()
    return ResearchUnitEvaluation(
        research_id=base.research_id,
        capability_id=base.capability_id,
        source=RepositorySource(
            repository=base.source.repository,
            url=base.source.url,
            pinned_revision=base.source.pinned_revision,
            license_id=license_id,
            language=base.source.language,
        ),
        evidence=base.evidence,
        risks=risks,
        scores=base.scores,
        total_score=base.total_score,
        recommendation=recommendation,
        blockers=blockers,
        reuse_mode=base.reuse_mode,
    )


def test_github_radar_evaluation_maps_to_eief_finding() -> None:
    finding = finding_from_evaluation(
        _github_evaluation(),
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert finding.radar is RadarName.GITHUB_RADAR
    assert finding.decision_impact is DecisionImpact.NEUTRAL
    assert finding.execution_allowed is False
    assert "LIVE_ORDER_BLOCKED" in finding.blockers
    assert finding.evidence_ids == ("README.md#bbbbbbbbbbbb",)


def test_github_radar_evaluation_maps_to_technology_candidate() -> None:
    candidate = technology_candidate_from_evaluation(_github_evaluation())

    assert candidate.recommendation is TechnologyRecommendation.WATCH
    assert candidate.execution_allowed is False
    assert candidate.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "NO_INSTALL_AUTHORITY" in candidate.blockers


def test_github_radar_adapter_maps_all_recommendation_outcomes() -> None:
    cases = (
        (
            RecommendationAction.ADOPT_IDEA,
            DecisionImpact.NEUTRAL,
            TechnologyRecommendation.RESEARCH_CANDIDATE,
        ),
        (
            RecommendationAction.POC,
            DecisionImpact.NEUTRAL,
            TechnologyRecommendation.PROTOTYPE_CANDIDATE,
        ),
        (
            RecommendationAction.REJECT,
            DecisionImpact.RISK,
            TechnologyRecommendation.REJECT,
        ),
        (
            RecommendationAction.RESEARCH,
            DecisionImpact.LOW_CONFIDENCE,
            TechnologyRecommendation.BACKLOG,
        ),
    )

    for action, expected_impact, expected_recommendation in cases:
        evaluation = _github_evaluation_with(
            action,
            blockers=()
            if action in {RecommendationAction.ADOPT_IDEA, RecommendationAction.POC}
            else ("LICENSE_REVIEW_REQUIRED",),
        )
        finding = finding_from_evaluation(
            evaluation,
            observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        )
        candidate = technology_candidate_from_evaluation(evaluation)

        assert finding.decision_impact is expected_impact
        assert candidate.recommendation is expected_recommendation
        assert finding.execution_allowed is False
        assert candidate.execution_allowed is False


def test_github_radar_adapter_marks_unblocked_evidence_partially_verified() -> None:
    evaluation = _github_evaluation_with(
        RecommendationAction.ADOPT_IDEA,
        blockers=(),
        risks=("SECURITY_REVIEW_REQUIRED",),
        license_id="UNKNOWN",
    )

    finding = finding_from_evaluation(
        evaluation,
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    candidate = technology_candidate_from_evaluation(evaluation)

    assert finding.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert candidate.license_risk == 0.5
    assert candidate.security_risk == 0.4

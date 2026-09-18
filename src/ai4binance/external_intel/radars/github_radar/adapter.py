"""Adapter from capability-first GitHub Radar evaluations to EIEF findings."""

from __future__ import annotations

from datetime import datetime

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    RadarName,
    SourceType,
    TechnologyRecommendation,
    VerificationStatus,
)
from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.models import ExternalFinding, TechnologyCandidate
from ai4binance.github_radar.models import RecommendationAction, ResearchUnitEvaluation


def finding_from_evaluation(
    evaluation: ResearchUnitEvaluation,
    *,
    observed_at: datetime,
) -> ExternalFinding:
    impact = _impact_for_recommendation(evaluation.recommendation)
    confidence = min(1.0, evaluation.total_score / 100.0)
    evidence_ids = tuple(
        f"{item.reference}#{item.content_sha256[:12]}" for item in evaluation.evidence
    )
    return ExternalFinding(
        finding_id=eief_id("techfind", evaluation.research_id),
        run_id=eief_id("run", evaluation.research_id, observed_at.isoformat()),
        radar=RadarName.GITHUB_RADAR,
        mission=MissionName.TECHNOLOGY_DEVELOPMENT,
        observed_at=observed_at,
        source_type=SourceType.GITHUB_REPOSITORY,
        event_type="github_research_candidate",
        claim=(
            f"{evaluation.source.repository} maps to "
            f"{evaluation.capability_id} as {evaluation.recommendation.value}"
        ),
        verification_status=(
            VerificationStatus.PARTIALLY_VERIFIED
            if not evaluation.blockers
            else VerificationStatus.UNVERIFIED
        ),
        decision_impact=impact,
        evidence_ids=evidence_ids,
        source_credibility=confidence,
        evidence_score=confidence,
        risk_score=1.0 - confidence,
        confidence=confidence,
        blockers=tuple(
            dict.fromkeys(
                (
                    *evaluation.blockers,
                    "NO_TRADE_SIGNAL_AUTHORITY",
                    "LIVE_ORDER_BLOCKED",
                )
            )
        ),
        audit_trace_id=eief_id("audit", evaluation.research_id),
    )


def technology_candidate_from_evaluation(
    evaluation: ResearchUnitEvaluation,
) -> TechnologyCandidate:
    confidence = min(1.0, evaluation.total_score / 100.0)
    risks = tuple(evaluation.risks)
    return TechnologyCandidate(
        candidate_id=eief_id("techcand", evaluation.research_id),
        technology_area=evaluation.capability_id,
        title=f"{evaluation.source.repository} capability research",
        recommendation=_technology_recommendation(evaluation.recommendation),
        evidence_ids=tuple(
            f"{item.reference}#{item.content_sha256[:12]}"
            for item in evaluation.evidence
        ),
        relevance_to_ai4binance=confidence,
        architecture_fit=confidence,
        implementation_risk=0.2 if not risks else min(1.0, len(risks) / 10),
        license_risk=0.5 if evaluation.source.license_id.upper() == "UNKNOWN" else 0.1,
        security_risk=0.4
        if any("security" in risk.casefold() for risk in risks)
        else 0.1,
        confidence=confidence,
        blockers=tuple(
            dict.fromkeys(
                (*evaluation.blockers, "NO_INSTALL_AUTHORITY", "LIVE_ORDER_BLOCKED")
            )
        ),
    )


def _impact_for_recommendation(action: RecommendationAction) -> DecisionImpact:
    if action in {RecommendationAction.ADOPT_IDEA, RecommendationAction.POC}:
        return DecisionImpact.NEUTRAL
    if action is RecommendationAction.REJECT:
        return DecisionImpact.RISK
    if action is RecommendationAction.WATCH:
        return DecisionImpact.NEUTRAL
    return DecisionImpact.LOW_CONFIDENCE


def _technology_recommendation(
    action: RecommendationAction,
) -> TechnologyRecommendation:
    if action is RecommendationAction.REJECT:
        return TechnologyRecommendation.REJECT
    if action is RecommendationAction.WATCH:
        return TechnologyRecommendation.WATCH
    if action is RecommendationAction.POC:
        return TechnologyRecommendation.PROTOTYPE_CANDIDATE
    if action is RecommendationAction.ADOPT_IDEA:
        return TechnologyRecommendation.RESEARCH_CANDIDATE
    return TechnologyRecommendation.BACKLOG

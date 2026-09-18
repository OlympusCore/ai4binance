from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    RadarName,
    SourceType,
    VerificationStatus,
)
from ai4binance.external_intel.core.models import ExternalFinding
from ai4binance.external_intel.scoring.fusion_score import (
    fused_confidence,
    fused_decision_impact,
)
from ai4binance.external_intel.scoring.manipulation_score import (
    ManipulationSignals,
    score_manipulation,
)
from ai4binance.external_intel.scoring.source_credibility import (
    SourceCredibilityInput,
    score_source_credibility,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def test_source_credibility_penalizes_promotion_and_manipulation() -> None:
    clean = score_source_credibility(
        SourceCredibilityInput(
            identity_verification_score=1.0,
            domain_expertise_score=1.0,
            historical_accuracy_score=1.0,
            originality_score=1.0,
            evidence_quality_score=1.0,
            independent_confirmation_score=1.0,
        )
    )
    promoted = score_source_credibility(
        SourceCredibilityInput(
            identity_verification_score=1.0,
            domain_expertise_score=1.0,
            historical_accuracy_score=1.0,
            originality_score=1.0,
            evidence_quality_score=1.0,
            independent_confirmation_score=1.0,
            promotion_penalty=0.5,
            manipulation_association_penalty=0.5,
        )
    )

    assert clean == 1.0
    assert promoted == 0.5


def test_manipulation_score_uses_copy_and_spam_signals() -> None:
    score = score_manipulation(
        ManipulationSignals(
            copy_ratio=1.0,
            low_source_quality_ratio=1.0,
            urgency_language_ratio=1.0,
            referral_or_pump_ratio=1.0,
            synchronized_activity_ratio=1.0,
        )
    )

    assert score == 1.0


def test_fusion_score_handles_empty_and_bounded_confidence() -> None:
    assert fused_confidence(()) == 0.0
    assert (
        fused_confidence(
            (
                _finding(RadarName.NEWS_RADAR, DecisionImpact.CONFIRM, 0.95, 0.0),
                _finding(RadarName.GITHUB_RADAR, DecisionImpact.CONFIRM, 0.95, 0.0),
                _finding(RadarName.X_RADAR, DecisionImpact.CONFIRM, 0.95, 0.0),
                _finding(
                    RadarName.REDDIT_RADAR,
                    DecisionImpact.CONFIRM,
                    0.95,
                    0.0,
                ),
                _finding(
                    RadarName.TELEGRAM_RADAR,
                    DecisionImpact.CONFIRM,
                    0.95,
                    0.0,
                ),
                _finding(
                    RadarName.SECURITY_RADAR,
                    DecisionImpact.CONFIRM,
                    0.95,
                    0.0,
                ),
            )
        )
        == 1.0
    )
    assert (
        fused_confidence(
            (_finding(RadarName.NEWS_RADAR, DecisionImpact.RISK, 0.1, 1.0),)
        )
        == 0.0
    )


@pytest.mark.parametrize(
    ("impacts", "expected"),
    [
        ((DecisionImpact.CRITICAL_RISK,), DecisionImpact.CRITICAL_RISK),
        ((DecisionImpact.RISK,), DecisionImpact.RISK),
        ((DecisionImpact.CONFLICT,), DecisionImpact.CONFLICT),
        ((DecisionImpact.DATA_UNAVAILABLE,), DecisionImpact.DATA_UNAVAILABLE),
        ((DecisionImpact.CONFIRM,), DecisionImpact.CONFIRM),
        ((DecisionImpact.WEAK_CONFIRM,), DecisionImpact.WEAK_CONFIRM),
        ((DecisionImpact.NEUTRAL,), DecisionImpact.NEUTRAL),
    ],
)
def test_fused_decision_impact_priority_order(
    impacts: tuple[DecisionImpact, ...],
    expected: DecisionImpact,
) -> None:
    findings = tuple(
        _finding(RadarName.NEWS_RADAR, impact, 0.8, 0.0) for impact in impacts
    )

    assert fused_decision_impact(findings) is expected


def test_fused_decision_impact_demotes_social_only_confirmation() -> None:
    assert fused_decision_impact(()) is DecisionImpact.DATA_UNAVAILABLE
    assert (
        fused_decision_impact(
            (
                _finding(RadarName.X_RADAR, DecisionImpact.CONFIRM, 0.7, 0.0),
                _finding(
                    RadarName.REDDIT_RADAR,
                    DecisionImpact.WEAK_CONFIRM,
                    0.7,
                    0.0,
                ),
            )
        )
        is DecisionImpact.LOW_CONFIDENCE
    )


def _finding(
    radar: RadarName,
    impact: DecisionImpact,
    confidence: float,
    manipulation_risk: float,
) -> ExternalFinding:
    return ExternalFinding(
        finding_id=f"{radar.value}:{impact.value}:{confidence}:{manipulation_risk}",
        run_id="run:test",
        radar=radar,
        mission=MissionName.MARKET_NARRATIVE,
        observed_at=NOW,
        source_type=SourceType.NEWS_ARTICLE,
        event_type="LOCAL_TEST_FINDING",
        claim="Local deterministic test finding.",
        verification_status=VerificationStatus.VERIFIED,
        evidence_ids=("test:evidence",),
        symbol="HOTUSDT",
        confidence=confidence,
        decision_impact=impact,
        manipulation_risk=manipulation_risk,
    )

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
from ai4binance.external_intel.core.models import (
    ExternalDecisionImpact,
    ExternalEvidence,
    ExternalFinding,
)
from ai4binance.external_intel.core.validation import hash_material


def test_external_finding_preserves_fail_closed_authority() -> None:
    finding = ExternalFinding(
        finding_id="extfind_test",
        run_id="run_test",
        radar=RadarName.NEWS_RADAR,
        mission=MissionName.BINANCE_OPPORTUNITY_NEWS,
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        source_type=SourceType.NEWS_ARTICLE,
        event_type="provider_unavailable",
        claim="news provider is unavailable",
        verification_status=VerificationStatus.DATA_UNAVAILABLE,
        decision_impact=DecisionImpact.DATA_UNAVAILABLE,
        evidence_ids=(),
        blockers=("DATA_UNAVAILABLE", "LIVE_ORDER_BLOCKED"),
    )

    assert finding.execution_allowed is False
    assert finding.promotion_status == "RESEARCH_ONLY"
    assert finding.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_external_finding_rejects_execution_terms() -> None:
    with pytest.raises(ValueError, match="forbidden execution terms"):
        ExternalFinding(
            finding_id="extfind_bad",
            run_id="run_bad",
            radar=RadarName.NEWS_RADAR,
            mission=MissionName.BINANCE_OPPORTUNITY_NEWS,
            observed_at=datetime(2026, 8, 9, tzinfo=UTC),
            source_type=SourceType.NEWS_ARTICLE,
            event_type="provider_unavailable",
            claim="BUY this token now",
            verification_status=VerificationStatus.UNVERIFIED,
            decision_impact=DecisionImpact.LOW_CONFIDENCE,
            evidence_ids=(),
        )


def test_data_unavailable_finding_requires_visible_blocker() -> None:
    with pytest.raises(ValueError, match="data-unavailable"):
        ExternalFinding(
            finding_id="extfind_missing_blocker",
            run_id="run_bad",
            radar=RadarName.X_RADAR,
            mission=MissionName.BINANCE_OPPORTUNITY_NEWS,
            observed_at=datetime(2026, 8, 9, tzinfo=UTC),
            source_type=SourceType.X_POST,
            event_type="provider_unavailable",
            claim="x provider is unavailable",
            verification_status=VerificationStatus.DATA_UNAVAILABLE,
            decision_impact=DecisionImpact.DATA_UNAVAILABLE,
            evidence_ids=(),
        )


def test_external_evidence_redacts_authority_and_hashes() -> None:
    evidence = ExternalEvidence(
        evidence_id="ev_1",
        source_type=SourceType.NEWS_ARTICLE,
        source_uri="https://example.test/news/1",
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        content_sha256=hash_material("news"),
        citation="example.test/news/1",
        author_or_origin="Example",
        reliability=0.7,
    )

    assert evidence.execution_allowed is False
    assert len(evidence.content_sha256) == 64


def test_decision_impact_requires_live_blocker() -> None:
    with pytest.raises(ValueError, match="live blocker"):
        ExternalDecisionImpact(
            symbol="HOTUSDT",
            generated_at=datetime(2026, 8, 9, tzinfo=UTC),
            external_bias=DecisionImpact.NEUTRAL,
            decision_impact=DecisionImpact.NEUTRAL,
            confidence=0.5,
            blockers=("MANUAL_REVIEW_REQUIRED",),
        )

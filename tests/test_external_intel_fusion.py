from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    RadarName,
    SourceType,
    VerificationStatus,
)
from ai4binance.external_intel.core.models import ExternalFinding
from ai4binance.external_intel.fusion.engine import FusionEngine
from ai4binance.external_intel.integration.decision_governance_adapter import (
    to_compact_decision_payload,
)


def _finding(
    radar: RadarName,
    impact: DecisionImpact,
    *,
    mission: MissionName = MissionName.BINANCE_OPPORTUNITY_NEWS,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    symbol: str | None = None,
    evidence_ids: tuple[str, ...] = ("ev1",),
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",),
    observed_at: datetime | None = None,
    run_id: str = "run_fusion",
    finding_id: str | None = None,
    confidence: float = 0.5,
) -> ExternalFinding:
    return ExternalFinding(
        finding_id=finding_id or f"finding_{radar.value}",
        run_id=run_id,
        radar=radar,
        mission=mission,
        observed_at=observed_at or datetime(2026, 8, 9, tzinfo=UTC),
        source_type=SourceType.NEWS_ARTICLE,
        event_type="external_context",
        claim="external context requires review",
        verification_status=verification_status,
        decision_impact=impact,
        evidence_ids=evidence_ids,
        symbol=symbol,
        confidence=confidence,
        risk_score=0.7 if impact is DecisionImpact.RISK else 0.0,
        blockers=blockers,
    )


def test_fusion_prioritizes_risk_and_keeps_live_blocker() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(RadarName.NEWS_RADAR, DecisionImpact.WEAK_CONFIRM),
            _finding(
                RadarName.SECURITY_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.SECURITY_RISK,
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.decision_impact is DecisionImpact.RISK
    assert "EXTERNAL_RISK_REVIEW_REQUIRED" in impact.blockers
    assert "LIVE_ORDER_BLOCKED" in impact.blockers


def test_decision_adapter_outputs_compact_advisory_payload() -> None:
    impact = FusionEngine().fuse(
        (),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    payload = to_compact_decision_payload(impact)

    assert payload["decision_impact"] == "DATA_UNAVAILABLE"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_fusion_excludes_technology_confirmation_from_market_impact() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(RadarName.NEWS_RADAR, DecisionImpact.NEUTRAL),
            _finding(
                RadarName.OPEN_WEB_RADAR,
                DecisionImpact.WEAK_CONFIRM,
                mission=MissionName.TECHNOLOGY_DEVELOPMENT,
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.NEUTRAL
    assert impact.decision_impact is DecisionImpact.NEUTRAL
    assert "NON_MARKET_ADVISORY_FINDINGS_ISOLATED" in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_excludes_github_radar_even_with_market_mission() -> None:
    impact = FusionEngine().fuse(
        (_finding(RadarName.GITHUB_RADAR, DecisionImpact.WEAK_CONFIRM),),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.DATA_UNAVAILABLE
    assert impact.decision_impact is DecisionImpact.DATA_UNAVAILABLE
    assert "NON_MARKET_ADVISORY_FINDINGS_ISOLATED" in impact.blockers


def test_fusion_keeps_operational_risk_visible_without_market_bias() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.GITHUB_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.TECHNOLOGY_DEVELOPMENT,
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.DATA_UNAVAILABLE
    assert impact.decision_impact is DecisionImpact.DATA_UNAVAILABLE
    assert impact.confidence == 0.0
    assert impact.news_risk == 0.0
    assert impact.security_risk == 0.0
    assert impact.regulatory_risk == 0.0
    assert "MARKET_ADVISORY_DATA_UNAVAILABLE" in impact.blockers
    assert "OPERATIONAL_RESEARCH_RISK_PRESENT" in impact.blockers
    assert "EXTERNAL_RISK_REVIEW_REQUIRED" not in impact.blockers


def test_fusion_excludes_non_verified_positive_market_influence() -> None:
    for verification_status in (
        VerificationStatus.PARTIALLY_VERIFIED,
        VerificationStatus.UNVERIFIED,
        VerificationStatus.STALE,
        VerificationStatus.FALSE,
        VerificationStatus.MISLEADING,
    ):
        impact = FusionEngine().fuse(
            (
                _finding(
                    RadarName.NEWS_RADAR,
                    DecisionImpact.CONFIRM,
                    verification_status=verification_status,
                ),
            ),
            generated_at=datetime(2026, 8, 9, tzinfo=UTC),
            symbol="HOTUSDT",
        )

        assert impact.external_bias is DecisionImpact.LOW_CONFIDENCE
        assert impact.decision_impact is DecisionImpact.LOW_CONFIDENCE
        assert impact.confidence == 0.0
        assert "MARKET_EVIDENCE_NOT_VERIFIED" in impact.blockers
        assert "NON_VERIFIED_MARKET_INFLUENCE_EXCLUDED" in impact.blockers
        assert "MANUAL_REVIEW_REQUIRED" in impact.blockers
        assert impact.execution_allowed is False
        assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_retains_non_verified_market_risk_without_confidence_boost() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.SECURITY_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.SECURITY_RISK,
                verification_status=VerificationStatus.UNVERIFIED,
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.RISK
    assert impact.decision_impact is DecisionImpact.RISK
    assert impact.confidence == 0.0
    assert "MARKET_EVIDENCE_NOT_VERIFIED" in impact.blockers
    assert "NON_VERIFIED_MARKET_INFLUENCE_EXCLUDED" not in impact.blockers
    assert "EXTERNAL_RISK_REVIEW_REQUIRED" in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_isolates_explicit_cross_symbol_findings() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.NEWS_RADAR,
                DecisionImpact.WEAK_CONFIRM,
                symbol="HOTUSDT",
                evidence_ids=("ev_hot",),
            ),
            _finding(
                RadarName.REGULATORY_RADAR,
                DecisionImpact.NEUTRAL,
                mission=MissionName.REGULATORY_RISK,
                evidence_ids=("ev_market_wide",),
            ),
            _finding(
                RadarName.SECURITY_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.SECURITY_RISK,
                symbol="BTCUSDT",
                evidence_ids=("ev_btc",),
                blockers=("LIVE_ORDER_BLOCKED", "BTC_ONLY_BLOCKER"),
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.WEAK_CONFIRM
    assert impact.decision_impact is DecisionImpact.WEAK_CONFIRM
    assert impact.security_risk == 0.0
    assert impact.evidence_ids == ("ev_hot", "ev_market_wide")
    assert "CROSS_SYMBOL_FINDINGS_ISOLATED" in impact.blockers
    assert "BTC_ONLY_BLOCKER" not in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_excludes_future_dated_market_findings() -> None:
    generated_at = datetime(2026, 8, 9, tzinfo=UTC)
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.NEWS_RADAR,
                DecisionImpact.WEAK_CONFIRM,
                symbol="HOTUSDT",
                evidence_ids=("ev_current",),
            ),
            _finding(
                RadarName.SECURITY_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.SECURITY_RISK,
                symbol="HOTUSDT",
                evidence_ids=("ev_future",),
                blockers=("LIVE_ORDER_BLOCKED", "FUTURE_SOURCE_BLOCKER"),
                observed_at=generated_at + timedelta(microseconds=1),
            ),
        ),
        generated_at=generated_at,
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.LOW_CONFIDENCE
    assert impact.decision_impact is DecisionImpact.LOW_CONFIDENCE
    assert impact.security_risk == 0.0
    assert impact.evidence_ids == ("ev_current",)
    assert "FUTURE_DATED_FINDINGS_EXCLUDED" in impact.blockers
    assert "MARKET_TEMPORAL_INTEGRITY_FAILED" in impact.blockers
    assert "MANUAL_REVIEW_REQUIRED" in impact.blockers
    assert "FUTURE_SOURCE_BLOCKER" not in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_returns_data_unavailable_when_only_market_finding_is_future() -> None:
    generated_at = datetime(2026, 8, 9, tzinfo=UTC)
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.NEWS_RADAR,
                DecisionImpact.CONFIRM,
                symbol="HOTUSDT",
                evidence_ids=("ev_future",),
                observed_at=generated_at + timedelta(seconds=1),
            ),
        ),
        generated_at=generated_at,
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.DATA_UNAVAILABLE
    assert impact.decision_impact is DecisionImpact.DATA_UNAVAILABLE
    assert impact.confidence == 0.0
    assert impact.evidence_ids == ()
    assert "MARKET_ADVISORY_DATA_UNAVAILABLE" in impact.blockers
    assert "FUTURE_DATED_FINDINGS_EXCLUDED" in impact.blockers
    assert "MARKET_TEMPORAL_INTEGRITY_FAILED" in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_rejects_mixed_run_findings() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.NEWS_RADAR,
                DecisionImpact.CONFIRM,
                symbol="HOTUSDT",
                evidence_ids=("ev_run_a",),
                run_id="run_a",
            ),
            _finding(
                RadarName.SECURITY_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.SECURITY_RISK,
                symbol="HOTUSDT",
                evidence_ids=("ev_run_b",),
                blockers=("LIVE_ORDER_BLOCKED", "RUN_B_BLOCKER"),
                run_id="run_b",
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.DATA_UNAVAILABLE
    assert impact.decision_impact is DecisionImpact.DATA_UNAVAILABLE
    assert impact.confidence == 0.0
    assert impact.security_risk == 0.0
    assert impact.evidence_ids == ()
    assert "MIXED_RUN_FINDINGS_REJECTED" in impact.blockers
    assert "CYCLE_INTEGRITY_FAILED" in impact.blockers
    assert "MANUAL_REVIEW_REQUIRED" in impact.blockers
    assert "MARKET_ADVISORY_DATA_UNAVAILABLE" in impact.blockers
    assert "RUN_B_BLOCKER" not in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_collapses_identical_finding_replay() -> None:
    primary = _finding(
        RadarName.NEWS_RADAR,
        DecisionImpact.CONFIRM,
        symbol="HOTUSDT",
        evidence_ids=("ev_primary",),
        confidence=0.9,
    )
    secondary = _finding(
        RadarName.REGULATORY_RADAR,
        DecisionImpact.NEUTRAL,
        mission=MissionName.REGULATORY_RISK,
        symbol="HOTUSDT",
        evidence_ids=("ev_secondary",),
        confidence=0.1,
    )
    generated_at = datetime(2026, 8, 9, tzinfo=UTC)

    baseline = FusionEngine().fuse(
        (primary, secondary), generated_at=generated_at, symbol="HOTUSDT"
    )
    replayed = FusionEngine().fuse(
        (primary, primary, secondary), generated_at=generated_at, symbol="HOTUSDT"
    )

    assert replayed.external_bias is baseline.external_bias
    assert replayed.decision_impact is baseline.decision_impact
    assert replayed.confidence == baseline.confidence
    assert replayed.evidence_ids == baseline.evidence_ids
    assert "DUPLICATE_FINDING_REPLAY_COLLAPSED" in replayed.blockers
    assert replayed.execution_allowed is False
    assert replayed.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_fusion_rejects_conflicting_finding_identity() -> None:
    impact = FusionEngine().fuse(
        (
            _finding(
                RadarName.NEWS_RADAR,
                DecisionImpact.CONFIRM,
                symbol="HOTUSDT",
                evidence_ids=("ev_confirm",),
                finding_id="finding_conflict",
            ),
            _finding(
                RadarName.SECURITY_RADAR,
                DecisionImpact.RISK,
                mission=MissionName.SECURITY_RISK,
                symbol="HOTUSDT",
                evidence_ids=("ev_risk",),
                blockers=("LIVE_ORDER_BLOCKED", "CONFLICTING_SOURCE_BLOCKER"),
                finding_id="finding_conflict",
            ),
        ),
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        symbol="HOTUSDT",
    )

    assert impact.external_bias is DecisionImpact.DATA_UNAVAILABLE
    assert impact.decision_impact is DecisionImpact.DATA_UNAVAILABLE
    assert impact.confidence == 0.0
    assert impact.security_risk == 0.0
    assert impact.evidence_ids == ()
    assert "FINDING_IDENTITY_CONFLICT" in impact.blockers
    assert "EVIDENCE_INTEGRITY_FAILED" in impact.blockers
    assert "MANUAL_REVIEW_REQUIRED" in impact.blockers
    assert "MARKET_ADVISORY_DATA_UNAVAILABLE" in impact.blockers
    assert "CONFLICTING_SOURCE_BLOCKER" not in impact.blockers
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"

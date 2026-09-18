from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    OpportunityStatus,
    RadarName,
    RadarStatus,
    SourceType,
    TechnologyRecommendation,
    VerificationStatus,
)
from ai4binance.external_intel.core.models import (
    EvidenceGraphEdge,
    EvidenceGraphNode,
    ExternalClaim,
    ExternalDecisionImpact,
    ExternalEvidence,
    ExternalFinding,
    OpportunityCandidate,
    RadarRunManifest,
    TechnologyCandidate,
    UniverseSnapshot,
)
from ai4binance.external_intel.core.validation import (
    hash_material,
    require_aware,
    require_optional_text,
    require_sha256,
    require_text,
    require_unique_text,
    require_unit_interval,
)
from ai4binance.external_intel.evidence.evidence_graph import EvidenceGraph
from ai4binance.external_intel.evidence.original_source import (
    assess_original_sources,
)
from ai4binance.external_intel.evidence.verification import verify_claim
from ai4binance.external_intel.scoring.fusion_score import (
    fused_confidence,
    fused_decision_impact,
)
from ai4binance.external_intel.scoring.manipulation_score import ManipulationSignals
from ai4binance.external_intel.scoring.source_credibility import SourceCredibilityInput
from ai4binance.external_intel.universe.classifier import classify_asset

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _finding(
    impact: DecisionImpact,
    *,
    radar: RadarName = RadarName.NEWS_RADAR,
    confidence: float = 0.5,
    manipulation: float = 0.0,
) -> ExternalFinding:
    return ExternalFinding(
        finding_id=f"finding-{radar.value}-{impact.value}",
        run_id="run-1",
        radar=radar,
        mission=MissionName.MARKET_NARRATIVE,
        observed_at=NOW,
        source_type=SourceType.NEWS_ARTICLE,
        event_type="external_observation",
        claim="Evidence describes a market narrative without execution authority.",
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        decision_impact=impact,
        evidence_ids=("evidence-1",),
        confidence=confidence,
        manipulation_risk=manipulation,
        blockers=("LIVE_ORDER_BLOCKED",),
    )


def test_validation_helpers_reject_invalid_contract_values() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        require_text("field", "")
    with pytest.raises(ValueError, match="bounded"):
        require_optional_text("field", "x" * 2_001)
    with pytest.raises(ValueError, match="unique"):
        require_unique_text("values", ("a", "a"))
    with pytest.raises(ValueError, match="timezone-aware"):
        require_aware("observed_at", datetime(2026, 8, 9))
    with pytest.raises(ValueError, match="zero and one"):
        require_unit_interval("score", 1.1)
    with pytest.raises(ValueError, match="SHA-256"):
        require_sha256("digest", "not-a-digest")
    assert hash_material("a", "b") == hash_material("a", "b")


def test_radar_manifest_keeps_report_only_authority() -> None:
    manifest = RadarRunManifest(
        run_id="run-1",
        radar=RadarName.SECURITY_RADAR,
        mission=MissionName.SECURITY_RISK,
        started_at=NOW,
        status=RadarStatus.DATA_UNAVAILABLE,
        blockers=("DATA_UNAVAILABLE",),
    )

    assert manifest.execution_allowed is False
    with pytest.raises(ValueError, match="cannot be negative"):
        RadarRunManifest(
            run_id="run-2",
            radar=RadarName.NEWS_RADAR,
            mission=MissionName.MARKET_NARRATIVE,
            started_at=NOW,
            status=RadarStatus.READY,
            source_count=-1,
        )


def test_evidence_and_claim_reject_execution_terms_and_bad_hashes() -> None:
    with pytest.raises(ValueError, match="forbidden execution terms"):
        ExternalEvidence(
            evidence_id="ev-1",
            source_type=SourceType.NEWS_ARTICLE,
            source_uri="https://example.test/post",
            observed_at=NOW,
            content_sha256="a" * 64,
            citation="contains BUY as a forbidden execution verb",
        )
    with pytest.raises(ValueError, match="cannot be empty"):
        ExternalClaim(
            claim_id="claim-1",
            text="neutral claim",
            radar=RadarName.NEWS_RADAR,
            mission=MissionName.EVIDENCE_VERIFICATION,
            source_evidence_ids=(),
            observed_at=NOW,
        )


def test_data_unavailable_finding_requires_visible_blocker() -> None:
    with pytest.raises(ValueError, match="data-unavailable"):
        ExternalFinding(
            finding_id="finding-1",
            run_id="run-1",
            radar=RadarName.X_RADAR,
            mission=MissionName.MARKET_NARRATIVE,
            observed_at=NOW,
            source_type=SourceType.X_POST,
            event_type="provider_unavailable",
            claim="Provider unavailable.",
            verification_status=VerificationStatus.DATA_UNAVAILABLE,
            decision_impact=DecisionImpact.DATA_UNAVAILABLE,
            evidence_ids=(),
        )


def test_evidence_graph_rejects_unknown_edges_and_authority() -> None:
    graph = EvidenceGraph().add_node(
        EvidenceGraphNode(
            node_id="source-1",
            node_type="source",
            label="source",
            evidence_ids=("evidence-1",),
        )
    )

    assert graph.nodes[0].node_id == "source-1"
    with pytest.raises(ValueError, match="unknown node"):
        graph.add_edge(
            EvidenceGraphEdge(
                edge_id="edge-1",
                source_node_id="source-1",
                target_node_id="missing",
                relationship="supports",
            )
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        EvidenceGraph(execution_allowed=True)


def test_snapshot_and_candidate_contracts_remain_advisory() -> None:
    asset = classify_asset("HOT", spot_symbols=("HOTUSDT",))
    snapshot = UniverseSnapshot(
        snapshot_id="snapshot-1", observed_at=NOW, assets=(asset,)
    )

    assert snapshot.execution_allowed is False
    with pytest.raises(ValueError, match="requires at least one asset"):
        UniverseSnapshot(snapshot_id="snapshot-2", observed_at=NOW, assets=())
    with pytest.raises(ValueError, match="cannot grant trading authority"):
        OpportunityCandidate(
            candidate_id="opp-1",
            asset="HOT",
            symbol="HOTUSDT",
            status=OpportunityStatus.OPPORTUNITY_CANDIDATE,
            evidence_ids=("ev-1",),
            opportunity_score=0.4,
            risk_score=0.4,
            confidence=0.4,
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        TechnologyCandidate(
            candidate_id="tech-1",
            technology_area="R01-C01",
            title="Research idea",
            recommendation=TechnologyRecommendation.WATCH,
            evidence_ids=("ev-1",),
            relevance_to_ai4binance=0.5,
            architecture_fit=0.5,
            implementation_risk=0.5,
            license_risk=0.5,
            security_risk=0.5,
            confidence=0.5,
            installation_allowed=True,
        )


def test_external_decision_impact_requires_live_blocker() -> None:
    with pytest.raises(ValueError, match="live blocker"):
        ExternalDecisionImpact(
            symbol="HOTUSDT",
            generated_at=NOW,
            external_bias=DecisionImpact.NEUTRAL,
            decision_impact=DecisionImpact.NEUTRAL,
            confidence=0.1,
            blockers=("MANUAL_REVIEW_REQUIRED",),
        )


def test_common_fusion_paths_are_deterministic() -> None:
    assert fused_decision_impact(()) is DecisionImpact.DATA_UNAVAILABLE
    assert (
        fused_decision_impact((_finding(DecisionImpact.CRITICAL_RISK),))
        is DecisionImpact.CRITICAL_RISK
    )
    assert (
        fused_decision_impact((_finding(DecisionImpact.CONFLICT),))
        is DecisionImpact.CONFLICT
    )
    assert (
        fused_decision_impact(
            (
                _finding(DecisionImpact.CONFIRM, radar=RadarName.X_RADAR),
                _finding(DecisionImpact.WEAK_CONFIRM, radar=RadarName.REDDIT_RADAR),
            )
        )
        is DecisionImpact.LOW_CONFIDENCE
    )
    assert 0.0 <= fused_confidence((_finding(DecisionImpact.NEUTRAL),)) <= 1.0
    assert fused_confidence((_finding(DecisionImpact.NEUTRAL, manipulation=1.0),)) < 0.5


def test_evidence_helpers_cover_empty_and_positive_paths() -> None:
    first = ExternalEvidence(
        evidence_id="ev-1",
        source_type=SourceType.NEWS_ARTICLE,
        source_uri="https://example.test/a",
        observed_at=NOW,
        content_sha256="a" * 64,
        citation="primary source",
        author_or_origin="source-a",
        reliability=0.9,
    )
    second = ExternalEvidence(
        evidence_id="ev-2",
        source_type=SourceType.REDDIT_POST,
        source_uri="https://example.test/b",
        observed_at=NOW,
        content_sha256="b" * 64,
        citation="secondary discussion",
        author_or_origin="source-b",
        reliability=0.6,
    )
    claim = ExternalClaim(
        claim_id="claim-verified",
        text="Two independent sources mention the same external observation.",
        radar=RadarName.NEWS_RADAR,
        mission=MissionName.EVIDENCE_VERIFICATION,
        source_evidence_ids=("ev-1", "ev-2"),
        observed_at=NOW,
    )

    assert assess_original_sources((first, second)).independent_source_count == 2
    with pytest.raises(ValueError, match="requires evidence"):
        assess_original_sources(())
    assert verify_claim(claim, ()) is VerificationStatus.DATA_UNAVAILABLE
    assert verify_claim(claim, (first, second)) is VerificationStatus.VERIFIED
    assert verify_claim(claim, (first,)) is VerificationStatus.UNVERIFIED


def test_scoring_inputs_reject_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="zero and one"):
        SourceCredibilityInput(identity_verification_score=-0.1)
    with pytest.raises(ValueError, match="zero and one"):
        ManipulationSignals(copy_ratio=2.0)

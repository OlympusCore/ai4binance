from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.governance.controls import (
    ControlEligibility,
    ControlEvaluation,
    ControlResolutionAuthority,
    ControlSeverity,
    ControlSource,
    HardBlocker,
)
from ai4binance.opportunity_policy import classify_opportunity_grade
from ai4binance.opportunity_report import (
    OpportunityCandidateView,
    OpportunityGap,
    OpportunityNextAction,
    OpportunityReportHeader,
    OpportunityReportV2,
    OpportunitySection,
    OpportunitySnapshotDiff,
    _decimal_score,
    _pattern_type_value,
    build_report_v2_payload,
)
from ai4binance.opportunity_report import (
    _next_safe_action as _report_next_safe_action,
)
from ai4binance.opportunity_report import (
    _text_tuple as _report_text_tuple,
)
from ai4binance.opportunity_scanner import (
    CandidateRankingPolicy,
    OpportunityDisposition,
    OpportunityFunnelMetrics,
    OpportunityFunnelStage,
    OpportunityScanCandidate,
    OpportunityScanReport,
    OpportunityVisibilityState,
    _apply_candidate_ranking,
    _blocker_resolution_authority,
    _blocker_source,
    _bounded_score,
    _disposition,
    _funnel_stage,
    _lifecycle_state,
    _next_safe_action,
    _opportunity_score,
    _soft_penalties,
    _visibility_state,
    _why_visible,
    build_opportunity_scan_report,
)
from ai4binance.scanners.orchestrator import ScannerOrchestrator
from ai4binance.universe import UniverseFilterResult, UniverseMarket, UniverseSymbol


def test_opportunity_scanner_ranks_candidates_and_filters_token_risk() -> None:
    report = build_opportunity_scan_report(
        "scan-all",
        spot_symbols=(
            _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000"),
            _spot("USDCUSDT", "USDC", volume="9000000", spread="2", depth="200000"),
            _spot("ETHUPUSDT", "ETHUP", volume="9000000", spread="5", depth="80000"),
        ),
        futures_symbols=(
            _future(
                "BTCUSDT",
                "BTC",
                volume="7000000",
                spread="4",
                depth="250000",
                open_interest="20000000",
                funding="0.0001",
            ),
        ),
    )
    payload = report.to_payload()
    ranked = cast(Sequence[Mapping[str, object]], payload["ranked_candidates"])

    assert report.status == "RUNNING_WITH_BLOCKERS"
    assert report.accepted_symbols[:2] == ("BTCUSDT", "SOLUSDT")
    assert "USDCUSDT" in report.rejected_symbols
    assert "ETHUPUSDT" in report.rejected_symbols
    assert "STABLECOIN_BASE_EXCLUDED" in report.blockers
    assert "LEVERAGED_TOKEN_EXCLUDED" in report.blockers
    assert "LIVE_ORDER_BLOCKED" in report.blockers
    assert report.candidates[0].symbol == "BTCUSDT"
    assert report.candidates[0].execution_allowed is False
    assert report.candidates[0].hard_blockers == ()
    assert ranked[0]["hard_blockers"] == ()
    assert "control_evaluation" in ranked[0]
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_opportunity_scanner_fails_closed_without_input() -> None:
    report = build_opportunity_scan_report("scan-spot")

    assert report.accepted_symbols == ()
    assert report.rejected_symbols == ()
    assert report.blockers == ("SCANNER_INPUT_UNAVAILABLE", "LIVE_ORDER_BLOCKED")
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_scanner_separates_hard_blockers_from_soft_penalties() -> None:
    report = build_opportunity_scan_report(
        "scan-spot",
        spot_symbols=(
            _spot("USDCUSDT", "USDC", volume="9000000", spread="2", depth="200000"),
            _spot("SLOWUSDT", "SLOW", volume="2000000", spread="12", depth="50000"),
        ),
    )
    stable = next(item for item in report.candidates if item.symbol == "USDCUSDT")
    slow = next(item for item in report.candidates if item.symbol == "SLOWUSDT")

    assert stable.accepted is False
    assert stable.hard_blockers == ("STABLECOIN_BASE_EXCLUDED",)
    assert stable.control_evaluation.hard_gate_passed is False
    assert stable.control_evaluation.adjusted_score == stable.adjusted_score
    assert stable.execution_allowed is False
    assert slow.accepted is True
    assert slow.hard_blockers == ()
    assert slow.soft_penalties == ("MINOR_SPREAD_DEGRADATION",)
    assert slow.adjusted_score < slow.base_score


def test_hard_blocker_is_not_modeled_as_numeric_score_penalty() -> None:
    report = build_opportunity_scan_report(
        "scan-spot",
        spot_symbols=(
            _spot("USDCUSDT", "USDC", volume="9000000", spread="2", depth="200000"),
        ),
    )
    candidate = report.candidates[0]

    assert candidate.accepted is False
    assert candidate.hard_blockers == ("STABLECOIN_BASE_EXCLUDED",)
    assert candidate.base_score == candidate.adjusted_score
    assert candidate.control_evaluation.total_penalty == Decimal("0")


def test_execution_blocker_does_not_hide_research_candidate() -> None:
    symbol = _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000")
    report = build_opportunity_scan_report(
        "scan-spot",
        orchestrator=cast(
            ScannerOrchestrator,
            _StaticOrchestrator(
                (UniverseFilterResult(symbol, False, ("OOS_NOT_COMPLETE",)),)
            ),
        ),
    )
    candidate = report.candidates[0]

    assert report.accepted_symbols == ("SOLUSDT",)
    assert report.rejected_symbols == ()
    assert report.status == "READY"
    assert candidate.discovery_exclusions == ()
    assert candidate.funnel_stage == OpportunityFunnelStage.QUALIFIED.value
    assert candidate.disposition == OpportunityDisposition.WAIT_FOR_RETEST.value
    assert candidate.validation_gaps == (
        "OOS_NOT_COMPLETE",
        "PAPER_VALIDATION_PENDING",
    )
    assert "OOS_NOT_COMPLETE" in candidate.execution_blockers
    assert "LIVE_ORDER_BLOCKED" in candidate.execution_blockers
    assert candidate.visibility_state == "CONFIRMATION_PENDING"
    assert candidate.execution_eligible is False
    assert candidate.paper_eligible is False
    assert candidate.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_market_quality_prefilter_does_not_claim_setup_evidence() -> None:
    report = build_opportunity_scan_report(
        "scan-spot",
        spot_symbols=(
            _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000"),
        ),
    )
    candidate = report.candidates[0]
    payload = report.to_payload()
    ranked = cast(Sequence[Mapping[str, object]], payload["ranked_candidates"])
    payload_candidate = ranked[0]

    assert candidate.market_quality_score > Decimal("80")
    assert candidate.rank_score == Decimal("0")
    assert candidate.ranking_eligible is False
    assert candidate.selected_for_virtual_cycle is False
    assert candidate.setup_score == Decimal("0")
    assert candidate.multi_timeframe_score == Decimal("0")
    assert candidate.opportunity_score == Decimal("0")
    assert candidate.discovery_grade == "D"
    assert candidate.deep_setup_evidence_available is False
    assert candidate.strategy_id == "SPOT_MARKET_QUALITY_SCAN"
    assert candidate.regime == "UNCLASSIFIED"
    assert candidate.signal_score == Decimal("0")
    assert candidate.evidence_score == candidate.evidence_quality_score
    assert candidate.risk_reward is None
    assert candidate.visibility_state == "CONFIRMATION_PENDING"
    assert candidate.funnel_stage == OpportunityFunnelStage.QUALIFIED.value
    assert candidate.disposition == OpportunityDisposition.WAIT_FOR_RETEST.value
    assert candidate.confirmation_gaps == (
        "SETUP_EVIDENCE_UNAVAILABLE",
        "TRADE_PLAN_INCOMPLETE",
    )
    assert candidate.validation_gaps == (
        "OOS_NOT_COMPLETE",
        "PAPER_VALIDATION_PENDING",
    )
    assert "SETUP_EVIDENCE_UNAVAILABLE" in candidate.execution_blockers
    assert payload_candidate["rank_score_basis"] == "DETERMINISTIC_CANDIDATE_RANK_V1"
    assert payload_candidate["ranking_eligible"] is False
    assert payload_candidate["selected_for_virtual_cycle"] is False
    assert payload_candidate["market_quality_score"] == candidate.market_quality_score
    assert payload_candidate["opportunity_score"] == candidate.opportunity_score
    assert payload_candidate["setup_score"] == Decimal("0")
    assert payload_candidate["multi_timeframe_score"] == Decimal("0")
    assert payload_candidate["deep_setup_evidence_available"] is False
    supporting_evidence = cast(
        Sequence[str],
        payload_candidate["supporting_evidence"],
    )
    assert "SETUP_EVIDENCE_UNAVAILABLE" in supporting_evidence
    assert payload_candidate["execution_allowed"] is False
    assert payload_candidate["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_opportunity_report_v2_separates_visibility_from_execution() -> None:
    report = build_opportunity_scan_report(
        "scan-spot",
        spot_symbols=(
            _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000"),
        ),
    )
    payload = report.to_payload()
    report_v2 = cast(Mapping[str, object], payload["opportunity_report_v2"])
    sections = cast(
        Mapping[str, Sequence[Mapping[str, object]]],
        report_v2["sections"],
    )

    assert report_v2["report_version"] == "2.0"
    assert report_v2["execution_allowed"] is False
    assert report_v2["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert sections["top_opportunities"] == ()
    assert sections["confirmation_pending"][0]["symbol"] == "SOLUSDT"
    assert sections["confirmation_pending"][0]["grade"] == "D"
    assert sections["validation_ladder"][0]["symbol"] == "SOLUSDT"


def test_duplicate_candidate_is_not_reported_twice() -> None:
    report = build_opportunity_scan_report(
        "scan-spot",
        spot_symbols=(
            _spot("SOLUSDT", "SOL", volume="3000000", spread="9", depth="90000"),
            _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000"),
        ),
    )

    assert report.accepted_symbols == ("SOLUSDT",)
    assert len(report.candidates) == 1
    assert report.candidates[0].market_quality_score > Decimal("80")
    assert report.funnel.total_universe == 2
    assert report.funnel.symbols_scanned == 2
    assert report.funnel.raw_candidates == 1
    assert report.funnel.classified == 1
    assert report.funnel.discovery_eligible == 1
    assert report.funnel.paper_executed == 0


def test_opportunity_funnel_reports_discovery_and_execution_stages() -> None:
    report = build_opportunity_scan_report(
        "scan-all",
        spot_symbols=(
            _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000"),
            _spot("USDCUSDT", "USDC", volume="9000000", spread="2", depth="200000"),
        ),
    )
    payload = report.to_payload()
    funnel = cast(Mapping[str, object], payload["funnel"])

    assert funnel["total_universe"] == 2
    assert funnel["classified"] == 2
    assert funnel["discovered"] == 2
    assert funnel["qualified"] == 1
    assert funnel["virtual_eligible"] == 0
    assert funnel["discovery_eligible"] == 1
    assert funnel["market_quality_pass"] == 1
    assert funnel["setup_detected"] == 0
    assert funnel["symbols_scanned"] == 2
    assert funnel["raw_candidates"] == 2
    assert funnel["paper_eligible"] == 0
    assert funnel["accepted"] == 0
    assert funnel["rejected"] == 1
    assert funnel["watch"] == 0
    assert funnel["wait_for_retest"] == 1
    assert funnel["watch_only"] == 0
    assert funnel["confirmation_pending"] == 1
    assert funnel["paper_executed"] == 0
    assert funnel["raw_symbols_scanned"] == 2
    assert funnel["eligible_symbols"] == 1
    assert funnel["excluded_symbols"] == 1
    assert funnel["qualified_setups"] == 1
    assert funnel["virtual_executed_candidates"] == 0
    assert funnel["excluded_symbols_by_reason"]
    assert funnel["reason_code_counts"]


def test_opportunity_funnel_reports_category_rejections_separately() -> None:
    report = build_opportunity_scan_report(
        "scan-spot",
        spot_symbols=(
            _spot("SOLUSDT", "SOL", volume="5000000", spread="8", depth="120000"),
            _spot("USDCUSDT", "USDC", volume="9000000", spread="2", depth="200000"),
            _spot(
                "LOWVOLUSDT",
                "LOWVOL",
                volume="500000",
                spread="8",
                depth="120000",
            ),
            _spot(
                "WIDEUSDT",
                "WIDE",
                volume="5000000",
                spread="60",
                depth="120000",
            ),
            _spot(
                "BROKENDATAUSDT",
                "BROKEN",
                volume="5000000",
                spread="8",
                depth="120000",
                data_quality_ok=False,
            ),
        ),
    )
    funnel = report.funnel.to_payload()

    assert funnel["symbols_scanned"] == 5
    assert funnel["raw_candidates"] == 5
    assert funnel["data_quality_rejected"] == 1
    assert funnel["liquidity_rejected"] == 1
    assert funnel["spread_rejected"] == 1
    assert funnel["token_risk_rejected"] == 1
    assert funnel["watch_only"] == 0
    assert funnel["confirmation_pending"] == 1
    assert funnel["paper_eligible"] == 0
    assert funnel["paper_executed"] == 0


def test_opportunity_grade_policy_is_shared_by_radar_surfaces() -> None:
    assert classify_opportunity_grade(Decimal("90")) == "A"
    assert classify_opportunity_grade(Decimal("80")) == "B+"
    assert classify_opportunity_grade(Decimal("70")) == "B"
    assert classify_opportunity_grade(Decimal("60")) == "B-"
    assert classify_opportunity_grade(Decimal("50")) == "C"
    assert classify_opportunity_grade(Decimal("49.999")) == "D"

    payload = build_report_v2_payload(
        command="opportunities",
        status="ACTIVE",
        market="SPOT",
        snapshot_id="test:snapshot",
        ranked_candidates=(
            {
                "symbol": "HOTUSDT",
                "score": Decimal("77"),
                "discovery_grade": "A",
            },
        ),
        blockers=(),
    )
    sections = cast(Mapping[str, Sequence[Mapping[str, object]]], payload["sections"])
    candidate = sections["setup_forming"][0]
    assert candidate["grade"] == "B"


def test_opportunity_report_covers_empty_and_ordering() -> None:
    payload = build_report_v2_payload(
        command="opportunities",
        status="ACTIVE",
        market="SPOT",
        snapshot_id="snapshot-1",
        ranked_candidates=(
            {
                "symbol": "AAAUSDT",
                "market": "SPOT",
                "timeframe": "1h",
                "setup_name": "session_vwap_reclaim",
                "score": Decimal("92"),
                "confidence": Decimal("0.9"),
                "visibility_state": "WATCH_ONLY",
                "accepted": True,
            },
            {
                "symbol": "BBBUSDT",
                "market": "SPOT",
                "timeframe": "1h",
                "setup_name": "session_vwap_reclaim",
                "score": Decimal("50"),
                "confidence": Decimal("0.4"),
                "visibility_state": "SETUP_FORMING",
                "accepted": True,
                "validation_gaps": ("OOS_NOT_COMPLETE",),
            },
            {
                "symbol": "CCCUSDT",
                "market": "SPOT",
                "timeframe": "1h",
                "setup_name": "session_vwap_reclaim",
                "score": Decimal("30"),
                "confidence": Decimal("0.3"),
                "visibility_state": "CONFIRMATION_PENDING",
                "accepted": True,
                "confirmation_gaps": ("ENTRY_TRIGGER_REQUIRED",),
            },
            {
                "symbol": "DDDUSDT",
                "market": "SPOT",
                "timeframe": "1h",
                "setup_name": "session_vwap_reclaim",
                "score": Decimal("15"),
                "confidence": Decimal("0.2"),
                "accepted": False,
            },
        ),
        blockers=("RISK_APPROVAL_MISSING",),
        next_safe_actions=(),
    )
    sections = cast(Mapping[str, Sequence[Mapping[str, object]]], payload["sections"])
    next_actions = cast(Sequence[Mapping[str, str]], payload["next_safe_actions"])
    snapshot_diff = cast(Mapping[str, object], payload["snapshot_diff"])

    assert sections["top_opportunities"][0]["symbol"] == "AAAUSDT"
    assert sections["setup_forming"][0]["symbol"] == "BBBUSDT"
    assert sections["confirmation_pending"][0]["symbol"] == "CCCUSDT"
    assert sections["validation_ladder"][0]["symbol"] == "BBBUSDT"
    assert sections["rejected_or_lost"][0]["symbol"] == "DDDUSDT"
    assert next_actions == (
        {
            "action": "KEEP_RESEARCH_RADAR_RUNNING",
            "authority_boundary": "RESEARCH_ONLY",
        },
    )
    assert snapshot_diff["still_pending"] == ("BBBUSDT", "CCCUSDT")
    machine_payload = cast(Mapping[str, object], payload["machine_payload"])
    assert machine_payload["candidate_count"] == 4
    assert machine_payload["visible_candidate_count"] == 3


def test_opportunity_report_helpers_cover_negative_and_serialization_fallbacks() -> (
    None
):
    gap = OpportunityGap(
        layer="confirmation",
        code="ENTRY_TRIGGER_REQUIRED",
        next_safe_action="WAIT_FOR_CONFIRMATION",
    )
    action = OpportunityNextAction("RUN_VALIDATION_QUEUE")
    header = OpportunityReportHeader(
        command="opportunities",
        status="ACTIVE",
        market="SPOT",
        snapshot_id="snapshot-1",
    )
    candidate = OpportunityCandidateView(
        symbol="HOTUSDT",
        market="SPOT",
        timeframe="1h",
        setup_name="session_vwap_reclaim",
        direction="BULLISH",
        lifecycle_state="WATCH_ONLY",
        grade="A",
        score=Decimal("91"),
        confidence=Decimal("0.9"),
        why_visible=("MOMENTUM_CONFIRMED",),
        supporting_evidence=("snapshot:s1",),
        counter_evidence=(),
        discovery_blockers=(),
        confirmation_gaps=(),
        validation_gaps=(),
        promotion_requirements=(),
        execution_blockers=("LIVE_ORDER_BLOCKED",),
        next_safe_action="KEEP_RESEARCH_RADAR_RUNNING",
        upgrade_condition="None",
        invalidation_condition="Invalidated",
        pattern_type="CUSTOM_PATTERN",
    )
    report = OpportunityReportV2(
        header=header,
        sections={"top": OpportunitySection("top", (candidate,))},
        blockers=("LIVE_ORDER_BLOCKED",),
        next_safe_actions=(action,),
        snapshot_diff=OpportunitySnapshotDiff(
            previous_snapshot_id=None,
            current_snapshot_id="snapshot-1",
        ),
        machine_payload={"candidate_count": 1},
    )

    assert gap.to_payload()["layer"] == "confirmation"
    assert action.to_payload()["authority_boundary"] == "RESEARCH_ONLY"
    assert header.to_payload()["snapshot_id"] == "snapshot-1"
    assert candidate.to_payload()["pattern_type"] == "CUSTOM_PATTERN"
    report_payload = cast(Mapping[str, object], report.to_payload())
    sections_payload = cast(
        Mapping[str, Sequence[Mapping[str, object]]], report_payload["sections"]
    )
    assert sections_payload["top"][0]["symbol"] == "HOTUSDT"

    with pytest.raises(ValueError, match="cannot grant execution authority"):
        replace(report, execution_allowed=True)

    assert (
        _pattern_type_value(" CUSTOM ", fallback_setup_name="session_vwap_reclaim")
        == "CUSTOM"
    )
    assert (
        _pattern_type_value("   ", fallback_setup_name="session_vwap_reclaim")
        == "VWAP_CONFIRMATION"
    )
    assert _report_text_tuple("ONE") == ("ONE",)
    assert _report_text_tuple(5) == ()
    assert _decimal_score(object()) == Decimal("0")
    assert _decimal_score("NaN") == Decimal("0")
    assert _report_next_safe_action((), ("OOS_NOT_COMPLETE",)) == "RUN_VALIDATION_QUEUE"


def test_opportunity_scanner_covers_futures_command_and_unknown_command() -> None:
    future = _future(
        "BTCUSDT",
        "BTC",
        volume="7000000",
        spread="4",
        depth="250000",
        open_interest="20000000",
        funding="0.0001",
    )
    orchestrator = cast(
        ScannerOrchestrator,
        _StaticOrchestrator((UniverseFilterResult(future, True, ()),)),
    )

    futures_report = build_opportunity_scan_report(
        "scan-futures",
        orchestrator=orchestrator,
    )
    all_report = build_opportunity_scan_report("scan-all", orchestrator=orchestrator)

    assert futures_report.market == UniverseMarket.USD_M_FUTURES.value
    assert futures_report.candidates[0].derivatives_score == Decimal("100")
    assert all_report.market == "ALL"


def test_opportunity_candidate_model_derives_taxonomy_and_rejects_drift() -> None:
    candidate = OpportunityScanCandidate(
        symbol="HOTUSDT",
        market="SPOT",
        rank_score=Decimal("75"),
        accepted=True,
        blockers=("SETUP_EVIDENCE_UNAVAILABLE", "OOS_NOT_COMPLETE"),
        liquidity_score=Decimal("90"),
        depth_score=Decimal("90"),
        spread_score=Decimal("95"),
        opportunity_score=Decimal("65"),
        execution_blockers=("SETUP_EVIDENCE_UNAVAILABLE", "OOS_NOT_COMPLETE"),
    )

    assert candidate.confirmation_gaps == ("SETUP_EVIDENCE_UNAVAILABLE",)
    assert candidate.validation_gaps == ("OOS_NOT_COMPLETE",)
    assert candidate.snapshot_id == "universe:SPOT:HOTUSDT"
    assert candidate.opportunity_key == (
        "SPOT:HOTUSDT:UNSPECIFIED:SETUP_UNAVAILABLE:WATCH_ONLY"
    )
    assert candidate.opportunity_instance_id.endswith(candidate.snapshot_id)
    assert candidate.discovery_eligible is True
    assert candidate.qualified is True
    assert candidate.virtual_eligible is False
    assert candidate.funnel_stage == OpportunityFunnelStage.QUALIFIED.value
    assert candidate.disposition == OpportunityDisposition.WAIT_FOR_RETEST.value
    assert candidate.execution_eligible is False
    assert candidate.blocker_taxonomy["CONFIRMATION_GAP"] == (
        "SETUP_EVIDENCE_UNAVAILABLE",
    )

    with pytest.raises(ValueError, match="identity"):
        OpportunityScanCandidate(
            "",
            "SPOT",
            Decimal("1"),
            True,
            (),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
        )
    with pytest.raises(ValueError, match="between 0 and 100"):
        OpportunityScanCandidate(
            "HOTUSDT",
            "SPOT",
            Decimal("101"),
            True,
            (),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
        )
    with pytest.raises(ValueError, match="acceptance and exclusions"):
        OpportunityScanCandidate(
            "HOTUSDT",
            "SPOT",
            Decimal("1"),
            True,
            (),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            discovery_exclusions=("EXCLUDED",),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        OpportunityScanCandidate(
            "HOTUSDT",
            "SPOT",
            Decimal("1"),
            True,
            (),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        OpportunityScanCandidate(
            "HOTUSDT",
            "SPOT",
            Decimal("1"),
            True,
            (),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            promotion_status="PAPER_APPROVED",
        )

    with pytest.raises(
        ValueError,
        match="excluded scan candidate cannot be accepted",
    ):
        OpportunityScanCandidate(
            "HOTUSDT",
            "SPOT",
            Decimal("1"),
            True,
            (),
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            control_evaluation=ControlEvaluation(
                evaluation_id="control:evaluation:hotusdt",
                hard_blockers=(
                    HardBlocker(
                        blocker_id="hard:hotusdt:governance",
                        blocker_type="TEST",
                        source=ControlSource.GOVERNANCE,
                        severity=ControlSeverity.HIGH,
                        reason_code="GOVERNANCE_BLOCKER",
                        evidence_refs=("universe:SPOT:HOTUSDT",),
                        policy_ref="policy:test",
                    ),
                ),
                hard_gate_passed=False,
                eligibility=ControlEligibility.BLOCKED,
                reason_codes=("GOVERNANCE_BLOCKER",),
            ),
        )

    excluded_candidate = OpportunityScanCandidate(
        symbol="HOTUSDT",
        market="SPOT",
        rank_score=Decimal("75"),
        accepted=False,
        blockers=(),
        liquidity_score=Decimal("90"),
        depth_score=Decimal("90"),
        spread_score=Decimal("95"),
        opportunity_score=Decimal("65"),
        hard_blockers=("DISCOVERY_FILTERED",),
        market_quality_score=Decimal("80"),
    )
    assert excluded_candidate.discovery_exclusions == ("DISCOVERY_FILTERED",)
    assert excluded_candidate.hard_blockers == ("DISCOVERY_FILTERED",)
    assert excluded_candidate.funnel_stage == OpportunityFunnelStage.DISCOVERED.value
    assert excluded_candidate.disposition == OpportunityDisposition.REJECTED.value

    normalized = OpportunityScanCandidate(
        symbol="HOTUSDT",
        market="SPOT",
        rank_score=Decimal("75"),
        accepted=True,
        blockers=(),
        liquidity_score=Decimal("90"),
        depth_score=Decimal("90"),
        spread_score=Decimal("95"),
        opportunity_score=Decimal("65"),
        market_quality_score=Decimal("80"),
        raw_discovery_score=Decimal("55"),
        visibility_state=OpportunityVisibilityState.SETUP_FORMING.value,
        counter_evidence=("MANUAL_COUNTER_EVIDENCE",),
        next_safe_action="MANUAL_NEXT_ACTION",
    )
    assert normalized.discovery_exclusions == ()
    assert normalized.hard_blockers == ()
    assert normalized.visibility_state == OpportunityVisibilityState.SETUP_FORMING.value
    assert normalized.counter_evidence == ("MANUAL_COUNTER_EVIDENCE",)
    assert normalized.next_safe_action == "MANUAL_NEXT_ACTION"
    assert normalized.funnel_stage == OpportunityFunnelStage.VIRTUAL_ELIGIBLE.value
    assert normalized.disposition == OpportunityDisposition.ACCEPTED.value


def test_opportunity_report_model_rejects_invalid_state_and_authority() -> None:
    with pytest.raises(ValueError, match="status"):
        OpportunityScanReport("scan-spot", "SPOT", (), (), status="INVALID")
    with pytest.raises(ValueError, match="snapshot"):
        OpportunityScanReport("scan-spot", "SPOT", (), (), snapshot_id=" ")
    with pytest.raises(ValueError, match="cannot authorize"):
        OpportunityScanReport("scan-spot", "SPOT", (), (), execution_allowed=True)
    with pytest.raises(ValueError, match="cannot authorize"):
        OpportunityScanReport(
            "scan-spot",
            "SPOT",
            (),
            (),
            live_eligibility_status="READY",
        )
    with pytest.raises(ValueError, match="non-negative"):
        OpportunityFunnelMetrics(-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError, match="classified"):
        OpportunityFunnelMetrics(1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_opportunity_state_helpers_cover_safe_action_paths() -> None:
    assert _bounded_score(Decimal("1"), Decimal("0")) == Decimal("0")
    assert _bounded_score(Decimal("-1"), Decimal("100")) == Decimal("0")
    assert _bounded_score(Decimal("200"), Decimal("100")) == Decimal("100")
    assert (
        _visibility_state(
            discovery_exclusions=("EXCLUDED",),
            confirmation_gaps=(),
            validation_gaps=(),
            opportunity_score=Decimal("0"),
        )
        is OpportunityVisibilityState.INVALIDATED
    )
    assert (
        _visibility_state(
            discovery_exclusions=(),
            confirmation_gaps=(),
            validation_gaps=("OOS_NOT_COMPLETE",),
            opportunity_score=Decimal("0"),
        )
        is OpportunityVisibilityState.VALIDATION_PENDING
    )
    assert (
        _visibility_state(
            discovery_exclusions=(),
            confirmation_gaps=(),
            validation_gaps=(),
            opportunity_score=Decimal("50"),
        )
        is OpportunityVisibilityState.SETUP_FORMING
    )
    assert (
        _funnel_stage(
            discovery_exclusions=("EXCLUDED",),
            confirmation_gaps=(),
            validation_gaps=(),
        )
        is OpportunityFunnelStage.DISCOVERED
    )
    assert (
        _funnel_stage(
            discovery_exclusions=(),
            confirmation_gaps=("SETUP_EVIDENCE_UNAVAILABLE",),
            validation_gaps=(),
        )
        is OpportunityFunnelStage.QUALIFIED
    )
    assert (
        _funnel_stage(
            discovery_exclusions=(),
            confirmation_gaps=(),
            validation_gaps=(),
        )
        is OpportunityFunnelStage.VIRTUAL_ELIGIBLE
    )
    assert (
        _disposition(
            discovery_exclusions=("EXCLUDED",),
            confirmation_gaps=(),
            validation_gaps=(),
            virtual_eligible=False,
        )
        is OpportunityDisposition.REJECTED
    )
    assert (
        _disposition(
            discovery_exclusions=(),
            confirmation_gaps=("SETUP_EVIDENCE_UNAVAILABLE",),
            validation_gaps=(),
            virtual_eligible=False,
        )
        is OpportunityDisposition.WAIT_FOR_RETEST
    )
    assert (
        _disposition(
            discovery_exclusions=(),
            confirmation_gaps=(),
            validation_gaps=("OOS_NOT_COMPLETE",),
            virtual_eligible=False,
        )
        is OpportunityDisposition.WATCH
    )
    assert (
        _disposition(
            discovery_exclusions=(),
            confirmation_gaps=(),
            validation_gaps=(),
            virtual_eligible=True,
        )
        is OpportunityDisposition.ACCEPTED
    )
    assert (
        _lifecycle_state(OpportunityVisibilityState.INVALIDATED)
        == OpportunityLifecycleState.BLOCKED.value
    )
    assert (
        _lifecycle_state(OpportunityVisibilityState.VALIDATION_PENDING)
        == OpportunityLifecycleState.VALIDATION_PENDING.value
    )
    assert (
        _lifecycle_state(OpportunityVisibilityState.SETUP_FORMING)
        == OpportunityLifecycleState.SETUP_FORMING.value
    )
    assert (
        _lifecycle_state(OpportunityVisibilityState.RESEARCH_CANDIDATE)
        == OpportunityLifecycleState.DEVELOPING.value
    )
    assert _why_visible(
        market_quality_score=Decimal("10"),
        setup_score=Decimal("10"),
        liquidity_score=Decimal("10"),
        depth_score=Decimal("10"),
        spread_score=Decimal("10"),
    ) == ("WATCHLIST_RESEARCH_VISIBLE",)
    assert _why_visible(
        market_quality_score=Decimal("80"),
        setup_score=Decimal("70"),
        liquidity_score=Decimal("80"),
        depth_score=Decimal("80"),
        spread_score=Decimal("90"),
    ) == (
        "MARKET_QUALITY_PASS",
        "DEEP_SETUP_EVIDENCE_AVAILABLE",
        "LIQUIDITY_ACCEPTABLE",
        "DEPTH_ACCEPTABLE",
        "SPREAD_ACCEPTABLE",
    )
    assert (
        _next_safe_action(
            discovery_exclusions=("EXCLUDED",),
            confirmation_gaps=(),
            validation_gaps=(),
        )
        == "DO_NOT_SHOW_AS_ACTIVE_OPPORTUNITY"
    )
    assert (
        _next_safe_action(
            discovery_exclusions=(),
            confirmation_gaps=(),
            validation_gaps=("OOS_NOT_COMPLETE",),
        )
        == "RUN_VALIDATION_QUEUE"
    )
    assert _opportunity_score(
        market_quality_score=Decimal("100"),
        setup_score=Decimal("100"),
        evidence_quality_score=Decimal("100"),
        discovery_exclusions=(),
    ) == Decimal("100.00")
    assert _blocker_source("LOW_LIQUIDITY") is ControlSource.LIQUIDITY
    assert _blocker_source("STABLECOIN_BASE_EXCLUDED") is ControlSource.RISK
    assert _blocker_source("GOVERNANCE_BLOCKER") is ControlSource.GOVERNANCE
    assert (
        _blocker_resolution_authority("LOW_LIQUIDITY")
        is ControlResolutionAuthority.LIQUIDITY_ENGINE
    )
    assert (
        _blocker_resolution_authority("STABLECOIN_BASE_EXCLUDED")
        is ControlResolutionAuthority.RISK_ENGINE
    )
    assert (
        _blocker_resolution_authority("GOVERNANCE_BLOCKER")
        is ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE
    )


def test_opportunity_soft_penalties_cover_liquidity_and_depth_degradation() -> None:
    symbol = _spot("THINUSDT", "THIN", volume="1000000", spread="95", depth="40000")

    penalties = _soft_penalties(
        symbol,
        liquidity=Decimal("70"),
        depth=Decimal("70"),
        spread=Decimal("95"),
    )

    assert tuple(item.reason_code for item in penalties) == (
        "WEAK_RELATIVE_VOLUME",
        "SHALLOW_DEPTH",
    )


def test_candidate_ranking_policy_selects_top_virtual_candidates_per_market() -> None:
    ranked = _apply_candidate_ranking(
        (
            _virtual_candidate("ALPHAUSDT", "SPOT", setup="92", evidence="88"),
            _virtual_candidate("BETAUSDT", "SPOT", setup="86", evidence="84"),
            _virtual_candidate("GAMMAUSDT", "SPOT", setup="80", evidence="82"),
            _virtual_candidate("DELTAUSDT", "SPOT", setup="72", evidence="78"),
            _virtual_candidate(
                "BTCUSDT",
                "USD_M_FUTURES",
                setup="91",
                evidence="89",
            ),
            _virtual_candidate(
                "ETHUSDT",
                "USD_M_FUTURES",
                setup="87",
                evidence="86",
            ),
            _virtual_candidate(
                "SOLUSDT",
                "USD_M_FUTURES",
                setup="84",
                evidence="83",
            ),
            _virtual_candidate(
                "XRPUSDT",
                "USD_M_FUTURES",
                setup="70",
                evidence="74",
            ),
            _virtual_candidate(
                "BLOCKEDUSDT",
                "SPOT",
                setup="99",
                evidence="99",
                hard_blockers=("DISCOVERY_FILTERED",),
                accepted=False,
            ),
        ),
        CandidateRankingPolicy(),
    )

    selected = {item.symbol for item in ranked if item.selected_for_virtual_cycle}
    spot_selected = tuple(
        item.symbol
        for item in ranked
        if item.market == "SPOT" and item.selected_for_virtual_cycle
    )
    futures_selected = tuple(
        item.symbol
        for item in ranked
        if item.market == "USD_M_FUTURES" and item.selected_for_virtual_cycle
    )
    blocked = next(item for item in ranked if item.symbol == "BLOCKEDUSDT")

    assert selected == {
        "ALPHAUSDT",
        "BETAUSDT",
        "GAMMAUSDT",
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    }
    assert spot_selected == ("ALPHAUSDT", "BETAUSDT", "GAMMAUSDT")
    assert futures_selected == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert blocked.ranking_eligible is False
    assert blocked.selected_for_virtual_cycle is False
    assert blocked.rank_score == Decimal("0")


def test_candidate_ranking_policy_rejects_invalid_weight_sum() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.00"):
        CandidateRankingPolicy(
            setup_quality_weight=Decimal("0.30"),
            evidence_quality_weight=Decimal("0.20"),
            regime_alignment_weight=Decimal("0.15"),
            liquidity_quality_weight=Decimal("0.20"),
            execution_quality_weight=Decimal("0.10"),
            reward_risk_quality_weight=Decimal("0.10"),
        )


def _spot(
    symbol: str,
    base: str,
    *,
    volume: str,
    spread: str,
    depth: str,
    data_quality_ok: bool = True,
) -> UniverseSymbol:
    return UniverseSymbol(
        symbol=symbol,
        market=UniverseMarket.SPOT,
        base_asset=base,
        quote_asset="USDT",
        status="TRADING",
        min_notional_usdt=Decimal("5"),
        quote_volume_24h_usdt=Decimal(volume),
        spread_bps=Decimal(spread),
        depth_0_5_pct_usdt=Decimal(depth),
        data_quality_ok=data_quality_ok,
    )


def _future(
    symbol: str,
    base: str,
    *,
    volume: str,
    spread: str,
    depth: str,
    open_interest: str,
    funding: str,
    data_quality_ok: bool = True,
) -> UniverseSymbol:
    return UniverseSymbol(
        symbol=symbol,
        market=UniverseMarket.USD_M_FUTURES,
        base_asset=base,
        quote_asset="USDT",
        status="TRADING",
        min_notional_usdt=Decimal("5"),
        quote_volume_24h_usdt=Decimal(volume),
        spread_bps=Decimal(spread),
        depth_0_5_pct_usdt=Decimal(depth),
        contract_type="PERPETUAL",
        margin_asset="USDT",
        open_interest_usdt=Decimal(open_interest),
        funding_rate=Decimal(funding),
        data_quality_ok=data_quality_ok,
    )


def _virtual_candidate(
    symbol: str,
    market: str,
    *,
    setup: str,
    evidence: str,
    hard_blockers: tuple[str, ...] = (),
    accepted: bool = True,
) -> OpportunityScanCandidate:
    return OpportunityScanCandidate(
        symbol=symbol,
        market=market,
        rank_score=Decimal("0"),
        accepted=accepted,
        blockers=hard_blockers,
        liquidity_score=Decimal("90"),
        depth_score=Decimal("92"),
        spread_score=Decimal("95"),
        strategy_id="TEST_STRATEGY",
        regime="TREND",
        signal_score=Decimal(setup),
        evidence_score=Decimal(evidence),
        risk_reward=Decimal("2.0"),
        invalidation="TEST_INVALIDATION",
        expected_holding_period="4H",
        market_quality_score=Decimal("90"),
        opportunity_score=Decimal("78"),
        discovery_grade="B+",
        research_confidence=Decimal(evidence),
        research_state="READY",
        lifecycle_state=OpportunityLifecycleState.SETUP_FORMING.value,
        opportunity_key=f"{market}:{symbol}:TEST",
        opportunity_instance_id=f"{market}:{symbol}:TEST:INSTANCE",
        snapshot_id=f"universe:{market}:{symbol}",
        direction="LONG",
        discovery_exclusions=hard_blockers,
        execution_blockers=(),
        hard_blockers=hard_blockers,
        soft_penalties=(),
        visibility_state=OpportunityVisibilityState.SETUP_FORMING.value,
        why_visible=("TEST_VISIBLE",),
        supporting_evidence=("TEST_EVIDENCE",),
        next_safe_action="TEST_NEXT_ACTION",
        upgrade_condition="TEST_UPGRADE",
        invalidation_condition="TEST_INVALIDATION_CONDITION",
        base_score=Decimal("90"),
        total_penalty=Decimal("0"),
        adjusted_score=Decimal("90"),
        eligibility=ControlEligibility.ELIGIBLE.value,
        control_evaluation=ControlEvaluation(
            evaluation_id=f"control:evaluation:{symbol.lower()}",
            hard_blockers=(),
            hard_gate_passed=True,
            base_score=Decimal("90"),
            total_penalty=Decimal("0"),
            adjusted_score=Decimal("90"),
            eligibility=ControlEligibility.ELIGIBLE,
            reason_codes=(),
        ),
        derivatives_score=Decimal("60") if market == "USD_M_FUTURES" else Decimal("0"),
        structure_score=Decimal("85"),
        momentum_score=Decimal("80"),
        volume_score=Decimal("82"),
        volatility_score=Decimal("76"),
        setup_score=Decimal(setup),
        multi_timeframe_score=Decimal("88"),
        evidence_quality_score=Decimal(evidence),
        trade_plan_complete=True,
        validation_passed=True,
        paper_eligible=False,
        deep_setup_evidence_available=True,
        asset_risk_status="PASSED",
    )


class _StaticOrchestrator:
    def __init__(self, results: tuple[UniverseFilterResult, ...]) -> None:
        self._results = results

    def scan_spot(self, symbols: tuple[UniverseSymbol, ...]) -> SimpleNamespace:
        return SimpleNamespace(results=self._results)

    def scan_futures(self, symbols: tuple[UniverseSymbol, ...]) -> SimpleNamespace:
        return SimpleNamespace(results=self._results)

    def scan_all(
        self,
        *,
        spot_symbols: tuple[UniverseSymbol, ...],
        futures_symbols: tuple[UniverseSymbol, ...],
    ) -> SimpleNamespace:
        return SimpleNamespace(results=self._results)

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.config import Settings
from ai4binance.opportunities import OpportunityInbox, OpportunityInboxItem
from ai4binance.portfolio.opportunity_recovery import (
    OpportunityRecoveryRadar,
    RecoveryCandidate,
    RecoveryLadderStage,
    RecoveryLensContribution,
    RecoveryProposalKind,
    RecoveryRadarPolicy,
    TechnicalRecoveryRange,
    _confidence_decimal,
    _decimal,
    _extract_inbox,
    _extract_market_state,
    _false_positive_risk,
    _has_context_value,
    _intelligence_score,
    _inventory_blockers,
    _mapping,
    _market_intelligence_blockers,
    _miss_risk,
    _next_actions_for_item,
    _opportunity_grade,
    _review_action_for_item,
    _score_decimal,
    _select_range,
    _sequence,
    _source_presence_score,
    _stage_for_item,
    _technical_range_confidence,
    _technical_range_evidence_refs,
    _technical_ranges_from_market_state,
    _text_tuple,
    _threshold_score,
    build_opportunity_recovery_radar,
)
from ai4binance.validation import ValidationSummary


def test_recovery_radar_builds_inventory_ladder_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    radar = build_opportunity_recovery_radar(
        settings,
        symbol="HOTUSDT",
        inventory_units="18400000",
        range_low="0.000312",
        range_high="0.000390",
        opportunities_builder=lambda settings, symbol: _opportunities_payload(symbol),
    )

    assert radar.symbol == "HOTUSDT"
    assert radar.recovery_mode == "RECOVERY_GUARDED_RESEARCH_MODE"
    assert radar.hindsight_notice == "HINDSIGHT_ENVELOPE_ONLY"
    assert radar.range_source == "OPERATOR_RANGE"
    assert radar.range_move_ratio == Decimal("0.25")
    assert radar.ideal_full_cycle_end_units == Decimal("23000000")
    assert radar.ideal_full_cycle_unit_gain == Decimal("4600000")
    inventory_candidate = radar.ladder[0]
    assert inventory_candidate.proposal_kind is (
        RecoveryProposalKind.INVENTORY_SELL_REBUY_REVIEW
    )
    assert inventory_candidate.ladder_stage is RecoveryLadderStage.TRADE_CANDIDATE
    assert inventory_candidate.review_action == "SELL_HIGH_REBUY_LOW_REVIEW"
    assert inventory_candidate.max_review_units == Decimal("4600000.00")
    assert inventory_candidate.estimated_cycle_unit_gain > Decimal("1100000")
    assert inventory_candidate.intelligence_score > Decimal("80")
    assert inventory_candidate.opportunity_grade in {
        "RADAR_ONLY",
        "C_REVIEW",
        "B_REVIEW",
    }
    assert inventory_candidate.miss_risk in {"LOW", "MEDIUM", "MEDIUM_HIGH"}
    assert inventory_candidate.false_positive_risk == "HIGH"
    assert tuple(lens.lens for lens in inventory_candidate.lens_contributions)[:4] == (
        "inventory_context",
        "range_amplitude",
        "validation_oos",
        "risk_gate",
    )
    assert "mspacis_structure" in tuple(
        lens.lens for lens in inventory_candidate.lens_contributions
    )
    assert "rotation_economics" in tuple(
        lens.lens for lens in inventory_candidate.lens_contributions
    )
    assert "RECOVERY_COST_BASIS_UNVERIFIED" in inventory_candidate.blockers
    assert "OOS_APPROVAL_MISSING" in inventory_candidate.blockers
    assert "RISK_APPROVAL_MISSING" in inventory_candidate.blockers
    assert "LIVE_ORDER_BLOCKED" in inventory_candidate.blockers
    assert inventory_candidate.validation_queue_ref.startswith(
        "recovery-validation:recovery:HOTUSDT:inventory-rotation"
    )
    assert inventory_candidate.oos_evidence_status == "QUEUED_RESEARCH_ONLY"
    assert radar.execution_allowed is False
    assert radar.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_recovery_radar_derives_dynamic_technical_range_without_manual_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    radar = build_opportunity_recovery_radar(
        settings,
        symbol="HOTUSDT",
        inventory_units="18400000",
        opportunities_builder=lambda settings, symbol: _technical_opportunities_payload(
            symbol
        ),
    )

    assert radar.range_source == "TECHNICAL_RANGE:15m:ROLLING_SUPPORT_RESISTANCE"
    assert radar.hindsight_notice == "TECHNICAL_RANGE_ESTIMATE_NOT_SIGNAL"
    assert radar.range_low == Decimal("0.000331")
    assert radar.range_high == Decimal("0.000340")
    assert radar.range_move_ratio > Decimal("0.027")
    assert "TECHNICAL_RANGE_NOT_EXECUTION_SIGNAL" in radar.blockers
    technical = radar.ladder[1]
    assert technical.proposal_kind is (
        RecoveryProposalKind.TECHNICAL_RANGE_ROTATION_REVIEW
    )
    assert technical.setup_name == "technical_range_rotation"
    assert technical.review_action == "SELL_RESISTANCE_REBUY_SUPPORT_REVIEW"
    assert technical.estimated_sell_price == Decimal("0.000340")
    assert technical.estimated_rebuy_price == Decimal("0.000331")
    assert "market_outlook:key_levels:15m" in technical.evidence_refs
    assert "market_outlook:timeframe_biases" in technical.evidence_refs
    assert "market_outlook:setups_on_radar" in technical.evidence_refs
    assert "MSPACIS:pending_explicit_contract" in technical.evidence_refs
    assert technical.intelligence_score > Decimal("90")
    assert technical.opportunity_grade in {"C_REVIEW", "B_REVIEW", "A_REVIEW"}
    assert technical.miss_risk in {"MEDIUM", "MEDIUM_HIGH", "HIGH"}
    assert technical.false_positive_risk == "HIGH"
    assert tuple(lens.lens for lens in technical.lens_contributions)[:4] == (
        "support_resistance",
        "range_amplitude",
        "trend_regime",
        "pattern_setup",
    )
    assert "TECHNICAL_TRIGGER_CONFIRMATION_REQUIRED" in technical.blockers
    assert "LEVEL_REACTION_CONFIRMATION_REQUIRED" in technical.blockers
    assert "LIVE_ORDER_BLOCKED" in technical.blockers
    assert technical.validation_queue_ref.startswith(
        "recovery-validation:recovery:HOTUSDT:technical-range:15m"
    )
    assert technical.oos_evidence_status == "QUEUED_RESEARCH_ONLY"
    assert technical.execution_allowed is False


def test_recovery_radar_keeps_existing_watchlist_candidates_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    radar = build_opportunity_recovery_radar(
        settings,
        symbol="HOTUSDT",
        inventory_units="18400000",
        range_low="0.000312",
        range_high="0.000390",
        cost_basis="0.000350",
        opportunities_builder=lambda settings, symbol: _opportunities_payload(symbol),
    )

    watchlist = radar.ladder[1]
    assert watchlist.proposal_kind is (
        RecoveryProposalKind.VALIDATION_OPPORTUNITY_REVIEW
    )
    assert watchlist.setup_name == "breakout_retest"
    assert watchlist.ladder_stage is RecoveryLadderStage.WATCHLIST
    assert watchlist.review_action == "COMPLETE_OOS_BEFORE_ACTION"
    assert watchlist.intelligence_score > Decimal("0")
    assert watchlist.false_positive_risk == "HIGH"
    assert tuple(lens.lens for lens in watchlist.lens_contributions)[:4] == (
        "pattern_setup",
        "validation_oos",
        "risk_gate",
        "directional_clarity",
    )
    assert "mspacis_structure" in tuple(
        lens.lens for lens in watchlist.lens_contributions
    )
    assert "RUN_VALIDATION_QUEUE" in watchlist.next_safe_actions
    assert "BUILD_CANDIDATE_RISK_PLAN" in watchlist.next_safe_actions
    assert watchlist.validation_queue_ref.startswith(
        "recovery-validation:recovery:HOTUSDT:watchlist"
    )
    assert watchlist.oos_evidence_status == "QUEUED_RESEARCH_ONLY"
    assert watchlist.execution_allowed is False
    assert watchlist.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_recovery_radar_promotes_ready_items_to_paper_ready_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    radar = build_opportunity_recovery_radar(
        settings,
        symbol="HOTUSDT",
        inventory_units="18400000",
        range_low="0.000312",
        range_high="0.000390",
        opportunities_builder=lambda settings, symbol: {
            "inbox": {
                "symbol": symbol,
                "items": (
                    {
                        "market": "SPOT",
                        "symbol": symbol,
                        "setup_name": "support_reclaim",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "source": "validation_summary",
                        "status": "READY",
                        "promotion_status": "STAGED_CANDIDATE",
                        "score": "72",
                        "confidence": "0.61",
                        "blockers": (),
                    },
                ),
            },
            "blockers": (),
        },
    )

    staged = radar.ladder[1]
    assert staged.ladder_stage is RecoveryLadderStage.PAPER_READY
    assert staged.review_action == "BUY_REVIEW_AFTER_RISK_PLAN"
    assert staged.blockers == ("LIVE_ORDER_BLOCKED",)
    assert staged.next_safe_actions == ("KEEP_RECOVERY_RADAR_RUNNING",)
    assert staged.execution_allowed is False
    assert staged.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_recovery_radar_default_builder_fails_closed_without_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    radar = build_opportunity_recovery_radar(
        settings,
        symbol="HOTUSDT",
        inventory_units="18400000",
        range_low="0.000312",
        range_high="0.000390",
    )

    assert radar.ladder[0].setup_name == "inventory_rotation_recovery"
    assert "VALIDATION_ARTIFACTS_UNAVAILABLE" in radar.blockers
    assert "MARKET_OUTLOOK_UNAVAILABLE" in radar.blockers
    assert "NO_VISIBLE_OPPORTUNITY_EVIDENCE" in radar.blockers
    assert "LIVE_ORDER_BLOCKED" in radar.blockers
    assert radar.next_safe_actions


def test_recovery_radar_contracts_reject_authority_and_bad_ranges() -> None:
    with pytest.raises(ValueError, match="range low must be below high"):
        OpportunityRecoveryRadar(
            symbol="HOTUSDT",
            inventory_units=Decimal("1"),
            range_low=Decimal("2"),
            range_high=Decimal("1"),
            range_source="OPERATOR_RANGE",
            range_move_ratio=Decimal("0"),
            ideal_full_cycle_end_units=Decimal("1"),
            ideal_full_cycle_unit_gain=Decimal("0"),
            ladder=(),
            blockers=("LIVE_ORDER_BLOCKED",),
            next_safe_actions=("RUN_VALIDATION_QUEUE",),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        RecoveryCandidate(
            candidate_id="recovery:bad",
            symbol="HOTUSDT",
            proposal_kind=RecoveryProposalKind.INVENTORY_SELL_REBUY_REVIEW,
            ladder_stage=RecoveryLadderStage.TRADE_CANDIDATE,
            review_action="SELL_HIGH_REBUY_LOW_REVIEW",
            rationale="test",
            source="test",
            timeframe="1h",
            setup_name="inventory_rotation_recovery",
            score=Decimal("50"),
            confidence=Decimal("0"),
            blockers=("LIVE_ORDER_BLOCKED",),
            next_safe_actions=("PREPARE_RISK_REVIEW",),
            evidence_refs=("test",),
            execution_allowed=True,
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"maximum_inventory_review_ratio": Decimal("0")}, "inventory review ratio"),
        ({"fee_ratio_per_side": Decimal("1")}, "fee ratio"),
        ({"minimum_range_move_ratio": Decimal("-0.01")}, "ratios"),
        ({"minimum_notional_usdt": Decimal("0")}, "policy limits"),
        ({"high_attention_score": Decimal("0")}, "policy limits"),
        (
            {
                "high_attention_score": Decimal("120"),
                "action_candidate_score": Decimal("100"),
            },
            "policy limits",
        ),
        ({"action_candidate_score": Decimal("201")}, "policy limits"),
        ({"maximum_technical_ranges": -1}, "policy limits"),
        ({"max_candidates": 0}, "policy limits"),
    ],
)
def test_recovery_radar_policy_rejects_invalid_limits(
    kwargs: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        RecoveryRadarPolicy(**cast(Any, kwargs))


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"timeframe": ""}, "identity"),
        ({"max_review_units": Decimal("-1")}, "non-negative"),
        ({"score": Decimal("101")}, "out of range"),
        ({"confidence": Decimal("2")}, "out of range"),
        ({"intelligence_score": Decimal("201")}, "intelligence score"),
        ({"opportunity_grade": ""}, "IQ labels"),
        ({"estimated_sell_price": Decimal("0")}, "prices"),
        ({"blockers": ("A", "A")}, "unique"),
        ({"next_safe_actions": ("",)}, "blanks"),
        ({"promotion_status": "STAGED_CANDIDATE"}, "cannot authorize"),
        ({"live_eligibility_status": "PAPER_READY"}, "cannot authorize"),
    ],
)
def test_recovery_candidate_contract_rejects_invalid_inputs(
    overrides: dict[str, object],
    match: str,
) -> None:
    base = {
        "candidate_id": "recovery:HOTUSDT:test",
        "symbol": "HOTUSDT",
        "proposal_kind": RecoveryProposalKind.VALIDATION_OPPORTUNITY_REVIEW,
        "ladder_stage": RecoveryLadderStage.WATCHLIST,
        "review_action": "KEEP_ON_RECOVERY_WATCHLIST",
        "rationale": "test",
        "source": "test",
        "timeframe": "1h",
        "setup_name": "test_setup",
        "score": Decimal("50"),
        "confidence": Decimal("0.5"),
        "blockers": ("LIVE_ORDER_BLOCKED",),
        "next_safe_actions": ("RUN_VALIDATION_QUEUE",),
        "evidence_refs": ("test",),
    }
    base.update(overrides)

    with pytest.raises(ValueError, match=match):
        RecoveryCandidate(**cast(Any, base))


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"symbol": ""}, "symbol is required"),
        ({"range_move_ratio": Decimal("-1")}, "non-negative"),
        ({"blockers": ("A", "A")}, "unique"),
        ({"next_safe_actions": ("",)}, "blanks"),
        ({"execution_allowed": True}, "cannot authorize"),
        ({"promotion_status": "STAGED_CANDIDATE"}, "cannot authorize"),
    ],
)
def test_recovery_radar_contract_rejects_invalid_inputs(
    overrides: dict[str, object],
    match: str,
) -> None:
    base = {
        "symbol": "HOTUSDT",
        "inventory_units": Decimal("1"),
        "range_low": Decimal("1"),
        "range_high": Decimal("2"),
        "range_source": "OPERATOR_RANGE",
        "range_move_ratio": Decimal("1"),
        "ideal_full_cycle_end_units": Decimal("2"),
        "ideal_full_cycle_unit_gain": Decimal("1"),
        "ladder": (),
        "blockers": ("LIVE_ORDER_BLOCKED",),
        "next_safe_actions": ("RUN_VALIDATION_QUEUE",),
    }
    base.update(overrides)

    with pytest.raises(ValueError, match=match):
        OpportunityRecoveryRadar(**cast(Any, base))

    with pytest.raises(ValueError, match="range source is required"):
        OpportunityRecoveryRadar(
            symbol="HOTUSDT",
            inventory_units=Decimal("1"),
            range_low=Decimal("1"),
            range_high=Decimal("2"),
            range_source="",
            range_move_ratio=Decimal("1"),
            ideal_full_cycle_end_units=Decimal("2"),
            ideal_full_cycle_unit_gain=Decimal("1"),
            ladder=(),
            blockers=("LIVE_ORDER_BLOCKED",),
            next_safe_actions=("RUN_VALIDATION_QUEUE",),
        )


def test_technical_recovery_range_contract_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="identity"):
        TechnicalRecoveryRange(
            timeframe="",
            source="ROLLING_SUPPORT_RESISTANCE",
            support_price=Decimal("1"),
            resistance_price=Decimal("2"),
            range_move_ratio=Decimal("1"),
            confidence=Decimal("0.5"),
            evidence_refs=("market_outlook:key_levels:1h",),
        )
    with pytest.raises(ValueError, match="support must be below resistance"):
        TechnicalRecoveryRange(
            timeframe="1h",
            source="ROLLING_SUPPORT_RESISTANCE",
            support_price=Decimal("2"),
            resistance_price=Decimal("1"),
            range_move_ratio=Decimal("1"),
            confidence=Decimal("0.5"),
            evidence_refs=("market_outlook:key_levels:1h",),
        )
    with pytest.raises(ValueError, match="out of range"):
        TechnicalRecoveryRange(
            timeframe="1h",
            source="ROLLING_SUPPORT_RESISTANCE",
            support_price=Decimal("1"),
            resistance_price=Decimal("2"),
            range_move_ratio=Decimal("1"),
            confidence=Decimal("2"),
            evidence_refs=("market_outlook:key_levels:1h",),
        )


def test_recovery_lens_contract_and_iq_score_are_bounded() -> None:
    with pytest.raises(ValueError, match="identity"):
        RecoveryLensContribution(
            lens="",
            direction="CONTEXT",
            score=Decimal("50"),
            confidence=Decimal("0.5"),
            evidence_ref="test",
        )
    with pytest.raises(ValueError, match="out of range"):
        RecoveryLensContribution(
            lens="trend_regime",
            direction="CONTEXT",
            score=Decimal("101"),
            confidence=Decimal("0.5"),
            evidence_ref="test",
        )

    score = _intelligence_score(
        (
            RecoveryLensContribution(
                "support_resistance",
                "SELL_REBUY",
                Decimal("100"),
                Decimal("1"),
                "levels",
            ),
            RecoveryLensContribution(
                "validation_oos",
                "GATED",
                Decimal("100"),
                Decimal("1"),
                "validation",
            ),
        )
    )

    assert score == Decimal("200")


def test_recovery_radar_builder_rejects_invalid_operator_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="inventory_units must be positive"):
        build_opportunity_recovery_radar(
            settings,
            inventory_units="0",
            range_low="0.000312",
            range_high="0.000390",
        )
    with pytest.raises(ValueError, match="range_low must be below range_high"):
        build_opportunity_recovery_radar(
            settings,
            inventory_units="18400000",
            range_low="0.000390",
            range_high="0.000312",
            opportunities_builder=lambda settings, symbol: (
                _technical_opportunities_payload(symbol)
            ),
        )
    with pytest.raises(ValueError, match="cost_basis must be positive"):
        build_opportunity_recovery_radar(
            settings,
            inventory_units="18400000",
            range_low="0.000312",
            range_high="0.000390",
            cost_basis="-1",
        )
    with pytest.raises(ValueError, match="technical range is unavailable"):
        build_opportunity_recovery_radar(
            settings,
            inventory_units="18400000",
            opportunities_builder=lambda settings, symbol: _opportunities_payload(
                symbol
            ),
        )


def test_technical_range_derivation_pairs_support_and_resistance_by_timeframe() -> None:
    ranges = _technical_ranges_from_market_state(
        cast(
            Mapping[str, object],
            _technical_opportunities_payload("HOTUSDT")["market_state"],
        ),
        RecoveryRadarPolicy(),
    )

    assert tuple(item.timeframe for item in ranges)[:2] == ("15m", "1h")
    assert ranges[0].support_price == Decimal("0.000331")
    assert ranges[0].resistance_price == Decimal("0.000340")
    assert ranges[0].confidence > Decimal("0.30")


def test_recovery_radar_helper_branches_cover_candidate_ladder_semantics() -> None:
    ready_item = {
        "status": "READY",
        "promotion_status": "STAGED_CANDIDATE",
        "direction": "BULLISH",
    }
    blocked_item = {
        "status": "WATCHLIST",
        "promotion_status": "STAGED_CANDIDATE",
        "direction": "BEARISH",
    }
    neutral_item = {
        "status": "WATCHLIST",
        "promotion_status": "RESEARCH_ONLY",
        "direction": "UNKNOWN",
    }

    assert _stage_for_item(ready_item, ()) is RecoveryLadderStage.PAPER_READY
    assert (
        _stage_for_item(blocked_item, ("RISK_APPROVAL_MISSING",))
        is RecoveryLadderStage.LIVE_BLOCKED_UNTIL_RISK_OOS
    )
    assert (
        _stage_for_item(neutral_item, ("OOS_APPROVAL_MISSING",))
        is RecoveryLadderStage.WATCHLIST
    )
    assert _stage_for_item(neutral_item, ()) is RecoveryLadderStage.RADAR_ONLY
    assert _review_action_for_item(blocked_item, ()) == "SELL_REVIEW_AFTER_RISK_PLAN"
    assert _review_action_for_item(ready_item, ()) == "BUY_REVIEW_AFTER_RISK_PLAN"
    assert (
        _review_action_for_item(neutral_item, ("OOS_APPROVAL_MISSING",))
        == "COMPLETE_OOS_BEFORE_ACTION"
    )
    assert _review_action_for_item(neutral_item, ()) == "KEEP_ON_RECOVERY_WATCHLIST"
    assert _next_actions_for_item(
        (
            "BACKTEST_APPROVAL_MISSING",
            "RISK_APPROVAL_MISSING",
            "EXECUTION_NOT_ALLOWED",
            "ORDER_BOOK_DEPTH_MISSING",
        )
    ) == (
        "RUN_VALIDATION_QUEUE",
        "PREPARE_RISK_REVIEW",
        "BUILD_CANDIDATE_RISK_PLAN",
        "REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE",
    )


def test_recovery_radar_mapping_and_normalization_helpers() -> None:
    item = OpportunityInboxItem(
        market="SPOT",
        symbol="HOTUSDT",
        setup_name="breakout_retest",
        timeframe="1h",
        direction="UNKNOWN",
        source="validation_summary",
        status="WATCHLIST",
        promotion_status="RESEARCH_ONLY",
        score=0.42,
        confidence=0.25,
        blockers=("OOS_APPROVAL_MISSING",),
    )
    inbox = OpportunityInbox(
        symbol="HOTUSDT",
        items=(item,),
        validation_summary=ValidationSummary(
            symbol="HOTUSDT",
            artifact_directory="runtime/artifacts/validation",
            run_count=0,
            staged_candidate_count=0,
            research_only_count=0,
            top_blockers=(),
            runs=(),
            blockers=("VALIDATION_ARTIFACTS_UNAVAILABLE",),
        ),
        blockers=("NO_READY_CANDIDATE",),
    )

    extracted = _extract_inbox({"inbox": inbox})
    assert _extract_market_state({"market_state": {"symbol": "HOTUSDT"}}) == {
        "symbol": "HOTUSDT"
    }
    assert _extract_market_state({"market_state": "bad"}) == {}
    assert extracted["symbol"] == "HOTUSDT"
    assert _sequence(extracted["items"]) == (item,)
    mapped = _mapping(item)
    assert mapped["setup_name"] == "breakout_retest"
    assert _mapping(object()) == {}
    assert _sequence(["a", "b"]) == ("a", "b")
    assert _sequence("not-a-sequence") == ()
    assert _text_tuple(" HOTUSDT ") == ("HOTUSDT",)
    assert _text_tuple([" OOS_APPROVAL_MISSING ", ""]) == ("OOS_APPROVAL_MISSING",)
    assert _score_decimal("0.42") == Decimal("42.00")
    assert _score_decimal("142") == Decimal("100")
    assert _confidence_decimal("-1") == Decimal("0")
    assert _confidence_decimal("2") == Decimal("1")
    assert _decimal("not-a-decimal", Decimal("7")) == Decimal("7")
    assert _text_tuple({"bad": "type"}) == ()


def test_recovery_radar_helper_branches_cover_fail_closed_edges() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        RecoveryLensContribution(
            lens="trend_regime",
            direction="CONTEXT",
            score=Decimal("-1"),
            confidence=Decimal("0.5"),
            evidence_ref="test",
        )
    with pytest.raises(ValueError, match="non-negative"):
        TechnicalRecoveryRange(
            timeframe="1h",
            source="ROLLING_SUPPORT_RESISTANCE",
            support_price=Decimal("1"),
            resistance_price=Decimal("2"),
            range_move_ratio=Decimal("-0.1"),
            confidence=Decimal("0.5"),
            evidence_refs=("market_outlook:key_levels:1h",),
        )
    with pytest.raises(ValueError, match="queue ref is invalid"):
        RecoveryCandidate(
            candidate_id="recovery:HOTUSDT:test",
            symbol="HOTUSDT",
            proposal_kind=RecoveryProposalKind.VALIDATION_OPPORTUNITY_REVIEW,
            ladder_stage=RecoveryLadderStage.WATCHLIST,
            review_action="KEEP_ON_RECOVERY_WATCHLIST",
            rationale="test",
            source="test",
            timeframe="1h",
            setup_name="test_setup",
            score=Decimal("50"),
            confidence=Decimal("0.5"),
            blockers=("LIVE_ORDER_BLOCKED",),
            next_safe_actions=("RUN_VALIDATION_QUEUE",),
            evidence_refs=("test",),
            validation_queue_ref=" ",
        )

    tiny_range_blockers = _inventory_blockers(
        Decimal("0"),
        Decimal("100"),
        Decimal("101"),
        Decimal("100"),
        RecoveryRadarPolicy(minimum_range_move_ratio=Decimal("0.02")),
    )
    assert "RECOVERY_INVENTORY_UNAVAILABLE" in tiny_range_blockers
    assert "RECOVERY_RANGE_TOO_SMALL" in tiny_range_blockers
    assert "RECOVERY_COST_BASIS_UNVERIFIED" not in tiny_range_blockers

    partial_low, partial_high, partial_source, partial_blockers = _select_range(
        "0.00031",
        None,
        (
            TechnicalRecoveryRange(
                timeframe="15m",
                source="ROLLING_SUPPORT_RESISTANCE",
                support_price=Decimal("0.000331"),
                resistance_price=Decimal("0.000340"),
                range_move_ratio=Decimal("0.027190332326"),
                confidence=Decimal("0.35"),
                evidence_refs=("market_outlook:key_levels:15m",),
            ),
        ),
    )
    assert partial_low == Decimal("0.000331")
    assert partial_high == Decimal("0.000340")
    assert partial_source == "TECHNICAL_RANGE:15m:ROLLING_SUPPORT_RESISTANCE"
    assert partial_blockers == (
        "OPERATOR_RANGE_PARTIAL_IGNORED",
        "TECHNICAL_RANGE_NOT_EXECUTION_SIGNAL",
    )

    ranges = _technical_ranges_from_market_state(
        {
            "key_levels": (
                {
                    "kind": "SUPPORT",
                    "timeframe": "4h",
                    "zone": {"upper": "0"},
                },
                {
                    "kind": "RESISTANCE",
                    "timeframe": "4h",
                    "zone": {"lower": "10"},
                },
                {
                    "kind": "SUPPORT",
                    "timeframe": "1h",
                    "zone": {"upper": "10"},
                },
                {
                    "kind": "RESISTANCE",
                    "timeframe": "1h",
                    "zone": {"lower": "10"},
                },
            )
        },
        RecoveryRadarPolicy(),
    )
    assert ranges == ()

    assert _market_intelligence_blockers({}) == (
        "MSPACIS_EVIDENCE_INCOMPLETE",
        "RELATIVE_STRENGTH_EVIDENCE_MISSING",
        "DERIVATIVES_SUPPLEMENT_MISSING",
        "NEWS_WHALE_RISK_UNVERIFIED",
    )
    assert (
        _market_intelligence_blockers(
            {
                "market_structure": {"trend": "up"},
                "price_action": {"bias": "bullish"},
                "candlestick_intelligence": {"signal": "inside-bar"},
                "key_levels": ({"kind": "SUPPORT"},),
                "setups_on_radar": ({"setup_name": "retest"},),
                "relative_strength": {"HOTBTC": "STRONG"},
                "hot_btc_relative_strength": "STRONG",
                "hot_eth_relative_strength": "STRONG",
                "derivatives": {"funding": "NEUTRAL"},
                "funding": "NEUTRAL",
                "open_interest": "STABLE",
                "long_short_ratio": "BALANCED",
                "news": {"risk": "LOW"},
                "social": {"signal": "QUIET"},
                "whale": {"status": "CALM"},
                "onchain": {"flow": "STABLE"},
                "market_context_events": ("NONE",),
            }
        )
        == ()
    )
    assert _source_presence_score({}, ()) == Decimal("0")
    assert _has_context_value({}) is False
    assert _has_context_value([]) is False
    assert _has_context_value(" ") is False
    assert _has_context_value(0) is True
    assert _threshold_score(Decimal("1"), Decimal("0")) == Decimal("100")
    assert _intelligence_score(()) == Decimal("0")

    policy = RecoveryRadarPolicy(
        high_attention_score=Decimal("120"),
        action_candidate_score=Decimal("150"),
    )
    assert _opportunity_grade(Decimal("160"), policy) == "A_REVIEW"
    assert _opportunity_grade(Decimal("95"), policy) == "C_REVIEW"
    assert _miss_risk(Decimal("160"), (), policy) == "HIGH"
    assert _miss_risk(Decimal("130"), (), policy) == "MEDIUM_HIGH"
    assert (
        _miss_risk(
            Decimal("80"),
            ("TECHNICAL_TRIGGER_CONFIRMATION_REQUIRED",),
            policy,
        )
        == "MEDIUM"
    )
    assert _false_positive_risk(()) == "MEDIUM"

    market_state = {
        "market_regime": "TRENDING",
        "pro_trend_direction": "UP",
        "timeframe_biases": ({"timeframe": "1h", "confidence": "0.9"},),
        "setups_on_radar": (),
    }
    assert _technical_range_confidence(market_state, "1h") == Decimal("0.45")
    assert _technical_range_evidence_refs(market_state, "1h") == (
        "market_outlook:key_levels:1h",
        "technical:rolling_support_resistance",
        "market_outlook:market_regime",
        "market_outlook:pro_trend_direction",
        "market_outlook:timeframe_biases",
        "MSPACIS:pending_explicit_contract",
    )


def test_recovery_technical_helpers_cover_empty_context_and_setup_refs() -> None:
    assert _technical_range_confidence({}, "1h") == Decimal("0.20")
    assert _technical_range_confidence(
        {
            "setups_on_radar": ({"setup_name": "trend_continuation"},),
            "timeframe_biases": (),
        },
        "4h",
    ) == Decimal("0.30")
    assert _technical_range_evidence_refs({}, "4h") == (
        "market_outlook:key_levels:4h",
        "technical:rolling_support_resistance",
        "MSPACIS:pending_explicit_contract",
    )
    assert _technical_range_evidence_refs(
        {
            "setups_on_radar": ({"setup_name": "trend_continuation"},),
        },
        "4h",
    ) == (
        "market_outlook:key_levels:4h",
        "technical:rolling_support_resistance",
        "market_outlook:setups_on_radar",
        "MSPACIS:pending_explicit_contract",
    )


def test_recovery_radar_cli_reports_missing_inputs_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance.cli import main

    _settings(monkeypatch, tmp_path)

    assert main(["opportunity-recovery-radar", "--format", "json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert "RECOVERY_INPUT_REQUIRED:inventory_units" in payload["blockers"]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_recovery_radar_cli_text_is_user_friendly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance.cli import main
    from ai4binance.cli import status as status_module

    _settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        status_module,
        "opportunities_payload",
        lambda settings, symbol: _opportunities_payload(symbol),
    )

    exit_code = main(
        [
            "recovery-radar",
            "--symbol",
            "HOTUSDT",
            "--inventory-units",
            "18400000",
            "--range-low",
            "0.000312",
            "--range-high",
            "0.000390",
            "--format",
            "text",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Opportunity Recovery Radar: HOTUSDT" in output
    assert "HINDSIGHT_ENVELOPE_ONLY" in output
    assert "range_source: OPERATOR_RANGE" in output
    assert "iq=" in output
    assert "miss_risk=" in output
    assert "top_lenses=" in output
    assert "TRADE_CANDIDATE inventory_rotation_recovery" in output
    assert "LIVE_ORDER_BLOCKED" in output


def test_recovery_radar_cli_derives_technical_range_from_runtime_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance.cli import main

    settings = _settings(monkeypatch, tmp_path)
    market_root = settings.evidence_artifact_directory / "market-outlook"
    market_root.mkdir(parents=True)
    (market_root / "runtime-state.json").write_text(
        json.dumps(_technical_opportunities_payload("HOTUSDT")["market_state"]),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "candidate-ladder",
            "--symbol",
            "HOTUSDT",
            "--inventory-units",
            "18400000",
            "--format",
            "text",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "TECHNICAL_RANGE_ESTIMATE_NOT_SIGNAL" in output
    assert "range_source: TECHNICAL_RANGE:15m:ROLLING_SUPPORT_RESISTANCE" in output
    assert "technical_range_rotation" in output
    assert "top_lenses=support_resistance, range_amplitude, trend_regime" in output
    assert "TECHNICAL_TRIGGER_CONFIRMATION_REQUIRED" in output


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv(
        "AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY", str(tmp_path / "Validation")
    )
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    return Settings()


def _opportunities_payload(symbol: str | None) -> dict[str, object]:
    normalized = (symbol or "HOTUSDT").upper()
    return {
        "command": "opportunities",
        "status": "ACTIVE",
        "inbox": {
            "symbol": normalized,
            "items": (
                {
                    "market": "SPOT",
                    "symbol": normalized,
                    "setup_name": "breakout_retest",
                    "timeframe": "1d",
                    "direction": "UNKNOWN",
                    "source": "validation_summary",
                    "status": "WATCHLIST",
                    "promotion_status": "RESEARCH_ONLY",
                    "score": "0.000006",
                    "confidence": "1",
                    "blockers": (
                        "LOW_OOS_TRADE_COUNT",
                        "OOS_EDGE_CONCENTRATION",
                        "UNSTABLE_PARAMETER_SENSITIVITY",
                        "EXECUTION_NOT_ALLOWED",
                    ),
                },
            ),
        },
        "blockers": (
            "TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",
            "OOS_APPROVAL_MISSING",
            "RISK_APPROVAL_MISSING",
        ),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _technical_opportunities_payload(symbol: str | None) -> dict[str, object]:
    payload = _opportunities_payload(symbol)
    payload["market_state"] = {
        "symbol": (symbol or "HOTUSDT").upper(),
        "market_regime": "RANGE",
        "pro_trend_direction": "BEARISH",
        "timeframe_biases": (
            {"timeframe": "15m", "direction": "NEUTRAL", "confidence": "0.18"},
            {"timeframe": "1h", "direction": "NEUTRAL", "confidence": "0.10"},
        ),
        "setups_on_radar": (
            {
                "setup_name": "trend_continuation",
                "timeframe": "1h",
                "direction": "BEARISH",
                "score": "66",
                "confidence": "0.45",
                "blockers": ("ENTRY_TRIGGER_MISSING",),
            },
        ),
        "relative_strength": {"HOTBTC": "WEAK", "HOTETH": "WEAK"},
        "derivatives": {"funding": "NEUTRAL", "open_interest": "UNKNOWN"},
        "news": {"risk": "UNVERIFIED"},
        "whale": {"status": "UNVERIFIED"},
        "key_levels": (
            {
                "kind": "SUPPORT",
                "source": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe": "1h",
                "zone": {"lower": "0.000328", "upper": "0.000329"},
            },
            {
                "kind": "RESISTANCE",
                "source": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe": "1h",
                "zone": {"lower": "0.000367", "upper": "0.000368"},
            },
            {
                "kind": "SUPPORT",
                "source": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe": "15m",
                "zone": {"lower": "0.000330", "upper": "0.000331"},
            },
            {
                "kind": "RESISTANCE",
                "source": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe": "15m",
                "zone": {"lower": "0.000340", "upper": "0.000341"},
            },
            {
                "kind": "SUPPORT",
                "source": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe": "4h",
                "zone": {"lower": "0.000312", "upper": "0.000313"},
            },
            {
                "kind": "RESISTANCE",
                "source": "ROLLING_SUPPORT_RESISTANCE",
                "timeframe": "4h",
                "zone": {"lower": "0.000390", "upper": "0.000391"},
            },
        ),
    }
    return payload

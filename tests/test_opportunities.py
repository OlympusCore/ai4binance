"""Research-only opportunity observation tests."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.domain import Action, SetupTier
from ai4binance.opportunities import (
    OpportunityBias,
    OpportunityInbox,
    OpportunityInboxBuilder,
    OpportunityInboxItem,
    VWAPOpportunity,
    VWAPOpportunityConfig,
    VWAPOpportunityEvaluator,
    _next_safe_actions,
)
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle, PromotionStatus
from ai4binance.validation.summary import ValidationSummary, ValidationSummaryReader

START = datetime(2026, 7, 11, tzinfo=UTC)


def snapshot(*, bearish: bool = False, latest_volume: str = "1000") -> MarketSnapshot:
    rows: list[OHLCVCandle] = []
    for index in range(21):
        close = Decimal("100")
        volume = Decimal("100")
        if index == 19:
            close = Decimal("101") if bearish else Decimal("99")
        if index == 20:
            close = Decimal("98") if bearish else Decimal("102")
            volume = Decimal(latest_volume)
        rows.append(
            OHLCVCandle(
                timestamp=START + timedelta(minutes=15 * index),
                open=Decimal("100"),
                high=max(Decimal("103"), close),
                low=min(Decimal("97"), close),
                close=close,
                volume=volume,
            )
        )
    return MarketSnapshot(
        snapshot_id="vwap-snapshot",
        created_at=rows[-1].timestamp,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": tuple(rows)},
        latest_price=rows[-1].close,
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_VALID,
    )


def evaluate(
    market: MarketSnapshot,
    *,
    structure_aligned: bool = True,
    htf_aligned: bool = True,
    inventory_available: bool = False,
) -> VWAPOpportunity:
    return VWAPOpportunityEvaluator().evaluate(
        market,
        timeframe="15m",
        session_start=START,
        structure_aligned=structure_aligned,
        htf_aligned=htf_aligned,
        inventory_available=inventory_available,
    )


def test_confirmed_bullish_reclaim_is_still_research_only() -> None:
    result = evaluate(snapshot())
    assert result.bias is OpportunityBias.BULLISH
    assert result.action is Action.BUY
    assert result.setup_tier is SetupTier.B
    assert result.blockers == ()
    assert result.promotion_status is PromotionStatus.RESEARCH_ONLY
    assert result.execution_allowed is False


def test_confirmation_failures_force_no_trade() -> None:
    result = evaluate(
        snapshot(latest_volume="100"),
        structure_aligned=False,
        htf_aligned=False,
    )
    assert result.action is Action.NO_TRADE
    assert "VOLUME_CONFIRMATION_MISSING" in result.blockers
    assert "STRUCTURE_CONFIRMATION_REQUIRED" in result.blockers
    assert "HTF_CONFIRMATION_REQUIRED" in result.blockers


def test_spot_sell_requires_inventory() -> None:
    blocked = evaluate(snapshot(bearish=True))
    allowed_observation = evaluate(snapshot(bearish=True), inventory_available=True)
    assert blocked.action is Action.NO_TRADE
    assert "SPOT_INVENTORY_REQUIRED_FOR_SELL" in blocked.blockers
    assert allowed_observation.action is Action.SELL
    assert allowed_observation.execution_allowed is False


def test_insufficient_session_data_fails_closed() -> None:
    result = VWAPOpportunityEvaluator().evaluate(
        snapshot(),
        timeframe="15m",
        session_start=START + timedelta(hours=4),
        structure_aligned=True,
        htf_aligned=True,
    )
    assert result.action is Action.NO_TRADE
    assert result.blockers == ("INSUFFICIENT_SESSION_DATA",)


def test_config_and_session_boundary_validation() -> None:
    with pytest.raises(ValueError, match="positive"):
        VWAPOpportunityConfig(atr_period=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        VWAPOpportunityEvaluator().evaluate(
            snapshot(),
            timeframe="15m",
            session_start=datetime(2026, 7, 11),
            structure_aligned=True,
            htf_aligned=True,
        )


def test_opportunity_inbox_keeps_research_loop_enabled() -> None:
    summary = ValidationSummary(
        symbol="HOTUSDT",
        artifact_directory="Backtest/validation",
        run_count=0,
        staged_candidate_count=0,
        research_only_count=0,
        top_blockers=(),
        runs=(),
        blockers=(),
    )
    item = OpportunityInboxItem(
        market="SPOT",
        symbol="HOTUSDT",
        setup_name="breakout_retest",
        timeframe="1h",
        direction="BULLISH",
        source="market_outlook",
        status="READY",
        promotion_status="STAGED_CANDIDATE",
        score=70.0,
        confidence=0.7,
        blockers=(),
    )

    inbox = OpportunityInbox(
        symbol="HOTUSDT",
        items=(item,),
        validation_summary=summary,
        blockers=(),
        generation_status="ACTIVE",
    )

    assert inbox.research_loop_allowed is True
    assert inbox.opportunity_generation_allowed is True
    assert inbox.execution_allowed is False
    assert inbox.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="generation status"):
        OpportunityInbox("HOTUSDT", (), summary, (), generation_status="PAUSED")
    with pytest.raises(ValueError, match="research generation"):
        OpportunityInbox(
            "HOTUSDT",
            (),
            summary,
            (),
            research_loop_allowed=False,
        )
    with pytest.raises(ValueError, match="execution authority"):
        OpportunityInbox("HOTUSDT", (), summary, (), execution_allowed=True)


def test_opportunity_inbox_degrades_without_any_evidence(tmp_path: Path) -> None:
    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(tmp_path / "missing-validation"),
        tmp_path / "missing-market-outlook.json",
    ).build("HOTUSDT")

    assert inbox.generation_status == "DEGRADED"
    assert inbox.items == ()
    assert inbox.research_blockers == (
        "MARKET_OUTLOOK_UNAVAILABLE",
        "NO_VISIBLE_OPPORTUNITY_EVIDENCE",
    )
    assert "VALIDATION_ARTIFACTS_UNAVAILABLE" in inbox.execution_blockers
    assert "NO_READY_CANDIDATE" in inbox.execution_blockers
    assert "RUN_ANALYZE_PUBLIC" in inbox.next_safe_actions
    assert "RUN_VALIDATION_QUEUE" in inbox.next_safe_actions


def test_opportunity_inbox_maps_structured_market_setups(tmp_path: Path) -> None:
    outlook = tmp_path / "runtime-state.json"
    outlook.write_text(
        json.dumps(
            {
                "blockers": ["ORDER_BOOK_DEPTH_MISSING"],
                "setups_on_radar": [
                    {
                        "setup_name": "support_reclaim",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "status": "WAIT_FOR_RETEST",
                        "promotion_status": "RESEARCH_ONLY",
                        "score": 62.5,
                        "confidence": 0.55,
                        "blockers": ["ENTRY_TRIGGER_MISSING"],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(tmp_path / "missing-validation"),
        outlook,
    ).build("HOTUSDT")

    assert inbox.generation_status == "ACTIVE"
    assert inbox.items[0].setup_name == "support_reclaim"
    assert inbox.items[0].score == 62.5
    assert "ENTRY_TRIGGER_MISSING" in inbox.items[0].blockers
    assert "VALIDATION_GATE_REQUIRED" in inbox.items[0].blockers
    assert "REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE" in inbox.next_safe_actions


def test_safe_opportunity_actions_are_deduplicated_and_specific() -> None:
    actions = _next_safe_actions(
        (
            "MARKET_OUTLOOK_UNAVAILABLE",
            "BACKTEST_APPROVAL_MISSING",
            "NO_READY_CANDIDATE",
            "ORDER_BOOK_DEPTH_MISSING",
            "WHALE_FUSION_SNAPSHOT_MISSING",
            "EXTERNAL_EVIDENCE_MISSING_OR_UNSOURCED",
            "DEPENDENCY_NOT_READY:derivatives",
            "TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",
            "RISK_APPROVAL_MISSING",
            "HIGH_IMPACT_DATA_UNAVAILABLE",
            "MACRO_CYCLE_EVIDENCE_UNAVAILABLE",
            "TPO_AUCTION_PROFILE_NOT_IMPLEMENTED",
            "UNKNOWN_BLOCKER",
            "BACKTEST_APPROVAL_MISSING",
        )
    )

    assert actions == (
        "RUN_ANALYZE_PUBLIC",
        "RUN_VALIDATION_QUEUE",
        "KEEP_WATCHLIST_AND_WAIT_FOR_READY_SETUP",
        "REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE",
        "RUN_WHALE_FUSION_RESEARCH",
        "COLLECT_SOURCED_EXTERNAL_EVIDENCE",
        "REFRESH_DERIVATIVES_RESEARCH",
        "BUILD_CANDIDATE_RISK_PLAN",
        "PREPARE_RISK_REVIEW",
        "COLLECT_HIGH_IMPACT_EVENT_CONTEXT",
        "REFRESH_MACRO_CYCLE_CONTEXT",
        "STAGE_MARKET_PROFILE_RESEARCH",
        "REVIEW_BLOCKER:UNKNOWN_BLOCKER",
    )
    assert _next_safe_actions(()) == ("KEEP_RESEARCH_RADAR_RUNNING",)

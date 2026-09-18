"""Research-only opportunity observation tests."""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai4binance.cli.opportunity_radar_persistence import (
    write_opportunity_radar_snapshot,
)
from ai4binance.domain import Action, SetupTier
from ai4binance.domain.opportunity_observation import (
    OpportunityBias,
    OpportunityLifecycleState,
    VWAPOpportunity,
    VWAPOpportunityConfig,
)
from ai4binance.opportunities import (
    OpportunityInbox,
    OpportunityInboxBuilder,
    OpportunityInboxItem,
    _deduplicate_items,
    _float_0_1,
    _float_0_100,
    _funnel_counts,
    _market_item,
    _market_lifecycle_state,
    _market_state_symbol,
    _next_safe_actions,
    _object_tuple,
    _pattern_type_value,
    _positive_decimal,
    _radar_item,
    _safe_action_for_blocker,
    _text_tuple,
    _validation_lifecycle_state,
    _validation_opportunity_score,
    _validation_promotion_requirements,
)
from ai4binance.opportunity_radar import (
    OpportunityRadarCandidate,
    OpportunityRadarSnapshot,
    VWAPOpportunityEvaluator,
    _direction,
    _trade_plan,
    _trend_aligned,
    _vwap_lifecycle_state,
    build_opportunity_radar_snapshot,
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
    assert result.lifecycle_state is OpportunityLifecycleState.WATCH_ONLY
    assert result.promotion_status == PromotionStatus.RESEARCH_ONLY
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
    assert result.lifecycle_state is OpportunityLifecycleState.CONFIRMATION_PENDING


def test_spot_sell_requires_inventory() -> None:
    blocked = evaluate(snapshot(bearish=True))
    allowed_observation = evaluate(snapshot(bearish=True), inventory_available=True)
    assert blocked.action is Action.NO_TRADE
    assert "SPOT_INVENTORY_REQUIRED_FOR_SELL" in blocked.blockers
    assert blocked.lifecycle_state is OpportunityLifecycleState.WATCH_ONLY
    assert allowed_observation.action is Action.SELL
    assert allowed_observation.execution_allowed is False


def test_vwap_evaluator_surfaces_negative_and_degraded_paths() -> None:
    neutral_rows = tuple(
        OHLCVCandle(
            timestamp=START + timedelta(minutes=15 * index),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("100"),
        )
        for index in range(21)
    )
    neutral_snapshot = MarketSnapshot(
        snapshot_id="neutral-vwap",
        created_at=neutral_rows[-1].timestamp,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": neutral_rows},
        latest_price=Decimal("100"),
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_INVALID,
    )
    neutral = VWAPOpportunityEvaluator().evaluate(
        neutral_snapshot,
        timeframe="15m",
        session_start=START,
        structure_aligned=True,
        htf_aligned=True,
    )

    assert "DATA_NOT_VALID" in neutral.blockers
    assert "VWAP_TRIGGER_MISSING" in neutral.blockers
    assert "VWAP_OVEREXTENDED" in neutral.blockers

    choppy_rows = []
    for index in range(21):
        close = Decimal("99") if index % 2 == 0 else Decimal("101")
        volume = Decimal("100")
        if index == 20:
            close = Decimal("102")
            volume = Decimal("1000")
        choppy_rows.append(
            OHLCVCandle(
                timestamp=START + timedelta(minutes=15 * index),
                open=Decimal("100"),
                high=Decimal("103"),
                low=Decimal("97"),
                close=close,
                volume=volume,
            )
        )
    choppy_snapshot = MarketSnapshot(
        snapshot_id="choppy-vwap",
        created_at=choppy_rows[-1].timestamp,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": tuple(choppy_rows)},
        latest_price=Decimal("102"),
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_VALID,
    )
    choppy = VWAPOpportunityEvaluator().evaluate(
        choppy_snapshot,
        timeframe="15m",
        session_start=START,
        structure_aligned=True,
        htf_aligned=True,
    )

    assert "VWAP_CHOP_DETECTED" in choppy.blockers
    assert choppy.action is Action.NO_TRADE


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
    assert result.lifecycle_state is OpportunityLifecycleState.WATCH_ONLY


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
        artifact_directory="runtime/artifacts/research/backtest/validation",
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
    assert item.lifecycle_state is OpportunityLifecycleState.WATCH_ONLY
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


def test_opportunity_lifecycle_contract_allows_paper_visibility_without_execution() -> (
    None
):
    values = tuple(state.value for state in OpportunityLifecycleState)
    assert values == (
        "NEW",
        "DISCOVERED",
        "WATCH_ONLY",
        "SETUP_FORMING",
        "DEVELOPING",
        "CONFIRMATION_PENDING",
        "RESEARCH_CANDIDATE",
        "QUALIFIED",
        "CONFIRMED",
        "VALIDATION_PENDING",
        "PAPER_ELIGIBLE",
        "VIRTUAL_ELIGIBLE",
        "BLOCKED",
        "REJECTED",
        "INVALIDATED",
        "EXPIRED",
        "CLOSED",
    )

    item = OpportunityInboxItem(
        market="SPOT",
        symbol="HOTUSDT",
        setup_name="breakout_retest",
        timeframe="1h",
        direction="BULLISH",
        source="validation_summary",
        status="READY",
        promotion_status="STAGED_CANDIDATE",
        score=72.0,
        confidence=0.7,
        blockers=(),
        lifecycle_state="PAPER_ELIGIBLE",
    )

    assert item.lifecycle_state is OpportunityLifecycleState.PAPER_ELIGIBLE
    assert item.execution_allowed is False
    assert item.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_lifecycle_rejects_unsafe_paper_eligible_states() -> None:
    with pytest.raises(ValueError, match="cannot contain blockers"):
        paper_eligible_item(blockers=("OOS_APPROVAL_MISSING",))
    with pytest.raises(ValueError, match="requires staged validation evidence"):
        paper_eligible_item(promotion_status="RESEARCH_ONLY")
    with pytest.raises(ValueError, match="requires ready status"):
        paper_eligible_item(status="WATCHLIST")
    with pytest.raises(ValueError, match="lifecycle state"):
        paper_eligible_item(lifecycle_state="TRADE_NOW")


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"target_risk_reward": Decimal("0")}, "target risk/reward must be positive"),
        (
            {"stretch_risk_reward": Decimal("1.5")},
            "stretch risk/reward cannot be below target",
        ),
        ({"pattern_type": " "}, "pattern_type cannot be blank"),
        ({"score": float("nan")}, "opportunity score must be 0..100"),
        ({"score": 101.0}, "opportunity score must be 0..100"),
        ({"confidence": float("nan")}, "opportunity confidence must be 0..1"),
        ({"confidence": 1.5}, "opportunity confidence must be 0..1"),
        ({"score_basis": " "}, "opportunity score basis is required"),
        (
            {"next_evidence_action": " "},
            "opportunity next evidence action is required",
        ),
        ({"entry": " "}, "opportunity trade plan fields are required"),
        (
            {"expected_return": float("inf")},
            "opportunity expected return must be finite",
        ),
        (
            {"score_components": ((" ", 1.0),)},
            "opportunity score component name is required",
        ),
        (
            {"score_components": (("component", 101.0),)},
            "opportunity score components must be 0..100",
        ),
        (
            {"why_now": ("WHY_NOW", "WHY_NOW")},
            "opportunity evidence and gate lists must be unique",
        ),
        (
            {"blockers": ("OOS_APPROVAL_MISSING",)},
            "PAPER_ELIGIBLE opportunity cannot contain blockers",
        ),
        (
            {"promotion_status": "RESEARCH_ONLY"},
            "PAPER_ELIGIBLE opportunity requires staged validation evidence",
        ),
        (
            {"status": "WATCHLIST"},
            "PAPER_ELIGIBLE opportunity requires ready status",
        ),
        (
            {"execution_allowed": True},
            "opportunity inbox item cannot grant execution authority",
        ),
        (
            {"live_eligibility_status": "PENDING"},
            "opportunity inbox item cannot grant execution authority",
        ),
        ({"lifecycle_state": "TRADE_NOW"}, "opportunity lifecycle state is invalid"),
    ],
)
def test_opportunity_inbox_item_rejects_invalid_contract_variants(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(paper_eligible_item(), **cast(dict[str, Any], updates))


def test_opportunity_inbox_helpers_cover_remaining_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _object_tuple((1, 2)) == (1, 2)
    assert _object_tuple([1, 2]) == (1, 2)
    assert _object_tuple("ignored") == ()
    assert _text_tuple("  hello ") == ("hello",)
    assert _text_tuple(("a", " ", "b")) == ("a", "b")
    assert _float_0_100("bad") == 0.0
    assert _float_0_100("101") == 100.0
    assert _float_0_100("inf") == 0.0
    assert _float_0_1("bad") == 0.0
    assert _float_0_1("2") == 1.0
    assert _float_0_1("inf") == 0.0
    assert _positive_decimal("bad", default=Decimal("7")) == Decimal("7")
    assert _positive_decimal("0", default=Decimal("7")) == Decimal("7")
    assert _positive_decimal("2.5", default=Decimal("7")) == Decimal("2.5")
    assert _pattern_type_value("", fallback_setup_name="support_reclaim") == (
        "REVERSAL_PATTERN"
    )
    assert _validation_opportunity_score(()) == 0.0

    implemented_run = SimpleNamespace(
        promotion_status="STAGED_CANDIDATE",
        metrics=(),
    )
    blocked_run = SimpleNamespace(
        promotion_status="STAGED_CANDIDATE",
        metrics=(),
    )
    staged_requirements = _validation_promotion_requirements(implemented_run, ())
    deferred_requirements = _validation_promotion_requirements(
        SimpleNamespace(promotion_status="RESEARCH_ONLY"),
        (),
    )

    assert staged_requirements == ()
    assert deferred_requirements == ("VALIDATION_GATE_REQUIRED",)
    assert (
        _validation_lifecycle_state("support_reclaim", implemented_run, ())
        is OpportunityLifecycleState.PAPER_ELIGIBLE
    )
    assert (
        _validation_lifecycle_state(
            "support_reclaim",
            blocked_run,
            ("ENTRY_TRIGGER_MISSING",),
        )
        is OpportunityLifecycleState.CONFIRMATION_PENDING
    )
    assert (
        _validation_lifecycle_state("harmonic_reversal", implemented_run, ())
        is OpportunityLifecycleState.WATCH_ONLY
    )
    assert (
        _validation_lifecycle_state(
            "support_reclaim",
            SimpleNamespace(promotion_status="RESEARCH_ONLY", metrics=()),
            (),
        )
        is OpportunityLifecycleState.WATCH_ONLY
    )
    assert (
        _market_lifecycle_state(
            {"lifecycle_state": "SETUP_FORMING"},
            (),
            "WAIT_FOR_RETEST",
        )
        is OpportunityLifecycleState.SETUP_FORMING
    )
    assert (
        _market_lifecycle_state({}, ("ENTRY_TRIGGER_MISSING",), "PARTIAL")
        is OpportunityLifecycleState.CONFIRMATION_PENDING
    )
    assert (
        _market_lifecycle_state({}, (), "WAIT_FOR_RETEST")
        is OpportunityLifecycleState.CONFIRMATION_PENDING
    )
    assert (
        _market_lifecycle_state({}, (), "SETUP_FORMING")
        is OpportunityLifecycleState.SETUP_FORMING
    )
    assert (
        _market_lifecycle_state({}, (), "OTHER") is OpportunityLifecycleState.WATCH_ONLY
    )
    assert (
        _safe_action_for_blocker("MARKET_OUTLOOK_SYMBOL_MISMATCH:BTCUSDT!=ETHUSDT")
        == "RUN_SYMBOL_SCOPED_ANALYZE_PUBLIC"
    )
    assert _market_state_symbol({"symbol": "ALL"}) == ""
    assert _market_state_symbol({"symbol": "MARKET_WIDE"}) == ""
    assert (
        _market_item(
            "HOTUSDT",
            "support_reclaim",
            (),
            "UNKNOWN",
            "PARTIAL",
        ).promotion_status
        == "RESEARCH_ONLY"
    )
    assert (
        _market_item(
            "HOTUSDT",
            {
                "setup_name": "support_reclaim",
                "timeframe": "1h",
                "direction": "BULLISH",
                "status": "WATCHLIST",
                "promotion_status": "RESEARCH_ONLY",
                "score": 61.0,
                "confidence": 0.61,
            },
            (),
            "UNKNOWN",
            "PARTIAL",
        ).pattern_type
        == "REVERSAL_PATTERN"
    )

    radar_item = _radar_item(
        {
            "symbol": "hotusdt",
            "setup_name": "support_reclaim",
            "pattern_type": "",
            "timeframe": "1h",
            "direction": "BULLISH",
            "status": "WATCHLIST",
            "promotion_status": "RESEARCH_ONLY",
            "score": "nan",
            "confidence": "2",
            "blockers": ["ENTRY_TRIGGER_MISSING"],
            "confirmation_requirements": ["ENTRY_TRIGGER_MISSING"],
            "promotion_requirements": ["OOS_APPROVAL_MISSING"],
            "execution_blockers": ["RISK_APPROVAL_MISSING"],
            "target_risk_reward": "0",
        }
    )
    assert radar_item.pattern_type == "REVERSAL_PATTERN"
    assert radar_item.score == 0.0
    assert radar_item.confidence == 1.0
    assert radar_item.target_risk_reward == Decimal("2")
    assert radar_item.next_evidence_action == "REVIEW_BLOCKER:ENTRY_TRIGGER_MISSING"
    assert _next_safe_actions(()) == ("KEEP_RESEARCH_RADAR_RUNNING",)

    monkeypatch.setattr(
        "ai4binance.opportunities._safe_action_for_blocker", lambda _: ""
    )
    assert _next_safe_actions(("BLOCKER_WITH_NO_ACTION",)) == (
        "KEEP_RESEARCH_RADAR_RUNNING",
    )

    builder = OpportunityInboxBuilder(
        ValidationSummaryReader(tmp_path / "missing-validation"),
        tmp_path / "missing-market-outlook.json",
        max_items=1,
    )
    with pytest.raises(ValueError, match="positive"):
        OpportunityInboxBuilder(
            ValidationSummaryReader(tmp_path / "missing-validation"),
            tmp_path / "missing-market-outlook.json",
            max_items=0,
        )
    with pytest.raises(ValueError, match="symbol is required"):
        OpportunityInbox(
            symbol=" ",
            items=(),
            validation_summary=ValidationSummary(
                symbol="HOTUSDT",
                artifact_directory="runtime/artifacts/research/backtest/validation",
                run_count=0,
                staged_candidate_count=0,
                research_only_count=0,
                top_blockers=(),
                runs=(),
                blockers=(),
            ),
            blockers=(),
        )
    with pytest.raises(ValueError, match="symbol is required"):
        OpportunityInboxItem(
            market="SPOT",
            symbol=" ",
            setup_name="support_reclaim",
            timeframe="1h",
            direction="BULLISH",
            source="market_outlook",
            status="WATCHLIST",
            promotion_status="RESEARCH_ONLY",
            score=0.0,
            confidence=0.0,
            blockers=(),
        )

    market_wide_state = {
        "candidate_states": [
            "ignored",
            {"symbol": ""},
            {"symbol": "ETHUSDT"},
            {
                "symbol": "HOTUSDT",
                "setup_name": "support_reclaim",
                "timeframe": "1h",
                "direction": "BULLISH",
                "status": "WATCHLIST",
                "promotion_status": "RESEARCH_ONLY",
                "score": 61.0,
                "confidence": 0.61,
            },
        ]
    }
    filtered = builder._radar_items("HOTUSDT", market_wide_state)
    assert len(filtered) == 1
    assert filtered[0].symbol == "HOTUSDT"
    assert builder._radar_items("MARKET_WIDE", market_wide_state)[0].symbol == "ETHUSDT"
    assert builder._market_items("HOTUSDT", {"setups_on_radar": []}) == ()
    symbol_mismatch_outlook = tmp_path / "symbol-mismatch.json"
    symbol_mismatch_outlook.write_text(
        json.dumps(
            {
                "symbol": "ETHUSDT",
                "status": "PARTIAL",
                "setups_on_radar": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    mismatch_inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(tmp_path / "missing-validation"),
        symbol_mismatch_outlook,
    ).build("HOTUSDT")
    assert mismatch_inbox.research_blockers == (
        "MARKET_OUTLOOK_SYMBOL_MISMATCH:ETHUSDT!=HOTUSDT",
        "NO_VISIBLE_OPPORTUNITY_EVIDENCE",
    )
    assert "MARKET_OUTLOOK_SYMBOL_MISMATCH:ETHUSDT!=HOTUSDT" in (
        mismatch_inbox.execution_blockers
    )


def test_opportunity_dedup_and_funnel_counts_cover_rank_and_lifecycle_branches() -> (
    None
):
    lower_rank = replace(
        paper_eligible_item(),
        source="opportunity_radar_snapshot",
        score=70.0,
        confidence=0.7,
        semantic_key="SPOT:HOTUSDT:1H:support_reclaim:BULLISH",
    )
    higher_rank = replace(
        lower_rank,
        source="validation_summary",
        score=80.0,
        confidence=0.8,
    )

    deduplicated = _deduplicate_items((lower_rank, higher_rank))
    assert deduplicated == (higher_rank,)

    items = (
        replace(paper_eligible_item(), score=95.0),
        replace(
            paper_eligible_item(),
            blockers=("ENTRY_TRIGGER_MISSING",),
            promotion_status="RESEARCH_ONLY",
            status="WATCHLIST",
            lifecycle_state=OpportunityLifecycleState.CONFIRMATION_PENDING,
        ),
        replace(
            paper_eligible_item(),
            blockers=(),
            promotion_status="RESEARCH_ONLY",
            status="WATCHLIST",
            lifecycle_state=OpportunityLifecycleState.SETUP_FORMING,
            score=60.0,
        ),
    )

    counts = dict(_funnel_counts(items))
    assert counts["visible_count"] == 3
    assert counts["paper_eligible_count"] == 1
    assert counts["confirmation_pending_count"] == 1
    assert counts["setup_forming_count"] == 1
    assert counts["blocked_visible_count"] == 1
    assert _funnel_counts(
        (
            replace(
                paper_eligible_item(),
                lifecycle_state=OpportunityLifecycleState.INVALIDATED,
                status="WATCHLIST",
                promotion_status="RESEARCH_ONLY",
                blockers=(),
            ),
        )
    )[0] == ("visible_count", 1)

    lower_rank = replace(
        paper_eligible_item(),
        source="opportunity_radar_snapshot",
        score=70.0,
        confidence=0.7,
        semantic_key="SPOT:HOTUSDT:1H:support_reclaim:BULLISH",
    )
    higher_rank = replace(
        lower_rank,
        source="validation_summary",
        score=80.0,
        confidence=0.8,
    )
    assert _deduplicate_items((higher_rank, lower_rank)) == (higher_rank,)


def paper_eligible_item(
    *,
    blockers: tuple[str, ...] = (),
    promotion_status: str = "STAGED_CANDIDATE",
    status: str = "READY",
    lifecycle_state: OpportunityLifecycleState | str = (
        OpportunityLifecycleState.PAPER_ELIGIBLE
    ),
) -> OpportunityInboxItem:
    return OpportunityInboxItem(
        market="SPOT",
        symbol="HOTUSDT",
        setup_name="breakout_retest",
        timeframe="1h",
        direction="BULLISH",
        source="validation_summary",
        status=status,
        promotion_status=promotion_status,
        score=72.0,
        confidence=0.7,
        blockers=blockers,
        lifecycle_state=lifecycle_state,
    )


def test_degraded_inbox_cannot_contain_paper_eligible_item() -> None:
    summary = ValidationSummary(
        symbol="HOTUSDT",
        artifact_directory="runtime/artifacts/research/backtest/validation",
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
        source="validation_summary",
        status="READY",
        promotion_status="STAGED_CANDIDATE",
        score=72.0,
        confidence=0.7,
        blockers=(),
        lifecycle_state=OpportunityLifecycleState.PAPER_ELIGIBLE,
    )

    with pytest.raises(ValueError, match="degraded opportunity inbox"):
        OpportunityInbox(
            symbol="HOTUSDT",
            items=(item,),
            validation_summary=summary,
            blockers=(),
            generation_status="DEGRADED",
        )


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
    assert inbox.items[0].pattern_type == "REVERSAL_PATTERN"
    assert inbox.items[0].score == 62.5
    assert (
        inbox.items[0].lifecycle_state is OpportunityLifecycleState.CONFIRMATION_PENDING
    )
    assert "ENTRY_TRIGGER_MISSING" in inbox.items[0].blockers
    assert "VALIDATION_GATE_REQUIRED" in inbox.items[0].promotion_requirements
    assert "VALIDATION_GATE_REQUIRED" not in inbox.items[0].blockers
    assert "REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE" in inbox.next_safe_actions


def test_market_setup_cannot_claim_paper_eligible_without_validation(
    tmp_path: Path,
) -> None:
    outlook = tmp_path / "runtime-state.json"
    outlook.write_text(
        json.dumps(
            {
                "blockers": [],
                "setups_on_radar": [
                    {
                        "setup_name": "breakout_retest",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "status": "READY",
                        "promotion_status": "STAGED_CANDIDATE",
                        "score": 72.0,
                        "confidence": 0.7,
                        "blockers": [],
                        "lifecycle_state": "PAPER_ELIGIBLE",
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

    assert inbox.items[0].lifecycle_state is OpportunityLifecycleState.WATCH_ONLY
    assert "VALIDATION_GATE_REQUIRED" in inbox.items[0].promotion_requirements
    assert "VALIDATION_GATE_REQUIRED" not in inbox.items[0].blockers
    assert "VALIDATION_ARTIFACTS_UNAVAILABLE" in inbox.execution_blockers


def test_validation_net_return_is_not_used_as_opportunity_score(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    _write_run_card(
        validation_root,
        blockers=(),
        metrics=(
            ("net_return", 0.18),
            ("bootstrap_probability_of_loss", 0.25),
        ),
        promotion_status="STAGED_CANDIDATE",
        playbook="support_reclaim",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(validation_root),
        tmp_path / "missing-market-outlook.json",
    ).build("HOTUSDT")

    item = inbox.items[0]
    assert item.lifecycle_state is OpportunityLifecycleState.PAPER_ELIGIBLE
    assert item.promotion_status == "STAGED_CANDIDATE"
    assert item.score_basis == "VALIDATION_EVIDENCE_QUALITY_SCORE_0_100"
    assert item.score == 83.75
    assert item.score != 0.18
    assert item.expected_return == 0.18
    assert "EXECUTION_NOT_ALLOWED" not in item.blockers
    assert item.execution_allowed is False
    assert item.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert ("paper_eligible_count", 1) in inbox.funnel_counts
    assert ("b_plus_count", 1) in inbox.funnel_counts
    assert ("b_count", 0) in inbox.funnel_counts


def test_implemented_playbook_with_missing_evidence_stays_research_only(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    _write_run_card(
        validation_root,
        blockers=("ENTRY_TRIGGER_MISSING",),
        metrics=(("bootstrap_probability_of_loss", 0.25),),
        promotion_status="STAGED_CANDIDATE",
        playbook="support_reclaim",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(validation_root),
        tmp_path / "missing-market-outlook.json",
    ).build("HOTUSDT")

    item = inbox.items[0]
    assert item.setup_name == "support_reclaim"
    assert item.promotion_status == "RESEARCH_ONLY"
    assert item.lifecycle_state is OpportunityLifecycleState.CONFIRMATION_PENDING
    assert "ENTRY_TRIGGER_MISSING" in item.blockers


def test_unimplemented_playbook_remains_watch_only(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    _write_run_card(
        validation_root,
        blockers=(),
        metrics=(("bootstrap_probability_of_loss", 0.25),),
        promotion_status="STAGED_CANDIDATE",
        playbook="harmonic_reversal",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(validation_root),
        tmp_path / "missing-market-outlook.json",
    ).build("HOTUSDT")

    item = inbox.items[0]
    assert item.setup_name == "harmonic_reversal"
    assert item.promotion_status == "RESEARCH_ONLY"
    assert item.lifecycle_state is OpportunityLifecycleState.WATCH_ONLY
    assert item.status == "WATCHLIST"


def test_opportunity_inbox_deduplicates_semantic_candidates(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    _write_run_card(
        validation_root,
        blockers=(),
        metrics=(("bootstrap_probability_of_loss", 0.25),),
        promotion_status="STAGED_CANDIDATE",
        playbook="support_reclaim",
    )
    outlook = tmp_path / "runtime-state.json"
    outlook.write_text(
        json.dumps(
            {
                "setups_on_radar": [
                    {
                        "setup_name": "support_reclaim",
                        "timeframe": "1h",
                        "direction": "UNKNOWN",
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
        ValidationSummaryReader(validation_root),
        outlook,
    ).build("HOTUSDT")

    assert len(inbox.items) == 1
    assert inbox.items[0].source == "validation_summary"
    assert inbox.items[0].setup_name == "support_reclaim"
    assert inbox.items[0].semantic_key == "SPOT:HOTUSDT:1H:support_reclaim:UNKNOWN"
    assert ("visible_count", 1) in inbox.funnel_counts


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
        "PLAN_NEXT_EVIDENCE_REFRESH",
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


def test_canonical_radar_snapshot_builds_setup_evidence_without_live_authority(
    tmp_path: Path,
) -> None:
    radar = build_opportunity_radar_snapshot(
        (_multi_timeframe_snapshot(),),
        cycle_id="cycle-1",
        observed_at=START + timedelta(hours=21),
    )
    latest_path = write_opportunity_radar_snapshot(
        radar,
        tmp_path / "opportunity-radar" / "latest.json",
    )

    inbox = OpportunityInboxBuilder(
        ValidationSummaryReader(tmp_path / "missing-validation"),
        tmp_path / "missing-market-outlook.json",
        radar_snapshot_path=latest_path,
    ).build("MARKET_WIDE")

    assert radar.status == "READY"
    assert radar.candidates[0].setup_name == "session_vwap_reclaim"
    assert radar.candidates[0].pattern_type == "VWAP_CONFIRMATION"
    assert radar.candidates[0].entry != "PENDING_VALIDATED_LEVEL"
    assert radar.execution_allowed is False
    assert radar.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert inbox.generation_status == "ACTIVE"
    assert inbox.items[0].source == "opportunity_radar_snapshot"
    assert inbox.items[0].pattern_type == "VWAP_CONFIRMATION"
    assert inbox.items[0].entry != "PENDING_VALIDATED_LEVEL"
    assert "OOS_NOT_COMPLETE" in inbox.items[0].promotion_requirements
    assert "LIVE_ORDER_BLOCKED" in inbox.items[0].execution_blockers


def test_canonical_radar_snapshot_fails_closed_without_required_timeframes() -> None:
    radar = build_opportunity_radar_snapshot(
        (snapshot(),),
        cycle_id="missing-mtf",
        observed_at=START + timedelta(hours=21),
    )

    candidate = radar.candidates[0]
    assert radar.status == "RUNNING_WITH_BLOCKERS"
    assert candidate.setup_name == "SETUP_UNAVAILABLE"
    assert candidate.score == Decimal("0")
    assert candidate.timeframe == "UNSPECIFIED"
    assert "CANONICAL_MTF_SNAPSHOT_INCOMPLETE:1h,4h" in candidate.blockers
    assert candidate.execution_allowed is False
    assert candidate.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_opportunity_radar_contracts_reject_invalid_identity_and_authority() -> None:
    observed = START + timedelta(hours=1)
    candidate = OpportunityRadarCandidate(
        opportunity_id="opportunity:1",
        symbol="HOTUSDT",
        market="SPOT",
        timeframe="1h",
        setup_name="support_reclaim",
        direction="BULLISH",
        status="WATCHLIST",
        promotion_status="RESEARCH_ONLY",
        score=Decimal("50"),
        grade="C",
        confidence=Decimal("0.5"),
        target_risk_reward=Decimal("2"),
        observed_at=observed,
        source_snapshot_id="snapshot-1",
        supporting_evidence=("snapshot:snapshot-1",),
        counter_evidence=("VALIDATION_GATE_REQUIRED",),
        confirmation_requirements=("ENTRY_TRIGGER_REQUIRED",),
        promotion_requirements=("OOS_NOT_COMPLETE",),
        execution_blockers=("LIVE_ORDER_BLOCKED",),
        next_evidence_action="WAIT_FOR_CONFIRMATION",
    )

    assert candidate.to_inbox_item()["execution_allowed"] is False
    assert candidate.to_inbox_item()["pattern_type"] == "REVERSAL_PATTERN"
    invalid_candidates: tuple[Callable[[], OpportunityRadarCandidate], ...] = (
        lambda: replace(candidate, opportunity_id=""),
        lambda: replace(candidate, score=Decimal("101")),
        lambda: replace(candidate, confidence=Decimal("1.1")),
        lambda: replace(candidate, target_risk_reward=Decimal("0")),
        lambda: replace(candidate, supporting_evidence=("same", "same")),
        lambda: replace(candidate, promotion_status="STAGED_CANDIDATE"),
        lambda: replace(candidate, execution_allowed=True),
    )
    for invalid_candidate in invalid_candidates:
        with pytest.raises(
            ValueError,
            match=r"opportunity|score|confidence|risk|evidence|staged|execution",
        ):
            invalid_candidate()

    snapshot_report = OpportunityRadarSnapshot(
        radar_id="radar-1",
        cycle_id="cycle-1",
        observed_at=observed,
        source_snapshot_ids=("snapshot-1",),
        universe_version="universe:v1",
        policy_version="policy:v1",
        candidates=(candidate,),
        blockers=("LIVE_ORDER_BLOCKED",),
    )
    assert snapshot_report.candidate_count == 1
    assert snapshot_report.to_payload()["execution_allowed"] is False
    invalid_snapshots: tuple[Callable[[], OpportunityRadarSnapshot], ...] = (
        lambda: replace(snapshot_report, radar_id=""),
        lambda: replace(snapshot_report, observed_at=datetime(2026, 7, 11)),
        lambda: replace(snapshot_report, source_snapshot_ids=()),
        lambda: replace(snapshot_report, status="TRADE_NOW"),
        lambda: replace(snapshot_report, blockers=("dup", "dup")),
        lambda: replace(snapshot_report, execution_allowed=True),
    )
    for invalid_snapshot in invalid_snapshots:
        with pytest.raises(
            ValueError,
            match=r"radar|observed|snapshot|status|blockers|execution",
        ):
            invalid_snapshot()


def test_opportunity_radar_blocks_invalid_snapshot_quality_and_price() -> None:
    invalid = MarketSnapshot(
        snapshot_id="invalid-quality",
        created_at=START,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m", "1h", "4h", "1d"),
        ohlcv_by_timeframe={
            "15m": tuple(snapshot().ohlcv_by_timeframe["15m"]),
            "1h": tuple(snapshot().ohlcv_by_timeframe["15m"]),
            "4h": tuple(snapshot().ohlcv_by_timeframe["15m"]),
            "1d": tuple(snapshot().ohlcv_by_timeframe["15m"]),
        },
        latest_price=Decimal("0"),
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_INVALID,
    )

    radar = build_opportunity_radar_snapshot(
        (invalid,),
        cycle_id="invalid-quality",
        observed_at=START + timedelta(hours=1),
    )

    assert radar.status == "RUNNING_WITH_BLOCKERS"
    assert "CANONICAL_SNAPSHOT_DATA_NOT_VALID" in radar.candidates[0].blockers
    assert "CANONICAL_LATEST_PRICE_UNAVAILABLE" in radar.candidates[0].blockers


def test_opportunity_radar_trade_plan_fails_closed_for_invalid_levels() -> None:
    base = _multi_timeframe_snapshot()
    rows = tuple(
        OHLCVCandle(
            timestamp=candle.timestamp,
            open=Decimal("1"),
            high=Decimal("1.1"),
            low=Decimal("0.1"),
            close=Decimal("0.2") if index == 20 else Decimal("1"),
            volume=candle.volume,
        )
        for index, candle in enumerate(base.ohlcv_by_timeframe["15m"])
    )
    low_price = MarketSnapshot(
        snapshot_id="low-price-snapshot",
        created_at=base.created_at,
        exchange=base.exchange,
        market_type=base.market_type,
        symbol=base.symbol,
        timeframes=base.timeframes,
        ohlcv_by_timeframe={
            "15m": rows,
            "1h": rows,
            "4h": rows,
            "1d": rows,
        },
        latest_price=Decimal("0.2"),
        bid=Decimal("0.19"),
        ask=Decimal("0.21"),
        spread=Decimal("0.02"),
        data_quality=DataQuality.DATA_VALID,
    )

    radar = build_opportunity_radar_snapshot(
        (low_price,),
        cycle_id="low-price",
        observed_at=START + timedelta(hours=21),
    )

    assert radar.candidates[0].entry == "PENDING_VALIDATED_LEVEL"
    assert radar.execution_allowed is False


def test_opportunity_radar_rejects_blank_pattern_type_and_empty_snapshot_stream() -> (
    None
):
    observed = START + timedelta(hours=1)
    with pytest.raises(ValueError, match="pattern_type cannot be blank"):
        OpportunityRadarCandidate(
            opportunity_id="opportunity:1",
            symbol="HOTUSDT",
            market="SPOT",
            timeframe="1h",
            setup_name="support_reclaim",
            direction="BULLISH",
            status="WATCHLIST",
            promotion_status="RESEARCH_ONLY",
            score=Decimal("50"),
            grade="C",
            confidence=Decimal("0.5"),
            target_risk_reward=Decimal("2"),
            observed_at=observed,
            source_snapshot_id="snapshot-1",
            supporting_evidence=("snapshot:snapshot-1",),
            counter_evidence=("VALIDATION_GATE_REQUIRED",),
            confirmation_requirements=("ENTRY_TRIGGER_REQUIRED",),
            promotion_requirements=("OOS_NOT_COMPLETE",),
            execution_blockers=("LIVE_ORDER_BLOCKED",),
            next_evidence_action="WAIT_FOR_CONFIRMATION",
            pattern_type=" ",
        )

    with pytest.raises(ValueError, match="at least one market snapshot"):
        build_opportunity_radar_snapshot((), cycle_id="empty")


def test_opportunity_radar_helper_paths_cover_ordering_and_serialization() -> None:
    bearish = evaluate(snapshot(bearish=True), inventory_available=True)
    assert _direction(bearish) == "BEARISH"

    neutral_rows = tuple(
        OHLCVCandle(
            timestamp=START + timedelta(minutes=15 * index),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("100"),
        )
        for index in range(21)
    )
    neutral_snapshot = MarketSnapshot(
        snapshot_id="neutral-direction",
        created_at=neutral_rows[-1].timestamp,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": neutral_rows},
        latest_price=Decimal("100"),
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_VALID,
    )
    watch_only = VWAPOpportunityEvaluator().evaluate(
        neutral_snapshot,
        timeframe="15m",
        session_start=START,
        structure_aligned=True,
        htf_aligned=True,
    )
    assert _direction(watch_only) == "WATCH_ONLY"
    assert (
        _vwap_lifecycle_state(("SPOT_INVENTORY_REQUIRED_FOR_SELL",))
        is OpportunityLifecycleState.WATCH_ONLY
    )

    assert _trend_aligned((snapshot().ohlcv_by_timeframe["15m"][0],)) is False

    assert _trade_plan(replace(bearish, atr=Decimal("0"))) == {}
    sell_plan = _trade_plan(bearish)
    assert sell_plan["entry"] == "98"
    assert Decimal(sell_plan["stop_loss"]) > Decimal(sell_plan["entry"])
    assert Decimal(sell_plan["tp1"]) < Decimal(sell_plan["entry"])

    negative_sell_plan = _trade_plan(
        replace(
            bearish,
            price=Decimal("1"),
            atr=Decimal("2"),
            action=Action.SELL,
        )
    )
    assert negative_sell_plan == {}


def _write_run_card(
    root: Path,
    *,
    blockers: tuple[str, ...],
    metrics: tuple[tuple[str, float], ...],
    promotion_status: str,
    playbook: str = "UNKNOWN_PLAYBOOK",
) -> None:
    path = root / "HOTUSDT" / "1h" / f"{playbook}.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        "runtime/artifacts/research/backtest/validation/HOTUSDT/1h/run-card.jsonl",
                        "sha",
                    ]
                ],
                "blockers": list(blockers),
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": f"hyp:{playbook}:1h",
                "metrics": [list(item) for item in metrics],
                "promotion_status": promotion_status,
                "run_id": f"run:{playbook}",
                "symbol": "HOTUSDT",
                "timeframe": "1h",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _multi_timeframe_snapshot() -> MarketSnapshot:
    base = snapshot()
    decision_time = START + timedelta(hours=21)

    def rows(timeframe_minutes: int) -> tuple[OHLCVCandle, ...]:
        start = decision_time - timedelta(minutes=timeframe_minutes * 21)
        source = tuple(base.ohlcv_by_timeframe["15m"])
        return tuple(
            replace(
                candle,
                timestamp=start + timedelta(minutes=timeframe_minutes * index),
            )
            for index, candle in enumerate(source)
        )

    rows_15m = rows(15)
    return MarketSnapshot(
        snapshot_id="canonical-mtf-snapshot",
        created_at=base.created_at,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m", "1h", "4h", "1d"),
        ohlcv_by_timeframe={
            "15m": rows_15m,
            "1h": rows(60),
            "4h": rows(240),
            "1d": rows(1440),
        },
        latest_price=base.latest_price,
        bid=Decimal("101.9"),
        ask=Decimal("102.1"),
        spread=Decimal("0.2"),
        data_quality=DataQuality.DATA_VALID,
    )

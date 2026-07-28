"""Deterministic Market Outlook synthesis and fail-closed contract tests."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from test_technical_agents import technical_snapshot

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.domain import PriceZone, SetupTier
from ai4binance.outlook import (
    BiasDirection,
    HighImpactEvent,
    KeyLevel,
    KeyLevelKind,
    MarketOutlook,
    MarketOutlookEngine,
    OutlookStatus,
    SetupRadarItem,
    TimeframeBias,
    TpoCompositeContext,
)
from ai4binance.schemas import AnalysisState, DataQuality


def full_analysis() -> AnalysisState:
    return EnterpriseOrchestrator(minimum_candles=50).analyze(technical_snapshot())


def test_outlook_reuses_agent_evidence_and_remains_research_only() -> None:
    outlook = MarketOutlookEngine().build(full_analysis())

    assert outlook.snapshot_id == "technical-1"
    assert outlook.status is OutlookStatus.PARTIAL
    assert [item.timeframe for item in outlook.timeframe_biases] == [
        "1d",
        "4h",
        "1h",
        "15m",
    ]
    assert all(
        item.direction is BiasDirection.BULLISH for item in outlook.timeframe_biases
    )
    assert outlook.market_regime in {"STRONG_UPTREND", "WEAK_UPTREND"}
    assert outlook.pro_trend_direction is BiasDirection.BULLISH
    assert outlook.timeframe_conflict is False
    assert {item.kind for item in outlook.key_levels} == {
        KeyLevelKind.SUPPORT,
        KeyLevelKind.RESISTANCE,
    }
    assert all(item.zone.lower < item.zone.upper for item in outlook.key_levels)
    assert outlook.tpo_composites.status == "PROXY_ONLY"
    assert outlook.tpo_composites.point_of_control_proxy is not None
    assert "TPO_AUCTION_PROFILE_NOT_IMPLEMENTED" in outlook.blockers
    assert outlook.execution_allowed is False
    assert outlook.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_outlook_parses_only_sourced_high_impact_events() -> None:
    snapshot = replace(
        technical_snapshot(),
        news_snapshot={
            "high_impact_events": (
                {
                    "event_id": "macro-1",
                    "title": "Scheduled macro release",
                    "scheduled_at": "2026-07-13T15:00:00+03:00",
                    "impact": "high",
                    "source": "official-calendar",
                },
                {
                    "title": "Unsourced item",
                    "scheduled_at": datetime(2026, 7, 13, 16, tzinfo=UTC),
                    "impact": "HIGH",
                },
                {
                    "title": "Low impact item",
                    "scheduled_at": datetime(2026, 7, 13, 17, tzinfo=UTC),
                    "impact": "LOW",
                    "source": "official-calendar",
                },
                "not-a-mapping",
                {
                    "title": "Critical scheduled event",
                    "scheduled_at": "2026-07-13T18:00:00Z",
                    "impact": "CRITICAL",
                    "source": "official-calendar",
                },
            )
        },
    )
    analysis = EnterpriseOrchestrator(minimum_candles=50).analyze(snapshot)
    outlook = MarketOutlookEngine().build(analysis)

    assert [item.title for item in outlook.high_impact_data] == [
        "Scheduled macro release",
        "Critical scheduled event",
    ]
    assert "HIGH_IMPACT_DATA_UNAVAILABLE" not in outlook.blockers
    assert "HIGH_IMPACT_EVENT_INVALID:1" in outlook.warnings
    assert "HIGH_IMPACT_EVENT_INVALID:2" in outlook.warnings
    assert "HIGH_IMPACT_EVENT_INVALID:3" in outlook.warnings


def test_outlook_is_deterministic_and_blocks_missing_history() -> None:
    engine = MarketOutlookEngine()
    analysis = full_analysis()
    assert engine.build(analysis) == engine.build(analysis)

    blocked = EnterpriseOrchestrator().analyze(
        replace(technical_snapshot(), data_quality=DataQuality.DATA_INVALID)
    )
    blocked_outlook = engine.build(blocked)
    assert blocked_outlook.status is OutlookStatus.BLOCKED
    assert blocked_outlook.volatility_state == "UNKNOWN"
    assert blocked_outlook.tpo_composites.status == "UNAVAILABLE"


def test_atr_buffered_levels_never_cross_zero() -> None:
    analysis = full_analysis()
    structural = analysis.agent_results["support_resistance"]
    volatility = analysis.agent_results["volatility"]
    modified_results = dict(analysis.agent_results)
    modified_results["support_resistance"] = replace(
        structural,
        calculation_metadata={
            "timeframes": {"1h": {"support": "0.01", "resistance": "0.02"}}
        },
    )
    modified_results["volatility"] = replace(
        volatility,
        calculation_metadata={"timeframes": {"1h": {"atr_14": "1"}}},
    )
    outlook = MarketOutlookEngine().build(
        replace(analysis, agent_results=modified_results)
    )

    support = next(
        item
        for item in outlook.key_levels
        if item.timeframe == "1h" and item.kind is KeyLevelKind.SUPPORT
    )
    assert support.zone.lower == Decimal("0")


def test_setup_radar_falls_back_to_deduplicated_agent_detections() -> None:
    analysis = full_analysis()
    trend = analysis.agent_results["trend"]
    results = dict(analysis.agent_results)
    results["trend"] = replace(
        trend,
        directional_vote=-0.5,
        score=65.0,
        confidence=0.5,
        detected_setups=("BEARISH_TEST", "BEARISH_TEST", "BEARISH_TEST:1h"),
    )

    outlook = MarketOutlookEngine().build(
        replace(analysis, agent_results=results, candidate_setups=())
    )

    detected = [
        item for item in outlook.setups_on_radar if item.setup_name == "BEARISH_TEST"
    ]
    assert [item.timeframe for item in detected] == ["1h", "UNKNOWN"]
    assert all(item.direction is BiasDirection.BEARISH for item in detected)
    assert all(item.setup_tier is SetupTier.C for item in detected)
    assert all(item.blockers == ("SETUP_NOT_OOS_VALIDATED",) for item in detected)


def test_outlook_context_branches_are_explicit() -> None:
    analysis = full_analysis()
    wyckoff = analysis.agent_results["wyckoff"]
    volatility = analysis.agent_results["volatility"]
    results = dict(analysis.agent_results)

    results["wyckoff"] = replace(wyckoff, detected_setups=("SPRING_PROXY",))
    results["volatility"] = replace(volatility, warnings=("ABNORMAL_VOLATILITY:1h",))
    accumulation = MarketOutlookEngine().build(replace(analysis, agent_results=results))
    assert accumulation.macro_cycle_view == "ACCUMULATION_CANDIDATE"
    assert accumulation.volatility_state == "ABNORMAL"

    results["wyckoff"] = replace(wyckoff, detected_setups=("UPTHRUST_PROXY",))
    distribution = MarketOutlookEngine().build(replace(analysis, agent_results=results))
    assert distribution.macro_cycle_view == "DISTRIBUTION_CANDIDATE"


def test_outlook_value_helpers_fail_closed() -> None:
    assert MarketOutlookEngine._direction(-1.0) is BiasDirection.BEARISH
    assert MarketOutlookEngine._direction(0.0) is BiasDirection.NEUTRAL
    assert MarketOutlookEngine._tier(80.0) is SetupTier.A
    assert MarketOutlookEngine._tier(75.0) is SetupTier.B
    assert MarketOutlookEngine._tier(10.0) is SetupTier.NO_TRADE
    assert MarketOutlookEngine._float(True) is None
    assert MarketOutlookEngine._float("1") is None
    assert MarketOutlookEngine._float(float("nan")) is None
    assert MarketOutlookEngine._decimal(True) is None
    assert MarketOutlookEngine._decimal("invalid") is None
    assert MarketOutlookEngine._decimal("NaN") is None
    assert MarketOutlookEngine._datetime("invalid") is None
    assert MarketOutlookEngine._datetime("2026-07-13T10:00:00") is None
    assert MarketOutlookEngine._datetime(123) is None
    assert (
        MarketOutlookEngine._status(DataQuality.DATA_VALID, ()) is OutlookStatus.READY
    )


def test_outlook_models_reject_unsafe_or_incomplete_values() -> None:
    bias = TimeframeBias("1h", BiasDirection.BULLISH, 80.0, 0.8, ("TEST",))
    for changes, message in (
        ({"timeframe": ""}, "timeframe"),
        ({"score": -1.0}, "score"),
        ({"confidence": 2.0}, "confidence"),
        ({"reason_codes": ()}, "reason_codes"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(bias, **changes)

    setup = SetupRadarItem(
        "setup",
        "1h",
        BiasDirection.BULLISH,
        SetupTier.B,
        70.0,
        0.7,
        "PARTIAL",
        "RESEARCH_ONLY",
    )
    with pytest.raises(ValueError, match="setup_name"):
        replace(setup, setup_name="")
    with pytest.raises(ValueError, match="score"):
        replace(setup, score=101.0)
    with pytest.raises(ValueError, match="confidence"):
        replace(setup, confidence=-1.0)

    event = HighImpactEvent(
        "event", "title", datetime(2026, 7, 13, tzinfo=UTC), "HIGH", "source"
    )
    with pytest.raises(ValueError, match="title"):
        replace(event, title="")
    with pytest.raises(ValueError, match="timestamp"):
        replace(event, scheduled_at=datetime(2026, 7, 13))
    with pytest.raises(ValueError, match="HIGH or CRITICAL"):
        replace(event, impact="LOW")

    level = KeyLevel("1h", KeyLevelKind.SUPPORT, PriceZone(Decimal("1"), Decimal("2")))
    with pytest.raises(ValueError, match="source"):
        replace(level, source="")

    tpo = TpoCompositeContext("AVAILABLE")
    with pytest.raises(ValueError, match="status"):
        replace(tpo, status="")
    with pytest.raises(ValueError, match="point-of-control"):
        replace(tpo, point_of_control_proxy=Decimal("-1"))
    with pytest.raises(ValueError, match="requires blockers"):
        replace(tpo, status="PROXY_ONLY")


def test_market_outlook_contract_rejects_authority_or_missing_context() -> None:
    outlook: MarketOutlook = MarketOutlookEngine().build(full_analysis())
    with pytest.raises(ValueError, match="identity"):
        replace(outlook, snapshot_id="")
    with pytest.raises(ValueError, match="timestamp"):
        replace(outlook, timestamp=datetime(2026, 7, 13))
    with pytest.raises(ValueError, match="context"):
        replace(outlook, market_regime="")
    with pytest.raises(ValueError, match="risk"):
        replace(outlook, volatility_state="")
    with pytest.raises(ValueError, match="execution"):
        replace(outlook, execution_allowed=True)
    with pytest.raises(ValueError, match="live blocked"):
        replace(outlook, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="READY"):
        replace(outlook, status=OutlookStatus.READY)

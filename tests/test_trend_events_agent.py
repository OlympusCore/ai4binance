"""Governance and behavior tests for trend event intelligence."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.trend_events import TrendEventsAgent
from ai4binance.schemas import AgentStatus, DataQuality, MarketSnapshot, OHLCVCandle

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _snapshot(direction: int, count: int = 220) -> MarketSnapshot:
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(hours=count - index),
            open=Decimal("1000") + Decimal(direction * index),
            high=Decimal("1001") + Decimal(direction * index),
            low=Decimal("999") + Decimal(direction * index),
            close=Decimal("1000.5") + Decimal(direction * index),
            volume=Decimal("100"),
        )
        for index in range(count)
    )
    return MarketSnapshot(
        snapshot_id=f"trend-events-{direction}-{count}",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("4h",),
        ohlcv_by_timeframe={"4h": candles},
        latest_price=candles[-1].close,
        bid=candles[-1].close,
        ask=candles[-1].close,
        spread=Decimal("0"),
        data_quality=DataQuality.DATA_VALID,
    )


def test_trend_events_agent_tracks_direction_without_authority() -> None:
    agent = TrendEventsAgent(build_default_registry().get("trend_events"))
    bullish = agent.analyze(_snapshot(1), {})
    bearish = agent.analyze(_snapshot(-1), {})
    assert bullish.status is AgentStatus.SUCCESS
    assert bullish.directional_vote > 0
    assert bearish.directional_vote < 0
    assert bullish.hard_gate_eligible is False
    assert bullish.promotion_status.value == "RESEARCH_ONLY"
    details = bullish.calculation_metadata["4h"]
    assert isinstance(details, Mapping)
    assert details["atr_period"] == 14
    assert details["price_source"] == "OHLC4"
    assert details["multiplier"] == "2"


def test_trend_events_agent_fails_closed_without_warmup() -> None:
    agent = TrendEventsAgent(build_default_registry().get("trend_events"))
    result = agent.analyze(_snapshot(1, count=14), {})
    assert result.status is AgentStatus.INSUFFICIENT_DATA
    assert result.blockers == ("TREND_EVENTS_WARMUP_MISSING",)

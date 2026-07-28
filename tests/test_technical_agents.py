"""Core deterministic technical-agent tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.agents.technical import (
    CORE_TECHNICAL_AGENT_TYPES,
    PriceActionAgent,
    build_core_technical_agent,
)
from ai4binance.domain import Decision
from ai4binance.schemas import AgentStatus, DataQuality, MarketSnapshot, OHLCVCandle

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


def trend_candles(
    count: int,
    *,
    direction: int = 1,
) -> tuple[OHLCVCandle, ...]:
    rows = []
    for index in range(count):
        close = Decimal("1") + (Decimal(direction * index) * Decimal("0.002"))
        rows.append(
            OHLCVCandle(
                timestamp=NOW - timedelta(hours=count - index),
                open=close - (Decimal(direction) * Decimal("0.001")),
                high=max(close, close - Decimal(direction) * Decimal("0.001"))
                + Decimal("0.002"),
                low=min(close, close - Decimal(direction) * Decimal("0.001"))
                - Decimal("0.002"),
                close=close,
                volume=Decimal("100") + Decimal(index),
            )
        )
    return tuple(rows)


def technical_snapshot(*, direction: int = 1) -> MarketSnapshot:
    data = {
        timeframe: trend_candles(60, direction=direction)
        for timeframe in ("15m", "1h", "4h", "1d")
    }
    latest = data["15m"][-1].close
    return MarketSnapshot(
        snapshot_id=f"technical-{direction}",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("15m", "1h", "4h", "1d"),
        ohlcv_by_timeframe=data,
        latest_price=latest,
        bid=latest - Decimal("0.0001"),
        ask=latest + Decimal("0.0001"),
        spread=Decimal("0.0002"),
        exchange_filters={"PRICE_FILTER": {"tickSize": "0.0001"}},
        data_freshness={timeframe: {"stale": False} for timeframe in data},
        data_quality=DataQuality.DATA_VALID,
        market_metadata={"trading_status": "TRADING"},
    )


def test_every_core_agent_has_a_real_implementation() -> None:
    registry = build_default_registry()
    assert len(CORE_TECHNICAL_AGENT_TYPES) == 10
    for name in CORE_TECHNICAL_AGENT_TYPES:
        assert build_core_technical_agent(registry.get(name)) is not None
    assert build_core_technical_agent(registry.get("ichimoku")) is None


def test_core_agents_evaluate_uptrend_without_execution_authority() -> None:
    registry = build_default_registry()
    snapshot = technical_snapshot()
    for name in CORE_TECHNICAL_AGENT_TYPES:
        agent = build_core_technical_agent(registry.get(name))
        assert agent is not None
        result = agent.analyze(snapshot, {})
        if name == "price_action":
            assert result.status is AgentStatus.NOT_APPLICABLE
        else:
            assert result.status in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}
            assert result.score > 0
        assert (
            result.execution_allowed is False
            if hasattr(result, "execution_allowed")
            else True
        )
        assert result.hard_gate_eligible is False


def test_trend_and_momentum_agents_change_direction() -> None:
    registry = build_default_registry()
    for name in ("trend", "moving_average", "momentum", "market_structure"):
        agent = build_core_technical_agent(registry.get(name))
        assert agent is not None
        bullish = agent.analyze(technical_snapshot(direction=1), {})
        bearish = agent.analyze(technical_snapshot(direction=-1), {})
        assert bullish.directional_vote > 0
        assert bearish.directional_vote < 0


def test_price_action_agent_detects_contextual_engulfing() -> None:
    registry = build_default_registry()
    base = technical_snapshot()
    candles = list(base.ohlcv_by_timeframe["15m"])
    candles[-2] = OHLCVCandle(
        candles[-2].timestamp,
        Decimal("1.10"),
        Decimal("1.11"),
        Decimal("0.99"),
        Decimal("1.00"),
        Decimal("100"),
    )
    candles[-1] = OHLCVCandle(
        candles[-1].timestamp,
        Decimal("0.99"),
        Decimal("1.13"),
        Decimal("0.98"),
        Decimal("1.12"),
        Decimal("150"),
    )
    snapshot = MarketSnapshot(
        snapshot_id="engulfing",
        created_at=base.created_at,
        exchange=base.exchange,
        market_type=base.market_type,
        symbol=base.symbol,
        timeframes=("15m",),
        ohlcv_by_timeframe={"15m": tuple(candles)},
        latest_price=Decimal("1.12"),
        bid=Decimal("1.119"),
        ask=Decimal("1.121"),
        spread=Decimal("0.002"),
        exchange_filters=base.exchange_filters,
        data_freshness={"15m": {"stale": False}},
        data_quality=DataQuality.DATA_VALID,
        market_metadata=base.market_metadata,
    )
    agent = PriceActionAgent(registry.get("price_action"))
    result = agent.analyze(snapshot, {})
    assert result.status is AgentStatus.SUCCESS
    assert result.directional_vote == 1.0
    assert result.detected_setups == ("BULLISH_ENGULFING:15m",)


def test_orchestrator_populates_scores_but_remains_no_trade() -> None:
    state = EnterpriseOrchestrator(minimum_candles=50).analyze(technical_snapshot())
    assert state.final_decision is not None
    assert state.final_decision.decision_state is Decision.NO_TRADE
    assert state.final_decision.final_signal_score > 0
    assert state.final_decision.sub_scores.trend_score > 0
    assert state.final_decision.sub_scores.momentum_score > 0
    assert state.final_decision.independent_confluence_count >= 5
    assert state.agent_results["confluence"].status is AgentStatus.PARTIAL
    assert "OOS_APPROVAL_MISSING" in state.final_decision.blockers

"""Structural direction, lifecycle and geometry cannot fall back to indicators."""

from dataclasses import replace
from decimal import Decimal

import pytest

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.technical import MarketStructureAgent, SupportResistanceAgent
from ai4binance.data.timeframes import timeframe_duration, timeframe_from_duration
from ai4binance.domain import Action, CandidateStatus, ValidationStatus
from ai4binance.intelligence.contracts import ScenarioState
from ai4binance.intelligence.plan import TradePlanEngine
from ai4binance.intelligence.trading import ScenarioEngine
from ai4binance.schemas import AgentResult, MarketSnapshot
from ai4binance.strategies.engine import StrategyEngine
from ai4binance.strategies.rules import historical_playbook_decision
from tests.test_strategy_rules import structural_candles
from tests.test_trading_intelligence import _costed_snapshot, _evidence_results, _result


def structural_context(
    *, short: bool = False
) -> tuple[MarketSnapshot, dict[str, AgentResult]]:
    snapshot = _costed_snapshot()
    data = {}
    for timeframe in snapshot.timeframes:
        interval = timeframe_duration(timeframe)
        rows = structural_candles()
        data[timeframe] = tuple(
            replace(
                candle,
                timestamp=snapshot.created_at - (len(rows) - index) * interval,
                open=(Decimal("2200") - candle.open if short else candle.open) / 1000,
                close=(Decimal("2200") - candle.close if short else candle.close)
                / 1000,
                high=(Decimal("2200") - candle.low if short else candle.high) / 1000,
                low=(Decimal("2200") - candle.high if short else candle.low) / 1000,
            )
            for index, candle in enumerate(rows)
        )
    price = data["15m"][-1].close
    snapshot = replace(
        snapshot,
        market_type="USD_M_FUTURES",
        ohlcv_by_timeframe=data,
        latest_price=price,
        bid=price - Decimal(".0001"),
        ask=price + Decimal(".0001"),
        market_metadata={**snapshot.market_metadata, "estimated_funding_periods": 1},
        derivatives_snapshot={
            "source_count": 10,
            "as_of": snapshot.created_at.isoformat(),
            "funding_rate": "0.0001",
            "open_interest": "10000",
            "mark_price": str(price),
            "index_price": str(price),
        },
    )
    registry = build_default_registry()
    results = _evidence_results()
    results.update(
        {
            "market_structure": MarketStructureAgent(
                registry.get("market_structure")
            ).analyze(snapshot, {}),
            "support_resistance": SupportResistanceAgent(
                registry.get("support_resistance")
            ).analyze(snapshot, {}),
            "trend_channel": _result("trend_channel"),
            "derivatives": _result("derivatives"),
            "market_regime": _result(
                "market_regime",
                vote=-1 if short else 1,
                metadata={"regime": "STRONG_DOWNTREND" if short else "STRONG_UPTREND"},
            ),
            "price_action": _result(
                "price_action",
                vote=-1 if short else 1,
                evidence=(
                    "BEARISH_ENGULFING:15m" if short else "BULLISH_ENGULFING:15m",
                ),
            ),
        }
    )
    return snapshot, results


@pytest.mark.parametrize("short", [False, True])
def test_futures_entry_uses_structure_without_trend_or_confluence(short: bool) -> None:
    snapshot, results = structural_context(short=short)
    state = ScenarioEngine().build(snapshot, results)
    assert state.selected_scenario is not None
    (candidate,) = StrategyEngine().generate(
        snapshot, results, trading_intelligence=state
    )
    assert candidate.action is (Action.SELL if short else Action.BUY)
    assert candidate.status is CandidateStatus.READY_FOR_RISK
    assert candidate.inventory_action == "NONE"
    assert candidate.blockers == ()
    assert candidate.scenario_id == state.selected_scenario_id
    assert candidate.target_sources
    assert candidate.net_risk_reward is not None
    assert candidate.net_risk_reward < candidate.risk_reward
    assert candidate.entry_price == snapshot.ohlcv_by_timeframe["15m"][-1].close
    assert candidate.stop_loss == state.selected_scenario.invalidation_level
    assert candidate.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert candidate.expected_r is None
    assert "STRUCTURAL_ENTRY_V3" in candidate.evidence


@pytest.mark.parametrize(
    "missing",
    [
        "levels",
        "structures",
        "trigger",
        "fresh_entry",
        "trendline",
        "entry_gap",
        "unknown_level_age",
    ],
)
def test_missing_structure_never_falls_back_to_indicator_seed(missing: str) -> None:
    snapshot, results = structural_context()
    state = ScenarioEngine().build(snapshot, results)
    if missing == "levels":
        state = replace(state, levels=())
    elif missing == "structures":
        state = replace(state, structures=())
    elif missing == "trendline":
        state = replace(
            state,
            trend_geometry=tuple(
                replace(line, break_state="BROKEN") for line in state.trend_geometry
            ),
        )
    elif missing == "unknown_level_age":
        state = replace(
            state,
            levels=tuple(replace(level, freshness="UNKNOWN") for level in state.levels),
        )
    elif missing == "entry_gap":
        rows = tuple(snapshot.ohlcv_by_timeframe["15m"])
        snapshot = replace(
            snapshot,
            ohlcv_by_timeframe={
                **snapshot.ohlcv_by_timeframe,
                "15m": rows[:20] + rows[21:],
            },
        )
    elif missing == "trigger":
        scenario = state.selected_scenario
        assert scenario is not None
        state = replace(
            state, scenarios=(replace(scenario, state=ScenarioState.FORMING),)
        )
    else:
        rows = tuple(snapshot.ohlcv_by_timeframe["15m"])
        snapshot = replace(
            snapshot,
            ohlcv_by_timeframe={**snapshot.ohlcv_by_timeframe, "15m": rows[:-1]},
        )
    assert TradePlanEngine().propose(snapshot, state) == ()


@pytest.mark.parametrize(
    "lifecycle", ["FORMING", "INVALIDATED", "EXPIRED", "CONFIRMED"]
)
def test_chart_pattern_trigger_requires_explicit_lifecycle(lifecycle: str) -> None:
    snapshot, results = structural_context()
    results.pop("price_action")
    results["chart_pattern"] = _result(
        "chart_pattern",
        metadata={
            "source_timeframe": "15m",
            "lifecycle_state": lifecycle,
            "pattern_id": "confirmed-anchors",
        },
    )
    state = ScenarioEngine().build(snapshot, results)
    candidates = TradePlanEngine().propose(snapshot, state)
    assert bool(candidates) is (lifecycle == "CONFIRMED")


def test_historical_geometry_is_causal_and_gap_rejecting() -> None:
    rows = structural_candles()
    first = historical_playbook_decision("trend_continuation", rows)
    assert first.triggered
    future = replace(
        rows[-1],
        timestamp=rows[-1].timestamp + timeframe_duration("1h"),
        high=Decimal("9999"),
    )
    assert (
        historical_playbook_decision("trend_continuation", (*rows, future)[:-1])
        == first
    )
    assert (
        "STRUCTURAL_HISTORY_GAP"
        in historical_playbook_decision(
            "trend_continuation", rows[:30] + rows[31:]
        ).blockers
    )
    assert timeframe_from_duration(timeframe_duration("15m")) == "15m"


def test_indicator_votes_cannot_reverse_a_structural_entry() -> None:
    snapshot, results = structural_context()
    baseline = StrategyEngine().generate(snapshot, results)
    assert baseline
    contrary = {
        **results,
        "trend": _result("trend", vote=-1),
        "moving_average": _result("moving_average", vote=-1),
        "confluence": _result("confluence", vote=-1),
    }
    assert StrategyEngine().generate(snapshot, contrary) == baseline

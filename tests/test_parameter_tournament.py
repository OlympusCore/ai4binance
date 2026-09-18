"""Research-only strategy parameter tournament tests."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.research.backtesting import BacktestIntent, SignalProvider
from ai4binance.research.backtesting.robustness import (
    BacktestRobustnessAnalyzer,
    StressScenario,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage.jsonl import JsonlAuditStore
from ai4binance.tuning import (
    StrategyParameterTournament,
    StrategyProfileCandidate,
    TournamentConfig,
    TournamentContext,
)
from ai4binance.tuning.storage import StrategyParameterTournamentAuditWriter
from ai4binance.validation import MarketRegime, ParameterSet, WalkForwardConfig

NOW = datetime(2026, 3, 1, tzinfo=UTC)
STRONG = StrategyProfileCandidate(
    "trend_tp_3",
    ParameterSet("tp3", (("take_profit_multiplier", 3.0),)),
)
WEAK = StrategyProfileCandidate(
    "trend_tp_1",
    ParameterSet("tp1", (("take_profit_multiplier", 1.0),)),
)


def candles(
    count: int = 12,
    *,
    base: Decimal = Decimal("100"),
) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=base,
            high=base + Decimal("4"),
            low=base - Decimal("2"),
            close=base,
            volume=Decimal("1000"),
        )
        for index in range(count)
    )


def strategy_factory(parameters: ParameterSet) -> SignalProvider:
    values = dict(parameters.values)
    target = Decimal("100") + Decimal(str(values["take_profit_multiplier"]))

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) % 2 == 0:
            return None
        return BacktestIntent(
            signal_id=f"{parameters.name}:{history[-1].timestamp.isoformat()}",
            timestamp=history[-1].timestamp,
            stop_loss=Decimal("95"),
            take_profit=target,
            atr=Decimal("2"),
        )

    return provider


def regime_classifier(candle: OHLCVCandle) -> MarketRegime:
    return MarketRegime.TREND if candle.timestamp.hour % 4 < 2 else MarketRegime.RANGE


def config(
    *,
    walk_forward: WalkForwardConfig | None = None,
    min_symbol_count: int = 2,
    min_timeframe_count: int = 2,
    min_trade_count: int = 4,
    max_symbol_concentration: float = 0.8,
    max_timeframe_concentration: float = 0.8,
    min_stress_return_ratio: float = 0.25,
) -> TournamentConfig:
    return TournamentConfig(
        walk_forward=walk_forward
        or WalkForwardConfig(
            train_size=4,
            test_size=2,
            step_size=2,
            min_oos_trades=4,
            max_turnover=0.6,
            max_edge_concentration=0.3,
        ),
        min_symbol_count=min_symbol_count,
        min_timeframe_count=min_timeframe_count,
        min_trade_count=min_trade_count,
        max_symbol_concentration=max_symbol_concentration,
        max_timeframe_concentration=max_timeframe_concentration,
        min_stress_return_ratio=min_stress_return_ratio,
    )


def contexts() -> tuple[TournamentContext, ...]:
    return (
        TournamentContext("BTCUSDT", "1h", candles()),
        TournamentContext("ETHUSDT", "4h", candles(base=Decimal("120"))),
    )


def test_tournament_ranks_profiles_deterministically_and_remains_research_only() -> (
    None
):
    engine = StrategyParameterTournament()

    first = engine.run(
        contexts=contexts(),
        candidates=(WEAK, STRONG),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config(),
    )
    second = engine.run(
        contexts=contexts(),
        candidates=(WEAK, STRONG),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config(),
    )

    assert [entry.profile_id for entry in first.entries] == ["trend_tp_3", "trend_tp_1"]
    assert all(entry.status == "RESEARCH_CANDIDATE" for entry in first.entries)
    assert all(not entry.execution_allowed for entry in first.entries)
    assert first.status == "RESEARCH_CANDIDATE"
    assert not first.execution_allowed
    assert first.entries[0].promotion_status.value == "RESEARCH_ONLY"
    assert first.entries[0].trade_count == 4
    assert first.entries[0].sortino is None
    assert first.entries[0].parameter_stability == 1.0
    assert len(first.entries[0].regime_breakdown) == 2
    assert first.report_id == second.report_id


def test_tournament_blocks_single_symbol_dependency() -> None:
    report = StrategyParameterTournament().run(
        contexts=(
            TournamentContext("BTCUSDT", "1h", candles()),
            TournamentContext("BTCUSDT", "4h", candles(base=Decimal("105"))),
        ),
        candidates=(STRONG,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config(min_symbol_count=2, min_timeframe_count=2),
    )

    assert "TOURNAMENT_SYMBOL_DIVERSITY_INSUFFICIENT" in report.entries[0].blockers


def test_tournament_blocks_cost_stress_collapse() -> None:
    analyzer = BacktestRobustnessAnalyzer(
        scenarios=(
            StressScenario("BASE", Decimal("0.001"), Decimal("0.0005")),
            StressScenario("HARSH", Decimal("0.01"), Decimal("0.02")),
        ),
        simulations=200,
        seed=7,
    )
    report = StrategyParameterTournament(robustness_analyzer=analyzer).run(
        contexts=(TournamentContext("BTCUSDT", "1h", candles()),),
        candidates=(WEAK,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config(
            min_symbol_count=1,
            min_timeframe_count=1,
            min_trade_count=4,
            min_stress_return_ratio=0.5,
        ),
    )

    assert "TOURNAMENT_COST_STRESS_COLLAPSE" in report.entries[0].blockers


def test_tournament_report_persists_to_append_only_audit(tmp_path: Path) -> None:
    report = StrategyParameterTournament().run(
        contexts=contexts(),
        candidates=(STRONG, WEAK),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config(),
    )
    output = tmp_path / "tournament.jsonl"
    StrategyParameterTournamentAuditWriter(JsonlAuditStore(output)).append(report)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["event_type"] == "STRATEGY_PARAMETER_TOURNAMENT_REPORT"
    assert payload["payload"]["report"]["report_id"] == report.report_id
    assert payload["payload"]["report"]["status"] == "RESEARCH_CANDIDATE"


def test_tournament_rejects_empty_inputs_and_covers_empty_metric_helpers() -> None:
    engine = StrategyParameterTournament()
    with pytest.raises(ValueError, match="at least one context"):
        engine.run(
            contexts=(),
            candidates=(STRONG,),
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=config(),
        )
    with pytest.raises(ValueError, match="at least one candidate"):
        engine.run(
            contexts=contexts(),
            candidates=(),
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=config(),
        )

    assert StrategyParameterTournament._worst_stress_ratio((), 1.0) == 0.0
    assert StrategyParameterTournament._worst_stress_ratio((("BASE", 1.0),), 0.0) == 0.0
    assert StrategyParameterTournament._average_r(()) == 0.0
    assert StrategyParameterTournament._tail_loss(()) == 0.0
    assert StrategyParameterTournament._sortino(()) is None


def test_tournament_blocker_aggregation_covers_count_drawdown_and_timeframes() -> None:
    report = StrategyParameterTournament().run(
        contexts=contexts(),
        candidates=(STRONG,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config(),
    )

    blockers = StrategyParameterTournament._blockers(
        report.entries[0].evaluations,
        trade_count=0,
        max_drawdown=1.0,
        config=config(min_symbol_count=1, min_timeframe_count=3),
    )

    assert "TOURNAMENT_TRADE_COUNT_INSUFFICIENT" in blockers
    assert "TOURNAMENT_OOS_DRAWDOWN_EXCESSIVE" in blockers
    assert "TOURNAMENT_TIMEFRAME_DIVERSITY_INSUFFICIENT" in blockers

"""Phase D staged-exit, MTM and robustness regression tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai4binance.backtest import (
    BacktestEngine,
    BacktestIntent,
    BacktestRobustnessAnalyzer,
    SignalProvider,
)
from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 3, 1, tzinfo=UTC)


def candle(
    index: int,
    *,
    high: str = "106",
    low: str = "99",
    close: str = "100",
) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=NOW + timedelta(hours=index),
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


def staged_intent(timestamp: datetime) -> BacktestIntent:
    return BacktestIntent(
        signal_id="staged-signal",
        timestamp=timestamp,
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        atr=Decimal("2"),
        take_profit_levels=(Decimal("105"), Decimal("110")),
        partial_exit_ratio=Decimal("0.5"),
    )


def test_multiple_targets_create_partial_then_complete_exit() -> None:
    candles = (
        candle(0, high="101"),
        candle(1, high="106"),
        candle(2, high="111", close="110"),
    )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=lambda history: (
            staged_intent(history[-1].timestamp) if len(history) == 1 else None
        ),
    )

    trade = result.trades[0]
    assert len(trade.staged_exits) == 1
    assert trade.staged_exits[0].quantity == Decimal("0.5")
    assert trade.staged_exits[0].price == Decimal("104.9475")
    assert trade.quantity == Decimal("1")
    assert trade.net_pnl_usdt > Decimal("7")
    assert any(
        event["event_type"] == "PARTIAL_TAKE_PROFIT" for event in result.audit_events
    )


def test_mark_to_market_drawdown_captures_recovered_intratrade_loss() -> None:
    candles = (
        candle(0, high="101"),
        candle(1, high="101"),
        candle(2, high="100", low="98", close="98"),
        candle(3, high="111", close="110"),
    )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=lambda history: (
            replace(staged_intent(history[-1].timestamp), take_profit_levels=())
            if len(history) == 1
            else None
        ),
    )

    assert len(result.equity_curve) == len(candles)
    assert min(point.equity_usdt for point in result.equity_curve) < Decimal("998")
    assert result.trades[0].net_pnl_usdt > 0
    assert result.metrics.max_drawdown > 0.002


def test_breakout_stop_is_recorded_as_false_breakout() -> None:
    candles = (candle(0, high="101"), candle(1, high="101", low="94"))
    breakout = replace(
        staged_intent(candles[0].timestamp),
        take_profit_levels=(),
        reason_codes=("BREAKOUT_RETEST",),
    )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=lambda history: breakout if len(history) == 1 else None,
    )

    assert len(result.false_breakouts) == 1
    assert result.false_breakouts[0].signal_id == "staged-signal"
    assert result.false_breakouts[0].net_pnl_usdt < 0


def test_cost_stress_and_bootstrap_are_deterministic_and_non_executing() -> None:
    candles = tuple(candle(index) for index in range(24))

    def provider_factory() -> SignalProvider:
        def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
            if len(history) % 2 == 0:
                return None
            return replace(
                staged_intent(history[-1].timestamp),
                signal_id=f"stress-{len(history)}",
                take_profit=Decimal("105"),
                take_profit_levels=(),
            )

        return provider

    analyzer = BacktestRobustnessAnalyzer(simulations=100, seed=7)
    first = analyzer.analyze(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        provider_factory=provider_factory,
    )
    second = analyzer.analyze(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        provider_factory=provider_factory,
    )

    assert first == second
    assert len(first.stress_results) == 3
    assert first.bootstrap.simulations == 100
    assert first.bootstrap.probability_of_loss == 0.0
    assert first.promotion_status is ValidationStatus.STAGED_CANDIDATE
    assert first.execution_allowed is False

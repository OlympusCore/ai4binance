"""Regression tests for conservative event-driven Spot backtesting."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.backtest import BacktestConfig, BacktestEngine, BacktestIntent
from ai4binance.backtest.models import BacktestExitReason
from ai4binance.backtest.storage import BacktestAuditWriter
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage.jsonl import JsonlAuditStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def candle(
    offset: int,
    open_price: str,
    high: str,
    low: str,
    close: str,
) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=NOW + timedelta(hours=offset),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


def intent(timestamp: datetime, signal_id: str = "signal-1") -> BacktestIntent:
    return BacktestIntent(
        signal_id=signal_id,
        timestamp=timestamp,
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        atr=Decimal("2"),
    )


def test_backtest_uses_closed_history_and_next_bar_open_fill() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "106", "99", "105"),
        candle(2, "105", "112", "104", "110"),
    )
    observed_lengths: list[int] = []

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        observed_lengths.append(len(history))
        assert history[:] == candles[: len(history)]
        with pytest.raises(IndexError):
            _ = history[len(history)]
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine().run(
        symbol="hotusdt",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert observed_lengths == [1, 2, 3]
    assert result.symbol == "HOTUSDT"
    assert result.trades[0].entry_timestamp == candles[1].timestamp
    assert result.trades[0].entry_price == Decimal("100.0500")
    assert result.trades[0].exit_price == Decimal("109.9450")
    assert result.trades[0].exit_reason is BacktestExitReason.TAKE_PROFIT_EXIT
    assert result.metrics.trade_count == 1
    assert result.metrics.buy_and_hold_return > 0.0


def test_trailing_stop_cannot_ratchet_and_trigger_on_same_bar() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "109", "98", "105"),
        candle(2, "105", "106", "101", "103"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        proposed = intent(history[-1].timestamp)
        return (
            replace(proposed, take_profit=Decimal("120")) if len(history) == 1 else None
        )

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    trade = result.trades[0]
    assert trade.exit_timestamp == candles[2].timestamp
    assert trade.exit_reason is BacktestExitReason.TRAILING_STOP_EXIT
    assert trade.exit_price == Decimal("101.9490")
    assert trade.closure_review.trailing_quality == "TRIGGERED"


def test_stop_first_ordering_and_fee_accounting_are_conservative() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "111", "94", "105"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    trade = result.trades[0]
    assert trade.exit_reason is BacktestExitReason.STOP_LOSS_EXIT
    assert trade.entry_fee_usdt == Decimal("0.1000500")
    assert trade.exit_fee_usdt == Decimal("0.0949525")
    assert trade.net_pnl_usdt < Decimal("-5")
    assert result.metrics.max_drawdown > 0.0
    assert result.metrics.win_rate == 0.0


def test_pending_open_position_and_end_of_data_are_audited() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "102", "99", "101"),
        candle(2, "101", "103", "100", "102"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp, f"signal-{len(history)}")

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert result.trades[0].exit_reason is BacktestExitReason.END_OF_DATA_EXIT
    assert result.trades[0].closure_review.ignored_signals == 2
    assert result.rejected_signals[0].blockers == ("POSITION_ALREADY_OPEN",)
    assert result.rejected_signals[-1].blockers == ("POSITION_ALREADY_OPEN",)
    assert result.audit_events[-1]["event_type"] == "END_OF_DATA_EXIT"


def test_mismatched_and_last_bar_signals_are_rejected() -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "101", "99", "100"),
    )

    def mismatched(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) == 1:
            return intent(NOW + timedelta(days=1))
        return intent(history[-1].timestamp, "last-bar")

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=mismatched,
    )

    assert result.rejected_signals[0].blockers == ("SIGNAL_TIMESTAMP_MISMATCH",)
    assert result.rejected_signals[1].blockers == ("NO_NEXT_BAR",)
    assert result.metrics.trade_count == 0
    assert result.metrics.profit_factor is None
    assert result.metrics.sharpe is None


@pytest.mark.parametrize(
    ("config", "next_open", "blocker"),
    [
        (
            BacktestConfig(),
            "90",
            "INVALID_NEXT_BAR_GEOMETRY",
        ),
        (
            BacktestConfig(initial_cash_usdt=Decimal("50")),
            "100",
            "INSUFFICIENT_BACKTEST_CASH",
        ),
    ],
)
def test_next_bar_fill_is_rejected_when_geometry_or_cash_changed(
    config: BacktestConfig,
    next_open: str,
    blocker: str,
) -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, next_open, "101", "89", "100"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine(config).run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )

    assert blocker in result.rejected_signals[0].blockers
    assert result.audit_events[0]["event_type"] == "ENTRY_REJECTED"
    assert result.metrics.trade_count == 0


def test_backtest_result_persists_as_redacted_jsonl(tmp_path: Path) -> None:
    candles = (
        candle(0, "100", "101", "99", "100"),
        candle(1, "100", "111", "99", "110"),
    )

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        return intent(history[-1].timestamp) if len(history) == 1 else None

    result = BacktestEngine().run(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles,
        signal_provider=provider,
    )
    output = tmp_path / "backtests.jsonl"
    BacktestAuditWriter(JsonlAuditStore(output)).append(result)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["event_type"] == "BACKTEST_RESULT"
    assert payload["payload"]["result"]["metrics"]["trade_count"] == 1
    assert payload["payload"]["result"]["trades"][0]["signal_id"] == "signal-1"


@pytest.mark.parametrize(
    "candles",
    [
        (candle(0, "100", "101", "99", "100"),),
        (
            candle(1, "100", "101", "99", "100"),
            candle(0, "100", "101", "99", "100"),
        ),
    ],
)
def test_backtest_rejects_insufficient_or_unsorted_data(
    candles: tuple[OHLCVCandle, ...],
) -> None:
    with pytest.raises(ValueError, match=r"at least two|strictly chronological"):
        BacktestEngine().run(
            symbol="HOTUSDT",
            timeframe="1h",
            candles=candles,
            signal_provider=lambda _history: None,
        )


def test_backtest_contracts_reject_unsafe_assumptions() -> None:
    with pytest.raises(ValueError, match="initial cash"):
        BacktestConfig(initial_cash_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="fee_ratio"):
        BacktestConfig(fee_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="slippage_ratio"):
        BacktestConfig(slippage_ratio=Decimal("0.1"))
    with pytest.raises(ValueError, match="trailing_multiplier"):
        BacktestConfig(trailing_multiplier=Decimal("0"))
    with pytest.raises(ValueError, match="tick_size"):
        BacktestConfig(tick_size=Decimal("0"))
    with pytest.raises(ValueError, match="signal identity"):
        replace(intent(NOW), signal_id="")
    with pytest.raises(ValueError, match="timeframe"):
        BacktestEngine().run(
            symbol="HOTUSDT",
            timeframe="",
            candles=(
                candle(0, "100", "101", "99", "100"),
                candle(1, "100", "101", "99", "100"),
            ),
            signal_provider=lambda _history: None,
        )

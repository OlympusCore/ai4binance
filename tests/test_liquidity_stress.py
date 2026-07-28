from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.backtest.engine import BacktestEngine
from ai4binance.backtest.liquidity import LiquidityStressConfig, assess_liquidity_fill
from ai4binance.backtest.models import BacktestConfig, BacktestIntent
from ai4binance.schemas import OHLCVCandle


def _candles(volume: Decimal) -> tuple[OHLCVCandle, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        OHLCVCandle(
            timestamp=start + timedelta(hours=index),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=volume,
        )
        for index in range(3)
    )


def test_liquidity_fill_caps_quantity_and_reports_remainder() -> None:
    decision = assess_liquidity_fill(
        requested_quantity=Decimal("10"),
        candle_volume=Decimal("500"),
        config=LiquidityStressConfig(max_volume_participation=Decimal("0.01")),
    )

    assert decision.filled_quantity == Decimal("5.00")
    assert decision.remaining_quantity == Decimal("5.00")
    assert decision.blockers == ()
    assert decision.execution_allowed is False


def test_backtest_records_partial_entry_fill() -> None:
    candles = _candles(Decimal("500"))

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return BacktestIntent(
            signal_id="partial",
            timestamp=history[-1].timestamp,
            stop_loss=Decimal("8"),
            take_profit=Decimal("12"),
            atr=Decimal("1"),
        )

    result = BacktestEngine(
        BacktestConfig(
            quantity=Decimal("10"),
            liquidity_stress=LiquidityStressConfig(
                max_volume_participation=Decimal("0.01")
            ),
        )
    ).run(symbol="HOTUSDT", timeframe="1h", candles=candles, signal_provider=provider)

    assert result.trades[0].quantity == Decimal("5.00")
    assert result.audit_events[0]["event_type"] == "ENTRY_PARTIALLY_FILLED"


def test_backtest_rejects_too_small_partial_fill() -> None:
    candles = _candles(Decimal("10"))

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) != 1:
            return None
        return BacktestIntent(
            signal_id="blocked",
            timestamp=history[-1].timestamp,
            stop_loss=Decimal("8"),
            take_profit=Decimal("12"),
            atr=Decimal("1"),
        )

    result = BacktestEngine(
        BacktestConfig(
            quantity=Decimal("10"),
            liquidity_stress=LiquidityStressConfig(
                max_volume_participation=Decimal("0.01"),
                minimum_fill_ratio=Decimal("0.25"),
            ),
        )
    ).run(symbol="HOTUSDT", timeframe="1h", candles=candles, signal_provider=provider)

    assert result.trades == ()
    assert result.rejected_signals[0].blockers == (
        "LIQUIDITY_PARTIAL_FILL_BELOW_MINIMUM",
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_volume_participation": Decimal("0")},
        {"minimum_fill_ratio": Decimal("1.1")},
        {"impact_ratio": Decimal("0.02")},
    ],
)
def test_liquidity_config_rejects_invalid_ratios(kwargs: dict[str, Decimal]) -> None:
    with pytest.raises(ValueError, match=r"liquidity|volume|fill|impact"):
        LiquidityStressConfig(**kwargs)


def test_liquidity_fill_rejects_zero_volume_and_invalid_request() -> None:
    decision = assess_liquidity_fill(
        requested_quantity=Decimal("1"),
        candle_volume=Decimal("0"),
        config=LiquidityStressConfig(),
    )
    assert decision.blockers == ("LIQUIDITY_FILL_UNAVAILABLE",)
    with pytest.raises(ValueError, match="requested"):
        assess_liquidity_fill(
            requested_quantity=Decimal("0"),
            candle_volume=Decimal("1"),
            config=LiquidityStressConfig(),
        )

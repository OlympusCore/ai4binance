"""Transparent deterministic indicator primitive tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.indicators import (
    atr,
    clamp,
    closes,
    confirmed_swings,
    cross_over,
    cross_under,
    ema,
    ema_series,
    ohlc4,
    relative_volume,
    rsi,
    session_vwap,
    supertrend,
)
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def candles(count: int, *, step: Decimal = Decimal("1")) -> tuple[OHLCVCandle, ...]:
    rows = []
    for index in range(count):
        close = Decimal("100") + (Decimal(index) * step)
        rows.append(
            OHLCVCandle(
                timestamp=NOW + timedelta(hours=index),
                open=close - Decimal("0.5"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=Decimal("100") + Decimal(index),
            )
        )
    return tuple(rows)


def test_ema_atr_rsi_and_relative_volume_known_series() -> None:
    rows = candles(30)
    assert ema((Decimal("1"), Decimal("2"), Decimal("3")), 3) == Decimal("2")
    assert atr(rows, 14) == Decimal("2")
    assert rsi(closes(rows), 14) == Decimal("100")
    assert rsi((Decimal("1"),) * 15, 14) == Decimal("50")
    falling = tuple(Decimal(20 - index) for index in range(15))
    assert rsi(falling, 14) == Decimal("0")
    assert relative_volume(rows, 20) > Decimal("1")
    assert ema_series((Decimal("1"), Decimal("2"), Decimal("3")), 2) == (
        Decimal("1.5"),
        Decimal("2.5"),
    )


def test_ohlc4_crosses_and_supertrend_are_closed_candle_deterministic() -> None:
    rows = candles(30)
    assert ohlc4(rows[0]) == sum(
        (rows[0].open, rows[0].high, rows[0].low, rows[0].close), Decimal("0")
    ) / Decimal("4")
    assert cross_over(Decimal("1"), Decimal("1"), Decimal("2"), Decimal("1"))
    assert not cross_over(Decimal("2"), Decimal("1"), Decimal("3"), Decimal("1"))
    assert cross_under(Decimal("1"), Decimal("1"), Decimal("0"), Decimal("1"))
    points = supertrend(rows)
    assert len(points) == 16
    assert points[-1].direction == 1
    assert points[-1].atr == Decimal("2")
    assert points[-1].band < rows[-1].close


def test_confirmed_swings_excludes_unconfirmed_right_edge() -> None:
    values = (1, 2, 5, 2, 1, 2, 6)
    rows = tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=Decimal(value),
            high=Decimal(value),
            low=Decimal(value),
            close=Decimal(value),
            volume=Decimal("1"),
        )
        for index, value in enumerate(values)
    )
    swings = confirmed_swings(rows)
    assert any(point.index == 2 and point.kind == "HIGH" for point in swings)
    assert all(point.index != 6 for point in swings)


def test_new_trend_primitives_reject_unsafe_parameters() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        supertrend(candles(20), multiplier=Decimal("0"))
    with pytest.raises(ValueError, match="swing windows"):
        confirmed_swings(candles(5), left=0)
    with pytest.raises(ValueError, match=r"left \+ right"):
        confirmed_swings(candles(4))


def test_relative_volume_handles_zero_baseline() -> None:
    rows = tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=Decimal("1") if index == 2 else Decimal("0"),
        )
        for index in range(3)
    )
    assert relative_volume(rows, 2) == Decimal("0")


@pytest.mark.parametrize(
    "operation",
    [
        lambda: ema((Decimal("1"),), 2),
        lambda: atr(candles(2), 2),
        lambda: rsi((Decimal("1"),), 14),
        lambda: relative_volume(candles(2), 2),
    ],
)
def test_indicators_reject_insufficient_warmup(operation: object) -> None:
    assert callable(operation)
    with pytest.raises(ValueError, match=r"requires|indicator"):
        operation()


def test_clamp_is_deterministic() -> None:
    assert clamp(Decimal("2"), Decimal("0"), Decimal("1")) == Decimal("1")
    assert clamp(Decimal("-1"), Decimal("0"), Decimal("1")) == Decimal("0")


def test_session_vwap_uses_explicit_boundary_and_hlc3() -> None:
    rows = candles(3)
    expected = (
        ((rows[1].high + rows[1].low + rows[1].close) / Decimal("3")) * rows[1].volume
        + ((rows[2].high + rows[2].low + rows[2].close) / Decimal("3")) * rows[2].volume
    ) / (rows[1].volume + rows[2].volume)
    assert session_vwap(rows, rows[1].timestamp) == expected


def test_session_vwap_rejects_invalid_session_inputs() -> None:
    rows = candles(2)
    with pytest.raises(ValueError, match="timezone-aware"):
        session_vwap(rows, datetime(2026, 7, 11))
    with pytest.raises(ValueError, match="selected session"):
        session_vwap(rows, NOW + timedelta(days=1))
    zero_volume = tuple(
        OHLCVCandle(
            timestamp=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=Decimal("0"),
        )
        for row in rows
    )
    with pytest.raises(ValueError, match="positive cumulative volume"):
        session_vwap(zero_volume, NOW)

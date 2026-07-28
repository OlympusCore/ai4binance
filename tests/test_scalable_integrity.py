from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.integrity import IntegrityStatus
from ai4binance.validation.scalable_integrity import (
    analyze_scalable_lookahead,
    logarithmic_checkpoints,
)


def _candles(count: int) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            datetime(2020, 1, 1, tzinfo=UTC) + timedelta(hours=index),
            Decimal(index + 10),
            Decimal(index + 11),
            Decimal(index + 9),
            Decimal(index + 10),
            Decimal("100"),
        )
        for index in range(count)
    )


def test_logarithmic_checkpoints_are_sparse_with_dense_tail() -> None:
    checkpoints = logarithmic_checkpoints(10_000, minimum_history=32, tail_points=8)

    assert len(checkpoints) < 32
    assert checkpoints[-1] == 9_998
    assert checkpoints[-8:] == tuple(range(9_991, 9_999))


def test_scalable_integrity_passes_causal_indicator_with_bounded_calls() -> None:
    calls = 0

    def causal(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        nonlocal calls
        calls += 1
        return tuple(float(item.close) for item in values)

    report = analyze_scalable_lookahead(_candles(1_024), causal)

    assert report.status is IntegrityStatus.PASSED
    assert report.evaluation_count < 40
    assert calls == report.evaluation_count + 1
    assert report.execution_allowed is False


def test_scalable_integrity_refines_first_suspicious_interval() -> None:
    def future_mean(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        mean = sum(float(item.close) for item in values) / len(values)
        return tuple(mean for _item in values)

    report = analyze_scalable_lookahead(_candles(256), future_mean)

    assert report.status is IntegrityStatus.BLOCKED
    assert report.first_violation_index == 31
    assert report.blockers == ("LOOKAHEAD_BIAS_DETECTED",)


def test_scalable_integrity_blocks_output_shape_drift() -> None:
    report = analyze_scalable_lookahead(_candles(64), lambda _values: ())

    assert report.blockers == ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)
    assert report.promotion_allowed is False


def test_scalable_integrity_blocks_prefix_shape_drift_and_invalid_inputs() -> None:
    def prefix_drift(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        if len(values) == 64:
            return tuple(float(item.close) for item in values)
        return ()

    report = analyze_scalable_lookahead(_candles(64), prefix_drift)
    assert report.blockers == ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)
    with pytest.raises(ValueError, match="dimensions"):
        logarithmic_checkpoints(10, minimum_history=10)
    with pytest.raises(ValueError, match="tolerance"):
        analyze_scalable_lookahead(_candles(64), prefix_drift, tolerance=-1)
    duplicate = (*_candles(63), _candles(63)[-1])
    with pytest.raises(ValueError, match="chronological"):
        analyze_scalable_lookahead(duplicate, prefix_drift)

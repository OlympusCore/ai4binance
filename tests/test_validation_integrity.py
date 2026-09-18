"""Causal feature-integrity gate tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.schemas import OHLCVCandle
from ai4binance.validation import (
    FeatureObservation,
    IndicatorIntegritySuite,
    IntegrityStatus,
    analyze_indicator_integrity,
    analyze_lookahead,
    analyze_recursive_stability,
    analyze_temporal_lineage,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def candles(count: int = 6) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=Decimal(100 + index),
            high=Decimal(101 + index),
            low=Decimal(99 + index),
            close=Decimal(100 + index),
            volume=Decimal("1000"),
        )
        for index in range(count)
    )


def causal_close(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
    return tuple(float(item.close) for item in values)


def future_mean(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
    mean = sum(float(item.close) for item in values) / len(values)
    return tuple(mean for _item in values)


def test_lookahead_gate_passes_causal_and_blocks_future_dependent_output() -> None:
    passed = analyze_lookahead(candles(), causal_close)
    assert passed.status is IntegrityStatus.PASSED
    assert passed.checked_points == 4

    blocked = analyze_lookahead(candles(), future_mean)
    assert blocked.status is IntegrityStatus.BLOCKED
    assert blocked.blockers == ("LOOKAHEAD_BIAS_DETECTED",)
    assert blocked.violation_indices
    assert blocked.execution_allowed is False


def test_recursive_stability_detects_warmup_sensitive_formula() -> None:
    stable = analyze_recursive_stability(candles(), causal_close)
    assert stable.blockers == ()

    def cumulative(values: tuple[OHLCVCandle, ...]) -> tuple[float | None, ...]:
        total = 0.0
        output: list[float] = []
        for item in values:
            total += float(item.close)
            output.append(total)
        return tuple(output)

    unstable = analyze_recursive_stability(candles(), cumulative)
    assert unstable.blockers == ("RECURSIVE_INDICATOR_INSTABILITY",)
    assert unstable.maximum_drift > 0.0


def test_combined_integrity_suite_controls_promotion_without_execution() -> None:
    passed = analyze_indicator_integrity(candles(), causal_close)
    assert passed.status is IntegrityStatus.PASSED
    assert passed.blockers == ()
    assert passed.promotion_allowed is True
    assert passed.execution_allowed is False

    blocked = analyze_indicator_integrity(candles(), future_mean)
    assert blocked.status is IntegrityStatus.BLOCKED
    assert "LOOKAHEAD_BIAS_DETECTED" in blocked.blockers
    assert "RECURSIVE_INDICATOR_INSTABILITY" in blocked.blockers
    assert blocked.promotion_allowed is False


def test_combined_integrity_suite_contract_is_fail_closed() -> None:
    report = analyze_lookahead(candles(), causal_close)
    with pytest.raises(ValueError, match="blockers must match"):
        IndicatorIntegritySuite(
            report,
            report,
            IntegrityStatus.BLOCKED,
            ("UNRELATED",),
            False,
        )
    with pytest.raises(ValueError, match="status must match"):
        IndicatorIntegritySuite(
            report,
            report,
            IntegrityStatus.BLOCKED,
            (),
            False,
        )
    with pytest.raises(ValueError, match="promotion must fail closed"):
        IndicatorIntegritySuite(
            report,
            report,
            IntegrityStatus.PASSED,
            (),
            False,
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        IndicatorIntegritySuite(
            report,
            report,
            IntegrityStatus.PASSED,
            (),
            True,
            True,
        )


def test_temporal_lineage_rejects_future_or_late_information() -> None:
    valid = FeatureObservation("close", NOW, NOW, NOW, 100.0)
    future = FeatureObservation(
        "news", NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=1), 1.0
    )
    report = analyze_temporal_lineage((valid, future))
    assert report.violation_indices == (1,)
    assert report.blockers == ("FEATURE_AVAILABILITY_VIOLATION",)


def test_integrity_contracts_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="sufficient history"):
        analyze_lookahead(candles(2), causal_close)
    with pytest.raises(ValueError, match="zero warmup"):
        analyze_recursive_stability(candles(), causal_close, warmup_offsets=(1, 2))
    mismatch = analyze_lookahead(candles(), lambda _items: ())
    assert mismatch.blockers == ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)
    with pytest.raises(ValueError, match="timezone-aware"):
        FeatureObservation("x", NOW.replace(tzinfo=None), NOW, NOW, 1.0)
    with pytest.raises(ValueError, match="feature name"):
        replace(FeatureObservation("x", NOW, NOW, NOW, 1.0), feature_name=" ")
    with pytest.raises(ValueError, match="finite"):
        FeatureObservation("x", NOW, NOW, NOW, float("nan"))
    with pytest.raises(ValueError, match="ordered"):
        analyze_recursive_stability(candles(), causal_close, warmup_offsets=(0, 2, 1))
    with pytest.raises(ValueError, match="insufficient candles"):
        analyze_recursive_stability(candles(), causal_close, warmup_offsets=(0, 5))
    with pytest.raises(ValueError, match="tolerance"):
        analyze_lookahead(candles(), causal_close, tolerance=-1.0)


def test_integrity_handles_none_and_incremental_length_mismatches() -> None:
    def none_mismatch(
        values: tuple[OHLCVCandle, ...],
    ) -> tuple[float | None, ...]:
        output: list[float | None] = [float(item.close) for item in values]
        if len(values) < 6:
            output[-1] = None
        return tuple(output)

    report = analyze_lookahead(candles(), none_mismatch)
    assert report.blockers == ("LOOKAHEAD_BIAS_DETECTED",)

    def prefix_mismatch(
        values: tuple[OHLCVCandle, ...],
    ) -> tuple[float | None, ...]:
        return causal_close(values) if len(values) == 6 else ()

    mismatch = analyze_lookahead(candles(), prefix_mismatch)
    assert mismatch.blockers == ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)

    recursive_mismatch = analyze_recursive_stability(candles(), prefix_mismatch)
    assert recursive_mismatch.blockers == ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)

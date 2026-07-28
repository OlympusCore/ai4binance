"""Causal feature-integrity gates inspired by mature backtest toolchains."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

from ai4binance.schemas import OHLCVCandle

IndicatorFunction = Callable[[tuple[OHLCVCandle, ...]], tuple[float | None, ...]]


class IntegrityStatus(StrEnum):
    """Fail-closed integrity outcome."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    """One point-in-time feature value with explicit source lineage."""

    feature_name: str
    observed_at: datetime
    available_at: datetime
    max_source_timestamp: datetime
    value: float | None

    def __post_init__(self) -> None:
        timestamps = (self.observed_at, self.available_at, self.max_source_timestamp)
        if not self.feature_name.strip():
            raise ValueError("feature name is required")
        if any(item.tzinfo is None or item.utcoffset() is None for item in timestamps):
            raise ValueError("feature lineage timestamps must be timezone-aware")
        if self.value is not None and not isfinite(self.value):
            raise ValueError("feature value must be finite when present")


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """Auditable report which can block promotion but never authorize execution."""

    status: IntegrityStatus
    checked_points: int
    violation_indices: tuple[int, ...]
    maximum_drift: float
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.checked_points < 0 or self.maximum_drift < 0.0:
            raise ValueError("integrity report counts and drift cannot be negative")
        if self.status is IntegrityStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked integrity report requires blockers")
        if self.status is IntegrityStatus.PASSED and self.blockers:
            raise ValueError("passed integrity report cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("integrity evidence cannot authorize execution")


@dataclass(frozen=True, slots=True)
class IndicatorIntegritySuite:
    """Combined promotion gate for causal and warmup-stable indicators."""

    lookahead: IntegrityReport
    recursive_stability: IntegrityReport
    status: IntegrityStatus
    blockers: tuple[str, ...]
    promotion_allowed: bool
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        expected_blockers = tuple(
            dict.fromkeys(
                (*self.lookahead.blockers, *self.recursive_stability.blockers)
            )
        )
        if self.blockers != expected_blockers:
            raise ValueError("integrity suite blockers must match component reports")
        expected_status = (
            IntegrityStatus.BLOCKED if self.blockers else IntegrityStatus.PASSED
        )
        if self.status is not expected_status:
            raise ValueError("integrity suite status must match blockers")
        if self.promotion_allowed is not (self.status is IntegrityStatus.PASSED):
            raise ValueError("integrity suite promotion must fail closed")
        if self.execution_allowed:
            raise ValueError("integrity evidence cannot authorize execution")


def analyze_temporal_lineage(
    observations: tuple[FeatureObservation, ...],
) -> IntegrityReport:
    """Reject features that use or expose information after the observation time."""
    violations = tuple(
        index
        for index, item in enumerate(observations)
        if item.max_source_timestamp > item.observed_at
        or item.available_at > item.observed_at
    )
    blockers = ("FEATURE_AVAILABILITY_VIOLATION",) if violations else ()
    return _report(len(observations), violations, 0.0, blockers)


def analyze_lookahead(
    candles: tuple[OHLCVCandle, ...],
    compute: IndicatorFunction,
    *,
    minimum_history: int = 2,
    tolerance: float = 1e-12,
) -> IntegrityReport:
    """Compare batch values with values available from each historical prefix."""
    _validate_analysis_inputs(candles, minimum_history, tolerance)
    batch = compute(candles)
    if len(batch) != len(candles):
        return _report(0, (), 0.0, ("INDICATOR_OUTPUT_LENGTH_MISMATCH",))

    violations: list[int] = []
    maximum_drift = 0.0
    checked = 0
    for index in range(minimum_history - 1, len(candles) - 1):
        prefix = compute(candles[: index + 1])
        if len(prefix) != index + 1:
            return _report(
                checked,
                tuple(violations),
                maximum_drift,
                ("INDICATOR_OUTPUT_LENGTH_MISMATCH",),
            )
        expected = batch[index]
        observed = prefix[-1]
        checked += 1
        if expected is None or observed is None:
            if expected is not observed:
                violations.append(index)
            continue
        drift = abs(expected - observed)
        maximum_drift = max(maximum_drift, drift)
        if drift > tolerance:
            violations.append(index)
    blockers = ("LOOKAHEAD_BIAS_DETECTED",) if violations else ()
    return _report(checked, tuple(violations), maximum_drift, blockers)


def analyze_recursive_stability(
    candles: tuple[OHLCVCandle, ...],
    compute: IndicatorFunction,
    *,
    warmup_offsets: tuple[int, ...] = (0, 1, 2),
    tolerance: float = 1e-6,
) -> IntegrityReport:
    """Measure endpoint drift when an indicator starts from different warmups."""
    _validate_analysis_inputs(candles, 2, tolerance)
    if not warmup_offsets or warmup_offsets[0] != 0:
        raise ValueError("recursive analysis requires a zero warmup baseline")
    if tuple(sorted(set(warmup_offsets))) != warmup_offsets:
        raise ValueError("warmup offsets must be unique and ordered")
    if warmup_offsets[-1] >= len(candles) - 1:
        raise ValueError("warmup offsets leave insufficient candles")

    endpoint_values: list[float | None] = []
    for offset in warmup_offsets:
        output = compute(candles[offset:])
        if len(output) != len(candles) - offset:
            return _report(0, (), 0.0, ("INDICATOR_OUTPUT_LENGTH_MISMATCH",))
        endpoint_values.append(output[-1])
    baseline = endpoint_values[0]
    violations: list[int] = []
    maximum_drift = 0.0
    for index, value in enumerate(endpoint_values[1:], start=1):
        if baseline is None or value is None:
            if baseline is not value:
                violations.append(index)
            continue
        drift = abs(baseline - value)
        maximum_drift = max(maximum_drift, drift)
        if drift > tolerance:
            violations.append(index)
    blockers = ("RECURSIVE_INDICATOR_INSTABILITY",) if violations else ()
    return _report(len(endpoint_values), tuple(violations), maximum_drift, blockers)


def analyze_indicator_integrity(
    candles: tuple[OHLCVCandle, ...],
    compute: IndicatorFunction,
    *,
    minimum_history: int = 2,
    lookahead_tolerance: float = 1e-12,
    warmup_offsets: tuple[int, ...] = (0, 1, 2),
    recursive_tolerance: float = 1e-6,
) -> IndicatorIntegritySuite:
    """Run both independent diagnostics and combine them into one fail-closed gate."""
    lookahead = analyze_lookahead(
        candles,
        compute,
        minimum_history=minimum_history,
        tolerance=lookahead_tolerance,
    )
    recursive = analyze_recursive_stability(
        candles,
        compute,
        warmup_offsets=warmup_offsets,
        tolerance=recursive_tolerance,
    )
    blockers = tuple(dict.fromkeys((*lookahead.blockers, *recursive.blockers)))
    status = IntegrityStatus.BLOCKED if blockers else IntegrityStatus.PASSED
    return IndicatorIntegritySuite(
        lookahead=lookahead,
        recursive_stability=recursive,
        status=status,
        blockers=blockers,
        promotion_allowed=status is IntegrityStatus.PASSED,
    )


def _validate_analysis_inputs(
    candles: tuple[OHLCVCandle, ...], minimum_history: int, tolerance: float
) -> None:
    if minimum_history < 2 or len(candles) < minimum_history + 1:
        raise ValueError("integrity analysis requires sufficient history")
    if not isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("integrity tolerance must be finite and non-negative")
    timestamps = tuple(candle.timestamp for candle in candles)
    if timestamps != tuple(sorted(set(timestamps))):
        raise ValueError("integrity candles must be unique and chronological")


def _report(
    checked: int,
    violations: tuple[int, ...],
    maximum_drift: float,
    blockers: tuple[str, ...],
) -> IntegrityReport:
    return IntegrityReport(
        status=IntegrityStatus.BLOCKED if blockers else IntegrityStatus.PASSED,
        checked_points=checked,
        violation_indices=violations,
        maximum_drift=maximum_drift,
        blockers=blockers,
    )

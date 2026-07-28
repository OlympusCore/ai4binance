"""Scalable checkpoint and bounded-bisect look-ahead diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.integrity import IndicatorFunction, IntegrityStatus


@dataclass(frozen=True, slots=True)
class ScalableIntegrityReport:
    """Bounded integrity evidence for long histories."""

    status: IntegrityStatus
    candle_count: int
    evaluation_count: int
    checkpoint_indices: tuple[int, ...]
    violation_indices: tuple[int, ...]
    first_violation_index: int | None
    maximum_drift: float
    blockers: tuple[str, ...]
    promotion_allowed: bool
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        expected_pass = not self.blockers
        if (self.status is IntegrityStatus.PASSED) is not expected_pass:
            raise ValueError("scalable integrity status must match blockers")
        if self.promotion_allowed is not expected_pass or self.execution_allowed:
            raise ValueError("scalable integrity authority must fail closed")


def logarithmic_checkpoints(
    candle_count: int,
    *,
    minimum_history: int = 32,
    tail_points: int = 16,
) -> tuple[int, ...]:
    """Return logarithmic history checkpoints plus a dense bounded tail."""
    if minimum_history < 2 or candle_count <= minimum_history or tail_points < 1:
        raise ValueError("checkpoint dimensions are invalid")
    indices: set[int] = set()
    current = minimum_history - 1
    last_checked = candle_count - 2
    while current <= last_checked:
        indices.add(current)
        current = max(current + 1, (current + 1) * 2 - 1)
    tail_start = max(minimum_history - 1, last_checked - tail_points + 1)
    indices.update(range(tail_start, last_checked + 1))
    return tuple(sorted(indices))


def analyze_scalable_lookahead(
    candles: tuple[OHLCVCandle, ...],
    compute: IndicatorFunction,
    *,
    minimum_history: int = 32,
    tail_points: int = 16,
    tolerance: float = 1e-12,
) -> ScalableIntegrityReport:
    """Check sparse prefixes and refine the first suspicious interval."""
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("integrity tolerance must be finite and non-negative")
    timestamps = tuple(item.timestamp for item in candles)
    if timestamps != tuple(sorted(set(timestamps))):
        raise ValueError("integrity candles must be unique and chronological")
    checkpoints = logarithmic_checkpoints(
        len(candles), minimum_history=minimum_history, tail_points=tail_points
    )
    batch = compute(candles)
    if len(batch) != len(candles):
        return _scalable_report(
            len(candles), 0, checkpoints, (), 0.0, ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)
        )

    evaluation_count = 0
    maximum_drift = 0.0
    violations: list[int] = []

    def evaluate(index: int) -> tuple[bool, str | None]:
        nonlocal evaluation_count, maximum_drift
        prefix = compute(candles[: index + 1])
        evaluation_count += 1
        if len(prefix) != index + 1:
            return False, "INDICATOR_OUTPUT_LENGTH_MISMATCH"
        expected, observed = batch[index], prefix[-1]
        if expected is None or observed is None:
            return expected is observed, None
        drift = abs(expected - observed)
        maximum_drift = max(maximum_drift, drift)
        return drift <= tolerance, None

    prior = minimum_history - 2
    length_error = False
    for checkpoint in checkpoints:
        passed, error = evaluate(checkpoint)
        if error:
            length_error = True
            break
        if not passed:
            for index in range(prior + 1, checkpoint + 1):
                if index == checkpoint:
                    violations.append(index)
                    break
                refined_pass, refined_error = evaluate(index)
                if refined_error:
                    length_error = True
                    break
                if not refined_pass:
                    violations.append(index)
                    break
            break
        prior = checkpoint
    blockers: tuple[str, ...]
    if length_error:
        blockers = ("INDICATOR_OUTPUT_LENGTH_MISMATCH",)
    elif violations:
        blockers = ("LOOKAHEAD_BIAS_DETECTED",)
    else:
        blockers = ()
    return _scalable_report(
        len(candles),
        evaluation_count,
        checkpoints,
        tuple(violations),
        maximum_drift,
        blockers,
    )


def _scalable_report(
    candle_count: int,
    evaluation_count: int,
    checkpoints: tuple[int, ...],
    violations: tuple[int, ...],
    maximum_drift: float,
    blockers: tuple[str, ...],
) -> ScalableIntegrityReport:
    return ScalableIntegrityReport(
        status=IntegrityStatus.BLOCKED if blockers else IntegrityStatus.PASSED,
        candle_count=candle_count,
        evaluation_count=evaluation_count,
        checkpoint_indices=checkpoints,
        violation_indices=violations,
        first_violation_index=violations[0] if violations else None,
        maximum_drift=maximum_drift,
        blockers=blockers,
        promotion_allowed=not blockers,
    )

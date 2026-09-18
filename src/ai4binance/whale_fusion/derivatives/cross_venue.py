"""Supplementary multi-venue coverage and robust direction research evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class VenueObservation:
    venue: str
    observed_at: datetime
    price: Decimal
    return_bps: Decimal
    spread_bps: Decimal
    liquidity_weight: Decimal
    reliability: Decimal
    sequence_valid: bool = True
    fields_valid: bool = True

    def __post_init__(self) -> None:
        values = (
            self.price,
            self.return_bps,
            self.spread_bps,
            self.liquidity_weight,
            self.reliability,
        )
        if (
            not self.venue.strip()
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
            or any(not value.is_finite() for value in values)
            or self.price <= ZERO
            or self.spread_bps < ZERO
            or not ZERO <= self.liquidity_weight <= ONE
            or not ZERO <= self.reliability <= ONE
        ):
            raise ValueError("venue observation is invalid")


@dataclass(frozen=True, slots=True)
class CrossVenueResearchResult:
    score: Decimal | None
    coverage_ratio: Decimal
    valid_venues: tuple[str, ...]
    excluded_venues: tuple[str, ...]
    maximum_weight_ratio: Decimal
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not ZERO <= self.coverage_ratio <= ONE
            or not ZERO <= self.maximum_weight_ratio <= ONE
            or (self.score is not None and not -ONE <= self.score <= ONE)
            or self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("cross-venue research result is invalid")


@dataclass(frozen=True, slots=True)
class CrossVenueResearchEngine:
    maximum_age_seconds: int = 120
    minimum_valid_venues: int = 3
    minimum_coverage_ratio: Decimal = Decimal("0.60")
    maximum_venue_weight_ratio: Decimal = Decimal("0.60")

    def __post_init__(self) -> None:
        if (
            self.maximum_age_seconds <= 0
            or self.minimum_valid_venues < 2
            or not ZERO < self.minimum_coverage_ratio <= ONE
            or not ZERO < self.maximum_venue_weight_ratio <= ONE
        ):
            raise ValueError("cross-venue policy is invalid")

    def evaluate(
        self,
        observations: tuple[VenueObservation, ...],
        now: datetime,
    ) -> CrossVenueResearchResult:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("evaluation timestamp must be timezone-aware")
        if len({item.venue for item in observations}) != len(observations):
            raise ValueError("venue observations must be unique")
        valid: list[VenueObservation] = []
        excluded: list[str] = []
        blockers: list[str] = []
        for item in observations:
            age = (now - item.observed_at).total_seconds()
            if age < 0:
                blockers.append("VENUE_TIMESTAMP_IN_FUTURE")
                excluded.append(item.venue)
            elif age > self.maximum_age_seconds:
                excluded.append(item.venue)
            elif not item.sequence_valid:
                blockers.append("VENUE_SEQUENCE_INVALID")
                excluded.append(item.venue)
            elif not item.fields_valid:
                blockers.append("VENUE_FIELDS_INVALID")
                excluded.append(item.venue)
            else:
                valid.append(item)
        coverage = (
            Decimal(len(valid)) / Decimal(len(observations)) if observations else ZERO
        )
        if len(valid) < self.minimum_valid_venues:
            blockers.append("INSUFFICIENT_VALID_VENUES")
        if coverage < self.minimum_coverage_ratio:
            blockers.append("MULTI_VENUE_COVERAGE_BELOW_POLICY")
        weighted: list[tuple[VenueObservation, Decimal]] = []
        for item in valid:
            spread_quality = ONE / (ONE + (item.spread_bps / Decimal("10")))
            weight = item.liquidity_weight * item.reliability * spread_quality
            if weight > ZERO:
                weighted.append((item, weight))
        total_weight = sum((weight for _, weight in weighted), ZERO)
        maximum_weight = (
            max((weight for _, weight in weighted), default=ZERO) / total_weight
            if total_weight > ZERO
            else ZERO
        )
        if maximum_weight > self.maximum_venue_weight_ratio:
            blockers.append("MULTI_VENUE_CONCENTRATION_HIGH")
        score: Decimal | None = None
        if total_weight > ZERO and not blockers:
            score = (
                sum(
                    (
                        weight
                        * max(
                            -ONE,
                            min(ONE, item.return_bps / Decimal("100")),
                        )
                        for item, weight in weighted
                    ),
                    ZERO,
                )
                / total_weight
            )
        return CrossVenueResearchResult(
            score=score,
            coverage_ratio=coverage,
            valid_venues=tuple(sorted(item.venue for item in valid)),
            excluded_venues=tuple(sorted(excluded)),
            maximum_weight_ratio=maximum_weight,
            blockers=tuple(dict.fromkeys(blockers)),
        )


def robust_mad_zscores(
    values: tuple[Decimal, ...], *, minimum_history: int = 5
) -> tuple[Decimal, ...] | None:
    """Return deterministic median/MAD z-scores or fail closed on weak history."""
    if minimum_history < 3:
        raise ValueError("minimum history must be at least three")
    if len(values) < minimum_history:
        return None
    if any(not value.is_finite() for value in values):
        raise ValueError("MAD history must contain finite values")
    median = _median(values)
    mad = _median(tuple(abs(value - median) for value in values))
    if mad == ZERO:
        return tuple(ZERO for _ in values)
    scale = Decimal("1.4826") * mad
    return tuple((value - median) / scale for value in values)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")

"""Post-hoc opportunity outcome and missed-opportunity research contracts.

This module is intentionally outside the real-time opportunity domain so future
outcomes cannot enter candidate generation through a domain import.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from ai4binance.opportunity_intelligence import TIMEFRAME_DURATIONS
from ai4binance.schemas import OHLCVCandle

ZERO = Decimal("0")


class OpportunityOutcomeStatus(StrEnum):
    PENDING_HORIZON = "PENDING_HORIZON"
    EVALUATED = "EVALUATED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class OpportunityOutcomeClass(StrEnum):
    FAVORABLE = "FAVORABLE"
    ADVERSE = "ADVERSE"
    MIXED = "MIXED"
    INVALIDATED_FIRST = "INVALIDATED_FIRST"
    TARGET_FIRST = "TARGET_FIRST"
    UNRESOLVED = "UNRESOLVED"


class MissedOpportunityCause(StrEnum):
    UNIVERSE_EXCLUDED = "UNIVERSE_EXCLUDED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_STALE = "DATA_STALE"
    TIMEFRAME_ALIGNMENT_FAILED = "TIMEFRAME_ALIGNMENT_FAILED"
    FEATURE_NOT_TRIGGERED = "FEATURE_NOT_TRIGGERED"
    STRUCTURE_NOT_DETECTED = "STRUCTURE_NOT_DETECTED"
    PRICE_ACTION_NOT_DETECTED = "PRICE_ACTION_NOT_DETECTED"
    PATTERN_NOT_DETECTED = "PATTERN_NOT_DETECTED"
    CANDIDATE_SCORE_TOO_LOW = "CANDIDATE_SCORE_TOO_LOW"
    LIQUIDITY_BLOCKED = "LIQUIDITY_BLOCKED"
    RISK_BLOCKED = "RISK_BLOCKED"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    GOVERNANCE_BLOCKED = "GOVERNANCE_BLOCKED"
    PORTFOLIO_BLOCKED = "PORTFOLIO_BLOCKED"
    LATE_DETECTION = "LATE_DETECTION"
    EXPIRED_BEFORE_CONFIRMATION = "EXPIRED_BEFORE_CONFIRMATION"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"
    UNKNOWN = "UNKNOWN"


class MissedOpportunityAssessment(StrEnum):
    CORRECT_BLOCK = "CORRECT_BLOCK"
    POSSIBLE_FALSE_NEGATIVE = "POSSIBLE_FALSE_NEGATIVE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class OpportunityOutcomeEvaluation:
    outcome_id: str
    opportunity_id: str
    evaluation_horizon: int
    evaluation_started_at: datetime
    evaluation_completed_at: datetime | None
    reference_price: Decimal
    maximum_favorable_excursion: Decimal | None
    maximum_adverse_excursion: Decimal | None
    time_to_mfe_bars: int | None
    time_to_mae_bars: int | None
    invalidation_hit: bool | None
    target_reference_hit: bool | None
    target_before_invalidation: bool | None
    invalidation_before_target: bool | None
    potential_r_multiple: Decimal | None
    final_outcome_class: OpportunityOutcomeClass
    outcome_reason_codes: tuple[str, ...]
    dataset_id: str
    evaluation_version: str = "opportunity-outcome:v1"
    status: OpportunityOutcomeStatus = OpportunityOutcomeStatus.EVALUATED
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        identity = (
            self.outcome_id,
            self.opportunity_id,
            self.dataset_id,
            self.evaluation_version,
        )
        if any(not value.strip() for value in identity):
            raise ValueError("opportunity outcome identity is required")
        _require_aware(self.evaluation_started_at, "outcome start time")
        if self.evaluation_completed_at is not None:
            _require_aware(self.evaluation_completed_at, "outcome completion time")
        if self.evaluation_horizon < 1 or self.reference_price <= ZERO:
            raise ValueError("opportunity outcome horizon and price must be positive")
        if len(set(self.outcome_reason_codes)) != len(self.outcome_reason_codes):
            raise ValueError("opportunity outcome reasons must be unique")
        if any(not value.strip() for value in self.outcome_reason_codes):
            raise ValueError("opportunity outcome reasons cannot be blank")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity outcome cannot authorize execution")
        if self.status is OpportunityOutcomeStatus.EVALUATED:
            required = (
                self.evaluation_completed_at,
                self.maximum_favorable_excursion,
                self.maximum_adverse_excursion,
                self.time_to_mfe_bars,
                self.time_to_mae_bars,
            )
            if any(value is None for value in required):
                raise ValueError("evaluated opportunity outcome is incomplete")


@dataclass(frozen=True, slots=True)
class MissedOpportunityReview:
    missed_opportunity_id: str
    opportunity_id: str
    symbol: str
    market: str
    timeframe: str
    opportunity_window_start: datetime
    opportunity_window_end: datetime
    counterfactual_detection_time: datetime
    actual_detection_time: datetime | None
    cause: MissedOpportunityCause
    assessment: MissedOpportunityAssessment
    blocking_reason_codes: tuple[str, ...]
    candidate_rules_active: tuple[str, ...]
    policy_versions: tuple[str, ...]
    feature_versions: tuple[str, ...]
    lookahead_safe_reconstruction_status: str
    counterfactual_method_version: str = "missed-opportunity:v1"
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        identity = (
            self.missed_opportunity_id,
            self.opportunity_id,
            self.symbol,
            self.market,
            self.timeframe,
            self.lookahead_safe_reconstruction_status,
            self.counterfactual_method_version,
        )
        if any(not value.strip() for value in identity):
            raise ValueError("missed-opportunity identity is required")
        timestamps = (
            self.opportunity_window_start,
            self.opportunity_window_end,
            self.counterfactual_detection_time,
        )
        for value in timestamps:
            _require_aware(value, "missed-opportunity timestamp")
        if self.actual_detection_time is not None:
            _require_aware(self.actual_detection_time, "actual detection time")
        if self.opportunity_window_end < self.opportunity_window_start:
            raise ValueError("missed-opportunity window is invalid")
        if self.lookahead_safe_reconstruction_status != "VERIFIED":
            if self.assessment is not MissedOpportunityAssessment.UNRESOLVED:
                raise ValueError("unverified reconstruction must remain unresolved")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("missed-opportunity review cannot authorize execution")


def evaluate_opportunity_outcome(
    *,
    opportunity_id: str,
    direction: str,
    reference_price: Decimal,
    observed_at: datetime,
    future_candles: Sequence[OHLCVCandle],
    evaluation_horizon: int,
    dataset_id: str,
    timeframe: str,
    invalidation_price: Decimal | None = None,
    target_price: Decimal | None = None,
) -> OpportunityOutcomeEvaluation:
    """Evaluate only candles that became available strictly after observation."""
    _require_aware(observed_at, "opportunity observation time")
    if direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("opportunity outcome direction is invalid")
    if timeframe not in TIMEFRAME_DURATIONS:
        raise ValueError("opportunity outcome timeframe is unsupported")
    if evaluation_horizon < 1 or reference_price <= ZERO:
        raise ValueError("opportunity outcome inputs are invalid")
    duration = TIMEFRAME_DURATIONS[timeframe]
    eligible = tuple(
        candle
        for candle in future_candles
        if candle.timestamp >= observed_at and candle.timestamp + duration > observed_at
    )
    selected = eligible[:evaluation_horizon]
    outcome_id = _outcome_id(opportunity_id, dataset_id, evaluation_horizon)
    if len(selected) < evaluation_horizon:
        return OpportunityOutcomeEvaluation(
            outcome_id=outcome_id,
            opportunity_id=opportunity_id,
            evaluation_horizon=evaluation_horizon,
            evaluation_started_at=observed_at,
            evaluation_completed_at=None,
            reference_price=reference_price,
            maximum_favorable_excursion=None,
            maximum_adverse_excursion=None,
            time_to_mfe_bars=None,
            time_to_mae_bars=None,
            invalidation_hit=None,
            target_reference_hit=None,
            target_before_invalidation=None,
            invalidation_before_target=None,
            potential_r_multiple=None,
            final_outcome_class=OpportunityOutcomeClass.UNRESOLVED,
            outcome_reason_codes=("OUTCOME_HORIZON_INCOMPLETE",),
            dataset_id=dataset_id,
            status=OpportunityOutcomeStatus.PENDING_HORIZON,
        )
    bullish = direction == "BULLISH"
    favorable = tuple(
        candle.high - reference_price if bullish else reference_price - candle.low
        for candle in selected
    )
    adverse = tuple(
        reference_price - candle.low if bullish else candle.high - reference_price
        for candle in selected
    )
    mfe = max(ZERO, *favorable)
    mae = max(ZERO, *adverse)
    time_to_mfe = favorable.index(max(favorable)) + 1
    time_to_mae = adverse.index(max(adverse)) + 1
    invalidation_index = _first_level_hit(
        selected,
        invalidation_price,
        bullish=bullish,
        favorable=False,
    )
    target_index = _first_level_hit(
        selected,
        target_price,
        bullish=bullish,
        favorable=True,
    )
    invalidation_hit = invalidation_index is not None if invalidation_price else None
    target_hit = target_index is not None if target_price else None
    target_first = (
        target_index is not None
        and (invalidation_index is None or target_index < invalidation_index)
        if target_price is not None and invalidation_price is not None
        else None
    )
    invalidation_first = (
        invalidation_index is not None
        and (target_index is None or invalidation_index < target_index)
        if target_price is not None and invalidation_price is not None
        else None
    )
    risk = (
        abs(reference_price - invalidation_price)
        if invalidation_price is not None
        else None
    )
    potential_r = mfe / risk if risk is not None and risk > ZERO else None
    if target_first:
        outcome_class = OpportunityOutcomeClass.TARGET_FIRST
    elif invalidation_first:
        outcome_class = OpportunityOutcomeClass.INVALIDATED_FIRST
    elif mfe > mae:
        outcome_class = OpportunityOutcomeClass.FAVORABLE
    elif mae > mfe:
        outcome_class = OpportunityOutcomeClass.ADVERSE
    else:
        outcome_class = OpportunityOutcomeClass.MIXED
    return OpportunityOutcomeEvaluation(
        outcome_id=outcome_id,
        opportunity_id=opportunity_id,
        evaluation_horizon=evaluation_horizon,
        evaluation_started_at=observed_at,
        evaluation_completed_at=selected[-1].timestamp + duration,
        reference_price=reference_price,
        maximum_favorable_excursion=mfe,
        maximum_adverse_excursion=mae,
        time_to_mfe_bars=time_to_mfe,
        time_to_mae_bars=time_to_mae,
        invalidation_hit=invalidation_hit,
        target_reference_hit=target_hit,
        target_before_invalidation=target_first,
        invalidation_before_target=invalidation_first,
        potential_r_multiple=potential_r,
        final_outcome_class=outcome_class,
        outcome_reason_codes=(f"OUTCOME_{outcome_class.value}",),
        dataset_id=dataset_id,
    )


def classify_missed_opportunity(
    *,
    opportunity_id: str,
    symbol: str,
    market: str,
    timeframe: str,
    window_start: datetime,
    window_end: datetime,
    counterfactual_detection_time: datetime,
    actual_detection_time: datetime | None,
    cause: MissedOpportunityCause,
    outcome: OpportunityOutcomeEvaluation,
    blocking_reason_codes: tuple[str, ...] = (),
    candidate_rules_active: tuple[str, ...] = (),
    policy_versions: tuple[str, ...] = (),
    feature_versions: tuple[str, ...] = (),
) -> MissedOpportunityReview:
    """Classify post-hoc evidence without mislabeling profitable hard blocks."""
    if outcome.status is not OpportunityOutcomeStatus.EVALUATED:
        assessment = MissedOpportunityAssessment.UNRESOLVED
        reconstruction = "NOT_EVALUABLE"
    elif cause in {
        MissedOpportunityCause.RISK_BLOCKED,
        MissedOpportunityCause.VALIDATION_BLOCKED,
        MissedOpportunityCause.GOVERNANCE_BLOCKED,
        MissedOpportunityCause.PORTFOLIO_BLOCKED,
    }:
        assessment = (
            MissedOpportunityAssessment.CORRECT_BLOCK
            if outcome.final_outcome_class
            in {
                OpportunityOutcomeClass.INVALIDATED_FIRST,
                OpportunityOutcomeClass.ADVERSE,
            }
            else MissedOpportunityAssessment.UNRESOLVED
        )
        reconstruction = "VERIFIED"
    elif outcome.final_outcome_class in {
        OpportunityOutcomeClass.TARGET_FIRST,
        OpportunityOutcomeClass.FAVORABLE,
    }:
        assessment = MissedOpportunityAssessment.POSSIBLE_FALSE_NEGATIVE
        reconstruction = "VERIFIED"
    else:
        assessment = MissedOpportunityAssessment.CORRECT_BLOCK
        reconstruction = "VERIFIED"
    payload = "|".join((opportunity_id, cause.value, window_start.isoformat()))
    return MissedOpportunityReview(
        missed_opportunity_id=(
            f"missed-opportunity:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"
        ),
        opportunity_id=opportunity_id,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        opportunity_window_start=window_start,
        opportunity_window_end=window_end,
        counterfactual_detection_time=counterfactual_detection_time,
        actual_detection_time=actual_detection_time,
        cause=cause,
        assessment=assessment,
        blocking_reason_codes=blocking_reason_codes,
        candidate_rules_active=candidate_rules_active,
        policy_versions=policy_versions,
        feature_versions=feature_versions,
        lookahead_safe_reconstruction_status=reconstruction,
        evidence_refs=(f"outcome:{outcome.outcome_id}",),
    )


def _first_level_hit(
    candles: Sequence[OHLCVCandle],
    level: Decimal | None,
    *,
    bullish: bool,
    favorable: bool,
) -> int | None:
    if level is None:
        return None
    for index, candle in enumerate(candles):
        if favorable:
            hit = candle.high >= level if bullish else candle.low <= level
        else:
            hit = candle.low <= level if bullish else candle.high >= level
        if hit:
            return index
    return None


def _outcome_id(opportunity_id: str, dataset_id: str, horizon: int) -> str:
    payload = f"{opportunity_id}|{dataset_id}|{horizon}"
    return f"outcome:{sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


__all__ = (
    "MissedOpportunityAssessment",
    "MissedOpportunityCause",
    "MissedOpportunityReview",
    "OpportunityOutcomeClass",
    "OpportunityOutcomeEvaluation",
    "OpportunityOutcomeStatus",
    "classify_missed_opportunity",
    "evaluate_opportunity_outcome",
)

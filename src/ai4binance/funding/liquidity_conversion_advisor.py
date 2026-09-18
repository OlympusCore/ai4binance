"""Rank manual liquidity and conversion candidates without mutating accounts."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.portfolio.asset_policy import (
    AssetClassification,
    AssetClassificationRecord,
)

ZERO = Decimal("0")


class ConversionDecision(StrEnum):
    USE_FREE_CASH_FIRST = "USE_FREE_CASH_FIRST"
    CONVERSION_CANDIDATE = "CONVERSION_CANDIDATE"
    NOT_FUNDING_SOURCE = "NOT_FUNDING_SOURCE"
    NO_AVAILABLE_FUNDING = "NO_AVAILABLE_FUNDING"


@dataclass(frozen=True, slots=True)
class ConversionAdvisorPolicy:
    minimum_liquidity_score: Decimal = Decimal("50")
    maximum_exit_slippage_bps: Decimal = Decimal("75")
    minimum_conversion_usdt: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        values = (
            self.minimum_liquidity_score,
            self.maximum_exit_slippage_bps,
            self.minimum_conversion_usdt,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("conversion advisor policy values must be non-negative")


@dataclass(frozen=True, slots=True)
class ConversionSource:
    record: AssetClassificationRecord
    liquidity_score: Decimal
    exit_slippage_bps: Decimal
    opportunity_gap: Decimal = ZERO
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (self.liquidity_score, self.exit_slippage_bps, self.opportunity_gap)
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("conversion source values must be non-negative")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("conversion source blockers cannot be empty")


@dataclass(frozen=True, slots=True)
class ConversionCandidate:
    asset: str
    decision: ConversionDecision
    estimated_free_capital_usdt: Decimal
    liquidity_score: Decimal
    exit_slippage_bps: Decimal
    opportunity_gap: Decimal
    reason_codes: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    approval_required: bool = True
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("conversion candidate asset is required")
        values = (
            self.estimated_free_capital_usdt,
            self.liquidity_score,
            self.exit_slippage_bps,
            self.opportunity_gap,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("conversion candidate values must be non-negative")
        if any(not item.strip() for item in (*self.reason_codes, *self.blockers)):
            raise ValueError("conversion candidate codes cannot be empty")
        if self.execution_allowed:
            raise ValueError("conversion candidate cannot authorize execution")


@dataclass(frozen=True, slots=True)
class LiquidityConversionPlan:
    free_quote_capital_usdt: Decimal
    candidates: tuple[ConversionCandidate, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.free_quote_capital_usdt.is_finite()
            or self.free_quote_capital_usdt < ZERO
        ):
            raise ValueError("free quote capital must be non-negative")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("conversion plan blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("conversion plan cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class LiquidityAndConversionAdvisor:
    policy: ConversionAdvisorPolicy = field(default_factory=ConversionAdvisorPolicy)

    def review(
        self,
        *,
        free_quote_capital_usdt: Decimal = ZERO,
        sources: tuple[ConversionSource, ...],
    ) -> LiquidityConversionPlan:
        if not free_quote_capital_usdt.is_finite() or free_quote_capital_usdt < ZERO:
            raise ValueError("free_quote_capital_usdt must be non-negative")
        candidates = [self._candidate(source) for source in sources]
        usable = tuple(
            sorted(
                (
                    item
                    for item in candidates
                    if item.decision is ConversionDecision.CONVERSION_CANDIDATE
                ),
                key=lambda item: (
                    item.opportunity_gap,
                    item.liquidity_score,
                    item.estimated_free_capital_usdt,
                ),
                reverse=True,
            )
        )
        rejected = tuple(
            item
            for item in candidates
            if item.decision is not ConversionDecision.CONVERSION_CANDIDATE
        )
        ordered = (*usable, *rejected)
        blockers = tuple(
            dict.fromkeys(
                blocker for candidate in ordered for blocker in candidate.blockers
            )
        )
        if free_quote_capital_usdt <= ZERO and not usable:
            blockers = tuple(dict.fromkeys((*blockers, "NO_AVAILABLE_FUNDING")))
            ordered = (
                *ordered,
                ConversionCandidate(
                    "NONE",
                    ConversionDecision.NO_AVAILABLE_FUNDING,
                    ZERO,
                    ZERO,
                    ZERO,
                    ZERO,
                    ("NO_AVAILABLE_FUNDING",),
                    ("NO_AVAILABLE_FUNDING",),
                ),
            )
        return LiquidityConversionPlan(free_quote_capital_usdt, ordered, blockers)

    def _candidate(self, source: ConversionSource) -> ConversionCandidate:
        record = source.record
        blockers = list(source.blockers)
        reason_codes: list[str] = []
        decision = ConversionDecision.CONVERSION_CANDIDATE
        estimated_value = record.estimated_value_usdt or ZERO
        if record.classification in {
            AssetClassification.CASH_EQUIVALENT,
            AssetClassification.FEE_RESERVE,
            AssetClassification.PROTECTED_POSITION,
            AssetClassification.DUST,
            AssetClassification.ILLIQUID,
            AssetClassification.UNSUPPORTED,
            AssetClassification.LOCKED,
        }:
            decision = ConversionDecision.NOT_FUNDING_SOURCE
            blockers.append(f"{record.classification.value}_NOT_CONVERSION_SOURCE")
        if estimated_value < self.policy.minimum_conversion_usdt:
            decision = ConversionDecision.NOT_FUNDING_SOURCE
            blockers.append("MIN_CONVERSION_NOTIONAL_FAILED")
        if source.liquidity_score < self.policy.minimum_liquidity_score:
            decision = ConversionDecision.NOT_FUNDING_SOURCE
            blockers.append("INSUFFICIENT_EXIT_LIQUIDITY")
        if source.exit_slippage_bps > self.policy.maximum_exit_slippage_bps:
            decision = ConversionDecision.NOT_FUNDING_SOURCE
            blockers.append("EXCESSIVE_EXIT_SLIPPAGE")
        reason_codes.append(
            "MANUAL_CONVERSION_REVIEW"
            if decision is ConversionDecision.CONVERSION_CANDIDATE
            else "CONVERSION_REJECTED_BY_POLICY"
        )
        return ConversionCandidate(
            record.asset,
            decision,
            (
                estimated_value
                if decision is ConversionDecision.CONVERSION_CANDIDATE
                else ZERO
            ),
            source.liquidity_score,
            source.exit_slippage_bps,
            source.opportunity_gap,
            tuple(reason_codes),
            tuple(dict.fromkeys(blockers)),
        )

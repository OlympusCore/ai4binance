"""Compare current holdings against new opportunities without asset loyalty."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.markets import CapitalMarket
from ai4binance.portfolio.current_holding_review import (
    CurrentHoldingAssessment,
    HoldingDecision,
)
from ai4binance.portfolio.holding_opportunity import PortfolioOpportunity

ZERO = Decimal("0")
ONE = Decimal("1")


class OpportunityComparisonDecision(StrEnum):
    KEEP_CURRENT_HOLDING = "KEEP_CURRENT_HOLDING"
    REDUCE_CURRENT_HOLDING = "REDUCE_CURRENT_HOLDING"
    EXIT_CURRENT_HOLDING = "EXIT_CURRENT_HOLDING"
    ROTATE_TO_NEW_OPPORTUNITY = "ROTATE_TO_NEW_OPPORTUNITY"
    USE_FREE_CASH_FIRST = "USE_FREE_CASH_FIRST"
    WAIT_FOR_BETTER_ENTRY = "WAIT_FOR_BETTER_ENTRY"
    NO_ACTION = "NO_ACTION"
    RESEARCH_ONLY = "RESEARCH_ONLY"


@dataclass(frozen=True, slots=True)
class OpportunityComparisonPolicy:
    minimum_quality_advantage: Decimal = Decimal("10")
    minimum_rr_advantage: Decimal = Decimal("0.5")
    maximum_reduction_pct: Decimal = Decimal("0.20")
    minimum_reduction_pct: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        values = (
            self.minimum_quality_advantage,
            self.minimum_rr_advantage,
            self.maximum_reduction_pct,
            self.minimum_reduction_pct,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("comparison policy values must be non-negative")
        if (
            self.maximum_reduction_pct > ONE
            or self.minimum_reduction_pct > self.maximum_reduction_pct
        ):
            raise ValueError("comparison reduction policy is invalid")


@dataclass(frozen=True, slots=True)
class OpportunityComparison:
    holding_asset: str
    holding_symbol: str
    opportunity_symbol: str
    opportunity_market: CapitalMarket
    holding_quality_score: Decimal
    opportunity_quality_score: Decimal
    holding_risk_reward: Decimal
    opportunity_risk_reward: Decimal
    decision: OpportunityComparisonDecision
    suggested_reduction_pct: Decimal = ZERO
    reason_codes: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    manual_approval_required: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if any(
            not item.strip()
            for item in (
                self.holding_asset,
                self.holding_symbol,
                self.opportunity_symbol,
            )
        ):
            raise ValueError("comparison identity is required")
        values = (
            self.holding_quality_score,
            self.opportunity_quality_score,
            self.holding_risk_reward,
            self.opportunity_risk_reward,
            self.suggested_reduction_pct,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("comparison values must be non-negative")
        if self.suggested_reduction_pct > ONE:
            raise ValueError("suggested reduction percentage cannot exceed one")
        if any(not item.strip() for item in (*self.reason_codes, *self.blockers)):
            raise ValueError("comparison codes cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("comparison cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class OpportunityComparisonEngine:
    policy: OpportunityComparisonPolicy = field(
        default_factory=OpportunityComparisonPolicy
    )

    def compare(
        self,
        *,
        holding: CurrentHoldingAssessment,
        opportunity: PortfolioOpportunity,
        free_cash_usdt: Decimal = ZERO,
    ) -> OpportunityComparison:
        if not free_cash_usdt.is_finite() or free_cash_usdt < ZERO:
            raise ValueError("free_cash_usdt must be finite and non-negative")
        blockers = tuple(dict.fromkeys((*holding.blockers, *opportunity.blockers)))
        quality_gap = opportunity.profile.quality_score - holding.technical_quality
        rr_gap = opportunity.profile.risk_reward - holding.holding_risk_reward
        reason_codes: list[str] = []
        reduction_pct = ZERO
        approval_required = True
        if blockers:
            decision = OpportunityComparisonDecision.RESEARCH_ONLY
            reason_codes.append("BLOCKED_EVIDENCE")
        elif free_cash_usdt >= opportunity.required_capital_usdt:
            decision = OpportunityComparisonDecision.USE_FREE_CASH_FIRST
            reason_codes.append("FREE_CASH_HAS_PRIORITY")
        elif (
            quality_gap >= self.policy.minimum_quality_advantage
            and rr_gap >= self.policy.minimum_rr_advantage
            and holding.recommended_action
            in {
                HoldingDecision.CONVERSION_CANDIDATE,
                HoldingDecision.REDUCE_CANDIDATE,
                HoldingDecision.EXIT_CANDIDATE,
                HoldingDecision.RECOVERY_WATCH,
            }
        ):
            decision = OpportunityComparisonDecision.ROTATE_TO_NEW_OPPORTUNITY
            reason_codes.append("OPPORTUNITY_ADVANTAGE_CONFIRMED")
            reduction_pct = min(
                self.policy.maximum_reduction_pct,
                max(self.policy.minimum_reduction_pct, quality_gap / Decimal("100")),
            )
        elif holding.recommended_action is HoldingDecision.HOLD_OPPORTUNITY:
            decision = OpportunityComparisonDecision.KEEP_CURRENT_HOLDING
            approval_required = False
            reason_codes.append("CURRENT_HOLDING_REMAINS_STRONGER")
        else:
            decision = OpportunityComparisonDecision.WAIT_FOR_BETTER_ENTRY
            approval_required = False
            reason_codes.append("OPPORTUNITY_ADVANTAGE_INSUFFICIENT")
        return OpportunityComparison(
            holding.asset,
            holding.symbol,
            opportunity.symbol,
            opportunity.market,
            holding.technical_quality,
            opportunity.profile.quality_score,
            holding.holding_risk_reward,
            opportunity.profile.risk_reward,
            decision,
            reduction_pct,
            tuple(dict.fromkeys(reason_codes)),
            blockers,
            approval_required,
        )

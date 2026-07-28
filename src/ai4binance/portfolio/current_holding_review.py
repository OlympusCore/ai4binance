"""Objective per-holding review contracts with no execution authority."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.portfolio.asset_policy import AssetClassification
from ai4binance.portfolio.holding_opportunity import RiskRewardProfile

ZERO = Decimal("0")
ONE = Decimal("1")


class HoldingDecision(StrEnum):
    ADD_CANDIDATE = "ADD_CANDIDATE"
    HOLD_OPPORTUNITY = "HOLD_OPPORTUNITY"
    RECOVERY_WATCH = "RECOVERY_WATCH"
    REDUCE_CANDIDATE = "REDUCE_CANDIDATE"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    CONVERSION_CANDIDATE = "CONVERSION_CANDIDATE"
    NO_ACTION = "NO_ACTION"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class RecoveryState(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class CurrentHoldingReviewPolicy:
    minimum_risk_reward: Decimal = Decimal("1.5")
    minimum_hold_quality: Decimal = Decimal("65")
    maximum_risk_score: Decimal = Decimal("70")
    minimum_liquidity_score: Decimal = Decimal("50")

    def __post_init__(self) -> None:
        values = (
            self.minimum_risk_reward,
            self.minimum_hold_quality,
            self.maximum_risk_score,
            self.minimum_liquidity_score,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("holding review policy values must be non-negative")
        if any(
            value > Decimal("100")
            for value in (
                self.minimum_hold_quality,
                self.maximum_risk_score,
                self.minimum_liquidity_score,
            )
        ):
            raise ValueError("holding review score thresholds must be <= 100")


@dataclass(frozen=True, slots=True)
class CurrentHoldingInput:
    asset: str
    symbol: str
    classification: AssetClassification
    market_value_usdt: Decimal
    portfolio_weight: Decimal
    profile: RiskRewardProfile
    liquidity_score: Decimal
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        asset = self.asset.strip().upper()
        symbol = self.symbol.strip().upper()
        if not asset or not asset.isalnum() or not symbol or not symbol.isalnum():
            raise ValueError("holding input asset and symbol must be alphanumeric")
        if (
            not self.market_value_usdt.is_finite()
            or self.market_value_usdt < ZERO
            or not self.portfolio_weight.is_finite()
            or not ZERO <= self.portfolio_weight <= ONE
            or not self.liquidity_score.is_finite()
            or not ZERO <= self.liquidity_score <= Decimal("100")
        ):
            raise ValueError("holding input values are invalid")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("holding input blockers cannot be empty")
        object.__setattr__(self, "asset", asset)
        object.__setattr__(self, "symbol", symbol)


@dataclass(frozen=True, slots=True)
class CurrentHoldingAssessment:
    asset: str
    symbol: str
    classification: AssetClassification
    market_value_usdt: Decimal
    portfolio_weight: Decimal
    technical_quality: Decimal
    holding_risk_reward: Decimal
    liquidity_score: Decimal
    recovery_state: RecoveryState
    recommended_action: HoldingDecision
    reason_codes: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    manual_approval_required: bool = True
    confidence: Decimal = Decimal("0.5")
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.asset.strip() or not self.symbol.strip():
            raise ValueError("holding assessment identity is required")
        values = (
            self.market_value_usdt,
            self.portfolio_weight,
            self.technical_quality,
            self.holding_risk_reward,
            self.liquidity_score,
            self.confidence,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("holding assessment values are invalid")
        if self.portfolio_weight > ONE or self.confidence > ONE:
            raise ValueError("holding assessment ratios are invalid")
        if any(not item.strip() for item in (*self.reason_codes, *self.blockers)):
            raise ValueError("holding assessment codes cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("holding assessment cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class CurrentHoldingReviewReport:
    assessments: tuple[CurrentHoldingAssessment, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if any(not item.strip() for item in self.blockers):
            raise ValueError("holding review blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("holding review report cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class CurrentHoldingReviewEngine:
    policy: CurrentHoldingReviewPolicy = field(
        default_factory=CurrentHoldingReviewPolicy
    )

    def review(
        self, holdings: tuple[CurrentHoldingInput, ...]
    ) -> CurrentHoldingReviewReport:
        assessments = tuple(self._assess(item) for item in holdings)
        blockers = tuple(
            dict.fromkeys(
                blocker for assessment in assessments for blocker in assessment.blockers
            )
        )
        return CurrentHoldingReviewReport(assessments, blockers)

    def _assess(self, holding: CurrentHoldingInput) -> CurrentHoldingAssessment:
        blockers = list(holding.blockers)
        reason_codes: list[str] = []
        approval_required = True
        if holding.classification in {
            AssetClassification.UNSUPPORTED,
            AssetClassification.ILLIQUID,
        }:
            blockers.append(f"{holding.classification.value}_HOLDING")
        if holding.liquidity_score < self.policy.minimum_liquidity_score:
            blockers.append("INSUFFICIENT_EXIT_LIQUIDITY")
        weak_rr = holding.profile.risk_reward < self.policy.minimum_risk_reward
        high_risk = holding.profile.risk_score > self.policy.maximum_risk_score
        strong_quality = (
            holding.profile.quality_score >= self.policy.minimum_hold_quality
        )
        if blockers:
            action = HoldingDecision.RESEARCH_ONLY
            recovery = RecoveryState.UNDETERMINED
            reason_codes.append("BLOCKED_EVIDENCE")
        elif holding.classification is AssetClassification.CASH_EQUIVALENT:
            action = HoldingDecision.NO_ACTION
            recovery = RecoveryState.UNDETERMINED
            approval_required = False
            reason_codes.append("LIQUID_CASH_NOT_HOLDING_RISK")
        elif holding.classification is AssetClassification.DUST:
            action = HoldingDecision.NO_ACTION
            recovery = RecoveryState.UNDETERMINED
            approval_required = False
            reason_codes.append("DUST_NOT_RELIABLE_FUNDING")
        elif high_risk:
            action = HoldingDecision.EXIT_CANDIDATE
            recovery = RecoveryState.LOW
            reason_codes.append("RISK_SCORE_EXCEEDS_POLICY")
        elif weak_rr:
            action = HoldingDecision.CONVERSION_CANDIDATE
            recovery = RecoveryState.LOW
            reason_codes.append("RISK_REWARD_BELOW_POLICY")
        elif strong_quality:
            action = HoldingDecision.HOLD_OPPORTUNITY
            recovery = RecoveryState.HIGH
            approval_required = False
            reason_codes.append("HOLDING_QUALITY_CONFIRMED")
        else:
            action = HoldingDecision.RECOVERY_WATCH
            recovery = RecoveryState.MEDIUM
            approval_required = False
            reason_codes.append("RECOVERY_CONDITIONS_REQUIRE_CONFIRMATION")
        return CurrentHoldingAssessment(
            holding.asset,
            holding.symbol,
            holding.classification,
            holding.market_value_usdt,
            holding.portfolio_weight,
            holding.profile.quality_score,
            holding.profile.risk_reward,
            holding.liquidity_score,
            recovery,
            action,
            tuple(dict.fromkeys(reason_codes)),
            tuple(dict.fromkeys(blockers)),
            approval_required,
            holding.profile.confidence,
        )

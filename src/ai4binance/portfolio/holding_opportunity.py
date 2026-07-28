"""Objective holding-vs-opportunity review without asset attachment."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.markets import CapitalMarket

ZERO = Decimal("0")
ONE = Decimal("1")


class HoldingOpportunityAction(StrEnum):
    HOLD_REVIEW = "HOLD_REVIEW"
    USE_LIQUID_CAPITAL_REVIEW = "USE_LIQUID_CAPITAL_REVIEW"
    REDUCE_TO_LIQUIDITY_REVIEW = "REDUCE_TO_LIQUIDITY_REVIEW"
    ROTATE_TO_SPOT_REVIEW = "ROTATE_TO_SPOT_REVIEW"
    ROTATE_TO_FUTURES_REVIEW = "ROTATE_TO_FUTURES_REVIEW"
    WATCHLIST = "WATCHLIST"
    BLOCKED = "HOLDING_OPPORTUNITY_BLOCKED"


@dataclass(frozen=True, slots=True)
class RiskRewardProfile:
    quality_score: Decimal
    risk_reward: Decimal
    risk_score: Decimal
    confidence: Decimal = Decimal("0.5")

    def __post_init__(self) -> None:
        for name, value in (
            ("quality_score", self.quality_score),
            ("risk_score", self.risk_score),
        ):
            if not value.is_finite() or not ZERO <= value <= Decimal("100"):
                raise ValueError(f"{name} must be between zero and 100")
        if not self.risk_reward.is_finite() or self.risk_reward < ZERO:
            raise ValueError("risk_reward must be finite and non-negative")
        if not self.confidence.is_finite() or not ZERO <= self.confidence <= ONE:
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class HoldingOpportunity:
    asset: str
    symbol: str
    value_usdt: Decimal
    liquidatable_value_usdt: Decimal
    profile: RiskRewardProfile
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        asset = self.asset.strip().upper()
        symbol = self.symbol.strip().upper()
        if not asset or not asset.isalnum() or not symbol or not symbol.isalnum():
            raise ValueError("holding asset and symbol must be alphanumeric")
        if min(self.value_usdt, self.liquidatable_value_usdt) < ZERO:
            raise ValueError("holding values cannot be negative")
        if self.liquidatable_value_usdt > self.value_usdt:
            raise ValueError("liquidatable value cannot exceed holding value")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("holding blockers cannot be empty")
        object.__setattr__(self, "asset", asset)
        object.__setattr__(self, "symbol", symbol)


@dataclass(frozen=True, slots=True)
class PortfolioOpportunity:
    market: CapitalMarket
    symbol: str
    required_capital_usdt: Decimal
    profile: RiskRewardProfile
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol or not symbol.isalnum():
            raise ValueError("opportunity symbol must be alphanumeric")
        if (
            not self.required_capital_usdt.is_finite()
            or self.required_capital_usdt <= ZERO
        ):
            raise ValueError("required_capital_usdt must be finite and positive")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("opportunity blockers cannot be empty")
        object.__setattr__(self, "symbol", symbol)


@dataclass(frozen=True, slots=True)
class HoldingOpportunityPolicy:
    minimum_risk_reward: Decimal = Decimal("1.5")
    maximum_risk_score: Decimal = Decimal("70")
    minimum_quality_advantage: Decimal = Decimal("10")
    minimum_rr_advantage: Decimal = Decimal("0.5")
    maximum_rotation_ratio_per_holding: Decimal = Decimal("0.25")
    maximum_single_opportunity_ratio: Decimal = Decimal("0.20")
    minimum_rotation_usdt: Decimal = Decimal("10")
    minimum_liquid_reserve_ratio: Decimal = Decimal("0.10")
    futures_capital_target_ratio: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        ratios = (
            self.maximum_rotation_ratio_per_holding,
            self.maximum_single_opportunity_ratio,
            self.minimum_liquid_reserve_ratio,
            self.futures_capital_target_ratio,
        )
        if any(
            not value.is_finite() or value < ZERO or value > ONE for value in ratios
        ):
            raise ValueError("holding opportunity ratios must be between zero and one")
        if self.maximum_rotation_ratio_per_holding <= ZERO:
            raise ValueError("maximum_rotation_ratio_per_holding must be positive")
        if self.maximum_single_opportunity_ratio <= ZERO:
            raise ValueError("maximum_single_opportunity_ratio must be positive")
        for name, value in (
            ("minimum_risk_reward", self.minimum_risk_reward),
            ("maximum_risk_score", self.maximum_risk_score),
            ("minimum_quality_advantage", self.minimum_quality_advantage),
            ("minimum_rr_advantage", self.minimum_rr_advantage),
            ("minimum_rotation_usdt", self.minimum_rotation_usdt),
        ):
            if not value.is_finite() or value < ZERO:
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class HoldingOpportunityAdvice:
    action: HoldingOpportunityAction
    subject: str
    target_symbol: str | None
    market: CapitalMarket | None
    proposed_notional_usdt: Decimal
    rationale: str
    blockers: tuple[str, ...] = ()
    approval_required: bool = True
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.subject.strip() or not self.rationale.strip():
            raise ValueError("holding opportunity advice identity is required")
        if (
            not self.proposed_notional_usdt.is_finite()
            or self.proposed_notional_usdt < ZERO
        ):
            raise ValueError("advice notional must be finite and non-negative")
        if self.target_symbol is not None and not self.target_symbol.strip():
            raise ValueError("target_symbol cannot be empty")
        if self.execution_allowed:
            raise ValueError("holding opportunity advice cannot authorize execution")


@dataclass(frozen=True, slots=True)
class HoldingOpportunityReport:
    total_portfolio_value_usdt: Decimal
    liquid_capital_usdt: Decimal
    liquid_ratio: Decimal
    advice: tuple[HoldingOpportunityAdvice, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        values = (
            self.total_portfolio_value_usdt,
            self.liquid_capital_usdt,
            self.liquid_ratio,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("holding opportunity report values are invalid")
        if self.liquid_ratio > ONE:
            raise ValueError("liquid_ratio cannot exceed one")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("holding opportunity report cannot allow execution")


@dataclass(frozen=True, slots=True)
class HoldingsOpportunityReviewEngine:
    """Compare holdings and new opportunities without loyalty to any coin."""

    policy: HoldingOpportunityPolicy = field(default_factory=HoldingOpportunityPolicy)

    def review(
        self,
        *,
        holdings: tuple[HoldingOpportunity, ...],
        opportunities: tuple[PortfolioOpportunity, ...],
        liquid_capital_usdt: Decimal,
        total_portfolio_value_usdt: Decimal,
        current_futures_capital_usdt: Decimal = ZERO,
    ) -> HoldingOpportunityReport:
        self._validate_amount("liquid_capital_usdt", liquid_capital_usdt)
        self._validate_amount(
            "total_portfolio_value_usdt", total_portfolio_value_usdt, positive=True
        )
        self._validate_amount(
            "current_futures_capital_usdt", current_futures_capital_usdt
        )
        liquid_ratio = liquid_capital_usdt / total_portfolio_value_usdt
        blockers = tuple(
            dict.fromkeys(
                (
                    *(blocker for item in holdings for blocker in item.blockers),
                    *(blocker for item in opportunities for blocker in item.blockers),
                )
            )
        )
        advice: list[HoldingOpportunityAdvice] = []
        best = self._best_valid_opportunity(opportunities)
        if best is None:
            advice.extend(self._holding_only_advice(holdings, liquid_ratio))
        else:
            advice.extend(
                self._fund_best_opportunity(
                    best,
                    holdings,
                    liquid_capital_usdt,
                    total_portfolio_value_usdt,
                    current_futures_capital_usdt,
                )
            )
        if blockers:
            advice.append(
                HoldingOpportunityAdvice(
                    HoldingOpportunityAction.BLOCKED,
                    "ACCOUNT_EVIDENCE",
                    None,
                    None,
                    ZERO,
                    "Some account or market evidence is blocked; recommendations "
                    "remain manual review only.",
                    blockers,
                )
            )
        if not advice:
            advice.append(
                HoldingOpportunityAdvice(
                    HoldingOpportunityAction.WATCHLIST,
                    "PORTFOLIO",
                    None,
                    None,
                    ZERO,
                    "No validated opportunity is strong enough to justify rotation.",
                    approval_required=False,
                )
            )
        return HoldingOpportunityReport(
            total_portfolio_value_usdt,
            liquid_capital_usdt,
            liquid_ratio,
            tuple(advice),
            blockers,
        )

    def _best_valid_opportunity(
        self, opportunities: tuple[PortfolioOpportunity, ...]
    ) -> PortfolioOpportunity | None:
        valid = tuple(
            item
            for item in opportunities
            if not item.blockers
            and item.profile.risk_reward >= self.policy.minimum_risk_reward
            and item.profile.risk_score <= self.policy.maximum_risk_score
        )
        if not valid:
            return None
        return max(
            valid,
            key=lambda item: (
                item.profile.quality_score,
                item.profile.risk_reward,
                item.profile.confidence,
            ),
        )

    def _holding_only_advice(
        self,
        holdings: tuple[HoldingOpportunity, ...],
        liquid_ratio: Decimal,
    ) -> tuple[HoldingOpportunityAdvice, ...]:
        output: list[HoldingOpportunityAdvice] = []
        for holding in holdings:
            weak = (
                holding.profile.risk_reward < self.policy.minimum_risk_reward
                or holding.profile.risk_score > self.policy.maximum_risk_score
            )
            if weak and liquid_ratio < self.policy.minimum_liquid_reserve_ratio:
                output.append(
                    HoldingOpportunityAdvice(
                        HoldingOpportunityAction.REDUCE_TO_LIQUIDITY_REVIEW,
                        holding.asset,
                        None,
                        CapitalMarket.SPOT,
                        min(
                            holding.liquidatable_value_usdt
                            * self.policy.maximum_rotation_ratio_per_holding,
                            holding.value_usdt
                            * self.policy.maximum_single_opportunity_ratio,
                        ),
                        "Holding has weak risk/reward and portfolio liquid reserve "
                        "is low; review partial conversion to liquid quote.",
                        holding.blockers,
                    )
                )
            elif not holding.blockers:
                output.append(
                    HoldingOpportunityAdvice(
                        HoldingOpportunityAction.HOLD_REVIEW,
                        holding.asset,
                        holding.symbol,
                        CapitalMarket.SPOT,
                        ZERO,
                        "Holding remains reviewable; no stronger validated "
                        "alternative is available.",
                        approval_required=False,
                    )
                )
        return tuple(output)

    def _fund_best_opportunity(
        self,
        opportunity: PortfolioOpportunity,
        holdings: tuple[HoldingOpportunity, ...],
        liquid_capital_usdt: Decimal,
        total_portfolio_value_usdt: Decimal,
        current_futures_capital_usdt: Decimal,
    ) -> tuple[HoldingOpportunityAdvice, ...]:
        if opportunity.market is CapitalMarket.USD_M_FUTURES:
            remaining_futures_cap = (
                self.policy.futures_capital_target_ratio * total_portfolio_value_usdt
                - current_futures_capital_usdt
            )
            if remaining_futures_cap <= ZERO:
                return (
                    HoldingOpportunityAdvice(
                        HoldingOpportunityAction.BLOCKED,
                        "USD_M_FUTURES_CAPITAL",
                        opportunity.symbol,
                        opportunity.market,
                        ZERO,
                        "Futures capital target is already full; do not add "
                        "Futures risk.",
                        ("FUTURES_CAPITAL_TARGET_REACHED",),
                    ),
                )
        else:
            remaining_futures_cap = opportunity.required_capital_usdt
        capped_required = min(
            opportunity.required_capital_usdt,
            self.policy.maximum_single_opportunity_ratio * total_portfolio_value_usdt,
            remaining_futures_cap,
        )
        if liquid_capital_usdt >= capped_required:
            return (
                HoldingOpportunityAdvice(
                    HoldingOpportunityAction.USE_LIQUID_CAPITAL_REVIEW,
                    "LIQUID_CAPITAL",
                    opportunity.symbol,
                    opportunity.market,
                    capped_required,
                    "Use existing liquid capital before selling any coin.",
                ),
            )
        source = self._rotation_source(holdings, opportunity)
        if source is None:
            return (
                HoldingOpportunityAdvice(
                    HoldingOpportunityAction.BLOCKED,
                    "ROTATION_SOURCE",
                    opportunity.symbol,
                    opportunity.market,
                    ZERO,
                    "No holding has enough weaker, liquidatable value to fund "
                    "the better opportunity.",
                    ("NO_SUITABLE_ROTATION_SOURCE",),
                ),
            )
        proposed = min(
            capped_required - liquid_capital_usdt,
            source.liquidatable_value_usdt
            * self.policy.maximum_rotation_ratio_per_holding,
        )
        if proposed < self.policy.minimum_rotation_usdt:
            return (
                HoldingOpportunityAdvice(
                    HoldingOpportunityAction.BLOCKED,
                    source.asset,
                    opportunity.symbol,
                    opportunity.market,
                    ZERO,
                    "Calculated rotation is below the minimum useful notional.",
                    ("ROTATION_MIN_NOTIONAL_BLOCKED",),
                ),
            )
        return (
            HoldingOpportunityAdvice(
                (
                    HoldingOpportunityAction.ROTATE_TO_FUTURES_REVIEW
                    if opportunity.market is CapitalMarket.USD_M_FUTURES
                    else HoldingOpportunityAction.ROTATE_TO_SPOT_REVIEW
                ),
                source.asset,
                opportunity.symbol,
                opportunity.market,
                proposed,
                "A stronger risk/reward opportunity exists; review partial "
                "coin-to-liquid conversion without exceeding rotation caps.",
                (
                    f"SOURCE_SYMBOL={source.symbol}",
                    f"TARGET_RR={opportunity.profile.risk_reward}",
                    f"SOURCE_RR={source.profile.risk_reward}",
                ),
            ),
        )

    def _rotation_source(
        self,
        holdings: tuple[HoldingOpportunity, ...],
        opportunity: PortfolioOpportunity,
    ) -> HoldingOpportunity | None:
        candidates = tuple(
            holding
            for holding in holdings
            if not holding.blockers
            and holding.liquidatable_value_usdt >= self.policy.minimum_rotation_usdt
            and opportunity.profile.quality_score - holding.profile.quality_score
            >= self.policy.minimum_quality_advantage
            and opportunity.profile.risk_reward - holding.profile.risk_reward
            >= self.policy.minimum_rr_advantage
        )
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                item.profile.quality_score,
                item.profile.risk_reward,
                -item.liquidatable_value_usdt,
            ),
        )

    @staticmethod
    def _validate_amount(name: str, value: Decimal, *, positive: bool = False) -> None:
        if not value.is_finite() or value < ZERO or (positive and value <= ZERO):
            expected = "positive" if positive else "non-negative"
            raise ValueError(f"{name} must be finite and {expected}")

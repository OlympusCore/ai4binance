"""Proposal-only Spot/Futures capital rebalancing agent."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ai4binance.domain.market.markets import CapitalMarket

ZERO = Decimal("0")
ONE = Decimal("1")


class PortfolioRebalanceAction(StrEnum):
    HOLD_REVIEW = "HOLD_REVIEW"
    TRANSFER_TO_SPOT_REVIEW = "TRANSFER_TO_SPOT_REVIEW"
    TRANSFER_TO_FUTURES_REVIEW = "TRANSFER_TO_FUTURES_REVIEW"
    FREE_SPOT_LIQUIDITY_REVIEW = "FREE_SPOT_LIQUIDITY_REVIEW"
    REDUCE_FUTURES_RISK_REVIEW = "REDUCE_FUTURES_RISK_REVIEW"
    BLOCKED = "REBALANCE_BLOCKED"


@dataclass(frozen=True, slots=True)
class MarketAllocationState:
    market: CapitalMarket
    position_value_usdt: Decimal
    liquid_value_usdt: Decimal
    risk_notional_usdt: Decimal = ZERO
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.position_value_usdt,
            self.liquid_value_usdt,
            self.risk_notional_usdt,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("market allocation values must be finite and non-negative")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("market allocation blockers cannot be empty")

    @property
    def total_value_usdt(self) -> Decimal:
        return self.position_value_usdt + self.liquid_value_usdt

    @property
    def position_ratio(self) -> Decimal:
        if self.total_value_usdt <= ZERO:
            return ZERO
        return self.position_value_usdt / self.total_value_usdt

    @property
    def liquid_ratio(self) -> Decimal:
        if self.total_value_usdt <= ZERO:
            return ZERO
        return self.liquid_value_usdt / self.total_value_usdt


@dataclass(frozen=True, slots=True)
class PortfolioRebalancingPolicy:
    target_spot_ratio: Decimal = Decimal("0.90")
    target_futures_ratio: Decimal = Decimal("0.10")
    allocation_hysteresis_ratio: Decimal = Decimal("0.02")
    spot_min_liquid_ratio: Decimal = Decimal("0.10")
    futures_min_liquid_ratio: Decimal = Decimal("0.70")
    minimum_transfer_usdt: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        ratios = (
            self.target_spot_ratio,
            self.target_futures_ratio,
            self.allocation_hysteresis_ratio,
            self.spot_min_liquid_ratio,
            self.futures_min_liquid_ratio,
        )
        if any(
            not value.is_finite() or value < ZERO or value > ONE for value in ratios
        ):
            raise ValueError("portfolio rebalance ratios must be between zero and one")
        if self.target_spot_ratio + self.target_futures_ratio != ONE:
            raise ValueError("Spot and Futures targets must sum to one")
        if (
            not self.minimum_transfer_usdt.is_finite()
            or self.minimum_transfer_usdt <= ZERO
        ):
            raise ValueError("minimum_transfer_usdt must be finite and positive")


@dataclass(frozen=True, slots=True)
class PortfolioRebalancingAdvice:
    action: PortfolioRebalanceAction
    market: CapitalMarket | None
    proposed_notional_usdt: Decimal
    rationale: str
    blockers: tuple[str, ...] = ()
    approval_required: bool = True
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("portfolio rebalancing advice rationale is required")
        if (
            not self.proposed_notional_usdt.is_finite()
            or self.proposed_notional_usdt < ZERO
        ):
            raise ValueError("portfolio rebalancing advice amount is invalid")
        if self.execution_allowed:
            raise ValueError("portfolio rebalancing advice cannot authorize execution")


@dataclass(frozen=True, slots=True)
class PortfolioRebalancingReport:
    target_spot_ratio: Decimal
    target_futures_ratio: Decimal
    current_spot_ratio: Decimal
    current_futures_ratio: Decimal
    spot_position_ratio: Decimal
    spot_liquid_ratio: Decimal
    futures_position_ratio: Decimal
    futures_liquid_ratio: Decimal
    futures_risk_notional_usdt: Decimal
    advice: tuple[PortfolioRebalancingAdvice, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        ratios = (
            self.target_spot_ratio,
            self.target_futures_ratio,
            self.current_spot_ratio,
            self.current_futures_ratio,
            self.spot_position_ratio,
            self.spot_liquid_ratio,
            self.futures_position_ratio,
            self.futures_liquid_ratio,
        )
        if any(
            not value.is_finite() or value < ZERO or value > ONE for value in ratios
        ):
            raise ValueError("portfolio rebalancing report ratios are invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("portfolio rebalancing report cannot allow execution")


@dataclass(frozen=True, slots=True)
class RebalancingAgent:
    """Review target 90/10 Spot/Futures allocation without moving capital."""

    policy: PortfolioRebalancingPolicy = field(
        default_factory=PortfolioRebalancingPolicy
    )

    def review(
        self,
        *,
        spot: MarketAllocationState,
        futures: MarketAllocationState,
    ) -> PortfolioRebalancingReport:
        if spot.market is not CapitalMarket.SPOT:
            raise ValueError("spot state must use SPOT market")
        if futures.market is not CapitalMarket.USD_M_FUTURES:
            raise ValueError("futures state must use USD_M_FUTURES market")
        blockers = tuple(dict.fromkeys((*spot.blockers, *futures.blockers)))
        total = spot.total_value_usdt + futures.total_value_usdt
        if total <= ZERO:
            blockers = tuple(dict.fromkeys((*blockers, "PORTFOLIO_VALUE_UNAVAILABLE")))
            return self._report(
                spot,
                futures,
                ZERO,
                ZERO,
                blockers,
                (
                    PortfolioRebalancingAdvice(
                        PortfolioRebalanceAction.BLOCKED,
                        None,
                        ZERO,
                        "Portfolio value is unavailable; rebalance cannot be "
                        "evaluated.",
                        blockers,
                    ),
                ),
            )
        current_spot_ratio = spot.total_value_usdt / total
        current_futures_ratio = futures.total_value_usdt / total
        advice = list(
            self._allocation_advice(current_spot_ratio, current_futures_ratio, total)
        )
        advice.extend(self._liquidity_advice(spot, futures))
        if blockers:
            advice.append(
                PortfolioRebalancingAdvice(
                    PortfolioRebalanceAction.BLOCKED,
                    None,
                    ZERO,
                    "Account evidence has blockers; rebalance stays "
                    "manual-review only.",
                    blockers,
                )
            )
        if not advice:
            advice.append(
                PortfolioRebalancingAdvice(
                    PortfolioRebalanceAction.HOLD_REVIEW,
                    None,
                    ZERO,
                    "Spot/Futures allocation and liquidity ratios are within policy.",
                    approval_required=False,
                )
            )
        return self._report(
            spot,
            futures,
            current_spot_ratio,
            current_futures_ratio,
            blockers,
            tuple(advice),
        )

    def _allocation_advice(
        self,
        current_spot_ratio: Decimal,
        current_futures_ratio: Decimal,
        total_value_usdt: Decimal,
    ) -> tuple[PortfolioRebalancingAdvice, ...]:
        spot_delta = self.policy.target_spot_ratio - current_spot_ratio
        if abs(spot_delta) <= self.policy.allocation_hysteresis_ratio:
            return ()
        proposed = abs(spot_delta) * total_value_usdt
        if proposed < self.policy.minimum_transfer_usdt:
            return ()
        if current_spot_ratio < self.policy.target_spot_ratio:
            return (
                PortfolioRebalancingAdvice(
                    PortfolioRebalanceAction.TRANSFER_TO_SPOT_REVIEW,
                    CapitalMarket.SPOT,
                    proposed,
                    "Spot allocation is below the 90% target; review a manual "
                    "Futures-to-Spot capital shift.",
                ),
            )
        return (
            PortfolioRebalancingAdvice(
                PortfolioRebalanceAction.TRANSFER_TO_FUTURES_REVIEW,
                CapitalMarket.USD_M_FUTURES,
                proposed,
                "Futures allocation is below the 10% target; review a manual "
                "Spot-to-Futures capital shift.",
                (
                    "FUTURES_TARGET_IS_CAPITAL_ALLOCATION_NOT_LEVERAGED_NOTIONAL",
                    f"CURRENT_FUTURES_RATIO={current_futures_ratio}",
                ),
            ),
        )

    def _liquidity_advice(
        self,
        spot: MarketAllocationState,
        futures: MarketAllocationState,
    ) -> tuple[PortfolioRebalancingAdvice, ...]:
        output: list[PortfolioRebalancingAdvice] = []
        if (
            spot.total_value_usdt > ZERO
            and spot.liquid_ratio < self.policy.spot_min_liquid_ratio
        ):
            output.append(
                PortfolioRebalancingAdvice(
                    PortfolioRebalanceAction.FREE_SPOT_LIQUIDITY_REVIEW,
                    CapitalMarket.SPOT,
                    self.policy.spot_min_liquid_ratio * spot.total_value_usdt
                    - spot.liquid_value_usdt,
                    "Spot bucket should keep at least 10% liquid quote reserve for "
                    "fees, failed entries, and new validated opportunities.",
                )
            )
        futures_position_cap = ONE - self.policy.futures_min_liquid_ratio
        if (
            futures.total_value_usdt > ZERO
            and futures.position_ratio > futures_position_cap
        ):
            output.append(
                PortfolioRebalancingAdvice(
                    PortfolioRebalanceAction.REDUCE_FUTURES_RISK_REVIEW,
                    CapitalMarket.USD_M_FUTURES,
                    futures.position_value_usdt
                    - futures_position_cap * futures.total_value_usdt,
                    "Futures bucket should keep at least 70% liquid margin reserve; "
                    "review position reduction or additional margin before new risk.",
                    (
                        "FUTURES_LIQUIDITY_RESERVE_LOW",
                        f"FUTURES_RISK_NOTIONAL={futures.risk_notional_usdt}",
                    ),
                )
            )
        return tuple(output)

    def _report(
        self,
        spot: MarketAllocationState,
        futures: MarketAllocationState,
        current_spot_ratio: Decimal,
        current_futures_ratio: Decimal,
        blockers: tuple[str, ...],
        advice: tuple[PortfolioRebalancingAdvice, ...],
    ) -> PortfolioRebalancingReport:
        return PortfolioRebalancingReport(
            self.policy.target_spot_ratio,
            self.policy.target_futures_ratio,
            current_spot_ratio,
            current_futures_ratio,
            spot.position_ratio,
            spot.liquid_ratio,
            futures.position_ratio,
            futures.liquid_ratio,
            futures.risk_notional_usdt,
            advice,
            blockers,
        )

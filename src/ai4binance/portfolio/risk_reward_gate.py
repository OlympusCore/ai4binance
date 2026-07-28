"""Portfolio-aware deterministic risk/reward gate for advisory decisions."""

from dataclasses import dataclass, field
from decimal import Decimal

from ai4binance.markets import CapitalMarket

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class RiskRewardGatePolicy:
    minimum_rr: Decimal = Decimal("1.5")
    maximum_single_opportunity_pct: Decimal = Decimal("0.20")
    spot_liquid_quote_reserve_pct: Decimal = Decimal("0.10")
    futures_capital_target_pct: Decimal = Decimal("0.10")
    futures_available_margin_reserve_pct: Decimal = Decimal("0.70")
    minimum_oos_confidence: Decimal = Decimal("0.50")
    minimum_liquidation_distance_pct: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        values = (
            self.minimum_rr,
            self.maximum_single_opportunity_pct,
            self.spot_liquid_quote_reserve_pct,
            self.futures_capital_target_pct,
            self.futures_available_margin_reserve_pct,
            self.minimum_oos_confidence,
            self.minimum_liquidation_distance_pct,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("risk/reward gate policy values must be non-negative")
        if any(
            value > ONE
            for value in (
                self.maximum_single_opportunity_pct,
                self.spot_liquid_quote_reserve_pct,
                self.futures_capital_target_pct,
                self.futures_available_margin_reserve_pct,
                self.minimum_oos_confidence,
                self.minimum_liquidation_distance_pct,
            )
        ):
            raise ValueError("risk/reward gate ratios must be <= one")


@dataclass(frozen=True, slots=True)
class RiskRewardGateInput:
    market: CapitalMarket
    symbol: str
    risk_reward: Decimal
    opportunity_pct: Decimal
    spot_liquid_quote_reserve_pct: Decimal
    futures_capital_pct: Decimal = ZERO
    futures_available_margin_pct: Decimal | None = None
    liquidation_distance_pct: Decimal | None = None
    daily_loss_limit_clear: bool = True
    weekly_loss_limit_clear: bool = True
    oos_confidence: Decimal = ZERO
    data_quality_ok: bool = False
    stop_valid: bool = False
    same_direction_spot_futures: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("risk/reward gate symbol is required")
        ratios = (
            self.risk_reward,
            self.opportunity_pct,
            self.spot_liquid_quote_reserve_pct,
            self.futures_capital_pct,
            self.oos_confidence,
            *(
                value
                for value in (
                    self.futures_available_margin_pct,
                    self.liquidation_distance_pct,
                )
                if value is not None
            ),
        )
        if any(not value.is_finite() or value < ZERO for value in ratios):
            raise ValueError("risk/reward gate input values must be non-negative")


@dataclass(frozen=True, slots=True)
class RiskRewardGateResult:
    symbol: str
    accepted: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("risk/reward result symbol is required")
        if self.accepted == bool(self.blockers):
            raise ValueError("risk/reward result acceptance and blockers disagree")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("risk/reward blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("risk/reward gate cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class RiskRewardGate:
    policy: RiskRewardGatePolicy = field(default_factory=RiskRewardGatePolicy)

    def evaluate(self, request: RiskRewardGateInput) -> RiskRewardGateResult:
        blockers: list[str] = []
        if not request.data_quality_ok:
            blockers.append("DATA_INCOMPLETE")
        if not request.stop_valid:
            blockers.append("NO_VALID_STOP")
        if request.risk_reward < self.policy.minimum_rr:
            blockers.append("INSUFFICIENT_RR")
        if request.opportunity_pct > self.policy.maximum_single_opportunity_pct:
            blockers.append("MAXIMUM_SINGLE_OPPORTUNITY_EXCEEDED")
        if (
            request.spot_liquid_quote_reserve_pct
            < self.policy.spot_liquid_quote_reserve_pct
        ):
            blockers.append("LIQUID_RESERVE_DEFICIT")
        if request.oos_confidence < self.policy.minimum_oos_confidence:
            blockers.append("OOS_CONFIDENCE_LOW")
        if not request.daily_loss_limit_clear:
            blockers.append("DAILY_LOSS_LIMIT")
        if not request.weekly_loss_limit_clear:
            blockers.append("WEEKLY_LOSS_LIMIT")
        if request.same_direction_spot_futures:
            blockers.append("SAME_DIRECTION_SPOT_FUTURES_EXPOSURE")
        if request.market is CapitalMarket.USD_M_FUTURES:
            if request.futures_capital_pct > self.policy.futures_capital_target_pct:
                blockers.append("FUTURES_CAPITAL_LIMIT")
            if (
                request.futures_available_margin_pct is None
                or request.futures_available_margin_pct
                < self.policy.futures_available_margin_reserve_pct
            ):
                blockers.append("MARGIN_RESERVE_DEFICIT")
            if (
                request.liquidation_distance_pct is None
                or request.liquidation_distance_pct
                < self.policy.minimum_liquidation_distance_pct
            ):
                blockers.append("LIQUIDATION_RISK")
        return RiskRewardGateResult(
            request.symbol.strip().upper(),
            not blockers,
            tuple(dict.fromkeys(blockers)),
        )

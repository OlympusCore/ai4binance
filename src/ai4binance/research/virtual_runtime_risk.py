"""Deterministic virtual-runtime portfolio risk contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum

from ai4binance.portfolio.risk_budget import PortfolioRiskPolicy

ZERO = Decimal("0")
ONE = Decimal("1")


class SimulatedLeverageState(StrEnum):
    """Research-only leverage suitability outcomes."""

    ELIGIBLE = "SIMULATED_LEVERAGE_ELIGIBLE"
    REDUCED = "SIMULATED_LEVERAGE_REDUCED"
    BLOCKED = "SIMULATED_LEVERAGE_BLOCKED"


@dataclass(frozen=True, slots=True)
class SimulatedLeverageAssessment:
    """Non-executable leverage assessment without signal authority."""

    state: SimulatedLeverageState
    requested_leverage: int | None
    permitted_leverage: int | None
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("requested_leverage", "permitted_leverage"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or value < 1):
                raise ValueError(f"{field_name} must be a positive integer")
        if self.state is SimulatedLeverageState.BLOCKED and not self.blockers:
            raise ValueError("blocked leverage assessment requires blockers")
        if self.state is not SimulatedLeverageState.BLOCKED and self.blockers:
            raise ValueError("eligible leverage assessment cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("simulated leverage cannot authorize execution")


@dataclass(frozen=True, slots=True)
class VirtualPortfolioRiskGovernor:
    """Deterministic portfolio-level veto policy for virtual-market entries."""

    exposure_policy: PortfolioRiskPolicy = field(
        default_factory=lambda: PortfolioRiskPolicy(
            maximum_gross_usdt=Decimal("5000"),
            maximum_symbol_usdt=Decimal("2500"),
            maximum_correlation_group_usdt=Decimal("3000"),
            maximum_strategy_usdt=Decimal("2500"),
        )
    )
    maximum_risk_per_trade_usdt: Decimal = Decimal("250")
    maximum_open_risk_usdt: Decimal = Decimal("500")
    maximum_drawdown_ratio: Decimal = Decimal("0.15")
    maximum_consecutive_losses: int = 3
    maximum_margin_utilization_ratio: Decimal = Decimal("0.60")
    maximum_futures_leverage: int = 5

    def __post_init__(self) -> None:
        if (
            min(
                self.maximum_risk_per_trade_usdt,
                self.maximum_open_risk_usdt,
                self.maximum_margin_utilization_ratio,
            )
            <= ZERO
        ):
            raise ValueError("virtual portfolio governor limits must be positive")
        if not ZERO < self.maximum_drawdown_ratio <= ONE:
            raise ValueError(
                "virtual portfolio drawdown limit must stay within zero and one"
            )
        if not ZERO < self.maximum_margin_utilization_ratio <= ONE:
            raise ValueError(
                "virtual portfolio margin utilization limit must stay within "
                "zero and one"
            )
        if self.maximum_consecutive_losses < 0:
            raise ValueError(
                "virtual portfolio consecutive loss limit cannot be negative"
            )
        if self.maximum_futures_leverage < 1:
            raise ValueError(
                "virtual portfolio futures leverage limit must be positive"
            )

    def assess_simulated_leverage(
        self,
        *,
        requested_leverage: int | None,
        position_notional_usdt: Decimal | None,
        available_margin_usdt: Decimal | None,
        margin_utilization_ratio: Decimal | None,
        strategy_oos_approved: bool,
        upstream_blockers: tuple[str, ...] = (),
    ) -> SimulatedLeverageAssessment:
        """Assess bounded simulation suitability; confidence is never an input."""
        blockers = list(upstream_blockers)
        valid_requested = (
            requested_leverage is not None
            and not isinstance(requested_leverage, bool)
            and requested_leverage >= 1
        )
        if not valid_requested:
            blockers.append("SIMULATED_LEVERAGE_REQUEST_INVALID")
        if position_notional_usdt is None or position_notional_usdt <= ZERO:
            blockers.append("SIMULATED_POSITION_NOTIONAL_INVALID")
        if available_margin_usdt is None or available_margin_usdt <= ZERO:
            blockers.append("SIMULATED_AVAILABLE_MARGIN_INVALID")
        if margin_utilization_ratio is None or not (
            ZERO <= margin_utilization_ratio <= ONE
        ):
            blockers.append("SIMULATED_MARGIN_UTILIZATION_INVALID")
        elif margin_utilization_ratio > self.maximum_margin_utilization_ratio:
            blockers.append("FUTURES_MARGIN_UTILIZATION_LIMIT_EXCEEDED")
        if not strategy_oos_approved:
            blockers.append("SIMULATED_LEVERAGE_OOS_APPROVAL_MISSING")
        if blockers:
            return SimulatedLeverageAssessment(
                state=SimulatedLeverageState.BLOCKED,
                requested_leverage=requested_leverage if valid_requested else None,
                permitted_leverage=None,
                blockers=tuple(dict.fromkeys(blockers)),
            )
        assert position_notional_usdt is not None
        assert available_margin_usdt is not None
        assert requested_leverage is not None
        required = int(
            (position_notional_usdt / available_margin_usdt).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        if required > self.maximum_futures_leverage:
            return SimulatedLeverageAssessment(
                state=SimulatedLeverageState.BLOCKED,
                requested_leverage=requested_leverage,
                permitted_leverage=None,
                blockers=("SIMULATED_LEVERAGE_FEASIBILITY_EXCEEDED",),
            )
        permitted = min(requested_leverage, self.maximum_futures_leverage)
        if permitted < required:
            return SimulatedLeverageAssessment(
                state=SimulatedLeverageState.BLOCKED,
                requested_leverage=requested_leverage,
                permitted_leverage=None,
                blockers=("SIMULATED_LEVERAGE_INSUFFICIENT_FOR_NOTIONAL",),
            )
        state = (
            SimulatedLeverageState.REDUCED
            if requested_leverage > self.maximum_futures_leverage
            else SimulatedLeverageState.ELIGIBLE
        )
        return SimulatedLeverageAssessment(
            state=state,
            requested_leverage=requested_leverage,
            permitted_leverage=permitted,
        )

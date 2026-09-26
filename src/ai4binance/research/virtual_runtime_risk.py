"""Deterministic virtual-runtime portfolio risk contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from itertools import pairwise
from typing import cast

from ai4binance.portfolio.risk_budget import PortfolioRiskPolicy
from ai4binance.risk import structural_margin_loss_per_unit

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
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 1
            ):
                raise ValueError(f"{field_name} must be a positive integer")
        if self.state is SimulatedLeverageState.BLOCKED and not self.blockers:
            raise ValueError("blocked leverage assessment requires blockers")
        if self.state is not SimulatedLeverageState.BLOCKED and self.blockers:
            raise ValueError("eligible leverage assessment cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("simulated leverage cannot authorize execution")


@dataclass(frozen=True, slots=True)
class FuturesRiskBracket:
    """Snapshot-bound USD-M isolated-margin tier, including maintenance deduction."""

    notional_floor: Decimal
    notional_cap: Decimal
    initial_leverage: int
    maintenance_ratio: Decimal
    cumulative_maintenance: Decimal

    def __post_init__(self) -> None:
        values = (
            self.notional_floor,
            self.notional_cap,
            self.maintenance_ratio,
            self.cumulative_maintenance,
        )
        if any(not v.is_finite() for v in values):
            raise ValueError("Futures bracket values must be finite")
        if not ZERO <= self.notional_floor < self.notional_cap:
            raise ValueError("Futures bracket range is invalid")
        if (
            not ZERO < self.maintenance_ratio < ONE
            or self.cumulative_maintenance < ZERO
            or self.cumulative_maintenance
            > self.notional_floor * self.maintenance_ratio
        ):
            raise ValueError("Futures bracket maintenance is invalid")
        if (
            not isinstance(self.initial_leverage, int)
            or isinstance(self.initial_leverage, bool)
            or self.initial_leverage < 1
        ):
            raise ValueError("Futures bracket leverage is invalid")


def validate_futures_brackets(brackets: tuple[FuturesRiskBracket, ...]) -> None:
    """Require continuous maintenance tiers in their declared order."""
    if not brackets or brackets[0].notional_floor != ZERO:
        raise ValueError("Futures maintenance brackets must start at zero")
    for left, right in pairwise(brackets):
        if (
            left.notional_cap != right.notional_floor
            or left.maintenance_ratio > right.maintenance_ratio
            or left.initial_leverage < right.initial_leverage
            or right.cumulative_maintenance
            != left.cumulative_maintenance
            + right.notional_floor * (right.maintenance_ratio - left.maintenance_ratio)
        ):
            raise ValueError("Futures maintenance brackets are discontinuous")


def isolated_liquidation_price(
    *,
    long: bool,
    entry: Decimal,
    quantity: Decimal,
    wallet_margin: Decimal,
    brackets: tuple[FuturesRiskBracket, ...],
) -> Decimal:
    """Solve equity = mark-notional maintenance, checking the resulting tier.

    Wallet margin must already include funding and isolated collateral changes.
    Trading fees paid from the free wallet must not be deducted a second time.
    This isolated linear-contract model grants no exchange execution authority.
    """
    validate_futures_brackets(brackets)
    if any(not v.is_finite() for v in (entry, quantity, wallet_margin)):
        raise ValueError("isolated liquidation inputs must be finite")
    if min(entry, quantity) <= ZERO or not isinstance(long, bool):
        raise ValueError("isolated liquidation position is invalid")
    sign = ONE if long else -ONE
    for tier in brackets:
        price = (
            sign * entry * quantity - wallet_margin - tier.cumulative_maintenance
        ) / (quantity * (sign - tier.maintenance_ratio))
        if long and price <= ZERO:
            return ZERO
        if tier.notional_floor <= price * quantity < tier.notional_cap:
            return price
    raise ValueError("liquidation notional is outside verified maintenance brackets")


@dataclass(frozen=True, slots=True)
class StructuralLeverageAssessment:
    """Conservative simulation result; no position sizing or execution authority."""

    permitted_leverage: int | None
    initial_margin: Decimal | None
    stressed_stop_mark: Decimal | None
    margin_surplus_at_stressed_stop: Decimal | None
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("structural leverage cannot authorize execution")
        if self.blockers and self.permitted_leverage is not None:
            raise ValueError("blocked structural leverage cannot permit leverage")


@dataclass(frozen=True, slots=True)
class FuturesLeverageGovernor:
    """Deterministic OOS- and margin-bound governor for virtual Futures leverage."""

    maximum_margin_utilization_ratio: Decimal = Decimal("0.60")
    maximum_futures_leverage: int = 5

    def __post_init__(self) -> None:
        if any(
            not value.is_finite() for value in (self.maximum_margin_utilization_ratio,)
        ):
            raise ValueError("virtual portfolio governor limits must be finite")
        if not isinstance(self.maximum_futures_leverage, int) or isinstance(
            self.maximum_futures_leverage, bool
        ):
            raise ValueError("virtual portfolio leverage limit must be an integer")
        if not ZERO < self.maximum_margin_utilization_ratio <= ONE:
            raise ValueError(
                "virtual portfolio margin utilization limit must stay within "
                "zero and one"
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
            isinstance(requested_leverage, int)
            and not isinstance(requested_leverage, bool)
            and requested_leverage >= 1
        )
        if not valid_requested:
            blockers.append("SIMULATED_LEVERAGE_REQUEST_INVALID")
        if (
            position_notional_usdt is None
            or not position_notional_usdt.is_finite()
            or position_notional_usdt <= ZERO
        ):
            blockers.append("SIMULATED_POSITION_NOTIONAL_INVALID")
        if (
            available_margin_usdt is None
            or not available_margin_usdt.is_finite()
            or available_margin_usdt <= ZERO
        ):
            blockers.append("SIMULATED_AVAILABLE_MARGIN_INVALID")
        if (
            margin_utilization_ratio is None
            or not margin_utilization_ratio.is_finite()
            or not (ZERO <= margin_utilization_ratio <= ONE)
        ):
            blockers.append("SIMULATED_MARGIN_UTILIZATION_INVALID")
        elif margin_utilization_ratio > self.maximum_margin_utilization_ratio:
            blockers.append("FUTURES_MARGIN_UTILIZATION_LIMIT_EXCEEDED")
        if strategy_oos_approved is not True:
            blockers.append("SIMULATED_LEVERAGE_OOS_APPROVAL_MISSING")
        if blockers:
            return SimulatedLeverageAssessment(
                SimulatedLeverageState.BLOCKED,
                requested_leverage if valid_requested else None,
                None,
                tuple(dict.fromkeys(blockers)),
            )
        position_notional = cast(Decimal, position_notional_usdt)
        available_margin = cast(Decimal, available_margin_usdt)
        requested = cast(int, requested_leverage)
        required = int(
            (position_notional / available_margin).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        if required > self.maximum_futures_leverage:
            return SimulatedLeverageAssessment(
                SimulatedLeverageState.BLOCKED,
                requested,
                None,
                ("SIMULATED_LEVERAGE_FEASIBILITY_EXCEEDED",),
            )
        permitted = min(requested, self.maximum_futures_leverage)
        if permitted < required:
            return SimulatedLeverageAssessment(
                SimulatedLeverageState.BLOCKED,
                requested,
                None,
                ("SIMULATED_LEVERAGE_INSUFFICIENT_FOR_NOTIONAL",),
            )
        return SimulatedLeverageAssessment(
            SimulatedLeverageState.REDUCED
            if requested > self.maximum_futures_leverage
            else SimulatedLeverageState.ELIGIBLE,
            requested,
            permitted,
        )

    def assess_structural_leverage(
        self,
        *,
        entry: Decimal,
        stop: Decimal,
        quantity: Decimal,
        mark_price: Decimal,
        available_margin: Decimal,
        risk_budget: Decimal,
        round_trip_cost_ratio: Decimal,
        adverse_funding_ratio: Decimal,
        mark_stress_ratio: Decimal,
        brackets: tuple[FuturesRiskBracket, ...],
        strategy_oos_approved: bool,
        upstream_blockers: tuple[str, ...] = (),
    ) -> StructuralLeverageAssessment:
        """Choose the lowest feasible isolated leverage after stress and tier vetoes.

        Quantity and risk budget must come from the deterministic risk owner.
        Funding is a nonnegative loss bound over the complete intended holding
        horizon. Stop and current mark are distinct from contract trade price.
        Missing inputs are never estimated from a signal confidence score.
        """
        values = (
            entry,
            stop,
            quantity,
            mark_price,
            available_margin,
            risk_budget,
            round_trip_cost_ratio,
            adverse_funding_ratio,
            mark_stress_ratio,
        )
        blockers = list(upstream_blockers)
        blockers.extend(self._structural_input_blockers(values))
        if strategy_oos_approved is not True:
            blockers.append("SIMULATED_LEVERAGE_OOS_APPROVAL_MISSING")
        ordered = tuple(sorted(brackets, key=lambda b: b.notional_floor))
        if not ordered or any(
            a.notional_cap != b.notional_floor for a, b in pairwise(ordered)
        ):
            blockers.append("FUTURES_RISK_BRACKETS_UNAVAILABLE_OR_INCONSISTENT")
        if blockers:
            return StructuralLeverageAssessment(
                None, None, None, None, tuple(dict.fromkeys(blockers))
            )
        stressed_stop, loss_per_unit = structural_margin_loss_per_unit(
            entry,
            stop,
            mark_price,
            round_trip_cost_ratio + adverse_funding_ratio,
            mark_stress_ratio,
        )
        if stressed_stop <= ZERO:
            return StructuralLeverageAssessment(
                None, None, None, None, ("FUTURES_STRESSED_STOP_INVALID",)
            )
        notional = entry * quantity
        loss = loss_per_unit * quantity
        if loss > risk_budget:
            return StructuralLeverageAssessment(
                None,
                None,
                stressed_stop,
                None,
                ("FUTURES_STRESSED_RISK_BUDGET_EXCEEDED",),
            )
        tiers = self._stress_tiers(
            ordered, (entry, mark_price, stressed_stop), quantity
        )
        if not tiers:
            return StructuralLeverageAssessment(
                None,
                None,
                stressed_stop,
                None,
                ("FUTURES_NOTIONAL_OUTSIDE_BRACKETS",),
            )
        maximum = min(
            self.maximum_futures_leverage, *(b.initial_leverage for b in tiers)
        )
        required = max(
            1,
            int(
                (notional / available_margin).to_integral_value(rounding=ROUND_CEILING)
            ),
        )
        if required > maximum:
            return StructuralLeverageAssessment(
                None,
                None,
                stressed_stop,
                None,
                ("SIMULATED_LEVERAGE_FEASIBILITY_EXCEEDED",),
            )
        margin = notional / Decimal(required)
        tier = tiers[-1]
        maintenance = max(
            ZERO,
            stressed_stop * quantity * tier.maintenance_ratio
            - tier.cumulative_maintenance,
        )
        surplus = margin - loss - maintenance
        if surplus <= ZERO:
            return StructuralLeverageAssessment(
                None,
                None,
                stressed_stop,
                surplus,
                ("FUTURES_LIQUIDATION_BEFORE_STRESSED_STOP",),
            )
        return StructuralLeverageAssessment(
            required, margin, stressed_stop, surplus, ()
        )

    @staticmethod
    def _structural_input_blockers(values: tuple[Decimal, ...]) -> tuple[str, ...]:
        if any(not v.is_finite() for v in values):
            return ("STRUCTURAL_LEVERAGE_NONFINITE_INPUT",)
        if (
            min(values[:6]) <= ZERO
            or values[0] == values[1]
            or min(values[6:]) < ZERO
            or max(values[6:]) >= ONE
        ):
            return ("STRUCTURAL_LEVERAGE_INVALID_INPUT",)
        return ()

    @staticmethod
    def _stress_tiers(
        brackets: tuple[FuturesRiskBracket, ...],
        prices: tuple[Decimal, ...],
        quantity: Decimal,
    ) -> tuple[FuturesRiskBracket, ...]:
        tiers = []
        for price in prices:
            tier = next(
                (
                    b
                    for b in brackets
                    if b.notional_floor <= price * quantity < b.notional_cap
                ),
                None,
            )
            if tier is None:
                return ()
            tiers.append(tier)
        return tuple(tiers)

    def structural_margin_blockers(
        self,
        *,
        context: Mapping[str, object] | None,
        requested_leverage: int | None,
        snapshot_id: str,
        symbol: str,
        entry: Decimal,
        stop: Decimal,
        quantity: Decimal,
        mark_price: Decimal | None,
        available_margin: Decimal | None,
        round_trip_cost_ratio: Decimal,
        risk_budget: Decimal,
    ) -> tuple[str, ...]:
        """Validate explicit snapshot-bound evidence before a V2 virtual entry."""
        if context is None or mark_price is None or available_margin is None:
            return ("STRUCTURAL_MARGIN_EVIDENCE_UNAVAILABLE",)
        if (
            context.get("snapshot_id") != snapshot_id
            or context.get("symbol") != symbol
            or context.get("margin_mode") != "ISOLATED"
        ):
            return ("STRUCTURAL_MARGIN_IDENTITY_OR_MODE_INVALID",)
        try:
            rows = context["brackets"]
            if not isinstance(rows, (tuple, list)) or not rows or len(rows) > 100:
                raise ValueError("brackets are unavailable")
            brackets = []
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError("bracket is invalid")
                leverage = row["initialLeverage"]
                if not isinstance(leverage, int) or isinstance(leverage, bool):
                    raise ValueError("bracket leverage is invalid")
                brackets.append(
                    FuturesRiskBracket(
                        Decimal(str(row["notionalFloor"])),
                        Decimal(str(row["notionalCap"])),
                        leverage,
                        Decimal(str(row["maintMarginRatio"])),
                        Decimal(str(row["cum"])),
                    )
                )
            funding = Decimal(str(context["adverse_funding_ratio"]))
            stress = Decimal(str(context["mark_stress_ratio"]))
        except (ValueError, KeyError, ArithmeticError, TypeError):
            return ("STRUCTURAL_MARGIN_EVIDENCE_INVALID",)
        assessment = self.assess_structural_leverage(
            entry=entry,
            stop=stop,
            quantity=quantity,
            mark_price=mark_price,
            available_margin=available_margin,
            risk_budget=risk_budget,
            round_trip_cost_ratio=round_trip_cost_ratio,
            adverse_funding_ratio=funding,
            mark_stress_ratio=stress,
            brackets=tuple(brackets),
            strategy_oos_approved=context.get("strategy_oos_approved") is True,
        )
        if (
            not assessment.blockers
            and requested_leverage != assessment.permitted_leverage
        ):
            return ("FUTURES_LEVERAGE_NOT_MINIMUM_FEASIBLE",)
        return assessment.blockers

    def futures_entry_blockers(
        self,
        *,
        requested_leverage: int | None,
        current_margin_utilization: Decimal | None,
        projected_margin_utilization: Decimal | None,
    ) -> tuple[str, ...]:
        """Enforce simulation limits without claiming OOS or execution authority."""
        blockers: list[str] = []
        if (
            not isinstance(requested_leverage, int)
            or isinstance(requested_leverage, bool)
            or requested_leverage < 1
        ):
            blockers.append("FUTURES_LEVERAGE_UNAVAILABLE")
        elif requested_leverage > self.maximum_futures_leverage:
            blockers.append("FUTURES_LEVERAGE_LIMIT_EXCEEDED")
        for name, utilization in (
            ("CURRENT", current_margin_utilization),
            ("PROJECTED", projected_margin_utilization),
        ):
            if utilization is None or not utilization.is_finite() or utilization < ZERO:
                blockers.append(f"FUTURES_{name}_MARGIN_UTILIZATION_UNAVAILABLE")
            elif utilization > self.maximum_margin_utilization_ratio:
                blockers.append("FUTURES_MARGIN_UTILIZATION_LIMIT_EXCEEDED")
        return tuple(dict.fromkeys(blockers))


@dataclass(frozen=True, slots=True)
class VirtualPortfolioRiskGovernor(FuturesLeverageGovernor):
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

    def __post_init__(self) -> None:
        super().__post_init__()
        if any(
            not value.is_finite()
            for value in (
                self.maximum_risk_per_trade_usdt,
                self.maximum_open_risk_usdt,
                self.maximum_drawdown_ratio,
            )
        ):
            raise ValueError("virtual portfolio governor limits must be finite")
        if (
            min(
                self.maximum_risk_per_trade_usdt,
                self.maximum_open_risk_usdt,
            )
            <= ZERO
        ):
            raise ValueError("virtual portfolio governor limits must be positive")
        if not ZERO < self.maximum_drawdown_ratio <= ONE:
            raise ValueError(
                "virtual portfolio drawdown limit must stay within zero and one"
            )
        if self.maximum_consecutive_losses < 0:
            raise ValueError(
                "virtual portfolio consecutive loss limit cannot be negative"
            )

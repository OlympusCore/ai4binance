"""Proposal-only portfolio exposure and correlation-group governance."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PositionExposure:
    symbol: str
    strategy_id: str
    correlation_group: str
    notional_usdt: Decimal

    def __post_init__(self) -> None:
        identities = (self.symbol, self.strategy_id, self.correlation_group)
        if any(not item.strip() for item in identities) or self.notional_usdt < ZERO:
            raise ValueError("position exposure is invalid")


@dataclass(frozen=True, slots=True)
class PortfolioRiskPolicy:
    maximum_gross_usdt: Decimal = Decimal("500")
    maximum_symbol_usdt: Decimal = Decimal("250")
    maximum_correlation_group_usdt: Decimal = Decimal("300")
    maximum_strategy_usdt: Decimal = Decimal("250")

    def __post_init__(self) -> None:
        limits = (
            self.maximum_gross_usdt,
            self.maximum_symbol_usdt,
            self.maximum_correlation_group_usdt,
            self.maximum_strategy_usdt,
        )
        if min(limits) <= ZERO:
            raise ValueError("portfolio risk limits must be positive")


@dataclass(frozen=True, slots=True)
class PortfolioRiskAssessment:
    proposed_symbol: str
    gross_after_usdt: Decimal
    approved_for_proposal: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.proposed_symbol.strip() or self.gross_after_usdt < ZERO:
            raise ValueError("portfolio assessment is invalid")
        if self.approved_for_proposal and self.blockers:
            raise ValueError("approved proposal cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("portfolio assessment cannot authorize execution")


def assess_proposed_exposure(
    current: tuple[PositionExposure, ...],
    proposed: PositionExposure,
    policy: PortfolioRiskPolicy | None = None,
) -> PortfolioRiskAssessment:
    """Evaluate an exposure proposal without changing inventory or risk limits."""
    active_policy = policy or PortfolioRiskPolicy()
    combined = (*current, proposed)
    gross = sum((item.notional_usdt for item in combined), ZERO)
    symbol_total = sum(
        (item.notional_usdt for item in combined if item.symbol == proposed.symbol),
        ZERO,
    )
    group_total = sum(
        (
            item.notional_usdt
            for item in combined
            if item.correlation_group == proposed.correlation_group
        ),
        ZERO,
    )
    strategy_total = sum(
        (
            item.notional_usdt
            for item in combined
            if item.strategy_id == proposed.strategy_id
        ),
        ZERO,
    )
    checks = (
        (
            gross > active_policy.maximum_gross_usdt,
            "PORTFOLIO_GROSS_LIMIT_EXCEEDED",
        ),
        (
            symbol_total > active_policy.maximum_symbol_usdt,
            "SYMBOL_EXPOSURE_LIMIT_EXCEEDED",
        ),
        (
            group_total > active_policy.maximum_correlation_group_usdt,
            "CORRELATION_GROUP_LIMIT_EXCEEDED",
        ),
        (
            strategy_total > active_policy.maximum_strategy_usdt,
            "STRATEGY_EXPOSURE_LIMIT_EXCEEDED",
        ),
    )
    blockers = tuple(code for failed, code in checks if failed)
    return PortfolioRiskAssessment(
        proposed.symbol,
        gross,
        not blockers,
        blockers,
    )


def assess_current_exposure(
    current: tuple[PositionExposure, ...],
    policy: PortfolioRiskPolicy | None = None,
) -> PortfolioRiskAssessment:
    """Evaluate observed exposure against limits without creating a proposal."""
    active_policy = policy or PortfolioRiskPolicy()
    gross = sum((item.notional_usdt for item in current), ZERO)
    symbol_totals = {
        symbol: sum(
            (item.notional_usdt for item in current if item.symbol == symbol), ZERO
        )
        for symbol in {item.symbol for item in current}
    }
    group_totals = {
        group: sum(
            (item.notional_usdt for item in current if item.correlation_group == group),
            ZERO,
        )
        for group in {item.correlation_group for item in current}
    }
    strategy_totals = {
        strategy: sum(
            (item.notional_usdt for item in current if item.strategy_id == strategy),
            ZERO,
        )
        for strategy in {item.strategy_id for item in current}
    }
    blockers: list[str] = []
    if gross > active_policy.maximum_gross_usdt:
        blockers.append("PORTFOLIO_GROSS_LIMIT_EXCEEDED")
    if any(
        value > active_policy.maximum_symbol_usdt for value in symbol_totals.values()
    ):
        blockers.append("SYMBOL_EXPOSURE_LIMIT_EXCEEDED")
    if any(
        value > active_policy.maximum_correlation_group_usdt
        for value in group_totals.values()
    ):
        blockers.append("CORRELATION_GROUP_LIMIT_EXCEEDED")
    if any(
        value > active_policy.maximum_strategy_usdt
        for value in strategy_totals.values()
    ):
        blockers.append("STRATEGY_EXPOSURE_LIMIT_EXCEEDED")
    return PortfolioRiskAssessment(
        "CURRENT_PORTFOLIO", gross, not blockers, tuple(blockers)
    )

"""Read-only Spot portfolio valuation and concentration analytics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol

from ai4binance.portfolio.risk_budget import (
    PortfolioRiskPolicy,
    PositionExposure,
    assess_current_exposure,
)
from ai4binance.portfolio.wallet import WalletSnapshot

ZERO = Decimal("0")
ONE = Decimal("1")
DEFAULT_CONCENTRATION_LIMIT = Decimal("0.40")
PAR_USDT_ASSETS = frozenset({"USDT", "FDUSD", "USDC"})


class SpotPriceReader(Protocol):
    def ticker_price(self, symbol: str) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class FallbackSpotPriceReader:
    """Use wallet price coverage first, preserving the TOP50 snapshot fallback."""

    primary: SpotPriceReader
    fallback: SpotPriceReader

    def ticker_price(self, symbol: str) -> Decimal:
        try:
            return self.primary.ticker_price(symbol)
        except (OSError, RuntimeError, TypeError, ValueError):
            return self.fallback.ticker_price(symbol)


@dataclass(frozen=True, slots=True)
class ValuedSpotAsset:
    asset: str
    quantity: Decimal
    price_usdt: Decimal
    value_usdt: Decimal
    weight: Decimal
    average_cost_usdt: Decimal | None = None
    unrealized_pnl_usdt: Decimal | None = None

    def __post_init__(self) -> None:
        if (
            not self.asset.strip()
            or min(self.quantity, self.price_usdt, self.value_usdt, self.weight) < ZERO
            or self.weight > ONE
        ):
            raise ValueError("valued Spot asset is invalid")
        optional = (self.average_cost_usdt, self.unrealized_pnl_usdt)
        if any(value is not None and not value.is_finite() for value in optional):
            raise ValueError("Spot cost and PnL values must be finite")


@dataclass(frozen=True, slots=True)
class PortfolioAnalytics:
    total_value_usdt: Decimal
    valued_assets: tuple[ValuedSpotAsset, ...]
    unpriced_assets: tuple[str, ...]
    largest_asset: str | None
    largest_weight: Decimal
    unrealized_pnl_usdt: Decimal | None
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.total_value_usdt < ZERO
            or not ZERO <= self.largest_weight <= ONE
            or (self.largest_asset is None) != (not self.valued_assets)
        ):
            raise ValueError("portfolio analytics is invalid")
        if (
            self.unrealized_pnl_usdt is not None
            and not self.unrealized_pnl_usdt.is_finite()
        ):
            raise ValueError("portfolio PnL must be finite")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("portfolio analytics cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class PortfolioAnalyticsService:
    prices: SpotPriceReader
    concentration_limit: Decimal = DEFAULT_CONCENTRATION_LIMIT
    risk_policy: PortfolioRiskPolicy = field(default_factory=PortfolioRiskPolicy)

    def __post_init__(self) -> None:
        if not ZERO < self.concentration_limit <= ONE:
            raise ValueError("concentration limit must be between zero and one")

    def evaluate(
        self,
        wallet: WalletSnapshot,
        *,
        average_costs_usdt: Mapping[str, Decimal] | None = None,
    ) -> PortfolioAnalytics:
        costs = {
            asset.strip().upper(): self._finite_decimal(value, "average cost")
            for asset, value in (average_costs_usdt or {}).items()
        }
        raw: list[tuple[str, Decimal, Decimal, Decimal, Decimal | None]] = []
        unpriced: list[str] = []
        for balance in wallet.balances:
            quantity = balance.free + balance.locked
            if quantity <= ZERO:
                continue
            try:
                price = (
                    ONE
                    if balance.asset in PAR_USDT_ASSETS
                    else self._finite_decimal(
                        self.prices.ticker_price(f"{balance.asset}USDT"),
                        "ticker price",
                    )
                )
                if price <= ZERO:
                    raise ValueError("ticker price must be positive")
            except (OSError, RuntimeError, TypeError, ValueError):
                unpriced.append(balance.asset)
                continue
            raw.append(
                (
                    balance.asset,
                    quantity,
                    price,
                    quantity * price,
                    ONE
                    if balance.asset in PAR_USDT_ASSETS
                    else costs.get(balance.asset),
                )
            )
        total = sum((item[3] for item in raw), ZERO)
        valued = tuple(
            ValuedSpotAsset(
                asset=asset,
                quantity=quantity,
                price_usdt=price,
                value_usdt=value,
                weight=value / total if total > ZERO else ZERO,
                average_cost_usdt=cost,
                unrealized_pnl_usdt=(
                    (price - cost) * quantity if cost is not None else None
                ),
            )
            for asset, quantity, price, value, cost in raw
        )
        largest = max(valued, key=lambda item: item.weight, default=None)
        largest_position = max(
            (item for item in valued if item.asset not in PAR_USDT_ASSETS),
            key=lambda item: item.weight,
            default=None,
        )
        pnl_values = tuple(
            item.unrealized_pnl_usdt
            for item in valued
            if item.unrealized_pnl_usdt is not None
        )
        complete_cost_basis = bool(valued) and len(pnl_values) == len(valued)
        blockers: list[str] = []
        if unpriced:
            blockers.append("PORTFOLIO_UNPRICED_ASSETS")
        if valued and not complete_cost_basis:
            blockers.append("PORTFOLIO_COST_BASIS_UNAVAILABLE")
        if (
            largest_position is not None
            and largest_position.weight > self.concentration_limit
        ):
            blockers.append("PORTFOLIO_CONCENTRATION_LIMIT_EXCEEDED")
        risk = assess_current_exposure(
            tuple(
                PositionExposure(
                    symbol=f"{item.asset}USDT",
                    strategy_id="CURRENT_SPOT_INVENTORY",
                    correlation_group="CRYPTO_SPOT",
                    notional_usdt=item.value_usdt,
                )
                for item in valued
                if item.asset not in PAR_USDT_ASSETS
            ),
            self.risk_policy,
        )
        blockers.extend(risk.blockers)
        return PortfolioAnalytics(
            total_value_usdt=total,
            valued_assets=valued,
            unpriced_assets=tuple(unpriced),
            largest_asset=largest.asset if largest is not None else None,
            largest_weight=largest.weight if largest is not None else ZERO,
            unrealized_pnl_usdt=(
                sum(pnl_values, ZERO) if complete_cost_basis else None
            ),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _finite_decimal(value: object, name: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{name} must be decimal-compatible") from None
        if not parsed.is_finite() or parsed < ZERO:
            raise ValueError(f"{name} must be finite and non-negative")
        return parsed

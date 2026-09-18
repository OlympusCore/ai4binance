"""Market-specific virtual portfolio state contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import cast

ZERO = Decimal("0")
ONE = Decimal("1")


class VirtualPositionSide(StrEnum):
    """Explicit directional semantics for virtual derivatives positions."""

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class VirtualPortfolioState:
    """Market-specific virtual portfolio state with independent capital tracking."""

    portfolio_id: str
    market: str
    cash_usdt: Decimal
    equity_usdt: Decimal
    initial_equity_usdt: Decimal = Decimal("1000")
    inventory_quantity: Decimal = ZERO
    inventory_cost_basis_usdt: Decimal = ZERO
    realized_pnl_usdt: Decimal = ZERO
    unrealized_pnl_usdt: Decimal = ZERO
    fees_paid_usdt: Decimal = ZERO
    slippage_cost_usdt: Decimal = ZERO
    funding_cost_usdt: Decimal = ZERO
    high_watermark_usdt: Decimal | None = None
    max_drawdown_ratio: Decimal = ZERO
    current_open_risk_usdt: Decimal = ZERO
    consecutive_losses: int = 0
    position_side: VirtualPositionSide | None = None
    position_entry_price: Decimal | None = None
    position_mark_price: Decimal | None = None
    position_notional_usdt: Decimal | None = None
    isolated_margin_usdt: Decimal | None = None
    initial_margin_usdt: Decimal | None = None
    maintenance_margin_usdt: Decimal | None = None
    liquidation_price: Decimal | None = None
    leverage: int | None = None
    margin_utilization_ratio: Decimal | None = None
    open_position_count: int = 0
    max_concurrent_positions: int = 1

    def to_payload(self) -> dict[str, object]:
        """Serialize the complete wallet state without losing decimal precision."""

        return {
            "portfolio_id": self.portfolio_id,
            "market": self.market,
            "cash_usdt": str(self.cash_usdt),
            "equity_usdt": str(self.equity_usdt),
            "initial_equity_usdt": str(self.initial_equity_usdt),
            "inventory_quantity": str(self.inventory_quantity),
            "inventory_cost_basis_usdt": str(self.inventory_cost_basis_usdt),
            "realized_pnl_usdt": str(self.realized_pnl_usdt),
            "unrealized_pnl_usdt": str(self.unrealized_pnl_usdt),
            "fees_paid_usdt": str(self.fees_paid_usdt),
            "slippage_cost_usdt": str(self.slippage_cost_usdt),
            "funding_cost_usdt": str(self.funding_cost_usdt),
            "high_watermark_usdt": _optional_decimal_text(self.high_watermark_usdt),
            "max_drawdown_ratio": str(self.max_drawdown_ratio),
            "current_open_risk_usdt": str(self.current_open_risk_usdt),
            "consecutive_losses": self.consecutive_losses,
            "position_side": (
                self.position_side.value if self.position_side is not None else None
            ),
            "position_entry_price": _optional_decimal_text(self.position_entry_price),
            "position_mark_price": _optional_decimal_text(self.position_mark_price),
            "position_notional_usdt": _optional_decimal_text(
                self.position_notional_usdt
            ),
            "isolated_margin_usdt": _optional_decimal_text(self.isolated_margin_usdt),
            "initial_margin_usdt": _optional_decimal_text(self.initial_margin_usdt),
            "maintenance_margin_usdt": _optional_decimal_text(
                self.maintenance_margin_usdt
            ),
            "liquidation_price": _optional_decimal_text(self.liquidation_price),
            "leverage": self.leverage,
            "margin_utilization_ratio": _optional_decimal_text(
                self.margin_utilization_ratio
            ),
            "open_position_count": self.open_position_count,
            "max_concurrent_positions": self.max_concurrent_positions,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> VirtualPortfolioState:
        """Restore and validate a complete wallet state payload."""

        side = payload.get("position_side")
        leverage = payload.get("leverage")
        return cls(
            portfolio_id=_required_text(payload, "portfolio_id"),
            market=_required_text(payload, "market"),
            cash_usdt=_required_decimal(payload, "cash_usdt"),
            equity_usdt=_required_decimal(payload, "equity_usdt"),
            initial_equity_usdt=_required_decimal(payload, "initial_equity_usdt"),
            inventory_quantity=_required_decimal(payload, "inventory_quantity"),
            inventory_cost_basis_usdt=_required_decimal(
                payload, "inventory_cost_basis_usdt"
            ),
            realized_pnl_usdt=_required_decimal(payload, "realized_pnl_usdt"),
            unrealized_pnl_usdt=_required_decimal(payload, "unrealized_pnl_usdt"),
            fees_paid_usdt=_required_decimal(payload, "fees_paid_usdt"),
            slippage_cost_usdt=_required_decimal(payload, "slippage_cost_usdt"),
            funding_cost_usdt=_required_decimal(payload, "funding_cost_usdt"),
            high_watermark_usdt=_optional_decimal(payload, "high_watermark_usdt"),
            max_drawdown_ratio=_required_decimal(payload, "max_drawdown_ratio"),
            current_open_risk_usdt=_required_decimal(payload, "current_open_risk_usdt"),
            consecutive_losses=_required_integer(payload, "consecutive_losses"),
            position_side=(
                VirtualPositionSide(_required_text_value(side, "position_side"))
                if side is not None
                else None
            ),
            position_entry_price=_optional_decimal(payload, "position_entry_price"),
            position_mark_price=_optional_decimal(payload, "position_mark_price"),
            position_notional_usdt=_optional_decimal(payload, "position_notional_usdt"),
            isolated_margin_usdt=_optional_decimal(payload, "isolated_margin_usdt"),
            initial_margin_usdt=_optional_decimal(payload, "initial_margin_usdt"),
            maintenance_margin_usdt=_optional_decimal(
                payload, "maintenance_margin_usdt"
            ),
            liquidation_price=_optional_decimal(payload, "liquidation_price"),
            leverage=(
                _required_integer_value(leverage, "leverage")
                if leverage is not None
                else None
            ),
            margin_utilization_ratio=_optional_decimal(
                payload, "margin_utilization_ratio"
            ),
            open_position_count=_required_integer(payload, "open_position_count"),
            max_concurrent_positions=_required_integer(
                payload, "max_concurrent_positions"
            ),
        )

    def __post_init__(self) -> None:
        if not self.portfolio_id.strip() or not self.market.strip():
            raise ValueError("virtual portfolio identity is required")
        if min(self.initial_equity_usdt, self.equity_usdt) <= ZERO:
            raise ValueError("virtual portfolio equity must be positive")
        if (
            min(
                self.cash_usdt,
                self.inventory_quantity,
                self.inventory_cost_basis_usdt,
                self.fees_paid_usdt,
                self.slippage_cost_usdt,
                self.current_open_risk_usdt,
            )
            < ZERO
        ):
            raise ValueError("virtual portfolio balances must be non-negative")
        if not ZERO <= self.max_drawdown_ratio <= ONE:
            raise ValueError(
                "virtual portfolio drawdown ratio must stay within zero and one"
            )
        if not self.funding_cost_usdt.is_finite():
            raise ValueError("virtual portfolio funding cost must be finite")
        if self.unrealized_pnl_usdt + self.cash_usdt < -self.equity_usdt:
            raise ValueError("virtual portfolio unrealized PnL is inconsistent")
        if self.open_position_count < 0 or self.max_concurrent_positions < 1:
            raise ValueError("virtual portfolio capacity must be positive")
        if self.consecutive_losses < 0:
            raise ValueError(
                "virtual portfolio consecutive loss count cannot be negative"
            )
        normalized_market = self.market.strip().upper()
        if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
            raise ValueError("virtual portfolio market must be SPOT or USD_M_FUTURES")
        object.__setattr__(self, "market", normalized_market)
        if self.high_watermark_usdt is None:
            object.__setattr__(self, "high_watermark_usdt", self.equity_usdt)
        high_watermark_usdt = self.high_watermark_usdt
        if high_watermark_usdt is None:
            high_watermark_usdt = self.equity_usdt
        elif high_watermark_usdt <= ZERO:
            raise ValueError("virtual portfolio high watermark must be positive")
        if high_watermark_usdt < self.equity_usdt:
            raise ValueError("virtual portfolio high watermark cannot trail equity")
        if normalized_market == "SPOT":
            if (
                self.inventory_quantity == ZERO
                and self.inventory_cost_basis_usdt != ZERO
            ):
                raise ValueError(
                    "Spot virtual portfolio cannot keep cost basis without inventory"
                )
            if self.cash_usdt > (
                high_watermark_usdt + self.realized_pnl_usdt + self.initial_equity_usdt
            ):
                raise ValueError(
                    "Spot virtual portfolio cash appears inconsistent with "
                    "independent capital"
                )
            if any(
                value is not None
                for value in (
                    self.position_side,
                    self.position_entry_price,
                    self.position_mark_price,
                    self.position_notional_usdt,
                    self.isolated_margin_usdt,
                    self.initial_margin_usdt,
                    self.maintenance_margin_usdt,
                    self.liquidation_price,
                    self.leverage,
                    self.margin_utilization_ratio,
                )
            ):
                raise ValueError(
                    "Spot virtual portfolio cannot contain Futures position fields"
                )
        if normalized_market == "USD_M_FUTURES":
            if (
                self.inventory_quantity != ZERO
                or self.inventory_cost_basis_usdt != ZERO
            ):
                raise ValueError(
                    "USD_M_FUTURES virtual portfolio cannot carry Spot inventory state"
                )
            futures_scalars = (
                self.position_entry_price,
                self.position_mark_price,
                self.position_notional_usdt,
                self.isolated_margin_usdt,
                self.initial_margin_usdt,
                self.maintenance_margin_usdt,
                self.liquidation_price,
                self.margin_utilization_ratio,
            )
            if self.open_position_count > 0:
                if self.position_side is None or any(
                    value is None for value in futures_scalars
                ):
                    raise ValueError(
                        "USD_M_FUTURES open virtual position requires full "
                        "margin evidence"
                    )
                if self.leverage is None or self.leverage < 1:
                    raise ValueError(
                        "USD_M_FUTURES open virtual position requires positive leverage"
                    )
                if not ZERO <= cast(Decimal, self.margin_utilization_ratio) <= ONE:
                    raise ValueError(
                        "USD_M_FUTURES margin utilization must stay within zero and one"
                    )
            elif self.position_side is not None:
                raise ValueError(
                    "USD_M_FUTURES flat virtual portfolio cannot keep directional "
                    "position state"
                )


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _required_text(payload: Mapping[str, object], key: str) -> str:
    return _required_text_value(payload.get(key), key)


def _required_text_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"virtual portfolio {label} must be non-empty text")
    return value.strip()


def _required_decimal(payload: Mapping[str, object], key: str) -> Decimal:
    value = payload.get(key)
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError) as error:
        raise ValueError(f"virtual portfolio {key} must be decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"virtual portfolio {key} must be finite")
    return parsed


def _optional_decimal(payload: Mapping[str, object], key: str) -> Decimal | None:
    if payload.get(key) is None:
        return None
    return _required_decimal(payload, key)


def _required_integer(payload: Mapping[str, object], key: str) -> int:
    return _required_integer_value(payload.get(key), key)


def _required_integer_value(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"virtual portfolio {label} must be integer")
    try:
        parsed = int(str(value))
    except (ValueError, TypeError) as error:
        raise ValueError(f"virtual portfolio {label} must be integer") from error
    if str(parsed) != str(value):
        raise ValueError(f"virtual portfolio {label} must be canonical integer")
    return parsed

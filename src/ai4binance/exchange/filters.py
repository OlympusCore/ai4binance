"""Decimal-safe Binance Spot filter parsing and order validation."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.exchange.models import FilterValue, SymbolInfo

ZERO = Decimal("0")


def _decimal_field(
    values: Mapping[str, FilterValue],
    field_name: str,
    *,
    default: Decimal | None = None,
) -> Decimal:
    raw_value = values.get(field_name)
    if raw_value is None and default is not None:
        return default
    if not isinstance(raw_value, (str, int, float)) or isinstance(raw_value, bool):
        raise ExchangePayloadError(f"filter field {field_name} is missing or invalid")
    try:
        parsed = Decimal(str(raw_value))
    except InvalidOperation:
        raise ExchangePayloadError(f"filter field {field_name} is invalid") from None
    if not parsed.is_finite() or parsed < ZERO:
        raise ExchangePayloadError(f"filter field {field_name} must be non-negative")
    return parsed


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= ZERO:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


@dataclass(frozen=True, slots=True)
class PriceFilter:
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal

    def round_down(self, price: Decimal) -> Decimal:
        return _round_down(price, self.tick_size)

    def blockers(self, price: Decimal) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.min_price > ZERO and price < self.min_price:
            blockers.append("PRICE_BELOW_MINIMUM")
        if self.max_price > ZERO and price > self.max_price:
            blockers.append("PRICE_ABOVE_MAXIMUM")
        if self.tick_size > ZERO and price % self.tick_size != ZERO:
            blockers.append("PRICE_TICK_SIZE_INVALID")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class LotSizeFilter:
    min_quantity: Decimal
    max_quantity: Decimal
    step_size: Decimal

    def round_down(self, quantity: Decimal) -> Decimal:
        return _round_down(quantity, self.step_size)

    def blockers(self, quantity: Decimal) -> tuple[str, ...]:
        blockers: list[str] = []
        if quantity < self.min_quantity:
            blockers.append("QUANTITY_BELOW_MINIMUM")
        if self.max_quantity > ZERO and quantity > self.max_quantity:
            blockers.append("QUANTITY_ABOVE_MAXIMUM")
        if self.step_size > ZERO and quantity % self.step_size != ZERO:
            blockers.append("QUANTITY_STEP_SIZE_INVALID")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class NotionalFilter:
    min_notional: Decimal
    max_notional: Decimal

    def blockers(self, price: Decimal, quantity: Decimal) -> tuple[str, ...]:
        notional = price * quantity
        blockers: list[str] = []
        if notional < self.min_notional:
            blockers.append("NOTIONAL_BELOW_MINIMUM")
        if self.max_notional > ZERO and notional > self.max_notional:
            blockers.append("NOTIONAL_ABOVE_MAXIMUM")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class SymbolFilters:
    """Mandatory Spot filters required for safe previews and execution checks."""

    price: PriceFilter
    lot_size: LotSizeFilter
    notional: NotionalFilter

    @classmethod
    def from_symbol_info(cls, symbol_info: SymbolInfo) -> "SymbolFilters":
        price_values = symbol_info.filters.get("PRICE_FILTER")
        lot_values = symbol_info.filters.get("LOT_SIZE")
        notional_values = symbol_info.filters.get("NOTIONAL")
        if notional_values is None:
            notional_values = symbol_info.filters.get("MIN_NOTIONAL")
        if price_values is None or lot_values is None or notional_values is None:
            raise ExchangePayloadError(
                "PRICE_FILTER, LOT_SIZE and NOTIONAL/MIN_NOTIONAL are required"
            )
        return cls(
            price=PriceFilter(
                min_price=_decimal_field(price_values, "minPrice"),
                max_price=_decimal_field(price_values, "maxPrice"),
                tick_size=_decimal_field(price_values, "tickSize"),
            ),
            lot_size=LotSizeFilter(
                min_quantity=_decimal_field(lot_values, "minQty"),
                max_quantity=_decimal_field(lot_values, "maxQty"),
                step_size=_decimal_field(lot_values, "stepSize"),
            ),
            notional=NotionalFilter(
                min_notional=_decimal_field(notional_values, "minNotional"),
                max_notional=_decimal_field(
                    notional_values,
                    "maxNotional",
                    default=ZERO,
                ),
            ),
        )

    def validate_order(self, price: Decimal, quantity: Decimal) -> tuple[str, ...]:
        if price <= ZERO or quantity <= ZERO:
            return ("PRICE_AND_QUANTITY_MUST_BE_POSITIVE",)
        return tuple(
            dict.fromkeys(
                (
                    *self.price.blockers(price),
                    *self.lot_size.blockers(quantity),
                    *self.notional.blockers(price, quantity),
                )
            )
        )

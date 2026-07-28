"""Binance Spot filter parsing and Decimal-safe rounding tests."""

from decimal import Decimal

import pytest

from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import SymbolInfo


def symbol_info() -> SymbolInfo:
    return SymbolInfo(
        symbol="HOTUSDT",
        status="TRADING",
        base_asset="HOT",
        quote_asset="USDT",
        filters={
            "PRICE_FILTER": {
                "minPrice": "0.0001",
                "maxPrice": "10",
                "tickSize": "0.0001",
            },
            "LOT_SIZE": {
                "minQty": "10",
                "maxQty": "1000000",
                "stepSize": "10",
            },
            "NOTIONAL": {
                "minNotional": "5",
                "maxNotional": "1000",
            },
        },
    )


def test_symbol_filters_round_down_and_validate_order() -> None:
    filters = SymbolFilters.from_symbol_info(symbol_info())
    assert filters.price.round_down(Decimal("0.00129")) == Decimal("0.0012")
    assert filters.lot_size.round_down(Decimal("123")) == Decimal("120")
    assert filters.validate_order(Decimal("0.1"), Decimal("100")) == ()
    assert filters.validate_order(Decimal("0"), Decimal("100")) == (
        "PRICE_AND_QUANTITY_MUST_BE_POSITIVE",
    )


def test_symbol_filters_return_complete_blocker_list() -> None:
    filters = SymbolFilters.from_symbol_info(symbol_info())
    blockers = filters.validate_order(Decimal("0.00015"), Decimal("11"))
    assert blockers == (
        "PRICE_TICK_SIZE_INVALID",
        "QUANTITY_STEP_SIZE_INVALID",
        "NOTIONAL_BELOW_MINIMUM",
    )
    blockers = filters.validate_order(Decimal("10.1"), Decimal("1000001"))
    assert "PRICE_ABOVE_MAXIMUM" in blockers
    assert "QUANTITY_ABOVE_MAXIMUM" in blockers
    assert "NOTIONAL_ABOVE_MAXIMUM" in blockers


def test_symbol_filters_support_min_notional_fallback() -> None:
    info = symbol_info()
    filters = dict(info.filters)
    notional = filters.pop("NOTIONAL")
    filters["MIN_NOTIONAL"] = {"minNotional": notional["minNotional"]}
    parsed = SymbolFilters.from_symbol_info(
        SymbolInfo("HOTUSDT", "TRADING", "HOT", "USDT", filters)
    )
    assert parsed.notional.max_notional == Decimal("0")


def test_symbol_filters_reject_missing_and_invalid_rules() -> None:
    info = symbol_info()
    with pytest.raises(ExchangePayloadError, match="are required"):
        SymbolFilters.from_symbol_info(
            SymbolInfo(
                info.symbol,
                info.status,
                info.base_asset,
                info.quote_asset,
                {"PRICE_FILTER": info.filters["PRICE_FILTER"]},
            )
        )
    filters = dict(info.filters)
    filters["LOT_SIZE"] = {
        "minQty": "not-decimal",
        "maxQty": "100",
        "stepSize": "1",
    }
    with pytest.raises(ExchangePayloadError, match="minQty"):
        SymbolFilters.from_symbol_info(
            SymbolInfo("HOTUSDT", "TRADING", "HOT", "USDT", filters)
        )

"""Binance public payload parsing tests."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from ai4binance.exchange.client import BinancePublicClient
from ai4binance.exchange.errors import ExchangePayloadError

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)


def exchange_info_payload() -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": "HOTUSDT",
                "status": "TRADING",
                "baseAsset": "HOT",
                "quoteAsset": "USDT",
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.000001",
                        "maxPrice": "10",
                        "tickSize": "0.000001",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "1",
                        "maxQty": "1000000",
                        "stepSize": "1",
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": "5",
                        "maxNotional": "10000",
                    },
                ],
            }
        ]
    }


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, str | int] | None]] = []

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        self.calls.append((path, params))
        if path == "/api/v3/time":
            return {"serverTime": NOW_MS}
        if path == "/api/v3/exchangeInfo":
            return exchange_info_payload()
        if path == "/api/v3/ticker/price":
            return {"symbol": "HOTUSDT", "price": "0.001234"}
        if path == "/api/v3/ticker/bookTicker":
            return {
                "symbol": "HOTUSDT",
                "bidPrice": "0.001233",
                "askPrice": "0.001235",
            }
        if path == "/api/v3/klines":
            return [
                [
                    NOW_MS - 7_200_000,
                    "0.001",
                    "0.0013",
                    "0.0009",
                    "0.0012",
                    "1000",
                    NOW_MS - 3_600_001,
                ]
            ]
        raise AssertionError(f"unexpected path: {path}")


def test_public_client_parses_all_supported_market_payloads() -> None:
    transport = FakeTransport()
    client = BinancePublicClient(transport)

    assert client.server_time() == NOW
    symbol_info = client.exchange_info(" hotusdt ")
    assert symbol_info.status == "TRADING"
    assert symbol_info.filters["PRICE_FILTER"]["tickSize"] == "0.000001"
    assert str(client.ticker_price("HOTUSDT")) == "0.001234"
    book = client.book_ticker("HOTUSDT")
    assert str(book.spread) == "0.000002"
    klines = client.klines("HOTUSDT", "1h", 100)
    assert len(klines) == 1
    assert str(klines[0].close) == "0.0012"
    assert transport.calls[-1][1] == {
        "symbol": "HOTUSDT",
        "interval": "1h",
        "limit": 100,
    }


@pytest.mark.parametrize("symbol", ["", "HOT/USDT", "HÖTUSDT"])
def test_public_client_rejects_unsafe_symbols(symbol: str) -> None:
    with pytest.raises(ValueError, match="ASCII alphanumeric"):
        BinancePublicClient(FakeTransport()).ticker_price(symbol)


def test_public_client_rejects_invalid_interval_and_limit() -> None:
    client = BinancePublicClient(FakeTransport())
    with pytest.raises(ValueError, match="unsupported Binance interval"):
        client.klines("HOTUSDT", "7m", 100)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        client.klines("HOTUSDT", "1h", 1001)


class InvalidTransport:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del path, params
        return self.payload


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"serverTime": "not-an-int"},
        {"serverTime": True},
    ],
)
def test_server_time_rejects_invalid_payload(payload: object) -> None:
    with pytest.raises(ExchangePayloadError):
        BinancePublicClient(InvalidTransport(payload)).server_time()


def test_exchange_info_rejects_missing_or_unknown_filter_values() -> None:
    with pytest.raises(ExchangePayloadError, match="exactly one symbol"):
        BinancePublicClient(InvalidTransport({"symbols": []})).exchange_info("HOTUSDT")
    payload = exchange_info_payload()
    symbols = payload["symbols"]
    assert isinstance(symbols, list)
    symbol = symbols[0]
    assert isinstance(symbol, dict)
    filters = symbol["filters"]
    assert isinstance(filters, list)
    filters.append({"filterType": "BROKEN", "nested": {"unsafe": True}})
    with pytest.raises(ExchangePayloadError, match="unsupported value"):
        BinancePublicClient(InvalidTransport(payload)).exchange_info("HOTUSDT")


def test_kline_rejects_short_or_invalid_numeric_payload() -> None:
    with pytest.raises(ExchangePayloadError, match="seven values"):
        BinancePublicClient(InvalidTransport([[1, 2]])).klines("HOTUSDT", "1h", 2)
    invalid = [[NOW_MS - 1000, "bad", "2", "1", "1", "1", NOW_MS]]
    with pytest.raises(ExchangePayloadError, match="decimal-compatible"):
        BinancePublicClient(InvalidTransport(invalid)).klines("HOTUSDT", "1h", 2)

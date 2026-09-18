"""Focused edge coverage for Binance USD-M public derivatives parsing."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

import ai4binance.whale_fusion.derivatives.binance_client as binance_client_module
from ai4binance.core.errors import (
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeTransportError,
)
from ai4binance.whale_fusion.derivatives.binance_client import (
    BinanceUsdMClient,
    UsdMFuturesPublicTransport,
)

NOW = datetime(2026, 9, 16, tzinfo=UTC)


class StaticTransport:
    def __init__(self, payloads: Mapping[str, object]) -> None:
        self.payloads = dict(payloads)

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        return self.payloads[path]


def test_usdm_transport_rejects_unsafe_bounds_and_paths() -> None:
    with pytest.raises(ValueError, match="official HTTPS"):
        UsdMFuturesPublicTransport(base_url="https://example.com")
    with pytest.raises(ValueError, match="retry and timeout"):
        UsdMFuturesPublicTransport(timeout_seconds=0)
    with pytest.raises(ValueError, match="bounds"):
        UsdMFuturesPublicTransport(max_response_bytes=10)

    transport = UsdMFuturesPublicTransport(sleeper=lambda _: None)
    with pytest.raises(ValueError, match="approved"):
        transport.get_json("/fapi/v1/order")

    assert transport._delay(1, "2") == Decimal("2")
    assert transport._delay(1, "bad") == Decimal("0.25")


class RetryingTransport(UsdMFuturesPublicTransport):
    def __init__(self, outcomes: list[object]) -> None:
        super().__init__(sleeper=lambda _: None, max_attempts=2)
        self.outcomes = outcomes

    def _request_once(self, url: str, path: str) -> object:
        del url, path
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_usdm_transport_retries_and_fails_closed() -> None:
    retryable_http = HTTPError(
        "https://fapi.binance.com/fapi/v1/openInterest",
        429,
        "rate limited",
        Message(),
        None,
    )
    assert RetryingTransport([retryable_http, {"ok": True}]).get_json(
        "/fapi/v1/openInterest"
    ) == {"ok": True}

    with pytest.raises(ExchangeHttpError, match="HTTP 400"):
        RetryingTransport(
            [
                HTTPError(
                    "https://fapi.binance.com/fapi/v1/openInterest",
                    400,
                    "bad",
                    Message(),
                    None,
                )
            ]
        ).get_json("/fapi/v1/openInterest")

    with pytest.raises(ExchangeTransportError, match="request failed"):
        RetryingTransport([URLError("down"), URLError("down")]).get_json(
            "/fapi/v1/openInterest"
        )


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, size: int) -> bytes:
        del size
        return self.payload


def test_usdm_transport_request_once_rejects_large_or_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = UsdMFuturesPublicTransport(max_response_bytes=1024)

    monkeypatch.setattr(
        binance_client_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"x" * 1025),
    )
    with pytest.raises(ExchangePayloadError, match="too large"):
        transport._request_once(
            "https://fapi.binance.com/fapi/v1/openInterest",
            "/fapi/v1/openInterest",
        )

    monkeypatch.setattr(
        binance_client_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"{not-json"),
    )
    with pytest.raises(ExchangePayloadError, match="invalid"):
        transport._request_once(
            "https://fapi.binance.com/fapi/v1/openInterest",
            "/fapi/v1/openInterest",
        )


def test_derivatives_client_covers_zero_basis_depth_and_trade_edges() -> None:
    payloads: dict[str, object] = {
        "/futures/data/openInterestHist": [
            {
                "timestamp": 1_700_000_000_000,
                "sumOpenInterest": "10",
                "sumOpenInterestValue": "100",
            }
        ],
        "/futures/data/topLongShortAccountRatio": [
            {"timestamp": 1_700_000_000_000, "longShortRatio": "1.2"}
        ],
        "/futures/data/topLongShortPositionRatio": [
            {"timestamp": 1_700_000_000_000, "longShortRatio": "1.1"}
        ],
        "/futures/data/globalLongShortAccountRatio": [
            {"timestamp": 1_700_000_000_000, "longShortRatio": "0.9"}
        ],
        "/futures/data/takerlongshortRatio": [
            {"timestamp": 1_700_000_000_000, "buySellRatio": "1.0"}
        ],
        "/fapi/v1/fundingRate": [
            {"fundingTime": 1_700_000_000_000, "fundingRate": "0.0001"}
        ],
        "/fapi/v1/premiumIndex": {
            "time": 1_700_000_000_000,
            "markPrice": "0",
            "indexPrice": "0",
        },
        "/fapi/v1/depth": {"bids": [["1", "0"]], "asks": [["1", "0"]]},
        "/fapi/v1/aggTrades": [
            {"T": 1_700_000_000_000, "p": "10", "q": "1", "m": True},
            {"T": 1_700_000_000_000, "p": "100000", "q": "2", "m": False},
        ],
    }
    transport = StaticTransport(payloads)
    client = BinanceUsdMClient(transport, clock=lambda: NOW)

    dataset = client.collect(" btcusdt ", period="1h", limit=1)
    assert dataset.symbol == "BTCUSDT"

    with pytest.raises(ExchangePayloadError, match="depth notional"):
        client.order_book_imbalance("BTCUSDT", limit=5)

    large = client.large_aggregate_trades("BTCUSDT", minimum_notional=Decimal("100000"))
    assert len(large) == 1
    assert large[0].attributes == {"aggressor_side": "BUY"}

    transport.payloads["/fapi/v1/aggTrades"] = [
        {"T": 1_700_000_000_000, "p": "100000", "q": "2", "m": "bad"}
    ]
    with pytest.raises(ExchangePayloadError, match="boolean"):
        client.large_aggregate_trades("BTCUSDT", minimum_notional=Decimal("1"))


def test_derivatives_client_helper_fail_closed_paths() -> None:
    client = BinanceUsdMClient(StaticTransport({}), clock=lambda: NOW)

    with pytest.raises(ValueError, match="symbol"):
        client.current_open_interest("BTC/USDT")
    with pytest.raises(ValueError, match="period"):
        client.collect("BTCUSDT", period="3m")
    with pytest.raises(ValueError, match="depth limit"):
        client.order_book_imbalance("BTCUSDT", limit=7)
    with pytest.raises(ValueError, match="aggregate-trade"):
        client.large_aggregate_trades("BTCUSDT", limit=0)
    with pytest.raises(ExchangePayloadError, match="object"):
        BinanceUsdMClient._mapping([], "payload")
    with pytest.raises(ExchangePayloadError, match="array"):
        BinanceUsdMClient._sequence({}, "payload")
    with pytest.raises(ExchangePayloadError, match="timestamp"):
        BinanceUsdMClient._timestamp(True, "time")
    with pytest.raises(ExchangePayloadError, match="decimal-compatible"):
        BinanceUsdMClient._decimal(object(), "value")
    with pytest.raises(ExchangePayloadError, match="decimal-compatible"):
        BinanceUsdMClient._decimal("bad", "value")
    with pytest.raises(ExchangePayloadError, match="finite"):
        BinanceUsdMClient._decimal("NaN", "value")
    with pytest.raises(ExchangePayloadError, match="price and quantity"):
        BinanceUsdMClient._book_notional([["1"]], "depth.bids")


def test_liquidation_event_uses_fallback_price() -> None:
    client = BinanceUsdMClient(StaticTransport({}), clock=lambda: NOW)

    point = client.liquidation_event(
        {
            "E": 1_700_000_000_000,
            "o": {
                "s": "BTCUSDT",
                "ap": "0",
                "p": "100",
                "q": "2",
                "S": "SELL",
            },
        }
    )

    assert point.value == Decimal("200")
    with pytest.raises(ExchangePayloadError, match="side"):
        client.liquidation_event(
            {
                "E": 1_700_000_000_000,
                "o": {"s": "BTCUSDT", "ap": "1", "p": "1", "q": "1", "S": "BAD"},
            }
        )

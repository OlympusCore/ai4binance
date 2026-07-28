"""Binance USD-M public collector and transport tests."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from email.message import Message
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import ai4binance.whale_fusion.derivatives.binance_client as client_module
from ai4binance.exchange.errors import ExchangeHttpError, ExchangePayloadError
from ai4binance.whale_fusion.derivatives import (
    BinanceUsdMClient,
    UsdMFuturesPublicTransport,
)
from ai4binance.whale_fusion.models import DerivativesMetric

NOW = datetime(2026, 7, 13, tzinfo=UTC)


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        supplied = dict(params or {})
        self.calls.append((path, supplied))
        if path == "/futures/data/openInterestHist":
            return [
                {
                    "sumOpenInterest": "100",
                    "sumOpenInterestValue": "200",
                    "timestamp": 1000,
                },
                {
                    "sumOpenInterest": "110",
                    "sumOpenInterestValue": "220",
                    "timestamp": 2000,
                },
            ]
        if path in {
            "/futures/data/topLongShortAccountRatio",
            "/futures/data/topLongShortPositionRatio",
            "/futures/data/globalLongShortAccountRatio",
        }:
            return [{"longShortRatio": "1.2", "timestamp": 1000}]
        if path == "/futures/data/takerlongshortRatio":
            return [{"buySellRatio": "1.5", "timestamp": 1000}]
        if path == "/fapi/v1/fundingRate":
            return [{"fundingRate": "0.001", "fundingTime": 1000}]
        if path == "/fapi/v1/premiumIndex":
            return {"markPrice": "1.01", "indexPrice": "1", "time": 2000}
        if path == "/fapi/v1/openInterest":
            return {"openInterest": "123", "time": 2000}
        if path == "/fapi/v1/depth":
            return {"bids": [["10", "3"]], "asks": [["10", "1"]]}
        if path == "/fapi/v1/aggTrades":
            return [
                {"p": "10", "q": "2", "T": 1000, "m": False},
                {"p": "10", "q": "20", "T": 2000, "m": True},
            ]
        raise AssertionError(path)


def test_client_collects_all_phase_two_public_metrics() -> None:
    transport = RecordingTransport()
    client = BinanceUsdMClient(transport, clock=lambda: NOW)
    result = client.collect("hotusdt", "1h", 100)
    assert result.symbol == "HOTUSDT"
    assert result.values(DerivativesMetric.OPEN_INTEREST) == (
        Decimal("100"),
        Decimal("110"),
    )
    assert result.values(DerivativesMetric.OPEN_INTEREST_VALUE) == (
        Decimal("200"),
        Decimal("220"),
    )
    assert result.values(DerivativesMetric.TOP_ACCOUNT_RATIO) == (Decimal("1.2"),)
    assert result.values(DerivativesMetric.FUNDING_RATE) == (Decimal("0.001"),)
    assert result.values(DerivativesMetric.MARK_PRICE) == (Decimal("1.01"),)
    assert result.values(DerivativesMetric.BASIS_RATE) == (Decimal("0.01"),)
    assert len(transport.calls) == 7
    assert all(call[1]["symbol"] == "HOTUSDT" for call in transport.calls)
    current = client.current_open_interest("hotusdt")
    assert current.value == 123


def test_client_normalizes_depth_large_trades_and_liquidation() -> None:
    client = BinanceUsdMClient(RecordingTransport(), clock=lambda: NOW)
    imbalance = client.order_book_imbalance("HOTUSDT", 100)
    assert imbalance.value == Decimal("0.5")

    trades = client.large_aggregate_trades("HOTUSDT", minimum_notional=Decimal("100"))
    assert tuple(point.value for point in trades) == (Decimal("200"),)
    assert trades[0].attributes["aggressor_side"] == "SELL"

    liquidation = client.liquidation_event(
        {"E": 3000, "o": {"s": "HOTUSDT", "S": "SELL", "ap": "10", "q": "5"}}
    )
    assert liquidation.value == Decimal("50")
    assert liquidation.attributes == {"symbol": "HOTUSDT", "side": "SELL"}


def test_microstructure_parsers_reject_invalid_bounds_and_payloads() -> None:
    client = BinanceUsdMClient(RecordingTransport(), clock=lambda: NOW)
    with pytest.raises(ValueError, match="depth limit"):
        client.order_book_imbalance("HOTUSDT", 7)
    with pytest.raises(ValueError, match="aggregate-trade bounds"):
        client.large_aggregate_trades("HOTUSDT", minimum_notional=Decimal("0"))
    with pytest.raises(ExchangePayloadError, match="side"):
        client.liquidation_event(
            {"E": 3000, "o": {"s": "HOTUSDT", "S": "INVALID", "ap": "10", "q": "5"}}
        )


def test_client_rejects_invalid_bounds_and_payloads() -> None:
    client = BinanceUsdMClient(RecordingTransport(), clock=lambda: NOW)
    with pytest.raises(ValueError, match="period or limit"):
        client.collect("HOTUSDT", "3h", 100)
    with pytest.raises(ValueError, match="symbol"):
        client.collect("HOT/USDT")

    class BadTransport:
        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            del path, params
            return {"unexpected": True}

    with pytest.raises(ExchangePayloadError):
        BinanceUsdMClient(BadTransport(), clock=lambda: NOW).collect("HOTUSDT")


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, size: int) -> bytes:
        return self.payload[:size]


def test_transport_is_get_only_sorted_and_host_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        assert request.method == "GET"
        assert timeout == 3
        urls.append(request.full_url)
        return FakeResponse(b"[]")

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    transport = UsdMFuturesPublicTransport(timeout_seconds=3)
    assert (
        transport.get_json(
            "/futures/data/openInterestHist", {"symbol": "HOTUSDT", "period": "1h"}
        )
        == []
    )
    assert urls == [
        "https://fapi.binance.com/futures/data/openInterestHist?period=1h&symbol=HOTUSDT"
    ]
    with pytest.raises(ValueError, match="approved"):
        transport.get_json("/fapi/v1/order")
    with pytest.raises(ValueError, match="official"):
        UsdMFuturesPublicTransport(base_url="https://example.com")


def test_transport_retries_and_sanitizes_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        nonlocal attempts
        del timeout
        attempts += 1
        headers = Message()
        headers["Retry-After"] = "2"
        raise HTTPError(request.full_url, 429, "limited", headers, None)

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    transport = UsdMFuturesPublicTransport(
        max_attempts=2, max_backoff_seconds=1, sleeper=delays.append
    )
    with pytest.raises(ExchangeHttpError) as error:
        transport.get_json("/fapi/v1/openInterest", {"symbol": "SECRET"})
    assert attempts == 2
    assert delays == [1]
    assert "SECRET" not in str(error.value)

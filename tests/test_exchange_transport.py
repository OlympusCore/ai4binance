"""Bounded public HTTPS transport tests."""

from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import ai4binance.exchange.transport as transport_module
from ai4binance.exchange.errors import (
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeTransportError,
)
from ai4binance.exchange.transport import UrllibJsonTransport


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, size: int) -> bytes:
        return self.payload[:size]


def test_transport_fetches_sorted_query_over_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_urls: list[str] = []

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        assert timeout == 3.0
        captured_urls.append(request.full_url)
        assert request.method == "GET"
        return FakeResponse(b'{"serverTime":123}')

    monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)
    transport = UrllibJsonTransport(timeout_seconds=3.0)
    result = transport.get_json("/api/v3/time", {"z": 2, "a": "x"})
    assert result == {"serverTime": 123}
    assert captured_urls == ["https://data-api.binance.vision/api/v3/time?a=x&z=2"]


def test_transport_retries_network_failure_with_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        nonlocal attempts
        del request, timeout
        attempts += 1
        if attempts < 3:
            raise URLError("temporary")
        return FakeResponse(b"[]")

    monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)
    transport = UrllibJsonTransport(
        max_attempts=3,
        backoff_seconds=0.5,
        sleeper=delays.append,
    )
    assert transport.get_json("/api/v3/klines") == []
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_transport_honors_capped_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []
    headers = Message()
    headers["Retry-After"] = "60"

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        nonlocal attempts
        del timeout
        attempts += 1
        if attempts == 1:
            raise HTTPError(request.full_url, 429, "rate limit", headers, None)
        return FakeResponse(b"{}")

    monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)
    transport = UrllibJsonTransport(
        max_attempts=2,
        max_backoff_seconds=2.0,
        sleeper=delays.append,
    )
    assert transport.get_json("/api/v3/time") == {}
    assert delays == [2.0]


def test_transport_fails_closed_without_leaking_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        del timeout
        raise HTTPError(request.full_url, 400, "bad", Message(), None)

    monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)
    with pytest.raises(ExchangeHttpError) as error:
        UrllibJsonTransport().get_json(
            "/api/v3/ticker/price",
            {"symbol": "HOTUSDT"},
        )
    assert "HOTUSDT" not in str(error.value)
    assert "/api/v3/ticker/price" in str(error.value)


def test_transport_rejects_invalid_json_and_oversized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transport_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"not-json"),
    )
    with pytest.raises(ExchangePayloadError, match="invalid"):
        UrllibJsonTransport().get_json("/api/v3/time")

    monkeypatch.setattr(
        transport_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"x" * 1025),
    )
    with pytest.raises(ExchangePayloadError, match="too large"):
        UrllibJsonTransport(max_response_bytes=1024).get_json("/api/v3/time")


def test_transport_rejects_unsafe_configuration_and_paths() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        UrllibJsonTransport(base_url="http://example.com")
    with pytest.raises(ValueError, match="public API v3"):
        UrllibJsonTransport().get_json("file:///etc/passwd")
    with pytest.raises(ValueError, match="public API v3"):
        UrllibJsonTransport().get_json("/api/v3/time?secret=value")


def test_transport_exhaustion_returns_sanitized_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transport_module,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("private detail")),
    )
    with pytest.raises(ExchangeTransportError) as error:
        UrllibJsonTransport(max_attempts=1).get_json("/api/v3/time")
    assert "private detail" not in str(error.value)

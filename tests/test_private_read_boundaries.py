"""Signed read boundaries reject unsafe requests without external traffic."""

from dataclasses import replace
from email.message import Message
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from ai4binance.core.errors import ExchangeHttpError
from ai4binance.exchange.private import (
    BinancePrivateAccountReader,
    BinanceUsdMPrivateAccountReader,
    SignedReadOnlyRequestFactory,
    SignedUsdMReadOnlyRequestFactory,
    UrllibPrivateJsonTransport,
)
from tests.test_private_security import RecordingTransport, factory


@pytest.mark.parametrize(
    "signer", [SignedReadOnlyRequestFactory, SignedUsdMReadOnlyRequestFactory]
)
def test_signers_reject_noncanonical_hosts_windows_and_control_overrides(
    signer: type[SignedReadOnlyRequestFactory] | type[SignedUsdMReadOnlyRequestFactory],
) -> None:
    credentials = factory().credentials
    with pytest.raises(ValueError, match="official HTTPS host"):
        signer(credentials, base_url="http://api.binance.com")
    for window in (999, 60_001):
        with pytest.raises(ValueError, match="between 1000 and 60000"):
            signer(credentials, receive_window_ms=window)
    request_factory = signer(credentials)
    path = (
        "/api/v3/account"
        if signer is SignedReadOnlyRequestFactory
        else "/fapi/v2/account"
    )
    for key in ("timestamp", "recvWindow", "signature"):
        with pytest.raises(ValueError, match="managed internally"):
            request_factory.build(path, {key: "override"})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("timeout_seconds", 0, "positive"),
        ("max_attempts", 0, "between 1 and 5"),
        ("max_attempts", 6, "between 1 and 5"),
        ("backoff_seconds", -1, "bounds"),
        ("max_response_bytes", 1023, "bounds"),
    ],
)
def test_private_transport_rejects_unbounded_configuration(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(UrllibPrivateJsonTransport(), **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("url", "method", "headers", "message"),
    [
        ("https://api.binance.com/api/v3/account", "POST", {}, "GET only"),
        ("https://api.binance.com/api/v3/order", "GET", {}, "not read-only"),
        ("https://api.binance.com/api/v3/account", "GET", {}, "API key header"),
        (
            "https://api.binance.com/api/v3/account",
            "GET",
            {"X-MBX-APIKEY": "test-placeholder"},
            "signed query controls",
        ),
    ],
)
def test_forged_private_requests_are_rejected_before_transport(
    url: str, method: str, headers: dict[str, str], message: str
) -> None:
    calls: list[Request] = []

    def loader(request: Request, timeout: float, limit: int) -> bytes:
        calls.append(request)
        return b"{}"

    transport = UrllibPrivateJsonTransport(response_loader=loader)
    with pytest.raises(ValueError, match=message):
        transport.get_json(
            Request(url, headers=headers, method=method)  # noqa: S310 - Offline fixture.
        )
    assert calls == []


@pytest.mark.parametrize(
    ("status", "expected_attempts"), [(400, 1), (418, 3), (429, 3), (500, 3)]
)
def test_private_http_failures_obey_retry_bounds_and_redact_details(
    status: int, expected_attempts: int
) -> None:
    calls = []
    delays: list[float] = []

    def loader(request: Request, timeout: float, limit: int) -> bytes:
        calls.append((timeout, limit))
        raise HTTPError(
            request.full_url, status, "sensitive-response-placeholder", Message(), None
        )

    transport = UrllibPrivateJsonTransport(
        response_loader=loader, sleeper=delays.append
    )
    with pytest.raises(ExchangeHttpError) as error:
        transport.get_json(factory().build("/api/v3/account"))
    assert len(calls) == expected_attempts
    assert delays == ([0.25, 0.5] if expected_attempts == 3 else [])
    assert "sensitive-response-placeholder" not in str(error.value)
    assert "signature=" not in str(error.value)


@pytest.mark.parametrize("usd_m", [False, True])
def test_account_readers_reject_history_bounds_without_sending_requests(
    usd_m: bool,
) -> None:
    transport = RecordingTransport()
    reader = (
        BinanceUsdMPrivateAccountReader(
            SignedUsdMReadOnlyRequestFactory(factory().credentials), transport
        )
        if usd_m
        else BinancePrivateAccountReader(factory(), transport)
    )
    for method in (reader.all_orders, reader.trades):
        for limit in (0, 1001):
            with pytest.raises(ValueError, match="limit"):
                method("BTCUSDT", limit=limit)
    with pytest.raises(ValueError, match="ASCII alphanumeric"):
        reader.open_orders("BTC/USDT")
    if isinstance(reader, BinanceUsdMPrivateAccountReader):
        with pytest.raises(ValueError, match="income limit"):
            reader.income(limit=0)
    else:
        with pytest.raises(ValueError, match="from_id"):
            reader.trades("BTCUSDT", from_id=-1)
        with pytest.raises(ValueError, match="transfer type"):
            reader.universal_transfers("UNAPPROVED")
        with pytest.raises(ValueError, match="transfer history limit"):
            reader.universal_transfers("MAIN_UMFUTURE", limit=0)
    assert transport.requests == []


def test_readers_preserve_optional_filters_and_paginated_fill_identity() -> None:
    transport = RecordingTransport()
    spot = BinancePrivateAccountReader(factory(), transport)
    assert spot.trades(" btcusdt ", from_id=0, limit=1) == {"ok": True}
    query = parse_qs(urlparse(transport.requests[-1].full_url).query)
    assert query["fromId"] == ["0"]
    assert query["symbol"] == ["BTCUSDT"]
    futures = BinanceUsdMPrivateAccountReader(
        SignedUsdMReadOnlyRequestFactory(factory().credentials), transport
    )
    for method in (
        spot.open_orders,
        futures.positions,
        futures.open_orders,
        futures.income,
        futures.algo_open_orders,
        futures.leverage_bracket,
    ):
        assert method() == {"ok": True}
        assert "symbol" not in parse_qs(urlparse(transport.requests[-1].full_url).query)
        assert transport.requests[-1].method == "GET"

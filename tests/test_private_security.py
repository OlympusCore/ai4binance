"""Private read-only signing and secret-handling security tests."""

import os
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from ai4binance.exchange.errors import ExchangePayloadError, ExchangeTransportError
from ai4binance.exchange.private import (
    BinancePrivateAccountReader,
    BinanceUsdMPrivateAccountReader,
    PrivateCredentials,
    SignedReadOnlyRequestFactory,
    SignedUsdMReadOnlyRequestFactory,
    UrllibPrivateJsonTransport,
)


def factory() -> SignedReadOnlyRequestFactory:
    return SignedReadOnlyRequestFactory(
        PrivateCredentials("public-key", "private-secret"),
        clock_ms=lambda: 1_700_000_000_000,
    )


def test_credentials_load_from_environment_without_repr_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "key-from-env")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret-from-env")
    credentials = PrivateCredentials.from_environment()
    assert credentials.api_key == "key-from-env"
    assert "key-from-env" not in repr(credentials)
    assert "secret-from-env" not in repr(credentials)


def test_credentials_load_allowlisted_file_without_environment_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    path = secrets / "bnc.env"
    path.write_text(
        "IGNORED_SETTING=value\n"
        "BINANCE_API_KEY='file-key'\n"
        'BINANCE_API_SECRET="file-secret"\n',
        encoding="utf-8",
    )

    credentials = PrivateCredentials.from_environment_or_file(Path("secrets/bnc.env"))

    assert credentials.api_key == "file-key"
    assert credentials.api_secret == "file-secret"  # noqa: S105
    assert "file-key" not in repr(credentials)
    assert "file-secret" not in repr(credentials)
    assert "BINANCE_API_KEY" not in os.environ
    assert "BINANCE_API_SECRET" not in os.environ


def test_credentials_reject_source_mixing_and_unsafe_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    path = secrets / "bnc.env"
    path.write_text(
        "BINANCE_API_KEY=file-key\nBINANCE_API_SECRET=file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BINANCE_API_KEY", "environment-key")
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    with pytest.raises(ValueError, match="credentials are required"):
        PrivateCredentials.from_environment_or_file(Path("secrets/bnc.env"))

    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="not allowlisted"):
        PrivateCredentials.from_file(path.resolve())
    path.write_text(
        "BINANCE_API_KEY=one\nBINANCE_API_KEY=two\nBINANCE_API_SECRET=secret\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate credential"):
        PrivateCredentials.from_file(Path("secrets/bnc.env"))


def test_credentials_file_failure_paths_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    relative = Path("secrets/bnc.env")
    with pytest.raises(ValueError, match="unavailable"):
        PrivateCredentials.from_file(relative)

    relative.parent.mkdir()
    relative.write_text("not an assignment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid assignment"):
        PrivateCredentials.from_file(relative)

    relative.write_text(
        'BINANCE_API_KEY="unterminated\nBINANCE_API_SECRET=value\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid quoting"):
        PrivateCredentials.from_file(relative)

    relative.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="must be UTF-8"):
        PrivateCredentials.from_file(relative)

    relative.write_bytes(b"x" * 16_385)
    with pytest.raises(ValueError, match="size limit"):
        PrivateCredentials.from_file(relative)


def test_complete_environment_pair_takes_atomic_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", "environment-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "environment-secret")

    credentials = PrivateCredentials.from_environment_or_file(Path("secrets/bnc.env"))

    assert credentials.api_key == "environment-key"
    assert credentials.api_secret.endswith("-secret")


def test_signed_request_is_get_only_and_secret_safe() -> None:
    request = factory().build("/api/v3/openOrders", {"symbol": "HOTUSDT"})
    parsed = urlparse(request.full_url)
    query = parse_qs(parsed.query)
    assert request.method == "GET"
    assert parsed.netloc == "api.binance.com"
    assert query["timestamp"] == ["1700000000000"]
    assert query["recvWindow"] == ["60000"]
    assert len(query["signature"][0]) == 64
    assert request.get_header("X-mbx-apikey") == "public-key"
    assert "private-secret" not in request.full_url


@pytest.mark.parametrize(
    "path",
    ["/api/v3/order", "/api/v3/order/test", "/sapi/v1/capital/withdraw/apply"],
)
def test_signer_rejects_write_paths(path: str) -> None:
    with pytest.raises(ValueError, match="read-only"):
        factory().build(path)


def test_signer_rejects_overrides_and_unofficial_host() -> None:
    with pytest.raises(ValueError, match="managed internally"):
        factory().build("/api/v3/account", {"timestamp": 1})
    with pytest.raises(ValueError, match="official HTTPS host"):
        SignedReadOnlyRequestFactory(
            PrivateCredentials("key", "secret"),
            base_url="https://evil.invalid",
        )


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    def get_json(self, request: Request) -> object:
        self.requests.append(request)
        return {"ok": True}


def test_private_reader_has_no_order_write_surface() -> None:
    transport = RecordingTransport()
    reader = BinancePrivateAccountReader(factory(), transport)
    assert reader.account() == {"ok": True}
    assert reader.open_orders("hotusdt") == {"ok": True}
    assert reader.all_orders("hotusdt") == {"ok": True}
    assert reader.universal_transfers("MAIN_UMFUTURE") == {"ok": True}
    assert len(transport.requests) == 4
    assert not hasattr(reader, "create_order")
    assert not hasattr(reader, "cancel_order")


def test_usd_m_private_reader_is_signed_get_only() -> None:
    transport = RecordingTransport()
    requests = SignedUsdMReadOnlyRequestFactory(
        PrivateCredentials("public-key", "private-secret"),
        clock_ms=lambda: 1_700_000_000_000,
    )
    reader = BinanceUsdMPrivateAccountReader(requests, transport)
    assert reader.account() == {"ok": True}
    assert reader.positions("hotusdt") == {"ok": True}
    assert reader.open_orders("hotusdt") == {"ok": True}
    assert reader.all_orders("hotusdt") == {"ok": True}
    assert reader.trades("hotusdt") == {"ok": True}
    assert reader.income("hotusdt") == {"ok": True}
    assert reader.algo_open_orders("hotusdt") == {"ok": True}
    assert urlparse(transport.requests[6].full_url).path == "/fapi/v1/openAlgoOrders"
    assert reader.leverage_bracket("hotusdt") == {"ok": True}
    assert reader.position_mode() == {"ok": True}
    assert reader.multi_assets_mode() == {"ok": True}
    assert all(request.method == "GET" for request in transport.requests)
    assert all("fapi.binance.com" in request.full_url for request in transport.requests)
    assert not hasattr(reader, "create_order")
    with pytest.raises(ValueError, match="read-only"):
        requests.build("/fapi/v1/order")
    with pytest.raises(ValueError, match="read-only"):
        requests.build("/fapi/v1/algo/openOrders")


def test_missing_credentials_and_invalid_symbol_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    with pytest.raises(ValueError, match="credentials are required"):
        PrivateCredentials.from_environment()
    with pytest.raises(ValueError, match="ASCII alphanumeric"):
        BinancePrivateAccountReader(factory(), RecordingTransport()).open_orders(
            "HOT/USDT"
        )


def test_private_transport_decodes_bounded_json_without_network() -> None:
    calls: list[str] = []

    def loader(request: Request, timeout: float, limit: int) -> bytes:
        calls.append(request.full_url)
        assert timeout == 2.0
        assert limit == 2048
        return b'{"canTrade":true}'

    transport = UrllibPrivateJsonTransport(
        timeout_seconds=2.0,
        max_response_bytes=2048,
        response_loader=loader,
    )
    assert transport.get_json(factory().build("/api/v3/account")) == {"canTrade": True}
    assert len(calls) == 1


def test_private_transport_retries_and_sanitizes_failures() -> None:
    attempts = 0

    def failing_loader(_request: Request, _timeout: float, _limit: int) -> bytes:
        nonlocal attempts
        attempts += 1
        raise URLError("private-secret must not escape")

    transport = UrllibPrivateJsonTransport(
        max_attempts=2,
        backoff_seconds=0,
        response_loader=failing_loader,
    )
    with pytest.raises(ExchangeTransportError) as captured:
        transport.get_json(factory().build("/api/v3/account"))
    assert attempts == 2
    assert "private-secret" not in str(captured.value)


def test_private_transport_rejects_invalid_json_oversize_and_forged_request() -> None:
    invalid = UrllibPrivateJsonTransport(response_loader=lambda _r, _t, _l: b"bad")
    with pytest.raises(ExchangePayloadError, match="invalid private"):
        invalid.get_json(factory().build("/api/v3/account"))
    oversized = UrllibPrivateJsonTransport(
        max_response_bytes=1024,
        response_loader=lambda _r, _t, _l: b"x" * 1025,
    )
    with pytest.raises(ExchangePayloadError, match="too large"):
        oversized.get_json(factory().build("/api/v3/account"))
    forged = Request("https://evil.invalid/api/v3/account", method="GET")
    with pytest.raises(ValueError, match="official HTTPS host"):
        invalid.get_json(forged)

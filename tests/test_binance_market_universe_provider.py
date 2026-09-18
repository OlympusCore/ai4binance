from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from email.message import Message
from typing import Any, cast
from urllib.error import HTTPError, URLError

import pytest

from ai4binance.application.orchestration import UniverseScanCycle
from ai4binance.cli.status import (
    build_market_universe_provider,
    build_universe_scan_cycle,
    scan_command_payload,
)
from ai4binance.config import Settings
from ai4binance.core.errors import (
    ExchangeError as CanonicalExchangeError,
)
from ai4binance.core.errors import (
    ExchangeHttpError as CanonicalExchangeHttpError,
)
from ai4binance.core.errors import (
    ExchangePayloadError as CanonicalExchangePayloadError,
)
from ai4binance.core.errors import ExchangeRateLimitError
from ai4binance.core.errors import (
    ExchangeTransportError as CanonicalExchangeTransportError,
)
from ai4binance.core.exchange_errors import (
    ExchangeError as CoreLegacyExchangeError,
)
from ai4binance.core.exchange_errors import (
    ExchangeHttpError as CoreLegacyExchangeHttpError,
)
from ai4binance.core.exchange_errors import (
    ExchangePayloadError as CoreLegacyExchangePayloadError,
)
from ai4binance.core.exchange_errors import (
    ExchangeTransportError as CoreLegacyExchangeTransportError,
)
from ai4binance.data.acquisition import LocalMarketSnapshotTransport
from ai4binance.domain.universe import (
    UniverseMarket as CanonicalUniverseMarket,
)
from ai4binance.domain.universe import (
    UniverseSymbol as CanonicalUniverseSymbol,
)
from ai4binance.exchange.errors import (
    ExchangeError,
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeTransportError,
)
from ai4binance.integrations.binance import (
    BinanceMarketUniverseProvider,
    BinanceUniverseSnapshot,
    ReadOnlyBinanceJsonTransport,
)
from ai4binance.opportunity_scanner import build_opportunity_scan_report
from ai4binance.universe import UniverseMarket, UniverseSymbol


def test_legacy_universe_and_exchange_imports_reexport_canonical_contracts() -> None:
    assert ExchangeError is CanonicalExchangeError
    assert ExchangeHttpError is CanonicalExchangeHttpError
    assert ExchangePayloadError is CanonicalExchangePayloadError
    assert ExchangeTransportError is CanonicalExchangeTransportError
    assert CoreLegacyExchangeError is CanonicalExchangeError
    assert CoreLegacyExchangeHttpError is CanonicalExchangeHttpError
    assert CoreLegacyExchangePayloadError is CanonicalExchangePayloadError
    assert CoreLegacyExchangeTransportError is CanonicalExchangeTransportError
    assert CanonicalExchangeError.__module__ == "ai4binance.core.errors.exchange"
    assert issubclass(CanonicalExchangeTransportError, CanonicalExchangeError)
    assert issubclass(CanonicalExchangeHttpError, CanonicalExchangeError)
    assert issubclass(CanonicalExchangePayloadError, CanonicalExchangeError)
    assert UniverseMarket is CanonicalUniverseMarket
    assert UniverseSymbol is CanonicalUniverseSymbol


def test_binance_market_universe_provider_builds_real_public_scan_inputs() -> None:
    provider = BinanceMarketUniverseProvider(
        spot_transport=_SpotTransport(),
        futures_transport=_FuturesTransport(),
        max_symbols_per_market=5,
    )

    snapshot = provider.snapshot(("SOLUSDT", "BTCUSDT"))

    assert snapshot.blockers == ()
    assert snapshot.spot_symbols[0].symbol == "SOLUSDT"
    assert snapshot.spot_symbols[0].quote_volume_24h_usdt == Decimal("5000000")
    assert snapshot.spot_symbols[0].spread_bps < Decimal("50")
    assert snapshot.spot_symbols[0].depth_0_5_pct_usdt > Decimal("25000")
    assert snapshot.spot_symbols[0].data_quality_ok is True
    assert snapshot.futures_symbols[0].symbol == "BTCUSDT"
    assert snapshot.futures_symbols[0].open_interest_usdt == Decimal("32500000")
    assert snapshot.futures_symbols[0].funding_rate == Decimal("0.0001")
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_binance_market_universe_provider_fails_closed_without_public_data() -> None:
    provider = BinanceMarketUniverseProvider(
        spot_transport=_BrokenTransport(),
        futures_transport=_BrokenTransport(),
    )

    snapshot = provider.snapshot(("SOLUSDT",))

    assert snapshot.spot_symbols == ()
    assert snapshot.futures_symbols == ()
    assert snapshot.blockers == ("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",)
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_binance_market_universe_provider_reports_empty_public_universe() -> None:
    provider = BinanceMarketUniverseProvider(
        spot_transport=_EmptySpotTransport(),
        futures_transport=_EmptyFuturesTransport(),
    )

    snapshot = provider.snapshot((" btcusdt ", "BTCUSDT", " "))

    assert snapshot.spot_symbols == ()
    assert snapshot.futures_symbols == ()
    assert snapshot.blockers == ("PUBLIC_MARKET_UNIVERSE_EMPTY",)
    assert snapshot.execution_allowed is False


def test_snapshot_excludes_non_active_spot_and_futures_contracts() -> None:
    spot = _RecordingTransport(
        {
            "/api/v3/exchangeInfo": {
                "symbols": [
                    _spot_listing("SOLUSDT", "SOL"),
                    _spot_listing("OLDUSDT", "OLD", status="BREAK"),
                    {
                        **_spot_listing("NOSTATUSUSDT", "NOSTATUS"),
                        "isSpotTradingAllowed": False,
                    },
                ]
            },
            "/api/v3/ticker/24hr": [{"symbol": "SOLUSDT", "quoteVolume": "1"}],
            "/api/v3/ticker/bookTicker": [
                {
                    "symbol": "SOLUSDT",
                    "bidPrice": "100",
                    "askPrice": "101",
                    "bidQty": "1",
                    "askQty": "1",
                }
            ],
        }
    )
    futures = _RecordingTransport(
        {
            "/fapi/v1/exchangeInfo": {
                "symbols": [
                    _futures_listing("SOLUSDT", "SOL"),
                    {**_futures_listing("OLDUSDT", "OLD"), "status": "BREAK"},
                    _futures_listing(
                        "SOLUSDT_260625", "SOL", contract="CURRENT_QUARTER"
                    ),
                ]
            },
            "/fapi/v1/ticker/24hr": [
                {"symbol": "SOLUSDT", "quoteVolume": "1", "lastPrice": "100"}
            ],
            "/fapi/v1/ticker/bookTicker": [
                {
                    "symbol": "SOLUSDT",
                    "bidPrice": "100",
                    "askPrice": "101",
                    "bidQty": "1",
                    "askQty": "1",
                }
            ],
            "/fapi/v1/premiumIndex": [{"symbol": "SOLUSDT", "lastFundingRate": "0"}],
            "/fapi/v1/openInterest": {"symbol": "SOLUSDT", "openInterest": "1"},
        }
    )

    snapshot = BinanceMarketUniverseProvider(spot, futures).snapshot()

    assert [item.symbol for item in snapshot.spot_symbols] == ["SOLUSDT"]
    assert [item.symbol for item in snapshot.futures_symbols] == ["SOLUSDT"]


def test_build_market_universe_provider_is_read_only() -> None:
    settings = Settings(
        public_api_base_url="https://data-api.binance.vision/",
        request_timeout_seconds=1.5,
        request_max_attempts=2,
        request_backoff_seconds=0.1,
        preferred_quote_assets=("usdt",),
    )

    provider = build_market_universe_provider(settings)

    assert provider.quote_assets == ("USDT",)
    assert isinstance(provider.spot_transport, LocalMarketSnapshotTransport)
    assert isinstance(provider.futures_transport, LocalMarketSnapshotTransport)
    assert provider.spot_transport.directory == (
        settings.dataset_directory / "spot" / "metadata"
    )
    assert provider.futures_transport.directory == (
        settings.dataset_directory / "usd_m_futures" / "metadata"
    )


def test_scan_command_payload_uses_universe_cycle_without_placeholder_metrics() -> None:
    cycle = UniverseScanCycle(
        provider=_StaticProvider(),
        scanner=build_opportunity_scan_report,
        priority_symbols=("SOLUSDT",),
    )

    payload = scan_command_payload("scan-spot", universe_scan_cycle=cycle)
    ranked_candidates = cast(
        Sequence[Mapping[str, object]],
        payload["ranked_candidates"],
    )
    blockers = cast(Sequence[str], payload["blockers"])
    first = ranked_candidates[0]

    assert payload["status"] == "READY"
    assert "SCANNER_INPUT_UNAVAILABLE" not in blockers
    assert first["symbol"] == "SOLUSDT"
    assert first["liquidity_score"] == Decimal("100")
    assert first["spread_score"] != Decimal("0")
    assert first["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_build_universe_scan_cycle_assembles_cli_provider_and_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        symbol="BTCUSDT",
        default_watch_symbol="ETHUSDT",
        fixed_symbols=("SOLUSDT",),
        priority_watchlist=("ADAUSDT",),
    )
    provider = _StaticProvider()

    monkeypatch.setattr(
        "ai4binance.cli.status.build_market_universe_provider",
        lambda configured: provider if configured is settings else None,
    )

    cycle = build_universe_scan_cycle(settings)

    assert cycle.provider is provider
    assert cycle.scanner is build_opportunity_scan_report
    assert cycle.priority_symbols == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "ADAUSDT",
    )


def test_binance_market_universe_provider_handles_sparse_public_payloads() -> None:
    provider = BinanceMarketUniverseProvider(
        spot_transport=_SparseSpotTransport(),
        futures_transport=_SparseFuturesTransport(),
        quote_assets=("USDT", "USDC"),
        max_symbols_per_market=3,
    )

    snapshot = provider.snapshot(("DOGEUSDC", "ETHUSDT"))

    assert snapshot.blockers == ()
    assert [item.symbol for item in snapshot.spot_symbols] == ["DOGEUSDC", "ADAUSDT"]
    assert snapshot.spot_symbols[0].data_quality_ok is True
    assert snapshot.spot_symbols[0].spread_bps == Decimal("1000000")
    assert snapshot.spot_symbols[0].min_notional_usdt == Decimal("0")
    assert snapshot.spot_symbols[1].data_quality_ok is False
    assert snapshot.futures_symbols[0].symbol == "ETHUSDT"
    assert snapshot.futures_symbols[0].open_interest_usdt == Decimal("0")
    assert snapshot.futures_symbols[0].data_quality_ok is False
    assert snapshot.execution_allowed is False


def test_market_universe_provider_handles_open_interest_failure_and_blanks() -> None:
    provider = BinanceMarketUniverseProvider(
        spot_transport=_BlankRecordSpotTransport(),
        futures_transport=_OpenInterestFailureFuturesTransport(),
        max_symbols_per_market=5,
    )

    snapshot = provider.snapshot(("BTCUSDT",))

    assert snapshot.blockers == ()
    assert snapshot.spot_symbols[0].symbol == "BTCUSDT"
    assert snapshot.spot_symbols[0].data_quality_ok is True
    assert snapshot.futures_symbols[0].symbol == "BTCUSDT"
    assert snapshot.futures_symbols[0].open_interest_usdt == Decimal("0")
    assert snapshot.futures_symbols[0].funding_rate == Decimal("0")
    assert snapshot.futures_symbols[0].data_quality_ok is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "malformed_case",
    ["mapping", "sequence"],
)
def test_binance_market_universe_provider_fails_closed_for_malformed_public_payloads(
    malformed_case: str,
) -> None:
    spot_transport: object
    if malformed_case == "mapping":
        spot_transport = _MalformedMappingSpotTransport()
    else:
        spot_transport = _MalformedSequenceSpotTransport()

    provider = BinanceMarketUniverseProvider(
        spot_transport=cast(Any, spot_transport),
        futures_transport=_EmptyFuturesTransport(),
    )

    snapshot = provider.snapshot()

    assert snapshot.spot_symbols == ()
    assert snapshot.futures_symbols == ()
    assert snapshot.blockers == ("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",)
    assert snapshot.execution_allowed is False


def test_binance_universe_snapshot_never_grants_execution() -> None:
    with pytest.raises(ValueError, match="cannot grant execution"):
        BinanceUniverseSnapshot((), (), execution_allowed=True)
    with pytest.raises(ValueError, match="cannot contain blanks"):
        BinanceUniverseSnapshot((), (), blockers=(" ",))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"base_url": "http://api.binance.com"}, "credential-free HTTPS"),
        ({"base_url": "https://user@example.com"}, "credential-free HTTPS"),
        ({"allowed_prefixes": ()}, "requires allowed path prefixes"),
        ({"timeout_seconds": 0}, "timeout_seconds must be positive"),
        ({"max_attempts": 0}, "max_attempts must be between"),
        ({"backoff_seconds": -1}, "backoff values must be non-negative"),
        ({"max_backoff_seconds": 0}, "backoff values must be non-negative"),
        ({"max_response_bytes": 100}, "max_response_bytes is too small"),
    ],
)
def test_read_only_binance_transport_rejects_unsafe_configuration(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    payload: dict[str, Any] = {
        "base_url": "https://api.binance.com/",
        "allowed_prefixes": ("/api/v3/",),
    }
    payload.update(kwargs)

    with pytest.raises(ValueError, match=message):
        ReadOnlyBinanceJsonTransport(**payload)


def test_read_only_binance_transport_bounds_paths_and_retry_delay() -> None:
    transport = ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com/",
        allowed_prefixes=("/api/v3/",),
        backoff_seconds=0.5,
        max_backoff_seconds=2.0,
    )

    assert transport.base_url == "https://api.binance.com"
    assert transport.allowed_prefixes == ("/api/v3/",)
    assert transport._retry_delay(1, "3.5") == 2.0
    assert transport._retry_delay(3, "not-a-number") == 2.0
    assert transport._retry_delay(1, None) == 0.5
    with pytest.raises(ValueError, match="outside the configured"):
        transport.get_json("/fapi/v1/exchangeInfo")


def test_read_only_binance_transport_retries_read_only_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_request_once(
        self: ReadOnlyBinanceJsonTransport,
        url: str,
        path: str,
    ) -> object:
        del self
        calls.append(url)
        if len(calls) == 1:
            raise URLError("temporary")
        assert path == "/api/v3/exchangeInfo"
        return {"ok": True}

    monkeypatch.setattr(
        ReadOnlyBinanceJsonTransport,
        "_request_once",
        fake_request_once,
    )
    transport = ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        max_attempts=2,
        sleeper=sleeps.append,
    )

    assert transport.get_json("/api/v3/exchangeInfo", {"symbol": "BTCUSDT"}) == {
        "ok": True
    }
    assert calls == [
        "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT",
        "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT",
    ]
    assert sleeps == [0.25]


def test_read_only_binance_transport_never_retries_rate_limit_and_blocks_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    headers = Message()
    headers["Retry-After"] = "1.5"

    def fake_request_once(
        self: ReadOnlyBinanceJsonTransport,
        url: str,
        path: str,
    ) -> object:
        del self, url, path
        calls.append("attempt")
        if len(calls) == 1:
            raise HTTPError(
                "https://api.binance.com/api/v3/time",
                429,
                "rate",
                headers,
                None,
            )
        return {"serverTime": 1}

    monkeypatch.setattr(
        ReadOnlyBinanceJsonTransport,
        "_request_once",
        fake_request_once,
    )
    transport = ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        max_attempts=2,
        sleeper=sleeps.append,
    )

    with pytest.raises(ExchangeRateLimitError) as raised:
        transport.get_json("/api/v3/time")
    assert raised.value.status_code == 429
    assert raised.value.retry_after_seconds == 1.5
    assert calls == ["attempt"]
    assert sleeps == []

    blocked = ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        max_attempts=1,
    )

    def fail_once(
        self: ReadOnlyBinanceJsonTransport,
        url: str,
        path: str,
    ) -> object:
        del self, url, path
        raise HTTPError(
            "https://api.binance.com/api/v3/time",
            500,
            "down",
            headers,
            None,
        )

    monkeypatch.setattr(
        ReadOnlyBinanceJsonTransport,
        "_request_once",
        fail_once,
    )
    with pytest.raises(ExchangeHttpError, match="public Binance HTTP 500"):
        blocked.get_json("/api/v3/time")


def test_read_only_binance_transport_blocks_final_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_once(
        self: ReadOnlyBinanceJsonTransport,
        url: str,
        path: str,
    ) -> object:
        del self, url, path
        raise URLError("offline")

    monkeypatch.setattr(
        ReadOnlyBinanceJsonTransport,
        "_request_once",
        fail_once,
    )
    transport = ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        max_attempts=1,
    )

    with pytest.raises(ExchangeTransportError, match="public Binance request failed"):
        transport.get_json("/api/v3/time")


def test_read_only_binance_transport_rejects_large_and_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        _UrlOpenResponse(b"x" * 1025),
        _UrlOpenResponse(b"{not-json"),
        _UrlOpenResponse(b'{"ok": true}'),
    ]

    def fake_urlopen(request: object, timeout: float) -> _UrlOpenResponse:
        del request
        assert timeout == 10.0
        return responses.pop(0)

    monkeypatch.setattr(
        "ai4binance.integrations.binance.market_universe_provider.urlopen",
        fake_urlopen,
    )
    transport = ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        max_response_bytes=1024,
    )

    with pytest.raises(ExchangePayloadError, match="payload too large"):
        transport._request_once("https://api.binance.com/api/v3/time", "/api/v3/time")
    with pytest.raises(ExchangePayloadError, match="invalid public Binance JSON"):
        transport._request_once("https://api.binance.com/api/v3/time", "/api/v3/time")
    assert transport._request_once(
        "https://api.binance.com/api/v3/time", "/api/v3/time"
    ) == {"ok": True}


class _SpotTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "SOLUSDT",
                        "status": "TRADING",
                        "baseAsset": "SOL",
                        "quoteAsset": "USDT",
                        "filters": [{"filterType": "MIN_NOTIONAL", "minNotional": "5"}],
                    }
                ]
            }
        if path == "/api/v3/ticker/24hr":
            return [{"symbol": "SOLUSDT", "quoteVolume": "5000000"}]
        if path == "/api/v3/ticker/bookTicker":
            return [
                {
                    "symbol": "SOLUSDT",
                    "bidPrice": "100",
                    "askPrice": "100.1",
                    "bidQty": "400",
                    "askQty": "400",
                }
            ]
        raise AssertionError(path)


class _FuturesTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        if path == "/fapi/v1/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "marginAsset": "USDT",
                    }
                ]
            }
        if path == "/fapi/v1/ticker/24hr":
            return [
                {"symbol": "BTCUSDT", "quoteVolume": "7000000", "lastPrice": "65000"}
            ]
        if path == "/fapi/v1/ticker/bookTicker":
            return [
                {
                    "symbol": "BTCUSDT",
                    "bidPrice": "65000",
                    "askPrice": "65010",
                    "bidQty": "1",
                    "askQty": "1",
                }
            ]
        if path == "/fapi/v1/premiumIndex":
            return [{"symbol": "BTCUSDT", "lastFundingRate": "0.0001"}]
        if path == "/fapi/v1/openInterest":
            assert params == {"symbol": "BTCUSDT"}
            return {"symbol": "BTCUSDT", "openInterest": "500"}
        raise AssertionError(path)


class _BrokenTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del path, params
        raise ExchangeTransportError("offline")


class _EmptySpotTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/api/v3/exchangeInfo":
            return {"symbols": []}
        if path in {"/api/v3/ticker/24hr", "/api/v3/ticker/bookTicker"}:
            return []
        raise AssertionError(path)


class _EmptyFuturesTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/fapi/v1/exchangeInfo":
            return {"symbols": []}
        if path in {
            "/fapi/v1/ticker/24hr",
            "/fapi/v1/ticker/bookTicker",
            "/fapi/v1/premiumIndex",
        }:
            return []
        raise AssertionError(path)


class _SparseSpotTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "ADAUSDT",
                        "status": "TRADING",
                        "baseAsset": "ADA",
                        "quoteAsset": "USDT",
                        "filters": [{"filterType": "PRICE_FILTER"}],
                    },
                    {
                        "symbol": "ETHBTC",
                        "status": "TRADING",
                        "baseAsset": "ETH",
                        "quoteAsset": "BTC",
                        "filters": [],
                    },
                    {
                        "symbol": "DOGEUSDC",
                        "status": "TRADING",
                        "baseAsset": "DOGE",
                        "quoteAsset": "USDC",
                        "filters": [{"filterType": "NOTIONAL", "minNotional": "-1"}],
                    },
                ]
            }
        if path == "/api/v3/ticker/24hr":
            return [{"symbol": "DOGEUSDC", "quoteVolume": "invalid"}]
        if path == "/api/v3/ticker/bookTicker":
            return [
                {
                    "symbol": "DOGEUSDC",
                    "bidPrice": "10",
                    "askPrice": "9",
                    "bidQty": "2",
                    "askQty": "3",
                }
            ]
        raise AssertionError(path)


class _SparseFuturesTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/fapi/v1/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "ETHUSDT",
                        "status": "TRADING",
                        "baseAsset": "ETH",
                        "quoteAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "marginAsset": "USDT",
                    },
                    {
                        "symbol": "XRPBTC",
                        "status": "TRADING",
                        "baseAsset": "XRP",
                        "quoteAsset": "BTC",
                    },
                ]
            }
        if path == "/fapi/v1/ticker/24hr":
            return [{"symbol": "ETHUSDT", "quoteVolume": "12", "lastPrice": "0"}]
        if path == "/fapi/v1/ticker/bookTicker":
            return [{"symbol": "ETHUSDT", "bidPrice": None, "askPrice": True}]
        if path == "/fapi/v1/premiumIndex":
            return [{"symbol": "ETHUSDT", "lastFundingRate": "NaN"}]
        if path == "/fapi/v1/openInterest":
            raise AssertionError("open interest is skipped when last price is zero")
        raise AssertionError(path)


class _BlankRecordSpotTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "filters": [{"filterType": "MIN_NOTIONAL", "minNotional": "5"}],
                    }
                ]
            }
        if path == "/api/v3/ticker/24hr":
            return [
                {"symbol": "", "quoteVolume": "999"},
                {"symbol": "BTCUSDT", "quoteVolume": "1000000"},
            ]
        if path == "/api/v3/ticker/bookTicker":
            return [
                {"symbol": "", "bidPrice": "1", "askPrice": "1", "bidQty": "1"},
                {
                    "symbol": "BTCUSDT",
                    "bidPrice": "100",
                    "askPrice": "100.2",
                    "bidQty": "10",
                    "askQty": "9",
                },
            ]
        raise AssertionError(path)


class _OpenInterestFailureFuturesTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/fapi/v1/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "marginAsset": "USDT",
                    }
                ]
            }
        if path == "/fapi/v1/ticker/24hr":
            return [{"symbol": "BTCUSDT", "quoteVolume": "1000000", "lastPrice": "100"}]
        if path == "/fapi/v1/ticker/bookTicker":
            return [
                {
                    "symbol": "BTCUSDT",
                    "bidPrice": "100",
                    "askPrice": "100.1",
                    "bidQty": "3",
                    "askQty": "3",
                }
            ]
        if path == "/fapi/v1/premiumIndex":
            return [{"symbol": "BTCUSDT", "lastFundingRate": True}]
        if path == "/fapi/v1/openInterest":
            raise ExchangeTransportError("open interest offline")
        raise AssertionError(path)


class _MalformedMappingSpotTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del path, params
        return []


class _MalformedSequenceSpotTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del params
        if path == "/api/v3/exchangeInfo":
            return {"symbols": {}}
        return []


class _StaticProvider:
    def snapshot(self, priority_symbols: object = ()) -> BinanceUniverseSnapshot:
        del priority_symbols
        return BinanceUniverseSnapshot(
            spot_symbols=(
                UniverseSymbol(
                    symbol="SOLUSDT",
                    market=UniverseMarket.SPOT,
                    base_asset="SOL",
                    quote_asset="USDT",
                    status="TRADING",
                    min_notional_usdt=Decimal("5"),
                    quote_volume_24h_usdt=Decimal("5000000"),
                    spread_bps=Decimal("8"),
                    depth_0_5_pct_usdt=Decimal("120000"),
                    data_quality_ok=True,
                ),
            ),
            futures_symbols=(),
        )


class _UrlOpenResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _UrlOpenResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        del size
        return self.payload


def test_eligible_market_snapshot_uses_exchange_info_only_and_excludes_assets() -> None:
    spot = _RecordingTransport(
        {
            "/api/v3/exchangeInfo": {
                "symbols": [
                    _spot_listing("BTCUSDT", "BTC"),
                    _spot_listing("USDCUSDT", "USDC"),
                    _spot_listing("USD1USDT", "USD1"),
                    _spot_listing("USDEUSDT", "USDE"),
                    _spot_listing("UUSDT", "U"),
                    _spot_listing("WBTCUSDT", "WBTC"),
                    _spot_listing("BTCUPUSDT", "BTCUP"),
                    _spot_listing("WOOUSDT", "WOO"),
                    _spot_listing("JUPUSDT", "JUP"),
                    _spot_listing("SYRUPUSDT", "SYRUP"),
                    _spot_listing("OLDUSDT", "OLD", status="BREAK"),
                ]
            }
        }
    )
    futures = _RecordingTransport(
        {
            "/fapi/v1/exchangeInfo": {
                "symbols": [
                    _futures_listing("BTCUSDT", "BTC"),
                    _futures_listing(
                        "ETHUSDT_260925", "ETH", contract="CURRENT_QUARTER"
                    ),
                    _futures_listing("USDCUSDT", "USDC"),
                    _futures_listing("WOOUSDT", "WOO"),
                    _futures_listing("JUPUSDT", "JUP"),
                    _futures_listing("SYRUPUSDT", "SYRUP"),
                ]
            }
        }
    )

    snapshot = BinanceMarketUniverseProvider(spot, futures).eligible_market_snapshot()

    assert snapshot.spot_symbols == ("BTCUSDT", "JUPUSDT", "SYRUPUSDT", "WOOUSDT")
    assert snapshot.futures_symbols == (
        "BTCUSDT",
        "JUPUSDT",
        "SYRUPUSDT",
        "WOOUSDT",
    )
    exclusions = dict(snapshot.excluded_assets)
    assert exclusions["USDC"] == ("STABLECOIN_BASE_ASSET",)
    assert exclusions["USD1"] == ("STABLECOIN_BASE_ASSET",)
    assert exclusions["USDE"] == ("STABLECOIN_BASE_ASSET",)
    assert exclusions["U"] == ("STABLECOIN_BASE_ASSET",)
    assert exclusions["WBTC"] == ("WRAPPED_ASSET",)
    assert exclusions["BTCUP"] == ("LEVERAGED_TOKEN",)
    assert "WOO" not in exclusions
    assert spot.calls == [
        (
            "/api/v3/exchangeInfo",
            {"symbolStatus": "TRADING", "showPermissionSets": "false"},
        )
    ]
    assert futures.calls == [("/fapi/v1/exchangeInfo", None)]
    assert snapshot.execution_allowed is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_eligible_market_snapshot_fails_closed_when_exchange_info_is_unavailable() -> (
    None
):
    snapshot = BinanceMarketUniverseProvider(
        _RaisingTransport(), _RaisingTransport()
    ).eligible_market_snapshot()

    assert snapshot.spot_symbols == ()
    assert snapshot.futures_symbols == ()
    assert snapshot.blockers == ("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",)


def test_eligible_market_snapshot_removes_configured_futures_symbol() -> None:
    spot = _RecordingTransport(
        {"/api/v3/exchangeInfo": {"symbols": [_spot_listing("HOTUSDT", "HOT")]}}
    )
    futures = _RecordingTransport(
        {"/fapi/v1/exchangeInfo": {"symbols": [_futures_listing("HOTUSDT", "HOT")]}}
    )

    snapshot = BinanceMarketUniverseProvider(
        spot, futures, futures_symbol_exclusions=("HOTUSDT",)
    ).eligible_market_snapshot()

    assert snapshot.spot_symbols == ("HOTUSDT",)
    assert snapshot.futures_symbols == ()


def test_top_volume_eligible_market_snapshot_bounds_each_market_and_fails_closed() -> (
    None
):
    spot = _RecordingTransport(
        {
            "/api/v3/exchangeInfo": {
                "symbols": [
                    _spot_listing("BTCUSDT", "BTC"),
                    _spot_listing("ETHUSDT", "ETH"),
                    _spot_listing("SOLUSDT", "SOL"),
                ]
            },
            "/api/v3/ticker/24hr": [
                {"symbol": "BTCUSDT", "quoteVolume": "100"},
                {"symbol": "ETHUSDT", "quoteVolume": "300"},
                {"symbol": "SOLUSDT", "quoteVolume": "200"},
            ],
        }
    )
    futures = _RecordingTransport(
        {
            "/fapi/v1/exchangeInfo": {
                "symbols": [
                    _futures_listing("BTCUSDT", "BTC"),
                    _futures_listing("ETHUSDT", "ETH"),
                    _futures_listing("SOLUSDT", "SOL"),
                ]
            },
            "/fapi/v1/ticker/24hr": [
                {"symbol": "BTCUSDT", "quoteVolume": "400"},
                {"symbol": "ETHUSDT", "quoteVolume": "200"},
                {"symbol": "SOLUSDT", "quoteVolume": "300"},
            ],
        }
    )

    snapshot = BinanceMarketUniverseProvider(
        spot, futures
    ).top_volume_eligible_market_snapshot(max_symbols_per_market=2)

    assert snapshot.spot_symbols == ("ETHUSDT", "SOLUSDT")
    assert snapshot.futures_symbols == ("BTCUSDT", "SOLUSDT")
    assert snapshot.source == "BINANCE_PUBLIC_24H_QUOTE_VOLUME"
    assert snapshot.execution_allowed is False
    assert snapshot.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert spot.calls[-1] == ("/api/v3/ticker/24hr", None)
    assert futures.calls[-1] == ("/fapi/v1/ticker/24hr", None)


class _RecordingTransport:
    def __init__(self, responses: Mapping[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Mapping[str, str | int] | None]] = []

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        self.calls.append((path, params))
        return self.responses[path]


class _RaisingTransport:
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        del path, params
        raise ExchangeTransportError("offline")


def _spot_listing(
    symbol: str,
    base_asset: str,
    *,
    status: str = "TRADING",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "baseAsset": base_asset,
        "quoteAsset": "USDT",
        "status": status,
        "permissions": ["SPOT"],
        "isSpotTradingAllowed": True,
        "filters": [],
    }


def _futures_listing(
    symbol: str,
    base_asset: str,
    *,
    contract: str = "PERPETUAL",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "baseAsset": base_asset,
        "quoteAsset": "USDT",
        "marginAsset": "USDT",
        "status": "TRADING",
        "contractType": contract,
    }

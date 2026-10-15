"""Test-only transport and universe inputs never contact an external provider."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.error import URLError

import pytest

from ai4binance.core.errors import ExchangePayloadError, ExchangeTransportError
from ai4binance.integrations import research_market_universe as research
from ai4binance.integrations.binance import market_universe_provider as binance
from tests.test_research_market_universe import (
    NOW,
    _MarketCapTransport,
    _metadata,
    _wallet_record,
    _write_wallet,
)


class _Response(BytesIO):
    headers: ClassVar[dict[str, str]] = {"X-Test-Only": "bounded-response"}


@pytest.mark.parametrize(
    "changes",
    [
        {"spot_symbols": ("ETHUSDT", "BTCUSDT")},
        {"spot_symbols": ("BTCUSDT", "BTCUSDT")},
        {"spot_symbols": ("btcUSDT",)},
        {"excluded_assets": (("BTC", ()),)},
        {"excluded_assets": (("BTC", (" ",)),)},
        {"blockers": (" ",)},
        {"selected_assets": ("BTC", "BTC")},
        {"selected_assets": ("btc",)},
        {"manual_selection_sha256": "x" * 64},
        {"manual_selection_sha256": "a"},
        {"execution_allowed": True},
        {"live_eligibility_status": "READY"},
        {"coin_m_contracts": (("BTCUSD_PERP", "ETHUSD", "PERPETUAL"),)},
        {"coin_m_contracts": (("BTCUSD_BAD", "BTCUSD", "PERPETUAL"),)},
        {"coin_m_contracts": (("BTCUSD_PERP", "BTCUSD", "UNKNOWN"),)},
        {
            "coin_m_contracts": (
                ("BTCUSD_PERP", "BTCUSD", "PERPETUAL"),
                ("BTCUSD_PERP", "BTCUSD", "PERPETUAL"),
            )
        },
    ],
)
def test_eligible_snapshot_rejects_ambiguous_identity_and_execution_authority(
    changes: dict[str, Any],
) -> None:
    kwargs = {"spot_symbols": (), "futures_symbols": (), **changes}
    with pytest.raises(ValueError, match=r"invalid|unique|blanks|execution"):
        binance.BinanceEligibleMarketSnapshot(**kwargs)


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": "https://not-allowed.test"},
        {"timeout_seconds": 0},
        {"max_attempts": 0},
        {"max_response_bytes": 100},
    ],
)
def test_market_cap_transport_rejects_invalid_boundary(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"allowlist|bounds|bound"):
        research.ReadOnlyCoinGeckoJsonTransport(**changes)


@pytest.mark.parametrize(
    "payload",
    [b"[]", b"\xff", b"invalid-json", b"{}", b"x" * 1025],
    ids=["empty-list", "invalid-utf8", "invalid-json", "wrong-shape", "oversize"],
)
def test_market_cap_http_response_is_bounded_and_typed(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    monkeypatch.setattr(research, "urlopen", lambda *a, **k: _Response(payload))
    transport = research.ReadOnlyCoinGeckoJsonTransport(max_response_bytes=1024)
    if payload == b"[]":
        assert transport.get_json("/api/v3/coins/markets") == []
    else:
        with pytest.raises(ExchangePayloadError):
            transport.get_json("/api/v3/coins/markets")


def test_market_cap_retry_exhaustion_and_path_rejection_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def unavailable(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise URLError("test-only provider outage")

    monkeypatch.setattr(research, "urlopen", unavailable)
    transport = research.ReadOnlyCoinGeckoJsonTransport(max_attempts=2)
    with pytest.raises(ValueError, match="boundary"):
        transport.get_json("/api/v3/coins/markets?outside=true")
    assert calls == []
    with pytest.raises(ExchangeTransportError):
        transport.get_json("/api/v3/coins/markets")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "payload",
    [b"[]", b"\xff", b"invalid-json", b"x" * 1025, b""],
    ids=["empty-list", "invalid-utf8", "invalid-json", "oversize", "empty-response"],
)
def test_binance_transport_bound_and_observers_use_actual_received_bytes(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    monkeypatch.setattr(binance, "urlopen", lambda *a, **k: _Response(payload))
    observed: list[tuple[str, bytes]] = []
    headers: list[object] = []
    transport = binance.ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        max_response_bytes=1024,
        response_headers_observer=headers.append,
        response_bytes_observer=lambda url, body: observed.append((url, body)),
    )
    if payload == b"[]":
        assert transport.get_json("/api/v3/exchangeInfo") == []
        assert observed == [("https://api.binance.com/api/v3/exchangeInfo", b"[]")]
    else:
        with pytest.raises(ExchangePayloadError):
            transport.get_json("/api/v3/exchangeInfo")
    assert headers == [{"X-Test-Only": "bounded-response"}]


@pytest.mark.parametrize(
    ("header", "expected"), [(None, None), ("invalid", None), ("-1", None), ("2", 2.0)]
)
def test_binance_retry_header_rejects_invalid_or_negative_delay(
    header: str | None, expected: float | None
) -> None:
    assert binance.ReadOnlyBinanceJsonTransport._parse_retry_after(header) == expected


def test_binance_backoff_remains_bounded_when_provider_delay_is_invalid() -> None:
    transport = binance.ReadOnlyBinanceJsonTransport(
        base_url="https://api.binance.com",
        allowed_prefixes=("/api/v3/",),
        backoff_seconds=1,
        max_backoff_seconds=3,
    )
    assert transport._retry_delay(1, "invalid") == 1
    assert transport._retry_delay(4, "0") == 3
    assert transport._retry_delay(1, "300") == 3
    assert binance._signed_decimal("NaN") == Decimal(0)
    assert binance._signed_decimal("not-a-number") == Decimal(0)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"payload": {}},
        {"payload": {"envelope": {"sync_run_id": None, "event_time": "2026-10-15"}}},
        {
            "payload": {
                "envelope": {"sync_run_id": "test-only", "event_time": "2026-10-15"}
            }
        },
    ],
)
def test_wallet_selection_rejects_unbound_or_unaware_record(
    payload: dict[str, object],
) -> None:
    assert research._wallet_record(json.dumps(payload).encode()) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"execution_allowed": True, "asset": "BTC", "market_value_usdt": "10"},
        {"execution_allowed": False, "asset": "BTC", "market_value_usdt": "invalid"},
    ],
)
def test_wallet_selection_rejects_unsafe_or_invalid_asset_value(
    payload: dict[str, object],
) -> None:
    assert (
        research._eligible_wallet_asset(payload, minimum_value_usdt=Decimal(1)) is None
    )


def test_wallet_universe_cannot_use_missing_empty_or_unaware_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "test-only-wallet.jsonl"
    kwargs: dict[str, Any] = {
        "minimum_value_usdt": Decimal(1),
        "maximum_age": timedelta(hours=1),
    }
    with pytest.raises(ValueError, match="timezone-aware"):
        research.read_wallet_assets_above_value(
            path, observed_at=datetime(2026, 10, 15), **kwargs
        )
    with pytest.raises(OSError, match="unavailable"):
        research.read_wallet_assets_above_value(
            path, observed_at=datetime.now(UTC), **kwargs
        )
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no valid records"):
        research.read_wallet_assets_above_value(
            path, observed_at=datetime.now(UTC), **kwargs
        )
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        research.manual_selection_digest(tmp_path / "missing.yaml")
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        research._manual_selection(tmp_path / "missing.yaml")
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID"):
        research._manual_selection(path)


@pytest.mark.parametrize("rows", [{}, ["test-only-invalid-row"], []])
def test_provider_reports_invalid_or_insufficient_public_universe(
    tmp_path: Path, rows: object
) -> None:
    wallet = tmp_path / "test-only-wallet.jsonl"
    _write_wallet(
        wallet,
        [_wallet_record(asset="BTC", value="2", run_id="TEST_ONLY", observed_at=NOW)],
    )
    provider = research.ResearchMarketUniverseProvider(
        binance=cast(binance.BinanceMarketUniverseProvider, AnyBinance(_metadata())),
        market_cap_transport=_MarketCapTransport(cast(list[dict[str, object]], rows)),
        wallet_balance_path=wallet,
        clock=lambda: NOW,
    )
    result = provider.priority_eligible_market_snapshot()
    assert any(
        code.startswith("PUBLIC_MARKET_CAP_UNIVERSE_") for code in result.blockers
    )
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


class AnyBinance:
    """Only a test transport; it cannot retrieve market or wallet data."""

    quote_assets = ("USDT",)
    spot_transport: Any = None
    futures_transport: Any = None
    coin_m_transport: Any = None

    def __init__(self, metadata: binance.BinanceEligibleMarketSnapshot) -> None:
        self.metadata = metadata

    def eligible_market_snapshot(self) -> binance.BinanceEligibleMarketSnapshot:
        return self.metadata


def test_provider_preserves_metadata_veto_and_rejects_invalid_bounds(
    tmp_path: Path,
) -> None:
    blocked = binance.BinanceEligibleMarketSnapshot(
        (), (), blockers=("TEST_ONLY_METADATA_VETO",)
    )
    kwargs: dict[str, Any] = {
        "binance": AnyBinance(blocked),
        "market_cap_transport": _MarketCapTransport([]),
        "wallet_balance_path": tmp_path / "missing.jsonl",
        "clock": lambda: NOW,
    }
    provider = research.ResearchMarketUniverseProvider(**kwargs)
    assert provider.eligible_market_snapshot() is blocked
    assert provider.priority_eligible_market_snapshot() is blocked
    assert provider.spot_transport is None
    assert provider._preferred_symbol(()) is None
    assert provider._preferred_symbol(("BTCUSDC",)) == "BTCUSDC"
    assert provider._symbols_by_asset(("BTC",)) == {}
    for changes in ({"market_cap_asset_limit": 0}, {"market_cap_page_size": 0}):
        with pytest.raises(ValueError, match=r"limit|page size"):
            research.ResearchMarketUniverseProvider(**{**kwargs, **changes})
    kwargs["clock"] = lambda: NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        research.ResearchMarketUniverseProvider(
            **kwargs
        ).priority_eligible_market_snapshot()

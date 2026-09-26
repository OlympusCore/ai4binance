"""Shared public market snapshot acquisition tests."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.data.acquisition import (
    DataAcquisitionAgent,
    LocalMarketSnapshotTransport,
)
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.exchange.errors import ExchangeTransportError
from ai4binance.exchange.models import BookTicker, MarketKline, SymbolInfo
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified
from ai4binance.schemas import DataQuality

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


def test_local_public_snapshot_reads_and_rejects_stale_data(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "ticker-24hr.json"
    write_json_object_verified(
        snapshot_path,
        {
            "observed_at": NOW.isoformat(),
            "rows": [{"symbol": "HOTUSDT", "lastPrice": "0.0012"}],
        },
        blocker="FIXTURE_WRITE_FAILED",
    )
    transport = LocalMarketSnapshotTransport(tmp_path, clock=lambda: NOW)
    assert transport.get_json("/api/v3/ticker/price", {"symbol": "HOTUSDT"}) == {
        "symbol": "HOTUSDT",
        "price": "0.0012",
    }
    stale = LocalMarketSnapshotTransport(
        tmp_path, clock=lambda: NOW + timedelta(hours=1)
    )
    with pytest.raises(ExchangePayloadError, match="unavailable"):
        stale.get_json("/api/v3/ticker/price", {"symbol": "HOTUSDT"})


def test_local_public_snapshot_can_read_wallet_price_coverage(tmp_path: Path) -> None:
    write_json_object_verified(
        tmp_path / "wallet-price-coverage.json",
        {
            "observed_at": NOW.isoformat(),
            "rows": [{"symbol": "HOTUSDT", "lastPrice": "0.0012"}],
        },
        blocker="FIXTURE_WRITE_FAILED",
    )

    transport = LocalMarketSnapshotTransport(
        tmp_path,
        ticker_snapshot_filename="wallet-price-coverage.json",
        clock=lambda: NOW,
    )

    assert transport.get_json("/api/v3/ticker/price", {"symbol": "HOTUSDT"}) == {
        "symbol": "HOTUSDT",
        "price": "0.0012",
    }
    with pytest.raises(ExchangePayloadError, match="owns"):
        transport.get_json("/api/v3/klines", {"symbol": "HOTUSDT"})


def test_local_transport_serves_futures_gateway_metadata(tmp_path: Path) -> None:
    for filename, rows in (
        (
            "ticker-24hr.json",
            [{"symbol": "BTCUSDT", "lastPrice": "60000"}],
        ),
        (
            "ticker-bookTicker.json",
            [{"symbol": "BTCUSDT", "bidPrice": "59999", "askPrice": "60001"}],
        ),
        (
            "premium-index.json",
            [{"symbol": "BTCUSDT", "lastFundingRate": "0.0001"}],
        ),
    ):
        write_json_object_verified(
            tmp_path / filename,
            {"observed_at": NOW.isoformat(), "rows": rows},
            blocker="FIXTURE_WRITE_FAILED",
        )
    transport = LocalMarketSnapshotTransport(tmp_path, clock=lambda: NOW)

    tickers = transport.get_json("/fapi/v1/ticker/24hr")
    assert isinstance(tickers, list)
    assert isinstance(tickers[0], Mapping)
    assert tickers[0]["symbol"] == "BTCUSDT"
    premium = transport.get_json("/fapi/v1/premiumIndex", {"symbol": "BTCUSDT"})
    assert isinstance(premium, Mapping)
    assert premium["lastFundingRate"] == "0.0001"


def test_local_archive_missing_fails_closed_without_kline_network(
    tmp_path: Path,
) -> None:
    client = FakePublicClient()
    agent = DataAcquisitionAgent(client=client, archive=ParquetOHLCVArchive(tmp_path))
    snapshot = agent.acquire("HOTUSDT", ("1m", "5m"))
    assert snapshot.data_quality == DataQuality.DATA_INVALID
    assert not any(name.startswith("klines") for name, _ in client.calls)


def test_local_snapshot_priority_reuses_canonical_liquidity_order(
    tmp_path: Path,
) -> None:
    from ai4binance.cli.runtime import (
        _canonical_resident_runtime_symbol,
        _virtual_market_priority_symbols,
        _virtual_market_ranked_symbols,
    )
    from ai4binance.config import Settings
    from tests.test_binance_market_universe_provider import _SpotTransport

    settings = Settings(dataset_directory=tmp_path)
    metadata = tmp_path / "spot" / "metadata"
    source = _SpotTransport()
    for endpoint, filename in (
        ("exchangeInfo", "exchange-info.json"),
        ("ticker/24hr", "ticker-24hr.json"),
        ("ticker/bookTicker", "ticker-bookTicker.json"),
    ):
        raw = source.get_json(f"/api/v3/{endpoint}")
        rows = raw["symbols"] if isinstance(raw, dict) else raw
        write_json_object_verified(
            metadata / filename,
            {
                "observed_at": NOW.isoformat(),
                **({"payload": raw} if endpoint == "exchangeInfo" else {"rows": rows}),
            },
            blocker="FIXTURE_WRITE_FAILED",
        )
    assert _virtual_market_priority_symbols(settings, (), ("SOLUSDT",), NOW) == (
        "SOLUSDT",
    )
    assert _virtual_market_priority_symbols(settings, (), ("BTCUSDT",), NOW) == ()
    assert _virtual_market_ranked_symbols(settings, (), NOW) == ("SOLUSDT",)
    assert _canonical_resident_runtime_symbol(settings, NOW) == "SOLUSDT"
    assert (
        _virtual_market_priority_symbols(
            settings, (), ("SOLUSDT",), NOW + timedelta(hours=1)
        )
        == ()
    )
    assert (
        _canonical_resident_runtime_symbol(settings, NOW + timedelta(hours=1))
        == settings.symbol
    )


def test_local_archive_supplies_candles_to_shared_snapshot(tmp_path: Path) -> None:
    client = FakePublicClient()
    archive = ParquetOHLCVArchive(tmp_path)
    candles = tuple(
        item.to_candle()
        for item in client.klines("HOTUSDT", "1m", 250)
        if item.close_time <= NOW
    )
    archive.update("HOTUSDT", "1m", candles, source="FIXTURE", generated_at=NOW)
    client.calls.clear()
    snapshot = DataAcquisitionAgent(client=client, archive=archive).acquire(
        "HOTUSDT", ("1m",)
    )
    assert snapshot.data_quality == DataQuality.DATA_VALID
    assert snapshot.market_metadata["source"] == "CANONICAL_LOCAL_MARKET_ARCHIVE"
    assert not any(name.startswith("klines") for name, _ in client.calls)


def test_acquisition_consumes_verified_local_depth_and_rejects_stale_or_gapped(
    tmp_path: Path,
) -> None:
    from ai4binance.data.market_depth import DepthJournal

    path = tmp_path / "depth.sqlite3"
    journal = DepthJournal(path)
    checkpoint = {
        "lastUpdateId": 100,
        "bids": [["0.0011", "2"]],
        "asks": [["0.0013", "3"]],
        "event_at": NOW.timestamp(),
        "bridged": True,
    }
    journal.append([("spot", "HOTUSDT", "checkpoint", checkpoint, NOW.timestamp())])
    agent = DataAcquisitionAgent(
        client=FakePublicClient(),
        depth_path=path,
        clock=lambda: NOW,
    )
    snapshot = agent.acquire("HOTUSDT", ("1m",))
    assert snapshot.order_book_summary["bid_depth"] == "2"
    assert snapshot.order_book_summary["ask_depth"] == "3"
    assert snapshot.order_book_summary["depth_last_update_id"] == 100
    assert agent._local_depth_summary("OTHERUSDT", NOW) == {
        "depth_status": "UNAVAILABLE"
    }
    assert agent._local_depth_summary("HOTUSDT", NOW + timedelta(seconds=31)) == {
        "depth_status": "UNAVAILABLE"
    }
    journal.append([("spot", "HOTUSDT", "gap", {}, NOW.timestamp())])
    assert agent._local_depth_summary("HOTUSDT", NOW) == {"depth_status": "UNAVAILABLE"}
    journal.close()


def symbol_info() -> SymbolInfo:
    return SymbolInfo(
        symbol="HOTUSDT",
        status="TRADING",
        base_asset="HOT",
        quote_asset="USDT",
        filters={
            "PRICE_FILTER": {
                "minPrice": "0.000001",
                "maxPrice": "10",
                "tickSize": "0.000001",
            },
            "LOT_SIZE": {
                "minQty": "1",
                "maxQty": "1000000",
                "stepSize": "1",
            },
            "MIN_NOTIONAL": {"minNotional": "5"},
        },
    )


class FakePublicClient:
    def __init__(self, *, candle_count: int = 200, fail: bool = False) -> None:
        self.candle_count = candle_count
        self.fail = fail
        self.calls: list[tuple[str, str | None]] = []

    def server_time(self) -> datetime:
        self.calls.append(("server_time", None))
        if self.fail:
            raise ExchangeTransportError("sanitized failure")
        return NOW

    def exchange_info(self, symbol: str) -> SymbolInfo:
        self.calls.append(("exchange_info", symbol))
        return symbol_info()

    def ticker_price(self, symbol: str) -> Decimal:
        self.calls.append(("ticker_price", symbol))
        return Decimal("0.0012")

    def book_ticker(self, symbol: str) -> BookTicker:
        self.calls.append(("book_ticker", symbol))
        return BookTicker(Decimal("0.00119"), Decimal("0.00121"))

    def klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> tuple[MarketKline, ...]:
        self.calls.append((f"klines:{interval}:{limit}", symbol))
        duration = timeframe_duration(interval)
        rows = []
        for offset in range(self.candle_count, 0, -1):
            close_time = NOW - (duration * offset)
            rows.append(
                MarketKline(
                    open_time=close_time - duration,
                    close_time=close_time,
                    open=Decimal("0.001"),
                    high=Decimal("0.0013"),
                    low=Decimal("0.0009"),
                    close=Decimal("0.0012"),
                    volume=Decimal("1000"),
                )
            )
        rows.append(
            MarketKline(
                open_time=NOW,
                close_time=NOW + duration,
                open=Decimal("0.0012"),
                high=Decimal("0.0014"),
                low=Decimal("0.0011"),
                close=Decimal("0.0013"),
                volume=Decimal("500"),
            )
        )
        return tuple(rows)


def test_acquisition_builds_deterministic_closed_candle_snapshot() -> None:
    client = FakePublicClient()
    agent = DataAcquisitionAgent(
        client,
        candle_limit=250,
        minimum_closed_candles=200,
        max_workers=2,
    )
    first = agent.acquire("hotusdt", ("1h", "4h"))
    second = agent.acquire("HOTUSDT", ("1h", "4h"))

    assert first.snapshot_id == second.snapshot_id
    assert first.market_type == "SPOT"
    assert first.data_quality is DataQuality.DATA_VALID
    assert len(first.ohlcv_by_timeframe["1h"]) == 200
    assert len(first.ohlcv_by_timeframe["4h"]) == 200
    assert first.market_metadata["closed_candles_only"] is True
    assert first.exchange_filters["PRICE_FILTER"] is not None
    freshness = first.data_freshness["1h"]
    assert isinstance(freshness, Mapping)
    assert freshness["stale"] is False
    assert all(candle.timestamp < NOW for candle in first.ohlcv_by_timeframe["1h"])


def test_acquisition_marks_insufficient_history_invalid() -> None:
    agent = DataAcquisitionAgent(
        FakePublicClient(candle_count=3),
        candle_limit=10,
        minimum_closed_candles=5,
    )
    result = agent.acquire("HOTUSDT", ("1h",))
    assert result.data_quality is DataQuality.DATA_INVALID
    freshness = result.data_freshness["1h"]
    assert isinstance(freshness, Mapping)
    assert freshness["closed_candle_count"] == 3


def test_acquisition_validates_configuration_and_timeframes() -> None:
    client = FakePublicClient()
    with pytest.raises(ValueError, match="candle_limit"):
        DataAcquisitionAgent(client, candle_limit=1)
    with pytest.raises(ValueError, match="minimum_closed_candles"):
        DataAcquisitionAgent(client, candle_limit=10, minimum_closed_candles=11)
    with pytest.raises(ValueError, match="max_workers"):
        DataAcquisitionAgent(client, max_workers=9)
    agent = DataAcquisitionAgent(client)
    with pytest.raises(ValueError, match="non-empty and unique"):
        agent.acquire("HOTUSDT", ("1h", "1h"))
    with pytest.raises(ValueError, match="unsupported timeframe"):
        agent.acquire("HOTUSDT", ("7m",))
    with pytest.raises(
        ValueError,
        match="public data acquisition supports only Spot market_type",
    ):
        DataAcquisitionAgent(client, market_type="USD_M_FUTURES")


def test_acquisition_propagates_sanitized_exchange_failure() -> None:
    agent = DataAcquisitionAgent(FakePublicClient(fail=True))
    with pytest.raises(ExchangeTransportError, match="sanitized failure"):
        agent.acquire("HOTUSDT", ("1h",))


def test_timeframe_duration_mapping() -> None:
    assert timeframe_duration("15m") == timedelta(minutes=15)
    assert timeframe_duration("1d") == timedelta(days=1)


def test_data_package_lazy_futures_exports_and_rejects_unknown_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.data as data_package
    from ai4binance.data import binance_vision_futures

    export_name = "BinanceVisionFuturesSyncResult"
    namespace = vars(data_package)
    monkeypatch.delitem(namespace, export_name, raising=False)

    assert data_package.__getattr__(export_name) is getattr(
        binance_vision_futures, export_name
    )
    assert namespace[export_name] is getattr(binance_vision_futures, export_name)
    with pytest.raises(AttributeError, match="UnknownFuturesExport"):
        data_package.__getattr__("UnknownFuturesExport")

"""Shared public market snapshot acquisition tests."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.data.acquisition import DataAcquisitionAgent
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.exchange.errors import ExchangeTransportError
from ai4binance.exchange.models import BookTicker, MarketKline, SymbolInfo
from ai4binance.schemas import DataQuality

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


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


def test_acquisition_propagates_sanitized_exchange_failure() -> None:
    agent = DataAcquisitionAgent(FakePublicClient(fail=True))
    with pytest.raises(ExchangeTransportError, match="sanitized failure"):
        agent.acquire("HOTUSDT", ("1h",))


def test_timeframe_duration_mapping() -> None:
    assert timeframe_duration("15m") == timedelta(minutes=15)
    assert timeframe_duration("1d") == timedelta(days=1)

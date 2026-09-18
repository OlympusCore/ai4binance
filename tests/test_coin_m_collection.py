"""COIN-M discovery, routing, inverse units, and shared-budget contracts."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.cli.market_data import build_market_history_synchronizer
from ai4binance.config import Settings
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_continuous import (
    ContinuousMarketHistory,
    MeteredPublicTransport,
    PublicRequestBudget,
    _load,
)
from ai4binance.data.market_history_sync import (
    BinanceVisionArchiveCache,
    MarketHistorySynchronizer,
    _daily_kline_key,
)
from ai4binance.integrations.binance.market_universe_provider import (
    BinanceEligibleMarketSnapshot,
    BinanceMarketUniverseProvider,
)

NOW = datetime(2026, 9, 11, 0, 2, tzinfo=UTC)


class Metadata:
    def __init__(self, symbols: list[dict[str, object]]) -> None:
        self.symbols = symbols

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        return {"symbols": self.symbols}


def contract(asset: str, suffix: str = "PERP") -> dict[str, object]:
    return {
        "symbol": asset + "USD_" + suffix,
        "pair": asset + "USD",
        "baseAsset": asset,
        "quoteAsset": "USD",
        "marginAsset": asset,
        "contractStatus": "TRADING",
        "contractType": "PERPETUAL" if suffix == "PERP" else "CURRENT_QUARTER",
    }


def test_coin_m_discovery_preserves_filters_and_delivery_contracts() -> None:
    entries = [
        contract("BTC"),
        contract("BTC", "260925"),
        contract("USDT"),
        contract("WBETH"),
        contract("ETHUP"),
    ]
    stopped = contract("SOL")
    stopped["contractStatus"] = "DELIVERED"
    entries.append(stopped)
    provider = BinanceMarketUniverseProvider(
        Metadata([]), Metadata([]), coin_m_transport=Metadata(entries)
    )
    result = provider.eligible_market_snapshot()
    assert result.coin_m_symbols == ("BTCUSD_260925", "BTCUSD_PERP")
    assert not result.blockers
    assert result.execution_allowed is False


@pytest.mark.parametrize("identity", ["../BTCUSD_PERP", "BTCUSD_BAD", "BTCUSD_PERP/.."])
def test_invalid_coin_contract_metadata_rejected(identity: str) -> None:
    with pytest.raises(ValueError, match="contract identity"):
        BinanceEligibleMarketSnapshot(
            (), (), coin_m_contracts=((identity, "BTCUSD", "PERPETUAL"),)
        )


def test_coin_archive_key_and_inverse_symbol_validation(tmp_path: Path) -> None:
    assert _daily_kline_key("cm", "BTCUSD_PERP", "klines", "5m", NOW.date()).startswith(
        "data/futures/cm/"
    )
    archive = ParquetOHLCVArchive(tmp_path)
    with pytest.raises(ValueError, match="symbol"):
        archive.read_window("../BTCUSD_PERP", "5m", start_at=NOW, end_at=NOW)


def test_live_builder_shares_futures_weight_budget_without_credentials(
    tmp_path: Path,
) -> None:
    provider = build_market_history_synchronizer(
        Settings(dataset_directory=tmp_path)
    ).universe_provider
    assert isinstance(provider.futures_transport, MeteredPublicTransport)
    assert isinstance(provider.coin_m_transport, MeteredPublicTransport)
    assert provider.futures_transport.budget is provider.coin_m_transport.budget
    assert provider.futures_transport.budget is not None
    assert (
        build_market_history_synchronizer(
            Settings(market_history_coin_m_enabled=False)
        ).universe_provider.coin_m_transport
        is None
    )


def test_shared_budget_accounts_for_depth_and_bulk_snapshot_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(
        "ai4binance.data.market_history_continuous.time.monotonic", lambda: clock[0]
    )
    monkeypatch.setattr(
        "ai4binance.data.market_history_continuous.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    budget = PublicRequestBudget()
    budget.acquire("/fapi/v1/depth")
    budget.acquire("/dapi/v1/premiumIndex")
    assert clock[0] == pytest.approx(0.1)
    budget.acquire("/fapi/v1/klines")
    assert clock[0] == pytest.approx(0.6)


class CoinTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        query = dict(params or {})
        self.calls.append((path, query))
        if path.endswith("fundingRate"):
            return [
                {
                    "symbol": "BTCUSD_PERP",
                    "fundingTime": query["startTime"],
                    "fundingRate": "0.001",
                }
            ]
        if path.endswith("openInterestHist"):
            return [
                {
                    "pair": "BTCUSD",
                    "contractType": "PERPETUAL",
                    "timestamp": query["startTime"],
                    "sumOpenInterest": "100",
                    "sumOpenInterestValue": "0.1",
                }
            ]
        interval_ms = {
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }[str(query.get("interval", "5m"))]
        return [
            [
                stamp,
                "100",
                "102",
                "99",
                "101",
                "5",
                stamp + interval_ms - 1,
                "0.05",
                2,
                "3",
                "0.03",
                "0",
            ]
            for stamp in range(
                int(query["startTime"]),
                min(
                    int(query["endTime"]) + 1,
                    int(query["startTime"]) + int(query["limit"]) * interval_ms,
                ),
                interval_ms,
            )
        ]


def collector(root: Path) -> ContinuousMarketHistory:
    history = MarketHistorySynchronizer(
        BinanceMarketUniverseProvider(Metadata([]), Metadata([])),
        root,
        BinanceVisionArchiveCache(root / "sources", lambda url: b""),
        root / "state.json",
    )
    transport = CoinTransport()
    return ContinuousMarketHistory(
        history,
        transport,
        transport,
        initial_days=1,
        pages_per_stream=3,
        vision_history_enabled=False,
        coin_m=transport,
        coin_m_contracts={
            "BTCUSD_PERP": ("BTCUSD", "PERPETUAL"),
            "BTCUSD_260925": ("BTCUSD", "CURRENT_QUARTER"),
        },
    )


def test_coin_m_candles_use_dapi_and_index_pair_shared_archive(tmp_path: Path) -> None:
    worker = collector(tmp_path)
    for kind, folder in (
        ("klines", "coin_m_futures/BTCUSD_PERP"),
        ("indexPriceKlines", "coin_m_futures_index/BTCUSD"),
    ):
        directory = tmp_path / folder
        directory.mkdir(parents=True, exist_ok=True)
        from ai4binance.data.market_history_continuous import _save

        start = NOW - timedelta(minutes=2)
        _save(
            directory / "collection-progress.json",
            {"requested_start": start.isoformat(), "next_at": start.isoformat()},
        )
        assert worker.coin_m is not None
        result = worker._candles(
            "coin_m_futures", "BTCUSD_PERP", kind, worker.coin_m, NOW
        )
        assert result["status"] == "CURRENT"
        assert (directory / "5m.parquet").is_file()
        receipt = _load(next((directory / "sources").glob("*.json")))
        if kind == "klines":
            assert receipt["volume_unit"] == "CONTRACTS"
    assert isinstance(worker.coin_m, CoinTransport)
    assert worker.coin_m.calls[-1][0] == "/dapi/v1/indexPriceKlines"
    assert worker.coin_m.calls[-1][1]["pair"] == "BTCUSD"


def test_coin_details_use_pair_contract_and_skip_delivery_funding(
    tmp_path: Path,
) -> None:
    from ai4binance.data.market_history_continuous import _save

    worker = collector(tmp_path)
    for kind in ("funding", "open_interest"):
        directory = tmp_path / "coin_m_futures/BTCUSD_PERP/details" / kind
        start = NOW - timedelta(minutes=5)
        _save(
            directory / "collection-progress.json",
            {"requested_start": start.isoformat(), "next_at": start.isoformat()},
        )
        assert (
            worker._details("BTCUSD_PERP", kind, NOW, market="coin_m_futures")["status"]
            == "CURRENT"
        )
    assert isinstance(worker.coin_m, CoinTransport)
    params = worker.coin_m.calls[-1][1]
    assert params["pair"] == "BTCUSD"
    assert params["contractType"] == "PERPETUAL"
    assert "symbol" not in params
    assert (
        worker._details("BTCUSD_260925", "funding", NOW, market="coin_m_futures")[
            "status"
        ]
        == "NOT_APPLICABLE"
    )

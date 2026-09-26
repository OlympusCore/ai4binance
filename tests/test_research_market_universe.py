from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.data.market_universe_retention import MarketUniverseRetention
from ai4binance.domain.universe import (
    RESEARCH_MARKET_UNIVERSE_SOURCE as CANONICAL_SOURCE,
)
from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot
from ai4binance.integrations.research_market_universe import (
    RESEARCH_MARKET_UNIVERSE_SOURCE,
    ResearchMarketUniverseProvider,
    read_wallet_assets_above_value,
)

NOW = datetime(2026, 9, 26, 1, 0, tzinfo=UTC)
MARKET_CAP_ASSETS = (
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "DOGE",
    "ADA",
    "TRX",
    "AVAX",
    "LINK",
    "DOT",
    "BCH",
    "LTC",
    "NEAR",
    "AAVE",
    "UNI",
    "ICP",
    "FIL",
    "XLM",
    "HBAR",
)


def test_research_universe_source_uses_canonical_domain_contract() -> None:
    assert RESEARCH_MARKET_UNIVERSE_SOURCE == CANONICAL_SOURCE


class _MarketCapTransport:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object]] = []

    def get_json(self, path: str, params: object = None) -> object:
        self.calls.append((path, params))
        return self.rows


def _wallet_record(
    *, asset: str, value: str, run_id: str, observed_at: datetime
) -> dict[str, object]:
    return {
        "timestamp": observed_at.isoformat(),
        "payload": {
            "asset": asset,
            "market_value_usdt": value,
            "execution_allowed": False,
            "envelope": {
                "sync_run_id": run_id,
                "event_time": observed_at.isoformat(),
            },
        },
    }


def _write_wallet(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _metadata() -> BinanceEligibleMarketSnapshot:
    assets = (*MARKET_CAP_ASSETS, "ATOM", "USDT", "WBTC")
    return BinanceEligibleMarketSnapshot(
        spot_symbols=tuple(sorted(f"{asset}USDT" for asset in assets)),
        futures_symbols=tuple(
            sorted(f"{asset}USDT" for asset in assets if asset not in {"USDT", "WBTC"})
        ),
    )


def test_wallet_reader_uses_only_latest_complete_run_and_strict_value_floor(
    tmp_path: Path,
) -> None:
    path = tmp_path / "balance_snapshots.jsonl"
    _write_wallet(
        path,
        [
            _wallet_record(
                asset="OLD",
                value="100",
                run_id="old",
                observed_at=NOW - timedelta(minutes=5),
            ),
            _wallet_record(asset="ATOM", value="1.01", run_id="new", observed_at=NOW),
            _wallet_record(asset="DUST", value="1", run_id="new", observed_at=NOW),
        ],
    )

    snapshot = read_wallet_assets_above_value(
        path,
        observed_at=NOW,
        minimum_value_usdt=Decimal("1"),
        maximum_age=timedelta(minutes=30),
    )

    assert snapshot.assets == ("ATOM",)
    assert snapshot.sync_run_id == "new"


def test_research_universe_unions_wallet_and_filtered_market_cap(
    tmp_path: Path,
) -> None:
    wallet_path = tmp_path / "balance_snapshots.jsonl"
    _write_wallet(
        wallet_path,
        [_wallet_record(asset="ATOM", value="2", run_id="new", observed_at=NOW)],
    )
    rows = [
        {"symbol": "usdt", "name": "Tether", "market_cap_rank": 1, "market_cap": 1},
        {
            "symbol": "wbtc",
            "name": "Wrapped Bitcoin",
            "market_cap_rank": 2,
            "market_cap": 1,
        },
        {
            "symbol": "usds",
            "name": "USDS",
            "market_cap_rank": 3,
            "market_cap": 1,
        },
        *[
            {
                "symbol": asset.lower(),
                "name": asset,
                "market_cap_rank": rank,
                "market_cap": 1_000_000 - rank,
            }
            for rank, asset in enumerate(MARKET_CAP_ASSETS, start=4)
        ],
    ]
    metadata = _metadata()
    binance = SimpleNamespace(
        quote_assets=("USDT", "USDC"),
        spot_transport=object(),
        futures_transport=object(),
        eligible_market_snapshot=lambda: metadata,
    )
    transport = _MarketCapTransport(rows)
    provider = ResearchMarketUniverseProvider(
        binance=binance,  # type: ignore[arg-type]
        market_cap_transport=transport,
        wallet_balance_path=wallet_path,
        clock=lambda: NOW,
    )

    result = provider.priority_eligible_market_snapshot()

    assert result.blockers == ()
    assert result.wallet_assets == ("ATOM",)
    assert result.market_cap_assets == MARKET_CAP_ASSETS
    assert len(result.market_cap_assets) == 20
    assert "USDT" not in result.selected_assets
    assert "WBTC" not in result.selected_assets
    assert "USDS" not in result.selected_assets
    assert "ATOMUSDT" in result.spot_symbols
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert transport.calls[0][0] == "/api/v3/coins/markets"


def test_research_universe_fails_closed_for_stale_wallet(tmp_path: Path) -> None:
    wallet_path = tmp_path / "balance_snapshots.jsonl"
    _write_wallet(
        wallet_path,
        [
            _wallet_record(
                asset="ATOM",
                value="2",
                run_id="old",
                observed_at=NOW - timedelta(hours=1),
            )
        ],
    )
    metadata = _metadata()
    provider = ResearchMarketUniverseProvider(
        binance=SimpleNamespace(
            quote_assets=("USDT",),
            spot_transport=object(),
            futures_transport=object(),
            eligible_market_snapshot=lambda: metadata,
        ),  # type: ignore[arg-type]
        market_cap_transport=_MarketCapTransport([]),
        wallet_balance_path=wallet_path,
        clock=lambda: NOW,
    )

    result = provider.priority_eligible_market_snapshot()

    assert result.spot_symbols == ()
    assert result.blockers == ("WALLET_UNIVERSE_UNAVAILABLE_OR_STALE",)


def test_retention_removes_only_out_of_scope_symbol_directories(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "market"
    sources = tmp_path / "market_sources"
    monitor = tmp_path / "monitor"
    replay = tmp_path / "replay"
    validation = tmp_path / "validation"
    keep = archive / "spot" / "BTCUSDT"
    drop = archive / "spot" / "OLDUSDT"
    non_ascii_drop = archive / "usd_m_futures" / "币安人生USDT"
    metadata = archive / "spot" / "metadata"
    coin_m_archive = archive / "coin_m_futures" / "metadata"
    source_keep = sources / "data/spot/daily/klines/BTCUSDT"
    source_drop = sources / "data/spot/daily/klines/OLDUSDT"
    coin_m = sources / "data/futures/cm/daily/klines/BTCUSD_PERP"
    monitor_keep = monitor / "SPOT" / "BTCUSDT"
    monitor_drop = monitor / "SPOT" / "OLDUSDT"
    replay.mkdir()
    replay_keep = replay / "BTCUSDT-5m-window.json"
    replay_drop = replay / "OLDUSDT-5m-window.json"
    replay_keep.write_text("{}", encoding="utf-8")
    replay_drop.write_text("{}", encoding="utf-8")
    validation_keep = validation / "BTCUSDT"
    validation_drop = validation / "OLDUSDT"
    for directory in (
        keep,
        drop,
        non_ascii_drop,
        metadata,
        coin_m_archive,
        source_keep,
        source_drop,
        coin_m,
        monitor_keep,
        monitor_drop,
        validation_keep,
        validation_drop,
    ):
        directory.mkdir(parents=True)
        (directory / "value.json").write_text("{}", encoding="utf-8")
    retention = MarketUniverseRetention(
        archive,
        sources,
        monitor,
        futures_replay_root=replay,
        futures_artifact_roots=(validation,),
    )
    universe = BinanceEligibleMarketSnapshot(
        spot_symbols=("BTCUSDT",), futures_symbols=("BTCUSDT",)
    )

    result = retention.prune(universe)

    assert result["status"] == "PRUNED"
    assert keep.is_dir()
    assert metadata.is_dir()
    assert not coin_m_archive.exists()
    assert source_keep.is_dir()
    assert monitor_keep.is_dir()
    assert replay_keep.is_file()
    assert validation_keep.is_dir()
    assert not drop.exists()
    assert not non_ascii_drop.exists()
    assert not source_drop.exists()
    assert not coin_m.exists()
    assert not monitor_drop.exists()
    assert not replay_drop.exists()
    assert not validation_drop.exists()


@pytest.mark.parametrize("invalid_value", [Decimal("0"), Decimal("NaN")])
def test_wallet_reader_rejects_invalid_floor(
    tmp_path: Path, invalid_value: Decimal
) -> None:
    with pytest.raises(ValueError, match="bounds must be positive"):
        read_wallet_assets_above_value(
            tmp_path / "missing.jsonl",
            observed_at=NOW,
            minimum_value_usdt=invalid_value,
            maximum_age=timedelta(minutes=30),
        )

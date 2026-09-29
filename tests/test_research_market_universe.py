from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from ai4binance.data.market_history_sync import read_cached_market_universe
from ai4binance.data.market_universe_retention import MarketUniverseRetention
from ai4binance.domain.universe import (
    RESEARCH_MANUAL_UNIVERSE_SOURCE,
)
from ai4binance.domain.universe import (
    RESEARCH_MARKET_UNIVERSE_SOURCE as CANONICAL_SOURCE,
)
from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot
from ai4binance.integrations.research_market_universe import (
    RESEARCH_MARKET_UNIVERSE_SOURCE,
    ReadOnlyCoinGeckoJsonTransport,
    ResearchMarketUniverseProvider,
    manual_selection_digest,
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


def test_manual_research_selection_uses_current_binance_metadata_without_coingecko(
    tmp_path: Path,
) -> None:
    wallet_path = tmp_path / "balance_snapshots.jsonl"
    _write_wallet(
        wallet_path,
        [_wallet_record(asset="ATOM", value="2", run_id="now", observed_at=NOW)],
    )
    selection_path = tmp_path / "manual_universe.yaml"
    selection_path.write_text(
        'schema_version: "1.0"\n'
        "selection_mode: MANUAL_RESEARCH_SELECTION\n"
        "spot_assets: [BTC, ETH]\n"
        "usd_m_futures_assets: [BTC, SOL]\n",
        encoding="utf-8",
    )
    metadata = _metadata()
    transport = _MarketCapTransport([])
    provider = ResearchMarketUniverseProvider(
        binance=SimpleNamespace(
            quote_assets=("USDT",),
            spot_transport=object(),
            futures_transport=object(),
            eligible_market_snapshot=lambda: metadata,
        ),  # type: ignore[arg-type]
        market_cap_transport=transport,
        wallet_balance_path=wallet_path,
        manual_selection_path=selection_path,
        clock=lambda: NOW,
    )

    result = provider.priority_eligible_market_snapshot()

    assert result.blockers == ()
    assert result.source == RESEARCH_MANUAL_UNIVERSE_SOURCE
    assert result.spot_symbols == ("ATOMUSDT", "BTCUSDT", "ETHUSDT")
    assert result.futures_symbols == ("ATOMUSDT", "BTCUSDT", "SOLUSDT")
    assert result.market_cap_assets == ()
    assert result.manual_selection_sha256 == manual_selection_digest(selection_path)
    assert transport.calls == []
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    cache_path = tmp_path / "universe-v3.json"
    cache_path.write_text(
        json.dumps(
            {
                "observed_at": NOW.isoformat(),
                "spot_symbols": result.spot_symbols,
                "futures_symbols": result.futures_symbols,
                "excluded_assets": result.excluded_assets,
                "source": result.source,
                "manual_selection_sha256": result.manual_selection_sha256,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    assert (
        read_cached_market_universe(
            cache_path,
            NOW,
            expected_source=RESEARCH_MANUAL_UNIVERSE_SOURCE,
            expected_manual_selection_sha256=manual_selection_digest(selection_path),
        )
        is not None
    )
    selection_path.write_text(
        selection_path.read_text(encoding="utf-8").replace("ETH", "ADA"),
        encoding="utf-8",
    )
    assert (
        read_cached_market_universe(
            cache_path,
            NOW,
            expected_source=RESEARCH_MANUAL_UNIVERSE_SOURCE,
            expected_manual_selection_sha256=manual_selection_digest(selection_path),
        )
        is None
    )


@pytest.mark.parametrize(
    ("spot_assets", "futures_assets"),
    [
        ("BTC, BTC", "SOL"),
        ("USDT", "SOL"),
        ("WBTC", "SOL"),
        ("NOTLISTED", "SOL"),
        ("BTC", ""),
    ],
)
def test_manual_research_selection_fails_closed_for_invalid_entries(
    tmp_path: Path, spot_assets: str, futures_assets: str
) -> None:
    wallet_path = tmp_path / "balance_snapshots.jsonl"
    _write_wallet(
        wallet_path,
        [_wallet_record(asset="ATOM", value="2", run_id="now", observed_at=NOW)],
    )
    selection_path = tmp_path / "manual_universe.yaml"
    selection_path.write_text(
        'schema_version: "1.0"\n'
        "selection_mode: MANUAL_RESEARCH_SELECTION\n"
        f"spot_assets: [{spot_assets}]\n"
        f"usd_m_futures_assets: [{futures_assets}]\n",
        encoding="utf-8",
    )
    metadata = _metadata()
    transport = _MarketCapTransport([])
    provider = ResearchMarketUniverseProvider(
        binance=SimpleNamespace(
            quote_assets=("USDT",),
            eligible_market_snapshot=lambda: metadata,
        ),  # type: ignore[arg-type]
        market_cap_transport=transport,
        wallet_balance_path=wallet_path,
        manual_selection_path=selection_path,
        clock=lambda: NOW,
    )

    result = provider.priority_eligible_market_snapshot()

    assert result.spot_symbols == ()
    assert result.futures_symbols == ()
    assert result.blockers == ("MANUAL_RESEARCH_SELECTION_INVALID",)
    assert result.execution_allowed is False
    assert transport.calls == []


def test_public_market_cap_proposal_is_explicit_and_does_not_edit_manual_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance.cli import market_data
    from ai4binance.config import Settings

    wallet_path = tmp_path / "balance_snapshots.jsonl"
    _write_wallet(
        wallet_path,
        [_wallet_record(asset="ATOM", value="2", run_id="now", observed_at=NOW)],
    )
    selection_path = tmp_path / "manual_universe.yaml"
    selection_path.write_text(
        'schema_version: "1.0"\n'
        "selection_mode: MANUAL_RESEARCH_SELECTION\n"
        "spot_assets: [BTC]\n"
        "usd_m_futures_assets: [ETH]\n",
        encoding="utf-8",
    )
    original = selection_path.read_bytes()
    rows = [
        {
            "symbol": asset.lower(),
            "name": asset,
            "market_cap_rank": index,
            "market_cap": 1_000_000 - index,
            "last_updated": NOW.isoformat(),
        }
        for index, asset in enumerate(MARKET_CAP_ASSETS, start=1)
    ]
    transport = _MarketCapTransport(rows)
    provider = ResearchMarketUniverseProvider(
        binance=SimpleNamespace(
            quote_assets=("USDT",),
            eligible_market_snapshot=_metadata,
        ),  # type: ignore[arg-type]
        market_cap_transport=transport,
        wallet_balance_path=wallet_path,
        manual_selection_path=selection_path,
        clock=lambda: NOW,
    )
    monkeypatch.setattr(
        market_data,
        "build_market_history_synchronizer",
        lambda _settings: SimpleNamespace(universe_provider=provider),
    )
    settings = Settings(market_history_manual_universe_path=selection_path)

    assert (
        market_data.run_market_history_command(
            "market-history-rank-proposal", settings, as_of=None, max_cycles=None
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "REVIEW_ONLY"
    assert result["manual_selection_modified"] is False
    assert len(result["spot_assets"]) == 20
    assert len(result["usd_m_futures_assets"]) == 20
    assert result["execution_allowed"] is False
    assert selection_path.read_bytes() == original
    assert len(transport.calls) == 1


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


@pytest.mark.parametrize("spot_only_extra", [False, True])
def test_research_universe_unions_wallet_and_filtered_market_cap(
    tmp_path: Path,
    spot_only_extra: bool,
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
                "last_updated": NOW.isoformat(),
            }
            for rank, asset in enumerate(MARKET_CAP_ASSETS, start=4)
        ],
    ]
    metadata = _metadata()
    if spot_only_extra:
        from dataclasses import replace

        metadata = replace(
            metadata,
            spot_symbols=tuple(
                sorted(
                    (
                        *(
                            s
                            for s in metadata.spot_symbols
                            if s != MARKET_CAP_ASSETS[0] + "USDT"
                        ),
                        "EXTRAUSDT",
                    )
                )
            ),
        )
        rows.append(
            {
                "symbol": "extra",
                "name": "Extra",
                "market_cap_rank": 99,
                "market_cap": 1,
                "last_updated": NOW.isoformat(),
            }
        )
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
    if spot_only_extra:
        assert "EXTRAUSDT" in result.spot_symbols
        assert "EXTRAUSDT" not in result.futures_symbols
        assert MARKET_CAP_ASSETS[0] + "USDT" in result.futures_symbols
        assert len(result.market_cap_assets) == 21
    else:
        assert result.market_cap_assets == MARKET_CAP_ASSETS
        assert len(result.market_cap_assets) == 20
    assert "USDT" not in result.selected_assets
    assert "WBTC" not in result.selected_assets
    assert "USDS" not in result.selected_assets
    assert "ATOMUSDT" in result.spot_symbols
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert transport.calls[0][0] == "/api/v3/coins/markets"


@pytest.mark.parametrize("age_minutes", [-2, 61])
def test_market_cap_ranking_rejects_stale_or_future_observations(
    tmp_path: Path,
    age_minutes: int,
) -> None:
    metadata = _metadata()
    provider = ResearchMarketUniverseProvider(
        binance=SimpleNamespace(quote_assets=("USDT", "USDC")),  # type: ignore[arg-type]
        market_cap_transport=_MarketCapTransport([]),
        wallet_balance_path=tmp_path / "unused.jsonl",
        clock=lambda: NOW,
    )
    rows = [
        {
            "symbol": MARKET_CAP_ASSETS[0],
            "name": MARKET_CAP_ASSETS[0],
            "market_cap_rank": 1,
            "market_cap": 100,
            "last_updated": (NOW - timedelta(minutes=age_minutes)).isoformat(),
        }
    ]
    with pytest.raises(ValueError, match="stale"):
        provider._ranked_assets(rows, metadata, market="SPOT")


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


@pytest.mark.parametrize("status_code", [403, 429, 503])
def test_public_market_cap_http_failure_reaches_universe_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    from ai4binance.integrations import research_market_universe

    calls: list[str] = []

    def blocked(request: object, **_kwargs: object) -> object:
        calls.append("request")
        raise HTTPError(
            "https://api.coingecko.com", status_code, "test-only", Message(), None
        )

    monkeypatch.setattr(research_market_universe, "urlopen", blocked)
    wallet_path = tmp_path / "wallet.jsonl"
    _write_wallet(
        wallet_path,
        [_wallet_record(asset="ATOM", value="2", run_id="test-only", observed_at=NOW)],
    )
    provider = ResearchMarketUniverseProvider(
        binance=SimpleNamespace(eligible_market_snapshot=_metadata),  # type: ignore[arg-type]
        market_cap_transport=ReadOnlyCoinGeckoJsonTransport(max_attempts=2),
        wallet_balance_path=wallet_path,
        clock=lambda: NOW,
    )

    result = provider.priority_eligible_market_snapshot()

    assert result.spot_symbols == result.futures_symbols == ()
    assert result.blockers == (
        "PUBLIC_MARKET_CAP_UNIVERSE_UNAVAILABLE",
        f"PUBLIC_MARKET_CAP_HTTP_{status_code}",
    )
    assert len(calls) == (2 if status_code == 503 else 1)


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

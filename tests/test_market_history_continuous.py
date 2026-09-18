"""Deterministic resume, bandwidth, coverage, and shared-reader contracts."""

import hashlib
import io
import json
import zipfile
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event, Thread
from typing import cast

import pytest

from ai4binance.cli.market_data import (
    _build_canonical_opportunity_pipeline,
    _priority_depth_markets,
)
from ai4binance.cli.market_data import (
    main as market_data_main,
)
from ai4binance.config import Settings
from ai4binance.core.errors import ExchangeHttpError, ExchangeTransportError
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_continuous import (
    ContinuousMarketHistory,
    MeteredPublicTransport,
    PublicRequestBudget,
    _load,
    _save,
    enqueue_market_history_refresh_request,
    market_history_refresh_status,
)
from ai4binance.data.market_history_sync import (
    MARKET_HISTORY_TIMEFRAMES,
    BinanceVisionArchiveCache,
    MarketHistorySynchronizer,
)
from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 9, 2, 0, 2, tzinfo=UTC)


class Universe:
    def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
        return BinanceEligibleMarketSnapshot(
            spot_symbols=("BTCUSDT",), futures_symbols=()
        )


class Transport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        query = dict(params or {})
        self.calls.append((path, query))
        if path.endswith(("bookTicker", "24hr")):
            return [{"symbol": "BTCUSDT"}]
        start = int(query["startTime"])
        end = int(query["endTime"])
        limit = int(query["limit"])
        interval = {
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }[str(query.get("interval", "5m"))]
        return [
            row(stamp, interval)
            for stamp in range(start, min(end + 1, start + limit * interval), interval)
        ]


def row(stamp: int, interval: int = 60_000) -> list[object]:
    return [
        stamp,
        "100",
        "102",
        "99",
        "101",
        "1",
        stamp + interval - 1,
        "101",
        2,
        "0.5",
        "50.5",
        "0",
    ]


def collector(
    root: Path, transport: Transport, pages: int = 2
) -> ContinuousMarketHistory:
    def unavailable(url: str) -> bytes:
        from email.message import Message
        from urllib.error import HTTPError

        raise HTTPError(url, 404, "fixture unavailable", Message(), None)

    history = MarketHistorySynchronizer(
        universe_provider=Universe(),  # type: ignore[arg-type]
        archive_root=root / "market",
        source_cache=BinanceVisionArchiveCache(root / "sources", unavailable),
        state_path=root / "state.json",
    )
    return ContinuousMarketHistory(
        history,
        transport,
        transport,
        initial_days=1,
        pages_per_stream=pages,
        vision_history_enabled=False,
    )


def test_collection_worker_limit_supports_bounded_archive_parallelism(
    tmp_path: Path,
) -> None:
    instance = collector(tmp_path, Transport())
    instance.max_workers = 8
    instance.__post_init__()

    instance.max_workers = 9
    with pytest.raises(ValueError, match="between 1 and 8"):
        instance.__post_init__()


@pytest.mark.parametrize("workers", [1, 4])
def test_staged_universe_collects_all_virtual_market_timeframes_before_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workers: int
) -> None:
    instance = collector(tmp_path, Transport())
    instance.max_workers = workers
    monkeypatch.setattr(
        MarketHistorySynchronizer,
        "_eligible_universe",
        lambda *_a, **_k: BinanceEligibleMarketSnapshot(
            spot_symbols=("BTCUSDT", "ETHUSDT"),
            futures_symbols=("BTCUSDT", "ETHUSDT"),
        ),
    )
    calls: list[tuple[str, str, str | None]] = []
    analyzed: list[tuple[str, str]] = []

    def collect(
        market: str,
        symbol: str,
        *_args: object,
        timeframe: str | None,
        **_kwargs: object,
    ) -> dict[str, object]:
        calls.append((market, symbol, timeframe))
        return {"status": "CURRENT"}

    def screen(market: str, symbol: str, _now: datetime) -> Mapping[str, object]:
        return {
            "status": "CURRENT",
            "enrichment_required": symbol == "ETHUSDT",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def analyze(market: str, symbol: str, _now: datetime) -> Mapping[str, object]:
        analyzed.append((market, symbol))
        return {"status": "CURRENT", "candidate_count": 0}

    monkeypatch.setattr(instance, "_collect_stream", collect)
    instance.on_symbol_screen = screen
    instance.on_symbol_ready = analyze
    result = instance.sync_cycle(observed_at=NOW)
    assert len(calls) == 20
    assert {tf for _, _, tf in calls} == set(MARKET_HISTORY_TIMEFRAMES)
    assert len(calls) == len(set(calls))
    assert sorted(analyzed) == [
        ("SPOT", "BTCUSDT"),
        ("SPOT", "ETHUSDT"),
        ("USD_M_FUTURES", "BTCUSDT"),
        ("USD_M_FUTURES", "ETHUSDT"),
    ]
    assert result["total_streams"] == result["completed_streams"] == 20
    assert result["completed_symbols"] == 4
    assert result["execution_allowed"] is False


@pytest.mark.parametrize("failed", [True, False])
def test_staged_screen_failure_or_no_trigger_never_downloads_enrichment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    instance = collector(tmp_path, Transport())
    calls: list[str | None] = []

    def collect(
        *_args: object, timeframe: str | None, **_kwargs: object
    ) -> dict[str, object]:
        calls.append(timeframe)
        return {"status": "CURRENT"}

    def screen(*_args: object) -> Mapping[str, object]:
        if failed:
            raise ValueError("fixture")
        return {"status": "CURRENT", "enrichment_required": False}

    monkeypatch.setattr(instance, "_collect_stream", collect)
    instance.on_symbol_screen = screen
    instance.sync_cycle(observed_at=NOW)
    assert calls == list(MARKET_HISTORY_TIMEFRAMES)


def test_existing_archive_fetches_only_holes_then_tail_without_replaying_rows(
    tmp_path: Path,
) -> None:
    transport = Transport()
    instance = collector(tmp_path, transport, pages=8)
    end = NOW.replace(minute=0)
    start = end - timedelta(days=1)
    holes = {start + timedelta(hours=3), start + timedelta(hours=15)}
    archive = ParquetOHLCVArchive(instance.history.archive_root / "spot")
    existing = tuple(
        OHLCVCandle(
            timestamp=start + timedelta(hours=i),
            open=Decimal(100),
            high=Decimal(102),
            low=Decimal(99),
            close=Decimal(101),
            volume=Decimal(1),
        )
        for i in range(23)
        if start + timedelta(hours=i) not in holes
    )
    archive.update(
        "BTCUSDT", "1h", existing, source="BINANCE_PUBLIC_REST_1H", generated_at=NOW
    )
    progress = archive.root / "BTCUSDT/1h/collection-progress.json"
    _save(
        progress,
        {
            "requested_start": start.isoformat(),
            "next_at": (end - timedelta(hours=1)).isoformat(),
            "first_available_at": start.isoformat(),
        },
    )
    result = instance._candles(
        "spot", "BTCUSDT", "klines", transport, NOW, timeframe="1h"
    )
    assert result["status"] == "CURRENT"
    assert len(transport.calls) == 3
    assert [query["limit"] for _, query in transport.calls] == [1, 1, 1]
    assert {int(query["startTime"]) for _, query in transport.calls} == {
        int(t.timestamp() * 1000) for t in (*holes, end - timedelta(hours=1))
    }
    assert archive.manifest("BTCUSDT", "1h").row_count == 24
    assert archive.manifest("BTCUSDT", "1h").gap_count == 0
    instance._candles("spot", "BTCUSDT", "klines", transport, NOW, timeframe="1h")
    assert len(transport.calls) == 3


def test_screen_pipeline_persists_separate_market_results(tmp_path: Path) -> None:
    from ai4binance.cli.market_data import _build_opportunity_screen

    pipeline = _build_opportunity_screen(
        Settings(dataset_directory=tmp_path / "market"), tmp_path
    )
    for market in ("SPOT", "USD_M_FUTURES"):
        result = pipeline(market, "BTCUSDT", NOW)
        assert result["status"] == "DATA_BLOCKED"
        assert result["enrichment_required"] is False
        path = (
            tmp_path
            / "runtime/artifacts/opportunity-radar/monitor"
            / market
            / "BTCUSDT/screening.json"
        )
        assert _load(path)["market"] == market


def test_futures_enrichment_uses_canonical_monitor_under_shared_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.ops import SingleInstanceLease

    settings = Settings(dataset_directory=tmp_path / "market")
    calls: list[str] = []

    def refresh(
        _settings: Settings,
        root: Path,
        symbol: str,
        _now: datetime,
        *,
        timeframes: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        assert timeframes == MARKET_HISTORY_TIMEFRAMES
        lock = (
            root
            / "runtime/artifacts/opportunity-radar/monitor/USD_M_FUTURES"
            / symbol
            / "refresh.lock"
        )
        assert SingleInstanceLease.lock_owner_is_active(lock)
        calls.append(symbol)
        return {
            "quality": [
                {"timeframe": tf, "status": "CURRENT"}
                for tf in ("5m", "15m", "1h", "4h", "1d")
            ],
            "candidates": [],
        }

    monkeypatch.setattr(futures_multitf, "_refresh_futures_monitor", refresh)
    pipeline = _build_canonical_opportunity_pipeline(
        settings, tmp_path, include_futures=True
    )
    assert pipeline("USD_M_FUTURES", "BTCUSDT", NOW)["status"] == "CURRENT"
    assert calls == ["BTCUSDT"]
    lock = (
        tmp_path
        / "runtime/artifacts/opportunity-radar/monitor/USD_M_FUTURES"
        / "BTCUSDT/refresh.lock"
    )
    with SingleInstanceLease(lock):
        assert pipeline("USD_M_FUTURES", "BTCUSDT", NOW)["status"] == "COALESCED"
        assert (
            futures_multitf._monitor_futures_symbol(settings, tmp_path, "BTCUSDT", NOW)[
                "status"
            ]
            == "COALESCED"
        )
    assert calls == ["BTCUSDT"]


def test_staged_explicit_refresh_coalesces_candidate_enrichment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    instance.refresh_request_path = tmp_path / "request.json"
    enqueue_market_history_refresh_request(
        instance.refresh_request_path,
        market="SPOT",
        symbol="BTCUSDT",
        requested_at=NOW,
        eligible_symbols=("BTCUSDT",),
    )
    calls: list[str | None] = []

    def collect(
        *_args: object, timeframe: str | None, **_kwargs: object
    ) -> dict[str, object]:
        calls.append(timeframe)
        return {"status": "CURRENT"}

    monkeypatch.setattr(instance, "_collect_stream", collect)
    instance.on_symbol_screen = lambda *_: {
        "status": "CURRENT",
        "enrichment_required": True,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    result = instance.sync_cycle(observed_at=NOW)
    assert calls == list(MARKET_HISTORY_TIMEFRAMES)
    assert (
        result["completed_streams"]
        == result["total_streams"]
        == len(MARKET_HISTORY_TIMEFRAMES)
    )


def test_recoverable_cycle_failure_is_persisted_for_retry(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    instance.history.state_path.write_text(
        '{"status":"COLLECTING","blockers":["MARKET_DATA_CYCLE_IN_PROGRESS"],'
        '"completed_streams":5,"total_streams":10}',
        encoding="utf-8",
    )

    instance.record_recoverable_cycle_failure(NOW, OSError("private detail"))

    state = _load(instance.history.state_path)
    assert state["status"] == "DEGRADED"
    assert state["last_error_type"] == "OSError"
    assert state["recovery_action"] == "RETRY_NEXT_CYCLE"
    assert state["completed_streams"] == 5
    assert state["total_streams"] == 10
    assert state["blockers"] == ["MARKET_HISTORY_CYCLE_RETRY_PENDING"]
    assert "private detail" not in instance.history.state_path.read_text(
        encoding="utf-8"
    )
    assert state["execution_allowed"] is False
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_recoverable_cycle_failure_tolerates_malformed_previous_blockers(
    tmp_path: Path,
) -> None:
    instance = collector(tmp_path, Transport())
    instance.history.state_path.write_text(
        '{"status":"COLLECTING","blockers":null}',
        encoding="utf-8",
    )

    instance.record_recoverable_cycle_failure(NOW, ValueError("bad payload"))

    state = _load(instance.history.state_path)
    assert state["status"] == "DEGRADED"
    assert state["blockers"] == ["MARKET_HISTORY_CYCLE_RETRY_PENDING"]


def test_resume_fetches_native_timeframes_without_local_materialization(
    tmp_path: Path,
) -> None:
    transport = Transport()
    first = collector(tmp_path, transport)
    report = first.sync_cycle(observed_at=NOW)
    assert report["status"] == "READY"
    refresh_schedule = report["timeframe_refresh_schedule"]
    assert isinstance(refresh_schedule, list)
    assert all(isinstance(row, Mapping) for row in refresh_schedule)
    refresh_rows = cast(list[Mapping[str, object]], refresh_schedule)
    assert all(row["network_download"] is True for row in refresh_rows)
    assert {row["closed_history_source"] for row in refresh_rows} == {
        f"BINANCE_VISION_{timeframe.upper()}_DIRECT"
        for timeframe in MARKET_HISTORY_TIMEFRAMES
    }
    progress = tmp_path / "market/spot/BTCUSDT/5m/collection-progress.json"
    resumed = collector(tmp_path, transport)
    second = resumed.sync_cycle(observed_at=NOW)
    assert second["status"] == "READY"
    klines = [params for path, params in transport.calls if path.endswith("klines")]
    assert {params["interval"] for params in klines} == set(MARKET_HISTORY_TIMEFRAMES)
    archive = ParquetOHLCVArchive(tmp_path / "market/spot")
    for timeframe in MARKET_HISTORY_TIMEFRAMES:
        assert archive.manifest("BTCUSDT", timeframe).gap_count == 0
    before = len(klines)
    resumed.sync_cycle(observed_at=NOW)
    assert (
        len([path for path, _ in transport.calls if path.endswith("klines")]) == before
    )
    assert _load(progress)["requested_start"] == "2026-09-01T00:00:00+00:00"
    assert second["execution_allowed"] is False


@pytest.mark.parametrize("long_backfill", [False, True])
def test_sync_finishes_symbol_streams_and_publishes_durable_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    long_backfill: bool,
) -> None:
    from types import SimpleNamespace

    elapsed = [0.0]
    monkeypatch.setattr(
        "ai4binance.data.market_history_continuous.time",
        SimpleNamespace(monotonic=lambda: elapsed[0]),
    )

    class DualUniverse:
        def __init__(self) -> None:
            self.calls = 0

        def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
            self.calls += 1
            return BinanceEligibleMarketSnapshot(
                spot_symbols=("ETHUSDT",), futures_symbols=("BTCUSDT",)
            )

    transport = Transport()
    universe_provider = DualUniverse()
    history = MarketHistorySynchronizer(
        universe_provider=universe_provider,  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", lambda _: b""),
        state_path=tmp_path / "state.json",
    )
    instance = ContinuousMarketHistory(
        history, transport, transport, initial_days=1, max_workers=1
    )
    markets: list[str] = []
    ready_symbols: list[tuple[str, str]] = []
    snapshot_markets: list[str] = []

    def observe_ready_symbol(
        market: str, symbol: str, _observed_at: datetime
    ) -> Mapping[str, object]:
        ready_symbols.append((market, symbol))
        return {
            "status": "CURRENT",
            "blockers": [],
            "candidate_count": 0,
            "generation_health": {
                "evaluated_attempt_count": 1,
                "rejected_attempt_count": 1,
                "rejected_by_stage": {"SIGNAL_QUALIFICATION": 1},
                "rejected_by_reason": {"SETUP_NOT_CONFIRMED": 1},
                "recent_rejections": [
                    {
                        "candidate_attempt_id": f"attempt:{market}:{symbol}",
                        "market": market,
                        "symbol": symbol,
                        "timeframe": "15m",
                        "observed_at": NOW.isoformat(),
                        "outcome": "NO_SETUP",
                        "failed_stage": "SIGNAL_QUALIFICATION",
                        "reason_codes": ["SETUP_NOT_CONFIRMED"],
                        "missing_fields": [],
                        "retryability": "RETRY_NEXT_CLOSED_CANDLE",
                        "execution_allowed": False,
                        "promotion_status": "RESEARCH_ONLY",
                        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    }
                ],
            },
        }

    instance.on_symbol_ready = observe_ready_symbol

    monkeypatch.setattr(
        instance, "_snapshots", lambda market, *args: snapshot_markets.append(market)
    )

    def collect(
        market: str,
        symbol: str,
        transport: object,
        now: datetime,
        *,
        kind: str,
        timeframe: str | None,
    ) -> dict[str, object]:
        del symbol, transport, now, kind, timeframe
        if long_backfill:
            elapsed[0] = 301.0
        markets.append(market)
        return {"status": "CURRENT"}

    monkeypatch.setattr(instance, "_collect_stream", collect)

    report = instance.sync_cycle(observed_at=NOW)

    assert markets[:1] == ["spot"]
    assert markets.count("spot") == 5
    assert markets.count("usd_m_futures") == 9
    assert snapshot_markets == (["spot", "usd_m_futures"] if long_backfill else [])
    assert report["completed_symbols"] == 2
    assert report["total_symbols"] == 2
    assert report["completed_streams"] == 14
    assert report["total_streams"] == 14
    assert report["completion_ratio"] == "1.000000"
    assert ready_symbols == [("SPOT", "ETHUSDT"), ("USD_M_FUTURES", "BTCUSDT")]
    assert report["opportunity_analysis_summary"] == {"CURRENT": 2}
    opportunity_projection = report["dashboard_opportunity_projection"]
    assert isinstance(opportunity_projection, Mapping)
    assert opportunity_projection["SPOT"]["status"] == "NO_TRADE"
    assert opportunity_projection["SPOT"]["analyzed_symbol_count"] == 1
    assert opportunity_projection["SPOT"]["no_opportunity_symbol_count"] == 1
    assert opportunity_projection["SPOT"]["rejected_attempt_count"] == 1
    assert opportunity_projection["SPOT"]["rejected_by_reason"] == {
        "SETUP_NOT_CONFIRMED": 1
    }
    assert opportunity_projection["SPOT"]["recent_rejections"][0]["symbol"] == (
        "ETHUSDT"
    )
    assert opportunity_projection["USD_M_FUTURES"]["status"] == "NO_TRADE"
    collector_coverage = report["collector_coverage"]
    assert isinstance(collector_coverage, Mapping)
    spot_coverage = collector_coverage["SPOT"]
    assert isinstance(spot_coverage, list)
    assert {row["timeframe"] for row in spot_coverage} == set(MARKET_HISTORY_TIMEFRAMES)
    assert all(row["current_count"] == 1 for row in spot_coverage)
    assert all(row["pending_count"] == 0 for row in spot_coverage)
    assert universe_provider.calls == (2 if long_backfill else 1)


def test_dashboard_opportunity_projection_does_not_equate_data_blocked_with_no_trade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    instance.on_symbol_ready = lambda *_: {
        "status": "DATA_BLOCKED",
        "blockers": ["OPPORTUNITY_DATA_UNAVAILABLE:5m"],
        "generation_health": {
            "evaluated_attempt_count": 1,
            "rejected_attempt_count": 1,
            "rejected_by_stage": {"DATA_QUALITY": 1},
            "rejected_by_reason": {"OPPORTUNITY_DATA_UNAVAILABLE:5m": 1},
            "recent_rejections": [],
        },
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    monkeypatch.setattr(
        instance, "_collect_stream", lambda *_args, **_kwargs: {"status": "CURRENT"}
    )

    report = instance.sync_cycle(observed_at=NOW)

    projection = report["dashboard_opportunity_projection"]
    assert isinstance(projection, Mapping)
    spot = projection["SPOT"]
    assert isinstance(spot, Mapping)
    assert spot["status"] == "DATA_UNAVAILABLE"
    assert spot["data_blocked_symbol_count"] == 1
    assert spot["no_opportunity_symbol_count"] == 0
    assert spot["rejected_attempt_count"] == 1
    assert spot["rejected_by_stage"] == {"DATA_QUALITY": 1}


def test_stream_plan_uses_each_native_price_candle_feed() -> None:
    spot_streams = ContinuousMarketHistory._collection_kinds("spot")
    futures_streams = ContinuousMarketHistory._collection_kinds("usd_m_futures")

    assert spot_streams == tuple(
        ("klines", timeframe) for timeframe in MARKET_HISTORY_TIMEFRAMES
    )
    assert futures_streams[:5] == spot_streams
    assert len(spot_streams) == 5
    assert len(futures_streams) == 9


def test_priority_symbols_precede_background_backfill(tmp_path: Path) -> None:
    instance = collector(tmp_path, Transport())
    instance.priority_symbols = ("HOTUSDT", "BTCUSDT")

    assert instance._prioritized_symbols(("0GUSDT", "BTCUSDT", "HOTUSDT")) == (
        "HOTUSDT",
        "BTCUSDT",
        "0GUSDT",
    )

    transport = Transport()
    streams = instance._interleaved_stream_work(
        (
            ("spot", "HOTUSDT", transport),
            ("usd_m_futures", "BTCUSDT", transport),
            ("spot", "0GUSDT", transport),
        )
    )
    leading_streams = [
        (market, symbol, kind, timeframe)
        for market, symbol, _, kind, timeframe in streams[:6]
    ]
    assert leading_streams == [
        ("spot", "HOTUSDT", "klines", "5m"),
        ("spot", "HOTUSDT", "klines", "15m"),
        ("spot", "HOTUSDT", "klines", "1h"),
        ("spot", "HOTUSDT", "klines", "4h"),
        ("spot", "HOTUSDT", "klines", "1d"),
        ("usd_m_futures", "BTCUSDT", "klines", "5m"),
    ]
    assert len(streams) == 19


def test_priority_depth_scope_does_not_subscribe_the_full_universe() -> None:
    class DepthUniverse:
        spot_symbols = ("HOTUSDT", "ETHUSDT")
        futures_symbols = ("BTCUSDT", "ETHUSDT")
        coin_m_symbols = ("BTCUSD_PERP",)

    assert _priority_depth_markets(
        DepthUniverse(),
        ("HOTUSDT", "BTCUSDT", "MISSING"),
        include_coin_m=True,
    ) == {
        "spot": ("HOTUSDT",),
        "usd_m_futures": ("BTCUSDT",),
        "coin_m_futures": (),
    }


def test_priority_depth_scope_falls_back_to_top_volume_per_primary_market() -> None:
    class DepthUniverse:
        spot_symbols = ("ETHUSDT", "BTCUSDT")
        futures_symbols = ("BTCUSDT", "ETHUSDT")
        coin_m_symbols: tuple[str, ...] = ()

    assert _priority_depth_markets(
        DepthUniverse(),
        ("HOTUSDT",),
        include_coin_m=False,
    ) == {
        "spot": ("ETHUSDT",),
        "usd_m_futures": ("BTCUSDT",),
    }


def test_opportunity_analysis_starts_after_native_timeframe_ingestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    instance.max_workers = 1
    calls: list[str | None] = []
    analyzed_after: list[int] = []

    def collect(
        *_args: object, timeframe: str | None, **_kwargs: object
    ) -> dict[str, object]:
        calls.append(timeframe)
        return {"status": "CURRENT"}

    def analyze(*_args: object) -> Mapping[str, object]:
        analyzed_after.append(len(calls))
        return {"status": "CURRENT", "blockers": []}

    monkeypatch.setattr(instance, "_collect_stream", collect)
    instance.on_symbol_ready = analyze

    instance.sync_cycle(observed_at=NOW)

    assert calls == list(MARKET_HISTORY_TIMEFRAMES)
    assert analyzed_after == [5]


def test_native_streams_are_the_canonical_dashboard_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    instance.max_workers = 1
    native_streams_started = Event()
    started: list[str | None] = []

    def collect(
        *_args: object, timeframe: str | None, **_kwargs: object
    ) -> dict[str, object]:
        started.append(timeframe)
        if timeframe == "1d":
            native_streams_started.set()
        return {"status": "CURRENT"}

    monkeypatch.setattr(instance, "_collect_stream", collect)
    instance.sync_cycle(observed_at=NOW)

    assert native_streams_started.is_set()
    assert started == list(MARKET_HISTORY_TIMEFRAMES)


def test_background_stream_plan_finishes_each_symbol_before_the_next(
    tmp_path: Path,
) -> None:
    instance = collector(tmp_path, Transport())
    transport = Transport()

    streams = instance._interleaved_stream_work(
        (
            ("spot", "AUSDT", transport),
            ("spot", "BUSDT", transport),
            ("usd_m_futures", "CUSDT", transport),
        )
    )

    assert [(market, symbol) for market, symbol, *_ in streams] == [
        *(("spot", "AUSDT"),) * len(MARKET_HISTORY_TIMEFRAMES),
        *(("spot", "BUSDT"),) * len(MARKET_HISTORY_TIMEFRAMES),
        *(("usd_m_futures", "CUSDT"),) * (len(MARKET_HISTORY_TIMEFRAMES) + 4),
    ]


def test_symbol_with_incomplete_stream_does_not_start_opportunity_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())
    observed: list[str] = []

    def observe_incomplete_symbol(
        _market: str, symbol: str, _observed_at: datetime
    ) -> Mapping[str, object]:
        observed.append(symbol)
        return {"status": "CURRENT"}

    instance.on_symbol_ready = observe_incomplete_symbol
    monkeypatch.setattr(
        instance,
        "_collect_stream",
        lambda *_args, **kwargs: {
            "status": "BACKFILLING" if kwargs.get("timeframe") == "5m" else "CURRENT"
        },
    )

    report = instance.sync_cycle(observed_at=NOW)

    assert observed == []
    assert report["opportunity_analysis_summary"] == {}
    blockers = report["blockers"]
    assert isinstance(blockers, list)
    assert "MARKET_DATA_BACKFILL_PENDING" in blockers


def test_opportunity_analysis_failure_is_visible_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())

    def fail(
        _market: str, _symbol: str, _observed_at: datetime
    ) -> Mapping[str, object]:
        raise OSError("private detail must not escape")

    instance.on_symbol_ready = fail
    monkeypatch.setattr(
        instance,
        "_collect_stream",
        lambda *_args, **_kwargs: {"status": "CURRENT"},
    )

    report = instance.sync_cycle(observed_at=NOW)

    assert report["status"] == "DEGRADED"
    blockers = report["blockers"]
    assert isinstance(blockers, list)
    assert "OPPORTUNITY_ANALYSIS_FAILURE" in blockers
    assert report["opportunity_analysis_summary"] == {"BLOCKED": 1}
    assert report["execution_allowed"] is False
    serialized = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert "private detail" not in serialized


def test_stream_failure_summary_uses_safe_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport())

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ValueError("collection progress exceeds the verified dataset: secret")

    monkeypatch.setattr(instance, "_candles", fail)

    report = instance.sync_cycle(observed_at=NOW)

    failures = report["stream_failure_summary"]
    assert isinstance(failures, dict)
    assert sum(failures.values()) == len(MARKET_HISTORY_TIMEFRAMES)
    assert all("PROGRESS_AHEAD_OF_VERIFIED_DATASET" in key for key in failures)
    assert "secret" not in (tmp_path / "state.json").read_text(encoding="utf-8")


def test_canonical_opportunity_pipeline_reuses_archive_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def refresh(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "quality": [
                {
                    "timeframe": timeframe,
                    "status": "CURRENT",
                }
                for timeframe in MARKET_HISTORY_TIMEFRAMES
            ],
            "candidates": [
                {
                    "market": "SPOT",
                    "symbol": "BTCUSDT",
                    "timeframe": "5m",
                    "direction": "BULLISH",
                    "side": "BUY",
                    "quantity": "1",
                    "status": "WATCHLIST",
                    "entry": "101",
                    "stop_loss": "98",
                    "tp1": "105",
                    "tp2": "108",
                    "tp3": "111",
                    "target_risk_reward": "2",
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    "blockers": ["LIVE_ORDER_BLOCKED"],
                },
                {"status": "WATCH_ONLY", "blockers": []},
            ],
            "generation_health": {
                "evaluated_attempt_count": 2,
                "published_opportunity_count": 1,
                "rejected_attempt_count": 1,
                "rejected_by_stage": {"SIGNAL_QUALIFICATION": 1},
                "rejected_by_reason": {"SETUP_NOT_CONFIRMED": 1},
                "recent_rejections": [],
            },
        }

    monkeypatch.setattr("ai4binance.cli.market_data.refresh_monitor", refresh)
    pipeline = _build_canonical_opportunity_pipeline(
        Settings(dataset_directory=tmp_path / "market"), tmp_path
    )

    spot = pipeline("SPOT", "BTCUSDT", NOW)
    futures = pipeline("USD_M_FUTURES", "BTCUSDT", NOW)

    assert spot["status"] == "CURRENT"
    assert spot["candidate_count"] == 2
    assert spot["dashboard_candidates"] == [
        {
            "timeframe": "5m",
            "direction": "BULLISH",
            "side": "BUY",
            "quantity": "1",
            "status": "WATCHLIST",
            "entry": "101",
            "stop_loss": "98",
            "tp1": "105",
            "tp2": "108",
            "tp3": "111",
            "target_risk_reward": "2",
            "blockers": ["LIVE_ORDER_BLOCKED"],
            "market": "SPOT",
            "symbol": "BTCUSDT",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    ]
    assert spot["decision_blockers"] == ["LIVE_ORDER_BLOCKED"]
    generation_health = cast(Mapping[str, object], spot["generation_health"])
    assert generation_health["rejected_by_reason"] == {"SETUP_NOT_CONFIRMED": 1}
    assert spot["compute_profile"] == "CPU_REFERENCE"
    assert spot["pipeline_mode"] == "OVERLAPPED_WITH_MARKET_DOWNLOAD"
    assert spot["execution_allowed"] is False
    assert calls == [
        {
            "market": "SPOT",
            "symbol": "BTCUSDT",
            "now": NOW,
            "minimum_candles": 200,
            "candle_limit": 250,
            "timeframes": MARKET_HISTORY_TIMEFRAMES,
        }
    ]
    assert futures["status"] == "DELEGATED"
    assert futures["owner"] == "futures-multitf"
    assert futures["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_dashboard_refresh_request_is_coalesced_and_other_symbol_is_busy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "market-history-refresh-request.json"
    first = enqueue_market_history_refresh_request(
        path,
        market="SPOT",
        symbol="BTCUSDT",
        eligible_symbols=("BTCUSDT",),
        requested_at=NOW,
    )
    duplicate = enqueue_market_history_refresh_request(
        path,
        market="SPOT",
        symbol="BTCUSDT",
        eligible_symbols=("BTCUSDT",),
        requested_at=NOW + timedelta(seconds=1),
    )
    busy = enqueue_market_history_refresh_request(
        path,
        market="SPOT",
        symbol="ETHUSDT",
        eligible_symbols=("BTCUSDT", "ETHUSDT"),
        requested_at=NOW + timedelta(seconds=1),
    )
    assert first["state"] == "PENDING"
    assert duplicate["request_id"] == first["request_id"]
    assert busy["state"] == "BUSY"
    assert busy["execution_allowed"] is False
    assert busy["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_dashboard_refresh_request_is_completed_by_the_canonical_collector(
    tmp_path: Path,
) -> None:
    instance = collector(tmp_path, Transport())
    instance.minimum_candles = 1
    instance.pages_per_stream = 6
    ready_at = NOW.replace(hour=23, minute=59)
    request_path = (tmp_path / "market-history-refresh-request.json").resolve()
    instance.refresh_request_path = request_path
    request = enqueue_market_history_refresh_request(
        request_path,
        market="SPOT",
        symbol="BTCUSDT",
        eligible_symbols=("BTCUSDT",),
        requested_at=ready_at,
    )
    report = instance.sync_cycle(observed_at=ready_at)
    status = market_history_refresh_status(request_path)
    completed_streams = report["completed_streams"]
    assert isinstance(completed_streams, int)
    assert completed_streams >= 1
    assert status["request_id"] == request["request_id"]
    assert status["state"] == "DATA_READY", status
    assert status["execution_allowed"] is False
    assert status["promotion_status"] == "RESEARCH_ONLY"
    assert status["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_dashboard_request_preempts_the_bounded_background_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late dashboard request must not wait for every queued symbol."""

    class TwoSymbolUniverse:
        def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
            return BinanceEligibleMarketSnapshot(
                spot_symbols=("BTCUSDT", "ETHUSDT"), futures_symbols=()
            )

    history = MarketHistorySynchronizer(
        universe_provider=TwoSymbolUniverse(),  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", lambda _: b""),
        state_path=tmp_path / "state.json",
    )
    request_path = (tmp_path / "market-history-refresh-request.json").resolve()
    instance = ContinuousMarketHistory(
        history,
        Transport(),
        Transport(),
        initial_days=1,
        max_workers=1,
        refresh_request_path=request_path,
    )
    first_started = Event()
    release_first = Event()
    calls: list[tuple[str, str, str, str | None]] = []

    def collect(
        market: str,
        symbol: str,
        transport: object,
        now: datetime,
        *,
        kind: str,
        timeframe: str | None,
    ) -> dict[str, object]:
        del transport, now
        calls.append((market, symbol, kind, timeframe))
        if len(calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=5)
        return {"status": "CURRENT"}

    monkeypatch.setattr(instance, "_collect_stream", collect)
    worker = Thread(target=lambda: instance.sync_cycle(observed_at=NOW))
    worker.start()
    assert first_started.wait(timeout=5)
    # With one worker, an unbounded submit implementation can enqueue all
    # streams before this request exists. The bounded queue can now promote it.
    enqueue_market_history_refresh_request(
        request_path,
        market="SPOT",
        symbol="ETHUSDT",
        eligible_symbols=("BTCUSDT", "ETHUSDT"),
        requested_at=NOW,
    )
    release_first.set()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert calls[0][1] == "BTCUSDT"
    assert calls[1][1] == "ETHUSDT"
    assert market_history_refresh_status(request_path)["state"] == "DATA_BLOCKED"


def test_dashboard_refresh_request_rejects_ineligible_symbol(tmp_path: Path) -> None:
    result = enqueue_market_history_refresh_request(
        tmp_path / "market-history-refresh-request.json",
        market="SPOT",
        symbol="ETHUSDT",
        eligible_symbols=("BTCUSDT",),
        requested_at=NOW,
    )
    assert result["state"] == "DATA_BLOCKED"
    assert result["blockers"] == ["MARKET_HISTORY_REFRESH_REQUEST_INELIGIBLE"]
    assert result["execution_allowed"] is False


def test_long_shutdown_does_not_slide_requested_start_forward(tmp_path: Path) -> None:
    transport = Transport()
    instance = collector(tmp_path, transport, pages=1)
    instance._candles("spot", "BTCUSDT", "klines", transport, NOW)
    progress = tmp_path / "market/spot/BTCUSDT/5m/collection-progress.json"
    saved = _load(progress)
    collector(tmp_path, transport, pages=1)._candles(
        "spot", "BTCUSDT", "klines", transport, NOW + timedelta(days=45)
    )
    assert _load(progress)["requested_start"] == saved["requested_start"]
    assert transport.calls[-1][1]["startTime"] == int(
        datetime.fromisoformat(str(saved["next_at"])).timestamp() * 1000
    )


def test_candle_progress_extends_an_older_short_bootstrap_without_data_loss(
    tmp_path: Path,
) -> None:
    transport = Transport()
    short_window = collector(tmp_path, transport, pages=1)
    short_window._candles("spot", "BTCUSDT", "klines", transport, NOW)
    progress = tmp_path / "market/spot/BTCUSDT/5m/collection-progress.json"
    extended_window = ContinuousMarketHistory(
        short_window.history, transport, transport, initial_days=2, pages_per_stream=1
    )

    extended_window._candles("spot", "BTCUSDT", "klines", transport, NOW)

    state = _load(progress)
    assert state["requested_start"] == "2026-08-31T00:00:00+00:00"
    assert state["coverage_extended_at"] == NOW.isoformat()


@pytest.mark.parametrize(
    "fault", ["gap", "duplicate", "future", "negative_volume", "short", "nan"]
)
def test_invalid_pages_fail_closed(fault: str) -> None:
    start = NOW - timedelta(minutes=3)
    stamp = int(start.timestamp() * 1000)
    rows: list[object] = [row(stamp), row(stamp + 60000)]
    if fault == "gap":
        rows[1] = row(stamp + 120000)
    elif fault == "duplicate":
        rows[1] = row(stamp)
    elif fault == "future":
        rows[1] = row(int(NOW.timestamp() * 1000))
    elif fault == "short":
        rows[1] = [stamp]
    else:
        invalid = row(stamp + 60000)
        invalid[5] = "-1" if fault == "negative_volume" else "NaN"
        rows[1] = invalid
    with pytest.raises(ValueError, match="kline"):
        ContinuousMarketHistory._parse_rows(rows, start, NOW)


def test_corrupt_progress_is_reported_without_reset(tmp_path: Path) -> None:
    transport = Transport()
    instance = collector(tmp_path, transport)
    progress = tmp_path / "market/spot/BTCUSDT/5m/collection-progress.json"
    _save(
        progress,
        {
            "requested_start": NOW.isoformat(),
            "next_at": (NOW + timedelta(days=1)).isoformat(),
        },
    )
    report = instance.sync_cycle(observed_at=NOW)
    assert isinstance(report["blockers"], list)
    assert "MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE" in report["blockers"]
    assert not any(
        path.endswith("klines") and params["interval"] == "5m"
        for path, params in transport.calls
    )


def test_rate_limit_stops_following_network_requests(tmp_path: Path) -> None:
    class Limited:
        calls = 0

        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            self.calls += 1
            raise ExchangeHttpError("public Binance HTTP 429")

    limited = Limited()
    transport = MeteredPublicTransport(limited, tmp_path, sleeper=lambda delay: None)
    for _ in range(3):
        with pytest.raises(ExchangeHttpError):
            transport.get_json("/fapi/v1/klines")
    assert limited.calls == 1


def test_exchange_info_configures_shared_budget_below_declared_weight_limit(
    tmp_path: Path,
) -> None:
    class ExchangeInfo:
        def get_json(
            self,
            path: str,
            params: Mapping[str, str | int] | None = None,
        ) -> object:
            del params
            assert path == "/api/v3/exchangeInfo"
            return {
                "rateLimits": [
                    {
                        "rateLimitType": "REQUEST_WEIGHT",
                        "interval": "MINUTE",
                        "intervalNum": 1,
                        "limit": 6000,
                    },
                    {
                        "rateLimitType": "REQUEST_WEIGHT",
                        "interval": "SECOND",
                        "intervalNum": 10,
                        "limit": 800,
                    },
                ]
            }

    budget = PublicRequestBudget(seconds_per_weight=0.05)
    transport = MeteredPublicTransport(ExchangeInfo(), tmp_path, budget=budget)

    transport.get_json("/api/v3/exchangeInfo")

    assert budget.seconds_per_weight == pytest.approx(10 / (800 * 0.70))


def test_stored_raw_candles_retain_trade_and_taker_fields(tmp_path: Path) -> None:
    transport = Transport()
    collector(tmp_path, transport, pages=1)._candles(
        "spot", "BTCUSDT", "klines", transport, NOW
    )
    sources = list((tmp_path / "market/spot/BTCUSDT/sources").glob("*.json"))
    assert len(sources) == 1
    rows = _load(sources[0])["rows"]
    assert isinstance(rows, list)
    assert rows[0][7:11] == ["101", 2, "0.5", "50.5"]


def test_unicode_exchange_identity_is_preserved_without_path_traversal(
    tmp_path: Path,
) -> None:
    symbol = "\u5e01\u5b89\u4eba\u751fUSDT"
    snapshot = BinanceEligibleMarketSnapshot(spot_symbols=(symbol,), futures_symbols=())
    transport = Transport()
    instance = collector(tmp_path, transport, pages=1)
    result = instance._candles(
        "spot", snapshot.spot_symbols[0], "klines", transport, NOW
    )
    assert result["status"] == "CURRENT"
    archive = ParquetOHLCVArchive(tmp_path / "market/spot")
    assert archive.manifest(symbol, "5m").symbol == symbol
    with pytest.raises(ValueError, match="alphanumeric"):
        archive.manifest("../outside", "5m")
    with pytest.raises(ValueError, match="identity"):
        BinanceEligibleMarketSnapshot(
            spot_symbols=("x/../BTCUSDT",), futures_symbols=()
        )


def test_funding_page_limit_advances_only_after_last_verified_event(
    tmp_path: Path,
) -> None:
    class FundingTransport(Transport):
        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            assert params is not None
            start = int(params["startTime"])
            return [
                {
                    "symbol": "BTCUSDT",
                    "fundingTime": start + index * 60000,
                    "fundingRate": "0.0001",
                }
                for index in range(500)
            ]

    transport = FundingTransport()
    instance = collector(tmp_path, transport)
    result = instance._details("BTCUSDT", "funding", NOW)
    assert result["status"] == "BACKFILLING"
    expected = (
        NOW.replace(hour=0, minute=0)
        - timedelta(days=1)
        + timedelta(minutes=499, milliseconds=1)
    )
    assert result["next_at"] == expected.isoformat()


def test_open_interest_short_page_does_not_claim_the_unobserved_tail(
    tmp_path: Path,
) -> None:
    class InterestTransport(Transport):
        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            assert params is not None
            return [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": int(params["startTime"]),
                    "sumOpenInterest": "12",
                    "sumOpenInterestValue": "1200",
                }
            ]

    transport = InterestTransport()
    result = collector(tmp_path, transport)._details("BTCUSDT", "open_interest", NOW)
    assert result["status"] == "BACKFILLING"
    assert result["next_at"] == "2026-09-01T00:05:00+00:00"


def test_missing_old_open_interest_archive_retains_offline_gap(tmp_path: Path) -> None:
    transport = Transport()
    instance = collector(tmp_path, transport)
    path = (
        tmp_path
        / "market/usd_m_futures/BTCUSDT/details/open_interest/collection-progress.json"
    )
    start = NOW - timedelta(days=45)
    _save(path, {"requested_start": start.isoformat(), "next_at": start.isoformat()})
    result = instance._details("BTCUSDT", "open_interest", NOW)
    assert result["status"] == "UNAVAILABLE"
    assert _load(path)["next_at"] == start.isoformat()
    assert transport.calls == []


def test_compressed_history_bootstrap_preserves_checksum_and_all_timeframes(
    tmp_path: Path,
) -> None:
    start = NOW.replace(hour=0, minute=0) - timedelta(days=1)
    csv_text = "\n".join(
        ",".join(
            str(value)
            for value in row(int((start + timedelta(minutes=index)).timestamp() * 1000))
        )
        for index in range(1440)
    )
    cache, calls = archive_cache(tmp_path / "sources", csv_text)
    transport = Transport()
    history = MarketHistorySynchronizer(
        Universe(),  # type: ignore[arg-type]
        tmp_path / "market",
        cache,
        tmp_path / "state.json",
    )
    instance = ContinuousMarketHistory(
        history, transport, transport, initial_days=1, pages_per_stream=1
    )
    result = instance._candles(
        "spot", "BTCUSDT", "klines", transport, NOW, timeframe="5m"
    )
    assert result["status"] == "CURRENT"
    assert transport.calls
    assert calls == []
    assert instance.archive_request_count == 0
    manifest = ParquetOHLCVArchive(tmp_path / "market/spot").manifest("BTCUSDT", "5m")
    assert manifest.gap_count == 0
    requested_start = start.replace(second=0, microsecond=0)
    assert all(
        int(params["startTime"]) >= int(requested_start.timestamp() * 1000)
        for path, params in transport.calls
        if path.endswith("klines")
    )


def test_current_month_five_minute_bootstrap_uses_bounded_rest_tail(
    tmp_path: Path,
) -> None:
    now = NOW.replace(hour=0, minute=10)
    start = now.replace(hour=0, minute=0) - timedelta(days=1)
    csv_text = "\n".join(
        ",".join(
            str(value)
            for value in row(
                int((start + timedelta(minutes=index * 5)).timestamp() * 1000),
                300_000,
            )
        )
        for index in range(288)
    )
    cache, calls = archive_cache(tmp_path / "sources", csv_text)
    transport = Transport()
    history = MarketHistorySynchronizer(
        Universe(),  # type: ignore[arg-type]
        tmp_path / "market",
        cache,
        tmp_path / "state.json",
    )
    instance = ContinuousMarketHistory(
        history, transport, transport, initial_days=1, pages_per_stream=1
    )

    result = instance._candles(
        "spot", "BTCUSDT", "klines", transport, now, timeframe="5m"
    )

    assert result["status"] == "CURRENT"
    assert calls == []
    rest = [params for path, params in transport.calls if path.endswith("klines")]
    assert rest
    assert {params["interval"] for params in rest} == {"5m"}
    assert all(
        int(params["startTime"]) >= int(start.timestamp() * 1000) for params in rest
    )
    assert (
        ParquetOHLCVArchive(tmp_path / "market/spot")
        .manifest("BTCUSDT", "5m")
        .gap_count
        == 0
    )


def test_rest_pages_are_committed_as_one_archive_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = collector(tmp_path, Transport(), pages=3)
    instance.initial_days = 2
    updates = 0
    original_update = ParquetOHLCVArchive.update

    def update(*args: object, **kwargs: object) -> object:
        nonlocal updates
        updates += 1
        return original_update(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ParquetOHLCVArchive, "update", update)

    result = instance._candles(
        "spot", "BTCUSDT", "klines", instance.spot, NOW, timeframe="5m"
    )

    assert result["status"] == "CURRENT"
    assert updates == 1
    assert (
        ParquetOHLCVArchive(tmp_path / "market/spot")
        .manifest("BTCUSDT", "5m")
        .row_count
        == 576
    )


def test_unclosed_tail_and_future_cursor_are_repaired_to_closed_boundary(
    tmp_path: Path,
) -> None:
    instance = collector(tmp_path, Transport())
    archive = ParquetOHLCVArchive(tmp_path / "market/spot")
    closed = NOW - timedelta(hours=1, minutes=2)
    unclosed = NOW.replace(minute=0)
    archive.update(
        "BTCUSDT",
        "1h",
        (
            OHLCVCandle(closed, *(Decimal("1") for _ in range(5))),
            OHLCVCandle(unclosed, *(Decimal("1") for _ in range(5))),
        ),
        source="BINANCE_PUBLIC_REST_1H",
    )
    progress = tmp_path / "market/spot/BTCUSDT/1h/collection-progress.json"
    _save(
        progress,
        {
            "requested_start": (NOW - timedelta(days=1, minutes=2)).isoformat(),
            "next_at": (unclosed + timedelta(hours=1)).isoformat(),
        },
    )

    result = instance._candles(
        "spot", "BTCUSDT", "klines", instance.spot, NOW, timeframe="1h"
    )

    assert result["status"] == "CURRENT"
    assert archive.read("BTCUSDT", "1h") == (
        OHLCVCandle(closed, *(Decimal("1") for _ in range(5))),
    )
    assert _load(progress)["next_at"] == unclosed.isoformat()


def test_legacy_open_candle_is_replaced_only_with_temporal_proof(
    tmp_path: Path,
) -> None:
    transport = Transport()
    instance = collector(tmp_path, transport)
    archive = ParquetOHLCVArchive(tmp_path / "market/spot")
    closed = NOW - timedelta(minutes=32)
    legacy_open = NOW - timedelta(minutes=17)
    archive.update(
        "BTCUSDT",
        "15m",
        (
            OHLCVCandle(closed, *(Decimal("1") for _ in range(5))),
            OHLCVCandle(legacy_open, *(Decimal("1") for _ in range(5))),
        ),
        source="BINANCE_PUBLIC_REST_15M",
        generated_at=legacy_open + timedelta(minutes=7),
    )
    progress = tmp_path / "market/spot/BTCUSDT/15m/collection-progress.json"
    _save(
        progress,
        {
            "requested_start": (NOW - timedelta(days=1, minutes=2)).isoformat(),
            "next_at": NOW.replace(minute=0).isoformat(),
            "first_available_at": closed.isoformat(),
        },
    )

    result = instance._candles(
        "spot", "BTCUSDT", "klines", transport, NOW, timeframe="15m"
    )

    repaired = archive.read("BTCUSDT", "15m")
    assert result["status"] == "CURRENT"
    assert len(repaired) == 2
    assert repaired[-1].timestamp == legacy_open
    assert repaired[-1].close == Decimal("101")
    assert _load(progress)["unclosed_candle_repaired_at"] == NOW.isoformat()


def test_direct_timeframe_bootstrap_uses_its_own_closed_candle_window(
    tmp_path: Path,
) -> None:
    instance = ContinuousMarketHistory(
        collector(tmp_path, Transport()).history,
        Transport(),
        Transport(),
        initial_days=90,
        minimum_candles=200,
    )

    assert instance._candle_initial_start(NOW, timedelta(minutes=5)) == (
        datetime(2026, 6, 4, 0, 0, tzinfo=UTC)
    )
    assert instance._candle_initial_start(NOW, timedelta(days=1)) == (
        NOW.replace(hour=0, minute=0) - timedelta(days=201)
    )


def test_partial_first_month_reuses_one_complete_monthly_archive() -> None:
    start = datetime(2026, 6, 16, tzinfo=UTC)
    key, archive_end = ContinuousMarketHistory._vision_kline_key(
        "spot",
        "BTCUSDT",
        "klines",
        "5m",
        start,
        datetime(2026, 9, 14, tzinfo=UTC),
    )

    assert key.endswith("BTCUSDT-5m-2026-06.zip")
    assert archive_end == datetime(2026, 7, 1, tzinfo=UTC)


def test_native_vision_progress_does_not_write_other_timeframes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    verified_keys: list[str] = []

    class SourceCache:
        def verified(self, key: str, *, kind: str) -> tuple[object, bytes]:
            del kind
            verified_keys.append(key)
            return (
                SimpleNamespace(
                    sha256=hashlib.sha256(key.encode()).hexdigest(),
                    network_request_count=0,
                    downloaded_bytes=0,
                ),
                b"fixture",
            )

    class Archive:
        def update(
            self,
            symbol: str,
            timeframe: str,
            candles: tuple[OHLCVCandle, ...],
            *,
            source: str,
            generated_at: datetime,
            replace_conflicts_from_sources: tuple[str, ...] = (),
        ) -> object:
            del (
                symbol,
                timeframe,
                source,
                generated_at,
                replace_conflicts_from_sources,
            )
            return SimpleNamespace(last_timestamp=candles[-1].timestamp.isoformat())

    history = SimpleNamespace(source_cache=SourceCache())
    instance = ContinuousMarketHistory(
        history,  # type: ignore[arg-type]
        Transport(),
        Transport(),
    )

    def parsed(
        key: str,
        payload: bytes,
        start: datetime,
        end: datetime,
        *,
        interval: timedelta,
    ) -> tuple[OHLCVCandle, ...]:
        del key, payload
        return tuple(
            OHLCVCandle(
                timestamp=timestamp,
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
            )
            for timestamp in (start, end - interval)
        )

    monkeypatch.setattr(instance, "_parse_vision_candles", parsed)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 15, tzinfo=UTC)
    progress_path = tmp_path / "collection-progress.json"
    state: dict[str, object] = {
        "requested_start": start.isoformat(),
        "next_at": start.isoformat(),
    }

    cursor, unavailable = instance._vision_history(
        market="spot",
        symbol="BTCUSDT",
        kind="klines",
        timeframe="5m",
        archive=Archive(),  # type: ignore[arg-type]
        dataset_symbol="BTCUSDT",
        state=state,
        progress_path=progress_path,
        cursor=start,
        closed_history_end=end,
        interval=timedelta(minutes=5),
        now=end,
    )

    assert unavailable is None
    assert cursor == start
    assert verified_keys == []


def test_direct_native_write_does_not_modify_another_timeframe(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "market/spot")
    start = datetime(2026, 9, 1, tzinfo=UTC)
    direct = OHLCVCandle(
        timestamp=start,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("50"),
    )
    archive.update("BTCUSDT", "5m", (direct,), source="BINANCE_DIRECT_5M")
    native_fifteen_minute = tuple(
        OHLCVCandle(
            timestamp=start + timedelta(minutes=index),
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("1"),
            close=Decimal("2"),
            volume=Decimal("1"),
        )
        for index in range(1)
    )

    archive.update(
        "BTCUSDT",
        "15m",
        native_fifteen_minute,
        source="BINANCE_VISION_15M_SHA256:test",
    )

    assert archive.read("BTCUSDT", "5m") == (direct,)


def archive_cache(
    root: Path, csv_text: str
) -> tuple[BinanceVisionArchiveCache, list[str]]:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fixture.csv", csv_text)
    zipped = stream.getvalue()
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if url.endswith("CHECKSUM"):
            return (hashlib.sha256(zipped).hexdigest() + "  fixture.zip").encode()
        return zipped

    return BinanceVisionArchiveCache(root, fetch), calls


def test_offline_open_interest_recovers_from_verified_daily_metrics(
    tmp_path: Path,
) -> None:
    start = (NOW - timedelta(days=45)).replace(hour=0, minute=0)
    csv_text = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
        + "\n".join(
            f"{(start + timedelta(minutes=index * 5)).strftime('%Y-%m-%d %H:%M:%S')},"
            "BTCUSDT,10,1000"
            for index in range(288)
        )
    )
    cache, calls = archive_cache(tmp_path / "sources", csv_text)
    transport = Transport()
    history = MarketHistorySynchronizer(
        Universe(),  # type: ignore[arg-type]
        tmp_path / "market",
        cache,
        tmp_path / "state.json",
    )
    instance = ContinuousMarketHistory(history, transport, transport)
    progress = (
        tmp_path
        / "market/usd_m_futures/BTCUSDT/details/open_interest/collection-progress.json"
    )
    _save(
        progress, {"requested_start": start.isoformat(), "next_at": start.isoformat()}
    )
    result = instance._details("BTCUSDT", "open_interest", NOW)
    assert result["next_at"] == (start + timedelta(days=1)).isoformat()
    assert result["status"] == "BACKFILLING"
    assert len(calls) == 2
    assert transport.calls == []


def test_status_does_not_report_stale_collection_as_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "status.json"
    _save(
        path,
        {
            "schema_version": "2.0",
            "observed_at": "2020-01-01T00:00:00+00:00",
            "status": "READY",
            "blockers": [],
        },
    )
    monkeypatch.setenv("AI4BINANCE_MARKET_HISTORY_STATE_PATH", str(path))
    assert market_data_main(["status"]) == 2
    assert "MARKET_HISTORY_STATE_STALE" in capsys.readouterr().out


def test_network_outage_does_not_retry_every_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Offline:
        calls = 0

        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            self.calls += 1
            raise ExchangeTransportError("public network unavailable")

    offline = Offline()
    transport = MeteredPublicTransport(offline, tmp_path, sleeper=lambda delay: None)
    with pytest.raises(ExchangeTransportError, match="unavailable"):
        transport.get_json("/api/v3/klines")
    with pytest.raises(ExchangeHttpError, match="cooldown"):
        transport.get_json("/api/v3/klines")
    assert offline.calls == 1

    calls: list[object] = []

    def failed_open(request: object, **kwargs: object) -> object:
        calls.append(request)
        raise OSError("offline fixture")

    monkeypatch.setattr("urllib.request.urlopen", failed_open)
    cache = BinanceVisionArchiveCache.with_network(tmp_path / "vision")
    url = "https://data.binance.vision/data/spot/daily/fixture.zip"
    with pytest.raises(OSError, match="offline fixture"):
        cache.fetch(url)
    with pytest.raises(OSError, match="cooling down"):
        cache.fetch(url)
    assert len(calls) == 1


def test_dashboard_candidate_projection_filters_and_sanitizes_fields() -> None:
    from ai4binance.cli.market_data import _dashboard_candidate_projection

    candidates: list[object] = [
        "not-a-mapping",
        {
            "market": "SPOT",
            "symbol": "ETHUSDT",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        {
            "market": "SPOT",
            "symbol": "BTCUSDT",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "direction": "BULLISH",
            "side": "BUY",
            "quantity": "1",
            "status": "WATCHLIST",
            "entry": "101",
            "stop_loss": "98",
            "tp1": "105",
            "tp2": "108",
            "tp3": "111",
            "leverage": 2.0,
            "target_risk_reward": "2",
            "blockers": [7],
        },
    ]

    projected = _dashboard_candidate_projection(
        candidates, market="SPOT", symbol="BTCUSDT"
    )

    assert projected == [
        {
            "direction": "BULLISH",
            "side": "BUY",
            "quantity": "1",
            "status": "WATCHLIST",
            "entry": "101",
            "stop_loss": "98",
            "tp1": "105",
            "tp2": "108",
            "tp3": "111",
            "target_risk_reward": "2",
            "leverage": 2.0,
            "blockers": ["CANDIDATE_BLOCKERS_UNAVAILABLE"],
            "market": "SPOT",
            "symbol": "BTCUSDT",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    ]


def test_canonical_opportunity_pipeline_validates_time_and_busy_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import market_data

    pipeline = _build_canonical_opportunity_pipeline(
        Settings(dataset_directory=tmp_path / "market"), tmp_path
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        pipeline("SPOT", "BTCUSDT", datetime(2026, 9, 2))

    class BusyLease:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> None:
            raise RuntimeError("runtime instance is already active")

        def __exit__(self, *_args: object) -> None:
            pass

    monkeypatch.setattr(market_data, "SingleInstanceLease", BusyLease)
    coalesced = pipeline("SPOT", "BTCUSDT", NOW)
    assert coalesced["status"] == "COALESCED"

    class BrokenLease(BusyLease):
        def __enter__(self) -> None:
            raise RuntimeError("unexpected lease failure")

    monkeypatch.setattr(market_data, "SingleInstanceLease", BrokenLease)
    with pytest.raises(RuntimeError, match="unexpected lease failure"):
        pipeline("SPOT", "BTCUSDT", NOW)


def test_canonical_opportunity_pipeline_fails_closed_for_malformed_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai4binance.cli.market_data.refresh_monitor",
        lambda *_args, **_kwargs: {"candidates": (), "quality": ()},
    )
    pipeline = _build_canonical_opportunity_pipeline(
        Settings(dataset_directory=tmp_path / "market"), tmp_path
    )

    result = pipeline("SPOT", "BTCUSDT", NOW)

    assert result["status"] == "DATA_BLOCKED"
    assert result["candidate_count"] == 0
    assert result["blockers"] == [
        f"OPPORTUNITY_DATA_UNAVAILABLE:{timeframe}"
        for timeframe in MARKET_HISTORY_TIMEFRAMES
    ]


def _market_data_cli_settings(tmp_path: Path) -> Settings:
    from types import SimpleNamespace

    return cast(
        Settings,
        SimpleNamespace(
            market_history_initial_days=30,
            market_history_pages_per_stream=1,
            market_history_max_workers=1,
            minimum_closed_candles=21,
            market_history_live_interval_seconds=30,
            market_history_state_path=tmp_path / "state.json",
            market_history_opportunity_workers=1,
            market_depth_enabled=True,
            dataset_directory=tmp_path / "market",
            symbol="BTCUSDT",
            fixed_symbols=("ETHUSDT",),
            priority_watchlist=("BTCUSDT",),
            candle_limit=30,
        ),
    )


def test_market_history_commands_cover_sync_status_and_invalid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dataclasses import dataclass
    from types import SimpleNamespace

    from ai4binance.cli import market_data

    state_path = tmp_path / "state.json"
    synchronizer = SimpleNamespace(
        state_path=state_path,
        archive_root=tmp_path / "archive",
        universe_provider=SimpleNamespace(
            spot_transport="spot",
            futures_transport="futures",
            coin_m_transport=None,
        ),
        sync_day=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        market_data, "build_market_history_synchronizer", lambda _settings: synchronizer
    )

    class Continuous:
        def __init__(self, **kwargs: object) -> None:
            self.spot = kwargs["spot"]
            self.futures = kwargs["futures"]
            self.coin_m = kwargs["coin_m"]

        def sync_cycle(self, **_kwargs: object) -> dict[str, object]:
            return {"blockers": []}

    monkeypatch.setattr(market_data, "ContinuousMarketHistory", Continuous)
    monkeypatch.setattr(market_data, "SingleInstanceLease", lambda _path: nullcontext())
    settings = _market_data_cli_settings(tmp_path)

    state_path.write_text("[]", encoding="utf-8")
    assert (
        market_data.run_market_history_command(
            "market-history-status", settings, as_of=None, max_cycles=None
        )
        == 2
    )
    assert "MARKET_HISTORY_STATE_UNAVAILABLE" in capsys.readouterr().out

    assert (
        market_data.run_market_history_command(
            "market-history-sync", settings, as_of=None, max_cycles=None
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["blockers"] == []

    @dataclass
    class Report:
        blockers: tuple[str, ...]
        downloaded_bytes: int = 10
        network_request_count: int = 1

    synchronizer.sync_day = lambda *_args, **_kwargs: Report(())
    assert (
        market_data.run_market_history_command(
            "market-history-sync", settings, as_of="2026-09-02", max_cycles=None
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "READY"

    synchronizer.sync_day = lambda *_args, **_kwargs: Report(("SOURCE_UNAVAILABLE",))
    assert (
        market_data.run_market_history_command(
            "market-history-sync", settings, as_of="2026-09-02", max_cycles=None
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "DEGRADED"

    with pytest.raises(ValueError, match="unsupported market history command"):
        market_data.run_market_history_command(
            "unknown", settings, as_of=None, max_cycles=None
        )
    assert market_data._exclusive_as_of("2026-09-03").isoformat() == "2026-09-03"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        market_data._exclusive_as_of("03-09-2026")


def test_market_history_daemon_starts_depth_and_reports_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace

    from ai4binance.cli import market_data

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"blockers": []}), encoding="utf-8")
    universe = SimpleNamespace(
        blockers=(),
        spot_symbols=("BTCUSDT",),
        futures_symbols=("BTCUSDT",),
        coin_m_symbols=("BTCUSDT",),
    )
    synchronizer = SimpleNamespace(
        state_path=state_path,
        archive_root=tmp_path / "archive",
        universe_provider=SimpleNamespace(
            spot_transport="spot",
            futures_transport="futures",
            coin_m_transport="coin-m",
        ),
        _eligible_universe=lambda _now: universe,
    )
    monkeypatch.setattr(
        market_data, "build_market_history_synchronizer", lambda _settings: synchronizer
    )

    class Continuous:
        spot = "spot"
        futures = "futures"
        coin_m = "coin-m"

        def __init__(self, **_kwargs: object) -> None:
            pass

        def sync_cycle(self, **_kwargs: object) -> dict[str, object]:
            return {"blockers": []}

        def record_recoverable_cycle_failure(self, *_args: object) -> None:
            pass

    depth_events: list[object] = []

    class Depth:
        def __init__(self, _root: Path, transports: object) -> None:
            depth_events.append(transports)

        def start(self, markets: object) -> None:
            depth_events.append(markets)

        def close(self) -> None:
            depth_events.append("closed")

    class Supervisor:
        def __init__(self, **kwargs: object) -> None:
            self.cycle = cast(Callable[[datetime], object], kwargs["cycle"])

        def run(self, *, max_cycles: int | None) -> int:
            assert max_cycles == 1
            self.cycle(NOW)
            return 1

    monkeypatch.setattr(market_data, "ContinuousMarketHistory", Continuous)
    monkeypatch.setattr(market_data, "MarketDepthCollector", Depth)
    monkeypatch.setattr(market_data, "MarketHistorySupervisor", Supervisor)

    assert (
        market_data.run_market_history_command(
            "market-history-daemon",
            _market_data_cli_settings(tmp_path),
            as_of=None,
            max_cycles=1,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "STOPPED"
    assert payload["completed_cycles"] == 1
    assert depth_events[-1] == "closed"
    assert depth_events[1] == {
        "spot": ("BTCUSDT",),
        "usd_m_futures": ("BTCUSDT",),
        "coin_m_futures": ("BTCUSDT",),
    }


@pytest.mark.parametrize(
    ("message", "blocker"),
    [
        ("runtime instance is already active", "MARKET_HISTORY_ALREADY_RUNNING"),
        ("unexpected runtime failure", "MARKET_HISTORY_RUNTIME_FAILURE"),
    ],
)
def test_market_history_daemon_maps_runtime_failures_to_safe_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    message: str,
    blocker: str,
) -> None:
    from types import SimpleNamespace

    from ai4binance.cli import market_data

    synchronizer = SimpleNamespace(
        state_path=tmp_path / "state.json",
        archive_root=tmp_path / "archive",
        universe_provider=SimpleNamespace(
            spot_transport="spot",
            futures_transport="futures",
            coin_m_transport=None,
        ),
    )
    monkeypatch.setattr(
        market_data, "build_market_history_synchronizer", lambda _settings: synchronizer
    )

    class Continuous:
        spot = "spot"
        futures = "futures"
        coin_m = None

        def __init__(self, **_kwargs: object) -> None:
            pass

        def record_recoverable_cycle_failure(self, *_args: object) -> None:
            pass

    class Depth:
        def __init__(self, *_args: object) -> None:
            pass

        def close(self) -> None:
            pass

    class Supervisor:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run(self, *, max_cycles: int | None) -> int:
            raise RuntimeError(message)

    monkeypatch.setattr(market_data, "ContinuousMarketHistory", Continuous)
    monkeypatch.setattr(market_data, "MarketDepthCollector", Depth)
    monkeypatch.setattr(market_data, "MarketHistorySupervisor", Supervisor)

    assert (
        market_data.run_market_history_command(
            "market-history-daemon",
            _market_data_cli_settings(tmp_path),
            as_of=None,
            max_cycles=1,
        )
        == 2
    )
    assert blocker in capsys.readouterr().out

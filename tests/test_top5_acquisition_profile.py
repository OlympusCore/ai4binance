"""TEST_ONLY native-grid, ranking, scoped recovery and authority invariants."""

import errno
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

import pytest

from ai4binance.config import Settings
from ai4binance.core.errors import ExchangeRateLimitError, ExchangeTransportError
from ai4binance.data.acquisition_profile import (
    PROFILE_TIMEFRAMES,
    SAFE_STATE,
    acquisition_window,
    candle_health_status,
    candle_health_window,
    candle_window_health,
    content_digest,
    exact_quote_volume,
    native_schedule,
    previous_calendar_month,
    stream_health,
    validate_native_rows,
)
from ai4binance.data.archive import DatasetManifest, ParquetOHLCVArchive
from ai4binance.data.market_history_continuous import ContinuousMarketHistory
from ai4binance.data.market_history_sync import (
    BinanceVisionArchiveCache,
    MarketHistorySynchronizer,
)
from ai4binance.data.scoped_history import (
    _collect_turn,
    _job,
    _job_path,
    _merge_retained_pages,
    _scheduled_turn,
    _stream_health,
    profile_health,
    profile_root,
    verified_selection,
)
from ai4binance.data.weekly_volume import (
    ScopedRetryPolicy,
    WeeklyVolumeRanking,
    active_shared_circuit,
    candidate_inventory,
    load_evidence,
    record_public_response,
    save_evidence,
    verify_frozen_reconstruction,
)
from ai4binance.integrations.binance import BinanceMarketUniverseProvider
from ai4binance.schemas import OHLCVCandle

NOW = datetime(2026, 9, 2, 12, 4, tzinfo=UTC)
ASSETS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")


@pytest.fixture
def candle_health_archive(tmp_path: Path) -> Path:
    """TEST_ONLY complete native windows for one Spot and one Futures instrument."""
    for market, symbol in (("spot", "AAAUSDT"), ("usd_m_futures", "BBBUSDT")):
        archive = ParquetOHLCVArchive(tmp_path / market)
        for timeframe in PROFILE_TIMEFRAMES:
            window = candle_health_window(market, timeframe, NOW)
            duration = (window.end - window.start) / window.expected_count
            candles = tuple(
                OHLCVCandle(
                    timestamp=window.start + index * duration,
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=Decimal("1"),
                )
                for index in range(window.expected_count)
            )
            archive.update(
                symbol,
                timeframe,
                candles,
                source=f"BINANCE_PUBLIC_REST_{timeframe.upper()}",
            )
    return tmp_path


def test_candle_health_verifies_exact_spot_and_fixed_30_day_futures_windows(
    candle_health_archive: Path,
) -> None:
    report = candle_window_health(
        candle_health_archive,
        symbols={"spot": ("AAAUSDT",), "usd_m_futures": ("BBBUSDT",)},
        cutoff=NOW,
    )
    assert candle_health_status(report, NOW) == "VERIFIED"
    assert report["stream_count"] == report["verified_stream_count"] == 10
    assert report["execution_allowed"] is False
    assert report["promotion_status"] == "RESEARCH_ONLY"
    rows = cast(list[dict[str, object]], report["streams"])
    assert [row["requested_bars"] for row in rows[:5]] == [1000] * 5
    assert [row["requested_bars"] for row in rows[5:]] == [8640, 2880, 720, 180, 30]
    assert report["analysis_status"] == "NOT_EVALUATED"
    assert all("warmup_ready" not in row for row in rows)
    assert candle_health_status(report, NOW + timedelta(minutes=1)) == "STALE"
    assert candle_health_status(report, NOW - timedelta(seconds=1)) == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "cutoff", ["2026-03-13T00:00:00+00:00", "2026-11-13T00:00:00+00:00"]
)
def test_candle_health_uses_fixed_days_without_changing_calendar_month_profile(
    cutoff: str,
) -> None:
    now = datetime.fromisoformat(cutoff)
    window = candle_health_window("usd_m_futures", "1d", now)
    assert window.expected_count == 30
    assert window.end - window.start == timedelta(days=30)
    assert acquisition_window("usd_m_futures", "1d", now).expected_count != 30


@pytest.mark.parametrize(
    "failure", ["missing", "stale", "corrupt", "wrong_source", "gap"]
)
def test_candle_health_rejects_failed_required_windows(
    candle_health_archive: Path,
    failure: str,
) -> None:
    root = candle_health_archive
    archive = ParquetOHLCVArchive(root / "spot")
    window = candle_health_window("spot", "5m", NOW)
    if failure == "stale":
        archive.truncate_from(
            "AAAUSDT",
            "5m",
            start_at=window.end - timedelta(minutes=5),
            source="BINANCE_PUBLIC_REST_5M",
        )
    elif failure == "corrupt":
        path = root / "spot/AAAUSDT/5m.parquet"
        path.write_bytes(path.read_bytes() + b"TEST_ONLY_CORRUPTION")
    elif failure == "wrong_source":
        path = root / "spot/AAAUSDT/5m.manifest.json"
        manifest = json.loads(path.read_text())
        manifest["source"] = "TEST_ONLY_UNAPPROVED_SOURCE"
        path.write_text(json.dumps(manifest))
    else:
        # A distinct test archive avoids deleting or rewriting the original fixture.
        target = root / "incomplete"
        copy = ParquetOHLCVArchive(target / "spot")
        candles = archive.read("AAAUSDT", "5m")
        retained = (
            candles[1:] if failure == "missing" else candles[:500] + candles[501:]
        )
        copy.update("AAAUSDT", "5m", retained, source="BINANCE_PUBLIC_REST_5M")
        root = target
    report = candle_window_health(root, symbols={"spot": ("AAAUSDT",)}, cutoff=NOW)
    assert report["status"] == "PARTIAL"
    assert candle_health_status(report, NOW) != "VERIFIED"
    assert "REQUIRED_NATIVE_CANDLE_WINDOW_INCOMPLETE" in cast(
        list[str], report["blockers"]
    )


def test_candle_health_preserves_universe_veto_and_rejects_forged_complete_counts(
    candle_health_archive: Path,
) -> None:
    symbols = {"spot": ("AAAUSDT",), "usd_m_futures": ("BBBUSDT",)}
    blocked = candle_window_health(
        candle_health_archive,
        symbols=symbols,
        cutoff=NOW,
        universe_blockers=("UNIVERSE_UNVERIFIED",),
    )
    assert blocked["status"] == "PARTIAL"
    assert blocked["blockers"] == ["UNIVERSE_UNVERIFIED"]
    report = candle_window_health(candle_health_archive, symbols=symbols, cutoff=NOW)
    rows = cast(list[dict[str, object]], report["streams"])
    rows.pop()
    assert candle_health_status(report, NOW) == "NOT_VERIFIED"
    assert (
        candle_window_health(candle_health_archive, symbols={}, cutoff=NOW)["status"]
        == "PARTIAL"
    )


def native_row(
    stamp: int, interval: int, *, quote: str = "0.123456789123456789"
) -> list[object]:
    return [
        stamp,
        "100",
        "102",
        "99",
        "101",
        "1",
        stamp + interval - 1,
        quote,
        2,
        "0.5",
        "0.05",
        "0",
    ]


def test_candle_health_publication_keeps_supplemental_errors_and_native_expiry(
    candle_health_archive: Path,
) -> None:
    instance = fixture_collector(candle_health_archive / "collector")
    instance.candle_window_health_enabled = True
    instance.clock = lambda: NOW
    instance._candle_health = candle_window_health(
        candle_health_archive,
        symbols={"spot": ("AAAUSDT",), "usd_m_futures": ("BBBUSDT",)},
        cutoff=NOW,
    )
    payload: dict[str, object] = {
        "status": "DEGRADED",
        "blockers": ["MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE"],
        "stream_failure_summary": {"usd_m_futures:open_interest:none:DATASET_GAP": 1},
        **SAFE_STATE,
    }
    projected = instance._candle_progress_payload(payload)
    assert projected["status"] == "VERIFIED"
    assert projected["collection_status"] == "DEGRADED"
    assert projected["blockers"] == ["MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE"]
    assert projected["stream_failure_summary"] == {
        "usd_m_futures:open_interest:none:DATASET_GAP": 1
    }
    instance.clock = lambda: NOW + timedelta(minutes=1)
    assert (
        instance._candle_progress_payload({"status": "COLLECTING"})["status"]
        == "COLLECTING"
    )


def test_candle_health_status_cli_projects_scope_without_waiving_supplemental_blockers(
    candle_health_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace

    from ai4binance.cli import market_data

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> FixedDatetime:
            return cls.fromtimestamp(NOW.timestamp(), UTC)

    proof = candle_window_health(
        candle_health_archive,
        symbols={"spot": ("AAAUSDT",)},
        cutoff=NOW,
    )
    path = candle_health_archive / "health-state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "observed_at": NOW.isoformat(),
                "status": "VERIFIED",
                "collection_status": "DEGRADED",
                "blockers": ["MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE"],
                "data_core": proof,
                **SAFE_STATE,
            }
        )
    )
    monkeypatch.setattr(market_data, "datetime", FixedDatetime)
    monkeypatch.setattr(
        market_data,
        "build_market_history_synchronizer",
        lambda settings: SimpleNamespace(state_path=path),
    )
    assert (
        market_data.run_market_history_command(
            "market-history-status",
            Settings.model_construct(market_history_live_interval_seconds=180),
            as_of=None,
            max_cycles=None,
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "VERIFIED"
    assert output["blockers"] == ["MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE"]


def test_candle_health_dashboard_projection_reuses_proof_and_rejects_expiry(
    candle_health_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import runpy
    from types import SimpleNamespace

    proof = candle_window_health(
        candle_health_archive, symbols={"spot": ("AAAUSDT",)}, cutoff=NOW
    )
    state = {
        "observed_at": NOW.isoformat(),
        "status": "VERIFIED",
        "data_core": proof,
        "collection_status": "DEGRADED",
    }
    path = candle_health_archive / "runtime/state/market-history-latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(state))
    source = Path(__file__).resolve().parents[1] / "src/ai4binance/local_dashboard"
    project = runpy.run_path(str(source / "market_views.py.in"))["universe_view"]
    settings = SimpleNamespace(market_history_live_interval_seconds=180)
    assert (
        project(candle_health_archive, settings, "SPOT", ("AAAUSDT",), NOW)[
            "data_core_status"
        ]
        == "VERIFIED"
    )
    assert (
        project(candle_health_archive, settings, "SPOT", ("AAAUSDT",), NOW)[
            "quality_status"
        ]
        == "CURRENT"
    )
    assert (
        project(
            candle_health_archive,
            settings,
            "SPOT",
            ("AAAUSDT",),
            NOW + timedelta(minutes=1),
        )["data_core_status"]
        == "STALE"
    )
    assert (
        project(candle_health_archive, settings, "SPOT", ("OTHERUSDT",), NOW)[
            "data_core_status"
        ]
        == "NOT_VERIFIED"
    )


def test_candle_health_rejects_duplicate_candles_and_changed_partition(
    candle_health_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ParquetOHLCVArchive.read_window

    def duplicated(
        self: ParquetOHLCVArchive, *args: object, **kwargs: object
    ) -> tuple[OHLCVCandle, ...]:
        candles = original(
            self,
            str(args[0]),
            str(args[1]),
            start_at=cast(datetime, kwargs["start_at"]),
            end_at=cast(datetime, kwargs["end_at"]),
        )
        return (*candles, candles[-1]) if candles else candles

    with monkeypatch.context() as patch:
        patch.setattr(ParquetOHLCVArchive, "read_window", duplicated)
        report = candle_window_health(
            candle_health_archive, symbols={"spot": ("AAAUSDT",)}, cutoff=NOW
        )
        assert report["status"] == "PARTIAL"
        assert (
            cast(list[dict[str, object]], report["streams"])[0]["duplicate_count"] == 1
        )

    def replaced(
        self: ParquetOHLCVArchive, *args: object, **kwargs: object
    ) -> tuple[OHLCVCandle, ...]:
        candles = original(
            self,
            str(args[0]),
            str(args[1]),
            start_at=cast(datetime, kwargs["start_at"]),
            end_at=cast(datetime, kwargs["end_at"]),
        )
        next_stamp = candles[-1].timestamp + (
            candles[-1].timestamp - candles[-2].timestamp
        )
        self.append_verified_tail(
            str(args[0]),
            str(args[1]),
            (
                OHLCVCandle(
                    timestamp=next_stamp,
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=Decimal("1"),
                ),
            ),
            source="BINANCE_PUBLIC_REST_TEST_ONLY",
        )
        return candles

    with monkeypatch.context() as patch:
        patch.setattr(ParquetOHLCVArchive, "read_window", replaced)
        report = candle_window_health(
            candle_health_archive, symbols={"spot": ("AAAUSDT",)}, cutoff=NOW
        )
        assert report["status"] == "PARTIAL"
        assert all(
            row["error_code"] == "ValueError"
            for row in cast(list[dict[str, object]], report["streams"])
        )


def test_candle_health_dashboard_never_uses_ready_fallback_for_invalid_proof(
    candle_health_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import runpy

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> FixedDatetime:
            return cls.fromtimestamp(NOW.timestamp(), UTC)

    proof = candle_window_health(
        candle_health_archive, symbols={"spot": ("AAAUSDT",)}, cutoff=NOW
    )
    source = (
        Path(__file__).resolve().parents[1]
        / "src/ai4binance/local_dashboard/server.py.in"
    )
    project = runpy.run_path(str(source))["market_history_projection"]
    monkeypatch.setitem(project.__globals__, "datetime", FixedDatetime)
    state = {
        "status": "READY",
        "completed_streams": 5,
        "total_streams": 5,
        "blockers": [],
        "data_core": proof,
    }
    assert project(state, candle_health_archive)["data_core_status"] == "VERIFIED"
    proof["status"] = "PARTIAL"
    assert project(state, candle_health_archive)["readiness_status"] == "DEGRADED"


class FixtureTransport:
    """TEST_ONLY exchange-shaped responses; never contacts a network."""

    def __init__(self, *, market: str = "spot", fail_symbol: str = "") -> None:
        self.market = market
        self.fail_symbol = fail_symbol
        self.calls: list[dict[str, str | int]] = []

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        query = dict(params or {})
        if path.endswith("exchangeInfo"):
            return {
                "symbols": [
                    {
                        "symbol": asset + "USDT",
                        "baseAsset": asset,
                        "quoteAsset": "USDT",
                        "status": "TRADING",
                        "isSpotTradingAllowed": True,
                        "contractType": "PERPETUAL",
                        "marginAsset": "USDT",
                        "onboardDate": 0,
                    }
                    for asset in ASSETS
                ]
            }
        self.calls.append(query)
        if path.endswith(("fundingRate", "openInterestHist")):
            return []
        if query["symbol"] == self.fail_symbol:
            raise ExchangeTransportError("TEST_ONLY recoverable outage")
        interval = {
            "1h": 3600000,
            "5m": 300000,
            "15m": 900000,
            "4h": 14400000,
            "1d": 86400000,
        }[str(query["interval"])]
        start, end, limit = (
            int(query[key]) for key in ("startTime", "endTime", "limit")
        )
        return [
            native_row(stamp, interval)
            for stamp in range(start, min(end + 1, start + limit * interval), interval)
        ]


def fixture_collector(root: Path) -> ContinuousMarketHistory:
    left, right = FixtureTransport(), FixtureTransport(market="usd_m_futures")
    ranking = WeeklyVolumeRanking(left, right, root / "source")
    selection = ranking.run(cutoff=NOW)
    history = MarketHistorySynchronizer(
        BinanceMarketUniverseProvider(left, right),
        root / "market",
        BinanceVisionArchiveCache(root / "source", fetch=lambda url: b""),
        root / "state.json",
    )
    return ContinuousMarketHistory(
        history,
        left,
        right,
        pages_per_stream=1,
        archives_per_stream=1,
        vision_history_enabled=False,
        scoped_selection=selection,
        required_candles_by_timeframe=dict.fromkeys(PROFILE_TIMEFRAMES, 2016),
    )


@pytest.mark.parametrize("timeframe", PROFILE_TIMEFRAMES)
def test_spot_target_is_exact_grid_not_duration_rounding(timeframe: str) -> None:
    window = acquisition_window("spot", timeframe, NOW)
    assert window.expected_count == 1000
    assert window.end <= NOW
    stamps = [
        window.start + index * (window.end - window.start) / 1000
        for index in range(1000)
    ]
    healthy = stream_health(
        window,
        stamps,
        strategy_required_bars=2016,
        verified_archive_count=1000,
        lineage={},
    )
    assert healthy["status"] == "DATA_READY_1000"
    assert healthy["warmup_ready"] is False
    gap = stream_health(
        window,
        stamps[:500] + stamps[501:] + [stamps[0]],
        strategy_required_bars=2016,
        verified_archive_count=1000,
        lineage={},
    )
    assert gap["missing_count"] == 1
    assert gap["duplicate_count"] == 1
    assert gap["status"] == "PARTIAL"
    assert healthy["execution_allowed"] is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-03-31T12:00:00+00:00", "2024-02-29T12:00:00+00:00"),
        ("2025-03-31T12:00:00+00:00", "2025-02-28T12:00:00+00:00"),
        ("2026-01-31T00:00:00+00:00", "2025-12-31T00:00:00+00:00"),
    ],
)
def test_calendar_month_clamps_and_crosses_year(value: str, expected: str) -> None:
    assert (
        previous_calendar_month(datetime.fromisoformat(value)).isoformat() == expected
    )


def test_monthly_futures_daily_target_is_not_spot_1000() -> None:
    window = acquisition_window("usd_m_futures", "1d", NOW)
    assert window.expected_count == 31
    assert window.start == datetime(2026, 8, 2, tzinfo=UTC)


def test_native_microseconds_and_decimal_quote_volume() -> None:
    end = NOW.replace(minute=0)
    start = end - timedelta(hours=168)
    rows = [
        native_row(
            int((start + timedelta(hours=index)).timestamp()) * 1000000, 3600000000
        )
        for index in range(168)
    ]
    valid = validate_native_rows(rows, start=start, end=end, timeframe="1h")
    assert (
        Decimal(exact_quote_volume(valid, start, end))
        == Decimal("0.123456789123456789") * 168
    )
    with pytest.raises(ValueError, match="168"):
        exact_quote_volume(valid[:-1], start, end)
    with pytest.raises(ValueError, match="time boundary"):
        validate_native_rows(
            [native_row(int(end.timestamp()) * 1000, 3600000)],
            start=start,
            end=end,
            timeframe="1h",
        )


def test_ranking_common_top5_ties_and_cache_reuse(tmp_path: Path) -> None:
    left, right = FixtureTransport(), FixtureTransport(market="usd_m_futures")
    ranking = WeeklyVolumeRanking(left, right, tmp_path)
    first = ranking.run(cutoff=NOW)
    assert first["status"] == "VERIFIED"
    assert [item["asset_id"] for item in verified_selection(first)] == list(ASSETS[:5])
    assert len(left.calls) == len(right.calls) == 6
    second = ranking.run(cutoff=NOW)
    assert first["selection_version"] == second["selection_version"]
    assert len(left.calls) == len(right.calls) == 6
    assert all(
        query["interval"] == "1h" and query["limit"] == 168 for query in left.calls
    )


def test_missing_candidate_does_not_become_zero_or_current_top5(tmp_path: Path) -> None:
    left = FixtureTransport(fail_symbol="AAAUSDT")
    report = WeeklyVolumeRanking(left, FixtureTransport(), tmp_path).run(cutoff=NOW)
    assert report["status"] == "NOT_VERIFIED"
    assert report["selected"] == []
    assert report["unverified_assets"] == ["AAA"]
    assert any(query["symbol"] == "BBBUSDT" for query in left.calls)
    assert len(cast(list[object], report["diagnostic_top5"])) == 5


def test_scaled_identity_is_not_inferred_by_string_stripping() -> None:
    spot = {
        "symbols": [
            {
                "symbol": "PEPEUSDT",
                "baseAsset": "PEPE",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
            }
        ]
    }
    futures = {
        "symbols": [
            {
                "symbol": "1000PEPEUSDT",
                "baseAsset": "1000PEPE",
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            }
        ]
    }
    candidates, excluded = candidate_inventory(spot, futures)
    assert candidates == []
    assert len(excluded) == 2


def test_retry_budget_persists_after_reconstruction(tmp_path: Path) -> None:
    path = tmp_path / "retry.json"
    assert ScopedRetryPolicy().reserve(path, NOW)
    assert not ScopedRetryPolicy().reserve(path, NOW)
    assert ScopedRetryPolicy().reserve(path, NOW + timedelta(seconds=30))
    assert ScopedRetryPolicy().reserve(path, NOW + timedelta(seconds=90))
    assert not ScopedRetryPolicy().reserve(path, NOW + timedelta(minutes=10))
    state = load_evidence(path)
    assert len(cast(list[object], state["attempts"])) == 3
    assert datetime.fromisoformat(str(state["next_retry_at"])) == NOW + timedelta(
        seconds=990
    )


def test_healthy_5m_updates_do_not_exhaust_retry_failure_budget(tmp_path: Path) -> None:
    path = tmp_path / "TEST_ONLY-healthy-retries.json"
    policy = ScopedRetryPolicy()
    for index in range(12):
        now = NOW + timedelta(minutes=5 * index)
        assert policy.reserve(path, now)
        policy.succeed(path, now)
    assert load_evidence(path)["attempts"] == []


def test_success_releases_only_current_reservation_preserving_failures(
    tmp_path: Path,
) -> None:
    path = tmp_path / "TEST_ONLY-prior-failed-retries.json"
    policy = ScopedRetryPolicy()
    assert policy.reserve(path, NOW)
    assert policy.reserve(path, NOW + timedelta(seconds=30))
    policy.succeed(path, NOW + timedelta(seconds=31))
    state = load_evidence(path)
    assert state["attempts"] == [NOW.isoformat()]
    assert ScopedRetryPolicy().reserve(path, NOW + timedelta(seconds=60))
    policy.succeed(path, NOW + timedelta(seconds=61), useful_progress=False)
    current = load_evidence(path)
    assert current["attempts"] == [NOW.isoformat()]
    assert current["last_useful_update"] == state["last_useful_update"]


def test_recoverable_asset_fault_yields_to_healthy_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = fixture_collector(tmp_path)
    calls: list[str] = []

    def collect(
        self: ContinuousMarketHistory,
        market: str,
        symbol: str,
        kind: str,
        transport: object,
        now: datetime,
        **kwargs: object,
    ) -> dict[str, object]:
        del self, market, kind, transport, now, kwargs
        calls.append(symbol)
        if symbol == "AAAUSDT":
            raise ExchangeTransportError("TEST_ONLY unavailable")
        return {"status": "CURRENT"}

    monkeypatch.setattr(ContinuousMarketHistory, "_candles", collect)
    report = collector.sync_cycle(observed_at=NOW)
    assert "BBBUSDT" in calls
    assert calls.index("BBBUSDT") < len(calls) - 2
    assert report["execution_allowed"] is False
    assert len(cast(list[object], report["streams"])) == 50
    assert report["bounded_backlog"] == 110
    state = load_evidence(collector.history.state_path)
    assert state["status"] == "DEGRADED"
    assert state["profile_data_status"] == "PARTIAL"
    assert state["spot_universe_count"] == 5
    assert state["blockers"] == ["TOP5_NATIVE_GRID_INCOMPLETE"]


def test_read_only_health_preserves_canonical_writer_state(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    save_evidence(collector.history.state_path, {"scope": "TEST_ONLY_PRIOR_WRITER"})
    before = collector.history.state_path.read_bytes()
    report = profile_health(collector, cutoff=NOW)
    assert report["status"] == "PARTIAL"
    assert collector.history.state_path.read_bytes() == before


def test_corrupted_immutable_snapshot_is_rejected(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    report = profile_health(collector, cutoff=NOW)
    references = cast(list[dict[str, object]], report["snapshots"])
    path = Path(str(references[0]["artifact_path"]))
    snapshot = load_evidence(path)
    snapshot["symbol"] = "TEST_ONLY_TAMPERED"
    save_evidence(path, snapshot)
    with pytest.raises(ValueError, match="snapshot integrity"):
        profile_health(collector, cutoff=NOW)


@pytest.mark.parametrize(
    ("failed_market", "failed_tf", "healthy_symbol"),
    [("spot", "1d", "BBBUSDT"), ("usd_m_futures", "5m", "AAAUSDT")],
)
def test_failed_stream_yields_to_published_healthy_spot(
    tmp_path: Path, failed_market: str, failed_tf: str, healthy_symbol: str
) -> None:
    collector = fixture_collector(tmp_path)
    failing = FixtureTransport(fail_symbol="AAAUSDT")
    if failed_market == "spot":
        collector.spot = failing
    else:
        collector.futures = failing
    window = acquisition_window("spot", "5m", NOW)
    rows = [
        native_row(int(window.start.timestamp() * 1000) + index * 300000, 300000)
        for index in range(999)
    ]
    candles = collector._parse_rows(
        cast(list[object], rows),
        window.start,
        window.end,
        interval=timedelta(minutes=5),
    )
    archive = ParquetOHLCVArchive(collector.history.archive_root / "spot")
    archive.update(
        healthy_symbol, "5m", candles, source="BINANCE_PUBLIC_REST_5M", generated_at=NOW
    )
    collector.scoped_window_starts = {
        (failed_market, failed_tf): acquisition_window(
            failed_market, failed_tf, NOW
        ).start,
        ("spot", "5m"): window.start,
    }
    policy = ScopedRetryPolicy()
    failed_row: dict[str, object] = {
        "market": failed_market,
        "symbol": "AAAUSDT",
        "timeframe": failed_tf,
    }
    failed = _collect_turn(collector, failed_row, NOW, policy)
    healthy = _collect_turn(
        collector,
        {"market": "spot", "symbol": healthy_symbol, "timeframe": "5m"},
        NOW,
        policy,
    )
    assert failed["status"] == "BLOCKED"
    assert healthy["status"] == "PROGRESS"
    assert (
        _stream_health(collector, "spot", healthy_symbol, "5m", NOW)["status"]
        == "DATA_READY_1000"
    )
    report = profile_health(collector, cutoff=NOW)
    references = cast(list[dict[str, object]], report["snapshots"])
    reference = next(
        item
        for item in references
        if item["market"] == "spot" and item["symbol"] == healthy_symbol
    )
    published = load_evidence(Path(str(reference["artifact_path"])))
    streams = cast(list[dict[str, object]], published["streams"])
    assert streams[0]["available_verified_bars"] == 1000
    assert _collect_turn(collector, failed_row, NOW, policy)["status"] == "DEFERRED"
    assert len(failing.calls) == (2 if failed_market == "spot" else 1)


def test_all_sources_down_publish_degraded_without_false_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = fixture_collector(tmp_path)

    def offline(*args: object, **kwargs: object) -> object:
        raise ExchangeTransportError("TEST_ONLY all public sources unavailable")

    monkeypatch.setattr(FixtureTransport, "get_json", offline)
    first = collector.sync_cycle(observed_at=NOW)
    second = collector.sync_cycle(observed_at=NOW)
    assert first["status"] == second["status"] == "PARTIAL"
    assert first["useful_progress_count"] == second["useful_progress_count"] == 0
    enrichment = cast(list[dict[str, object]], first["futures_enrichment_results"])
    assert all(item["status"] == "BLOCKED" for item in enrichment)
    results = cast(list[dict[str, object]], second["results"])
    assert len(results) == 50
    assert all(item["status"] == "DEFERRED" for item in results)
    streams = cast(list[dict[str, object]], first["streams"])
    assert all(item["available_verified_bars"] == 0 for item in streams)
    assert load_evidence(collector.history.state_path)["status"] == "DEGRADED"


def test_fatal_storage_failure_and_intentional_cancel_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = fixture_collector(tmp_path)

    def full(*args: object, **kwargs: object) -> dict[str, object]:
        raise OSError(errno.ENOSPC, "TEST_ONLY disk full")

    monkeypatch.setattr(ContinuousMarketHistory, "_candles", full)
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    with pytest.raises(OSError, match="disk full") as failure:
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())
    assert failure.value.errno == errno.ENOSPC

    def cancel(*args: object, **kwargs: object) -> dict[str, object]:
        raise KeyboardInterrupt

    monkeypatch.setattr(ContinuousMarketHistory, "_candles", cancel)
    with pytest.raises(KeyboardInterrupt):
        _collect_turn(collector, {**row, "symbol": "BBBUSDT"}, NOW, ScopedRetryPolicy())


def test_shared_rate_limit_parks_other_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = fixture_collector(tmp_path)
    calls: list[str] = []

    def limited(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append("called")
        raise ExchangeRateLimitError(429, 120, "/api/v3/klines")

    monkeypatch.setattr(ContinuousMarketHistory, "_candles", limited)
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    _collect_turn(collector, row, NOW, ScopedRetryPolicy())
    result = _collect_turn(
        collector, {**row, "symbol": "BBBUSDT"}, NOW, ScopedRetryPolicy()
    )
    assert result["status"] == "DEGRADED_WAIT"
    assert len(calls) == 1


def test_tampered_selection_rejected(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    selection = dict(collector.scoped_selection or {})
    selection["selected"] = []
    with pytest.raises(ValueError, match="genuine"):
        verified_selection(selection)
    assert content_digest(SAFE_STATE)


@pytest.mark.parametrize("limited_path", ["exchangeInfo", "klines"])
def test_shared_cooldown_survives_ranking_to_collector_restart(
    tmp_path: Path, limited_path: str
) -> None:
    """TEST_ONLY host throttling persists across every profile GET entry point."""
    collector = fixture_collector(tmp_path)
    root = profile_root(collector)
    calls: list[str] = []

    class LimitedTransport(FixtureTransport):
        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            calls.append(path)
            if path.endswith(limited_path):
                raise ExchangeRateLimitError(429, 120, path)
            return super().get_json(path, params)

    now = datetime.now(UTC)
    ranking = WeeklyVolumeRanking(LimitedTransport(), FixtureTransport(), root)
    if limited_path == "exchangeInfo":
        assert ranking._metadata(now)["status"] == "NOT_VERIFIED"
    else:
        with pytest.raises(ExchangeRateLimitError):
            ranking._ranking_rows(
                "TEST_ONLY_uncached",
                ranking.spot,
                "/api/v3/",
                "AAAUSDT",
                now - timedelta(days=7),
                now,
                now,
            )
    circuit = active_shared_circuit(root, "spot", datetime.now(UTC))
    assert circuit["scope"] == "spot"
    assert datetime.fromisoformat(str(circuit["next_retry_at"])) >= (
        now + timedelta(seconds=120)
    )
    restarted = WeeklyVolumeRanking(LimitedTransport(), FixtureTransport(), root)
    restarted._metadata(datetime.now(UTC))
    result = _collect_turn(
        collector,
        {"market": "spot", "symbol": "BBBUSDT", "timeframe": "5m"},
        NOW,
        ScopedRetryPolicy(),
    )
    assert result["status"] == "DEGRADED_WAIT"
    assert len(calls) == 1
    assert (root / "metadata" / "usd_m_futures.json").is_file()
    assert not active_shared_circuit(root, "usd_m_futures", datetime.now(UTC))


def test_exact_gap_repair_and_resume_use_existing_collector(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    collector.scoped_window_starts = {
        ("spot", "5m"): acquisition_window("spot", "5m", NOW).start
    }
    first = collector._candles(
        "spot", "AAAUSDT", "klines", collector.spot, NOW, timeframe="5m"
    )
    assert first["status"] == "BACKFILLING"
    archive = ParquetOHLCVArchive(collector.history.archive_root / "spot")
    original = archive.read("AAAUSDT", "5m")
    assert len(original) == 499
    # TEST_ONLY isolated fixture partition; no authoritative archive is altered.
    for _ in range(2):
        collector._candles(
            "spot", "AAAUSDT", "klines", collector.spot, NOW, timeframe="5m"
        )
    assert len(archive.read("AAAUSDT", "5m")) == 1000
    before = archive.manifest("AAAUSDT", "5m").sha256
    collector._candles("spot", "AAAUSDT", "klines", collector.spot, NOW, timeframe="5m")
    assert archive.manifest("AAAUSDT", "5m").sha256 == before


def stage_fixture_page(collector: ContinuousMarketHistory) -> Path:
    """TEST_ONLY source receipt used to exercise the replay trust boundary."""
    window = acquisition_window("spot", "5m", NOW)
    end = window.start + timedelta(minutes=5)
    rows = [native_row(int(window.start.timestamp() * 1000), 300000)]
    params = {
        "symbol": "AAAUSDT",
        "interval": "5m",
        "startTime": int(window.start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000) - 1,
        "limit": 499,
    }
    url = "https://api.binance.com/api/v3/klines?" + urlencode(sorted(params.items()))
    raw = json.dumps(rows).encode()
    root = profile_root(collector)
    record_public_response(root, url, raw)
    packet: dict[str, object] = {
        "market": "spot",
        "symbol": "AAAUSDT",
        "timeframe": "5m",
        "start": window.start.isoformat(),
        "end": end.isoformat(),
        "source": "/api/v3/klines",
        "rows": rows,
        "selection_version": (collector.scoped_selection or {})["selection_version"],
        "raw_response_sha256": sha256(raw).hexdigest(),
    }
    packet["content_sha256"] = content_digest(packet)
    path = root / "pending" / "spot-AAAUSDT-5m" / f"{packet['content_sha256']}.json"
    save_evidence(path, packet)
    return path


def test_staged_page_replay_preserves_receipt_and_is_idempotent(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    path = stage_fixture_page(collector)
    assert _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    archive = ParquetOHLCVArchive(collector.history.archive_root / "spot")
    assert len(archive.read("AAAUSDT", "5m")) == 1
    before = archive.manifest("AAAUSDT", "5m").sha256
    assert not _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    assert archive.manifest("AAAUSDT", "5m").sha256 == before
    assert path.exists()


def test_staged_hash_failure_preserves_prior_archive(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    path = stage_fixture_page(collector)
    packet = load_evidence(path)
    packet["market"] = "usd_m_futures"
    save_evidence(path, packet)
    with pytest.raises(ValueError, match="binding"):
        _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    assert not (collector.history.archive_root / "spot" / "AAAUSDT").exists()


@pytest.mark.parametrize("timeframe", PROFILE_TIMEFRAMES)
def test_native_due_grace_has_no_work_duration_drift(timeframe: str) -> None:
    from ai4binance.data.timeframes import timeframe_duration

    boundary = acquisition_window("spot", timeframe, NOW).end
    duration = timeframe_duration(timeframe)
    before = native_schedule(
        boundary + timedelta(seconds=2), timeframe, arrival_grace_seconds=7
    )
    after = native_schedule(
        boundary + timedelta(seconds=50), timeframe, arrival_grace_seconds=7
    )
    assert before["acquisition_closed_boundary"] == (boundary - duration).isoformat()
    assert after["acquisition_closed_boundary"] == boundary.isoformat()
    assert (
        before["expected_closed_boundary"]
        == after["expected_closed_boundary"]
        == boundary.isoformat()
    )
    assert (
        before["next_native_due_at"]
        == after["next_native_due_at"]
        == (boundary + duration + timedelta(seconds=7)).isoformat()
    )
    from ai4binance.data.market_history_sync import _scoped_wakeup_delay

    assert (
        _scoped_wakeup_delay(
            {"local_next_wakeup_at": after["next_native_due_at"]},
            boundary + timedelta(seconds=50),
            180,
        )
        == duration.total_seconds() - 43
    )


@pytest.mark.parametrize("timeframe", PROFILE_TIMEFRAMES)
def test_receipts_count_only_missing_bars_and_survive_reload(
    tmp_path: Path, timeframe: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.data.timeframes import timeframe_duration

    collector = fixture_collector(tmp_path)
    window = acquisition_window("spot", timeframe, NOW)
    duration = timeframe_duration(timeframe)
    rows = [
        native_row(
            int((window.start + index * duration).timestamp() * 1000),
            int(duration.total_seconds() * 1000),
        )
        for index in range(1000)
    ]
    candles = collector._parse_rows(
        cast(list[object], rows), window.start, window.end, interval=duration
    )
    archive = ParquetOHLCVArchive(collector.history.archive_root / "spot")
    archive.update(
        "AAAUSDT",
        timeframe,
        candles,
        source=f"BINANCE_PUBLIC_REST_{timeframe.upper()}",
        generated_at=NOW,
    )
    collector.scoped_window_starts = {("spot", timeframe): window.start}
    transport = cast(FixtureTransport, collector.spot)
    transport.calls.clear()
    row: dict[str, object] = {
        "market": "spot",
        "symbol": "AAAUSDT",
        "timeframe": timeframe,
    }
    updates: list[str] = []
    original_update = ParquetOHLCVArchive.update

    def watched_update(
        self: ParquetOHLCVArchive,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        *,
        source: str,
        generated_at: datetime | None = None,
        replace_conflicts_from_sources: tuple[str, ...] = (),
    ) -> DatasetManifest:
        updates.append("TEST_ONLY write")
        return original_update(
            self,
            symbol,
            timeframe,
            candles,
            source=source,
            generated_at=generated_at,
            replace_conflicts_from_sources=replace_conflicts_from_sources,
        )

    monkeypatch.setattr(ParquetOHLCVArchive, "update", watched_update)
    before = archive.manifest("AAAUSDT", timeframe)
    assert (
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())["reason"]
        == "INSUFFICIENT_CANDLES"
    )
    assert (
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())["reason"]
        == "INSUFFICIENT_CANDLES"
    )
    assert transport.calls == []
    assert updates == []
    assert (
        _stream_health(collector, "spot", "AAAUSDT", timeframe, NOW)["warmup_ready"]
        is False
    )
    assert archive.manifest("AAAUSDT", timeframe) == before
    later = window.end + duration + timedelta(seconds=1)
    assert (
        _collect_turn(collector, row, later, ScopedRetryPolicy())["status"]
        == "PROGRESS"
    )
    assert len(transport.calls) == 1
    assert transport.calls[0]["limit"] == 1
    state = _job(collector, row)
    counters = cast(dict[str, int], state["counters"])
    assert (
        counters["get_attempts"]
        == counters["completed_responses"]
        == counters["canonical_inserts"]
        == counters["requested_missing_bars"]
        == 1
    )
    assert counters["duplicate_overlap_rows"] == 0
    assert len(archive.read("AAAUSDT", timeframe)) == 1001
    assert not _merge_retained_pages(
        collector, "spot", "AAAUSDT", "klines", timeframe, later
    )
    assert _job(collector, row)["counters"] == counters
    assert load_evidence(_job_path(collector, row))["last_useful_commit_at"]


def test_pending_response_replays_after_commit_failure_without_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = fixture_collector(tmp_path)
    window = acquisition_window("spot", "5m", NOW)
    collector.scoped_window_starts = {("spot", "5m"): window.start}
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    original = ParquetOHLCVArchive.update

    def unavailable(*args: object, **kwargs: object) -> object:
        raise ExchangeTransportError("TEST_ONLY interrupted canonical publication")

    monkeypatch.setattr(ParquetOHLCVArchive, "update", unavailable)
    assert (
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())["status"] == "BLOCKED"
    )
    state = _job(collector, row)
    assert state["deferred_publish_rows"] == 499
    assert cast(dict[str, int], state["counters"])["canonical_inserts"] == 0
    monkeypatch.setattr(ParquetOHLCVArchive, "update", original)
    transport = cast(FixtureTransport, collector.spot)
    calls = len(transport.calls)
    assert (
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())["status"] == "PROGRESS"
    )
    assert len(transport.calls) == calls
    state = _job(collector, row)
    assert state["deferred_publish_rows"] == 0
    assert cast(dict[str, int], state["counters"])["canonical_inserts"] == 499
    assert not _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    assert _job(collector, row)["counters"] == state["counters"]


def test_foreign_writer_lease_is_preserved_without_requests(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    lock = collector.history.state_path.with_suffix(".lock")
    save_evidence(
        lock, {"pid": 2147483647, "process_marker": "TEST_ONLY unknown owner"}
    )
    before = lock.read_bytes()
    transport = cast(FixtureTransport, collector.spot)
    transport.calls.clear()
    assert collector.sync_cycle(observed_at=NOW)["reason"] == "CANONICAL_WRITER_BUSY"
    assert lock.read_bytes() == before
    assert transport.calls == []
    assert not collector.history.state_path.exists()


def test_reconstruction_full_reload_and_partial_rejection(tmp_path: Path) -> None:
    root = tmp_path / "TEST_ONLY-source"

    class ReceiptedFixture(FixtureTransport):
        def get_json(
            self, path: str, params: Mapping[str, str | int] | None = None
        ) -> object:
            payload = super().get_json(path, params)
            host = (
                "https://api.binance.com"
                if self.market == "spot"
                else "https://fapi.binance.com"
            )
            if params is not None and path.endswith("klines"):
                record_public_response(
                    root,
                    host + path + "?" + urlencode(sorted(params.items())),
                    json.dumps(payload).encode(),
                )
            return payload

    ranking = WeeklyVolumeRanking(
        ReceiptedFixture(), ReceiptedFixture(market="usd_m_futures"), root
    )
    frozen = ranking.run(cutoff=NOW)
    # TEST_ONLY remove one decoded fixture packet to force later retrieval.
    lost_packet = next((root / "ranking-bars").glob("spot-AAAUSDT-*.json"))
    lost_packet.unlink()
    before = (root / "selection-active.json").read_bytes()
    manifest = ranking.reconstruct_frozen(frozen, tmp_path / "TEST_ONLY-durable")
    bound_root = tmp_path / "TEST_ONLY-durable" / str(frozen["selection_version"])
    result = verify_frozen_reconstruction(
        bound_root,
        {key: value for key, value in manifest.items() if key != "verification"},
    )
    assert result["verified_packet_count"] == 12
    assert result["original_packets_recovered"] == 11
    assert result["later_retrieved_packets"] == 1
    assert len(list((bound_root / "original-receipts").glob("*.json"))) == 12
    assert result["top5_matches_original"] is True
    assert (root / "selection-active.json").read_bytes() == before
    partial = {
        key: value
        for key, value in manifest.items()
        if key not in {"verification", "evidence_revision"}
    }
    partial["packet_references"] = cast(list[object], partial["packet_references"])[:-1]
    partial["evidence_revision"] = content_digest(partial)
    with pytest.raises(ValueError, match="missing declared"):
        verify_frozen_reconstruction(bound_root, partial)


def test_persisted_due_jobs_honor_grace_and_failed_a_yields_to_b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai4binance.data.scoped_history as scoped

    collector = fixture_collector(tmp_path)
    collector.scoped_arrival_grace_seconds = 7
    boundary = acquisition_window("spot", "5m", NOW).end
    jobs: list[dict[str, object]] = [
        {
            "market": "spot",
            "symbol": symbol,
            "timeframe": "5m",
            "status": "PARTIAL",
            "tail_ready": False,
            "missing_open_times": [(boundary - timedelta(minutes=5)).isoformat()],
        }
        for symbol in ("AAAUSDT", "BBBUSDT")
    ]

    def health(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "streams": jobs.copy(),
            "status": "PARTIAL",
            "blockers": ["TEST_ONLY_MISSING"],
        }

    called: list[str] = []

    def collect(
        collector: ContinuousMarketHistory,
        row: dict[str, object],
        cutoff: datetime,
        policy: ScopedRetryPolicy,
        *,
        allow_fetch: bool = True,
    ) -> dict[str, object]:
        if not allow_fetch:
            return {"status": "NO_RETAINED_PROGRESS"}
        called.append(str(row["symbol"]))
        return {"status": "BLOCKED" if row["symbol"] == "AAAUSDT" else "PROGRESS"}

    monkeypatch.setattr(scoped, "profile_health", health)
    monkeypatch.setattr(scoped, "_collect_turn", collect)
    monkeypatch.setattr(scoped, "_enrichment_turns", lambda *args: [])
    first = collector.sync_cycle(observed_at=boundary + timedelta(seconds=2))
    assert called == []
    assert (
        first["local_next_wakeup_at"] == (boundary + timedelta(seconds=7)).isoformat()
    )
    saved_a = _job(collector, jobs[0])
    saved_a["next_due_at"] = (boundary + timedelta(minutes=10)).isoformat()
    save_evidence(_job_path(collector, jobs[0]), saved_a)
    reloaded = fixture_collector(tmp_path)
    reloaded.scoped_arrival_grace_seconds = 7
    reloaded.clock = lambda: boundary + timedelta(seconds=8)
    second = reloaded.sync_cycle(observed_at=boundary + timedelta(seconds=8))
    assert called == ["BBBUSDT"]
    assert second["useful_progress_count"] == 1
    assert _job(reloaded, jobs[0])["expected_closed_boundary"] == boundary.isoformat()
    assert (
        _job(reloaded, jobs[1])["last_actual_run_at"]
        == (boundary + timedelta(seconds=8)).isoformat()
    )


def test_actual_start_lag_and_schedule_survive_delayed_local_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TEST_ONLY verified-clock stub and delayed replay; no real runtime claim."""
    collector = fixture_collector(tmp_path)
    requests_before = list(cast(FixtureTransport, collector.spot).calls)
    started = NOW + timedelta(seconds=45)
    collector.clock = lambda: started
    collector.scoped_clock_verified = True
    collector.scoped_clock_offset_seconds = 10
    row: dict[str, object] = {
        "market": "spot",
        "symbol": "AAAUSDT",
        "timeframe": "5m",
        "status": "DATA_READY_1000",
    }
    state = _job(collector, row)
    state["next_due_at"] = NOW.isoformat()
    save_evidence(_job_path(collector, row), state)
    _scheduled_turn(collector, row, NOW, ScopedRetryPolicy())
    assert _job(collector, row)["scheduling_lag_seconds"] == 55
    row["status"] = "MISSING"
    state = _job(collector, row)
    state["next_due_at"] = NOW.isoformat()
    for key in ("expected_closed_boundary", "arrival_deadline"):
        state.pop(key)
    save_evidence(_job_path(collector, row), state)

    def delayed_replay(*args: object, **kwargs: object) -> dict[str, object]:
        collector.clock = lambda: NOW + timedelta(seconds=90)
        return {"status": "PROGRESS"}

    monkeypatch.setattr("ai4binance.data.scoped_history._collect_turn", delayed_replay)
    assert (
        _scheduled_turn(collector, row, NOW, ScopedRetryPolicy())["status"]
        == "PROGRESS"
    )
    persisted = _job(collector, row)
    assert persisted["scheduling_lag_seconds"] == 55
    assert persisted["last_actual_run_at"] == started.isoformat()
    assert persisted["expected_closed_boundary"] == "2026-09-02T12:00:00+00:00"
    assert persisted["arrival_deadline"] == "2026-09-02T12:00:00+00:00"
    assert cast(FixtureTransport, collector.spot).calls == requests_before


def test_multiple_internal_gaps_fetch_only_missing_intervals(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    collector.clock = lambda: NOW
    window = acquisition_window("spot", "5m", NOW)
    rows = [
        native_row(
            int((window.start + timedelta(minutes=5 * index)).timestamp() * 1000),
            300000,
        )
        for index in range(1000)
    ]
    candles = collector._parse_rows(
        cast(list[object], rows),
        window.start,
        window.end,
        interval=timedelta(minutes=5),
    )
    candles = tuple(
        item for index, item in enumerate(candles) if index not in {200, 301, 302}
    )
    archive = ParquetOHLCVArchive(collector.history.archive_root / "spot")
    archive.update(
        "AAAUSDT", "5m", candles, source="BINANCE_PUBLIC_REST_5M", generated_at=NOW
    )
    collector.scoped_window_starts = {("spot", "5m"): window.start}
    transport = cast(FixtureTransport, collector.spot)
    transport.calls.clear()
    row: dict[str, object] = {
        "market": "spot",
        "symbol": "AAAUSDT",
        "timeframe": "5m",
        "tail_ready": True,
    }
    for _ in range(2):
        assert (
            _collect_turn(collector, row, NOW, ScopedRetryPolicy())["status"]
            == "PROGRESS"
        )
    assert [query["limit"] for query in transport.calls] == [1, 2]
    assert [query["startTime"] for query in transport.calls] == [
        int((window.start + timedelta(minutes=5 * index)).timestamp() * 1000)
        for index in (200, 301)
    ]
    assert len(archive.read("AAAUSDT", "5m")) == 1000
    counters = cast(dict[str, int], _job(collector, row)["counters"])
    assert counters["requested_missing_bars"] == counters["canonical_inserts"] == 3
    later = NOW + timedelta(minutes=15)
    assert (
        _collect_turn(collector, row, later, ScopedRetryPolicy())["status"]
        == "PROGRESS"
    )
    assert transport.calls[-1]["limit"] == 3
    assert len(archive.read("AAAUSDT", "5m")) == 1003


def test_late_response_is_retained_and_replayed_with_owner_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = fixture_collector(tmp_path)
    window = acquisition_window("spot", "5m", NOW)
    collector.scoped_window_starts = {("spot", "5m"): window.start}
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    clock_values = iter((100.0, 101.0, 131.0))
    monkeypatch.setattr(
        "ai4binance.data.scoped_history.time.monotonic", lambda: next(clock_values)
    )
    result = _collect_turn(collector, row, NOW, ScopedRetryPolicy())
    assert result["status"] == "BLOCKED"
    assert _job(collector, row)["deferred_publish_rows"] == 499
    assert not _job_path(collector, row).with_suffix(".lock").exists()
    assert not collector.history.state_path.with_suffix(".lock").exists()
    assert cast(dict[str, int], _job(collector, row)["counters"])["late_responses"] == 1
    monkeypatch.undo()
    transport = cast(FixtureTransport, collector.spot)
    calls = len(transport.calls)
    assert (
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())["status"] == "PROGRESS"
    )
    assert len(transport.calls) == calls


def test_counter_settlement_crash_reconciles_canonical_commit_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ai4binance.data.scoped_history as scoped

    collector = fixture_collector(tmp_path)
    window = acquisition_window("spot", "5m", NOW)
    collector.scoped_window_starts = {("spot", "5m"): window.start}
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    original = scoped._settle_effect
    calls = 0

    def interrupted(
        collector: ContinuousMarketHistory, row: Mapping[str, object], cutoff: datetime
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt("TEST_ONLY crash after canonical commit")
        original(collector, row, cutoff)

    monkeypatch.setattr(scoped, "_settle_effect", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())
    archive = ParquetOHLCVArchive(collector.history.archive_root / "spot")
    before = archive.manifest("AAAUSDT", "5m")
    assert before.row_count == 499
    monkeypatch.setattr(scoped, "_settle_effect", original)
    assert not _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    assert archive.manifest("AAAUSDT", "5m") == before
    counters = cast(dict[str, int], _job(collector, row)["counters"])
    assert counters["canonical_inserts"] == 499
    assert counters["get_attempts"] == 1
    assert not _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    assert _job(collector, row)["counters"] == counters


def test_response_alias_replacement_preserves_original_receipt(tmp_path: Path) -> None:
    url = "https://api.binance.com/api/v3/time"
    record_public_response(tmp_path, url, b'{"serverTime": 1000}')
    alias = tmp_path / "responses" / f"{sha256(url.encode()).hexdigest()}.json"
    original = load_evidence(alias)
    original_path = (
        tmp_path / "responses" / "history" / f"{content_digest(original)}.json"
    )
    before = original_path.read_bytes()
    record_public_response(tmp_path, url, b'{"serverTime": 2000}')
    assert (
        load_evidence(alias)["raw_response_sha256"] != original["raw_response_sha256"]
    )
    assert original_path.read_bytes() == before
    assert load_evidence(original_path) == original
    assert (tmp_path / "raw" / f"{original['raw_response_sha256']}.json").exists()


def test_pending_receipt_cannot_escape_stream_directory(tmp_path: Path) -> None:
    collector = fixture_collector(tmp_path)
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    outside = tmp_path / "TEST_ONLY-unrelated.json"
    save_evidence(outside, {"status": "TEST_ONLY_NOT_SOURCE_DATA"})
    state = _job(collector, row)
    state["active_request"] = {"phase": "PUBLISH_PENDING", "packet_path": str(outside)}
    save_evidence(_job_path(collector, row), state)
    with pytest.raises(ValueError, match="escapes its stream"):
        _merge_retained_pages(collector, "spot", "AAAUSDT", "klines", "5m", NOW)
    assert not (collector.history.archive_root / "spot" / "AAAUSDT").exists()


def test_raw_source_receipt_without_pending_page_prevents_another_get(
    tmp_path: Path,
) -> None:
    collector = fixture_collector(tmp_path)
    staged = stage_fixture_page(collector)
    staged.unlink()  # TEST_ONLY simulate a crash before the decoded publication packet.
    transport = cast(FixtureTransport, collector.spot)
    transport.calls.clear()
    row: dict[str, object] = {"market": "spot", "symbol": "AAAUSDT", "timeframe": "5m"}
    assert (
        _collect_turn(collector, row, NOW, ScopedRetryPolicy())["status"] == "PROGRESS"
    )
    assert transport.calls == []
    counters = cast(dict[str, int], _job(collector, row)["counters"])
    assert counters["get_attempts"] == 0
    assert counters["canonical_inserts"] == counters["retained_page_reuses"] == 1


def test_pending_publication_does_not_wait_for_network_retry_due(
    tmp_path: Path,
) -> None:
    collector = fixture_collector(tmp_path)
    stage_fixture_page(collector)
    row: dict[str, object] = {
        "market": "spot",
        "symbol": "AAAUSDT",
        "timeframe": "5m",
        "status": "PARTIAL",
        "tail_ready": False,
    }
    state = _job(collector, row)
    state["next_due_at"] = (NOW + timedelta(hours=1)).isoformat()
    save_evidence(_job_path(collector, row), state)
    transport = cast(FixtureTransport, collector.spot)
    transport.calls.clear()
    assert (
        _scheduled_turn(collector, row, NOW, ScopedRetryPolicy())["status"]
        == "PROGRESS"
    )
    assert transport.calls == []
    assert (
        cast(dict[str, int], _job(collector, row)["counters"])["canonical_inserts"] == 1
    )

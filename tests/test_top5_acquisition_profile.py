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

from ai4binance.core.errors import ExchangeRateLimitError, ExchangeTransportError
from ai4binance.data.acquisition_profile import (
    PROFILE_TIMEFRAMES,
    SAFE_STATE,
    acquisition_window,
    content_digest,
    exact_quote_volume,
    previous_calendar_month,
    stream_health,
    validate_native_rows,
)
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_continuous import ContinuousMarketHistory
from ai4binance.data.market_history_sync import (
    BinanceVisionArchiveCache,
    MarketHistorySynchronizer,
)
from ai4binance.data.scoped_history import (
    _collect_turn,
    _merge_retained_pages,
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
)
from ai4binance.integrations.binance import BinanceMarketUniverseProvider

NOW = datetime(2026, 9, 2, 12, 4, tzinfo=UTC)
ASSETS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")


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

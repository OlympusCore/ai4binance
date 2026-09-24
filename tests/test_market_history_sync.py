"""Proof contracts for low-bandwidth public market-history collection."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

from ai4binance.cli.market_data import main as market_history_main
from ai4binance.data.market_history_sync import (
    MARKET_HISTORY_TIMEFRAMES,
    BinanceVisionArchiveCache,
    MarketHistoryIntegrityError,
    MarketHistorySourceUnavailableError,
    MarketHistorySupervisor,
    MarketHistorySynchronizer,
    read_cached_market_universe,
)
from ai4binance.integrations.binance import BinanceEligibleMarketSnapshot
from ai4binance.schemas import OHLCVCandle

DAY = date(2026, 9, 1)
OBSERVED_AT = datetime(2026, 9, 2, 12, tzinfo=UTC)


@pytest.mark.parametrize("age_minutes", [-1, 0, 5, 6])
def test_shared_universe_cache_requires_current_safe_evidence(
    tmp_path: Path, age_minutes: int
) -> None:
    path = tmp_path / "universe-v3.json"
    payload = {
        "observed_at": (OBSERVED_AT - timedelta(minutes=age_minutes)).isoformat(),
        "spot_symbols": ["BTCUSDT"],
        "futures_symbols": ["BTCUSDT"],
        "excluded_assets": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = read_cached_market_universe(path, OBSERVED_AT)
    if 0 <= age_minutes <= 5:
        assert result is not None
        assert result.spot_symbols == ("BTCUSDT",)
    else:
        assert result is None
    payload["execution_allowed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_cached_market_universe(path, OBSERVED_AT) is None


def test_archive_cache_downloads_once_then_verifies_local_source(
    tmp_path: Path,
) -> None:
    key = "data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09-01.zip"
    payload = _kline_zip(5)
    responses = _source_responses({key: payload})
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return responses[url]

    cache = BinanceVisionArchiveCache(tmp_path, fetch)
    first, first_payload = cache.verified(key, kind="ohlcv")
    second, second_payload = cache.verified(key, kind="ohlcv")

    assert first.cache_hit is False
    assert first.network_request_count == 2
    assert first.downloaded_bytes > len(payload)
    assert second.cache_hit is True
    assert second.network_request_count == 0
    assert first_payload == second_payload == payload
    assert len(calls) == 2

    cached = tmp_path / key
    cached.write_bytes(b"tampered")
    with pytest.raises(MarketHistoryIntegrityError, match="checksum mismatch"):
        cache.verified(key, kind="ohlcv")


def test_archive_cache_rejects_unsafe_and_unpublished_sources(tmp_path: Path) -> None:
    def missing(url: str) -> bytes:
        raise HTTPError(url, 404, "missing", Message(), None)

    cache = BinanceVisionArchiveCache(tmp_path, missing)
    with pytest.raises(ValueError, match="unsafe"):
        cache.verified("../outside.zip", kind="ohlcv")
    with pytest.raises(MarketHistorySourceUnavailableError):
        cache.verified(
            "data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09-01.zip",
            kind="ohlcv",
        )


def test_archive_cache_recovers_one_missing_half_without_redownloading(
    tmp_path: Path,
) -> None:
    key = "data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-09-01.zip"
    payload = _kline_zip(5)
    responses = _source_responses({key: payload})
    archive_path = tmp_path / key
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(payload)
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return responses[url]

    source, recovered = BinanceVisionArchiveCache(tmp_path, fetch).verified(
        key, kind="ohlcv"
    )

    assert recovered == payload
    assert source.network_request_count == 1
    assert source.downloaded_bytes < len(payload)
    assert calls == [f"https://data.binance.vision/{key}.CHECKSUM"]


def test_synchronizer_materializes_all_timeframes_and_futures_detail(
    tmp_path: Path,
) -> None:
    spot_keys = {
        timeframe: _daily_key("spot", "BTCUSDT", "klines", timeframe)
        for timeframe in MARKET_HISTORY_TIMEFRAMES
    }
    futures_keys = {
        timeframe: _daily_key("futures/um", "BTCUSDT", "klines", timeframe)
        for timeframe in MARKET_HISTORY_TIMEFRAMES
    }
    mark_key = _daily_key("futures/um", "BTCUSDT", "markPriceKlines", "5m")
    metrics_key = "data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-09-01.zip"
    funding_key = (
        "data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-08.zip"
    )
    sources = {
        **{
            key: _kline_zip(1440 // _timeframe_minutes(timeframe), timeframe=timeframe)
            for timeframe, key in spot_keys.items()
        },
        **{
            key: _kline_zip(
                1440 // _timeframe_minutes(timeframe), timeframe=timeframe, header=True
            )
            for timeframe, key in futures_keys.items()
        },
        mark_key: _kline_zip(
            288, timeframe="5m", header=True, price_offset=Decimal("0.1")
        ),
        metrics_key: _simple_csv_zip(
            "create_time,symbol,sum_open_interest\n2026-09-01 00:00:00,BTCUSDT,123\n"
        ),
        funding_key: _simple_csv_zip(
            "calc_time,funding_interval_hours,last_funding_rate\n"
            "1788220800000,8,0.0001\n"
        ),
    }
    responses = _source_responses(sources)
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return responses[url]

    universe_provider = _UniverseProvider()
    synchronizer = MarketHistorySynchronizer(
        universe_provider=universe_provider,  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", fetch),
        state_path=tmp_path / "state" / "market-history-latest.json",
    )

    first = synchronizer.sync_day(DAY, observed_at=OBSERVED_AT)
    second = synchronizer.sync_day(DAY, observed_at=OBSERVED_AT + timedelta(hours=1))

    assert first.blockers == ()
    assert len(first.results) == 2
    assert all(result.status == "SYNCED" for result in first.results)
    assert len(first.results[0].manifests) == 5
    assert len(first.results[1].manifests) == 6
    assert all(result.receipt_path for result in first.results)
    assert {source.kind for source in first.results[1].detail_sources} == {
        "ohlcv",
        "mark_price",
        "open_interest_and_positioning",
        "funding_rate",
    }
    assert first.network_request_count == 26
    assert second.network_request_count == 0
    assert len(calls) == 26
    # The active exchange universe is intentionally revalidated after its
    # five-minute TTL; cached immutable archives still prevent re-downloads.
    assert universe_provider.calls == 2
    for market in ("spot", "usd_m_futures"):
        for timeframe in MARKET_HISTORY_TIMEFRAMES:
            assert (
                tmp_path / "market" / market / "BTCUSDT" / f"{timeframe}.parquet"
            ).is_file()
    state = json.loads(synchronizer.state_path.read_text(encoding="utf-8"))
    assert state["network_request_count"] == 0
    assert state["execution_allowed"] is False
    assert state["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    receipt = json.loads(Path(first.results[1].receipt_path or "").read_text())
    assert len(receipt["dataset_manifests"]) == 6
    assert len(receipt["source_files"]) == 8
    assert receipt["wallet_data_included"] is False


def test_synchronizer_and_supervisor_fail_closed_without_universe(
    tmp_path: Path,
) -> None:
    synchronizer = MarketHistorySynchronizer(
        universe_provider=_BlockedUniverseProvider(),  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", lambda url: b""),
        state_path=tmp_path / "state" / "market-history-latest.json",
    )
    report = synchronizer.sync_day(DAY, observed_at=OBSERVED_AT)

    assert report.blockers == ("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",)
    assert report.execution_allowed is False

    sleeps: list[float] = []
    supervisor = MarketHistorySupervisor(
        synchronizer=synchronizer,
        interval_seconds=900,
        lock_path=(tmp_path / "market-history.lock").resolve(),
        sleeper=sleeps.append,
        clock=lambda: OBSERVED_AT,
    )
    assert supervisor.run(max_cycles=1) == 1
    assert sleeps == []


def test_supervisor_retries_recoverable_cycle_failure_without_exiting(
    tmp_path: Path,
) -> None:
    attempts: list[datetime] = []
    failures: list[tuple[datetime, str]] = []
    sleeps: list[float] = []

    def cycle(now: datetime) -> None:
        attempts.append(now)
        if len(attempts) == 1:
            raise OSError("temporary transport failure")

    supervisor = MarketHistorySupervisor(
        synchronizer=object(),  # type: ignore[arg-type]
        interval_seconds=900,
        lock_path=(tmp_path / "market-history.lock").resolve(),
        sleeper=sleeps.append,
        clock=lambda: OBSERVED_AT,
        cycle=cycle,
        on_recoverable_error=lambda now, error: failures.append(
            (now, type(error).__name__)
        ),
    )

    assert supervisor.run(max_cycles=2) == 1
    assert attempts == [OBSERVED_AT, OBSERVED_AT]
    assert failures == [(OBSERVED_AT, "OSError")]
    assert len(sleeps) == 1
    assert 1 <= sleeps[0] <= 900


def test_supervisor_fast_retries_transient_universe_blocker(tmp_path: Path) -> None:
    sleeps: list[float] = []
    attempts = 0

    def cycle(_now: datetime) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return {
            "blockers": (
                ["PUBLIC_MARKET_LIQUIDITY_UNIVERSE_UNAVAILABLE"]
                if attempts == 1
                else []
            )
        }

    supervisor = MarketHistorySupervisor(
        synchronizer=object(),  # type: ignore[arg-type]
        interval_seconds=900,
        lock_path=(tmp_path / "market-history.lock").resolve(),
        sleeper=sleeps.append,
        clock=lambda: OBSERVED_AT,
        cycle=cycle,
    )

    assert supervisor.run(max_cycles=2) == 2
    assert sleeps == [30]


def test_supervisor_does_not_hide_programming_errors(tmp_path: Path) -> None:
    supervisor = MarketHistorySupervisor(
        synchronizer=object(),  # type: ignore[arg-type]
        interval_seconds=900,
        lock_path=(tmp_path / "market-history.lock").resolve(),
        cycle=lambda now: (_ for _ in ()).throw(TypeError("programming error")),
    )

    with pytest.raises(TypeError, match="programming error"):
        supervisor.run(max_cycles=1)


def test_standalone_status_command_reads_local_state_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_path = tmp_path / "market-history-latest.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "READY",
                "blockers": [],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI4BINANCE_MARKET_HISTORY_STATE_PATH", str(state_path))

    assert market_history_main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "market-history-status"
    assert payload["execution_allowed"] is False


class _UniverseProvider:
    def __init__(self) -> None:
        self.calls = 0

    def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
        self.calls += 1
        return BinanceEligibleMarketSnapshot(
            spot_symbols=("BTCUSDT",),
            futures_symbols=("BTCUSDT",),
            excluded_assets=(("USDC", ("STABLECOIN_BASE_ASSET",)),),
        )


class _BlockedUniverseProvider:
    @staticmethod
    def eligible_market_snapshot() -> BinanceEligibleMarketSnapshot:
        return BinanceEligibleMarketSnapshot(
            spot_symbols=(),
            futures_symbols=(),
            blockers=("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",),
        )


def test_eligible_universe_force_refreshes_current_exchange_metadata(
    tmp_path: Path,
) -> None:
    provider = _UniverseProvider()
    synchronizer = MarketHistorySynchronizer(
        universe_provider=provider,  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", lambda _: b""),
        state_path=tmp_path / "state.json",
    )

    first = synchronizer._eligible_universe(OBSERVED_AT, force_refresh=True)
    refreshed_at = OBSERVED_AT + timedelta(minutes=1)
    second = synchronizer._eligible_universe(refreshed_at, force_refresh=True)

    assert first.spot_symbols == second.spot_symbols == ("BTCUSDT",)
    assert provider.calls == 2
    cached = read_cached_market_universe(
        tmp_path / "sources" / "universe-v2.json", refreshed_at
    )
    assert cached is not None
    assert cached.futures_symbols == ("BTCUSDT",)


def test_force_refresh_falls_back_only_to_current_verified_universe_cache(
    tmp_path: Path,
) -> None:
    class TransientProvider:
        calls = 0

        def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
            self.calls += 1
            if self.calls == 1:
                return BinanceEligibleMarketSnapshot(
                    spot_symbols=("BTCUSDT",), futures_symbols=("BTCUSDT",)
                )
            return BinanceEligibleMarketSnapshot(
                spot_symbols=(),
                futures_symbols=(),
                blockers=("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",),
            )

    provider = TransientProvider()
    synchronizer = MarketHistorySynchronizer(
        universe_provider=provider,  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", lambda _: b""),
        state_path=tmp_path / "state.json",
    )

    synchronizer._eligible_universe(OBSERVED_AT, force_refresh=True)
    current = synchronizer._eligible_universe(
        OBSERVED_AT + timedelta(minutes=1), force_refresh=True
    )
    stale = synchronizer._eligible_universe(
        OBSERVED_AT + timedelta(minutes=6), force_refresh=True
    )

    assert current.spot_symbols == ("BTCUSDT",)
    assert not current.blockers
    assert stale.blockers == ("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",)


def test_eligible_universe_uses_the_bounded_top_volume_provider_when_available(
    tmp_path: Path,
) -> None:
    class TopVolumeUniverseProvider:
        calls: list[int]

        def __init__(self) -> None:
            self.calls = []

        def top_volume_eligible_market_snapshot(
            self, *, max_symbols_per_market: int
        ) -> BinanceEligibleMarketSnapshot:
            self.calls.append(max_symbols_per_market)
            return BinanceEligibleMarketSnapshot(
                spot_symbols=("BTCUSDT",), futures_symbols=("ETHUSDT",)
            )

        def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
            raise AssertionError("metadata-only universe must not be used")

    provider = TopVolumeUniverseProvider()
    synchronizer = MarketHistorySynchronizer(
        universe_provider=provider,  # type: ignore[arg-type]
        archive_root=tmp_path / "market",
        source_cache=BinanceVisionArchiveCache(tmp_path / "sources", lambda _: b""),
        state_path=tmp_path / "state.json",
    )

    snapshot = synchronizer._eligible_universe(OBSERVED_AT, force_refresh=True)

    assert provider.calls == [50]
    assert snapshot.spot_symbols == ("BTCUSDT",)
    assert snapshot.futures_symbols == ("ETHUSDT",)


def _candle(index: int) -> OHLCVCandle:
    value = Decimal(100 + index)
    return OHLCVCandle(
        timestamp=datetime.combine(DAY, datetime.min.time(), tzinfo=UTC)
        + timedelta(minutes=index),
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value + Decimal("0.5"),
        volume=Decimal("1"),
    )


def _daily_key(market: str, symbol: str, kind: str, timeframe: str = "5m") -> str:
    return (
        f"data/{market}/daily/{kind}/{symbol}/{timeframe}/"
        f"{symbol}-{timeframe}-{DAY.isoformat()}.zip"
    )


def _kline_zip(
    count: int,
    *,
    timeframe: str = "5m",
    header: bool = False,
    price_offset: Decimal = Decimal("0"),
) -> bytes:
    lines: list[str] = []
    if header:
        lines.append(
            "open_time,open,high,low,close,volume,close_time,quote_volume,"
            "count,taker_buy_volume,taker_buy_quote_volume,ignore"
        )
    start = datetime.combine(DAY, datetime.min.time(), tzinfo=UTC)
    for index in range(count):
        timestamp = int(
            (
                start + timedelta(minutes=index * _timeframe_minutes(timeframe))
            ).timestamp()
            * 1000
        )
        value = Decimal(100 + index) + price_offset
        lines.append(
            f"{timestamp},{value},{value + 1},{value - 1},{value + Decimal('0.5')},"
            f"1,{timestamp + 59999},1,1,1,1,0"
        )
    return _simple_csv_zip("\n".join(lines) + "\n")


def _timeframe_minutes(timeframe: str) -> int:
    return {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}[timeframe]


def _simple_csv_zip(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.csv", text)
    return buffer.getvalue()


def _source_responses(sources: dict[str, bytes]) -> dict[str, bytes]:
    responses: dict[str, bytes] = {}
    for key, payload in sources.items():
        url = f"https://data.binance.vision/{key}"
        digest = hashlib.sha256(payload).hexdigest().encode("ascii")
        responses[url] = payload
        responses[f"{url}.CHECKSUM"] = digest + b"  archive.zip\n"
    return responses

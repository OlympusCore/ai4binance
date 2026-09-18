"""Offline archive ingestion rejects corrupt data and bounds transport failures."""

import hashlib
import io
import json
import urllib.request
import zipfile
from dataclasses import replace
from datetime import timedelta
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from ai4binance.data.market_history_sync import (
    BinanceVisionArchiveCache,
    MarketHistoryIntegrityError,
    MarketHistorySupervisor,
    MarketHistorySynchronizer,
    _csv_rows,
    _parse_kline_archive,
    _validate_csv_archive,
    read_cached_market_universe,
)
from ai4binance.integrations.binance import (
    BinanceEligibleMarketSnapshot,
    BinanceMarketUniverseProvider,
)
from tests.test_market_history_sync import DAY, OBSERVED_AT, _simple_csv_zip


@pytest.mark.parametrize(
    "options", [{"timeout_seconds": 0}, {"maximum_response_bytes": 1023}]
)
def test_archive_transport_requires_safe_bounds(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match=r"positive|safe range"):
        BinanceVisionArchiveCache.with_network(tmp_path, **options)


@pytest.mark.parametrize("failure", [404, 429, 500, "io"])
def test_archive_transport_cooldown_after_offline_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: int | str
) -> None:
    error = (
        OSError("offline")
        if failure == "io"
        else HTTPError(
            "https://data.binance.vision/test.zip",
            int(failure),
            "offline",
            Message(),
            None,
        )
    )
    opener = Mock(side_effect=error)
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    cache = BinanceVisionArchiveCache.with_network(tmp_path)
    with pytest.raises(OSError, match="offline"):
        cache.fetch("https://data.binance.vision/test.zip")
    if failure == 404:
        with pytest.raises(HTTPError):
            cache.fetch("https://data.binance.vision/test.zip")
        assert opener.call_count == 2
    else:
        with pytest.raises(OSError, match="cooling down"):
            cache.fetch("https://data.binance.vision/test.zip")
        opener.assert_called_once()


def test_archive_transport_bounds_responses_and_rejects_unapproved_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opener = Mock(return_value=io.BytesIO(b"x" * 1025))
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    cache = BinanceVisionArchiveCache.with_network(
        tmp_path, maximum_response_bytes=1024
    )
    with pytest.raises(ValueError, match="allowlist"):
        cache.fetch("https://unapproved.invalid/test.zip")
    opener.assert_not_called()
    with pytest.raises(MarketHistoryIntegrityError, match="size limit"):
        cache.fetch("https://data.binance.vision/test.zip")


def test_cache_resumes_from_existing_checksum_without_redownloading(
    tmp_path: Path,
) -> None:
    payload = _simple_csv_zip("field\n1\n")
    checksum = hashlib.sha256(payload).hexdigest().encode("ascii")
    path = tmp_path / "data" / "sample.zip.CHECKSUM"
    path.parent.mkdir()
    path.write_bytes(checksum)
    fetch = Mock(return_value=payload)
    cache = BinanceVisionArchiveCache(tmp_path, fetch)
    source, restored = cache.verified("data/sample.zip", kind="test")
    assert restored == payload
    assert source.network_request_count == 1
    assert source.downloaded_bytes == len(payload)
    fetch.assert_called_once_with("https://data.binance.vision/data/sample.zip")


@pytest.mark.parametrize("checksum", [b"", b"\xff"])
def test_cache_rejects_malformed_checksum_before_persisting(
    tmp_path: Path, checksum: bytes
) -> None:
    cache = BinanceVisionArchiveCache(
        tmp_path, Mock(side_effect=[checksum, b"payload"])
    )
    with pytest.raises(MarketHistoryIntegrityError, match="checksum mismatch"):
        cache.verified("data/sample.zip", kind="test")
    assert not list(tmp_path.rglob("*.zip"))


@pytest.mark.parametrize(
    ("payload", "message"),
    [(b"", "size"), (b"not a ZIP", "invalid ZIP"), (_simple_csv_zip(""), "empty")],
)
def test_csv_archives_reject_missing_and_corrupt_content(
    payload: bytes, message: str
) -> None:
    with pytest.raises(MarketHistoryIntegrityError, match=message):
        _validate_csv_archive("sample.zip", payload)


@pytest.mark.parametrize(
    "names", [("one.csv", "two.csv"), ("nested/one.csv",), ("one.txt",)]
)
def test_csv_archive_members_must_be_single_safe_csv(names: tuple[str, ...]) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name in names:
            archive.writestr(name, "field\n1\n")
    with pytest.raises(MarketHistoryIntegrityError, match=r"exactly one|unsafe"):
        _csv_rows("sample.zip", stream.getvalue())


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("1788220800000,100", "incomplete"),
        ("1788220800000,bad,101,99,100,1", "invalid values"),
        ("header\n", "row count"),
        ("1788220801000,100,101,99,100,1", "timestamp"),
        ("1788220800000,100,101,99,100,1\n1788220920000,100,101,99,100,1", "cadence"),
    ],
)
def test_kline_parser_rejects_incomplete_nonfinite_and_noncontiguous_rows(
    rows: str, message: str
) -> None:
    with pytest.raises(MarketHistoryIntegrityError, match=message):
        _parse_kline_archive("sample.zip", _simple_csv_zip(rows), DAY, "5m")


def test_universe_cache_rejects_naive_or_oversized_evidence(tmp_path: Path) -> None:
    path = tmp_path / "universe.json"
    path.write_text(" " * 2_000_001, encoding="utf-8")
    assert read_cached_market_universe(path, OBSERVED_AT) is None
    path.write_text(
        json.dumps({"observed_at": OBSERVED_AT.replace(tzinfo=None).isoformat()}),
        encoding="utf-8",
    )
    assert read_cached_market_universe(path, OBSERVED_AT) is None
    assert read_cached_market_universe(path, OBSERVED_AT, max_age=timedelta(0)) is None


@pytest.mark.parametrize(("failure", "status"), [(404, "DEFERRED"), (500, "BLOCKED")])
def test_sync_reports_missing_and_failed_sources_for_both_markets(
    tmp_path: Path, failure: int, status: str
) -> None:
    def fetch(url: str) -> bytes:
        raise HTTPError(url, failure, "offline", Message(), None)

    provider = Mock(spec=BinanceMarketUniverseProvider)
    provider.coin_m_transport = None
    snapshot = BinanceEligibleMarketSnapshot(
        spot_symbols=("BTCUSDT",), futures_symbols=("BTCUSDT",), excluded_assets=()
    )
    provider.top_volume_eligible_market_snapshot.return_value = snapshot
    provider.eligible_market_snapshot.return_value = snapshot
    synchronizer = MarketHistorySynchronizer(
        provider,
        tmp_path / "archive",
        BinanceVisionArchiveCache(tmp_path / "cache", fetch),
        tmp_path / "state.json",
    )
    report = synchronizer.sync_day(DAY, observed_at=OBSERVED_AT)
    provider.top_volume_eligible_market_snapshot.assert_called_once_with(
        max_symbols_per_market=50
    )
    provider.eligible_market_snapshot.assert_not_called()
    assert [result.status for result in report.results] == [status, status]
    assert len(report.blockers) == 2
    assert report.execution_allowed is False
    assert all(not result.manifests for result in report.results)
    for at, day, message in (
        (OBSERVED_AT.replace(tzinfo=None), DAY, "timezone-aware"),
        (OBSERVED_AT, OBSERVED_AT.date(), "fully observable"),
    ):
        with pytest.raises(ValueError, match=message):
            synchronizer.sync_day(day, observed_at=at)


def test_history_supervisor_rejects_unbounded_or_ambiguous_runs(tmp_path: Path) -> None:
    supervisor = MarketHistorySupervisor(Mock(), 60, tmp_path / "lease.lock")
    with pytest.raises(ValueError, match="interval"):
        replace(supervisor, interval_seconds=59)
    with pytest.raises(ValueError, match="absolute"):
        replace(supervisor, lock_path=type(tmp_path)("relative.lock"))
    with pytest.raises(ValueError, match="positive"):
        supervisor.run(max_cycles=0)

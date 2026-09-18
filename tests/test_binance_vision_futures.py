"""Checksum-bound Binance Vision Futures replay ingestion tests."""

from __future__ import annotations

import io
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.data.binance_vision_futures import (
    BinanceVisionFuturesIntegrityError,
    BinanceVisionFuturesReplayIngestor,
)
from ai4binance.validation import RuntimeFuturesReplayLoader
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)


def _zip_csv(name: str, header: str, rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "\n".join((header, *rows)) + "\n")
    return buffer.getvalue()


def _source_payloads(
    *,
    mark_offset_ms: int = 0,
    replay_day: date = date(2024, 1, 1),
    funding_days: tuple[date, ...] | None = None,
    funding_offset_ms: int = 0,
    interval_minutes: int = 60,
) -> dict[str, bytes]:
    start = datetime.combine(replay_day, datetime.min.time(), tzinfo=UTC)
    funding_days = funding_days or (replay_day,)
    kline_header = (
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
        "taker_buy_volume,taker_buy_quote_volume,ignore"
    )
    kline_rows: list[str] = []
    mark_rows: list[str] = []
    for index in range(1440 // interval_minutes):
        open_time = int(
            (start + timedelta(minutes=index * interval_minutes)).timestamp() * 1000
        )
        close_time = open_time + interval_minutes * 60_000 - 1
        kline_rows.append(f"{open_time},100,102,99,101,10,{close_time},1000,20,5,500,0")
        mark_rows.append(
            f"{open_time + mark_offset_ms},100,102,99,100.5,0,{close_time},0,3600,0,0,0"
        )
    metrics_rows = [
        (
            f"{(start + timedelta(minutes=5 * index)):%Y-%m-%d %H:%M:%S},"
            f"BTCUSDT,{1000 + index},{100_000 + index},1,1,1,1"
        )
        for index in range(288)
    ]
    funding_rows: list[str] = []
    for day in funding_days:
        funding_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        for index in (0, 8, 16):
            timestamp = (
                int((funding_start + timedelta(hours=index)).timestamp() * 1000)
                + funding_offset_ms
            )
            funding_rows.append(f"{timestamp},8,0.0001")
    day_text = replay_day.isoformat()
    month_text = replay_day.strftime("%Y-%m")
    return {
        "ohlcv": _zip_csv(f"BTCUSDT-1h-{day_text}.csv", kline_header, kline_rows),
        "mark_price": _zip_csv(f"BTCUSDT-1h-{day_text}.csv", kline_header, mark_rows),
        "open_interest": _zip_csv(
            f"BTCUSDT-metrics-{day_text}.csv",
            (
                "create_time,symbol,sum_open_interest,sum_open_interest_value,"
                "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
                "count_long_short_ratio,sum_taker_long_short_vol_ratio"
            ),
            metrics_rows,
        ),
        "funding_rate": _zip_csv(
            f"BTCUSDT-fundingRate-{month_text}.csv",
            "calc_time,funding_interval_hours,last_funding_rate",
            funding_rows,
        ),
    }


def _fetcher(
    ingestor: BinanceVisionFuturesReplayIngestor,
    payloads: dict[str, bytes],
    *,
    corrupt_kind: str | None = None,
) -> Callable[[str], bytes]:
    keys = ingestor._source_keys("BTCUSDT", date(2024, 1, 1))

    def fetch(url: str) -> bytes:
        for kind, key in keys.items():
            if url.endswith(f"/{key}.CHECKSUM"):
                digest = (
                    "0" * 64
                    if kind == corrupt_kind
                    else sha256(payloads[kind]).hexdigest()
                )
                return f"{digest}  {Path(key).name}\n".encode()
            if url.endswith(f"/{key}"):
                return payloads[kind]
        raise AssertionError(f"unexpected URL: {url}")

    return fetch


def _ingestor(
    tmp_path: Path,
    payloads: dict[str, bytes],
) -> BinanceVisionFuturesReplayIngestor:
    placeholder = BinanceVisionFuturesReplayIngestor(tmp_path, lambda url: b"")
    return BinanceVisionFuturesReplayIngestor(
        tmp_path,
        _fetcher(placeholder, payloads),
    )


@pytest.mark.parametrize("timeframe", ["5m", "15m", "1h", "4h", "1d"])
def test_futures_replay_source_keys_are_timeframe_scoped(
    tmp_path: Path,
    timeframe: str,
) -> None:
    ingestor = BinanceVisionFuturesReplayIngestor(
        tmp_path,
        lambda url: b"",
        timeframe=timeframe,
    )

    keys = ingestor._source_keys("BTCUSDT", date(2024, 1, 1))

    assert f"/klines/BTCUSDT/{timeframe}/" in keys["ohlcv"]
    assert f"/markPriceKlines/BTCUSDT/{timeframe}/" in keys["mark_price"]


def test_futures_replay_ingestor_rejects_unsupported_timeframe(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="timeframe is unsupported"):
        BinanceVisionFuturesReplayIngestor(
            tmp_path,
            lambda url: b"",
            timeframe="1m",
        )


@pytest.mark.parametrize(
    ("timeframe", "minutes"),
    [("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440)],
)
def test_futures_replay_ingests_exact_timeframe_and_rejects_wrong_mark_close(
    tmp_path: Path,
    timeframe: str,
    minutes: int,
) -> None:
    payloads = _source_payloads(interval_minutes=minutes)
    seed = BinanceVisionFuturesReplayIngestor(
        tmp_path, lambda url: b"", timeframe=timeframe
    )
    ingestor = BinanceVisionFuturesReplayIngestor(
        tmp_path, _fetcher(seed, payloads), timeframe=timeframe
    )
    result = ingestor.sync_day(
        "BTCUSDT", date(2024, 1, 1), observed_at=datetime(2024, 2, 1, tzinfo=UTC)
    )
    assert len(result.dataset.candles) == 1440 // minutes
    assert result.dataset.timeframe == timeframe
    payloads["mark_price"] = _source_payloads(
        interval_minutes=15 if minutes != 15 else 60
    )["mark_price"]
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="mark-price"):
        ingestor.sync_day(
            "BTCUSDT", date(2024, 1, 1), observed_at=datetime(2024, 2, 1, tzinfo=UTC)
        )


def test_futures_sync_builds_checksum_bound_replay_artifact(tmp_path: Path) -> None:
    observed_at = datetime(2024, 2, 1, tzinfo=UTC)
    result = _ingestor(tmp_path, _source_payloads()).sync_day(
        "btcusdt",
        date(2024, 1, 1),
        observed_at=observed_at,
    )

    assert len(result.dataset.candles) == 24
    assert len(result.source_files) == 4
    assert all(len(source.sha256) == 64 for source in result.source_files)
    assert result.execution_allowed is False
    artifact = Path(result.artifact_path)
    assert sha256(artifact.read_bytes()).hexdigest() == result.artifact_sha256
    loaded = RuntimeFuturesReplayLoader(tmp_path).load(artifact.name)
    assert loaded.dataset_sha256 == result.dataset.dataset_sha256
    assert len(loaded.derivatives.series[DerivativesMetric.FUNDING_RATE]) == 3
    marks = loaded.derivatives.series[DerivativesMetric.MARK_PRICE]
    assert len(marks) == 24
    assert marks[0].value == marks[-1].value == pytest.approx(100.5)
    assert {key for key in marks[0].attributes if key.endswith("_source_sha256")} == {
        "funding_rate_source_sha256",
        "mark_price_source_sha256",
        "ohlcv_source_sha256",
        "open_interest_source_sha256",
    }


def test_futures_sync_uses_exact_public_rest_points_when_vision_metrics_are_sparse(
    tmp_path: Path,
) -> None:
    replay_day = date(2024, 1, 1)
    observed_at = datetime(2024, 2, 1, tzinfo=UTC)
    payloads = _source_payloads(replay_day=replay_day)

    class ExactReplayClient:
        def replay_history(
            self,
            symbol: str,
            period: str,
            start: datetime,
            end: datetime,
            *,
            observed_at: datetime,
        ) -> DerivativesDataset:
            del end
            duration = timedelta(hours=1) if period == "1h" else timedelta(minutes=5)
            timestamps = tuple(start + duration * index for index in range(24))
            provenance = Provenance(
                "BINANCE_USD_M_PUBLIC_REST",
                observed_at,
                "https://fapi.binance.com/futures/data/openInterestHist",
            )

            def points(
                metric: DerivativesMetric, value: str
            ) -> tuple[MetricPoint, ...]:
                return tuple(
                    MetricPoint(metric, timestamp, Decimal(value), provenance)
                    for timestamp in timestamps
                )

            return DerivativesDataset(
                symbol,
                observed_at,
                {
                    DerivativesMetric.MARK_PRICE: points(
                        DerivativesMetric.MARK_PRICE, "100"
                    ),
                    DerivativesMetric.OPEN_INTEREST: points(
                        DerivativesMetric.OPEN_INTEREST, "1000"
                    ),
                    DerivativesMetric.OPEN_INTEREST_VALUE: points(
                        DerivativesMetric.OPEN_INTEREST_VALUE, "100000"
                    ),
                    DerivativesMetric.FUNDING_RATE: (
                        MetricPoint(
                            DerivativesMetric.FUNDING_RATE,
                            start,
                            Decimal("0.0001"),
                            provenance,
                        ),
                    ),
                },
            )

    seed = BinanceVisionFuturesReplayIngestor(tmp_path, lambda _url: b"")
    ingestor = BinanceVisionFuturesReplayIngestor(
        tmp_path,
        _fetcher(seed, payloads),
        derivatives_client=ExactReplayClient(),  # type: ignore[arg-type]
    )
    result = ingestor.sync_range(
        "BTCUSDT", replay_day, replay_day, observed_at=observed_at
    )

    assert len(result.source_files) == 1
    assert result.dataset.derivatives.source == "BINANCE_USD_M_PUBLIC_REST"
    assert tuple(
        point.timestamp
        for point in result.dataset.derivatives.series[DerivativesMetric.OPEN_INTEREST]
    ) == tuple(candle.timestamp for candle in result.dataset.candles)


def test_futures_sync_rejects_missing_public_rest_open_interest_point(
    tmp_path: Path,
) -> None:
    replay_day = date(2024, 1, 1)
    observed_at = datetime(2024, 2, 1, tzinfo=UTC)
    payloads = _source_payloads(replay_day=replay_day)

    class MissingPointClient:
        def replay_history(
            self,
            symbol: str,
            _period: str,
            start: datetime,
            _end: datetime,
            *,
            observed_at: datetime,
        ) -> DerivativesDataset:
            timestamps = tuple(start + timedelta(hours=index) for index in range(24))
            provenance = Provenance(
                "BINANCE_USD_M_PUBLIC_REST",
                observed_at,
                "https://fapi.binance.com/futures/data/openInterestHist",
            )

            def points(metric: DerivativesMetric) -> tuple[MetricPoint, ...]:
                return tuple(
                    MetricPoint(metric, timestamp, Decimal("1"), provenance)
                    for timestamp in timestamps
                )

            return DerivativesDataset(
                symbol,
                observed_at,
                {
                    DerivativesMetric.MARK_PRICE: points(DerivativesMetric.MARK_PRICE),
                    DerivativesMetric.OPEN_INTEREST: points(
                        DerivativesMetric.OPEN_INTEREST
                    )[:-1],
                    DerivativesMetric.OPEN_INTEREST_VALUE: points(
                        DerivativesMetric.OPEN_INTEREST_VALUE
                    ),
                    DerivativesMetric.FUNDING_RATE: (
                        MetricPoint(
                            DerivativesMetric.FUNDING_RATE,
                            start,
                            Decimal("0.0001"),
                            provenance,
                        ),
                    ),
                },
            )

    seed = BinanceVisionFuturesReplayIngestor(tmp_path, lambda _url: b"")
    ingestor = BinanceVisionFuturesReplayIngestor(
        tmp_path,
        _fetcher(seed, payloads),
        derivatives_client=MissingPointClient(),  # type: ignore[arg-type]
    )
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="OPEN_INTEREST"):
        ingestor.sync_day("BTCUSDT", replay_day, observed_at=observed_at)


def test_futures_sync_is_byte_deterministic_for_exact_observation(
    tmp_path: Path,
) -> None:
    observed_at = datetime(2024, 2, 1, tzinfo=UTC)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    payloads = _source_payloads()
    first = _ingestor(first_root, payloads).sync_day(
        "BTCUSDT", date(2024, 1, 1), observed_at=observed_at
    )
    second = _ingestor(second_root, payloads).sync_day(
        "BTCUSDT", date(2024, 1, 1), observed_at=observed_at
    )

    assert first.dataset.dataset_sha256 == second.dataset.dataset_sha256
    assert first.artifact_sha256 == second.artifact_sha256
    assert (
        Path(first.artifact_path).read_bytes()
        == Path(second.artifact_path).read_bytes()
    )


def test_futures_range_deduplicates_monthly_source_and_preserves_cadence(
    tmp_path: Path,
) -> None:
    days = (date(2024, 1, 1), date(2024, 1, 2))
    payloads_by_day = {
        day: _source_payloads(
            replay_day=day,
            funding_days=days,
            funding_offset_ms=1,
        )
        for day in days
    }
    monthly_funding = payloads_by_day[days[0]]["funding_rate"]
    for payloads in payloads_by_day.values():
        payloads["funding_rate"] = monthly_funding
    placeholder = BinanceVisionFuturesReplayIngestor(tmp_path, lambda url: b"")
    url_payloads: dict[str, bytes] = {}
    for day, payloads in payloads_by_day.items():
        for kind, key in placeholder._source_keys("BTCUSDT", day).items():
            payload = payloads[kind]
            existing = url_payloads.setdefault(key, payload)
            assert existing == payload

    def fetch(url: str) -> bytes:
        for key, payload in url_payloads.items():
            if url.endswith(f"/{key}.CHECKSUM"):
                return f"{sha256(payload).hexdigest()}  {Path(key).name}\n".encode()
            if url.endswith(f"/{key}"):
                return payload
        raise AssertionError(f"unexpected URL: {url}")

    result = BinanceVisionFuturesReplayIngestor(tmp_path, fetch).sync_range(
        "BTCUSDT",
        days[0],
        days[-1],
        observed_at=datetime(2024, 2, 1, tzinfo=UTC),
    )

    assert len(result.dataset.candles) == 48
    assert len(result.source_files) == 7
    assert len(result.dataset.derivatives.series[DerivativesMetric.FUNDING_RATE]) == 6
    first_funding = result.dataset.derivatives.series[DerivativesMetric.FUNDING_RATE][0]
    assert first_funding.timestamp == datetime(2024, 1, 1, tzinfo=UTC)
    assert first_funding.attributes["raw_calc_time"].endswith("001")
    coverage = (
        result.dataset.candles[-1].timestamp - result.dataset.candles[0].timestamp
    )
    assert coverage == timedelta(hours=47)


def test_futures_sync_rejects_checksum_and_alignment_failures(
    tmp_path: Path,
) -> None:
    payloads = _source_payloads()
    placeholder = BinanceVisionFuturesReplayIngestor(tmp_path, lambda url: b"")
    corrupt = BinanceVisionFuturesReplayIngestor(
        tmp_path,
        _fetcher(placeholder, payloads, corrupt_kind="open_interest"),
    )
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="checksum mismatch"):
        corrupt.sync_day(
            "BTCUSDT",
            date(2024, 1, 1),
            observed_at=datetime(2024, 2, 1, tzinfo=UTC),
        )

    misaligned = _ingestor(tmp_path, _source_payloads(mark_offset_ms=1))
    with pytest.raises(
        BinanceVisionFuturesIntegrityError,
        match="mark-price",
    ):
        misaligned.sync_day(
            "BTCUSDT",
            date(2024, 1, 1),
            observed_at=datetime(2024, 2, 1, tzinfo=UTC),
        )


def test_futures_sync_rejects_unclosed_day_and_unsafe_archive(
    tmp_path: Path,
) -> None:
    ingestor = _ingestor(tmp_path, _source_payloads())
    with pytest.raises(ValueError, match="fully observable"):
        ingestor.sync_day(
            "BTCUSDT",
            date(2024, 1, 1),
            observed_at=datetime(2024, 1, 1, 12, tzinfo=UTC),
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../unsafe.csv", "x\n")
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="unsafe"):
        BinanceVisionFuturesReplayIngestor._parse_csv_archive(
            "unsafe.zip",
            buffer.getvalue(),
            ("x",),
        )


def test_futures_network_ingestor_enforces_allowlist_and_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        @staticmethod
        def read(size: int) -> bytes:
            return b"x" * size

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, *, timeout: Response(),
    )
    ingestor = BinanceVisionFuturesReplayIngestor.with_network(
        tmp_path,
        timeout_seconds=1,
        maximum_response_bytes=1024,
    )
    with pytest.raises(ValueError, match="allowlist"):
        ingestor.fetch("https://example.test/archive.zip")
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="size limit"):
        ingestor.fetch("https://data.binance.vision/archive.zip")


def test_futures_ingestor_low_level_fail_closed_parsers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        BinanceVisionFuturesReplayIngestor(tmp_path, lambda _url: b"", timeframe="2m")
    with pytest.raises(ValueError, match="positive"):
        BinanceVisionFuturesReplayIngestor.with_network(tmp_path, timeout_seconds=0)
    with pytest.raises(ValueError, match="safe range"):
        BinanceVisionFuturesReplayIngestor.with_network(
            tmp_path, maximum_response_bytes=1
        )
    with pytest.raises(ValueError, match="ASCII"):
        BinanceVisionFuturesReplayIngestor._validate_request(
            "bad-symbol", date(2024, 1, 1), datetime(2024, 2, 1, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        BinanceVisionFuturesReplayIngestor._validate_request(
            "BTCUSDT", date(2024, 1, 1), datetime(2024, 2, 1)
        )
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="timestamp"):
        BinanceVisionFuturesReplayIngestor._milliseconds("bad")
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="metrics timestamp"):
        BinanceVisionFuturesReplayIngestor._metrics_timestamp("bad")
    with pytest.raises(
        BinanceVisionFuturesIntegrityError, match="decimal value is invalid"
    ):
        BinanceVisionFuturesReplayIngestor._decimal("bad")
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="finite"):
        BinanceVisionFuturesReplayIngestor._decimal("NaN")
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="hourly boundary"):
        BinanceVisionFuturesReplayIngestor._funding_timestamp("1704067201500")
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="invalid ZIP"):
        BinanceVisionFuturesReplayIngestor._parse_csv_archive(
            "bad.zip", b"not-a-zip", ("x",)
        )


def test_futures_ingestor_rejects_range_and_kline_mismatch(tmp_path: Path) -> None:
    ingestor = BinanceVisionFuturesReplayIngestor(tmp_path, lambda _url: b"")
    with pytest.raises(ValueError, match="1 to 366"):
        ingestor.sync_range(
            "BTCUSDT",
            date(2024, 1, 2),
            date(2024, 1, 1),
            observed_at=datetime(2024, 2, 1, tzinfo=UTC),
        )
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="close-time"):
        ingestor._require_kline_close_alignment(
            ({"open_time": "0", "close_time": "0"},), "test"
        )
    with pytest.raises(BinanceVisionFuturesIntegrityError, match="OHLCV row"):
        ingestor._candle({}, timedelta(hours=1))

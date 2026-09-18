"""Checksum-verified Binance Vision ingestion tests."""

import io
import json
import urllib.request
import zipfile
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.data import (
    BinanceVisionIngestor,
    BinanceVisionIntegrityError,
    ParquetOHLCVArchive,
)


def zipped_csv(timestamp: int, close: str, *, symbol: str = "HOTUSDT") -> bytes:
    buffer = io.BytesIO()
    row = f"{timestamp},1.0,1.2,0.9,{close},100,0,0,0,0,0,0\n"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{symbol}-1h.csv", row)
    return buffer.getvalue()


def listing(*keys: str) -> bytes:
    contents = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in keys)
    return f"<ListBucketResult>{contents}</ListBucketResult>".encode()


def test_binance_vision_sync_verifies_sources_and_writes_manifests(
    tmp_path: Path,
) -> None:
    monthly_key = "data/spot/monthly/klines/HOTUSDT/1h/HOTUSDT-1h-2026-06.zip"
    daily_key = "data/spot/daily/klines/HOTUSDT/1h/HOTUSDT-1h-2026-07-11.zip"
    monthly = zipped_csv(1_751_328_000_000_000, "1.1")
    daily = zipped_csv(1_752_192_000_000_000, "1.2")

    def fetch(url: str) -> bytes:
        if "monthly%2F" in url or ("monthly/klines" in url and "list-type" in url):
            return listing(monthly_key)
        if "daily%2F" in url or ("daily/klines" in url and "list-type" in url):
            return listing(daily_key)
        for key, payload in ((monthly_key, monthly), (daily_key, daily)):
            if url.endswith(f"/{key}.CHECKSUM"):
                return f"{sha256(payload).hexdigest()}  {Path(key).name}\n".encode()
            if url.endswith(f"/{key}"):
                return payload
        raise AssertionError(f"unexpected URL: {url}")

    archive = ParquetOHLCVArchive(tmp_path)
    result = BinanceVisionIngestor(archive, fetch).sync(
        "HOTUSDT",
        ("1h",),
        as_of=date(2026, 7, 13),
    )[0]

    assert result.dataset_manifest.row_count == 2
    assert result.dataset_manifest.sha256 == archive.manifest("HOTUSDT", "1h").sha256
    assert len(result.source_files) == 2
    assert all(len(item.sha256) == 64 for item in result.source_files)
    stored_timestamp = archive.read("HOTUSDT", "1h")[0].timestamp
    assert stored_timestamp.tzinfo is not None
    assert stored_timestamp.utcoffset() == UTC.utcoffset(stored_timestamp)
    source_manifest = json.loads(Path(result.source_manifest_path).read_text())
    assert source_manifest["source_file_count"] == 2
    assert source_manifest["wallet_data_included"] is False
    assert source_manifest["execution_allowed"] is False


def test_binance_vision_sync_supports_btcusdt_for_validation_backtests(
    tmp_path: Path,
) -> None:
    monthly_key = "data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2026-06.zip"
    payload = zipped_csv(1_751_328_000_000_000, "1.1", symbol="BTCUSDT")

    def fetch(url: str) -> bytes:
        if "list-type" in url:
            return listing(monthly_key) if "monthly" in url else listing()
        if url.endswith(f"/{monthly_key}.CHECKSUM"):
            return f"{sha256(payload).hexdigest()}  {Path(monthly_key).name}\n".encode()
        if url.endswith(f"/{monthly_key}"):
            return payload
        raise AssertionError(f"unexpected URL: {url}")

    archive = ParquetOHLCVArchive(tmp_path)
    result = BinanceVisionIngestor(archive, fetch).sync(
        "BTCUSDT",
        ("1h",),
        as_of=date(2026, 7, 13),
    )[0]

    assert result.symbol == "BTCUSDT"
    assert archive.manifest("BTCUSDT", "1h").row_count == 1
    source_manifest = json.loads(Path(result.source_manifest_path).read_text())
    assert source_manifest["symbol"] == "BTCUSDT"
    assert source_manifest["wallet_data_included"] is False
    assert source_manifest["execution_allowed"] is False


def test_binance_vision_rejects_checksum_mismatch(tmp_path: Path) -> None:
    key = "data/spot/monthly/klines/HOTUSDT/1h/HOTUSDT-1h-2026-06.zip"
    payload = zipped_csv(1_751_328_000_000_000, "1.1")

    def fetch(url: str) -> bytes:
        if "list-type" in url:
            return listing(key) if "monthly" in url else listing()
        if url.endswith(".CHECKSUM"):
            return f"{'0' * 64}  archive.zip\n".encode()
        return payload

    with pytest.raises(BinanceVisionIntegrityError, match="checksum mismatch"):
        BinanceVisionIngestor(ParquetOHLCVArchive(tmp_path), fetch).sync(
            "HOTUSDT",
            ("1h",),
            as_of=date(2026, 7, 13),
        )


def test_network_ingestor_rejects_unsafe_limits(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    with pytest.raises(ValueError, match="timeout_seconds"):
        BinanceVisionIngestor.with_network(archive, timeout_seconds=0)
    with pytest.raises(ValueError, match="maximum_response_bytes"):
        BinanceVisionIngestor.with_network(archive, maximum_response_bytes=100)


def test_network_ingestor_enforces_url_allowlist_and_response_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Response:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return self._payload

    def oversized_urlopen(request: object, *, timeout: float) -> Response:
        assert timeout == 1
        return Response(b"x" * 1025)

    monkeypatch.setattr(urllib.request, "urlopen", oversized_urlopen)
    ingestor = BinanceVisionIngestor.with_network(
        ParquetOHLCVArchive(tmp_path),
        timeout_seconds=1,
        maximum_response_bytes=1024,
    )

    with pytest.raises(ValueError, match="allowlist"):
        ingestor.fetch("http://example.test/archive.zip")
    with pytest.raises(BinanceVisionIntegrityError, match="size limit"):
        ingestor.fetch("https://data.binance.vision/archive.zip")


def test_binance_vision_rejects_unsupported_sync_inputs(tmp_path: Path) -> None:
    ingestor = BinanceVisionIngestor(ParquetOHLCVArchive(tmp_path), lambda url: b"")

    with pytest.raises(ValueError, match="HOTUSDT and BTCUSDT"):
        ingestor.sync("ETHUSDT", ("1h",), as_of=date(2026, 7, 13))
    with pytest.raises(ValueError, match="non-empty and unique"):
        ingestor.sync("HOTUSDT", (), as_of=date(2026, 7, 13))
    with pytest.raises(ValueError, match="non-empty and unique"):
        ingestor.sync("HOTUSDT", ("1h", "1h"), as_of=date(2026, 7, 13))


def test_binance_vision_rejects_missing_and_malformed_archives(
    tmp_path: Path,
) -> None:
    ingestor = BinanceVisionIngestor(
        ParquetOHLCVArchive(tmp_path),
        lambda url: listing("data/spot/monthly/klines/HOTUSDT/1h/README.txt"),
    )
    with pytest.raises(FileNotFoundError, match="no monthly"):
        ingestor.sync("HOTUSDT", ("1h",), as_of=date(2026, 7, 13))

    with pytest.raises(BinanceVisionIntegrityError, match="unexpected"):
        BinanceVisionIngestor._archive_date("HOTUSDT-1h-latest.zip")


def test_binance_vision_rejects_large_listing_and_bad_archive_payload(
    tmp_path: Path,
) -> None:
    ingestor = BinanceVisionIngestor(
        ParquetOHLCVArchive(tmp_path),
        lambda url: b"x" * (10 * 1024 * 1024 + 1),
    )
    with pytest.raises(BinanceVisionIntegrityError, match="listing is too large"):
        ingestor._archive_keys(
            "data/spot/monthly/klines/HOTUSDT/1h/",
            "HOTUSDT",
            "1h",
            date(2026, 7, 13),
        )

    with pytest.raises(BinanceVisionIntegrityError, match="invalid ZIP"):
        BinanceVisionIngestor._parse_zip("HOTUSDT-1h-2026-06.zip", b"not a zip")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.csv", "")
        archive.writestr("two.csv", "")
    with pytest.raises(BinanceVisionIntegrityError, match="exactly one CSV"):
        BinanceVisionIngestor._parse_zip("HOTUSDT-1h-2026-06.zip", buffer.getvalue())

    with pytest.raises(BinanceVisionIntegrityError, match="incomplete"):
        BinanceVisionIngestor._row_to_candle(["1", "2"])
    with pytest.raises(BinanceVisionIntegrityError, match="invalid values"):
        BinanceVisionIngestor._row_to_candle(["bad", "1", "1", "1", "1", "1"])


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (1_700_000_000_000, datetime.fromtimestamp(1_700_000_000, tz=UTC)),
        (1_750_000_000_000_000, datetime.fromtimestamp(1_750_000_000, tz=UTC)),
    ],
)
def test_binance_vision_supports_millisecond_and_microsecond_timestamps(
    timestamp: int,
    expected: datetime,
) -> None:
    parsed = BinanceVisionIngestor._parse_zip(
        "HOTUSDT.zip",
        zipped_csv(timestamp, "1.1"),
    )
    assert parsed[0].timestamp == expected

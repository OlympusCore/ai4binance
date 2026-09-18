"""Offline malformed-archive and point-in-time replay rejection contracts."""

import io
import urllib.request
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai4binance.data import binance_vision_futures as vision
from ai4binance.data.market_history_sync import BinanceVisionArchiveCache
from tests.test_binance_vision_futures import _ingestor, _source_payloads, _zip_csv


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "archive size"),
        (_zip_csv("nested/unsafe.csv", "field", ["1"]), "member is unsafe"),
        (_zip_csv("valid.csv", "wrong", ["1"]), "schema is invalid"),
        (_zip_csv("valid.csv", "field", []), "record count"),
        (b"broken zip", "invalid ZIP"),
    ],
)
def test_archive_parser_rejects_invalid_inputs(payload: bytes, message: str) -> None:
    with pytest.raises(vision.BinanceVisionFuturesIntegrityError, match=message):
        vision.BinanceVisionFuturesReplayIngestor._parse_csv_archive(
            "test.zip", payload, ("field",)
        )


def test_multi_member_archive_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.csv", "field\n1")
        archive.writestr("two.csv", "field\n2")
    with pytest.raises(vision.BinanceVisionFuturesIntegrityError, match="exactly one"):
        vision.BinanceVisionFuturesReplayIngestor._parse_csv_archive(
            "test.zip", buffer.getvalue(), ("field",)
        )


@pytest.mark.parametrize("checksum", [b"", b"\xff"])
def test_malformed_published_checksum_never_admits_source(
    tmp_path: Path, checksum: bytes
) -> None:
    fetch = Mock(side_effect=[_zip_csv("a.csv", "field", ["1"]), checksum])
    ingestor = vision.BinanceVisionFuturesReplayIngestor(tmp_path, fetch)
    with pytest.raises(
        vision.BinanceVisionFuturesIntegrityError, match="checksum mismatch"
    ):
        ingestor._verified_rows("ohlcv", "test.zip", ("field",))


def test_persistent_cache_uses_verified_payload_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _zip_csv("a.csv", "field", ["1"])
    cache = SimpleNamespace(
        fetch=Mock(side_effect=AssertionError("network forbidden")),
        verified=Mock(return_value=(SimpleNamespace(sha256="a" * 64), payload)),
    )
    factory = Mock(return_value=cache)
    monkeypatch.setattr(BinanceVisionArchiveCache, "with_network", factory)
    ingestor = vision.BinanceVisionFuturesReplayIngestor.with_persistent_cache(
        tmp_path / "artifacts", tmp_path / "cache", timeout_seconds=7
    )
    source, rows = ingestor._verified_rows("ohlcv", "test.zip", ("field",))
    factory.assert_called_once_with(tmp_path / "cache", timeout_seconds=7)
    cache.verified.assert_called_once_with("test.zip", kind="ohlcv")
    assert source.sha256 == "a" * 64
    assert source.record_count == 1
    assert rows == ({"field": "1"},)
    cache.fetch.assert_not_called()


def test_network_response_limit_is_enforced_with_offline_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b"x" * 1025
    monkeypatch.setattr(urllib.request, "urlopen", Mock(return_value=response))
    ingestor = vision.BinanceVisionFuturesReplayIngestor.with_network(
        tmp_path, maximum_response_bytes=1024
    )
    with pytest.raises(vision.BinanceVisionFuturesIntegrityError, match="size limit"):
        ingestor.fetch("https://data.binance.vision/test.zip")
    response.read.assert_called_once_with(1025)


@pytest.mark.parametrize(
    ("kind", "change", "message"),
    [
        ("ohlcv", "drop_first", "contiguous UTC day"),
        ("mark_price", "drop_first", "timestamps do not align"),
        ("open_interest", "wrong_symbol", "symbol lineage"),
        ("open_interest", "drop_first", "timestamps do not align"),
        ("funding_rate", "drop_first", "incomplete at replay start"),
        ("ohlcv", "invalid_close", "invalid values"),
    ],
)
def test_replay_rejects_incomplete_or_misaligned_sources(
    tmp_path: Path, kind: str, change: str, message: str
) -> None:
    payloads = _source_payloads()
    with zipfile.ZipFile(io.BytesIO(payloads[kind])) as archive:
        name = archive.namelist()[0]
        lines = archive.read(name).decode().splitlines()
    if change == "drop_first":
        lines.pop(1)
    elif change == "wrong_symbol":
        lines[1] = lines[1].replace("BTCUSDT", "ETHUSDT")
    else:
        fields = lines[1].split(",")
        fields[6] = fields[0]
        lines[1] = ",".join(fields)
    payloads[kind] = _zip_csv(name, lines[0], lines[1:])
    with pytest.raises(vision.BinanceVisionFuturesIntegrityError, match=message):
        _ingestor(tmp_path, payloads).sync_day(
            "BTCUSDT", date(2024, 1, 1), observed_at=datetime(2024, 2, 1, tzinfo=UTC)
        )


def test_missing_kline_close_field_is_rejected() -> None:
    with pytest.raises(
        vision.BinanceVisionFuturesIntegrityError, match="close-time alignment"
    ):
        vision.BinanceVisionFuturesReplayIngestor._require_kline_close_alignment(
            ({},), "mark"
        )

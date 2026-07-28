"""Parquet research archive integrity and isolation tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from ai4binance.data import DatasetIntegrityError, ParquetOHLCVArchive
from ai4binance.schemas import OHLCVCandle


def candle(timestamp: datetime, close: str = "1.05") -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=timestamp,
        open=Decimal("1"),
        high=Decimal("1.1"),
        low=Decimal("0.9"),
        close=Decimal(close),
        volume=Decimal("100"),
    )


def test_archive_incrementally_merges_and_deduplicates(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    first = candle(start)
    second = candle(start + timedelta(hours=1))

    archive.update("HOTUSDT", "1h", (first,), source="BINANCE_PUBLIC_REST")
    manifest = archive.update(
        "HOTUSDT",
        "1h",
        (first, second),
        source="BINANCE_PUBLIC_REST",
    )

    assert archive.read("HOTUSDT", "1h") == (first, second)
    assert manifest.row_count == 2
    assert manifest.gap_count == 0
    assert len(manifest.sha256) == 64


def test_archive_records_gaps_without_inventing_candles(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    manifest = archive.update(
        "HOTUSDT",
        "1h",
        (candle(start), candle(start + timedelta(hours=2))),
        source="BINANCE_PUBLIC_REST",
    )

    assert manifest.gap_count == 1
    assert "->" in manifest.gaps[0]
    assert len(archive.read("HOTUSDT", "1h")) == 2


def test_archive_rejects_conflicting_duplicate(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    timestamp = datetime(2026, 7, 1, tzinfo=UTC)
    archive.update("HOTUSDT", "1h", (candle(timestamp),), source="BINANCE_PUBLIC_REST")

    with pytest.raises(DatasetIntegrityError, match="conflicting candle"):
        archive.update(
            "HOTUSDT",
            "1h",
            (candle(timestamp, "1.06"),),
            source="BINANCE_PUBLIC_REST",
        )


def test_archive_detects_checksum_tampering(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    archive.update(
        "HOTUSDT",
        "1h",
        (candle(datetime(2026, 7, 1, tzinfo=UTC)),),
        source="BINANCE_PUBLIC_REST",
    )
    parquet_path = tmp_path / "HOTUSDT" / "1h.parquet"
    parquet_path.write_bytes(parquet_path.read_bytes() + b"tampered")

    with pytest.raises(DatasetIntegrityError, match="checksum"):
        archive.read("HOTUSDT", "1h")


def test_archive_schema_contains_market_data_only(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    archive.update(
        "HOTUSDT",
        "15m",
        (candle(datetime(2026, 7, 1, tzinfo=UTC)),),
        source="BINANCE_PUBLIC_REST",
    )
    table = pq.read_table(  # type: ignore[no-untyped-call]
        tmp_path / "HOTUSDT" / "15m.parquet"
    )

    assert table.column_names == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert table.schema.metadata is not None
    assert table.schema.metadata[b"market_data_only"] == b"true"
    assert b"wallet" not in table.schema.metadata


def test_archive_rejects_unsafe_symbol_path(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    with pytest.raises(ValueError, match="alphanumeric"):
        archive.update(
            "../HOTUSDT",
            "1h",
            (candle(datetime(2026, 7, 1, tzinfo=UTC)),),
            source="BINANCE_PUBLIC_REST",
        )

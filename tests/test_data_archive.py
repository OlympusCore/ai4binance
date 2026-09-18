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


def test_archive_skips_rewriting_an_unchanged_verified_dataset(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    item = candle(datetime(2026, 7, 1, tzinfo=UTC))
    first = archive.update(
        "HOTUSDT",
        "1h",
        (item,),
        source="BINANCE_PUBLIC_REST",
        generated_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    parquet_path = tmp_path / "HOTUSDT" / "1h.parquet"
    initial_bytes = parquet_path.read_bytes()

    repeated = archive.update(
        "HOTUSDT",
        "1h",
        (item,),
        source="BINANCE_PUBLIC_REST",
        generated_at=datetime(2026, 7, 2, tzinfo=UTC),
    )

    assert repeated == first
    assert parquet_path.read_bytes() == initial_bytes


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


def test_archive_reads_checksum_verified_bounded_window(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    candles = tuple(candle(start + timedelta(hours=index)) for index in range(5))
    archive.update("HOTUSDT", "1h", candles, source="BINANCE_PUBLIC_REST")

    window = archive.read_window(
        "HOTUSDT",
        "1h",
        start_at=start + timedelta(hours=1),
        end_at=start + timedelta(hours=3),
    )

    assert window == candles[1:4]
    with pytest.raises(ValueError, match="cannot precede"):
        archive.read_window(
            "HOTUSDT",
            "1h",
            start_at=start + timedelta(hours=3),
            end_at=start,
        )


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


@pytest.mark.parametrize("conflicting", [False, True])
def test_legacy_duplicates_are_compacted_only_when_identical(
    tmp_path: Path, conflicting: bool
) -> None:
    from dataclasses import replace

    archive = ParquetOHLCVArchive(tmp_path)
    stamp = datetime(2026, 7, 1, tzinfo=UTC)
    first = candle(stamp)
    manifest = archive.update("HOTUSDT", "1h", (first,), source="BINANCE_PUBLIC_REST")
    parquet, metadata = archive._paths("HOTUSDT", "1h")
    repeated = (first, candle(stamp, "1.06") if conflicting else first)
    archive._write_parquet(parquet, "HOTUSDT", "1h", manifest.source, repeated)
    archive._write_manifest(
        metadata,
        replace(
            manifest,
            row_count=2,
            sha256=archive._file_checksum(parquet),
            gap_count=1,
            gaps=archive._find_gaps(repeated, "1h"),
        ),
    )
    if conflicting:
        with pytest.raises(DatasetIntegrityError, match="conflicting candle"):
            archive.update(
                "HOTUSDT",
                "1h",
                (first,),
                source=manifest.source,
                replace_conflicts_from_sources=("BINANCE_PUBLIC_REST",),
            )
        assert archive.manifest("HOTUSDT", "1h").row_count == 2
    else:
        repaired = archive.update("HOTUSDT", "1h", (first,), source=manifest.source)
        assert repaired.row_count == 1
        assert repaired.gap_count == 0
        assert archive.read("HOTUSDT", "1h") == (first,)


def test_archive_replaces_only_explicit_compatible_derived_conflicts(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    timestamp = datetime(2026, 7, 1, tzinfo=UTC)
    archive.update(
        "HOTUSDT",
        "1h",
        (candle(timestamp),),
        source="COMPATIBLE_DIRECT_PLUS_DERIVED_FROM_CANONICAL_1M:test",
    )

    direct = candle(timestamp, "1.06")
    manifest = archive.update(
        "HOTUSDT",
        "1h",
        (direct,),
        source="BINANCE_VISION_DIRECT_1H_SHA256:test",
        replace_conflicts_from_sources=(
            "COMPATIBLE_DIRECT_PLUS_DERIVED_FROM_CANONICAL_1M:",
        ),
    )

    assert archive.read("HOTUSDT", "1h") == (direct,)
    assert manifest.source == "BINANCE_VISION_DIRECT_1H_SHA256:test"


def test_archive_truncates_unclosed_tail_atomically(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    candles = tuple(candle(start + timedelta(hours=index)) for index in range(3))
    archive.update("HOTUSDT", "1h", candles, source="BINANCE_PUBLIC_REST")

    manifest = archive.truncate_from(
        "HOTUSDT",
        "1h",
        start_at=start + timedelta(hours=2),
        source="CLOSED_CANDLE_BOUNDARY_REPAIR",
    )

    assert archive.read("HOTUSDT", "1h") == candles[:2]
    assert manifest.row_count == 2
    assert manifest.source == "CLOSED_CANDLE_BOUNDARY_REPAIR"


def test_archive_refuses_a_truncation_that_would_empty_data(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    archive.update("HOTUSDT", "1h", (candle(start),), source="BINANCE_PUBLIC_REST")

    with pytest.raises(DatasetIntegrityError, match="would empty"):
        archive.truncate_from(
            "HOTUSDT",
            "1h",
            start_at=start,
            source="CLOSED_CANDLE_BOUNDARY_REPAIR",
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

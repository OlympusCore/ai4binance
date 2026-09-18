"""Contracts for controlled removal of superseded runtime 1m datasets."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.legacy_1m_cleanup import LegacyOneMinuteCleanup
from ai4binance.data.market_history_sync import MARKET_HISTORY_TIMEFRAMES
from ai4binance.schemas import OHLCVCandle


def test_cleanup_dry_run_inventories_without_removing_legacy_files(
    tmp_path: Path,
) -> None:
    _write_complete_replacement(tmp_path)

    result = LegacyOneMinuteCleanup(tmp_path).run()

    assert result["status"] == "DRY_RUN"
    assert result["removed_files"] == 0
    rows = result["rows"]
    assert isinstance(rows, list)
    assert rows[0]["market"] == "spot"
    assert rows[0]["status"] == "READY_FOR_APPROVED_REMOVAL"
    assert rows[0]["byte_count"] > 0
    assert rows[0]["paths"] == [
        "spot/BTCUSDT/1m.parquet",
        "spot/BTCUSDT/1m.manifest.json",
    ]
    assert (tmp_path / "spot/BTCUSDT/1m.parquet").is_file()
    assert (tmp_path / "cleanup-receipts/legacy-1m-latest.json").is_file()


def test_cleanup_apply_removes_only_verified_legacy_pair_and_is_idempotent(
    tmp_path: Path,
) -> None:
    _write_complete_replacement(tmp_path)

    applied = LegacyOneMinuteCleanup(tmp_path).run(apply=True)
    repeated = LegacyOneMinuteCleanup(tmp_path).run(apply=True)

    assert applied["status"] == "APPLIED"
    assert applied["removed_files"] == 2
    assert not (tmp_path / "spot/BTCUSDT/1m.parquet").exists()
    assert repeated["status"] == "APPLIED"
    assert repeated["removed_files"] == 0


def test_cleanup_refuses_missing_or_non_native_replacements(tmp_path: Path) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "spot")
    _write_candle(archive, "1m", "BINANCE_PUBLIC_REST_1M")
    _write_candle(archive, "5m", "DERIVED_FROM_CANONICAL_1M:test")

    result = LegacyOneMinuteCleanup(tmp_path).run(apply=True)

    assert result["status"] == "BLOCKED"
    assert result["removed_files"] == 0
    assert (tmp_path / "spot/BTCUSDT/1m.parquet").exists()
    assert result["blockers"] == ["LEGACY_1M_REPLACEMENT_INVALID:spot:BTCUSDT"]


def _write_complete_replacement(root: Path) -> None:
    archive = ParquetOHLCVArchive(root / "spot")
    _write_candle(archive, "1m", "BINANCE_PUBLIC_REST_1M")
    for timeframe in MARKET_HISTORY_TIMEFRAMES:
        _write_candle(
            archive,
            timeframe,
            f"BINANCE_VISION_{timeframe.upper()}_SHA256:test",
        )


def _write_candle(archive: ParquetOHLCVArchive, timeframe: str, source: str) -> None:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    candle = OHLCVCandle(
        timestamp=timestamp,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
    )
    archive.update("BTCUSDT", timeframe, (candle,), source=source)

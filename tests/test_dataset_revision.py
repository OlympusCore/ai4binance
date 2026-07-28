import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.revision import DatasetRevisionBuilder
from ai4binance.schemas import OHLCVCandle


def _candles(step: timedelta, count: int) -> tuple[OHLCVCandle, ...]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    return tuple(
        OHLCVCandle(
            timestamp=start + step * index,
            open=Decimal("1"),
            high=Decimal("1.1"),
            low=Decimal("0.9"),
            close=Decimal("1.05"),
            volume=Decimal("100"),
        )
        for index in range(count)
    )


def _seed(root: Path, timeframe: str, step: timedelta) -> None:
    manifest = ParquetOHLCVArchive(root).update(
        "HOTUSDT",
        timeframe,
        _candles(step, 4),
        source="BINANCE_VISION_CHECKSUM_VERIFIED",
        generated_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    payload = {
        "dataset_row_count": manifest.row_count,
        "dataset_sha256": manifest.sha256,
        "source_file_count": 1,
    }
    (root / "HOTUSDT" / f"{timeframe}.source-manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_dataset_revision_seals_all_timeframes(tmp_path: Path) -> None:
    for timeframe, step in (
        ("15m", timedelta(minutes=15)),
        ("1h", timedelta(hours=1)),
        ("4h", timedelta(hours=4)),
        ("1d", timedelta(days=1)),
    ):
        _seed(tmp_path, timeframe, step)
    builder = DatasetRevisionBuilder(tmp_path, minimum_history=timedelta(days=1))

    report = builder.build(
        symbol="HOTUSDT", generated_at=datetime(2026, 7, 16, tzinfo=UTC)
    )
    path = builder.write(report)

    assert report.revision_id.startswith("dataset:")
    assert report.total_rows == 16
    assert report.research_ready is True
    assert report.execution_allowed is False
    assert path.exists()


def test_dataset_revision_rejects_source_checksum_drift(tmp_path: Path) -> None:
    _seed(tmp_path, "1h", timedelta(hours=1))
    source = tmp_path / "HOTUSDT" / "1h.source-manifest.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["dataset_sha256"] = sha256(b"tampered").hexdigest()
    source.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        DatasetRevisionBuilder(tmp_path).build(symbol="HOTUSDT", timeframes=("1h",))

"""Offline snapshot verification with checksum-pinned authentic Binance samples."""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from ai4binance.data.acquisition import ArchivedMarketSnapshotAcquisition
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.domain.market_data import MarketDataProvenance
from ai4binance.schemas import DataQuality, OHLCVCandle

SAMPLE_PATH = Path(__file__).parent / "fixtures/binance/authentic_snapshot_samples.json"
SAMPLE_SHA256 = "a338e67e60f30debf2229aadfdd010cb7548f121bd72432599e66344cf757560"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
CUTOFF = datetime(2026, 10, 7, tzinfo=UTC)


def _archive(
    tmp_path: Path,
    market: str = "spot",
    *,
    source: str = "BINANCE_VISION_CHECKSUM_VERIFIED",
    generated_at: datetime = CUTOFF,
) -> ParquetOHLCVArchive:
    # These rows were extracted from official 2026-10-06 daily ZIP archives.
    # Each sample retains the upstream archive key and published checksum.
    raw = SAMPLE_PATH.read_bytes()
    assert sha256(raw).hexdigest() == SAMPLE_SHA256
    archive = ParquetOHLCVArchive(tmp_path)
    for sample in json.loads(raw):
        if sample["market"] != market:
            continue
        assert sample["source"]["key"].startswith("data/")
        assert len(sample["source"]["sha256"]) == 64
        candles = tuple(
            OHLCVCandle(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                **{
                    name: Decimal(row[name])
                    for name in ("open", "high", "low", "close", "volume")
                },
            )
            for row in sample["candles"]
        )
        archive.update(
            "BTCUSDT",
            sample["timeframe"],
            candles,
            source=source,
            generated_at=generated_at,
        )
    return archive


@pytest.mark.parametrize(
    ("market", "market_type"), [("spot", "SPOT"), ("um", "USD_M_FUTURES")]
)
def test_native_authentic_samples_share_cutoff_and_preserve_precision(
    tmp_path: Path,
    market: str,
    market_type: str,
) -> None:
    acquisition = ArchivedMarketSnapshotAcquisition(
        _archive(tmp_path, market), market_type, minimum_closed_candles=1
    )
    snapshot = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert snapshot.data_quality is DataQuality.DATA_VALID
    assert snapshot.provenance_class is MarketDataProvenance.HISTORICAL_REAL
    assert snapshot.created_at == CUTOFF
    assert snapshot.bid is None
    assert snapshot.ask is None
    assert snapshot.spread is None
    assert snapshot.market_metadata["historical_live_availability_verified"] is False
    assert snapshot.market_metadata["execution_allowed"] is False
    assert snapshot.market_metadata["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    repeated = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert snapshot.snapshot_id == repeated.snapshot_id
    for timeframe in TIMEFRAMES:
        assert snapshot.ohlcv_by_timeframe[timeframe]
        assert (
            cast(Mapping[str, object], snapshot.data_freshness[timeframe])["stale"]
            is False
        )


def test_unaligned_cutoff_keeps_the_required_closed_candle_window(
    tmp_path: Path,
) -> None:
    acquisition = ArchivedMarketSnapshotAcquisition(
        _archive(tmp_path), "SPOT", history_limit=2, minimum_closed_candles=2
    )
    snapshot = acquisition.acquire(
        "BTCUSDT", ("15m",), cutoff=CUTOFF + timedelta(minutes=7)
    )
    assert snapshot.data_quality is DataQuality.DATA_VALID
    assert len(snapshot.ohlcv_by_timeframe["15m"]) == 2
    assert snapshot.ohlcv_by_timeframe["15m"][-1].timestamp == CUTOFF - timedelta(
        minutes=15
    )


def test_authentic_open_daily_candle_blocks_snapshot(tmp_path: Path) -> None:
    acquisition = ArchivedMarketSnapshotAcquisition(
        _archive(tmp_path), "SPOT", minimum_closed_candles=1
    )
    cutoff = datetime(2026, 10, 6, 23, 50, tzinfo=UTC)
    snapshot = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=cutoff)
    assert snapshot.data_quality is DataQuality.DATA_INVALID
    assert not snapshot.ohlcv_by_timeframe["1d"]
    assert len(snapshot.ohlcv_by_timeframe["15m"]) == 1
    assert "1d:INSUFFICIENT_CLOSED_CANDLES" in cast(
        Sequence[str], snapshot.market_metadata["blocking_reasons"]
    )


def test_stale_and_required_missing_observations_remain_blocked(tmp_path: Path) -> None:
    acquisition = ArchivedMarketSnapshotAcquisition(
        _archive(tmp_path), "SPOT", minimum_closed_candles=1
    )
    stale = acquisition.acquire(
        "BTCUSDT", TIMEFRAMES, cutoff=datetime(2026, 10, 8, tzinfo=UTC)
    )
    assert stale.data_quality is DataQuality.DATA_INVALID
    assert "15m:STALE_OR_MISSING" in cast(
        Sequence[str], stale.market_metadata["blocking_reasons"]
    )
    missing = acquisition.acquire("ETHUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert missing.data_quality is DataQuality.DATA_INVALID
    assert missing.latest_price is None
    assert all(not rows for rows in missing.ohlcv_by_timeframe.values())


def test_retrieval_metadata_does_not_change_semantic_identity(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    acquisition = ArchivedMarketSnapshotAcquisition(
        archive, "SPOT", minimum_closed_candles=1
    )
    original = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    repeated_archive = _archive(
        tmp_path / "retrieved-again", generated_at=datetime(2026, 10, 8, tzinfo=UTC)
    )
    repeated = ArchivedMarketSnapshotAcquisition(
        repeated_archive, "SPOT", minimum_closed_candles=1
    ).acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert original.snapshot_id == repeated.snapshot_id
    assert (
        original.market_metadata["source_lineage"]
        != repeated.market_metadata["source_lineage"]
    )


def test_unverified_source_and_naive_cutoff_are_rejected(tmp_path: Path) -> None:
    archive = _archive(tmp_path, source="UNVERIFIED")
    acquisition = ArchivedMarketSnapshotAcquisition(
        archive, "SPOT", minimum_closed_candles=1
    )
    snapshot = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert snapshot.data_quality is DataQuality.DATA_INVALID
    assert "15m:ARCHIVE_UNAVAILABLE_OR_INVALID" in cast(
        Sequence[str], snapshot.market_metadata["blocking_reasons"]
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=datetime(2026, 10, 7))


def test_consumer_requiring_futures_enrichment_rejects_ohlcv_only(
    tmp_path: Path,
) -> None:
    acquisition = ArchivedMarketSnapshotAcquisition(
        _archive(tmp_path),
        "SPOT",
        minimum_closed_candles=1,
        require_futures_enrichment=True,
    )
    snapshot = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert snapshot.data_quality is DataQuality.DATA_INVALID
    assert "FUTURES_ENRICHMENT_UNVERIFIED" in cast(
        Sequence[str], snapshot.market_metadata["blocking_reasons"]
    )
    assert not snapshot.derivatives_snapshot


def test_per_timeframe_consumer_requirements_are_not_reduced(tmp_path: Path) -> None:
    acquisition = ArchivedMarketSnapshotAcquisition(
        _archive(tmp_path),
        "SPOT",
        minimum_closed_candles=1,
        local_candle_limits={"15m": 2, "1h": 2, "4h": 2, "1d": 2},
    )
    snapshot = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert snapshot.data_quality is DataQuality.DATA_INVALID
    assert "1d:INSUFFICIENT_CLOSED_CANDLES" in cast(
        Sequence[str], snapshot.market_metadata["blocking_reasons"]
    )
    assert (
        cast(Mapping[str, object], snapshot.data_freshness["1d"])[
            "required_candle_count"
        ]
        == 2
    )


def test_authentic_future_tail_does_not_change_past_snapshot(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    acquisition = ArchivedMarketSnapshotAcquisition(
        archive, "SPOT", minimum_closed_candles=1
    )
    before = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    sample_path = SAMPLE_PATH.with_name("authentic_post_cutoff_sample.json")
    raw = sample_path.read_bytes()
    assert sha256(raw).hexdigest() == (
        "9328600b8e079686ba3491f106a72599b3391c1f65653eb2a27e17dc081e7ac8"
    )
    rows = json.loads(raw)["candles"]
    future_candles = tuple(
        OHLCVCandle(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            **{
                name: Decimal(row[name])
                for name in ("open", "high", "low", "close", "volume")
            },
        )
        for row in rows
    )
    assert all(candle.timestamp >= CUTOFF for candle in future_candles)
    archive.update(
        "BTCUSDT",
        "15m",
        future_candles,
        source="BINANCE_VISION_CHECKSUM_VERIFIED",
        generated_at=CUTOFF,
    )
    after = acquisition.acquire("BTCUSDT", TIMEFRAMES, cutoff=CUTOFF)
    assert before.snapshot_id == after.snapshot_id
    assert before.ohlcv_by_timeframe == after.ohlcv_by_timeframe
    assert (
        before.market_metadata["source_lineage"]
        != after.market_metadata["source_lineage"]
    )

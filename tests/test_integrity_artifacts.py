from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.integrity_artifacts import (
    IntegrityArtifactScanner,
    IntegrityScanArtifact,
    IntegrityTarget,
    default_integrity_targets,
)


def _candles(count: int) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index),
            Decimal(index + 10),
            Decimal(index + 11),
            Decimal(index + 9),
            Decimal(index + 10),
            Decimal("100"),
        )
        for index in range(count)
    )


def test_integrity_scanner_writes_fail_closed_bounded_artifact(tmp_path: Path) -> None:
    target = IntegrityTarget(
        "close",
        "INDICATOR",
        lambda candles: tuple(float(item.close) for item in candles),
        2,
    )
    scanner = IntegrityArtifactScanner(maximum_candles_per_timeframe=8)

    artifact = scanner.scan(
        symbol="HOTUSDT",
        dataset_revision_id="dataset:abc",
        candles_by_timeframe={"1h": _candles(12)},
        targets=(target,),
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    path = tmp_path / "integrity.json"
    scanner.write(artifact, path)

    assert artifact.sampled is True
    assert artifact.promotion_allowed is False
    assert artifact.blockers == ("BOUNDED_INTEGRITY_SCAN_ONLY",)
    assert path.exists()


def test_default_integrity_catalog_computes_every_registered_target() -> None:
    candles = _candles(40)

    targets = default_integrity_targets()

    assert len(targets) == 16
    for target in targets:
        assert len(target.compute(candles)) == len(candles)


def test_integrity_scanner_covers_insufficient_and_complete_scans() -> None:
    short_target = IntegrityTarget(
        "needs-history",
        "INDICATOR",
        lambda candles: tuple(float(item.close) for item in candles),
        20,
    )
    short = IntegrityArtifactScanner(maximum_candles_per_timeframe=None).scan(
        symbol="HOTUSDT",
        dataset_revision_id="dataset:abc",
        candles_by_timeframe={"1h": _candles(8)},
        targets=(short_target,),
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    assert short.blockers == ("1h:needs-history:INTEGRITY_HISTORY_INSUFFICIENT",)

    close_target = IntegrityTarget(
        "close",
        "INDICATOR",
        lambda candles: tuple(float(item.close) for item in candles),
        2,
    )
    complete = IntegrityArtifactScanner(maximum_candles_per_timeframe=None).scan(
        symbol="HOTUSDT",
        dataset_revision_id="dataset:abc",
        candles_by_timeframe={"1h": _candles(8)},
        targets=(close_target,),
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    assert complete.promotion_allowed is True
    assert complete.blockers == ()

    with pytest.raises(ValueError, match="identity"):
        IntegrityScanArtifact(
            "bad",
            "HOTUSDT",
            datetime(2026, 7, 16, tzinfo=UTC),
            "dataset:abc",
            (),
            False,
            (),
            True,
        )

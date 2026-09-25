"""Fail-closed runtime Futures historical replay dataset tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from ai4binance.cli.futures_oos import (
    LocalGitFuturesOosRevisionResolver,
)
from ai4binance.cli.futures_oos import (
    main as futures_oos_main,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation import (
    FuturesOosRevisionSnapshot,
    RuntimeFuturesReplayDataset,
    RuntimeFuturesReplayLoader,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
SOURCE_ID = "BINANCE_USD_M_PUBLIC_REST"
SOURCE_URL = "https://fapi.binance.com"


def _candles(count: int = 8) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(hours=count - index),
            open=Decimal("100") + index,
            high=Decimal("102") + index,
            low=Decimal("99") + index,
            close=Decimal("101") + index,
            volume=Decimal("1000"),
        )
        for index in range(count)
    )


def _point(
    metric: DerivativesMetric,
    timestamp: datetime,
    value: str,
    *,
    source_id: str = SOURCE_ID,
    source_url: str = SOURCE_URL,
    observed_at: datetime = NOW,
) -> MetricPoint:
    return MetricPoint(
        metric=metric,
        timestamp=timestamp,
        value=Decimal(value),
        provenance=Provenance(source_id, observed_at, source_url),
    )


def _derivatives(
    candles: tuple[OHLCVCandle, ...],
    *,
    source: str = SOURCE_ID,
    source_id: str = SOURCE_ID,
    source_url: str = SOURCE_URL,
    observed_at: datetime = NOW,
    as_of: datetime = NOW,
) -> DerivativesDataset:
    open_interest = tuple(
        _point(
            DerivativesMetric.OPEN_INTEREST,
            candle.timestamp,
            str(1000 + index),
            source_id=source_id,
            source_url=source_url,
            observed_at=observed_at,
        )
        for index, candle in enumerate(candles)
    )
    funding = tuple(
        _point(
            DerivativesMetric.FUNDING_RATE,
            candle.timestamp,
            "0.0001",
            source_id=source_id,
            source_url=source_url,
            observed_at=observed_at,
        )
        for candle in candles[::4]
    )
    return DerivativesDataset(
        symbol="HOTUSDT",
        as_of=as_of,
        series={
            DerivativesMetric.OPEN_INTEREST: open_interest,
            DerivativesMetric.FUNDING_RATE: funding,
        },
        source=source,
    )


def _dataset(count: int = 8) -> RuntimeFuturesReplayDataset:
    candles = _candles(count)
    return RuntimeFuturesReplayDataset(
        symbol="HOTUSDT",
        candles=candles,
        derivatives=_derivatives(candles),
    )


def _write_replay(path: Path, dataset: RuntimeFuturesReplayDataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dataset.to_artifact_payload(), sort_keys=True),
        encoding="utf-8",
    )


def test_runtime_futures_replay_binds_aligned_public_history() -> None:
    candles = _candles()
    dataset = RuntimeFuturesReplayDataset(
        symbol="hotusdt",
        candles=candles,
        derivatives=_derivatives(candles),
    )

    assert dataset.symbol == "HOTUSDT"
    assert dataset.timeframe == "1h"
    assert dataset.market == "USD_M_FUTURES"
    assert dataset.open_interest == tuple(Decimal(1000 + index) for index in range(8))
    assert len(dataset.dataset_sha256) == 64
    assert dataset.dataset_sha256 == dataset.dataset_sha256
    assert dataset.execution_allowed is False
    assert dataset.promotion_status == "RESEARCH_ONLY"
    assert dataset.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runtime_futures_replay_loader_binds_exact_artifact_bytes(
    tmp_path: Path,
) -> None:
    dataset = _dataset()
    replay_path = tmp_path / "hotusdt.json"
    _write_replay(replay_path, dataset)
    encoded = replay_path.read_bytes()

    verified = RuntimeFuturesReplayLoader(tmp_path).load_verified("hotusdt.json")

    assert verified.dataset == dataset
    assert verified.artifact_sha256 == hashlib.sha256(encoded).hexdigest()
    assert verified.dataset.execution_allowed is False
    assert verified.dataset.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runtime_futures_replay_hash_changes_with_market_data() -> None:
    candles = _candles()
    original = RuntimeFuturesReplayDataset(
        symbol="HOTUSDT",
        candles=candles,
        derivatives=_derivatives(candles),
    )
    changed_candles = (*candles[:-1], replace(candles[-1], close=Decimal("108.5")))
    changed = RuntimeFuturesReplayDataset(
        symbol="HOTUSDT",
        candles=changed_candles,
        derivatives=_derivatives(changed_candles),
    )

    assert changed.dataset_sha256 != original.dataset_sha256


def test_runtime_futures_replay_rejects_missing_and_misaligned_open_interest() -> None:
    candles = _candles()
    with pytest.raises(ValueError, match="open-interest history"):
        RuntimeFuturesReplayDataset(
            symbol="HOTUSDT",
            candles=candles,
            derivatives=DerivativesDataset("HOTUSDT", NOW, {}),
        )

    derivatives = _derivatives(candles)
    misaligned = replace(
        derivatives,
        series={
            **derivatives.series,
            DerivativesMetric.OPEN_INTEREST: derivatives.series[
                DerivativesMetric.OPEN_INTEREST
            ][1:],
        },
    )
    with pytest.raises(ValueError, match="timestamps must align exactly"):
        RuntimeFuturesReplayDataset("HOTUSDT", candles, misaligned)


def test_runtime_futures_replay_rejects_duplicate_candles_and_wrong_identity() -> None:
    candles = _candles()
    with pytest.raises(ValueError, match="unique and strictly chronological"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            (*candles[:-1], candles[-2]),
            _derivatives(candles),
        )
    with pytest.raises(ValueError, match="symbol lineage"):
        RuntimeFuturesReplayDataset(
            "BTCUSDT",
            candles,
            _derivatives(candles),
        )
    with pytest.raises(ValueError, match="timeframe is unsupported"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            candles,
            _derivatives(candles),
            timeframe="1m",
        )


@pytest.mark.parametrize("timeframe", ["5m", "15m", "1h", "4h", "1d"])
def test_runtime_futures_replay_accepts_supported_timeframes(timeframe: str) -> None:
    durations = {
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }
    candles = tuple(
        replace(candle, timestamp=NOW + durations[timeframe] * index)
        for index, candle in enumerate(_candles())
    )
    observed_at = candles[-1].timestamp + durations[timeframe]
    dataset = RuntimeFuturesReplayDataset(
        "HOTUSDT",
        candles,
        _derivatives(candles, observed_at=observed_at, as_of=observed_at),
        timeframe=timeframe,
    )

    assert dataset.timeframe == timeframe


def test_runtime_futures_replay_rejects_non_public_and_spoofed_sources() -> None:
    candles = _candles()
    with pytest.raises(ValueError, match="approved public data source"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            candles,
            _derivatives(
                candles,
                source="PRIVATE_ACCOUNT_EXPORT",
                source_id="PRIVATE_ACCOUNT_EXPORT",
            ),
        )
    with pytest.raises(ValueError, match="provenance host"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            candles,
            _derivatives(candles, source_url="https://example.com/fapi.binance.com"),
        )


def test_runtime_futures_replay_rejects_out_of_bounds_derivatives() -> None:
    candles = _candles()
    derivatives = _derivatives(candles)
    future_funding = _point(
        DerivativesMetric.FUNDING_RATE,
        candles[-1].timestamp + timedelta(hours=1),
        "0.0001",
    )
    out_of_bounds = replace(
        derivatives,
        series={
            **derivatives.series,
            DerivativesMetric.FUNDING_RATE: (
                *derivatives.series[DerivativesMetric.FUNDING_RATE],
                future_funding,
            ),
        },
    )

    with pytest.raises(ValueError, match="exceed candle bounds"):
        RuntimeFuturesReplayDataset("HOTUSDT", candles, out_of_bounds)


def test_runtime_futures_replay_rejects_future_provenance_and_early_as_of() -> None:
    candles = _candles()
    with pytest.raises(ValueError, match="provenance exceeds"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            candles,
            _derivatives(candles, observed_at=NOW + timedelta(seconds=1)),
        )
    with pytest.raises(ValueError, match="as_of precedes"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            candles,
            _derivatives(candles, as_of=candles[-1].timestamp - timedelta(seconds=1)),
        )
    with pytest.raises(ValueError, match="provenance predates"):
        RuntimeFuturesReplayDataset(
            "HOTUSDT",
            candles,
            _derivatives(
                candles, observed_at=candles[0].timestamp - timedelta(seconds=1)
            ),
        )


def test_runtime_futures_replay_loader_round_trips_exact_artifact(
    tmp_path: Path,
) -> None:
    dataset = _dataset()
    replay_root = tmp_path / "runtime" / "datasets" / "futures"
    replay_path = replay_root / "hotusdt.json"
    _write_replay(replay_path, dataset)

    loaded = RuntimeFuturesReplayLoader(replay_root).load("hotusdt.json")

    assert loaded == dataset
    assert loaded.dataset_sha256 == dataset.dataset_sha256
    assert loaded.execution_allowed is False
    assert loaded.promotion_status == "RESEARCH_ONLY"
    assert loaded.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runtime_futures_replay_loader_rejects_tampering_and_unsafe_paths(
    tmp_path: Path,
) -> None:
    dataset = _dataset()
    replay_root = tmp_path / "runtime" / "datasets" / "futures"
    replay_path = replay_root / "hotusdt.json"
    _write_replay(replay_path, dataset)
    payload = json.loads(replay_path.read_text(encoding="utf-8"))
    payload["dataset_sha256"] = "0" * 64
    replay_path.write_text(json.dumps(payload), encoding="utf-8")

    loader = RuntimeFuturesReplayLoader(replay_root)
    with pytest.raises(ValueError, match="DATASET_HASH_MISMATCH"):
        loader.load("hotusdt.json")

    outside = tmp_path / "outside.json"
    _write_replay(outside, dataset)
    with pytest.raises(ValueError, match="PATH_OUTSIDE_ROOT"):
        loader.load(outside)

    oversized = replay_root / "oversized.json"
    oversized.write_bytes(b"{" + b"x" * 1_024)
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_UNSAFE"):
        RuntimeFuturesReplayLoader(replay_root, max_bytes=1_024).load(oversized)

    duplicate = replay_root / "duplicate.json"
    duplicate.write_text('{"schema_version":"1.0","schema_version":"1.0"}')
    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        loader.load(duplicate)


def test_local_git_futures_revision_resolver_requires_exact_clean_root(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git").mkdir()
    revision = "c" * 40
    clean_results = (
        subprocess.CompletedProcess((), 0, f"{tmp_path}\n".encode(), b""),
        subprocess.CompletedProcess((), 0, f"{revision}\n".encode(), b""),
        subprocess.CompletedProcess((), 0, b"", b""),
    )
    with (
        patch("ai4binance.cli.futures_oos.shutil.which", return_value="git"),
        patch(
            "ai4binance.cli.futures_oos.subprocess.run",
            side_effect=clean_results,
        ) as run,
    ):
        snapshot = LocalGitFuturesOosRevisionResolver(tmp_path)()

    assert snapshot == FuturesOosRevisionSnapshot(revision, repository_clean=True)
    assert run.call_count == 3

    dirty_results = (
        *clean_results[:2],
        subprocess.CompletedProcess((), 0, b" M tracked.py\n", b""),
    )
    with (
        patch("ai4binance.cli.futures_oos.shutil.which", return_value="git"),
        patch(
            "ai4binance.cli.futures_oos.subprocess.run",
            side_effect=dirty_results,
        ),
    ):
        dirty = LocalGitFuturesOosRevisionResolver(tmp_path)()

    assert dirty.repository_clean is False

    mismatch = subprocess.CompletedProcess(
        (),
        0,
        f"{tmp_path.parent}\n".encode(),
        b"",
    )
    with (
        patch("ai4binance.cli.futures_oos.shutil.which", return_value="git"),
        patch(
            "ai4binance.cli.futures_oos.subprocess.run",
            return_value=mismatch,
        ),
        pytest.raises(ValueError, match="REPOSITORY_ROOT_MISMATCH"),
    ):
        LocalGitFuturesOosRevisionResolver(tmp_path)()


def test_local_futures_oos_cli_publishes_research_only_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candles = tuple(
        replace(
            candle,
            high=(candle.open + Decimal("6") if index % 2 == 0 else candle.high),
            low=(candle.open - Decimal("1") if index % 2 == 0 else candle.low),
        )
        for index, candle in enumerate(_candles(36))
    )
    dataset = RuntimeFuturesReplayDataset(
        symbol="HOTUSDT",
        candles=candles,
        derivatives=_derivatives(candles),
    )
    replay_path = (
        tmp_path / "runtime" / "data" / "datasets" / "futures" / "hotusdt.json"
    )
    _write_replay(replay_path, dataset)
    revision = "c" * 40

    exit_code = futures_oos_main(
        (
            "--repository-root",
            str(tmp_path),
            "--replay-file",
            "hotusdt.json",
            "--setup",
            "NEW_LONG_PARTICIPATION",
            "--train-size",
            "6",
            "--test-size",
            "6",
            "--step-size",
            "6",
        ),
        revision_resolver=lambda: FuturesOosRevisionSnapshot(
            revision,
            repository_clean=True,
        ),
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "OOS_EVIDENCE_PUBLISHED"
    assert payload["dataset_sha256"] == dataset.dataset_sha256
    assert payload["code_revision"] == revision
    assert payload["blockers"] == []
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "STAGED_CANDIDATE"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert Path(payload["evidence_path"]).is_file()
    assert Path(payload["artifact_path"]).is_file()


def test_local_futures_oos_cli_rejects_tampered_replay_without_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    replay_path = (
        tmp_path / "runtime" / "data" / "datasets" / "futures" / "hotusdt.json"
    )
    _write_replay(replay_path, _dataset())
    payload = json.loads(replay_path.read_text(encoding="utf-8"))
    payload["dataset_sha256"] = "0" * 64
    replay_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = futures_oos_main(
        (
            "--repository-root",
            str(tmp_path),
            "--replay-file",
            "hotusdt.json",
            "--setup",
            "DELEVERAGING",
            "--train-size",
            "4",
            "--test-size",
            "2",
            "--step-size",
            "2",
        ),
        revision_resolver=lambda: FuturesOosRevisionSnapshot(
            "c" * 40,
            repository_clean=True,
        ),
    )

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["FUTURES_REPLAY_DATASET_HASH_MISMATCH"]
    assert result["execution_allowed"] is False
    assert result["promotion_status"] == "RESEARCH_ONLY"
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    evidence_root = tmp_path / "runtime" / "artifacts" / "validation" / "futures_oos"
    assert not evidence_root.exists()

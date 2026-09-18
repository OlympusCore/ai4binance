"""Closed-candle historical replay snapshot materialization tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.revision import DatasetRevisionBuilder
from ai4binance.historical_replay_application import (
    HistoricalReplayApplicationResult,
    HistoricalReplayApplicationService,
)
from ai4binance.historical_replay_evaluation import (
    HistoricalReplayPublication,
    HistoricalReplaySystemEvaluation,
    HistoricalReplaySystemEvaluator,
)
from ai4binance.historical_replay_persistence import (
    HistoricalReplayEvidencePublisher,
)
from ai4binance.research import (
    HistoricalMarketReplayRequest,
    HistoricalMarketSelection,
    HistoricalReplayDatasetBinding,
    HistoricalReplayEvidenceClass,
    HistoricalReplayExecutionContext,
    VirtualMarket,
    VirtualSystemVersionSegment,
    VirtualWalletEpoch,
)
from ai4binance.research.historical_replay_materialization import (
    HistoricalFuturesReplayDatasetSeries,
    HistoricalFuturesReplaySeriesLoader,
    HistoricalReplayDatasetSeries,
    HistoricalReplaySnapshotMaterializer,
    HistoricalSpotArchiveSeriesLoader,
)
from ai4binance.research_runtime import (
    HistoricalMarketReplayRunner,
    HistoricalReplayRunResult,
    HistoricalReplayRunStatus,
    HistoricalReplaySnapshot,
    build_research_application_service,
)
from ai4binance.schemas import DataQuality, OHLCVCandle
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(hours=2)
HASHES = tuple(character * 64 for character in "abcdef1")


def test_historical_replay_application_result_rejects_invalid_safety_state() -> None:
    replay = SimpleNamespace()
    evaluation = SimpleNamespace(replay_result=replay)
    base = HistoricalReplayApplicationResult(
        snapshots=cast(tuple[HistoricalReplaySnapshot, ...], (SimpleNamespace(),)),
        replay=cast(HistoricalReplayRunResult, replay),
        evaluation=cast(HistoricalReplaySystemEvaluation, evaluation),
        publication=cast(HistoricalReplayPublication, SimpleNamespace()),
    )

    assert base.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="requires snapshots"):
        replace(base, snapshots=())
    with pytest.raises(ValueError, match="identity drift"):
        replace(
            base,
            evaluation=cast(
                HistoricalReplaySystemEvaluation,
                SimpleNamespace(replay_result=SimpleNamespace()),
            ),
        )
    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(base, execution_allowed=True)


def _system_version() -> VirtualSystemVersionSegment:
    return VirtualSystemVersionSegment(
        effective_at=START,
        code_revision="materialization-test",
        configuration_sha256=HASHES[0],
        strategy_bundle_sha256=HASHES[1],
        feature_bundle_sha256=HASHES[2],
        dge_rule_bundle_sha256=HASHES[3],
        risk_policy_sha256=HASHES[4],
        validation_policy_sha256=HASHES[5],
        execution_model_sha256=HASHES[6],
    )


def _candles(
    timestamps: tuple[datetime, ...] | None = None,
) -> tuple[OHLCVCandle, ...]:
    opens = timestamps or tuple(
        START - timedelta(hours=1) + timedelta(hours=index) for index in range(4)
    )
    return tuple(
        OHLCVCandle(
            timestamp=timestamp,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for timestamp in opens
    )


def _binding(candles: tuple[OHLCVCandle, ...]) -> HistoricalReplayDatasetBinding:
    return HistoricalReplayDatasetBinding(
        market=VirtualMarket.SPOT,
        symbol="BTCUSDT",
        timeframe="1h",
        dataset_revision_id="dataset:spot:BTCUSDT:1h",
        dataset_sha256=HASHES[0],
        source_manifest_sha256=HASHES[1],
        source_provenance_ref="binance-vision:materialization-test",
        coverage_start=candles[0].timestamp,
        coverage_end=candles[-1].timestamp,
        row_count=len(candles),
    )


def _request(binding: HistoricalReplayDatasetBinding) -> HistoricalMarketReplayRequest:
    version = _system_version()
    return HistoricalMarketReplayRequest(
        run_id="historical-materialization-test",
        start_at=START,
        end_at=END,
        timeframes=("1h",),
        market_selections=(
            HistoricalMarketSelection(VirtualMarket.SPOT, ("BTCUSDT",)),
        ),
        dataset_bindings=(binding,),
        wallet_epochs=(
            VirtualWalletEpoch(
                epoch_id="historical-materialization-epoch",
                portfolio_id="historical-materialization-portfolio",
                market=VirtualMarket.SPOT,
                initial_capital_usdt=Decimal("1000"),
                started_at=START,
                start_reason="closed-candle materialization test",
                system_segment_sha256=version.semantic_sha256,
                evidence_class=HistoricalReplayEvidenceClass.HISTORICAL_REPLAY,
            ),
        ),
        system_version=version,
    )


def _context(
    binding: HistoricalReplayDatasetBinding,
    observed_at: datetime,
    candle: OHLCVCandle,
) -> HistoricalReplayExecutionContext:
    del candle
    return HistoricalReplayExecutionContext(
        market=binding.market,
        symbol=binding.symbol,
        timeframe=binding.timeframe,
        observed_at=observed_at,
        dataset_revision_id=binding.dataset_revision_id,
        dataset_sha256=binding.dataset_sha256,
        source_manifest_sha256=binding.source_manifest_sha256,
        source_provenance_ref=binding.source_provenance_ref,
        execution_model_sha256=HASHES[6],
        fee_ratio=Decimal("0.001"),
        slippage_ratio=Decimal("0.0005"),
        half_spread_ratio=Decimal("0.0001"),
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.00001"),
        minimum_notional=Decimal("5"),
    )


def _write_spot_archive(
    root: Path,
) -> tuple[HistoricalReplayDatasetBinding, tuple[OHLCVCandle, ...]]:
    archive_root = root
    candles = _candles()
    manifest = ParquetOHLCVArchive(archive_root).update(
        "BTCUSDT",
        "1h",
        candles,
        source="BINANCE_VISION_CHECKSUM_VERIFIED",
        generated_at=START,
    )
    source_manifest = {
        "dataset_row_count": manifest.row_count,
        "dataset_sha256": manifest.sha256,
        "source_file_count": 1,
    }
    (archive_root / "BTCUSDT" / "1h.source-manifest.json").write_text(
        json.dumps(source_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    builder = DatasetRevisionBuilder(archive_root)
    revision = builder.build(
        symbol="BTCUSDT",
        timeframes=("1h",),
        generated_at=START,
    )
    builder.write(revision)
    entry = revision.entries[0]
    return (
        HistoricalReplayDatasetBinding(
            market=VirtualMarket.SPOT,
            symbol="BTCUSDT",
            timeframe="1h",
            dataset_revision_id=revision.revision_id,
            dataset_sha256=entry.dataset_sha256,
            source_manifest_sha256=entry.source_manifest_sha256,
            source_provenance_ref=entry.source,
            coverage_start=datetime.fromisoformat(entry.first_timestamp),
            coverage_end=datetime.fromisoformat(entry.last_timestamp),
            row_count=entry.row_count,
        ),
        candles,
    )


def _write_futures_replay(
    root: Path,
    *,
    include_mark_prices: bool = True,
) -> tuple[HistoricalReplayDatasetBinding, Path]:
    candles = _candles()
    source_id = "BINANCE_USD_M_PUBLIC_REST"
    source_url = "https://fapi.binance.com/fapi/v1"

    def point(
        metric: DerivativesMetric,
        candle: OHLCVCandle,
        value: Decimal,
    ) -> MetricPoint:
        return MetricPoint(
            metric=metric,
            timestamp=candle.timestamp,
            value=value,
            provenance=Provenance(source_id, END, source_url),
        )

    series = {
        DerivativesMetric.OPEN_INTEREST: tuple(
            point(DerivativesMetric.OPEN_INTEREST, candle, Decimal(1000 + index))
            for index, candle in enumerate(candles)
        ),
        DerivativesMetric.FUNDING_RATE: tuple(
            point(DerivativesMetric.FUNDING_RATE, candles[index], Decimal("0.001"))
            for index in (0, 2)
        ),
    }
    if include_mark_prices:
        series[DerivativesMetric.MARK_PRICE] = tuple(
            point(DerivativesMetric.MARK_PRICE, candle, candle.close)
            for candle in candles
        )
    dataset = RuntimeFuturesReplayDataset(
        symbol="BTCUSDT",
        candles=candles,
        derivatives=DerivativesDataset(
            symbol="BTCUSDT",
            as_of=END,
            series=series,
            source=source_id,
        ),
    )
    path = root / "btcusdt.json"
    path.write_text(
        json.dumps(dataset.to_artifact_payload(), sort_keys=True),
        encoding="utf-8",
    )
    artifact_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    binding = HistoricalReplayDatasetBinding(
        market=VirtualMarket.USD_M_FUTURES,
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        dataset_revision_id=f"dataset:{dataset.dataset_sha256[:24]}",
        dataset_sha256=dataset.dataset_sha256,
        source_manifest_sha256=artifact_sha256,
        source_provenance_ref=source_id,
        coverage_start=candles[0].timestamp,
        coverage_end=candles[-1].timestamp,
        row_count=len(candles),
    )
    return binding, path


def test_materializer_builds_deterministic_closed_candle_prefixes() -> None:
    candles = _candles()
    binding = _binding(candles)
    request = _request(binding)
    materializer = HistoricalReplaySnapshotMaterializer(
        history_limit=3,
        minimum_closed_candles=2,
    )

    first = materializer.materialize(
        request,
        (HistoricalReplayDatasetSeries(binding, candles),),
        _context,
    )
    second = materializer.materialize(
        request,
        (HistoricalReplayDatasetSeries(binding, candles),),
        _context,
    )

    assert first == second
    assert tuple(item.created_at for item in first) == (
        START,
        START + timedelta(hours=1),
        END,
    )
    assert tuple(
        item.snapshot.ohlcv_by_timeframe["1h"][-1].timestamp for item in first
    ) == (
        START - timedelta(hours=1),
        START,
        START + timedelta(hours=1),
    )
    assert tuple(item.snapshot.data_quality for item in first) == (
        DataQuality.DATA_INVALID,
        DataQuality.DATA_VALID,
        DataQuality.DATA_VALID,
    )
    assert first[-1].snapshot.bid == Decimal("99.9900")
    assert first[-1].snapshot.ask == Decimal("100.0100")
    assert first[-1].snapshot.spread == Decimal("0.0200")
    assert first[-1].execution_context is not None
    assert first[-1].execution_context.execution_allowed is False


def test_dataset_series_rejects_binding_mismatch() -> None:
    candles = _candles()
    binding = _binding(candles)

    with pytest.raises(ValueError, match="row count"):
        HistoricalReplayDatasetSeries(replace(binding, row_count=3), candles)


def test_spot_archive_loader_rebuilds_revision_and_verifies_parquet(
    tmp_path: Path,
) -> None:
    binding, candles = _write_spot_archive(tmp_path)

    loaded = HistoricalSpotArchiveSeriesLoader(tmp_path).load(binding)

    assert loaded.binding == binding
    assert loaded.candles == candles


def test_spot_archive_loader_reads_only_bound_replay_window(tmp_path: Path) -> None:
    binding, candles = _write_spot_archive(tmp_path)
    loader = HistoricalSpotArchiveSeriesLoader(tmp_path)
    loaded = loader.load_many_window(
        (binding,),
        start_at=START,
        end_at=START + timedelta(hours=1),
        history_limit=2,
    )

    assert loaded[0].binding == binding
    assert loaded[0].candles == candles[:3]
    assert loaded[0].complete_binding_coverage is False
    request = replace(_request(binding), end_at=START + timedelta(hours=1))
    materializer = HistoricalReplaySnapshotMaterializer(
        history_limit=2,
        minimum_closed_candles=2,
    )
    assert materializer.materialize(request, loaded, _context) == (
        materializer.materialize(request, (loader.load(binding),), _context)
    )


def test_spot_archive_loader_rejects_revision_tampering(tmp_path: Path) -> None:
    binding, _ = _write_spot_archive(tmp_path)
    revision_path = tmp_path / "BTCUSDT" / "dataset-revision.json"
    payload = json.loads(revision_path.read_text(encoding="utf-8"))
    payload["revision_id"] = "dataset:tampered"
    revision_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="REVISION_EVIDENCE_MISMATCH"):
        HistoricalSpotArchiveSeriesLoader(tmp_path).load(binding)


def test_spot_archive_loader_enforces_row_bound(tmp_path: Path) -> None:
    binding, _ = _write_spot_archive(tmp_path)

    with pytest.raises(ValueError, match="ROW_COUNT_OUT_OF_BOUNDS"):
        HistoricalSpotArchiveSeriesLoader(
            tmp_path,
            max_rows=3,
        ).load(binding)


def test_spot_archive_loader_rejects_missing_bound_file(tmp_path: Path) -> None:
    binding, _ = _write_spot_archive(tmp_path)
    (tmp_path / "BTCUSDT" / "1h.source-manifest.json").unlink()

    with pytest.raises(ValueError, match="FILE_UNAVAILABLE_OR_UNSAFE"):
        HistoricalSpotArchiveSeriesLoader(tmp_path).load(binding)


def test_futures_loader_materializes_point_in_time_mark_and_funding(
    tmp_path: Path,
) -> None:
    binding, replay_path = _write_futures_replay(tmp_path)
    series = HistoricalFuturesReplaySeriesLoader(tmp_path).load(
        binding,
        replay_path,
    )
    version = _system_version()
    request = HistoricalMarketReplayRequest(
        run_id="historical-futures-materialization-test",
        start_at=START,
        end_at=END,
        timeframes=("1h",),
        market_selections=(
            HistoricalMarketSelection(
                VirtualMarket.USD_M_FUTURES,
                ("BTCUSDT",),
            ),
        ),
        dataset_bindings=(binding,),
        wallet_epochs=(
            VirtualWalletEpoch(
                epoch_id="historical-futures-materialization-epoch",
                portfolio_id="historical-futures-materialization-portfolio",
                market=VirtualMarket.USD_M_FUTURES,
                initial_capital_usdt=Decimal("1000"),
                started_at=START,
                start_reason="point-in-time Futures materialization test",
                system_segment_sha256=version.semantic_sha256,
                evidence_class=HistoricalReplayEvidenceClass.HISTORICAL_REPLAY,
            ),
        ),
        system_version=version,
    )

    def futures_context(
        event_binding: HistoricalReplayDatasetBinding,
        observed_at: datetime,
        candle: OHLCVCandle,
    ) -> HistoricalReplayExecutionContext:
        evidence = series.evidence_for(candle)
        return HistoricalReplayExecutionContext(
            market=event_binding.market,
            symbol=event_binding.symbol,
            timeframe=event_binding.timeframe,
            observed_at=observed_at,
            dataset_revision_id=event_binding.dataset_revision_id,
            dataset_sha256=event_binding.dataset_sha256,
            source_manifest_sha256=event_binding.source_manifest_sha256,
            source_provenance_ref=event_binding.source_provenance_ref,
            execution_model_sha256=HASHES[6],
            fee_ratio=Decimal("0.001"),
            slippage_ratio=Decimal("0.0005"),
            half_spread_ratio=Decimal("0.0001"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.001"),
            minimum_notional=Decimal("5"),
            mark_price=evidence.mark_price.value,
            funding_rate=evidence.funding_rate.value,
            funding_payment_due=evidence.funding_payment_due,
            leverage=5,
            isolated_margin_usdt=Decimal("100"),
            maintenance_margin_ratio=Decimal("0.02"),
            liquidation_fee_ratio=Decimal("0.005"),
        )

    snapshots = HistoricalReplaySnapshotMaterializer(
        history_limit=3,
        minimum_closed_candles=2,
    ).materialize(request, (series,), futures_context)

    assert tuple(
        item.execution_context.funding_payment_due
        for item in snapshots
        if item.execution_context is not None
    ) == (True, False, True)
    assert all(
        item.execution_context is not None
        and item.execution_context.mark_price == Decimal("100")
        and item.execution_context.execution_allowed is False
        and item.execution_context.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        for item in snapshots
    )
    result = HistoricalMarketReplayRunner(build_research_application_service()).run(
        request, snapshots
    )
    assert len(result.cycles) == 3
    assert result.status is HistoricalReplayRunStatus.RUNNING_WITH_BLOCKERS
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_futures_loader_rejects_binding_drift(tmp_path: Path) -> None:
    binding, replay_path = _write_futures_replay(tmp_path)

    with pytest.raises(ValueError, match="DATASET_BINDING_MISMATCH"):
        HistoricalFuturesReplaySeriesLoader(tmp_path).load(
            replace(binding, source_manifest_sha256=HASHES[0]),
            replay_path,
        )


def test_historical_replay_application_service_owns_complete_chain(
    tmp_path: Path,
) -> None:
    candles = _candles()
    binding = _binding(candles)
    request = _request(binding)
    service = HistoricalReplayApplicationService(
        materializer=HistoricalReplaySnapshotMaterializer(
            history_limit=3,
            minimum_closed_candles=2,
        ),
        runner=HistoricalMarketReplayRunner(build_research_application_service()),
        evaluator=HistoricalReplaySystemEvaluator(),
    )
    assert isinstance(
        HistoricalReplayEvidencePublisher(service.evaluator.runtime),
        HistoricalReplayEvidencePublisher,
    )

    result = service.execute(
        request,
        (HistoricalReplayDatasetSeries(binding, candles),),
        _context,
        root=tmp_path,
        stamp="20260101T020000Z",
    )

    assert result.snapshots == tuple(
        cycle.replay_snapshot for cycle in result.replay.cycles
    )
    assert result.evaluation.replay_result is result.replay
    assert result.publication.state_path.is_file()
    assert result.execution_allowed is False
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_futures_loader_rejects_missing_mark_history(tmp_path: Path) -> None:
    binding, replay_path = _write_futures_replay(
        tmp_path,
        include_mark_prices=False,
    )

    with pytest.raises(ValueError, match="mark prices must align"):
        HistoricalFuturesReplaySeriesLoader(tmp_path).load(binding, replay_path)


def test_materializer_requires_exact_request_dataset_coverage() -> None:
    candles = _candles()
    binding = _binding(candles)

    with pytest.raises(ValueError, match="exactly cover request"):
        HistoricalReplaySnapshotMaterializer(
            history_limit=3,
            minimum_closed_candles=2,
        ).materialize(_request(binding), (), _context)


def test_materializer_rejects_execution_context_drift() -> None:
    candles = _candles()
    binding = _binding(candles)

    def drifted_context(
        event_binding: HistoricalReplayDatasetBinding,
        observed_at: datetime,
        candle: OHLCVCandle,
    ) -> HistoricalReplayExecutionContext:
        return replace(
            _context(event_binding, observed_at, candle),
            execution_model_sha256=HASHES[0],
        )

    with pytest.raises(ValueError, match="match the system version"):
        HistoricalReplaySnapshotMaterializer(
            history_limit=3,
            minimum_closed_candles=2,
        ).materialize(
            _request(binding),
            (HistoricalReplayDatasetSeries(binding, candles),),
            drifted_context,
        )


def test_materializer_rejects_candle_cadence_gap() -> None:
    candles = _candles(
        (
            START - timedelta(hours=1),
            START + timedelta(hours=1),
            START + timedelta(hours=2),
        )
    )
    binding = _binding(candles)

    with pytest.raises(ValueError, match="cadence gap"):
        HistoricalReplaySnapshotMaterializer(
            history_limit=3,
            minimum_closed_candles=2,
        ).materialize(
            _request(binding),
            (HistoricalReplayDatasetSeries(binding, candles),),
            _context,
        )


@pytest.mark.parametrize(
    ("history_limit", "minimum_closed_candles"),
    [(1, 1), (10_001, 2), (3, 4)],
)
def test_materializer_rejects_unsafe_history_bounds(
    history_limit: int,
    minimum_closed_candles: int,
) -> None:
    with pytest.raises(ValueError, match="historical replay"):
        HistoricalReplaySnapshotMaterializer(
            history_limit=history_limit,
            minimum_closed_candles=minimum_closed_candles,
        )


@pytest.mark.parametrize(
    ("binding_change", "candles", "coverage", "message"),
    [
        (
            {},
            (),
            True,
            "cannot be empty",
        ),
        (
            {},
            _candles((START, START)),
            True,
            "unique and chronological",
        ),
        (
            {"row_count": 3},
            _candles(),
            True,
            "row count",
        ),
        (
            {"coverage_end": START},
            _candles(),
            True,
            "coverage must match",
        ),
        (
            {"row_count": 1},
            _candles(),
            False,
            "window exceeds",
        ),
    ],
)
def test_dataset_series_rejects_unsafe_or_inconsistent_coverage(
    binding_change: dict[str, object],
    candles: tuple[OHLCVCandle, ...],
    coverage: bool,
    message: str,
) -> None:
    source = _candles()
    binding = replace(_binding(source), **binding_change)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=message):
        HistoricalReplayDatasetSeries(
            binding,
            candles or source if binding_change else candles,
            complete_binding_coverage=coverage,
        )


def test_futures_series_and_materializer_static_checks_fail_closed(
    tmp_path: Path,
) -> None:
    binding, replay_path = _write_futures_replay(tmp_path)
    series = HistoricalFuturesReplaySeriesLoader(tmp_path).load(binding, replay_path)

    with pytest.raises(ValueError, match="not bound"):
        series.evidence_for(
            OHLCVCandle(
                START + timedelta(days=1),
                Decimal("100"),
                Decimal("101"),
                Decimal("99"),
                Decimal("100"),
                Decimal("1000"),
            )
        )
    with pytest.raises(ValueError, match="Futures binding"):
        HistoricalFuturesReplayDatasetSeries(
            binding=replace(binding, market=VirtualMarket.SPOT),
            candles=series.candles,
            mark_prices=series.mark_prices,
            funding_rates=series.funding_rates,
        )
    with pytest.raises(ValueError, match="mark prices"):
        HistoricalFuturesReplayDatasetSeries(
            binding=binding,
            candles=series.candles,
            mark_prices=series.mark_prices[:-1],
            funding_rates=series.funding_rates,
        )

    materializer = HistoricalReplaySnapshotMaterializer()
    context = _context(_binding(_candles()), START, _candles()[0])
    with pytest.raises(ValueError, match="event dataset"):
        materializer._require_execution_context(
            context=replace(context, symbol="ETHUSDT"),
            binding=_binding(_candles()),
            observed_at=START,
            execution_model_sha256=HASHES[6],
        )
    with pytest.raises(ValueError, match="event time"):
        materializer._require_execution_context(
            context=context,
            binding=_binding(_candles()),
            observed_at=START + timedelta(hours=1),
            execution_model_sha256=HASHES[6],
        )
    with pytest.raises(ValueError, match="dataset evidence"):
        materializer._require_execution_context(
            context=replace(context, dataset_sha256=HASHES[2]),
            binding=_binding(_candles()),
            observed_at=START,
            execution_model_sha256=HASHES[6],
        )
    assert materializer._snapshot_id(
        market="SPOT",
        symbol="BTCUSDT",
        observed_at=START,
        bindings=(_binding(_candles()),),
        context=context,
    ).startswith("historical:spot:btcusdt:")


def test_replay_materialization_boundary_guards_cover_loader_and_series(
    tmp_path: Path,
) -> None:
    candles = _candles()
    binding = _binding(candles)
    with pytest.raises(ValueError, match="mode must be boolean"):
        HistoricalReplayDatasetSeries(
            binding,
            candles,
            complete_binding_coverage=cast(bool, 1),
        )
    with pytest.raises(ValueError, match="canonical UTC"):
        HistoricalReplayDatasetSeries(
            binding,
            cast(
                tuple[OHLCVCandle, ...],
                (SimpleNamespace(timestamp=START.replace(tzinfo=None)),),
            ),
        )
    with pytest.raises(ValueError, match="row bound"):
        HistoricalSpotArchiveSeriesLoader(tmp_path, max_rows=1)
    with pytest.raises(ValueError, match="revision byte bound"):
        HistoricalSpotArchiveSeriesLoader(tmp_path, max_revision_bytes=1)

    loader = HistoricalSpotArchiveSeriesLoader(tmp_path)
    with pytest.raises(ValueError, match="cannot be empty"):
        loader.load_many(())
    with pytest.raises(TypeError, match="requires dataset bindings"):
        loader.load_many(cast(tuple[HistoricalReplayDatasetBinding, ...], (object(),)))
    with pytest.raises(ValueError, match="requires Spot"):
        loader.load_many((replace(binding, market=VirtualMarket.USD_M_FUTURES),))
    with pytest.raises(ValueError, match="must be unique"):
        loader.load_many((binding, binding))
    with pytest.raises(ValueError, match="ordered UTC"):
        loader.load_many_window(
            (binding,),
            start_at=END,
            end_at=START,
        )
    with pytest.raises(ValueError, match="history limit"):
        loader.load_many_window(
            (binding,),
            start_at=START,
            end_at=END,
            history_limit=1,
        )
    with pytest.raises(ValueError, match="cannot be empty"):
        loader.load_many_window((), start_at=START, end_at=END, history_limit=2)
    with pytest.raises(TypeError, match="requires dataset bindings"):
        loader.load_many_window(
            cast(tuple[HistoricalReplayDatasetBinding, ...], (object(),)),
            start_at=START,
            end_at=END,
        )
    with pytest.raises(ValueError, match="requires Spot"):
        loader.load_many_window(
            (replace(binding, market=VirtualMarket.USD_M_FUTURES),),
            start_at=START,
            end_at=END,
        )
    with pytest.raises(ValueError, match="must be unique"):
        loader.load_many_window((binding, binding), start_at=START, end_at=END)
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_UNSAFE"):
        loader._verified_revision("BTCUSDT")

    futures_binding, replay_path = _write_futures_replay(tmp_path)
    futures = HistoricalFuturesReplaySeriesLoader(tmp_path).load(
        futures_binding,
        replay_path,
    )
    with pytest.raises(ValueError, match="mark price evidence"):
        HistoricalFuturesReplayDatasetSeries(
            binding=futures_binding,
            candles=futures.candles,
            mark_prices=(
                replace(futures.mark_prices[0], metric=DerivativesMetric.FUNDING_RATE),
                *futures.mark_prices[1:],
            ),
            funding_rates=futures.funding_rates,
        )
    with pytest.raises(ValueError, match="funding evidence"):
        HistoricalFuturesReplayDatasetSeries(
            binding=futures_binding,
            candles=futures.candles,
            mark_prices=futures.mark_prices,
            funding_rates=(),
        )
    with pytest.raises(ValueError, match="requires a Futures binding"):
        HistoricalFuturesReplaySeriesLoader(tmp_path).load(binding, replay_path)


def test_spot_revision_parser_and_bound_series_reject_incomplete_evidence(
    tmp_path: Path,
) -> None:
    _binding_value, _candles_value = _write_spot_archive(tmp_path)
    loader = HistoricalSpotArchiveSeriesLoader(tmp_path)
    revision_path = tmp_path / "BTCUSDT" / "dataset-revision.json"
    revision_path.write_bytes(b"")
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_UNSAFE"):
        loader._verified_revision("BTCUSDT")
    revision_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="REVISION_INVALID"):
        loader._verified_revision("BTCUSDT")
    revision_path.write_text('{"entries": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="REVISION_INVALID"):
        loader._verified_revision("BTCUSDT")

    repaired_binding, _ = _write_spot_archive(tmp_path)
    revision = loader._verified_revision("BTCUSDT")
    with pytest.raises(ValueError, match="TIMEFRAME_NOT_IN_REVISION"):
        loader._load_bound_series(
            replace(repaired_binding, timeframe="4h"),
            revision,
        )
    with pytest.raises(ValueError, match="DATASET_BINDING_MISMATCH"):
        loader._load_bound_series(
            replace(repaired_binding, dataset_sha256=HASHES[2]),
            revision,
        )


def test_materializer_rejects_untyped_duplicate_and_empty_event_series() -> None:
    candles = _candles()
    binding = _binding(candles)
    request = _request(binding)
    materializer = HistoricalReplaySnapshotMaterializer(
        history_limit=3,
        minimum_closed_candles=2,
    )
    dataset = HistoricalReplayDatasetSeries(binding, candles)

    with pytest.raises(TypeError, match="canonical dataset series"):
        materializer.materialize(
            request,
            cast(tuple[HistoricalReplayDatasetSeries, ...], (object(),)),
            _context,
        )
    with pytest.raises(ValueError, match="datasets must be unique"):
        materializer.materialize(request, (dataset, dataset), _context)
    drifted = HistoricalReplayDatasetSeries(
        replace(binding, dataset_sha256=HASHES[2]),
        candles,
    )
    with pytest.raises(ValueError, match="preserve exact bindings"):
        materializer.materialize(request, (drifted,), _context)
    with pytest.raises(TypeError, match="invalid contract"):
        materializer.materialize(
            request,
            (dataset,),
            cast(object, lambda *_args: object()),  # type: ignore[arg-type]
        )

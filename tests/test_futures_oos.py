"""Fail-closed USD-M Futures OOS evidence and runtime integration tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.application.runtime import MarketAdvisory, RuntimeOpportunityReviewItem
from ai4binance.cli.runtime import RuntimeFuturesAdvisor
from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting import (
    BacktestIntent,
    BacktestResult,
    PerformanceEngineReport,
    RejectedSignal,
    SignalProvider,
)
from ai4binance.schemas import OHLCVCandle, OOSValidationStatus
from ai4binance.validation import (
    FuturesOosEvidenceWriter,
    MarketRegime,
    ParameterSet,
    WalkForwardConfig,
    WalkForwardReport,
    WalkForwardValidator,
)
from ai4binance.validation.futures_oos import (
    FUTURES_OOS_STRATEGY_ID,
    FUTURES_OOS_STRATEGY_VERSION,
    FuturesOosEvidenceQuery,
    FuturesOosEvidenceReader,
    runtime_futures_strategy_sha256,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesFeatures,
    PriceOiRegime,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
STRATEGY_SHA256 = runtime_futures_strategy_sha256(
    short_lookback=1,
    medium_lookback=4,
)


def _query() -> FuturesOosEvidenceQuery:
    return FuturesOosEvidenceQuery(
        symbol="HOTUSDT",
        timeframe="1h",
        setup_name="DELEVERAGING",
        strategy_sha256=STRATEGY_SHA256,
        as_of=NOW,
    )


def _write_evidence(
    root: Path,
    *,
    created_at: datetime = NOW - timedelta(days=1),
    artifact_path: str = "HOTUSDT/1h/deleveraging.oos.json",
    blockers: list[str] | None = None,
    setup_name: str = "DELEVERAGING",
    strategy_sha256: str = STRATEGY_SHA256,
) -> tuple[Path, Path]:
    artifact = root / "HOTUSDT" / "1h" / "deleveraging.oos.json"
    evidence = artifact.with_name("deleveraging.oos-evidence.json")
    artifact.unlink(missing_ok=True)
    evidence.unlink(missing_ok=True)
    FuturesOosEvidenceWriter(root).write(
        _approved_report(),
        setup_name="DELEVERAGING",
        strategy_sha256=STRATEGY_SHA256,
        dataset_sha256="d" * 64,
        code_revision="c" * 40,
    )
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    artifact_payload.update(
        {
            "created_at": created_at.isoformat(),
            "setup_name": setup_name,
            "strategy_sha256": strategy_sha256,
            "blockers": blockers or [],
        }
    )
    artifact_payload["walk_forward_report"]["created_at"] = created_at.isoformat()
    artifact.write_text(
        json.dumps(artifact_payload, sort_keys=True),
        encoding="utf-8",
    )
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
    evidence_payload.update(
        {
            "created_at": created_at.isoformat(),
            "setup_name": setup_name,
            "strategy_sha256": strategy_sha256,
            "blockers": blockers or [],
            "artifact_path": artifact_path,
            "artifact_sha256": artifact_sha256,
        }
    )
    evidence.write_text(
        json.dumps(evidence_payload, sort_keys=True),
        encoding="utf-8",
    )
    return evidence, artifact


def test_exact_bound_oos_evidence_validates_without_execution_authority(
    tmp_path: Path,
) -> None:
    _write_evidence(tmp_path)

    assert FuturesOosEvidenceReader(tmp_path).is_validated(_query()) is True


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("setup_name", "NEW_SHORT_PRESSURE"),
        ("strategy_sha256", "e" * 64),
        ("blockers", ["OOS_RETURN_INSUFFICIENT"]),
    ],
)
def test_conflicting_or_blocked_oos_evidence_fails_closed(
    tmp_path: Path,
    override: str,
    value: object,
) -> None:
    arguments = {override: value}
    _write_evidence(tmp_path, **arguments)  # type: ignore[arg-type]

    assert FuturesOosEvidenceReader(tmp_path).is_validated(_query()) is False


def test_missing_stale_future_tampered_and_unsafe_evidence_fail_closed(
    tmp_path: Path,
) -> None:
    reader = FuturesOosEvidenceReader(tmp_path)
    assert reader.is_validated(_query()) is False

    _write_evidence(tmp_path, created_at=NOW - timedelta(days=91))
    assert reader.is_validated(_query()) is False

    _write_evidence(tmp_path, created_at=NOW + timedelta(minutes=6))
    assert reader.is_validated(_query()) is False

    _, artifact = _write_evidence(tmp_path)
    artifact.write_text("tampered", encoding="utf-8")
    assert reader.is_validated(_query()) is False

    _write_evidence(tmp_path, artifact_path="../outside.json")
    assert reader.is_validated(_query()) is False


def test_reader_rejects_checksum_valid_artifact_without_validation_lineage(
    tmp_path: Path,
) -> None:
    evidence, artifact = _write_evidence(tmp_path)
    artifact.write_text('{"validated":true}\n', encoding="utf-8")
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    assert FuturesOosEvidenceReader(tmp_path).is_validated(_query()) is False


def test_query_and_reader_reject_invalid_contract_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="symbol"):
        FuturesOosEvidenceQuery(
            symbol="../HOTUSDT",
            timeframe="1h",
            setup_name="DELEVERAGING",
            strategy_sha256=STRATEGY_SHA256,
            as_of=NOW,
        )
    with pytest.raises(ValueError, match="size bounds"):
        FuturesOosEvidenceReader(tmp_path, max_evidence_bytes=0)


class _CollectorStub:
    def collect(self, symbol: str, period: str, limit: int) -> DerivativesDataset:
        assert (symbol, period, limit) == ("HOTUSDT", "1h", 100)
        return DerivativesDataset(symbol, NOW, {})


class _FeatureEngineStub:
    short_lookback = 1
    medium_lookback = 4

    def compute(
        self,
        dataset: DerivativesDataset,
        prices: tuple[object, ...],
    ) -> DerivativesFeatures:
        assert dataset.symbol == "HOTUSDT"
        assert prices == ()
        return DerivativesFeatures(
            symbol="HOTUSDT",
            as_of=NOW,
            oi_change_short=None,
            oi_change_medium=None,
            oi_zscore=None,
            oi_percentile=None,
            price_oi_regime=PriceOiRegime.DELEVERAGING,
            funding_percentile=None,
            basis_zscore=None,
            taker_imbalance=None,
            top_vs_global_divergence=None,
            mark_index_deviation=None,
            blockers=(),
        )


@dataclass
class _EvidenceStub:
    validated: bool
    query: FuturesOosEvidenceQuery | None = None

    def is_validated(self, query: FuturesOosEvidenceQuery) -> bool:
        self.query = query
        return self.validated


def _advisory(evidence: _EvidenceStub | None) -> MarketAdvisory:
    advisor = RuntimeFuturesAdvisor(
        _CollectorStub(),  # type: ignore[arg-type]
        _FeatureEngineStub(),  # type: ignore[arg-type]
        evidence,
    )
    snapshot = SimpleNamespace(symbol="HOTUSDT", ohlcv_by_timeframe={"1h": ()})
    return advisor.build(snapshot)


def test_runtime_futures_advisor_defaults_to_oos_blocked() -> None:
    advisory = _advisory(None)

    assert advisory.blockers == ("FUTURES_OOS_NOT_APPROVED",)
    assert advisory.action == "NO_TRADE"
    assert advisory.promotion_status == "RESEARCH_ONLY"
    assert advisory.execution_allowed is False
    assert advisory.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize("timeframe", ["5m", "15m", "1h"])
def test_runtime_futures_advisor_binds_collector_and_oos_to_requested_timeframe(
    timeframe: str,
) -> None:
    class Collector:
        def collect(self, symbol: str, period: str, limit: int) -> DerivativesDataset:
            assert (symbol, period, limit) == ("HOTUSDT", timeframe, 100)
            return DerivativesDataset(symbol, NOW, {})

    evidence = _EvidenceStub(False)
    advisor = RuntimeFuturesAdvisor(
        Collector(),  # type: ignore[arg-type]
        _FeatureEngineStub(),  # type: ignore[arg-type]
        evidence,
        timeframe=timeframe,
    )
    advisory = advisor.build(
        SimpleNamespace(symbol="HOTUSDT", ohlcv_by_timeframe={timeframe: ()})
    )
    assert evidence.query is not None
    assert evidence.query.timeframe == timeframe
    item = advisory.opportunity_radar[0]
    assert isinstance(item, RuntimeOpportunityReviewItem)
    assert item.timeframe == timeframe
    assert advisory.blockers == ("FUTURES_OOS_NOT_APPROVED",)
    assert advisory.execution_allowed is False
    assert advisory.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runtime_futures_advisor_consumes_only_validated_exact_query() -> None:
    evidence = _EvidenceStub(True)
    advisory = _advisory(evidence)

    assert advisory.blockers == ()
    assert evidence.query == _query()
    assert advisory.action == "NO_TRADE"
    assert advisory.promotion_status == "RESEARCH_ONLY"
    assert advisory.execution_allowed is False
    assert advisory.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def _validation_candles() -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(days=2) + timedelta(hours=index),
            open=Decimal("100"),
            high=Decimal("103"),
            low=Decimal("98"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for index in range(12)
    )


def _strategy_factory(parameters: ParameterSet) -> SignalProvider:
    values = dict(parameters.values)

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) % 2 == 0:
            return None
        return BacktestIntent(
            signal_id=f"{parameters.name}:{history[-1].timestamp.isoformat()}",
            timestamp=history[-1].timestamp,
            stop_loss=Decimal(str(values["stop"])),
            take_profit=Decimal(str(values["target"])),
            atr=Decimal("2"),
        )

    return provider


def _spot_approved_report() -> WalkForwardReport:
    parameters = ParameterSet(
        "futures-regime",
        (("target", 102.0), ("stop", 95.0)),
    )
    return WalkForwardValidator().validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=_validation_candles(),
        parameters=(parameters,),
        strategy_factory=_strategy_factory,
        regime_classifier=lambda candle: (
            MarketRegime.TREND
            if candle.timestamp.hour % 4 in {0, 1}
            else MarketRegime.RANGE
        ),
        config=WalkForwardConfig(
            train_size=4,
            test_size=2,
            step_size=2,
            min_oos_trades=4,
            max_turnover=0.6,
            max_edge_concentration=0.3,
        ),
    )


def _approved_report() -> WalkForwardReport:
    report = _spot_approved_report()
    return replace(
        report,
        folds=tuple(
            replace(
                fold,
                training_result=_as_futures_result(
                    fold.training_result,
                    setup_name="DELEVERAGING",
                ),
                oos_result=_as_futures_result(
                    fold.oos_result,
                    setup_name="DELEVERAGING",
                ),
            )
            for fold in report.folds
        ),
    )


def _as_futures_result(
    result: BacktestResult,
    *,
    setup_name: str,
) -> BacktestResult:
    trades = tuple(
        replace(
            trade,
            attribution=replace(
                trade.attribution,
                strategy_id=FUTURES_OOS_STRATEGY_ID,
                strategy_version=FUTURES_OOS_STRATEGY_VERSION,
                strategy_config_hash=STRATEGY_SHA256,
                market="USD_M_FUTURES",
                symbol="HOTUSDT",
                regime=setup_name,
                timeframe="1h",
            ),
        )
        for trade in result.trades
    )
    metrics = replace(result.metrics, market="USD_M_FUTURES")
    return replace(
        result,
        trades=trades,
        metrics=metrics,
        trade_outcomes=tuple(trade.trade_outcome for trade in trades),
        performance_engine_report=PerformanceEngineReport(futures_metrics=metrics),
    )


def test_writer_persists_idempotent_exact_bound_approved_report(
    tmp_path: Path,
) -> None:
    report = _approved_report()
    writer = FuturesOosEvidenceWriter(tmp_path)

    first = writer.write(
        report,
        setup_name="DELEVERAGING",
        strategy_sha256=STRATEGY_SHA256,
        dataset_sha256="d" * 64,
        code_revision="c" * 40,
    )
    second = writer.write(
        report,
        setup_name="DELEVERAGING",
        strategy_sha256=STRATEGY_SHA256,
        dataset_sha256="d" * 64,
        code_revision="c" * 40,
    )
    query = replace(_query(), as_of=report.created_at + timedelta(days=1))

    assert first.created is True
    assert second == replace(first, created=False)
    assert first.execution_allowed is False
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert FuturesOosEvidenceReader(tmp_path).is_validated(query) is True


def test_writer_rejects_weak_incomplete_and_conflicting_reports(
    tmp_path: Path,
) -> None:
    report = _approved_report()
    writer = FuturesOosEvidenceWriter(tmp_path)
    arguments = {
        "setup_name": "DELEVERAGING",
        "strategy_sha256": STRATEGY_SHA256,
        "dataset_sha256": "d" * 64,
        "code_revision": "c" * 40,
    }
    weak = replace(
        report,
        oos_validation_status=OOSValidationStatus.INSUFFICIENT,
        promotion_status=ValidationStatus.RESEARCH_ONLY,
        blockers=("OOS_RETURN_INSUFFICIENT",),
    )
    with pytest.raises(ValueError, match="not approved"):
        writer.write(weak, **arguments)

    incomplete = replace(
        report,
        statistical_evidence=replace(
            report.statistical_evidence,
            confirmatory=False,
        ),
    )
    with pytest.raises(ValueError, match="incomplete"):
        writer.write(incomplete, **arguments)

    writer.write(report, **arguments)
    with pytest.raises(ValueError, match="FUTURES_OOS_EVIDENCE_CONFLICT"):
        writer.write(report, **{**arguments, "dataset_sha256": "e" * 64})


def test_writer_rejects_spot_and_futures_missing_data_lineage(
    tmp_path: Path,
) -> None:
    writer = FuturesOosEvidenceWriter(tmp_path)
    arguments = {
        "setup_name": "DELEVERAGING",
        "strategy_sha256": STRATEGY_SHA256,
        "dataset_sha256": "d" * 64,
        "code_revision": "c" * 40,
    }
    with pytest.raises(ValueError, match="market lineage"):
        writer.write(_spot_approved_report(), **arguments)

    report = _approved_report()
    first_fold = report.folds[0]
    unavailable = replace(
        first_fold.oos_result,
        rejected_signals=(
            RejectedSignal(
                signal_id="futures-missing-data",
                timestamp=first_fold.test_started_at,
                blockers=("DATA_UNAVAILABLE",),
            ),
        ),
    )
    invalid = replace(
        report,
        folds=(replace(first_fold, oos_result=unavailable), *report.folds[1:]),
    )
    with pytest.raises(ValueError, match="market lineage"):
        writer.write(invalid, **arguments)

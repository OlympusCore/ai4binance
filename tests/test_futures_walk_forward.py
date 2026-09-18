"""Replay-aware USD-M Futures walk-forward validation tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting import FuturesBacktestIntent
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    TradeDirection,
)
from ai4binance.schemas import OHLCVCandle, OOSValidationStatus
from ai4binance.validation import (
    FuturesOosEvidenceQuery,
    FuturesOosEvidenceReader,
    FuturesOosEvidenceWriter,
    FuturesOosPublicationService,
    FuturesOosRevisionSnapshot,
    FuturesWalkForwardValidator,
    MarketRegime,
    ParameterSet,
    RuntimeFuturesBacktestAdapter,
    RuntimeFuturesBacktestConfig,
    RuntimeFuturesReplayDataset,
    WalkForwardConfig,
)
from ai4binance.validation.futures_oos import (
    FUTURES_OOS_STRATEGY_ID,
    FUTURES_OOS_STRATEGY_VERSION,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    PriceOiRegime,
    Provenance,
)

START = datetime(2026, 9, 1, tzinfo=UTC)
SOURCE_ID = "BINANCE_USD_M_PUBLIC_REST"
SOURCE_URL = "https://fapi.binance.com"
SETUP = PriceOiRegime.NEW_LONG_PARTICIPATION
PARAMETERS = ParameterSet(
    "canonical",
    (
        ("stop_loss_ratio", 0.02),
        ("take_profit_ratio", 0.04),
    ),
)


def _replay(
    count: int = 18,
    *,
    prices: tuple[str, ...] | None = None,
    open_interest: tuple[str, ...] | None = None,
    funding_indices: tuple[int, ...] | None = None,
    liquidation_lows: bool = False,
) -> RuntimeFuturesReplayDataset:
    price_values = prices or tuple(str(100 + index) for index in range(count))
    oi_values = open_interest or tuple(str(1000 + index * 10) for index in range(count))
    if len(price_values) != count or len(oi_values) != count:
        raise ValueError("test replay series lengths must match")
    candles = tuple(
        OHLCVCandle(
            timestamp=START + timedelta(hours=index),
            open=Decimal(price),
            high=Decimal(price) + Decimal("5"),
            low=Decimal("20") if liquidation_lows else Decimal(price) - Decimal("1"),
            close=Decimal(price),
            volume=Decimal("1000"),
        )
        for index, price in enumerate(price_values)
    )
    funding = funding_indices if funding_indices is not None else tuple(range(count))
    return RuntimeFuturesReplayDataset(
        symbol="BTCUSDT",
        candles=candles,
        derivatives=DerivativesDataset(
            symbol="BTCUSDT",
            as_of=candles[-1].timestamp,
            series={
                DerivativesMetric.OPEN_INTEREST: tuple(
                    _point(DerivativesMetric.OPEN_INTEREST, candle.timestamp, value)
                    for candle, value in zip(candles, oi_values, strict=True)
                ),
                DerivativesMetric.FUNDING_RATE: tuple(
                    _point(
                        DerivativesMetric.FUNDING_RATE,
                        candles[index].timestamp,
                        "0.0001",
                    )
                    for index in funding
                ),
            },
            source=SOURCE_ID,
        ),
    )


def _point(
    metric: DerivativesMetric,
    timestamp: datetime,
    value: str,
) -> MetricPoint:
    return MetricPoint(
        metric=metric,
        timestamp=timestamp,
        value=Decimal(value),
        provenance=Provenance(SOURCE_ID, timestamp, SOURCE_URL),
    )


def _strategy_factory(
    parameters: ParameterSet,
) -> RuntimeFuturesBacktestAdapter:
    values = dict(parameters.values)
    return RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(
            SETUP,
            stop_loss_ratio=Decimal(str(values["stop_loss_ratio"])),
            take_profit_ratio=Decimal(str(values["take_profit_ratio"])),
        )
    )


def _regime_classifier(candle: OHLCVCandle) -> MarketRegime:
    return MarketRegime.TREND if candle.timestamp.hour % 2 == 0 else MarketRegime.RANGE


def _config() -> WalkForwardConfig:
    return WalkForwardConfig(
        train_size=6,
        test_size=6,
        step_size=6,
        min_oos_trades=2,
        max_edge_concentration=0.6,
    )


def test_futures_walk_forward_stages_exact_lineage_without_live_authority() -> None:
    dataset = _replay()
    validator = FuturesWalkForwardValidator()

    report = validator.validate(
        dataset=dataset,
        setup=SETUP,
        parameters=(PARAMETERS,),
        strategy_factory=_strategy_factory,
        regime_classifier=_regime_classifier,
        config=_config(),
    )

    expected_hash = _strategy_factory(PARAMETERS).strategy_sha256
    assert len(report.folds) == 2
    assert report.report_id.startswith("futures-wf:")
    assert report.robustness.total_oos_trades == 2
    assert report.robustness.regime_count == 2
    assert report.oos_validation_status is OOSValidationStatus.APPROVED
    assert report.promotion_status is ValidationStatus.STAGED_CANDIDATE
    assert report.blockers == ()
    for fold in report.folds:
        assert fold.train_ended_at < fold.test_started_at
        for result in (fold.training_result, fold.oos_result):
            assert result.metrics.market == "USD_M_FUTURES"
            assert result.performance_engine_report.spot_metrics is None
            assert result.performance_engine_report.futures_metrics == result.metrics
            assert result.trade_outcomes == tuple(
                trade.trade_outcome for trade in result.trades
            )
            assert all(
                trade.attribution.strategy_config_hash == expected_hash
                and trade.attribution.regime == SETUP.value
                and trade.direction is TradeDirection.LONG
                for trade in result.trades
            )
    assert validator.execution_allowed is False
    assert validator.promotion_status == "RESEARCH_ONLY"
    assert validator.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_futures_windows_preserve_derivatives_scope_and_future_isolation() -> None:
    original = _replay()
    changed_prices = tuple(
        str(100 + index) if index < 6 else str(300 + index) for index in range(18)
    )
    changed_oi = tuple(
        str(1000 + index * 10) if index < 6 else str(5000 + index * 10)
        for index in range(18)
    )
    future_changed = _replay(prices=changed_prices, open_interest=changed_oi)
    validator = FuturesWalkForwardValidator()

    original_windows = validator._build_windows(original, _config())
    changed_windows = validator._build_windows(future_changed, _config())

    assert original_windows[0].train.dataset_sha256 == (
        changed_windows[0].train.dataset_sha256
    )
    for window in original_windows:
        assert set(window.train.candles).isdisjoint(window.test.candles)
        for replay in (window.train, window.test):
            timestamps = tuple(candle.timestamp for candle in replay.candles)
            assert (
                tuple(
                    point.timestamp
                    for point in replay.derivatives.series[
                        DerivativesMetric.OPEN_INTEREST
                    ]
                )
                == timestamps
            )
            assert all(
                timestamps[0] <= point.timestamp <= timestamps[-1]
                for points in replay.derivatives.series.values()
                for point in points
            )


def test_futures_walk_forward_rejects_window_without_funding_coverage() -> None:
    dataset = _replay(funding_indices=(0,))

    with pytest.raises(ValueError, match="funding coverage"):
        FuturesWalkForwardValidator().validate(
            dataset=dataset,
            setup=SETUP,
            parameters=(PARAMETERS,),
            strategy_factory=_strategy_factory,
            regime_classifier=_regime_classifier,
            config=_config(),
        )


@dataclass(frozen=True, slots=True)
class _InvalidIdentityStrategy:
    strategy_sha256: str = "NOT_A_SHA256"

    def __call__(
        self,
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        del replay
        return None


def test_futures_walk_forward_rejects_invalid_strategy_identity() -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        FuturesWalkForwardValidator().validate(
            dataset=_replay(),
            setup=SETUP,
            parameters=(PARAMETERS,),
            strategy_factory=lambda _parameters: _InvalidIdentityStrategy(),
            regime_classifier=_regime_classifier,
            config=_config(),
        )


@dataclass(frozen=True, slots=True)
class _LiquidatingStrategy:
    strategy_sha256: str = "b" * 64

    def __call__(
        self,
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        if len(replay.candles) != 1:
            return None
        candle = replay.candles[-1]
        digest = candle.timestamp.isoformat()
        return FuturesBacktestIntent(
            signal_id=f"liquidation:{digest}",
            timestamp=candle.timestamp,
            direction=TradeDirection.LONG,
            stop_loss=candle.close * Decimal("0.60"),
            take_profit=candle.close * Decimal("1.30"),
            strategy_id=FUTURES_OOS_STRATEGY_ID,
            strategy_version=FUTURES_OOS_STRATEGY_VERSION,
            strategy_config_hash=self.strategy_sha256,
            symbol=replay.symbol,
            regime=SETUP.value,
            timeframe=replay.timeframe,
            snapshot_id=replay.dataset_sha256,
            decision_id=f"decision:{digest}",
        )


def test_futures_liquidation_vetoes_walk_forward_promotion() -> None:
    report = FuturesWalkForwardValidator().validate(
        dataset=_replay(liquidation_lows=True),
        setup=SETUP,
        parameters=(PARAMETERS,),
        strategy_factory=lambda _parameters: _LiquidatingStrategy(),
        regime_classifier=_regime_classifier,
        config=_config(),
    )

    assert any(
        trade.exit_reason is BacktestExitReason.LIQUIDATION
        for fold in report.folds
        for trade in fold.oos_result.trades
    )
    assert "FUTURES_LIQUIDATION_OCCURRED" in report.blockers
    assert report.oos_validation_status is OOSValidationStatus.INSUFFICIENT
    assert report.promotion_status is ValidationStatus.RESEARCH_ONLY


def test_futures_oos_publication_binds_full_replay_strategy_and_revision(
    tmp_path: Path,
) -> None:
    dataset = _replay()
    revision = FuturesOosRevisionSnapshot("c" * 40, repository_clean=True)
    service = FuturesOosPublicationService(
        writer=FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=lambda: revision,
    )

    result = service.publish(
        dataset=dataset,
        setup=SETUP,
        parameters=(PARAMETERS,),
        strategy_factory=_strategy_factory,
        regime_classifier=_regime_classifier,
        config=_config(),
    )

    evidence_path = Path(result.evidence.evidence_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert result.report_id.startswith("futures-wf:")
    assert result.strategy_sha256 == _strategy_factory(PARAMETERS).strategy_sha256
    assert result.dataset_sha256 == dataset.dataset_sha256
    assert result.code_revision == "c" * 40
    assert evidence["strategy_sha256"] == result.strategy_sha256
    assert evidence["dataset_sha256"] == dataset.dataset_sha256
    assert evidence["code_revision"] == "c" * 40
    assert evidence["execution_allowed"] is False
    assert evidence["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert FuturesOosEvidenceReader(tmp_path).is_validated(
        FuturesOosEvidenceQuery(
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            setup_name=SETUP.value,
            strategy_sha256=result.strategy_sha256,
            as_of=dataset.candles[-1].timestamp + timedelta(days=1),
        )
    )
    assert result.execution_allowed is False
    assert result.promotion_status == "STAGED_CANDIDATE"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_futures_oos_publication_rejects_dirty_or_changed_revision(
    tmp_path: Path,
) -> None:
    dataset = _replay()
    arguments = {
        "dataset": dataset,
        "setup": SETUP,
        "parameters": (PARAMETERS,),
        "strategy_factory": _strategy_factory,
        "regime_classifier": _regime_classifier,
        "config": _config(),
    }
    dirty = FuturesOosPublicationService(
        writer=FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=lambda: FuturesOosRevisionSnapshot(
            "c" * 40,
            repository_clean=False,
        ),
    )
    with pytest.raises(ValueError, match="FUTURES_OOS_REPOSITORY_NOT_CLEAN"):
        dirty.publish(**arguments)  # type: ignore[arg-type]

    revisions = iter(
        (
            FuturesOosRevisionSnapshot("c" * 40, repository_clean=True),
            FuturesOosRevisionSnapshot("d" * 40, repository_clean=True),
        )
    )
    changed = FuturesOosPublicationService(
        writer=FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=lambda: next(revisions),
    )
    with pytest.raises(ValueError, match="CODE_REVISION_CHANGED"):
        changed.publish(**arguments)  # type: ignore[arg-type]

    assert not tuple(tmp_path.rglob("*.json"))


def test_futures_oos_publication_does_not_persist_liquidation_result(
    tmp_path: Path,
) -> None:
    service = FuturesOosPublicationService(
        writer=FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=lambda: FuturesOosRevisionSnapshot(
            "c" * 40,
            repository_clean=True,
        ),
    )

    with pytest.raises(ValueError, match="not approved"):
        service.publish(
            dataset=_replay(liquidation_lows=True),
            setup=SETUP,
            parameters=(PARAMETERS,),
            strategy_factory=lambda _parameters: _LiquidatingStrategy(),
            regime_classifier=_regime_classifier,
            config=_config(),
        )

    assert not tuple(tmp_path.rglob("*.json"))


def test_futures_oos_publication_rejects_multiple_selected_strategy_hashes(
    tmp_path: Path,
) -> None:
    dataset = _replay()
    report = FuturesWalkForwardValidator().validate(
        dataset=dataset,
        setup=SETUP,
        parameters=(PARAMETERS,),
        strategy_factory=_strategy_factory,
        regime_classifier=_regime_classifier,
        config=_config(),
    )
    alternate = ParameterSet(
        "alternate",
        (
            ("stop_loss_ratio", 0.03),
            ("take_profit_ratio", 0.06),
        ),
    )
    mixed_report = replace(
        report,
        folds=(
            report.folds[0],
            replace(report.folds[1], selected_parameters=alternate),
        ),
    )
    validator = Mock(spec=FuturesWalkForwardValidator)
    validator.validate.return_value = mixed_report
    service = FuturesOosPublicationService(
        writer=FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=lambda: FuturesOosRevisionSnapshot(
            "c" * 40,
            repository_clean=True,
        ),
        validator=cast(FuturesWalkForwardValidator, validator),
    )

    with pytest.raises(ValueError, match="SELECTED_STRATEGY_HASH_NOT_UNIQUE"):
        service.publish(
            dataset=dataset,
            setup=SETUP,
            parameters=(PARAMETERS, alternate),
            strategy_factory=_strategy_factory,
            regime_classifier=_regime_classifier,
            config=_config(),
        )

    assert not tuple(tmp_path.rglob("*.json"))


def test_futures_oos_publication_rejects_dataset_mutation_during_validation(
    tmp_path: Path,
) -> None:
    dataset = _replay()
    calls = 0

    def mutating_factory(parameters: ParameterSet) -> RuntimeFuturesBacktestAdapter:
        nonlocal calls
        calls += 1
        if calls == 5:
            candles = dataset.candles
            object.__setattr__(
                dataset,
                "candles",
                (
                    replace(
                        candles[0],
                        close=candles[0].close + Decimal("0.5"),
                    ),
                    *candles[1:],
                ),
            )
        return _strategy_factory(parameters)

    service = FuturesOosPublicationService(
        writer=FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=lambda: FuturesOosRevisionSnapshot(
            "c" * 40,
            repository_clean=True,
        ),
    )

    with pytest.raises(ValueError, match="DATASET_MUTATED_DURING_VALIDATION"):
        service.publish(
            dataset=dataset,
            setup=SETUP,
            parameters=(PARAMETERS,),
            strategy_factory=mutating_factory,
            regime_classifier=_regime_classifier,
            config=_config(),
        )

    assert calls == 5
    assert not tuple(tmp_path.rglob("*.json"))

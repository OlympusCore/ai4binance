"""Walk-forward, OOS robustness and promotion-governance tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.backtest import BacktestIntent, SignalProvider
from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle, OOSValidationStatus
from ai4binance.storage.jsonl import JsonlAuditStore
from ai4binance.validation import (
    MarketRegime,
    ParameterSet,
    WalkForwardConfig,
    WalkForwardMode,
    WalkForwardValidator,
)
from ai4binance.validation.models import WalkForwardFold
from ai4binance.validation.storage import WalkForwardAuditWriter

NOW = datetime(2026, 1, 1, tzinfo=UTC)
GOOD = ParameterSet("good", (("target", 102.0), ("stop", 95.0)))
BAD = ParameterSet("bad", (("target", 110.0), ("stop", 99.0)))


def candles(count: int) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=Decimal("100"),
            high=Decimal("103"),
            low=Decimal("98"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for index in range(count)
    )


def strategy_factory(parameters: ParameterSet) -> SignalProvider:
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


def regime_classifier(candle: OHLCVCandle) -> MarketRegime:
    return (
        MarketRegime.TREND
        if candle.timestamp.hour % 4 in {0, 1}
        else MarketRegime.RANGE
    )


def passing_config(
    *,
    mode: WalkForwardMode = WalkForwardMode.ROLLING,
    min_folds: int = 2,
    min_oos_trades: int = 4,
    max_turnover: float = 0.6,
    max_edge_concentration: float = 0.3,
    max_parameter_switch_rate: float = 0.5,
    min_regime_count: int = 2,
) -> WalkForwardConfig:
    return WalkForwardConfig(
        train_size=4,
        test_size=2,
        step_size=2,
        mode=mode,
        min_folds=min_folds,
        min_oos_trades=min_oos_trades,
        max_turnover=max_turnover,
        max_edge_concentration=max_edge_concentration,
        max_parameter_switch_rate=max_parameter_switch_rate,
        min_regime_count=min_regime_count,
    )


def test_rolling_walk_forward_selects_on_train_and_stages_stable_oos() -> None:
    report = WalkForwardValidator().validate(
        symbol="hotusdt",
        timeframe="1h",
        candles=candles(12),
        parameters=(BAD, GOOD),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=passing_config(),
    )

    assert len(report.folds) == 4
    assert all(fold.selected_parameters == GOOD for fold in report.folds)
    assert all(fold.train_ended_at < fold.test_started_at for fold in report.folds)
    assert report.robustness.total_oos_trades == 4
    assert report.robustness.parameter_switch_rate == 0.0
    assert report.robustness.regime_count == 2
    assert report.oos_validation_status is OOSValidationStatus.APPROVED
    assert report.promotion_status is ValidationStatus.STAGED_CANDIDATE
    assert report.blockers == ()


def test_anchored_windows_expand_without_oos_overlap() -> None:
    report = WalkForwardValidator().validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles(10),
        parameters=(GOOD,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=passing_config(
            mode=WalkForwardMode.ANCHORED,
            min_oos_trades=3,
            max_edge_concentration=0.34,
        ),
    )

    assert len(report.folds) == 3
    assert {fold.train_started_at for fold in report.folds} == {NOW}
    assert [fold.train_ended_at.hour for fold in report.folds] == [3, 5, 7]
    assert [fold.test_started_at.hour for fold in report.folds] == [4, 6, 8]


def test_first_fold_parameter_selection_is_unchanged_by_future_oos_prices() -> None:
    base_candles = candles(6)
    future_changed = base_candles[:4] + tuple(
        replace(item, high=Decimal("150"), close=Decimal("120"))
        for item in base_candles[4:]
    )
    config = passing_config(
        min_oos_trades=1,
        max_edge_concentration=1.0,
    )
    validator = WalkForwardValidator()

    original = validator.validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=base_candles,
        parameters=(BAD, GOOD),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config,
    )
    changed = validator.validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=future_changed,
        parameters=(BAD, GOOD),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=config,
    )

    assert original.folds[0].selected_parameters == GOOD
    assert changed.folds[0].selected_parameters == GOOD
    assert original.folds[0].training_objective == changed.folds[0].training_objective


def test_weak_oos_remains_research_only_with_explicit_penalties() -> None:
    report = WalkForwardValidator().validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles(8),
        parameters=(BAD,),
        strategy_factory=strategy_factory,
        regime_classifier=lambda _candle: MarketRegime.UNKNOWN,
        config=passing_config(
            min_oos_trades=10,
            max_turnover=0.1,
            max_edge_concentration=0.1,
            max_parameter_switch_rate=0.0,
            min_regime_count=2,
        ),
    )

    assert report.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert report.oos_validation_status is OOSValidationStatus.INSUFFICIENT
    assert "LOW_OOS_TRADE_COUNT" in report.blockers
    assert "WEAK_OOS_FOLD_CONSISTENCY" in report.blockers
    assert "OOS_RETURN_INSUFFICIENT" in report.blockers
    assert "EXCESSIVE_OOS_TURNOVER" in report.blockers
    assert "OOS_EDGE_CONCENTRATION" in report.blockers
    assert "INSUFFICIENT_REGIME_COVERAGE" in report.blockers


def test_parameter_switch_rate_is_penalized() -> None:
    validator = WalkForwardValidator()
    folds = (
        _fake_fold(0, GOOD),
        _fake_fold(1, BAD),
        _fake_fold(2, GOOD),
    )

    assert validator._parameter_switch_rate(folds) == 1.0


def _fake_fold(index: int, parameters: ParameterSet) -> WalkForwardFold:
    base_report = WalkForwardValidator().validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles(6),
        parameters=(GOOD,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=passing_config(
            min_oos_trades=1,
            max_edge_concentration=1.0,
        ),
    )
    return replace(
        base_report.folds[0],
        fold_index=index,
        selected_parameters=parameters,
    )


def test_walk_forward_report_persists_to_redacted_jsonl(tmp_path: Path) -> None:
    report = WalkForwardValidator().validate(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=candles(12),
        parameters=(GOOD,),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=passing_config(),
    )
    output = tmp_path / "walk-forward.jsonl"
    WalkForwardAuditWriter(JsonlAuditStore(output)).append(report)

    payload = json.loads(output.read_text(encoding="utf-8"))
    stored = payload["payload"]["report"]
    assert payload["event_type"] == "WALK_FORWARD_REPORT"
    assert stored["report_id"] == report.report_id
    assert stored["promotion_status"] == "STAGED_CANDIDATE"


@pytest.mark.parametrize(
    "config",
    [
        WalkForwardConfig(train_size=4, test_size=2, step_size=2),
        WalkForwardConfig(
            train_size=4,
            test_size=2,
            step_size=2,
            mode=WalkForwardMode.ANCHORED,
        ),
    ],
)
def test_insufficient_data_rejects_validation(config: WalkForwardConfig) -> None:
    with pytest.raises(ValueError, match="insufficient candles"):
        WalkForwardValidator().validate(
            symbol="HOTUSDT",
            timeframe="1h",
            candles=candles(5),
            parameters=(GOOD,),
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=config,
        )


def test_validation_contracts_reject_unsafe_inputs() -> None:
    with pytest.raises(ValueError, match="step must cover test"):
        WalkForwardConfig(train_size=4, test_size=2, step_size=1)
    with pytest.raises(ValueError, match="ratios"):
        passing_config(max_turnover=1.1)
    with pytest.raises(ValueError, match="at least two"):
        passing_config(min_folds=1)
    with pytest.raises(ValueError, match="parameter name"):
        ParameterSet("", (("x", 1.0),))
    with pytest.raises(ValueError, match="unique"):
        ParameterSet("duplicate", (("x", 1.0), ("x", 2.0)))
    with pytest.raises(ValueError, match="parameter candidates"):
        WalkForwardValidator().validate(
            symbol="HOTUSDT",
            timeframe="1h",
            candles=candles(6),
            parameters=(),
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=passing_config(),
        )

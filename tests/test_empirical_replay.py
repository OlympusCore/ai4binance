"""Causal and negative-evidence regression tests for empirical calibration."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.data import ParquetOHLCVArchive
from ai4binance.research.backtesting import BacktestEngine, BacktestIntent
from ai4binance.research.backtesting.models import TradeDirection
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.empirical_replay import (
    EmpiricalReplayWindow,
    run_empirical_spot_study,
)
from ai4binance.validation.replay_calibration import (
    ReplayForecast,
    replay_calibration_cohort,
)

START = datetime(2025, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _candles(count: int = 5) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=START + i * HOUR,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for i in range(count)
    )


@pytest.mark.parametrize("ambiguous", [False, True])
def test_real_fills_join_frozen_forecasts_and_censor_unknown_order(
    ambiguous: bool,
) -> None:
    candles = list(_candles())
    candles[3] = replace(
        candles[3],
        high=Decimal("111"),
        low=Decimal("89") if ambiguous else Decimal("99"),
    )
    intent = BacktestIntent(
        signal_id="frozen",
        timestamp=START + HOUR,
        stop_loss=Decimal("90"),
        take_profit=Decimal("110"),
        atr=Decimal("1"),
    )
    result = BacktestEngine().run(
        symbol="BTCUSDT",
        timeframe="1h",
        candles=tuple(candles),
        signal_provider=lambda history: intent if len(history) == 2 else None,
    )
    forecast = ReplayForecast(
        "frozen",
        "fixed-model",
        START - HOUR,
        START + 2 * HOUR,
        START + 5 * HOUR,
        Decimal("90"),
        Decimal("110"),
        Decimal("100"),
        TradeDirection.LONG,
        "TREND",
    )
    cohort = replay_calibration_cohort(
        result, (forecast,), tuple(candles), interval=HOUR, fold_id="HOLDOUT"
    )
    assert cohort.completed_trade_count == 1
    if ambiguous:
        assert cohort.observations == ()
        assert cohort.censor_counts == (("SIMULTANEOUS_BARRIER_TOUCH", 1),)
        assert result.trades[0].net_pnl_usdt < 0
    else:
        assert cohort.observations[0].target_first
        assert cohort.observations[0].predicted_at < cohort.observations[0].resolved_at
    with pytest.raises(ValueError, match="matching frozen"):
        replay_calibration_cohort(
            result, (), tuple(candles), interval=HOUR, fold_id="H"
        )
    with pytest.raises(ValueError, match="after the entry"):
        replay_calibration_cohort(
            result,
            (replace(forecast, predicted_at=START + 3 * HOUR),),
            tuple(candles),
            interval=HOUR,
            fold_id="H",
        )


def test_empirical_replay_persists_negative_evidence_without_claiming_profit(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "archive")
    archive.update(
        "BTCUSDT",
        "1h",
        _candles(500),
        source="LOCAL_TEST_FIXTURE",
        generated_at=START + 501 * HOUR,
    )
    window = EmpiricalReplayWindow(
        START, START + 200 * HOUR, START + 225 * HOUR, START + 500 * HOUR
    )
    result = run_empirical_spot_study(
        archive=archive,
        symbol="BTCUSDT",
        timeframe="1h",
        playbook="trend_continuation",
        window=window,
        output_root=tmp_path / "evidence",
        hypothesis_count=20,
    )
    assert result["replay_equal"] is True
    assert result["execution_allowed"] is False
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "NET_RETURN_NOT_POSITIVE" in blockers
    assert "COMPONENT_STUDY_NOT_SYSTEM_ACCEPTANCE" in blockers
    assert (tmp_path / "evidence" / str(result["run_id"]) / "replay.json").exists()
    with pytest.raises(ValueError, match="ALREADY_COMPLETED"):
        run_empirical_spot_study(
            archive=archive,
            symbol="BTCUSDT",
            timeframe="1h",
            playbook="trend_continuation",
            window=window,
            output_root=tmp_path / "evidence",
            hypothesis_count=20,
        )


def test_forecast_rejects_inverted_geometry_and_naive_time() -> None:
    with pytest.raises(ValueError, match="geometry"):
        ReplayForecast(
            "s",
            "m",
            START,
            START + HOUR,
            START + 2 * HOUR,
            Decimal("110"),
            Decimal("90"),
            Decimal("100"),
            TradeDirection.LONG,
            "TREND",
        )

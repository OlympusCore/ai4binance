"""Reproducible archived Spot playbook studies with an untouched final window.

This component study is not a substitute for the full multi-market runtime.
The geometry score is a declared uncalibrated baseline, not model confidence.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from functools import partial
from itertools import pairwise
from pathlib import Path
from time import perf_counter
from typing import cast

from ai4binance.application.validation_pipeline import HistoricalPlaybookAdapter
from ai4binance.data import ParquetOHLCVArchive
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.indicators import atr
from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting import BacktestEngine, BacktestIntent
from ai4binance.research.backtesting.models import BacktestResult, TradeDirection
from ai4binance.research.virtual_market import load_acceptance_policy
from ai4binance.research_governance import ResearchRunCard
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage import write_json_object_verified
from ai4binance.strategies.registry import build_playbook_registry
from ai4binance.strategies.rules import historical_playbook_decision
from ai4binance.validation.models import ParameterSet
from ai4binance.validation.overfit import calibrated_holdout, fit_oos_calibration
from ai4binance.validation.regimes import classify_validation_regime
from ai4binance.validation.replay_calibration import (
    ReplayCalibrationCohort,
    ReplayForecast,
    replay_calibration_cohort,
)
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    assess_statistical_evidence,
)
from ai4binance.validation_pipeline_runtime import (
    SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO,
    HistoricalValidationRuntime,
    runtime_spot_backtest_engine,
)


@dataclass(frozen=True, slots=True)
class EmpiricalReplayWindow:
    start: datetime
    calibration_end: datetime
    holdout_start: datetime
    end: datetime

    def __post_init__(self) -> None:
        dates = (self.start, self.calibration_end, self.holdout_start, self.end)
        if any(d.utcoffset() is None for d in dates) or not all(
            a < b for a, b in pairwise(dates)
        ):
            raise ValueError("empirical replay requires chronological aware windows")


def _save(path: Path, payload: object) -> None:
    write_json_object_verified(
        path,
        cast(dict[str, object], to_primitive(payload)),
        blocker="EMPIRICAL_REPLAY_WRITE_FAILED",
        durable=True,
    )


def _replay(
    candles: tuple[OHLCVCandle, ...],
    *,
    symbol: str,
    timeframe: str,
    playbook: str,
    model_id: str,
    trained_through: datetime,
    start: datetime,
    end: datetime,
    cost_multiplier: Decimal,
) -> tuple[BacktestResult, tuple[ReplayForecast, ...]]:
    interval = timeframe_duration(timeframe)
    registry = build_playbook_registry()
    profile = HistoricalValidationRuntime().risk_profile_registry.resolve(playbook)
    parameters = ParameterSet(
        "FROZEN_REGISTRY_DEFAULTS",
        (
            ("stop_atr_multiple", float(profile.stop_atr_multiple)),
            ("target_atr_multiple", float(profile.target_atr_multiple)),
        ),
    )
    adapter = HistoricalPlaybookAdapter(
        playbook,
        parameters,
        lambda name, history: historical_playbook_decision(
            name, history, registry=registry
        ),
        atr,
        BacktestIntent,
        symbol=symbol,
        timeframe=timeframe,
        regime_classifier=classify_validation_regime,
    )
    forecasts: list[ReplayForecast] = []

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        intent = cast(BacktestIntent | None, adapter(history))
        available = history[-1].timestamp + interval
        if intent is None or available <= start or available >= end:
            return None
        horizon = (
            min(end, available + interval * intent.maximum_holding_bars)
            if (intent.maximum_holding_bars is not None)
            else end
        )
        forecasts.append(
            ReplayForecast(
                intent.signal_id,
                model_id,
                trained_through,
                available,
                horizon,
                intent.stop_loss,
                intent.take_profit,
                history[-1].close,
                TradeDirection.LONG,
                intent.regime,
            )
        )
        return intent

    base = BacktestEngine()
    base = BacktestEngine(
        replace(
            base.config,
            fee_ratio=base.config.fee_ratio * cost_multiplier,
            slippage_ratio=base.config.slippage_ratio * cost_multiplier,
        )
    )
    engine = runtime_spot_backtest_engine(
        candles,
        base_engine=base,
        notional_to_equity_ratio=SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO,
    )
    return engine.run(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        signal_provider=provider,
    ), tuple(forecasts)


def run_empirical_spot_study(
    *,
    archive: ParquetOHLCVArchive,
    symbol: str,
    timeframe: str,
    playbook: str,
    window: EmpiricalReplayWindow,
    output_root: Path,
    hypothesis_count: int,
) -> dict[str, object]:
    """Freeze before replay, persist actual outcomes, fit only resolved past labels.

    All fees, losses, rejected opportunities and censored outcomes are retained.
    Failed studies are never deleted or tuned against the final window.
    """
    started = perf_counter()
    interval = timeframe_duration(timeframe)
    manifest = archive.manifest(symbol, timeframe)
    all_candles = archive.read(symbol, timeframe)
    candles = tuple(c for c in all_candles if window.start <= c.timestamp < window.end)
    if (
        not candles
        or candles[0].timestamp != window.start
        or (candles[-1].timestamp + interval != window.end)
        or any(b.timestamp - a.timestamp != interval for a, b in pairwise(candles))
    ):
        raise ValueError("EMPIRICAL_REPLAY_WINDOW_MISSING_OR_GAPPED")
    implementation = HistoricalValidationRuntime.implementation_sha256()
    specification = {
        "market": "SPOT",
        "symbol": symbol,
        "timeframe": timeframe,
        "playbook": playbook,
        "window": to_primitive(window),
        "hypothesis_count": hypothesis_count,
        "source_manifest": to_primitive(manifest),
        "implementation_sha256": implementation,
        "score_method": "UNCALIBRATED_GEOMETRY_BASELINE",
        "selection": "FIXED_REGISTRY_DEFAULTS_NO_HOLDOUT_TUNING",
    }
    run_id = ResearchRunCard.hash_json(specification)
    directory = output_root / run_id
    if (directory / "result.json").exists():
        raise ValueError("EMPIRICAL_REPLAY_ALREADY_COMPLETED_USE_EXISTING_EVIDENCE")
    _save(directory / "specification.json", specification)
    model_id = f"{playbook}:{timeframe}:{implementation}"
    run = partial(
        _replay,
        symbol=symbol,
        timeframe=timeframe,
        playbook=playbook,
        model_id=model_id,
        trained_through=window.start - interval,
    )
    calibration_candles = tuple(
        c for c in candles if c.timestamp < window.calibration_end
    )
    # Warm-up is strictly before the holdout and cannot create positions.
    holdout_candles = tuple(
        c for c in candles if c.timestamp >= window.holdout_start - interval * 200
    )
    calibration, calibration_forecasts = run(
        calibration_candles,
        start=window.start,
        end=window.calibration_end,
        cost_multiplier=Decimal("1"),
    )
    holdout, holdout_forecasts = run(
        holdout_candles,
        start=window.holdout_start,
        end=window.end,
        cost_multiplier=Decimal("1"),
    )
    repeat, repeat_forecasts = run(
        holdout_candles,
        start=window.holdout_start,
        end=window.end,
        cost_multiplier=Decimal("1"),
    )
    reproducible = holdout == repeat and holdout_forecasts == repeat_forecasts
    calibration_cohort = replay_calibration_cohort(
        calibration,
        calibration_forecasts,
        calibration_candles,
        interval=interval,
        fold_id="CALIBRATION",
    )
    holdout_cohort = replay_calibration_cohort(
        holdout,
        holdout_forecasts,
        holdout_candles,
        interval=interval,
        fold_id="FINAL_HOLDOUT",
    )
    # Freeze raw forecasts and full economic ledgers before fitting anything.
    _save(
        directory / "replay.json",
        {
            "calibration": calibration,
            "holdout": holdout,
            "calibration_forecasts": calibration_forecasts,
            "holdout_forecasts": holdout_forecasts,
            "calibration_cohort": calibration_cohort,
            "holdout_cohort": holdout_cohort,
        },
    )
    diagnostics = _calibrate(
        calibration_cohort,
        holdout_cohort,
        window,
        HistoricalValidationRuntime().dataset_sha256(candles),
    )
    stress = {}
    for multiplier in (Decimal("1.5"), Decimal("2")):
        stressed, _ = run(
            holdout_candles,
            start=window.holdout_start,
            end=window.end,
            cost_multiplier=multiplier,
        )
        stress[str(multiplier)] = to_primitive(stressed.metrics)
        _save(directory / f"cost-{multiplier}.json", {"result": stressed})
    blocks: dict[int, float] = {}
    for trade in holdout.trades:
        week = int(
            (trade.exit_timestamp - window.holdout_start).total_seconds() // 604800
        )
        blocks[week] = blocks.get(week, 0.0) + float(trade.net_pnl_usdt)
    weeks = max(
        1, int((window.end - window.holdout_start).total_seconds() // 604800) + 1
    )
    statistics = assess_statistical_evidence(
        tuple(blocks.get(i, 0.0) for i in range(weeks)),
        hypothesis_count=hypothesis_count,
        min_effective_sample_size=2,
        minimum_return=0,
        confidence_level=0.95,
        correction=MultipleTestingCorrection.BONFERRONI,
        confirmatory=True,
    )
    policy = load_acceptance_policy()
    blockers = list(statistics.blockers)
    if not reproducible:
        blockers.append("DECISION_REPRODUCIBILITY_FAILED")
    if holdout.metrics.net_return <= 0:
        blockers.append("NET_RETURN_NOT_POSITIVE")
    if holdout.metrics.trade_count < policy.minimum_completed_trades:
        blockers.append("TRADE_SAMPLE_INSUFFICIENT")
    # This is a component test, not the system's multi-market acceptance gate.
    blockers.append("COMPONENT_STUDY_NOT_SYSTEM_ACCEPTANCE")
    payload: dict[str, object] = {
        "run_id": run_id,
        "specification": specification,
        "calibration": diagnostics,
        "holdout_metrics": to_primitive(holdout.metrics),
        "cost_stress": stress,
        "weekly_statistics": to_primitive(statistics),
        "replay_equal": reproducible,
        "elapsed_seconds": perf_counter() - started,
        "blockers": blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    _save(directory / "result.json", payload)
    return payload


def _calibrate(
    calibration: ReplayCalibrationCohort,
    holdout: ReplayCalibrationCohort,
    window: EmpiricalReplayWindow,
    dataset_sha256: str,
) -> dict[str, object]:
    minimum = load_acceptance_policy().minimum_completed_trades
    try:
        model = fit_oos_calibration(
            calibration.observations,
            dataset_sha256=dataset_sha256,
            fitted_through=window.calibration_end,
            minimum_observations=minimum,
        )
        _, diagnostics = calibrated_holdout(
            model,
            holdout.observations,
            embargo=window.holdout_start - window.calibration_end,
            minimum_observations=minimum,
        )
    except ValueError as error:
        return {
            "status": "NOT_CALIBRATED",
            "reason": str(error),
            "calibration_rows": len(calibration.observations),
            "holdout_rows": len(holdout.observations),
        }
    return {
        "status": "FITTED_RESEARCH_ONLY",
        "model": to_primitive(model),
        "holdout_diagnostics": to_primitive(diagnostics),
    }

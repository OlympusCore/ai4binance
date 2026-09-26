"""Frozen calibration and existing market-acceptance gates on bound OOS evidence."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from ai4binance.research.backtesting.models import BacktestResult
from ai4binance.research.virtual_market import (
    AcceptancePolicy,
    MarketAcceptanceResult,
    MarketPerformanceEvidence,
    VirtualMarket,
    evaluate_market_acceptance,
)
from ai4binance.validation.overfit import (
    FrozenIsotonicCalibration,
    OosProbabilityObservation,
    ProbabilityDiagnostics,
    assess_oos_probabilities,
    calibrated_holdout,
    fit_oos_calibration,
)
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    StatisticalEvidenceAssessment,
    assess_statistical_evidence,
)


@dataclass(frozen=True, slots=True)
class CalibratedMarketAssessment:
    """Separate probability, economic acceptance, and uncertainty evidence."""

    calibration: FrozenIsotonicCalibration
    raw_holdout: ProbabilityDiagnostics
    calibrated_holdout: ProbabilityDiagnostics
    market_acceptance: MarketAcceptanceResult
    block_statistics: StatisticalEvidenceAssessment
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("calibration evidence cannot authorize execution")


def evaluate_calibrated_market_acceptance(
    *,
    calibration_rows: tuple[OosProbabilityObservation, ...],
    holdout_rows: tuple[OosProbabilityObservation, ...],
    dataset_sha256: str,
    replay_state_hash: str,
    fitted_through: datetime,
    embargo: timedelta,
    performance: MarketPerformanceEvidence,
    policy: AcceptancePolicy,
    hypothesis_count: int,
    block_days: int = 7,
    futures_path_result: BacktestResult | None = None,
) -> CalibratedMarketAssessment:
    """Evaluate an untouched cohort; a rejected market stays rejected.

    Return uncertainty uses non-overlapping calendar blocks to avoid counting
    simultaneous observations as independent trades. This diagnostic does not
    replace the governed walk-forward, cost-stress, or promotion requirements.
    """
    if (
        not holdout_rows
        or replay_state_hash != performance.replay_state_hash
        or len(replay_state_hash) != 64
        or any(c not in "0123456789abcdef" for c in replay_state_hash)
        or block_days < 1
        or {o.observation_id for o in calibration_rows}
        & {o.observation_id for o in holdout_rows}
    ):
        raise ValueError(
            "calibration acceptance requires distinct cohorts and exact replay binding"
        )
    if any(
        o.predicted_at < performance.configured_start_at
        or o.horizon_end > performance.last_replayed_at
        for o in holdout_rows
    ):
        raise ValueError("holdout horizons exceed market performance coverage")
    model = fit_oos_calibration(
        calibration_rows,
        dataset_sha256=dataset_sha256,
        fitted_through=fitted_through,
        minimum_observations=policy.minimum_completed_trades,
    )
    raw = assess_oos_probabilities(
        holdout_rows, minimum_observations=policy.minimum_completed_trades
    )
    transformed, calibrated = calibrated_holdout(
        model,
        holdout_rows,
        embargo=embargo,
        minimum_observations=policy.minimum_completed_trades,
    )
    groups: dict[int, list[float]] = {}
    origin = performance.configured_start_at
    for row in transformed:
        index = int((row.predicted_at - origin).total_seconds() // (block_days * 86400))
        groups.setdefault(index, []).append(row.net_r)
    statistics = assess_statistical_evidence(
        tuple(mean(values) for _, values in sorted(groups.items())),
        hypothesis_count=hypothesis_count,
        min_effective_sample_size=2,
        minimum_return=0,
        confidence_level=0.95,
        correction=MultipleTestingCorrection.BONFERRONI,
        confirmatory=True,
    )
    acceptance = evaluate_market_acceptance(performance, policy)
    blockers = [*calibrated.blockers, *statistics.blockers, *acceptance.blockers]
    if performance.market is VirtualMarket.USD_M_FUTURES and not (
        futures_path_result is not None
        and getattr(futures_path_result.assumptions, "require_mark_price_path", False)
        is True
        and any(
            event.get("event_type") == "FUTURES_LIQUIDATION_MODEL"
            and event.get("model") == "ISOLATED_MARK_OHLC_TIERED_V1"
            and event.get("dataset_sha256") == dataset_sha256
            for event in futures_path_result.audit_events
        )
    ):
        blockers.append("FUTURES_MARK_PRICE_PATH_UNVERIFIED")
    if calibrated.brier_score > raw.brier_score:
        blockers.append("CALIBRATION_DEGRADES_HELD_OUT_BRIER")
    return CalibratedMarketAssessment(
        model,
        raw,
        calibrated,
        acceptance,
        statistics,
        tuple(dict.fromkeys(blockers)),
    )

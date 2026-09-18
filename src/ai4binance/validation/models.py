"""Immutable walk-forward, OOS and promotion-governance models."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting.models import BacktestResult
from ai4binance.schemas import OOSValidationStatus
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    StatisticalEvidenceAssessment,
)


class WalkForwardMode(StrEnum):
    """Supported chronological training-window modes."""

    ROLLING = "ROLLING"
    ANCHORED = "ANCHORED"


class MarketRegime(StrEnum):
    """Coarse OOS regimes used for robustness reporting."""

    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ParameterSet:
    """Named, deterministic and hashable parameter candidate."""

    name: str
    values: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.values:
            raise ValueError("parameter name and values are required")
        keys = [key for key, _value in self.values]
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("parameter keys must be non-empty and unique")
        if any(not isfinite(value) for _key, value in self.values):
            raise ValueError("parameter values must be finite")
        object.__setattr__(self, "values", tuple(sorted(self.values)))


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    """Fail-closed validation windows and promotion thresholds."""

    train_size: int
    test_size: int
    step_size: int
    mode: WalkForwardMode = WalkForwardMode.ROLLING
    min_folds: int = 2
    min_oos_trades: int = 5
    min_profitable_fold_ratio: float = 0.6
    min_oos_net_return: float = 0.0
    max_oos_drawdown: float = 0.25
    max_turnover: float = 0.25
    max_edge_concentration: float = 0.5
    max_parameter_switch_rate: float = 0.5
    min_regime_count: int = 2
    min_effective_sample_size: int = 2
    confidence_level: float = 0.95
    multiple_testing_correction: MultipleTestingCorrection = (
        MultipleTestingCorrection.BONFERRONI
    )
    confirmatory: bool = True
    purge_size: int = 0
    embargo_size: int = 0

    def __post_init__(self) -> None:
        if min(self.train_size, self.test_size) < 2 or self.step_size < self.test_size:
            raise ValueError(
                "train/test sizes must be at least two and step must cover test"
            )
        if self.min_folds < 2 or self.min_regime_count < 2:
            raise ValueError("promotion requires at least two folds and two regimes")
        if self.min_oos_trades < 1 or self.min_effective_sample_size < 2:
            raise ValueError("OOS trade count and effective sample size are invalid")
        if self.purge_size < 0 or self.embargo_size < 0:
            raise ValueError("purge and embargo sizes cannot be negative")
        ratios = (
            self.min_profitable_fold_ratio,
            self.max_oos_drawdown,
            self.max_turnover,
            self.max_edge_concentration,
            self.max_parameter_switch_rate,
        )
        if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError(
                "validation ratios must be finite and between zero and one"
            )
        if not isfinite(self.min_oos_net_return):
            raise ValueError("minimum OOS return must be finite")
        if self.confidence_level not in {0.90, 0.95, 0.99}:
            raise ValueError("confidence level must be 0.90, 0.95 or 0.99")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    """One train-only selection followed by untouched OOS evaluation."""

    fold_index: int
    train_started_at: datetime
    train_ended_at: datetime
    test_started_at: datetime
    test_ended_at: datetime
    selected_parameters: ParameterSet
    training_objective: float
    training_result: BacktestResult
    oos_result: BacktestResult


@dataclass(frozen=True, slots=True)
class RegimePerformance:
    """OOS performance attributed by entry-time market regime."""

    regime: MarketRegime
    candle_count: int
    trade_count: int
    net_pnl_usdt: float
    win_rate: float


@dataclass(frozen=True, slots=True)
class RobustnessAssessment:
    """Transparent robustness penalties used by promotion governance."""

    total_oos_trades: int
    profitable_fold_ratio: float
    oos_net_return: float
    worst_fold_drawdown: float
    turnover: float
    edge_concentration: float
    parameter_switch_rate: float
    regime_count: int
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    """Auditable validation report that can never directly approve live use."""

    report_id: str
    symbol: str
    timeframe: str
    created_at: datetime
    config: WalkForwardConfig
    folds: tuple[WalkForwardFold, ...]
    regime_performance: tuple[RegimePerformance, ...]
    robustness: RobustnessAssessment
    statistical_evidence: StatisticalEvidenceAssessment
    oos_validation_status: OOSValidationStatus
    promotion_status: ValidationStatus
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        identity_missing = (
            not self.report_id.strip()
            or not self.symbol.strip()
            or not self.timeframe.strip()
        )
        if identity_missing:
            raise ValueError("report identity is required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("report timestamp must be timezone-aware")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError("walk-forward may only stage research candidates")
        if self.promotion_status is ValidationStatus.STAGED_CANDIDATE and self.blockers:
            raise ValueError("staged candidate cannot contain validation blockers")
        approved = self.oos_validation_status is OOSValidationStatus.APPROVED
        staged = self.promotion_status is ValidationStatus.STAGED_CANDIDATE
        if approved != staged:
            raise ValueError("OOS approval and staged promotion must be consistent")

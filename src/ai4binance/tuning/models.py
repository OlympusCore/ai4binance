"""Immutable parameter governance, tuning and sensitivity contracts."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, prod

from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.models import (
    ParameterSet,
    RegimePerformance,
    WalkForwardConfig,
    WalkForwardReport,
)

ALLOWED_PARAMETER_NAMES = frozenset(
    {
        "ema_fast",
        "ema_slow",
        "rsi_period",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "supertrend_atr_period",
        "supertrend_multiplier",
        "atr_stop_multiplier",
        "take_profit_multiplier",
        "trailing_multiplier",
        "volume_window",
        "support_resistance_lookback",
        "minimum_score",
        "minimum_risk_reward",
    }
)
PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "ema_fast": (2.0, 200.0),
    "ema_slow": (3.0, 500.0),
    "rsi_period": (2.0, 100.0),
    "macd_fast": (2.0, 100.0),
    "macd_slow": (3.0, 200.0),
    "macd_signal": (2.0, 100.0),
    "supertrend_atr_period": (2.0, 200.0),
    "supertrend_multiplier": (0.1, 20.0),
    "atr_stop_multiplier": (0.1, 20.0),
    "take_profit_multiplier": (0.1, 20.0),
    "trailing_multiplier": (0.1, 20.0),
    "volume_window": (2.0, 500.0),
    "support_resistance_lookback": (2.0, 1000.0),
    "minimum_score": (0.0, 100.0),
    "minimum_risk_reward": (0.1, 20.0),
}
INTEGER_PARAMETERS = frozenset(
    {
        "ema_fast",
        "ema_slow",
        "rsi_period",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "supertrend_atr_period",
        "volume_window",
        "support_resistance_lookback",
    }
)


@dataclass(frozen=True, slots=True)
class ParameterDomain:
    """Explicit finite values for one approved tunable parameter."""

    name: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.name not in ALLOWED_PARAMETER_NAMES:
            raise ValueError(f"parameter is not approved for tuning: {self.name}")
        if not self.values or any(not isfinite(value) for value in self.values):
            raise ValueError("parameter domain values must be non-empty and finite")
        if len(set(self.values)) != len(self.values):
            raise ValueError("parameter domain values must be unique")
        lower, upper = PARAMETER_BOUNDS[self.name]
        if any(not lower <= value <= upper for value in self.values):
            raise ValueError("parameter domain value is outside approved bounds")
        if self.name in INTEGER_PARAMETERS and any(
            not value.is_integer() for value in self.values
        ):
            raise ValueError("period and lookback parameters must be integers")
        object.__setattr__(self, "values", tuple(sorted(self.values)))


@dataclass(frozen=True, slots=True)
class SearchSpace:
    """Bounded deterministic Cartesian search space."""

    domains: tuple[ParameterDomain, ...]
    max_candidates: int = 256

    def __post_init__(self) -> None:
        names = [domain.name for domain in self.domains]
        if not self.domains or len(names) != len(set(names)):
            raise ValueError("search domains must be non-empty and unique")
        if not 1 <= self.max_candidates <= 4096:
            raise ValueError("max_candidates must be between 1 and 4096")
        if self.candidate_count > self.max_candidates:
            raise ValueError("search space exceeds max_candidates")

    @property
    def candidate_count(self) -> int:
        return prod(len(domain.values) for domain in self.domains)


@dataclass(frozen=True, slots=True)
class TuningConfig:
    """Validation config plus sensitivity thresholds."""

    walk_forward: WalkForwardConfig
    min_neighbor_count: int = 2
    min_neighbor_pass_ratio: float = 0.5
    min_neighbor_return_ratio: float = 0.5

    def __post_init__(self) -> None:
        if self.min_neighbor_count < 1:
            raise ValueError("minimum neighbor count must be positive")
        ratios = (self.min_neighbor_pass_ratio, self.min_neighbor_return_ratio)
        if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("sensitivity ratios must be between zero and one")


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    """One parameter candidate and its complete OOS evidence."""

    parameters: ParameterSet
    objective: float
    walk_forward_report: WalkForwardReport


@dataclass(frozen=True, slots=True)
class SensitivityAssessment:
    """Local-neighborhood stability around the selected candidate."""

    neighbor_count: int
    passing_neighbor_count: int
    pass_ratio: float
    minimum_return_ratio: float
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TuningReport:
    """Auditable tuning result with no autonomous deployment authority."""

    report_id: str
    symbol: str
    timeframe: str
    created_at: datetime
    search_space: SearchSpace
    config: TuningConfig
    evaluations: tuple[CandidateEvaluation, ...]
    selected_parameters: ParameterSet
    sensitivity: SensitivityAssessment
    promotion_status: ValidationStatus
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.report_id.strip() or not self.evaluations:
            raise ValueError("tuning report identity and evaluations are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("tuning timestamp must be timezone-aware")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError("tuning may only produce research or staged candidates")
        staged = self.promotion_status is ValidationStatus.STAGED_CANDIDATE
        if staged == bool(self.blockers):
            raise ValueError("tuning promotion and blockers are inconsistent")


@dataclass(frozen=True, slots=True)
class TournamentContext:
    """One governed symbol/timeframe history used in tournament research."""

    symbol: str
    timeframe: str
    candles: tuple[OHLCVCandle, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("tournament context identity is required")
        if len(self.candles) < 2:
            raise ValueError("tournament context requires at least two candles")


@dataclass(frozen=True, slots=True)
class StrategyProfileCandidate:
    """One approved parameter profile entering tournament research."""

    profile_id: str
    parameters: ParameterSet

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("strategy profile candidate requires a profile_id")


@dataclass(frozen=True, slots=True)
class TournamentConfig:
    """Research-only candidate-comparison thresholds."""

    walk_forward: WalkForwardConfig
    min_symbol_count: int = 2
    min_timeframe_count: int = 2
    min_trade_count: int = 10
    max_symbol_concentration: float = 0.8
    max_timeframe_concentration: float = 0.8
    min_stress_return_ratio: float = 0.5

    def __post_init__(self) -> None:
        if self.min_symbol_count < 1 or self.min_timeframe_count < 1:
            raise ValueError("tournament diversity counts must be positive")
        if self.min_trade_count < 1:
            raise ValueError("tournament trade count must be positive")
        ratios = (
            self.max_symbol_concentration,
            self.max_timeframe_concentration,
            self.min_stress_return_ratio,
        )
        if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("tournament ratios must be between zero and one")


@dataclass(frozen=True, slots=True)
class TournamentContextEvaluation:
    """Walk-forward and cost-stress evidence for one context."""

    context: TournamentContext
    walk_forward_report: WalkForwardReport
    robustness_blockers: tuple[str, ...]
    stress_net_returns: tuple[tuple[str, float], ...]
    bootstrap_probability_of_loss: float
    bootstrap_p95_max_drawdown: float


@dataclass(frozen=True, slots=True)
class TournamentEntry:
    """Research-only parameter-profile comparison output."""

    profile_id: str
    parameters: ParameterSet
    evaluations: tuple[TournamentContextEvaluation, ...]
    net_return_after_costs: float
    profit_factor: float | None
    expectancy: float
    max_drawdown: float
    sharpe: float | None
    sortino: float | None
    trade_count: int
    win_rate: float
    average_r: float
    tail_loss: float
    parameter_stability: float
    regime_breakdown: tuple[RegimePerformance, ...]
    blockers: tuple[str, ...]
    status: str = "RESEARCH_CANDIDATE"
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("tournament entry requires profile identity")
        if self.status != "RESEARCH_CANDIDATE":
            raise ValueError("tournament output may only be RESEARCH_CANDIDATE")
        if self.promotion_status is not ValidationStatus.RESEARCH_ONLY:
            raise ValueError("tournament may not auto-promote parameter profiles")
        if self.execution_allowed:
            raise ValueError("tournament evidence cannot allow execution")


@dataclass(frozen=True, slots=True)
class StrategyParameterTournamentReport:
    """Bounded tournament output ranked for research only."""

    report_id: str
    created_at: datetime
    config: TournamentConfig
    entries: tuple[TournamentEntry, ...]
    status: str = "RESEARCH_CANDIDATE"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.report_id.strip() or not self.entries:
            raise ValueError("tournament report identity and entries are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("tournament timestamp must be timezone-aware")
        if self.status != "RESEARCH_CANDIDATE":
            raise ValueError("tournament report may only remain RESEARCH_CANDIDATE")
        if self.execution_allowed:
            raise ValueError("tournament report cannot authorize execution")

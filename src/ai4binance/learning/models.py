"""Immutable controlled-learning and experiment recommendation models."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from ai4binance.domain import ValidationStatus

_NOT_APPLIED = "NOT_APPLIED"


@dataclass(frozen=True, slots=True)
class LessonCandidate:
    code: str
    evidence_count: int
    rationale: str


@dataclass(frozen=True, slots=True)
class ExperimentRecommendation:
    rank: int
    experiment_id: str
    objective: str
    required_validation: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfitabilityMetric:
    metric_id: str
    value: float | None
    supported: bool = True

    def __post_init__(self) -> None:
        if not self.metric_id.strip():
            raise ValueError("profitability metric identity is required")
        if self.supported and self.value is None:
            raise ValueError("supported profitability metric requires a value")
        if self.value is not None and not isfinite(self.value):
            raise ValueError("profitability metric value must be finite")


@dataclass(frozen=True, slots=True)
class StrategyRegimeAttribution:
    strategy_id: str
    strategy_version: str
    regime: str
    trade_count: int
    profit_factor: float | None
    net_expectancy_after_costs: float
    average_r: float
    average_mfe_r: float
    average_mae_r: float
    win_rate: float
    payoff_ratio: float | None

    def __post_init__(self) -> None:
        if not self.strategy_id.strip() or not self.strategy_version.strip():
            raise ValueError("strategy-regime attribution identity is required")
        if not self.regime.strip():
            raise ValueError("strategy-regime attribution regime is required")
        if self.trade_count < 1:
            raise ValueError("strategy-regime attribution requires trades")
        numeric = (
            self.net_expectancy_after_costs,
            self.average_r,
            self.average_mfe_r,
            self.average_mae_r,
            self.win_rate,
        )
        if any(not isfinite(value) for value in numeric):
            raise ValueError("strategy-regime attribution values must be finite")
        if self.profit_factor is not None and not isfinite(self.profit_factor):
            raise ValueError("strategy-regime profit factor must be finite")
        if self.payoff_ratio is not None and not isfinite(self.payoff_ratio):
            raise ValueError("strategy-regime payoff ratio must be finite")


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    analysis_id: str
    classification: str
    strategy_id: str
    regime: str
    sample_size: int
    average_mfe_r: float
    average_mae_r: float
    rationale: str
    improvement_candidate_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("analysis_id", self.analysis_id),
            ("classification", self.classification),
            ("strategy_id", self.strategy_id),
            ("regime", self.regime),
            ("rationale", self.rationale),
            ("improvement_candidate_id", self.improvement_candidate_id),
        ):
            if not value.strip():
                raise ValueError(f"failure analysis {name} is required")
        if self.sample_size < 1:
            raise ValueError("failure analysis sample size must be positive")
        if not isfinite(self.average_mfe_r) or not isfinite(self.average_mae_r):
            raise ValueError("failure analysis excursion values must be finite")


@dataclass(frozen=True, slots=True)
class ProfitabilityExperiment:
    experiment_id: str
    objective: str
    required_validation: tuple[str, ...]
    human_review_required: bool = True
    target_status: str = "PAPER_CANDIDATE"
    application_state: str = _NOT_APPLIED
    promotion_evidence_required: bool = True
    closure_evidence_required: bool = True

    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or not self.objective.strip():
            raise ValueError("profitability experiment identity is required")
        if not self.required_validation or any(
            not item.strip() for item in self.required_validation
        ):
            raise ValueError(
                "profitability experiment requires explicit validation steps"
            )
        if not self.human_review_required or self.target_status != "PAPER_CANDIDATE":
            raise ValueError(
                "profitability experiment must require human review "
                "before paper candidate"
            )
        _require_recommendation_only(
            "profitability experiment",
            application_state=self.application_state,
            promotion_evidence_required=self.promotion_evidence_required,
            closure_evidence_required=self.closure_evidence_required,
        )


@dataclass(frozen=True, slots=True)
class ExperimentCandidate:
    candidate_id: str
    strategy_id: str
    strategy_version: str
    regime: str
    sample_size: int
    baseline_expectancy_r: float
    reference_regime: str
    reference_expectancy_r: float
    hypothesis: str
    recommendation: str
    workflow: tuple[str, ...] = (
        "Baseline",
        "Candidate",
        "Replay",
        "WalkForward",
        "OOS",
        "Compare",
        "HumanReview",
        "Promotion",
    )
    status: str = "EXPERIMENT_CANDIDATE"
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    human_review_required: bool = True
    execution_allowed: bool = False
    application_state: str = _NOT_APPLIED
    promotion_evidence_required: bool = True
    closure_evidence_required: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("candidate_id", self.candidate_id),
            ("strategy_id", self.strategy_id),
            ("strategy_version", self.strategy_version),
            ("regime", self.regime),
            ("reference_regime", self.reference_regime),
            ("hypothesis", self.hypothesis),
            ("recommendation", self.recommendation),
        ):
            if not value.strip():
                raise ValueError(f"experiment candidate {name} is required")
        if self.sample_size < 1:
            raise ValueError("experiment candidate sample size must be positive")
        if not isfinite(self.baseline_expectancy_r) or not isfinite(
            self.reference_expectancy_r
        ):
            raise ValueError("experiment candidate expectancy values must be finite")
        expected_workflow = (
            "Baseline",
            "Candidate",
            "Replay",
            "WalkForward",
            "OOS",
            "Compare",
            "HumanReview",
            "Promotion",
        )
        if self.workflow != expected_workflow:
            raise ValueError("experiment candidate workflow must remain canonical")
        if self.status != "EXPERIMENT_CANDIDATE":
            raise ValueError("experiment candidate status must remain canonical")
        if self.promotion_status is not ValidationStatus.RESEARCH_ONLY:
            raise ValueError("experiment candidate must remain research only")
        if not self.human_review_required or self.execution_allowed:
            raise ValueError("experiment candidate cannot authorize execution")
        _require_recommendation_only(
            "experiment candidate",
            application_state=self.application_state,
            promotion_evidence_required=self.promotion_evidence_required,
            closure_evidence_required=self.closure_evidence_required,
        )


@dataclass(frozen=True, slots=True)
class ProfitabilityOptimizationLoop:
    loop_id: str
    stages: tuple[str, ...]
    metrics: tuple[ProfitabilityMetric, ...]
    strategy_regime_attribution: tuple[StrategyRegimeAttribution, ...]
    failure_analyses: tuple[FailureAnalysis, ...]
    experiments: tuple[ProfitabilityExperiment, ...]
    experiment_candidates: tuple[ExperimentCandidate, ...] = ()
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    risk_change_allowed: bool = False
    application_state: str = _NOT_APPLIED
    promotion_evidence_required: bool = True
    closure_evidence_required: bool = True

    def __post_init__(self) -> None:
        if not self.loop_id.strip():
            raise ValueError("profitability loop identity is required")
        expected = (
            "ClosedTrades",
            "EdgeLedger",
            "StrategyRegimeAttribution",
            "FailureAnalysis",
            "ImprovementCandidate",
            "BoundedExperiment",
            "WalkForward",
            "OOS",
            "CostStress",
            "HumanReview",
            "PaperCandidate",
        )
        if self.stages != expected:
            raise ValueError("profitability loop stages must remain canonical")
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(set(metric_ids)) != len(metric_ids):
            raise ValueError("profitability loop metric IDs must be unique")
        experiment_ids = tuple(item.experiment_id for item in self.experiments)
        if len(set(experiment_ids)) != len(experiment_ids):
            raise ValueError("profitability loop experiment IDs must be unique")
        experiment_candidate_ids = tuple(
            item.candidate_id for item in self.experiment_candidates
        )
        if len(set(experiment_candidate_ids)) != len(experiment_candidate_ids):
            raise ValueError(
                "profitability loop experiment candidate IDs must be unique"
            )
        if self.promotion_status is not ValidationStatus.RESEARCH_ONLY:
            raise ValueError("profitability loop must remain research only")
        if self.execution_allowed or self.risk_change_allowed:
            raise ValueError("profitability loop cannot authorize execution or risk")
        _require_recommendation_only(
            "profitability loop",
            application_state=self.application_state,
            promotion_evidence_required=self.promotion_evidence_required,
            closure_evidence_required=self.closure_evidence_required,
        )


@dataclass(frozen=True, slots=True)
class LearningSummary:
    summary_id: str
    created_at: datetime
    lessons: tuple[LessonCandidate, ...]
    experiments: tuple[ExperimentRecommendation, ...]
    profitability_loop: ProfitabilityOptimizationLoop | None = None
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    risk_change_allowed: bool = False
    application_state: str = _NOT_APPLIED
    promotion_evidence_required: bool = True
    closure_evidence_required: bool = True

    def __post_init__(self) -> None:
        if not self.summary_id.strip():
            raise ValueError("learning summary identity is required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("learning timestamp must be timezone-aware")
        if self.promotion_status is not ValidationStatus.RESEARCH_ONLY:
            raise ValueError("learning output must remain research only")
        if self.execution_allowed or self.risk_change_allowed:
            raise ValueError("learning cannot execute or change risk")
        _require_recommendation_only(
            "learning summary",
            application_state=self.application_state,
            promotion_evidence_required=self.promotion_evidence_required,
            closure_evidence_required=self.closure_evidence_required,
        )


def _require_recommendation_only(
    label: str,
    *,
    application_state: str,
    promotion_evidence_required: bool,
    closure_evidence_required: bool,
) -> None:
    if application_state != _NOT_APPLIED:
        raise ValueError(f"{label} cannot claim applied improvements")
    if not promotion_evidence_required or not closure_evidence_required:
        raise ValueError(
            f"{label} must require separate promotion and closure evidence"
        )

"""Walk-forward and out-of-sample validation contracts."""

from ai4binance.validation.integrity import (
    FeatureObservation,
    IndicatorIntegritySuite,
    IntegrityReport,
    IntegrityStatus,
    analyze_indicator_integrity,
    analyze_lookahead,
    analyze_recursive_stability,
    analyze_temporal_lineage,
)
from ai4binance.validation.models import (
    MarketRegime,
    ParameterSet,
    WalkForwardConfig,
    WalkForwardMode,
    WalkForwardReport,
)
from ai4binance.validation.multiple_comparison import (
    CandidatePerformance,
    MultipleComparisonReport,
    assess_multiple_comparisons,
)
from ai4binance.validation.overfit import (
    DeflatedSharpeAssessment,
    SelectionOverfitAssessment,
    assess_deflated_sharpe,
    assess_selection_overfit,
)
from ai4binance.validation.scalable_integrity import (
    ScalableIntegrityReport,
    analyze_scalable_lookahead,
    logarithmic_checkpoints,
)
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    StatisticalEvidenceAssessment,
    assess_statistical_evidence,
)
from ai4binance.validation.summary import (
    ValidationRunSummary,
    ValidationSummary,
    ValidationSummaryReader,
)
from ai4binance.validation.walk_forward import (
    RegimeClassifier,
    StrategyFactory,
    WalkForwardValidator,
)

__all__ = [
    "CandidatePerformance",
    "DeflatedSharpeAssessment",
    "FeatureObservation",
    "IndicatorIntegritySuite",
    "IntegrityReport",
    "IntegrityStatus",
    "MarketRegime",
    "MultipleComparisonReport",
    "MultipleTestingCorrection",
    "ParameterSet",
    "RegimeClassifier",
    "ScalableIntegrityReport",
    "SelectionOverfitAssessment",
    "StatisticalEvidenceAssessment",
    "StrategyFactory",
    "ValidationRunSummary",
    "ValidationSummary",
    "ValidationSummaryReader",
    "WalkForwardConfig",
    "WalkForwardMode",
    "WalkForwardReport",
    "WalkForwardValidator",
    "analyze_indicator_integrity",
    "analyze_lookahead",
    "analyze_recursive_stability",
    "analyze_scalable_lookahead",
    "analyze_temporal_lineage",
    "assess_deflated_sharpe",
    "assess_multiple_comparisons",
    "assess_selection_overfit",
    "assess_statistical_evidence",
    "logarithmic_checkpoints",
]

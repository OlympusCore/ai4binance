"""Walk-forward and out-of-sample validation contracts."""

from ai4binance.validation.futures_backtest_adapter import (
    RuntimeFuturesBacktestAdapter,
    RuntimeFuturesBacktestConfig,
    runtime_futures_backtest_engine,
)
from ai4binance.validation.futures_oos import (
    FuturesOosEvidenceQuery,
    FuturesOosEvidenceReader,
    FuturesOosEvidenceResolver,
    FuturesOosEvidenceWriter,
    FuturesOosEvidenceWriteResult,
    runtime_futures_strategy_sha256,
)
from ai4binance.validation.futures_oos_publication import (
    FuturesOosPublicationResult,
    FuturesOosPublicationService,
    FuturesOosRevisionResolver,
    FuturesOosRevisionSnapshot,
)
from ai4binance.validation.futures_replay import (
    RUNTIME_FUTURES_REPLAY_TIMEFRAMES,
    RuntimeFuturesReplayDataset,
    RuntimeFuturesReplayLoader,
    VerifiedRuntimeFuturesReplayArtifact,
)
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
from ai4binance.validation.live_gate_evidence import (
    LiveGateEvidenceKind,
    LiveGateEvidenceRecord,
    LiveGateEvidenceRegistry,
    LiveGateEvidenceResolution,
    LiveGateEvidenceSourceKind,
    LiveGateEvidenceVerificationStatus,
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
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceLedger,
    PromotionEvidenceRecord,
    PromotionEvidenceRegistry,
    PromotionEvidenceSourceKind,
)
from ai4binance.validation.regimes import classify_validation_regime
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
    FuturesReplayStrategy,
    FuturesStrategyFactory,
    FuturesWalkForwardValidator,
    RegimeClassifier,
    StrategyFactory,
    WalkForwardValidator,
)

__all__ = [
    "RUNTIME_FUTURES_REPLAY_TIMEFRAMES",
    "CandidatePerformance",
    "DeflatedSharpeAssessment",
    "FeatureObservation",
    "FuturesOosEvidenceQuery",
    "FuturesOosEvidenceReader",
    "FuturesOosEvidenceResolver",
    "FuturesOosEvidenceWriteResult",
    "FuturesOosEvidenceWriter",
    "FuturesOosPublicationResult",
    "FuturesOosPublicationService",
    "FuturesOosRevisionResolver",
    "FuturesOosRevisionSnapshot",
    "FuturesReplayStrategy",
    "FuturesStrategyFactory",
    "FuturesWalkForwardValidator",
    "IndicatorIntegritySuite",
    "IntegrityReport",
    "IntegrityStatus",
    "LiveGateEvidenceKind",
    "LiveGateEvidenceRecord",
    "LiveGateEvidenceRegistry",
    "LiveGateEvidenceResolution",
    "LiveGateEvidenceSourceKind",
    "LiveGateEvidenceVerificationStatus",
    "MarketRegime",
    "MultipleComparisonReport",
    "MultipleTestingCorrection",
    "ParameterSet",
    "PromotionEvidenceLedger",
    "PromotionEvidenceRecord",
    "PromotionEvidenceRegistry",
    "PromotionEvidenceSourceKind",
    "RegimeClassifier",
    "RuntimeFuturesBacktestAdapter",
    "RuntimeFuturesBacktestConfig",
    "RuntimeFuturesReplayDataset",
    "RuntimeFuturesReplayLoader",
    "ScalableIntegrityReport",
    "SelectionOverfitAssessment",
    "StatisticalEvidenceAssessment",
    "StrategyFactory",
    "ValidationRunSummary",
    "ValidationSummary",
    "ValidationSummaryReader",
    "VerifiedRuntimeFuturesReplayArtifact",
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
    "classify_validation_regime",
    "logarithmic_checkpoints",
    "runtime_futures_backtest_engine",
    "runtime_futures_strategy_sha256",
]

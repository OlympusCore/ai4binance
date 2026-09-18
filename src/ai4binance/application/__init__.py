"""Safe application services coordinating research-only workflows."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai4binance.application.live_readiness import (
        LiveReadinessBuilder,
        LiveReadinessEvidence,
    )
    from ai4binance.application.orchestration.whale_fusion import (
        WhaleFusionCycle,
        WhaleFusionResearchService,
        WhaleFusionWorkflowResult,
    )
    from ai4binance.application.research import (
        ResearchApplicationService,
        ResearchStage,
        ResearchStageStatus,
        ResearchWorkflowResult,
    )
    from ai4binance.application.runtime import (
        DualMarketAdvisoryReport,
        MarketAdvisory,
        ReadOnlyRuntimeCycle,
        RuntimeState,
    )
    from ai4binance.application.services.virtual_runtime import (
        IndependentVirtualPortfolios,
        VirtualMarketCycleResult,
        VirtualMarketRuntime,
        VirtualPortfolioState,
        VirtualRuntimeDecision,
        VirtualRuntimeDecisionStatus,
        VirtualRuntimeRequest,
        VirtualTradeIntent,
        evaluate_virtual_market_runtime,
        run_virtual_market_cycle,
    )
    from ai4binance.application.validation_pipeline import (
        HistoricalPlaybookAdapter,
        PlaybookValidationResult,
        ResearchValidationService,
        ValidationBatchResult,
    )
    from ai4binance.application.virtual_runtime_eligibility import (
        VirtualSimulationEligibility,
        VirtualSimulationStatus,
    )
    from ai4binance.application.virtual_runtime_performance import (
        VirtualPortfolioPerformanceMetrics,
        calculate_virtual_portfolio_performance_metrics,
    )

__all__ = (
    "DualMarketAdvisoryReport",
    "HistoricalPlaybookAdapter",
    "IndependentVirtualPortfolios",
    "LiveReadinessBuilder",
    "LiveReadinessEvidence",
    "MarketAdvisory",
    "PlaybookValidationResult",
    "ReadOnlyRuntimeCycle",
    "ResearchApplicationService",
    "ResearchStage",
    "ResearchStageStatus",
    "ResearchValidationService",
    "ResearchWorkflowResult",
    "RuntimeState",
    "ValidationBatchResult",
    "VirtualMarketCycleResult",
    "VirtualMarketRuntime",
    "VirtualPortfolioPerformanceMetrics",
    "VirtualPortfolioState",
    "VirtualRuntimeDecision",
    "VirtualRuntimeDecisionStatus",
    "VirtualRuntimeRequest",
    "VirtualSimulationEligibility",
    "VirtualSimulationStatus",
    "VirtualTradeIntent",
    "WhaleFusionCycle",
    "WhaleFusionResearchService",
    "WhaleFusionWorkflowResult",
    "calculate_virtual_portfolio_performance_metrics",
    "evaluate_virtual_market_runtime",
    "run_virtual_market_cycle",
)

_EXPORTS: dict[str, str] = {
    "DualMarketAdvisoryReport": "ai4binance.application.runtime",
    "HistoricalPlaybookAdapter": "ai4binance.application.validation_pipeline",
    "IndependentVirtualPortfolios": "ai4binance.application.services.virtual_runtime",
    "MarketAdvisory": "ai4binance.application.runtime",
    "LiveReadinessBuilder": "ai4binance.application.live_readiness",
    "LiveReadinessEvidence": "ai4binance.application.live_readiness",
    "PlaybookValidationResult": "ai4binance.application.validation_pipeline",
    "ReadOnlyRuntimeCycle": "ai4binance.application.runtime",
    "ResearchApplicationService": "ai4binance.application.research",
    "ResearchStage": "ai4binance.application.research",
    "ResearchStageStatus": "ai4binance.application.research",
    "ResearchValidationService": "ai4binance.application.validation_pipeline",
    "ResearchWorkflowResult": "ai4binance.application.research",
    "RuntimeState": "ai4binance.application.runtime",
    "ValidationBatchResult": "ai4binance.application.validation_pipeline",
    "VirtualMarketRuntime": "ai4binance.application.services.virtual_runtime",
    "VirtualMarketCycleResult": "ai4binance.application.services.virtual_runtime",
    "VirtualPortfolioState": "ai4binance.application.services.virtual_runtime",
    "VirtualPortfolioPerformanceMetrics": (
        "ai4binance.application.virtual_runtime_performance"
    ),
    "VirtualRuntimeDecision": "ai4binance.application.services.virtual_runtime",
    "VirtualRuntimeDecisionStatus": "ai4binance.application.services.virtual_runtime",
    "VirtualRuntimeRequest": "ai4binance.application.services.virtual_runtime",
    "VirtualSimulationEligibility": ("ai4binance.application.services.virtual_runtime"),
    "VirtualSimulationStatus": "ai4binance.application.services.virtual_runtime",
    "VirtualTradeIntent": "ai4binance.application.services.virtual_runtime",
    "evaluate_virtual_market_runtime": (
        "ai4binance.application.services.virtual_runtime"
    ),
    "calculate_virtual_portfolio_performance_metrics": (
        "ai4binance.application.virtual_runtime_performance"
    ),
    "run_virtual_market_cycle": "ai4binance.application.services.virtual_runtime",
    "WhaleFusionCycle": "ai4binance.application.orchestration.whale_fusion",
    "WhaleFusionResearchService": ("ai4binance.application.orchestration.whale_fusion"),
    "WhaleFusionWorkflowResult": ("ai4binance.application.orchestration.whale_fusion"),
}


def __getattr__(name: str) -> object:
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

"""Compatibility exports for the canonical bounded virtual runtime."""

import ai4binance.application.virtual_runtime_engine as _canonical
from ai4binance.application.virtual_runtime_engine import (
    IndependentVirtualPortfolios as IndependentVirtualPortfolios,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualAutonomyHaltStatus as VirtualAutonomyHaltStatus,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualClosedTradeRecord as VirtualClosedTradeRecord,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualClosureReview as VirtualClosureReview,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualEvidenceSurfaceAdapter as VirtualEvidenceSurfaceAdapter,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualExitContext as VirtualExitContext,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualFillPreview as VirtualFillPreview,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualFuturesPositionContext as VirtualFuturesPositionContext,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualImprovementResearchQueue as VirtualImprovementResearchQueue,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualImprovementResearchWorkItem as VirtualImprovementResearchWorkItem,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualLossStreakHaltReview as VirtualLossStreakHaltReview,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualManagedPosition as VirtualManagedPosition,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualMarketRuntime as VirtualMarketRuntime,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualNoTradeEvidenceSurface as VirtualNoTradeEvidenceSurface,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPortfolioPerformance as VirtualPortfolioPerformance,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPortfolioRiskGovernor as VirtualPortfolioRiskGovernor,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPortfolioState as VirtualPortfolioState,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPositionExit as VirtualPositionExit,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPositionLifecycleStatus as VirtualPositionLifecycleStatus,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPositionSide as VirtualPositionSide,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualPositionUpdateDecision as VirtualPositionUpdateDecision,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualResearchEvidenceSurface as VirtualResearchEvidenceSurface,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualRuntimeDecision as VirtualRuntimeDecision,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualRuntimeDecisionStatus as VirtualRuntimeDecisionStatus,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualRuntimeRequest as VirtualRuntimeRequest,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualStagedImprovementCandidate as VirtualStagedImprovementCandidate,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualTradeAttributionAggregate as VirtualTradeAttributionAggregate,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualTradeAttributionLedger as VirtualTradeAttributionLedger,
)
from ai4binance.application.virtual_runtime_engine import (
    VirtualTradeIntent as VirtualTradeIntent,
)
from ai4binance.application.virtual_runtime_engine import (
    __all__ as __all__,
)


def __getattr__(name: str) -> object:
    """Preserve incidental legacy exports from the canonical runtime owner."""
    return getattr(_canonical, name)

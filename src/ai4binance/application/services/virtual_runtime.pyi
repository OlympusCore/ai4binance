from ai4binance.application.virtual_runtime_eligibility import (
    VirtualSimulationEligibility,
    VirtualSimulationStatus,
    evaluate_virtual_simulation_eligibility,
)
from ai4binance.research.virtual_runtime import (
    IndependentVirtualPortfolios,
    VirtualEvidenceSurfaceAdapter,
    VirtualExitContext,
    VirtualImprovementResearchQueue,
    VirtualManagedPosition,
    VirtualMarketRuntime,
    VirtualNoTradeEvidenceSurface,
    VirtualPortfolioPerformance,
    VirtualPortfolioRiskGovernor,
    VirtualPortfolioState,
    VirtualPositionLifecycleStatus,
    VirtualPositionSide,
    VirtualResearchEvidenceSurface,
    VirtualRuntimeDecision,
    VirtualRuntimeDecisionStatus,
    VirtualRuntimeRequest,
    VirtualStagedImprovementCandidate,
    VirtualTradeIntent,
)

class VirtualMarketCycleResult:
    request: object
    decision: object
    eligibility: object
    blockers: tuple[str, ...]
    trade_intent: object | None
    portfolio_before: object
    portfolio_after: object
    audit_refs: tuple[str, ...]
    halt_review: object | None
    execution_allowed: bool
    live_eligibility_status: str

    @property
    def decision_status(self) -> object: ...
    @property
    def halted(self) -> bool: ...
    def to_payload(self) -> dict[str, object]: ...

def evaluate_virtual_market_runtime(
    request: object,
    *,
    runtime: object | None = ...,
) -> object: ...
def run_virtual_market_cycle(
    request: object,
    *,
    runtime: object | None = ...,
) -> VirtualMarketCycleResult: ...

__all__ = (
    "IndependentVirtualPortfolios",
    "VirtualEvidenceSurfaceAdapter",
    "VirtualExitContext",
    "VirtualImprovementResearchQueue",
    "VirtualManagedPosition",
    "VirtualMarketCycleResult",
    "VirtualMarketRuntime",
    "VirtualNoTradeEvidenceSurface",
    "VirtualPortfolioPerformance",
    "VirtualPortfolioRiskGovernor",
    "VirtualPortfolioState",
    "VirtualPositionLifecycleStatus",
    "VirtualPositionSide",
    "VirtualResearchEvidenceSurface",
    "VirtualRuntimeDecision",
    "VirtualRuntimeDecisionStatus",
    "VirtualRuntimeRequest",
    "VirtualSimulationEligibility",
    "VirtualSimulationStatus",
    "VirtualStagedImprovementCandidate",
    "VirtualTradeIntent",
    "evaluate_virtual_market_runtime",
    "evaluate_virtual_simulation_eligibility",
    "run_virtual_market_cycle",
)

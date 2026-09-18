"""Compatibility facade for canonical WHALE-FUSION orchestration services."""

from ai4binance.application.orchestration.whale_fusion import (
    WhaleFusionCycle as WhaleFusionCycle,
)
from ai4binance.application.orchestration.whale_fusion import (
    WhaleFusionResearchService as WhaleFusionResearchService,
)
from ai4binance.application.orchestration.whale_fusion import (
    WhaleFusionWorkflowResult as WhaleFusionWorkflowResult,
)

__all__ = (
    "WhaleFusionCycle",
    "WhaleFusionResearchService",
    "WhaleFusionWorkflowResult",
)

"""Compatibility facade for the canonical research-domain cycle aggregate."""

from ai4binance.domain.research.canonical_cycle import (
    MAX_BOUNDED_OBSERVATIONS,
    CanonicalCycleEnvelope,
    CanonicalCycleStep,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
)
from ai4binance.domain.research.lifecycle import (
    CycleLifecycleReceipt,
    LearningValidationResult,
    LifecycleClosureStep,
    MemoryDisposition,
)

__all__ = (
    "MAX_BOUNDED_OBSERVATIONS",
    "CanonicalCycleEnvelope",
    "CanonicalCycleStep",
    "CycleArtifactKind",
    "CycleArtifactRef",
    "CycleExecutionSurface",
    "CycleGovernanceStatus",
    "CycleLifecycleReceipt",
    "LearningValidationResult",
    "LifecycleClosureStep",
    "MemoryDisposition",
)

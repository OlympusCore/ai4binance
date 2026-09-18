"""External Intelligence & Evidence Fabric public contracts."""

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    RadarName,
    VerificationStatus,
)
from ai4binance.external_intel.core.models import (
    ExternalClaim,
    ExternalDecisionImpact,
    ExternalEvidence,
    ExternalFinding,
    ExternalObservation,
    RadarRunManifest,
    RetrievedDocument,
)
from ai4binance.external_intel.evidence import (
    EvidenceGraph,
    OriginalSourceAssessment,
    assess_original_sources,
)
from ai4binance.external_intel.evidence.verification import verify_claim
from ai4binance.external_intel.normalization.deduplication import (
    DuplicateCluster,
    cluster_duplicates,
)
from ai4binance.external_intel.scoring.manipulation_score import (
    ManipulationSignals,
    score_manipulation,
)
from ai4binance.external_intel.scoring.source_credibility import (
    SourceCredibilityInput,
    score_source_credibility,
)

__all__ = [
    "DecisionImpact",
    "DuplicateCluster",
    "EvidenceGraph",
    "ExternalClaim",
    "ExternalDecisionImpact",
    "ExternalEvidence",
    "ExternalFinding",
    "ExternalObservation",
    "ManipulationSignals",
    "MissionName",
    "OriginalSourceAssessment",
    "RadarName",
    "RadarRunManifest",
    "RetrievedDocument",
    "SourceCredibilityInput",
    "VerificationStatus",
    "assess_original_sources",
    "cluster_duplicates",
    "score_manipulation",
    "score_source_credibility",
    "verify_claim",
]

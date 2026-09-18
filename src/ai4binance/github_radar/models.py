"""Immutable contracts for capability-level repository research."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urlparse

_DOMAIN_RE = re.compile(r"R(?:[0-2][0-9]|30)")
_CAPABILITY_RE = re.compile(r"R(?:[0-2][0-9]|30)-C[0-9]{2}")
_VERIFICATION_RE = re.compile(r"V(?:0[1-9]|1[0-2])")
_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_HASH_RE = re.compile(r"[0-9a-f]{64}")


class RecommendationAction(StrEnum):
    REJECT = "REJECT"
    WATCH = "WATCH"
    RESEARCH = "RESEARCH"
    POC = "POC"
    ADOPT_IDEA = "ADOPT_IDEA"


class LocalCapabilityStatus(StrEnum):
    RESEARCH_GAP = "RESEARCH_GAP"
    DECLARED = "DECLARED"
    TESTED_CONTRACT = "TESTED_CONTRACT"
    RUNTIME_WIRED = "RUNTIME_WIRED"
    PRODUCTION_EVIDENCE = "PRODUCTION_EVIDENCE"


def _require_unique(
    name: str, values: tuple[str, ...], *, allow_empty: bool = True
) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{name} cannot be empty")
    if len(values) > 100 or len(set(values)) != len(values):
        raise ValueError(f"{name} must be bounded and unique")
    if any(not value.strip() or len(value) > 500 for value in values):
        raise ValueError(f"{name} contains an invalid value")


@dataclass(frozen=True, slots=True)
class ResearchDomain:
    domain_id: str
    title: str

    def __post_init__(self) -> None:
        if not _DOMAIN_RE.fullmatch(self.domain_id) or not self.title.strip():
            raise ValueError("research domain identity is invalid")


@dataclass(frozen=True, slots=True)
class VerificationProfile:
    profile_id: str
    title: str

    def __post_init__(self) -> None:
        if not _VERIFICATION_RE.fullmatch(self.profile_id) or not self.title.strip():
            raise ValueError("verification profile identity is invalid")


@dataclass(frozen=True, slots=True)
class AtomicCapability:
    capability_id: str
    domain_id: str
    title: str
    search_query: str
    target_layers: tuple[str, ...]
    target_agents: tuple[str, ...]
    local_evidence: tuple[str, ...]
    verification_profiles: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _CAPABILITY_RE.fullmatch(self.capability_id):
            raise ValueError("atomic capability identity is invalid")
        if not _DOMAIN_RE.fullmatch(self.domain_id):
            raise ValueError("atomic capability domain is invalid")
        if not self.capability_id.startswith(f"{self.domain_id}-"):
            raise ValueError("capability must belong to its encoded domain")
        if not self.title.strip() or not self.search_query.strip():
            raise ValueError("capability title and query are required")
        _require_unique("target layers", self.target_layers, allow_empty=False)
        _require_unique("target agents", self.target_agents, allow_empty=False)
        _require_unique("local evidence", self.local_evidence, allow_empty=False)
        _require_unique(
            "verification profiles", self.verification_profiles, allow_empty=False
        )
        if any(
            not _VERIFICATION_RE.fullmatch(item) for item in self.verification_profiles
        ):
            raise ValueError("capability verification profile is invalid")


@dataclass(frozen=True, slots=True)
class ResearchOntology:
    ontology_id: str
    schema_version: str
    domains: tuple[ResearchDomain, ...]
    verification_profiles: tuple[VerificationProfile, ...]
    capabilities: tuple[AtomicCapability, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.ontology_id.strip() or not self.schema_version.strip():
            raise ValueError("ontology identity is required")
        domain_ids = tuple(item.domain_id for item in self.domains)
        profile_ids = tuple(item.profile_id for item in self.verification_profiles)
        capability_ids = tuple(item.capability_id for item in self.capabilities)
        _require_unique("ontology domains", domain_ids, allow_empty=False)
        _require_unique("ontology profiles", profile_ids, allow_empty=False)
        _require_unique("ontology capabilities", capability_ids, allow_empty=False)
        if any(item.domain_id not in domain_ids for item in self.capabilities):
            raise ValueError("capability references an unknown domain")
        if any(
            profile not in profile_ids
            for item in self.capabilities
            for profile in item.verification_profiles
        ):
            raise ValueError("capability references an unknown verification profile")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("research ontology cannot grant trading authority")

    @property
    def by_capability_id(self) -> dict[str, AtomicCapability]:
        return {item.capability_id: item for item in self.capabilities}


@dataclass(frozen=True, slots=True)
class RepositorySource:
    repository: str
    url: str
    pinned_revision: str
    license_id: str
    language: str = "UNKNOWN"

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if (
            not self.repository.strip()
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
        ):
            raise ValueError("repository source must use credential-free HTTPS")
        if not _REVISION_RE.fullmatch(self.pinned_revision):
            raise ValueError("repository source requires a pinned 40-char revision")
        if not self.license_id.strip() or not self.language.strip():
            raise ValueError("repository license and language are required")


@dataclass(frozen=True, slots=True)
class EvidenceFragment:
    evidence_type: str
    reference: str
    claim: str
    content_sha256: str

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 2_000
            for value in (self.evidence_type, self.reference, self.claim)
        ):
            raise ValueError("evidence fields must be non-empty and bounded")
        if not _HASH_RE.fullmatch(self.content_sha256):
            raise ValueError("evidence requires a SHA-256 content hash")


@dataclass(frozen=True, slots=True)
class DimensionRating:
    dimension: str
    rating: float
    rationale: str

    def __post_init__(self) -> None:
        if not self.dimension.strip() or not 0.0 <= self.rating <= 1.0:
            raise ValueError("dimension rating must be within zero and one")
        if not self.rationale.strip() or len(self.rationale) > 2_000:
            raise ValueError("dimension rationale is required and bounded")


@dataclass(frozen=True, slots=True)
class RepositoryEvidence:
    capability_id: str
    source: RepositorySource
    evidence: tuple[EvidenceFragment, ...]
    risks: tuple[str, ...]
    ratings: tuple[DimensionRating, ...]
    passed_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _CAPABILITY_RE.fullmatch(self.capability_id):
            raise ValueError("repository evidence capability is invalid")
        _require_unique("repository risks", self.risks)
        _require_unique("passed gates", self.passed_gates)
        dimensions = tuple(item.dimension for item in self.ratings)
        _require_unique("rating dimensions", dimensions, allow_empty=False)
        if len(self.evidence) > 100:
            raise ValueError("repository evidence is unbounded")

    @property
    def research_id(self) -> str:
        material = (
            f"{self.source.repository}@{self.source.pinned_revision}:"
            f"{self.capability_id}"
        )
        return f"GR-{sha256(material.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True, slots=True)
class WeightedScore:
    dimension: str
    rating: float
    weight: int
    points: float
    rationale: str


@dataclass(frozen=True, slots=True)
class ResearchUnitEvaluation:
    research_id: str
    capability_id: str
    source: RepositorySource
    evidence: tuple[EvidenceFragment, ...]
    risks: tuple[str, ...]
    scores: tuple[WeightedScore, ...]
    total_score: float
    recommendation: RecommendationAction
    blockers: tuple[str, ...]
    reuse_mode: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"GR-[0-9a-f]{20}", self.research_id):
            raise ValueError("research unit identity is invalid")
        if not 0.0 <= self.total_score <= 100.0:
            raise ValueError("research score must be within zero and one hundred")
        _require_unique("evaluation blockers", self.blockers)
        if (
            self.recommendation
            in {
                RecommendationAction.POC,
                RecommendationAction.ADOPT_IDEA,
            }
            and self.blockers
        ):
            raise ValueError("advanced recommendation cannot contain hard blockers")
        if self.reuse_mode not in {"NONE", "LOCAL_REIMPLEMENTATION_ONLY"}:
            raise ValueError("unsupported repository reuse mode")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("repository evaluation cannot grant trading authority")


@dataclass(frozen=True, slots=True)
class LocalCapabilityAssessment:
    capability_id: str
    status: LocalCapabilityStatus
    present_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    target_agents: tuple[str, ...]
    target_layers: tuple[str, ...]
    related_gap_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _CAPABILITY_RE.fullmatch(self.capability_id):
            raise ValueError("local assessment capability is invalid")
        for name, values in (
            ("present evidence", self.present_evidence),
            ("missing evidence", self.missing_evidence),
            ("target agents", self.target_agents),
            ("target layers", self.target_layers),
            ("related gaps", self.related_gap_ids),
            ("baseline blockers", self.blockers),
        ):
            _require_unique(name, values)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("local baseline cannot grant trading authority")


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    owner: str
    name: str
    url: str
    default_branch: str
    stars: int
    pushed_at: datetime

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        identity = (self.owner, self.name, self.default_branch)
        if any(not value.strip() for value in identity):
            raise ValueError("GitHub repository identity is required")
        if parsed.scheme != "https" or parsed.netloc != "github.com":
            raise ValueError("GitHub repository URL must use github.com HTTPS")
        if self.stars < 0:
            raise ValueError("GitHub stars cannot be negative")
        if self.pushed_at.tzinfo is None or self.pushed_at.utcoffset() is None:
            raise ValueError("GitHub pushed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    path: str
    content: str

    def __post_init__(self) -> None:
        if not self.path.strip() or len(self.path) > 500:
            raise ValueError("fetched document path is invalid")
        if not self.content.strip() or len(self.content.encode("utf-8")) > 256_000:
            raise ValueError("fetched document content is empty or unbounded")


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    capability_id: str
    query: str
    source: RepositorySource
    evidence: tuple[EvidenceFragment, ...]
    risks: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _CAPABILITY_RE.fullmatch(self.capability_id) or not self.query.strip():
            raise ValueError("discovery candidate identity is invalid")
        _require_unique("discovery risks", self.risks)
        _require_unique("discovery blockers", self.blockers, allow_empty=False)
        if len(self.evidence) > 100:
            raise ValueError("discovery evidence is unbounded")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("discovery candidate cannot grant trading authority")

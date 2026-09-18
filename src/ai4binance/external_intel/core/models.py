"""Immutable shared models for External Intelligence & Evidence Fabric."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ai4binance.external_intel.core.enums import (
    AssetClass,
    DecisionImpact,
    ExtractionMethod,
    MissionName,
    OpportunityStatus,
    RadarName,
    RadarStatus,
    RetrievalStatus,
    SourceType,
    TechnologyRecommendation,
    VerificationStatus,
)
from ai4binance.external_intel.core.validation import (
    require_aware,
    require_optional_text,
    require_sha256,
    require_text,
    require_unique_text,
    require_unit_interval,
)

_FORBIDDEN_EIEF_OUTPUTS = frozenset(
    {
        "BUY",
        "SELL",
        "OPEN_LONG",
        "OPEN_SHORT",
        "EXECUTE",
        "MARKET_ORDER",
        "LIMIT_ORDER",
        "LIVE_ORDER_APPROVED",
    }
)


@dataclass(frozen=True, slots=True)
class ExternalObservation:
    observation_id: str
    provider_id: str
    source_type: SourceType
    source_uri: str
    canonical_uri: str
    title: str
    content_sha256: str
    retrieved_at: datetime
    published_at: datetime | None = None
    author_or_origin: str = "UNKNOWN"
    language: str = "UNKNOWN"
    summary: str = ""
    query_id: str | None = None
    query_text: str | None = None
    raw_reference: str = ""
    entities: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    event_candidates: tuple[str, ...] = ()
    source_credibility: float = 0.0
    retrieval_confidence: float = 0.0
    data_quality_status: RetrievalStatus = RetrievalStatus.VALID
    extraction_method: ExtractionMethod = ExtractionMethod.DETERMINISTIC
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("observation id", self.observation_id, maximum=200)
        require_text("observation provider", self.provider_id, maximum=200)
        require_text("observation source uri", self.source_uri, maximum=1_000)
        require_text("observation canonical uri", self.canonical_uri, maximum=1_000)
        require_text("observation title", self.title, maximum=1_000)
        require_sha256("observation content hash", self.content_sha256)
        require_aware("observation retrieved_at", self.retrieved_at)
        if self.published_at is not None:
            require_aware("observation published_at", self.published_at)
        require_text("observation author or origin", self.author_or_origin, maximum=500)
        require_text("observation language", self.language, maximum=40)
        require_optional_text("observation summary", self.summary, maximum=4_000)
        require_optional_text("observation query id", self.query_id, maximum=200)
        require_optional_text("observation query text", self.query_text, maximum=1_000)
        require_optional_text(
            "observation raw reference", self.raw_reference, maximum=2_000
        )
        require_unique_text("observation entities", self.entities)
        require_unique_text("observation symbols", self.symbols)
        require_unique_text("observation event candidates", self.event_candidates)
        require_unit_interval("observation source credibility", self.source_credibility)
        require_unit_interval(
            "observation retrieval confidence", self.retrieval_confidence
        )
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    document_id: str
    observation_id: str
    canonical_uri: str
    content_sha256: str
    title: str
    retrieved_at: datetime
    content_type: str
    byte_count: int
    text_excerpt: str = ""
    author_or_origin: str = "UNKNOWN"
    published_at: datetime | None = None
    language: str = "UNKNOWN"
    headings: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    extraction_method: ExtractionMethod = ExtractionMethod.DETERMINISTIC
    full_text_persisted: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("document id", self.document_id, maximum=200)
        require_text("document observation id", self.observation_id, maximum=200)
        require_text("document canonical uri", self.canonical_uri, maximum=1_000)
        require_sha256("document content hash", self.content_sha256)
        require_text("document title", self.title, maximum=1_000)
        require_aware("document retrieved_at", self.retrieved_at)
        require_text("document content type", self.content_type, maximum=200)
        if not 0 < self.byte_count <= 2_000_000:
            raise ValueError("document byte count must be positive and bounded")
        require_optional_text("document excerpt", self.text_excerpt, maximum=8_000)
        require_text("document author or origin", self.author_or_origin, maximum=500)
        if self.published_at is not None:
            require_aware("document published_at", self.published_at)
        require_text("document language", self.language, maximum=40)
        require_unique_text("document headings", self.headings, maximum_items=50)
        require_unique_text(
            "document references",
            self.references,
            maximum_items=100,
            maximum_text=1_000,
        )
        if self.full_text_persisted:
            raise ValueError("open-web documents cannot persist full article text")
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class RadarRunManifest:
    run_id: str
    radar: RadarName
    mission: MissionName
    started_at: datetime
    status: RadarStatus
    source_count: int = 0
    observation_count: int = 0
    claim_count: int = 0
    finding_count: int = 0
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("radar run id", self.run_id, maximum=200)
        require_aware("radar run started_at", self.started_at)
        for name, value in (
            ("source_count", self.source_count),
            ("observation_count", self.observation_count),
            ("claim_count", self.claim_count),
            ("finding_count", self.finding_count),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        require_unique_text("radar run blockers", self.blockers)
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class ExternalEvidence:
    evidence_id: str
    source_type: SourceType
    source_uri: str
    observed_at: datetime
    content_sha256: str
    citation: str
    author_or_origin: str = "UNKNOWN"
    reliability: float = 0.0
    raw_excerpt: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("evidence id", self.evidence_id, maximum=200)
        require_text("source uri", self.source_uri, maximum=1_000)
        require_aware("evidence observed_at", self.observed_at)
        require_sha256("evidence content hash", self.content_sha256)
        require_text("evidence citation", self.citation, maximum=1_000)
        require_text("evidence author or origin", self.author_or_origin, maximum=500)
        require_unit_interval("evidence reliability", self.reliability)
        require_optional_text("evidence excerpt", self.raw_excerpt, maximum=2_000)
        _require_no_forbidden_output(
            self.source_uri,
            self.citation,
            self.author_or_origin,
            self.raw_excerpt,
        )
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class ExternalClaim:
    claim_id: str
    text: str
    radar: RadarName
    mission: MissionName
    source_evidence_ids: tuple[str, ...]
    observed_at: datetime
    symbol: str | None = None
    asset: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("claim id", self.claim_id, maximum=200)
        require_text("claim text", self.text)
        require_unique_text(
            "claim evidence ids", self.source_evidence_ids, allow_empty=False
        )
        require_aware("claim observed_at", self.observed_at)
        require_optional_text("claim symbol", self.symbol, maximum=40)
        require_optional_text("claim asset", self.asset, maximum=40)
        require_unique_text("claim blockers", self.blockers)
        _require_no_forbidden_output(self.text, self.symbol or "", self.asset or "")
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class ExternalFinding:
    finding_id: str
    run_id: str
    radar: RadarName
    mission: MissionName
    observed_at: datetime
    source_type: SourceType
    event_type: str
    claim: str
    verification_status: VerificationStatus
    decision_impact: DecisionImpact
    evidence_ids: tuple[str, ...]
    symbol: str | None = None
    asset: str | None = None
    source_credibility: float = 0.0
    evidence_score: float = 0.0
    manipulation_risk: float = 0.0
    market_confirmation: float = 0.0
    opportunity_score: float = 0.0
    risk_score: float = 0.0
    confidence: float = 0.0
    blockers: tuple[str, ...] = ()
    audit_trace_id: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("finding id", self.finding_id, maximum=200)
        require_text("finding run id", self.run_id, maximum=200)
        require_aware("finding observed_at", self.observed_at)
        require_text("finding event type", self.event_type, maximum=200)
        require_text("finding claim", self.claim)
        require_optional_text("finding symbol", self.symbol, maximum=40)
        require_optional_text("finding asset", self.asset, maximum=40)
        for name, value in (
            ("source_credibility", self.source_credibility),
            ("evidence_score", self.evidence_score),
            ("manipulation_risk", self.manipulation_risk),
            ("market_confirmation", self.market_confirmation),
            ("opportunity_score", self.opportunity_score),
            ("risk_score", self.risk_score),
            ("confidence", self.confidence),
        ):
            require_unit_interval(name, value)
        require_unique_text("finding evidence ids", self.evidence_ids)
        require_unique_text("finding blockers", self.blockers)
        require_optional_text("finding audit trace id", self.audit_trace_id)
        if (
            self.verification_status is VerificationStatus.DATA_UNAVAILABLE
            and "DATA_UNAVAILABLE" not in self.blockers
        ):
            raise ValueError("data-unavailable findings must expose the blocker")
        _require_no_forbidden_output(
            self.event_type,
            self.claim,
            self.symbol or "",
            self.asset or "",
            *self.blockers,
        )
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class EvidenceGraphNode:
    node_id: str
    node_type: str
    label: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text("evidence graph node id", self.node_id, maximum=200)
        require_text("evidence graph node type", self.node_type, maximum=100)
        require_text("evidence graph node label", self.label, maximum=500)
        require_unique_text("evidence graph node evidence ids", self.evidence_ids)


@dataclass(frozen=True, slots=True)
class EvidenceGraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text("evidence graph edge id", self.edge_id, maximum=200)
        require_text("evidence graph edge source", self.source_node_id, maximum=200)
        require_text("evidence graph edge target", self.target_node_id, maximum=200)
        require_text("evidence graph relationship", self.relationship, maximum=100)
        require_unique_text("evidence graph edge evidence ids", self.evidence_ids)


@dataclass(frozen=True, slots=True)
class EligibleAsset:
    asset: str
    asset_class: AssetClass
    spot_symbols: tuple[str, ...] = ()
    futures_symbols: tuple[str, ...] = ()
    eligible_for_opportunity_scan: bool = False
    exclusion_reasons: tuple[str, ...] = ()
    classification_confidence: float = 0.0
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("eligible asset", self.asset, maximum=40)
        require_unique_text("eligible asset spot symbols", self.spot_symbols)
        require_unique_text("eligible asset futures symbols", self.futures_symbols)
        require_unique_text("eligible asset exclusions", self.exclusion_reasons)
        require_unit_interval(
            "eligible asset classification confidence",
            self.classification_confidence,
        )
        if self.eligible_for_opportunity_scan and self.exclusion_reasons:
            raise ValueError("eligible assets cannot carry exclusion reasons")
        if not self.eligible_for_opportunity_scan and not self.exclusion_reasons:
            raise ValueError("excluded assets require explicit exclusion reasons")
        _require_no_authority(
            self.execution_allowed,
            "RESEARCH_ONLY",
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    snapshot_id: str
    observed_at: datetime
    assets: tuple[EligibleAsset, ...]
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("universe snapshot id", self.snapshot_id, maximum=200)
        require_aware("universe snapshot observed_at", self.observed_at)
        if not self.assets:
            raise ValueError("universe snapshot requires at least one asset")
        asset_ids = tuple(asset.asset for asset in self.assets)
        require_unique_text("universe assets", asset_ids, allow_empty=False)
        require_unique_text("universe blockers", self.blockers)
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class OpportunityCandidate:
    candidate_id: str
    asset: str
    symbol: str
    status: OpportunityStatus
    evidence_ids: tuple[str, ...]
    opportunity_score: float
    risk_score: float
    confidence: float
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("opportunity candidate id", self.candidate_id, maximum=200)
        require_text("opportunity candidate asset", self.asset, maximum=40)
        require_text("opportunity candidate symbol", self.symbol, maximum=40)
        require_unique_text(
            "opportunity candidate evidence", self.evidence_ids, allow_empty=False
        )
        for name, value in (
            ("opportunity score", self.opportunity_score),
            ("opportunity risk score", self.risk_score),
            ("opportunity confidence", self.confidence),
        ):
            require_unit_interval(name, value)
        require_unique_text("opportunity blockers", self.blockers)
        _require_no_forbidden_output(self.status.value)
        _require_no_authority(
            self.execution_allowed,
            "RESEARCH_ONLY",
            self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class TechnologyCandidate:
    candidate_id: str
    technology_area: str
    title: str
    recommendation: TechnologyRecommendation
    evidence_ids: tuple[str, ...]
    relevance_to_ai4binance: float
    architecture_fit: float
    implementation_risk: float
    license_risk: float
    security_risk: float
    confidence: float
    affected_components: tuple[str, ...] = ()
    required_validation: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    installation_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_text("technology candidate id", self.candidate_id, maximum=200)
        require_text("technology area", self.technology_area, maximum=200)
        require_text("technology title", self.title, maximum=500)
        require_unique_text("technology evidence", self.evidence_ids)
        for name, value in (
            ("technology relevance", self.relevance_to_ai4binance),
            ("technology architecture fit", self.architecture_fit),
            ("technology implementation risk", self.implementation_risk),
            ("technology license risk", self.license_risk),
            ("technology security risk", self.security_risk),
            ("technology confidence", self.confidence),
        ):
            require_unit_interval(name, value)
        require_unique_text("technology blockers", self.blockers)
        require_unique_text("technology affected components", self.affected_components)
        require_unique_text("technology required validation", self.required_validation)
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("technology candidates cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("technology candidates must remain live blocked")


@dataclass(frozen=True, slots=True)
class ExternalDecisionImpact:
    symbol: str | None
    generated_at: datetime
    external_bias: DecisionImpact
    decision_impact: DecisionImpact
    confidence: float
    news_risk: float = 0.0
    social_risk: float = 0.0
    security_risk: float = 0.0
    regulatory_risk: float = 0.0
    manipulation_risk: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = field(default_factory=lambda: ("LIVE_ORDER_BLOCKED",))
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        require_optional_text("decision impact symbol", self.symbol, maximum=40)
        require_aware("decision impact generated_at", self.generated_at)
        for name, value in (
            ("decision confidence", self.confidence),
            ("news risk", self.news_risk),
            ("social risk", self.social_risk),
            ("security risk", self.security_risk),
            ("regulatory risk", self.regulatory_risk),
            ("manipulation risk", self.manipulation_risk),
        ):
            require_unit_interval(name, value)
        require_unique_text("decision evidence ids", self.evidence_ids)
        require_unique_text("decision blockers", self.blockers, allow_empty=False)
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("EIEF decision impact must keep live blocker visible")
        _require_no_authority(
            self.execution_allowed,
            self.promotion_status,
            self.live_eligibility_status,
        )


def _require_no_authority(
    execution_allowed: bool,
    promotion_status: str,
    live_eligibility_status: str,
) -> None:
    if (
        execution_allowed
        or promotion_status != "RESEARCH_ONLY"
        or live_eligibility_status != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("EIEF contracts cannot grant trading authority")


def _require_no_forbidden_output(*values: str) -> None:
    tokens = {
        token.strip().upper()
        for value in values
        for token in value.replace("/", " ").replace(",", " ").split()
    }
    forbidden = sorted(tokens.intersection(_FORBIDDEN_EIEF_OUTPUTS))
    if forbidden:
        raise ValueError(f"EIEF output contains forbidden execution terms: {forbidden}")

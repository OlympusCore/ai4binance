"""Credentialless Open Web Radar integrated with EIEF evidence contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    ProviderOperationalState,
    RadarName,
    RetrievalStatus,
    SourceType,
    VerificationStatus,
)
from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.models import (
    EvidenceGraphEdge,
    EvidenceGraphNode,
    ExternalClaim,
    ExternalEvidence,
    ExternalFinding,
    ExternalObservation,
    RetrievedDocument,
    TechnologyCandidate,
)
from ai4binance.external_intel.evidence import EvidenceGraph
from ai4binance.external_intel.normalization.urls import UrlPolicy
from ai4binance.external_intel.radars.open_web.router import (
    UrlRoute,
    UrlRouteKind,
    route_url,
)
from ai4binance.external_intel.retrieval.feeds import parse_feed
from ai4binance.external_intel.retrieval.html import extract_html_document
from ai4binance.external_intel.retrieval.source_config import (
    OpenWebPolicy,
    OpenWebSource,
)
from ai4binance.external_intel.retrieval.transport import (
    OpenWebFetchError,
    UrlFetcher,
)
from ai4binance.external_intel.storage.open_web import (
    CachedWebRecord,
    OpenWebEvidenceStore,
)
from ai4binance.external_intel.technology import analyze_technology

_EVIDENCE_ACTION_TERM = re.compile(
    r"\b(?:BUY|SELL|OPEN_LONG|OPEN_SHORT|EXECUTE|MARKET_ORDER|"
    r"LIMIT_ORDER|LIVE_ORDER_APPROVED)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class OpenWebRunReport:
    run_id: str
    generated_at: datetime
    mission: MissionName
    status: ProviderOperationalState
    provider_states: tuple[tuple[str, ProviderOperationalState], ...]
    routes: tuple[UrlRoute, ...]
    observations: tuple[ExternalObservation, ...]
    documents: tuple[RetrievedDocument, ...]
    evidence: tuple[ExternalEvidence, ...]
    claims: tuple[ExternalClaim, ...]
    findings: tuple[ExternalFinding, ...]
    technology_candidates: tuple[TechnologyCandidate, ...]
    evidence_graph: EvidenceGraph
    blockers: tuple[str, ...]
    cache_hits: int
    fetch_count: int
    model_inference_used: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("open-web report timestamp must be timezone-aware")
        if self.cache_hits < 0 or self.fetch_count < 0:
            raise ValueError("open-web metrics cannot be negative")
        if (
            self.model_inference_used
            or self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("open-web report cannot grant external authority")


@dataclass(slots=True)
class OpenWebRadarEngine:
    policy: OpenWebPolicy
    fetcher: UrlFetcher
    store: OpenWebEvidenceStore | None = None

    def __post_init__(self) -> None:
        if self.fetcher.policy.allowed_hosts != self.policy.allowed_hosts:
            raise ValueError("open-web fetcher and source policy hosts must match")

    @classmethod
    def from_policy(
        cls,
        policy: OpenWebPolicy,
        *,
        store: OpenWebEvidenceStore | None = None,
    ) -> OpenWebRadarEngine:
        return cls(policy, UrlFetcher(UrlPolicy(policy.allowed_hosts)), store)

    def scan(
        self,
        *,
        run_id: str,
        observed_at: datetime,
        mission: MissionName,
        seed_urls: tuple[str, ...] = (),
    ) -> OpenWebRunReport:
        records: list[CachedWebRecord] = []
        routes: list[UrlRoute] = []
        blockers: list[str] = []
        states: list[tuple[str, ProviderOperationalState]] = []
        processed: set[str] = set()
        cache_hits = 0
        fetch_count = 0

        for source in self.policy.sources:
            if source.mission is not mission:
                continue
            if not source.enabled:
                states.append(
                    (source.source_id, ProviderOperationalState.SOURCE_NOT_REQUIRED)
                )
                continue
            (
                source_records,
                source_routes,
                source_blockers,
                source_cache,
                source_fetch,
            ) = self._scan_source(source, observed_at, processed)
            records.extend(source_records)
            routes.extend(source_routes)
            blockers.extend(source_blockers)
            cache_hits += source_cache
            fetch_count += source_fetch
            state = (
                ProviderOperationalState.AVAILABLE
                if source_records
                else ProviderOperationalState.DEGRADED
            )
            states.append((source.source_id, state))
            if source.required and not source_records:
                blockers.append(f"REQUIRED_SOURCE_UNAVAILABLE:{source.source_id}")

        for seed_url in seed_urls:
            seed_records, seed_route, seed_blockers, was_cached, was_fetched = (
                self._process_url(
                    seed_url,
                    source_id="seed_url",
                    source_type=SourceType.WEB_ARTICLE,
                    source_reliability=0.5,
                    observed_at=observed_at,
                    published_at=None,
                    processed=processed,
                    robots_required=True,
                )
            )
            records.extend(seed_records)
            if seed_route is not None:
                routes.append(seed_route)
            blockers.extend(seed_blockers)
            cache_hits += int(was_cached)
            fetch_count += int(was_fetched)

        observations = tuple(record.observation for record in records)
        documents = tuple(record.document for record in records)
        evidence = tuple(record.evidence for record in records)
        candidates = tuple(
            candidate
            for record in records
            if (
                candidate := analyze_technology(
                    record.document,
                    evidence_id=record.evidence.evidence_id,
                    source_reliability=record.evidence.reliability,
                )
            )
            is not None
        )
        claims = tuple(
            self._claim(run_id, candidate, observed_at) for candidate in candidates
        )
        findings = tuple(
            self._finding(run_id, claim, candidate, observed_at)
            for claim, candidate in zip(claims, candidates, strict=True)
        )
        graph = _evidence_graph(records, claims, candidates)
        status = _report_status(records, blockers)
        if not records:
            blockers.append("DATA_UNAVAILABLE")
        return OpenWebRunReport(
            run_id=run_id,
            generated_at=observed_at,
            mission=mission,
            status=status,
            provider_states=tuple(states),
            routes=tuple(routes),
            observations=observations,
            documents=documents,
            evidence=evidence,
            claims=claims,
            findings=findings,
            technology_candidates=candidates,
            evidence_graph=graph,
            blockers=tuple(dict.fromkeys((*blockers, "LIVE_ORDER_BLOCKED"))),
            cache_hits=cache_hits,
            fetch_count=fetch_count,
        )

    def _scan_source(
        self,
        source: OpenWebSource,
        observed_at: datetime,
        processed: set[str],
    ) -> tuple[list[CachedWebRecord], list[UrlRoute], list[str], int, int]:
        try:
            feed = self.fetcher.fetch(
                source.feed_url,
                allowed_content_types=frozenset(
                    {
                        "application/atom+xml",
                        "application/rss+xml",
                        "application/xml",
                        "text/xml",
                    }
                ),
                robots_required=source.robots_required,
            )
            entries = parse_feed(
                feed.body, maximum=source.max_items, retrieved_at=observed_at
            )
        except (OpenWebFetchError, ValueError) as error:
            return [], [], [f"SOURCE_FETCH_FAILED:{source.source_id}:{error}"], 0, 0
        records: list[CachedWebRecord] = []
        routes: list[UrlRoute] = []
        blockers: list[str] = []
        cache_hits = 0
        fetch_count = 1
        for entry in entries:
            host = UrlPolicy(source.allowed_hosts)
            try:
                host.validate(entry.source_url)
            except ValueError:
                blockers.append(f"SOURCE_LINK_HOST_NOT_ALLOWED:{source.source_id}")
                continue
            result, route, item_blockers, was_cached, was_fetched = self._process_url(
                entry.source_url,
                source_id=source.source_id,
                source_type=source.source_type,
                source_reliability=source.reliability,
                observed_at=observed_at,
                published_at=entry.published_at,
                processed=processed,
                robots_required=source.robots_required,
            )
            records.extend(result)
            if route is not None:
                routes.append(route)
            blockers.extend(item_blockers)
            cache_hits += int(was_cached)
            fetch_count += int(was_fetched)
        return records, routes, blockers, cache_hits, fetch_count

    def _process_url(
        self,
        url: str,
        *,
        source_id: str,
        source_type: SourceType,
        source_reliability: float,
        observed_at: datetime,
        published_at: datetime | None,
        processed: set[str],
        robots_required: bool,
    ) -> tuple[list[CachedWebRecord], UrlRoute | None, list[str], bool, bool]:
        try:
            route = route_url(url, self.fetcher.policy)
        except ValueError:
            return [], None, ["URL_POLICY_BLOCKED"], False, False
        if route.canonical_url in processed:
            return [], route, [], True, False
        processed.add(route.canonical_url)
        if route.route is UrlRouteKind.GITHUB_RADAR:
            return [], route, ["ROUTE_TO_EXISTING_GITHUB_RADAR"], False, False
        try:
            cached = (
                self.store.get(route.canonical_url) if self.store is not None else None
            )
        except (OSError, ValueError):
            return [], route, [f"EVIDENCE_CACHE_INVALID:{source_id}"], False, False
        if cached is not None:
            return [cached], route, [], True, False
        try:
            resource = self.fetcher.fetch(
                route.canonical_url,
                allowed_content_types=frozenset({"text/html"}),
                robots_required=robots_required,
            )
            observation_id = eief_id(
                "webobs", source_id, resource.final_url, resource.content_sha256
            )
            document = extract_html_document(resource, observation_id=observation_id)
        except (OpenWebFetchError, ValueError) as error:
            return (
                [],
                route,
                [f"DOCUMENT_FETCH_FAILED:{source_id}:{error}"],
                False,
                True,
            )
        observation = ExternalObservation(
            observation_id=observation_id,
            provider_id=source_id,
            source_type=source_type,
            source_uri=url,
            canonical_uri=resource.final_url,
            title=document.title,
            content_sha256=document.content_sha256,
            retrieved_at=document.retrieved_at,
            published_at=published_at or document.published_at,
            author_or_origin=document.author_or_origin,
            language=document.language,
            summary=document.text_excerpt[:4_000],
            raw_reference=url,
            source_credibility=source_reliability,
            retrieval_confidence=0.9,
            data_quality_status=RetrievalStatus.VALID,
        )
        try:
            evidence = ExternalEvidence(
                evidence_id=eief_id("webev", document.document_id),
                source_type=source_type,
                source_uri=document.canonical_uri,
                observed_at=document.retrieved_at,
                content_sha256=document.content_sha256,
                citation=document.canonical_uri,
                author_or_origin=_safe_evidence_text(document.author_or_origin),
                reliability=source_reliability,
                raw_excerpt=_safe_evidence_text(document.text_excerpt[:2_000]),
            )
        except ValueError:
            return [], route, [f"EVIDENCE_CONTRACT_BLOCKED:{source_id}"], False, True
        record = CachedWebRecord(observation, document, evidence)
        if self.store is not None:
            try:
                self.store.append(record)
            except (OSError, ValueError):
                return [], route, [f"EVIDENCE_STORE_FAILED:{source_id}"], False, True
        return [record], route, [], False, True

    @staticmethod
    def _claim(
        run_id: str,
        candidate: TechnologyCandidate,
        observed_at: datetime,
    ) -> ExternalClaim:
        return ExternalClaim(
            claim_id=eief_id("webclaim", run_id, candidate.candidate_id),
            text=(
                f"Technology evidence maps candidate {candidate.candidate_id} to "
                f"{candidate.technology_area} for governed research"
            ),
            radar=RadarName.OPEN_WEB_RADAR,
            mission=MissionName.TECHNOLOGY_DEVELOPMENT,
            source_evidence_ids=candidate.evidence_ids,
            observed_at=observed_at,
            verification_status=VerificationStatus.UNVERIFIED,
            blockers=("INDEPENDENT_SOURCE_COUNT_LOW", "LIVE_ORDER_BLOCKED"),
        )

    @staticmethod
    def _finding(
        run_id: str,
        claim: ExternalClaim,
        candidate: TechnologyCandidate,
        observed_at: datetime,
    ) -> ExternalFinding:
        return ExternalFinding(
            finding_id=eief_id("webfind", claim.claim_id),
            run_id=run_id,
            radar=RadarName.OPEN_WEB_RADAR,
            mission=MissionName.TECHNOLOGY_DEVELOPMENT,
            observed_at=observed_at,
            source_type=SourceType.WEB_ARTICLE,
            event_type="technology_research_evidence",
            claim=claim.text,
            verification_status=VerificationStatus.UNVERIFIED,
            decision_impact=DecisionImpact.LOW_CONFIDENCE,
            evidence_ids=candidate.evidence_ids,
            source_credibility=candidate.confidence,
            evidence_score=candidate.confidence,
            risk_score=candidate.implementation_risk,
            confidence=candidate.confidence,
            blockers=tuple(
                dict.fromkeys(
                    (
                        *claim.blockers,
                        *candidate.blockers,
                        "NO_TRADE_SIGNAL_AUTHORITY",
                    )
                )
            ),
            audit_trace_id=eief_id("audit", claim.claim_id),
        )


def _report_status(
    records: list[CachedWebRecord], blockers: list[str]
) -> ProviderOperationalState:
    if not records:
        return ProviderOperationalState.UNAVAILABLE
    if any(blocker.startswith("REQUIRED_SOURCE_UNAVAILABLE") for blocker in blockers):
        return ProviderOperationalState.DEGRADED
    return ProviderOperationalState.AVAILABLE


def _evidence_graph(
    records: list[CachedWebRecord],
    claims: tuple[ExternalClaim, ...],
    candidates: tuple[TechnologyCandidate, ...],
) -> EvidenceGraph:
    nodes: list[EvidenceGraphNode] = []
    edges: list[EvidenceGraphEdge] = []
    evidence_to_document: dict[str, str] = {}
    for record in records:
        document_node = f"document:{record.document.document_id}"
        evidence_node = f"evidence:{record.evidence.evidence_id}"
        nodes.extend(
            (
                EvidenceGraphNode(
                    document_node,
                    "DOCUMENT",
                    record.document.title[:500],
                    (record.evidence.evidence_id,),
                ),
                EvidenceGraphNode(
                    evidence_node,
                    "EVIDENCE",
                    record.evidence.citation[:500],
                    (record.evidence.evidence_id,),
                ),
            )
        )
        evidence_to_document[record.evidence.evidence_id] = document_node
        edges.append(
            EvidenceGraphEdge(
                eief_id("edge", evidence_node, document_node, "OBSERVED_IN"),
                evidence_node,
                document_node,
                "OBSERVED_IN",
                (record.evidence.evidence_id,),
            )
        )
    for claim, candidate in zip(claims, candidates, strict=True):
        claim_node = f"claim:{claim.claim_id}"
        candidate_node = f"candidate:{candidate.candidate_id}"
        nodes.extend(
            (
                EvidenceGraphNode(
                    claim_node, "CLAIM", claim.text[:500], claim.source_evidence_ids
                ),
                EvidenceGraphNode(
                    candidate_node,
                    "TECHNOLOGY_CANDIDATE",
                    candidate.title[:500],
                    candidate.evidence_ids,
                ),
            )
        )
        for evidence_id in claim.source_evidence_ids:
            supported_document = evidence_to_document.get(evidence_id)
            if supported_document is None:
                continue
            edges.append(
                EvidenceGraphEdge(
                    eief_id("edge", claim_node, supported_document, "DERIVED_FROM"),
                    claim_node,
                    supported_document,
                    "DERIVED_FROM",
                    (evidence_id,),
                )
            )
        edges.append(
            EvidenceGraphEdge(
                eief_id("edge", candidate_node, claim_node, "SUPPORTED_BY"),
                candidate_node,
                claim_node,
                "SUPPORTED_BY",
                candidate.evidence_ids,
            )
        )
    return EvidenceGraph(tuple(nodes), tuple(edges))


def _safe_evidence_text(value: str) -> str:
    return _EVIDENCE_ACTION_TERM.sub("[ACTION_TERM_REDACTED]", value)

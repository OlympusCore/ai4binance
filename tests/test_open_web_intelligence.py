from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from email.message import Message
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector, Request

import pytest

from ai4binance.external_intel.cli.commands import open_web_payload
from ai4binance.external_intel.core.enums import (
    MissionName,
    ProviderOperationalState,
    RetrievalStatus,
    SourceType,
    TechnologyRecommendation,
)
from ai4binance.external_intel.core.models import (
    ExternalEvidence,
    ExternalObservation,
    RetrievedDocument,
)
from ai4binance.external_intel.normalization.urls import (
    UrlPolicy,
    canonicalize_url,
)
from ai4binance.external_intel.radars.open_web.engine import (
    OpenWebRadarEngine,
    OpenWebRunReport,
)
from ai4binance.external_intel.radars.open_web.router import (
    UrlRouteKind,
    route_url,
)
from ai4binance.external_intel.retrieval.feeds import feed_host, parse_feed
from ai4binance.external_intel.retrieval.html import extract_html_document
from ai4binance.external_intel.retrieval.source_config import (
    OpenWebPolicy,
    OpenWebSource,
    default_open_web_policy_path,
    load_open_web_policy,
)
from ai4binance.external_intel.retrieval.transport import (
    FetchedResource,
    OpenWebFetchError,
    UrlFetcher,
)
from ai4binance.external_intel.storage.open_web import (
    CachedWebRecord,
    OpenWebEvidenceStore,
)
from ai4binance.external_intel.technology import analyze_technology

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
PUBLIC_IPS = ("93.184.216.34",)
_ResponseValue = tuple[int, Message, bytes] | Exception


def _headers(content_type: str = "text/html", **values: str) -> Message:
    headers = Message()
    headers["Content-Type"] = content_type
    for key, value in values.items():
        headers[key.replace("_", "-")] = value
    return headers


class _Response:
    def __init__(self, status: int, headers: Message, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self._body = body

    def read(self, maximum: int = -1) -> bytes:
        return self._body if maximum < 0 else self._body[:maximum]

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _Opener:
    def __init__(
        self,
        responses: Mapping[str, _ResponseValue],
    ) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def open(self, request: Request, timeout: float) -> _Response:
        assert 0.1 <= timeout <= 30.0
        url = request.full_url
        self.calls.append(url)
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return _Response(*value)


def _fetcher(
    hosts: tuple[str, ...],
    responses: Mapping[str, _ResponseValue],
    *,
    timeout_seconds: float = 10.0,
    max_response_bytes: int = 1_000_000,
    max_redirects: int = 3,
) -> tuple[UrlFetcher, _Opener]:
    opener = _Opener(responses)
    fetcher = UrlFetcher(
        UrlPolicy(hosts),
        resolver=lambda _host: PUBLIC_IPS,
        opener=cast(OpenerDirector, opener),
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        max_redirects=max_redirects,
    )
    return fetcher, opener


def _resource(
    body: bytes = b"<html><title>Agent security update</title></html>",
    *,
    url: str = "https://github.blog/article/",
    content_type: str = "text/html",
) -> FetchedResource:
    return FetchedResource(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type=content_type,
        body=body,
        retrieved_at=NOW,
        content_sha256=sha256(body).hexdigest(),
    )


def _document(**overrides: object) -> RetrievedDocument:
    values: dict[str, object] = {
        "document_id": "doc-1",
        "observation_id": "obs-1",
        "canonical_uri": "https://github.blog/article/",
        "content_sha256": "a" * 64,
        "title": "Agent orchestration and RAG security",
        "retrieved_at": NOW,
        "content_type": "text/html",
        "byte_count": 100,
        "text_excerpt": "Agent security architecture with retrieval and RAG.",
        "author_or_origin": "GitHub",
        "language": "en",
        "headings": ("Context engineering",),
        "references": ("https://github.blog/reference/",),
    }
    values.update(overrides)
    return RetrievedDocument(**values)  # type: ignore[arg-type]


def _policy(*, enabled: bool = True, required: bool = True) -> OpenWebPolicy:
    return OpenWebPolicy(
        schema_version="TEST-1",
        network_mode="ALLOWLISTED_PUBLIC_WEB",
        search_mode="DIRECT_SOURCES_ONLY",
        llm_mode="DISABLED",
        cloud_llm_allowed=False,
        credentialed_provider_allowed=False,
        persist_full_article_text=False,
        seed_allowed_hosts=("github.blog", "github.com", "arxiv.org"),
        sources=(
            OpenWebSource(
                source_id="github_changelog",
                feed_url="https://github.blog/feed/",
                allowed_hosts=("github.blog",),
                mission=MissionName.TECHNOLOGY_DEVELOPMENT,
                source_type=SourceType.OFFICIAL_DOCUMENT,
                source_tier="TIER_0",
                reliability=0.9,
                enabled=enabled,
                required=required,
                robots_required=True,
                max_items=3,
            ),
        ),
    )


def _engine_responses() -> dict[str, tuple[int, Message, bytes] | Exception]:
    feed = b"""
    <rss><channel><item>
      <title>BUY: agent security and RAG update</title>
      <link>https://github.blog/article/?utm_source=tracker</link>
      <pubDate>Sun, 09 Aug 2026 12:00:00 GMT</pubDate>
    </item></channel></rss>
    """
    article = b"""
    <html lang="en"><head>
      <title>BUY agent security and RAG update</title>
      <meta name="author" content="Security Team" />
      <meta property="article:published_time" content="2026-08-09T11:00:00Z" />
    </head><body><h1>Agent orchestration security</h1>
      <p>BUY and SELL are untrusted article words. RAG security hardening.</p>
      <script>LIVE_ORDER_APPROVED</script>
      <a href="/reference/?utm_campaign=x">Reference</a>
    </body></html>
    """
    return {
        "https://github.blog/robots.txt": (
            200,
            _headers("text/plain"),
            b"User-agent: *\nAllow: /\n",
        ),
        "https://github.blog/feed/": (
            200,
            _headers("application/rss+xml"),
            feed,
        ),
        "https://github.blog/article/": (200, _headers(), article),
    }


def test_url_canonicalization_and_policy_block_unsafe_inputs() -> None:
    assert (
        canonicalize_url("HTTPS://Example.COM/path?utm_source=x&b=2&a=1#fragment")
        == "https://example.com/path?a=1&b=2"
    )
    assert canonicalize_url("https://example.com") == "https://example.com/"
    policy = UrlPolicy(("example.com",))
    assert (
        policy.validate("https://example.com/path", resolved_addresses=PUBLIC_IPS)
        == "https://example.com/path"
    )

    for url in (
        "http://example.com/",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
        "https://other.example/",
        "not-a-url",
    ):
        with pytest.raises(ValueError, match="open-web"):
            policy.validate(url)
    for address in ("127.0.0.1", "10.0.0.1", "::1", "not-an-ip"):
        with pytest.raises(ValueError, match="open-web"):
            policy.validate("https://example.com/", resolved_addresses=(address,))
    with pytest.raises(ValueError, match="URL policy"):
        UrlPolicy(())
    with pytest.raises(ValueError, match="URL policy"):
        UrlPolicy(("Example.COM",))
    with pytest.raises(ValueError, match="Port"):
        canonicalize_url("https://example.com:bad/")


def test_route_url_uses_existing_specialist_boundaries() -> None:
    policy = UrlPolicy(
        ("github.com", "arxiv.org", "www.binance.com", "t.co", "github.blog")
    )
    assert (
        route_url("https://github.com/org/repo", policy).route
        is UrlRouteKind.GITHUB_RADAR
    )
    assert (
        route_url("https://arxiv.org/abs/1", policy).route
        is UrlRouteKind.RESEARCH_DOCUMENT
    )
    assert (
        route_url("https://www.binance.com/en/support", policy).route
        is UrlRouteKind.OFFICIAL_EXCHANGE
    )
    assert (
        route_url("https://t.co/abc", policy).route is UrlRouteKind.REDIRECT_DISCOVERY
    )
    assert route_url("https://github.blog/post", policy).route is UrlRouteKind.OPEN_WEB


def test_feed_parser_handles_rss_atom_dedup_and_hostile_xml() -> None:
    rss = b"""
    <rss><channel>
      <item><title>One</title><link>https://github.blog/a/?utm_source=x</link>
        <pubDate>Sun, 09 Aug 2026 12:00:00 GMT</pubDate></item>
      <item><title>Duplicate</title><link>https://github.blog/a/</link></item>
      <item><title>Unsafe</title><link>http://github.blog/b/</link></item>
      <item><title></title><link>https://github.blog/c/</link></item>
    </channel></rss>
    """
    entries = parse_feed(rss, maximum=3, retrieved_at=NOW)
    assert len(entries) == 1
    assert entries[0].source_url == "https://github.blog/a/"
    assert feed_host(entries[0]) == "github.blog"

    atom = b"""
    <feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Atom</title><link rel="alternate" href="https://github.blog/b/" />
      <updated>2026-08-09T12:30:00Z</updated>
    </entry></feed>
    """
    assert parse_feed(atom, maximum=1)[0].title == "Atom"
    assert (
        parse_feed(
            b"<rss><channel><item><title>X</title><link>https://github.blog/x/</link>"
            b"</item></channel></rss>",
            maximum=1,
            retrieved_at=NOW,
        )[0].published_at
        == NOW
    )
    for payload, maximum in ((b"", 1), (b"x" * 2_000_001, 1), (rss, 0)):
        with pytest.raises(ValueError, match="feed"):
            parse_feed(payload, maximum=maximum)
    with pytest.raises(ValueError, match="invalid or unsafe"):
        parse_feed(
            b"<!DOCTYPE x [<!ENTITY y SYSTEM 'file:///etc/passwd'>]><x>&y;</x>",
            maximum=1,
        )


def test_html_extraction_is_bounded_and_does_not_persist_full_text() -> None:
    body = b"""
    <html lang="tr"><head><meta property="og:title" content="Agent security" />
    <meta name="author" content="Research Team" />
    <meta name="date" content="2026-08-09T10:00:00" /></head>
    <body><h1>Architecture</h1><script>ignored secret</script>
    <p>RAG and agent orchestration.</p><a href="/ref?utm_source=x">ref</a>
    <a href="javascript:alert(1)">bad</a></body></html>
    """
    document = extract_html_document(_resource(body), observation_id="obs")
    assert document.title == "Agent security"
    assert document.author_or_origin == "Research Team"
    assert document.language == "tr"
    assert document.published_at == datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    assert "ignored secret" not in document.text_excerpt
    assert document.references == ("https://github.blog/ref",)
    assert document.full_text_persisted is False
    with pytest.raises(ValueError, match="text/html"):
        extract_html_document(
            _resource(b"text", content_type="text/plain"), observation_id="obs"
        )
    with pytest.raises(ValueError, match="cannot persist"):
        _document(full_text_persisted=True)


def test_transport_enforces_robots_redirect_content_and_size() -> None:
    responses = {
        "https://example.com/robots.txt": (
            200,
            _headers("text/plain"),
            b"User-agent: *\nAllow: /\n",
        ),
        "https://example.com/start": (
            302,
            _headers(location="/final"),
            b"redirect",
        ),
        "https://example.com/final": (200, _headers(), b"<html>ok</html>"),
    }
    fetcher, opener = _fetcher(("example.com",), responses)
    resource = fetcher.fetch("https://example.com/start")
    assert resource.final_url == "https://example.com/final"
    assert resource.redirect_chain == ("https://example.com/final",)
    assert opener.calls.count("https://example.com/robots.txt") == 1
    assert fetcher.fetch("https://example.com/final").body == b"<html>ok</html>"
    assert opener.calls.count("https://example.com/robots.txt") == 1

    for name, response, expected in (
        ("type", (200, _headers("image/png"), b"png"), "CONTENT_TYPE_NOT_ALLOWED"),
        (
            "encoding",
            (200, _headers(content_encoding="gzip"), b"zip"),
            "CONTENT_ENCODING_NOT_ALLOWED",
        ),
        ("empty", (200, _headers(), b""), "EMPTY_RESPONSE"),
        ("status", (503, _headers(), b"down"), "HTTP_STATUS_503"),
        ("missing", (302, _headers(), b"redirect"), "REDIRECT_LOCATION_MISSING"),
    ):
        url = f"https://example.com/{name}"
        local, _ = _fetcher(
            ("example.com",),
            {url: response},
        )
        with pytest.raises(OpenWebFetchError, match=expected):
            local.fetch(url, robots_required=False)

    large, _ = _fetcher(
        ("example.com",),
        {"https://example.com/large": (200, _headers(), b"x" * 1_025)},
        max_response_bytes=1_024,
    )
    with pytest.raises(OpenWebFetchError, match="RESPONSE_TOO_LARGE"):
        large.fetch("https://example.com/large", robots_required=False)


def test_transport_fails_closed_for_robots_network_dns_and_limits() -> None:
    denied, _ = _fetcher(
        ("example.com",),
        {
            "https://example.com/robots.txt": (
                200,
                _headers("text/plain"),
                b"User-agent: *\nDisallow: /\n",
            )
        },
    )
    with pytest.raises(OpenWebFetchError, match="ROBOTS_DISALLOWED"):
        denied.fetch("https://example.com/secret")

    missing, _ = _fetcher(
        ("example.com",),
        {
            "https://example.com/robots.txt": (
                404,
                _headers("text/plain"),
                b"missing",
            ),
            "https://example.com/page": (200, _headers(), b"ok"),
        },
    )
    assert missing.fetch("https://example.com/page").body == b"ok"

    unavailable, _ = _fetcher(
        ("example.com",),
        {"https://example.com/page": URLError("offline")},
    )
    with pytest.raises(OpenWebFetchError, match="PROVIDER_UNAVAILABLE"):
        unavailable.fetch("https://example.com/page", robots_required=False)

    http_headers = _headers()
    http_error = HTTPError(
        "https://example.com/page", 429, "limited", http_headers, BytesIO(b"wait")
    )
    limited, _ = _fetcher(("example.com",), {"https://example.com/page": http_error})
    with pytest.raises(OpenWebFetchError, match="HTTP_STATUS_429"):
        limited.fetch("https://example.com/page", robots_required=False)

    for resolver, expected in (
        (lambda _host: (), "DNS_RESOLUTION_EMPTY"),
        (lambda _host: ("127.0.0.1",), "URL_POLICY_BLOCKED"),
    ):
        fetcher = UrlFetcher(UrlPolicy(("example.com",)), resolver=resolver)
        with pytest.raises(OpenWebFetchError, match=expected):
            fetcher.fetch("https://example.com/page", robots_required=False)

    def broken_resolver(_host: str) -> tuple[str, ...]:
        raise OSError("dns down")

    fetcher = UrlFetcher(UrlPolicy(("example.com",)), resolver=broken_resolver)
    with pytest.raises(OpenWebFetchError, match="DNS_RESOLUTION_FAILED"):
        fetcher.fetch("https://example.com/page", robots_required=False)

    with pytest.raises(ValueError, match="open-web timeout"):
        UrlFetcher(UrlPolicy(("example.com",)), timeout_seconds=0.0)
    with pytest.raises(ValueError, match="open-web response"):
        UrlFetcher(UrlPolicy(("example.com",)), max_response_bytes=3_000_000)
    with pytest.raises(ValueError, match="open-web redirect"):
        UrlFetcher(UrlPolicy(("example.com",)), max_redirects=6)


def test_transport_default_response_cap_matches_the_safe_hard_ceiling() -> None:
    fetcher = UrlFetcher(UrlPolicy(("example.com",)))

    assert fetcher.max_response_bytes == 2_000_000


def test_source_policy_loading_is_strict_and_credentialless(tmp_path: Path) -> None:
    default_policy = load_open_web_policy()
    assert default_policy.network_mode == "ALLOWLISTED_PUBLIC_WEB"
    assert default_policy.cloud_llm_allowed is False
    assert "github.blog" in default_policy.allowed_hosts
    assert default_open_web_policy_path(tmp_path).parent.name == "research"

    raw = json.loads(
        Path("config/research/open_web_sources.json").read_text(encoding="utf-8")
    )
    raw["cloud_llm_allowed"] = True
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="external authority"):
        load_open_web_policy(bad_path)

    raw["cloud_llm_allowed"] = False
    raw["unexpected"] = True
    bad_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="keys mismatch"):
        load_open_web_policy(bad_path)

    with pytest.raises(ValueError, match="required"):
        _policy(enabled=False, required=True)
    with pytest.raises(ValueError, match="tier"):
        OpenWebSource(
            "bad",
            "https://github.blog/feed/",
            ("github.blog",),
            MissionName.TECHNOLOGY_DEVELOPMENT,
            SourceType.WEB_ARTICLE,
            "TIER_9",
            0.5,
            True,
            False,
            True,
            1,
        )


def test_technology_analyzer_is_deterministic_and_advisory_only() -> None:
    candidate = analyze_technology(
        _document(), evidence_id="evidence-1", source_reliability=0.9
    )
    assert candidate is not None
    assert candidate.recommendation is TechnologyRecommendation.RESEARCH_CANDIDATE
    assert candidate.execution_allowed is False
    assert candidate.installation_allowed is False
    assert "LIVE_ORDER_BLOCKED" in candidate.blockers
    assert candidate.affected_components
    assert (
        analyze_technology(
            _document(title="Cooking", text_excerpt="A recipe", headings=()),
            evidence_id="evidence-2",
            source_reliability=0.4,
        )
        is None
    )


def test_technology_analyzer_covers_deepsearch_research_criteria() -> None:
    cases = (
        (
            "New Binance WebSocket SBE protocol update",
            "Official exchange API endpoint with market data stream changes.",
            "protocol-exchange-api",
        ),
        (
            "Walk-forward validation benchmark",
            "Backtest simulation improves OOS time series split and slippage review.",
            "backtest-validation",
        ),
        (
            "Regime indicator strategy research",
            "New alpha pattern and momentum factor for strategy hypothesis review.",
            "strategy-signal-research",
        ),
        (
            "Risk control circuit breaker",
            "Drawdown, exposure, correlation, and kill switch controls.",
            "risk-control",
        ),
        (
            "Durable multi-agent workflow orchestrator",
            "Autonomous pipeline with retry budget, state machine, and audit trace.",
            "workflow-orchestrator-pipeline",
        ),
        (
            "Ontology knowledge graph for evidence",
            "Graph RAG with semantic entity resolution and provenance graph review.",
            "ontology-knowledge-graph",
        ),
    )

    for index, (title, excerpt, expected_area) in enumerate(cases, start=1):
        candidate = analyze_technology(
            _document(
                document_id=f"doc-{index}",
                title=title,
                text_excerpt=excerpt,
                headings=(),
            ),
            evidence_id=f"evidence-{index}",
            source_reliability=0.9,
        )

        assert candidate is not None
        assert candidate.technology_area == expected_area
        assert candidate.execution_allowed is False
        assert candidate.installation_allowed is False
        assert "LIVE_ORDER_BLOCKED" in candidate.blockers
        assert candidate.required_validation


def test_open_web_store_round_trip_and_corruption_detection(tmp_path: Path) -> None:
    document = _document()
    observation = ExternalObservation(
        observation_id="obs-1",
        provider_id="source",
        source_type=SourceType.WEB_ARTICLE,
        source_uri=document.canonical_uri,
        canonical_uri=document.canonical_uri,
        title=document.title,
        content_sha256=document.content_sha256,
        retrieved_at=NOW,
        author_or_origin="GitHub",
        language="en",
        summary="summary",
        raw_reference=document.canonical_uri,
        source_credibility=0.8,
        retrieval_confidence=0.9,
        data_quality_status=RetrievalStatus.VALID,
    )
    evidence = ExternalEvidence(
        evidence_id="evidence-1",
        source_type=SourceType.WEB_ARTICLE,
        source_uri=document.canonical_uri,
        observed_at=NOW,
        content_sha256=document.content_sha256,
        citation=document.canonical_uri,
        author_or_origin="GitHub",
        reliability=0.8,
        raw_excerpt="Agent security evidence",
    )
    store = OpenWebEvidenceStore(tmp_path / "evidence.jsonl")
    assert store.get(document.canonical_uri) is None
    store.append(CachedWebRecord(observation, document, evidence))
    cached = store.get(document.canonical_uri)
    assert cached is not None
    assert cached.document == document
    assert cached.observation == observation
    assert cached.evidence == evidence
    assert store.get("https://github.blog/missing/") is None

    corrupt = OpenWebEvidenceStore(tmp_path / "corrupt.jsonl")
    corrupt.path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        corrupt.get(document.canonical_uri)


def test_open_web_engine_runs_end_to_end_and_reuses_cache(tmp_path: Path) -> None:
    policy = _policy()
    fetcher, _ = _fetcher(policy.allowed_hosts, _engine_responses())
    engine = OpenWebRadarEngine(
        policy,
        fetcher,
        OpenWebEvidenceStore(tmp_path / "open-web.jsonl"),
    )
    report = engine.scan(
        run_id="run-1",
        observed_at=NOW,
        mission=MissionName.TECHNOLOGY_DEVELOPMENT,
        seed_urls=("https://github.com/openai/example",),
    )
    assert report.status is ProviderOperationalState.AVAILABLE
    assert report.fetch_count == 2
    assert (
        len(report.observations) == len(report.documents) == len(report.evidence) == 1
    )
    assert (
        len(report.claims)
        == len(report.findings)
        == len(report.technology_candidates)
        == 1
    )
    assert "BUY" in report.documents[0].text_excerpt
    assert "BUY" not in report.evidence[0].raw_excerpt
    assert report.model_inference_used is False
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "ROUTE_TO_EXISTING_GITHUB_RADAR" in report.blockers
    assert report.evidence_graph.nodes
    assert report.evidence_graph.edges

    cached = engine.scan(
        run_id="run-2",
        observed_at=NOW,
        mission=MissionName.TECHNOLOGY_DEVELOPMENT,
    )
    assert cached.cache_hits == 1
    assert cached.fetch_count == 1
    assert cached.documents == report.documents

    payload = open_web_payload(
        engine=engine,
        evidence_path=tmp_path / "ignored.jsonl",
    )
    assert payload["status"] == "READY"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    serialized = payload["report"]
    assert isinstance(serialized, dict)
    topics = serialized["research_topics"]
    assessments = serialized["research_assessments"]
    assert isinstance(topics, tuple)
    assert isinstance(assessments, tuple)
    assert len(topics) == 14
    assessment = assessments[0]
    assert isinstance(assessment, dict)
    assert assessment["recommended_action"] in {
        "IGNORE",
        "WATCH",
        "RESEARCH",
        "PROTOTYPE",
        "VALIDATE",
        "ADOPT_CANDIDATE",
        "REJECT",
    }
    assert assessment["execution_allowed"] is False
    assert assessment["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_open_web_engine_degrades_when_sources_or_inputs_fail(tmp_path: Path) -> None:
    policy = _policy()
    failed_fetcher, _ = _fetcher(
        policy.allowed_hosts,
        {
            "https://github.blog/robots.txt": URLError("offline"),
        },
    )
    report = OpenWebRadarEngine(policy, failed_fetcher).scan(
        run_id="failed",
        observed_at=NOW,
        mission=MissionName.TECHNOLOGY_DEVELOPMENT,
        seed_urls=("http://github.blog/unsafe",),
    )
    assert report.status is ProviderOperationalState.UNAVAILABLE
    assert "DATA_UNAVAILABLE" in report.blockers
    assert "URL_POLICY_BLOCKED" in report.blockers
    assert any(
        item.startswith("REQUIRED_SOURCE_UNAVAILABLE") for item in report.blockers
    )

    disabled = _policy(enabled=False, required=False)
    empty_fetcher, _ = _fetcher(disabled.allowed_hosts, {})
    disabled_report = OpenWebRadarEngine(disabled, empty_fetcher).scan(
        run_id="disabled",
        observed_at=NOW,
        mission=MissionName.TECHNOLOGY_DEVELOPMENT,
    )
    assert disabled_report.provider_states == (
        ("github_changelog", ProviderOperationalState.SOURCE_NOT_REQUIRED),
    )

    with pytest.raises(ValueError, match="hosts must match"):
        OpenWebRadarEngine(policy, UrlFetcher(UrlPolicy(("github.blog",))))
    with pytest.raises(ValueError, match="timestamp"):
        OpenWebRunReport(
            "run",
            datetime(2026, 8, 9),
            MissionName.TECHNOLOGY_DEVELOPMENT,
            ProviderOperationalState.UNAVAILABLE,
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            report.evidence_graph,
            (),
            0,
            0,
        )

    missing = open_web_payload(policy_path=tmp_path / "missing.json")
    assert missing["status"] == "DEGRADED"
    assert missing["report"] is None
    assert missing["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

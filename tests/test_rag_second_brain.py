"""Local second-brain RAG and advisory runner tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import Request

import pytest

from ai4binance.agents.context_budget import TokenBudget, TokenBudgetGuard
from ai4binance.rag import (
    AdvisoryProviderGuard,
    ContextEngineeringReadinessEvidence,
    ContextEngineeringReadinessReview,
    ContextEngineeringReadinessStatus,
    ContextSourceEvidence,
    LlamaCppAdvisoryRunner,
    LocalRagIndexer,
    OllamaAdvisoryRunner,
    RagEvidenceQualityReview,
    RagEvidenceQualityStatus,
    RagFragment,
    RagIndex,
    SecondBrainPilotAdmission,
    SecondBrainPilotPolicy,
    assess_second_brain_pilot,
    render_rag_ui,
    review_context_engineering_readiness,
    review_rag_evidence_quality,
)

NOW = datetime(2026, 7, 19, tzinfo=UTC)
HASH = "a" * 64


def context_source(
    source_uri: str = "Artifacts/context/market-outlook.json",
    *,
    collected_at: datetime = NOW,
    citations: tuple[str, ...] = ("artifact://market-outlook",),
    token_count: int = 120,
    redacted: bool = True,
    private_path_detected: bool = False,
    secret_marker_detected: bool = False,
) -> ContextSourceEvidence:
    return ContextSourceEvidence(
        source_uri=source_uri,
        content_sha256=HASH,
        collected_at=collected_at,
        token_count=token_count,
        citations=citations,
        redacted=redacted,
        private_path_detected=private_path_detected,
        secret_marker_detected=secret_marker_detected,
    )


def test_local_rag_index_builds_hash_verified_hits_and_ui(tmp_path: Path) -> None:
    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "btc.md").write_text(
        "BTCUSDT validation backtest opportunity remains RESEARCH_ONLY.\n",
        encoding="utf-8",
    )
    secrets = tmp_path / "Logs"
    secrets.mkdir()
    (secrets / "unsafe.json").write_text(
        '{"api_key":"secret","text":"BTCUSDT"}\n',
        encoding="utf-8",
    )

    index = LocalRagIndexer(tmp_path).build(now=NOW)
    hits = index.query("BTCUSDT opportunity validation")
    output = tmp_path / "State" / "second-brain-index.json"
    index.write(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    ui = render_rag_ui(index, hits)

    assert index.execution_allowed is False
    assert index.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert payload["fragments"][0]["source_uri"] == "Docs/btc.md"
    assert hits[0].source_uri == "Docs/btc.md"
    assert hits[0].collected_at == NOW
    assert hits[0].authority == "READ_ONLY"
    assert hits[0].classification == "PUBLIC_RESEARCH"
    assert "unsafe" not in {fragment.source_uri for fragment in index.fragments}
    assert "AI4BINANCE Second Brain" in ui


def test_rag_query_filters_metadata_and_quality_accepts_cited_hits() -> None:
    matching = RagFragment(
        "fragment:read",
        "Docs/read.md",
        HASH,
        NOW,
        "BTCUSDT opportunity validation context",
        (("btcusdt", 1), ("opportunity", 1), ("validation", 1)),
        authority="READ_ONLY",
        classification="PUBLIC_RESEARCH",
    )
    filtered = RagFragment(
        "fragment:write",
        "Docs/write.md",
        "b" * 64,
        NOW,
        "BTCUSDT opportunity validation context",
        (("btcusdt", 1), ("opportunity", 1), ("validation", 1)),
        authority="WRITE",
        classification="PRIVATE",
    )
    index = RagIndex("rag:metadata", NOW, (matching, filtered))

    hits = index.query(
        "BTCUSDT opportunity validation",
        authorities=("READ_ONLY",),
        classifications=("PUBLIC_RESEARCH",),
    )
    review = review_rag_evidence_quality(
        query_id="q:metadata",
        hits=hits,
        citations=("Docs/read.md",),
        now=NOW,
    )

    assert tuple(hit.fragment_id for hit in hits) == ("fragment:read",)
    assert review.status is RagEvidenceQualityStatus.RESEARCH_ONLY_RAG_EVIDENCE
    assert review.accepted_hit_ids == ("fragment:read",)
    assert review.rejected_hit_ids == ()
    assert review.citation_coverage == 1.0
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.execution_allowed is False


def test_rag_evidence_quality_watchlists_stale_private_uncited_hits(
    tmp_path: Path,
) -> None:
    state = tmp_path / "State"
    state.mkdir()
    (state / "context.md").write_text(
        "BTCUSDT opportunity validation context remains advisory only.\n",
        encoding="utf-8",
    )
    index = LocalRagIndexer(tmp_path, allowed_roots=("State",)).build(
        now=NOW - timedelta(days=30)
    )

    review = review_rag_evidence_quality(
        query_id="q:unsafe",
        hits=index.query("BTCUSDT opportunity validation"),
        citations=(),
        now=NOW,
    )

    assert review.status is RagEvidenceQualityStatus.WATCHLIST
    assert "RAG_CITATION_REQUIRED" in review.blockers
    assert "RAG_CITATION_COVERAGE_INSUFFICIENT" in review.blockers
    assert "RAG_SOURCE_STALE" in review.blockers
    assert "RAG_PRIVATE_PATH_BLOCKED" in review.blockers
    assert "RAG_EVIDENCE_QUALITY_BLOCKED" in review.blockers
    assert review.accepted_hit_ids == ()
    assert review.rejected_hit_ids
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_second_brain_pilot_admits_cited_public_sources_only(
    tmp_path: Path,
) -> None:
    (tmp_path / "Computer.md").write_text(
        "Device: LOCAL-DEVICE-ALPHA\nGPU: PRIVATEGPU123\n",
        encoding="utf-8",
    )
    docs = tmp_path / "Docs"
    docs.mkdir()
    source = docs / "x-idea.md"
    source.write_text(
        "External X idea is summarized as RESEARCH_ONLY opportunity context.\n",
        encoding="utf-8",
    )

    admission = assess_second_brain_pilot(
        tmp_path,
        (source,),
        citations=("https://x.com/example/status/1",),
    )

    assert admission.status == "PASSED"
    assert admission.blockers == ()
    assert admission.raw_root == "Artifacts/second-brain/raw"
    assert admission.wiki_root == "Artifacts/second-brain/wiki"
    assert admission.sources[0].source_uri == "Docs/x-idea.md"
    assert admission.sources[0].accepted is True
    assert admission.execution_allowed is False
    assert admission.promotion_status == "RESEARCH_ONLY"
    assert admission.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_second_brain_pilot_blocks_secret_private_paths_and_missing_citations(
    tmp_path: Path,
) -> None:
    (tmp_path / "Computer.md").write_text(
        "Device: LOCAL-DEVICE-ALPHA\n",
        encoding="utf-8",
    )
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    source = secrets / "bnc.env"
    source.write_text(
        "BINANCE_API_KEY=secret-value\n",
        encoding="utf-8",
    )

    admission = assess_second_brain_pilot(tmp_path, (source,))

    assert admission.status == "BLOCKED"
    assert admission.sources[0].accepted is False
    assert "SECOND_BRAIN_PRIVATE_PATH_BLOCKED" in admission.sources[0].blockers
    assert "SECOND_BRAIN_SUFFIX_BLOCKED" in admission.sources[0].blockers
    assert "SECOND_BRAIN_CITATION_REQUIRED" in admission.sources[0].blockers
    assert "SECOND_BRAIN_SECRET_MARKER_BLOCKED" in admission.sources[0].blockers
    assert "secret-value" not in repr(admission)


def test_second_brain_pilot_blocks_computer_profile_leak_without_raw_token(
    tmp_path: Path,
) -> None:
    profile_marker = "LOCAL-DEVICE-ALPHA"
    (tmp_path / "Computer.md").write_text(
        f"Device: {profile_marker}\n",
        encoding="utf-8",
    )
    docs = tmp_path / "Docs"
    docs.mkdir()
    source = docs / "leaky.md"
    source.write_text(
        f"Do not put {profile_marker} in the wiki.\n",
        encoding="utf-8",
    )

    admission = assess_second_brain_pilot(
        tmp_path,
        (source,),
        citations=("artifact://local-test",),
    )

    assert admission.status == "BLOCKED"
    assert admission.sources[0].blockers == (
        "SECOND_BRAIN_COMPUTER_PROFILE_TOKEN_BLOCKED",
    )
    assert profile_marker not in repr(admission)


def test_second_brain_pilot_fails_closed_without_profile_or_sources(
    tmp_path: Path,
) -> None:
    admission = assess_second_brain_pilot(tmp_path, ())

    assert admission.status == "BLOCKED"
    assert admission.sources == ()
    assert admission.blockers == (
        "SECOND_BRAIN_COMPUTER_MD_NOT_FOUND",
        "SECOND_BRAIN_SOURCE_REQUIRED",
    )


def test_context_engineering_readiness_accepts_cited_redacted_context() -> None:
    review = review_context_engineering_readiness(
        ContextEngineeringReadinessEvidence(
            context_pack_id="context:hotusdt-market-outlook",
            task_id="advisory-market-outlook",
            sources=(context_source(),),
            prompt_sections=("system_scope", "task", "evidence", "blockers"),
            retrieval_strategy="just-in-time",
            max_context_tokens=2_000,
            output_reserve_tokens=400,
            instruction_tokens=180,
            history_tokens=20,
            tool_schema_tokens=40,
        ),
        now=NOW,
    )

    assert (
        review.status is ContextEngineeringReadinessStatus.RESEARCH_ONLY_CONTEXT_PATTERN
    )
    assert review.promotion_status == "RESEARCH_ONLY_CONTEXT_PATTERN"
    assert review.blockers == ("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED")
    assert review.citation_count == 1
    assert review.used_tokens == 360
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_context_engineering_readiness_watchlists_unsafe_or_stale_context() -> None:
    review = review_context_engineering_readiness(
        ContextEngineeringReadinessEvidence(
            context_pack_id="context:unsafe",
            task_id="advisory-market-outlook",
            sources=(
                context_source(
                    "Secrets/binance.env",
                    collected_at=datetime(2026, 6, 1, tzinfo=UTC),
                    citations=(),
                    redacted=False,
                    private_path_detected=True,
                    secret_marker_detected=True,
                ),
            ),
            prompt_sections=("system_scope",),
            retrieval_strategy="preload-everything",
            max_context_tokens=300,
            output_reserve_tokens=150,
            instruction_tokens=120,
            history_tokens=80,
            tool_schema_tokens=60,
            privacy_scan_passed=False,
        ),
        now=NOW,
    )

    assert review.status is ContextEngineeringReadinessStatus.WATCHLIST
    assert "CONTEXT_RETRIEVAL_STRATEGY_REVIEW_REQUIRED" in review.blockers
    assert "CONTEXT_TOKEN_BUDGET_EXCEEDED" in review.blockers
    assert "CONTEXT_PRIVACY_SCAN_REQUIRED" in review.blockers
    assert "CONTEXT_CITATION_REQUIRED" in review.blockers
    assert "CONTEXT_REDACTION_REQUIRED" in review.blockers
    assert "CONTEXT_PRIVATE_PATH_BLOCKED" in review.blockers
    assert "CONTEXT_SECRET_MARKER_BLOCKED" in review.blockers
    assert "CONTEXT_SOURCE_STALE" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_rag_contracts_reject_restricted_or_authorized_shapes() -> None:
    with pytest.raises(ValueError, match="restricted"):
        RagFragment(
            "fragment:1",
            "Docs/a.md",
            HASH,
            NOW,
            "api_key is not allowed",
            (("btc", 1),),
        )
    with pytest.raises(ValueError, match="execution"):
        RagFragment(
            "fragment:1",
            "Docs/a.md",
            HASH,
            NOW,
            "safe text",
            (("btc", 1),),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="score"):
        review_rag_evidence_quality(
            query_id="q:bad-threshold",
            hits=(),
            citations=(),
            now=NOW,
            minimum_score=2.0,
        )
    with pytest.raises(ValueError, match="human review"):
        RagEvidenceQualityReview(
            query_id="q:review",
            status=RagEvidenceQualityStatus.RESEARCH_ONLY_RAG_EVIDENCE,
            blockers=("LIVE_ORDER_BLOCKED",),
            accepted_hit_ids=("fragment:ok",),
            rejected_hit_ids=(),
            source_uris=("Docs/a.md",),
            source_sha256=(HASH,),
            citation_coverage=1.0,
            minimum_score=0.35,
            minimum_citation_coverage=1.0,
        )
    with pytest.raises(ValueError, match="repository-relative"):
        SecondBrainPilotPolicy(workspace_root="C:/outside")
    with pytest.raises(ValueError, match="promote or execute"):
        SecondBrainPilotPolicy(execution_allowed=True)
    with pytest.raises(ValueError, match="research-only"):
        SecondBrainPilotAdmission(
            "PASSED",
            "Artifacts/second-brain",
            "Artifacts/second-brain/raw",
            "Artifacts/second-brain/wiki",
            "Artifacts/second-brain/log.md",
            "Artifacts/second-brain/CLAUDE.md",
            (),
            (),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="context source identity"):
        context_source(source_uri="C:/outside/context.md")
    with pytest.raises(ValueError, match="timezone-aware"):
        context_source(collected_at=datetime(2026, 7, 19))
    with pytest.raises(ValueError, match="token count"):
        context_source(token_count=0)
    with pytest.raises(ValueError, match="citations"):
        context_source(citations=("same", "same"))
    with pytest.raises(ValueError, match="cannot authorize"):
        ContextSourceEvidence(
            source_uri="Artifacts/context/a.md",
            content_sha256=HASH,
            collected_at=NOW,
            token_count=1,
            citations=("artifact://a",),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="identity"):
        ContextEngineeringReadinessEvidence(
            context_pack_id="",
            task_id="task",
            sources=(),
            prompt_sections=("system",),
            retrieval_strategy="just-in-time",
            max_context_tokens=100,
            output_reserve_tokens=10,
            instruction_tokens=1,
        )
    with pytest.raises(ValueError, match="source URIs"):
        ContextEngineeringReadinessEvidence(
            context_pack_id="context:dup",
            task_id="task",
            sources=(context_source(), context_source()),
            prompt_sections=("system",),
            retrieval_strategy="just-in-time",
            max_context_tokens=100,
            output_reserve_tokens=10,
            instruction_tokens=1,
        )
    with pytest.raises(ValueError, match="output reserve"):
        ContextEngineeringReadinessEvidence(
            context_pack_id="context:bad-budget",
            task_id="task",
            sources=(),
            prompt_sections=("system",),
            retrieval_strategy="just-in-time",
            max_context_tokens=100,
            output_reserve_tokens=100,
            instruction_tokens=1,
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        ContextEngineeringReadinessEvidence(
            context_pack_id="context:authority",
            task_id="task",
            sources=(),
            prompt_sections=("system",),
            retrieval_strategy="just-in-time",
            max_context_tokens=100,
            output_reserve_tokens=10,
            instruction_tokens=1,
            llm_signal_authority=True,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        review_context_engineering_readiness(
            ContextEngineeringReadinessEvidence(
                context_pack_id="context:time",
                task_id="task",
                sources=(),
                prompt_sections=("system",),
                retrieval_strategy="just-in-time",
                max_context_tokens=100,
                output_reserve_tokens=10,
                instruction_tokens=1,
            ),
            now=datetime(2026, 7, 19),
        )
    with pytest.raises(ValueError, match="human review"):
        ContextEngineeringReadinessReview(
            context_pack_id="context:review",
            task_id="task",
            status=ContextEngineeringReadinessStatus.RESEARCH_ONLY_CONTEXT_PATTERN,
            blockers=("LIVE_ORDER_BLOCKED",),
            source_uris=("Artifacts/context/a.md",),
            source_sha256=(HASH,),
            citation_count=1,
            used_tokens=1,
            max_context_tokens=100,
            output_reserve_tokens=10,
        )
    with pytest.raises(ValueError, match="cannot promote"):
        ContextEngineeringReadinessReview(
            context_pack_id="context:review",
            task_id="task",
            status=ContextEngineeringReadinessStatus.RESEARCH_ONLY_CONTEXT_PATTERN,
            blockers=("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"),
            source_uris=("Artifacts/context/a.md",),
            source_sha256=(HASH,),
            citation_count=1,
            used_tokens=1,
            max_context_tokens=100,
            output_reserve_tokens=10,
            execution_allowed=True,
        )


def test_llama_runner_is_loopback_only_and_fails_closed_when_unavailable() -> None:
    with pytest.raises(ValueError, match="loopback"):
        LlamaCppAdvisoryRunner("http://example.com").run("prompt", ())

    result = LlamaCppAdvisoryRunner(
        "http://127.0.0.1:9",
        timeout_seconds=0.01,
    ).run("prompt", ())

    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "LOCAL_LLM_PROVIDER_UNAVAILABLE" in result.blockers


def test_advisory_provider_guard_bounds_prompt_timeout_and_response_size() -> None:
    guard = AdvisoryProviderGuard(max_prompt_chars=8, max_response_bytes=2_048)
    guard.validate_request("prompt", 1.0)
    budgeted_guard = AdvisoryProviderGuard(
        max_prompt_chars=128,
        token_budget_guard=TokenBudgetGuard(
            TokenBudget(context_window=12, max_current_input=2, output_reserve=10)
        ),
    )
    with pytest.raises(ValueError, match=r"INPUT|CONTEXT_WINDOW"):
        budgeted_guard.validate_request("prompt cannot fit budget", 1.0)
    with pytest.raises(ValueError, match="context"):
        guard.validate_request("too long prompt", 1.0)
    with pytest.raises(ValueError, match="timeout"):
        guard.validate_request("prompt", 1_000.0)
    with pytest.raises(ValueError, match="prompt"):
        LlamaCppAdvisoryRunner(
            "http://127.0.0.1:9",
            guard=guard,
        ).run("too long prompt", ())
    with pytest.raises(ValueError, match="prompt limit"):
        AdvisoryProviderGuard(max_prompt_chars=0)
    with pytest.raises(ValueError, match="response limit"):
        AdvisoryProviderGuard(max_response_bytes=1)
    with pytest.raises(ValueError, match="timeout range"):
        AdvisoryProviderGuard(minimum_timeout_seconds=2.0, maximum_timeout_seconds=1.0)


class ResponseStub:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> ResponseStub:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, limit: int) -> bytes:
        del limit
        return self.payload


def test_ollama_runner_is_loopback_only_and_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaAdvisoryRunner("http://example.com").run("prompt", ())

    def fake_urlopen(request: Request, timeout: float) -> ResponseStub:
        assert request.full_url == "http://127.0.0.1:11434/api/generate"
        assert timeout == 3.0
        return ResponseStub(b'{"response":"Research only summary."}')

    monkeypatch.setattr("ai4binance.rag.urllib.request.urlopen", fake_urlopen)
    result = OllamaAdvisoryRunner(timeout_seconds=3.0).run("prompt", ())

    assert result.provider == "ollama"
    assert result.response_text == "Research only summary."
    assert result.blockers == ("ADVISORY_ONLY",)
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"

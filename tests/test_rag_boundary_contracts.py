"""Advisory retrieval rejects invalid provenance, authority, and resource limits."""

import io
import json
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai4binance import rag as r
from ai4binance.governance.model_registry import ModelGateway
from ai4binance.multiops.llmops.contracts import TaskClass, TaskCriticality

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def contracts() -> dict[str, Any]:
    policy = r.SecondBrainPilotPolicy()
    source = r.SecondBrainSourceAdmission("docs/a.md", "citation", "a" * 64, True, ())
    admission = r.SecondBrainPilotAdmission(
        "PASSED",
        policy.workspace_root,
        policy.raw_root,
        policy.wiki_root,
        policy.log_path,
        policy.instructions_path,
        (source,),
        (),
    )
    context_source = r.ContextSourceEvidence(
        "docs/a.md", "a" * 64, NOW, 20, ("docs/a.md",)
    )
    context = r.ContextEngineeringReadinessEvidence(
        "context:test",
        "task:test",
        (context_source,),
        ("system_scope", "task", "evidence", "blockers"),
        "just-in-time",
        2000,
        400,
        100,
    )
    context_review = r.review_context_engineering_readiness(context, now=NOW)
    fragment = r.RagFragment(
        "fragment:test",
        "docs/a.md",
        "a" * 64,
        NOW,
        "research evidence",
        (("research", 1),),
    )
    hit = r.RagSearchHit(
        "fragment:test", "docs/a.md", 0.9, "research evidence", "a" * 64, NOW
    )
    quality = r.review_rag_evidence_quality(
        query_id="query:test", hits=(hit,), citations=(hit.source_uri,), now=NOW
    )
    request = r.RetrievalRequest(
        "query:test",
        "research",
        "second_brain_query",
        TaskClass.MODERATE,
        TaskCriticality.MEDIUM,
        r.RagAuthorityCeiling.ADVISORY_ONLY,
        ("docs",),
        ("READ_ONLY",),
        ("PUBLIC_RESEARCH",),
    )
    evaluation = r.evaluate_governed_retrieval(
        request, hits=(hit,), citations=(hit.source_uri,), now=NOW
    )
    governed_source = evaluation.source_evidence[0]
    injection = evaluation.injection_assessment
    index = r.RagIndex("rag:test", NOW, (fragment,))
    guard = r.AdvisoryProviderGuard()
    provenance = r.Provenance("docs/a.md", "a" * 64, "1")
    trust = r.TrustScore(0.9)
    return locals()


@pytest.mark.parametrize(
    ("name", "field", "value", "message"),
    [
        ("policy", "allowed_suffixes", (), "suffixes"),
        ("policy", "blocked_path_parts", (), "blocked path"),
        ("policy", "maximum_source_bytes", 0, "byte limit"),
        ("policy", "execution_allowed", True, "cannot promote"),
        ("policy", "live_eligibility_status", "LIVE", "live trading blocked"),
        ("source", "source_uri", " ", "repository-relative"),
        ("source", "content_sha256", "bad", "hash"),
        ("source", "blockers", ("GAP",), "cannot have blockers"),
        ("source", "accepted", False, "require blockers"),
        ("admission", "execution_allowed", True, "research-only"),
        ("admission", "status", "UNKNOWN", "status"),
        ("admission", "sources", (), "source evidence"),
        ("admission", "blockers", ("GAP",), "cannot have blockers"),
        ("admission", "status", "BLOCKED", "requires blockers"),
        ("context", "context_pack_id", " ", "identity"),
        ("context", "max_context_tokens", 1, "budgets"),
        ("context", "output_reserve_tokens", 2000, "reserve"),
        ("context", "execution_allowed", True, "authority"),
        ("context_review", "context_pack_id", " ", "identity"),
        ("context_review", "source_sha256", ("bad",), "hash"),
        ("context_review", "citation_count", -1, "citation count"),
        ("context_review", "used_tokens", -1, "budgets"),
        ("context_review", "blockers", ("LIVE_ORDER_BLOCKED",), "human review"),
        ("context_review", "blockers", ("HUMAN_REVIEW_REQUIRED",), "live blocker"),
        ("context_review", "execution_allowed", True, "cannot promote"),
        ("fragment", "fragment_id", " ", "identity"),
        ("fragment", "collected_at", datetime(2026, 1, 1), "timezone"),
        ("fragment", "execution_allowed", True, "execution"),
        ("fragment", "classification", " ", "classification"),
        ("fragment", "source_of_truth_scope", (" ",), "non-empty"),
        ("fragment", "source_of_truth_scope", ("same", "same"), "unique"),
        ("hit", "fragment_id", " ", "identity"),
        ("hit", "score", float("nan"), "finite"),
        ("hit", "excerpt", " ", "empty"),
        ("hit", "collected_at", datetime(2026, 1, 1), "timezone"),
        ("hit", "authority", " ", "metadata"),
        ("quality", "query_id", " ", "query id"),
        ("quality", "source_sha256", ("bad",), "hash"),
        ("quality", "citation_coverage", -1, "thresholds"),
        ("quality", "blockers", ("LIVE_ORDER_BLOCKED",), "human review"),
        ("quality", "blockers", ("HUMAN_REVIEW_REQUIRED",), "live blocker"),
        ("quality", "execution_allowed", True, "cannot promote"),
        ("request", "query_id", " ", "identity"),
        ("request", "minimum_score", -1, "score"),
        ("request", "minimum_citation_coverage", 2, "citation"),
        ("request", "max_source_age_days", 0, "age limit"),
        ("request", "execution_allowed", True, "execution"),
        ("governed_source", "fragment_id", " ", "identity"),
        ("governed_source", "content_sha256", "bad", "hash"),
        ("governed_source", "provenance_ref", " ", "provenance"),
        ("governed_source", "collected_at", datetime(2026, 1, 1), "timezone"),
        ("governed_source", "score", -1, "score"),
        ("governed_source", "blockers", ("GAP",), "cannot have blockers"),
        ("governed_source", "execution_allowed", True, "execution"),
        ("injection", "query_id", " ", "query id"),
        ("injection", "blockers", ("GAP",), "clear RAG"),
        (
            "injection",
            "status",
            r.RagInjectionAssessmentStatus.BLOCKED,
            "requires blockers",
        ),
        ("injection", "execution_allowed", True, "execution"),
        ("evaluation", "query_id", " ", "identity"),
        ("evaluation", "ragops_domain", "UNKNOWN", "RAGOPS"),
        ("evaluation", "final_authority", "EXECUTION", "NONE"),
        ("evaluation", "citation_coverage", 2, "coverage"),
        ("evaluation", "execution_allowed", True, "execution"),
        (
            "evaluation",
            "advisory_fusion_status",
            r.AdvisoryFusionStatus.READY,
            "allowance",
        ),
        ("provenance", "source_reference", " ", "reference"),
        ("provenance", "content_hash", "bad", "hash"),
        ("provenance", "parser_version", " ", "blank"),
        ("trust", "value", 2, "between"),
        ("trust", "source_reference", " ", "blank"),
        ("trust", "metric", " ", "required"),
        ("index", "index_id", "bad", "identity"),
        ("index", "created_at", datetime(2026, 1, 1), "timezone"),
        ("index", "execution_allowed", True, "execution"),
        ("guard", "maximum_timeout_seconds", 0, "timeout"),
    ],
)
def test_rag_contract_rejects_invalid_field(
    contracts: dict[str, Any], name: str, field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(contracts[name], **{field: value})


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    [
        ({"collected_at": NOW + timedelta(days=1)}, "RAG_SOURCE_FROM_FUTURE"),
        ({"score": 0.1}, "RAG_RETRIEVAL_SCORE_LOW"),
        ({"source_uri": "docs/api_key.md"}, "RAG_SECRET_MARKER_BLOCKED"),
        ({"authority": "EXECUTION"}, "RAG_AUTHORITY_NOT_READ_ONLY"),
        ({"classification": "PRIVATE"}, "RAG_CLASSIFICATION_BLOCKED"),
        ({"source_uri": "secrets/private.md"}, "RAG_PRIVATE_PATH_BLOCKED"),
    ],
)
def test_bad_retrieved_evidence_remains_blocked(
    contracts: dict[str, Any], overrides: dict[str, Any], blocker: str
) -> None:
    hit = replace(contracts["hit"], **overrides)
    quality = r.review_rag_evidence_quality(
        query_id="test", hits=(hit,), citations=(), now=NOW
    )
    assert blocker in quality.blockers
    assert quality.accepted_hit_ids == ()
    evaluated = r.evaluate_governed_retrieval(
        contracts["request"], hits=(hit,), citations=(), now=NOW
    )
    assert evaluated.execution_allowed is False
    assert blocker in evaluated.source_evidence[0].blockers


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"query_id": " "}, "query id"),
        ({"now": datetime(2026, 1, 1)}, "timezone"),
        ({"max_source_age_days": 0}, "age limit"),
        ({"minimum_score": 2}, "minimum score"),
        ({"minimum_citation_coverage": -1}, "citation threshold"),
    ],
)
def test_rag_quality_review_validates_inputs(
    overrides: dict[str, Any], message: str
) -> None:
    args: dict[str, Any] = {"query_id": "test", "hits": (), "citations": (), "now": NOW}
    with pytest.raises(ValueError, match=message):
        r.review_rag_evidence_quality(**(args | overrides))


def test_indexer_rejects_escapes_empty_sources_and_naive_time(
    tmp_path: Path, contracts: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="escapes repository"):
        r.LocalRagIndexer(tmp_path, allowed_roots=("../outside",)).build(now=NOW)
    with pytest.raises(ValueError, match="timezone"):
        r.LocalRagIndexer(tmp_path).build(now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="no approved"):
        r.LocalRagIndexer(tmp_path).build(now=NOW)
    assert not r.LocalRagIndexer(tmp_path)._accepts(
        tmp_path.parent / "other.md", tmp_path
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "empty.md").write_text(" ", encoding="utf-8")
    (docs / "good.md").write_text("Research evidence", encoding="utf-8")
    index = r.LocalRagIndexer(tmp_path, maximum_fragments=1).build(now=NOW)
    assert len(index.fragments) == 1
    assert index.query("unmatched") == ()
    with pytest.raises(ValueError, match="query is required"):
        index.query(" ")
    with pytest.raises(ValueError, match="limit"):
        index.query("research", limit=0)


@pytest.mark.parametrize(
    ("payload", "blocker"),
    [
        ({"content": "Local research summary"}, "ADVISORY_ONLY"),
        ([], "LOCAL_LLM_EMPTY_RESPONSE"),
        ({"content": " "}, "LOCAL_LLM_EMPTY_RESPONSE"),
        (None, "LOCAL_LLM_PROVIDER_UNAVAILABLE"),
    ],
)
def test_llama_provider_response_paths_are_offline(
    monkeypatch: pytest.MonkeyPatch, payload: object, blocker: str
) -> None:
    gateway = SimpleNamespace(
        admit_advisory=Mock(
            return_value=SimpleNamespace(allowed=True, blockers=(), route_decision=None)
        )
    )
    opener = (
        Mock(side_effect=OSError("offline"))
        if payload is None
        else Mock(return_value=io.BytesIO(json.dumps(payload).encode()))
    )
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    result = r.LlamaCppAdvisoryRunner(model_gateway=cast(ModelGateway, gateway)).run(
        "Summarize research.", ()
    )
    assert blocker in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    if isinstance(payload, dict) and payload.get("content", "").strip():
        assert result.response_text == payload["content"]

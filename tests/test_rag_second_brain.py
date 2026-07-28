"""Local second-brain RAG and advisory runner tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request

import pytest

from ai4binance.agents.context_budget import TokenBudget, TokenBudgetGuard
from ai4binance.rag import (
    AdvisoryProviderGuard,
    LlamaCppAdvisoryRunner,
    LocalRagIndexer,
    OllamaAdvisoryRunner,
    RagFragment,
    render_rag_ui,
)

NOW = datetime(2026, 7, 19, tzinfo=UTC)
HASH = "a" * 64


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
    assert "unsafe" not in {fragment.source_uri for fragment in index.fragments}
    assert "AI4BINANCE Second Brain" in ui


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

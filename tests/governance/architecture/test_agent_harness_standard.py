"""Draft agent harness standard preserves deterministic authority boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai4binance.governance import repository_validator

ROOT = Path(__file__).parents[3]
STANDARD_PATH = ROOT / "docs" / "standards" / "standard_agent_harness_engineering.md"


def _standard() -> tuple[dict[str, Any], str]:
    text = STANDARD_PATH.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", maxsplit=2)[1])
    assert isinstance(frontmatter, dict)
    return frontmatter, text


def test_agent_harness_standard_is_draft_without_authority_expansion() -> None:
    frontmatter, text = _standard()

    assert frontmatter["document_id"] == "AI4B-ARCH-STD-AGENT-HARNESS-001"
    assert frontmatter["status"] == "DRAFT"
    assert frontmatter["authority_scope"] == "agent_harness_engineering"
    assert frontmatter["authority_layer"] == (
        "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES"
    )
    assert frontmatter["source_of_truth"] is False
    assert frontmatter["machine_enforceable"] is False
    assert "execution_allowed=false" in text
    assert "RESEARCH_ONLY" in text
    assert "LIVE_ORDER_BLOCKED" in text


def test_agent_harness_standard_keeps_core_authorities_outside_agents() -> None:
    _frontmatter, text = _standard()

    required_fragments = (
        "It is not the deterministic trading core",
        "Do not embed the deterministic core inside LangGraph",
        (
            "Harness agents. Do not harness the deterministic core inside an "
            "agent framework."
        ),
        "Risk authority | Deterministic risk engine",
        "Validation authority | Deterministic validation engine",
        "Decision authority | Deterministic decision governance",
        "Execution eligibility | Governance and execution gates",
        "LLM unavailability MUST NOT break the deterministic core",
    )

    missing = [fragment for fragment in required_fragments if fragment not in text]

    assert missing == []


def test_agent_harness_standard_preserves_p0_fail_closed_invariants() -> None:
    _frontmatter, text = _standard()

    required_invariants = (
        "AGENT_CANNOT_EXECUTE_ORDERS",
        "AGENT_CANNOT_OVERRIDE_RISK",
        "AGENT_CANNOT_OVERRIDE_VALIDATION",
        "AGENT_CANNOT_OVERRIDE_GOVERNANCE",
        "AGENT_CANNOT_PROMOTE_STRATEGY",
        "AGENT_CANNOT_CHANGE_RISK_LIMITS",
        "AGENT_CANNOT_FETCH_UNGOVERNED_MARKET_DATA",
        "AGENT_MUST_USE_CANONICAL_SNAPSHOT",
        "AGENT_TOOL_CALLS_MUST_BE_AUDITED",
        "AGENT_OUTPUT_MUST_VALIDATE_AGAINST_CONTRACT",
        "AGENT_FAILURE_MUST_FAIL_SAFE",
        "LLM_FAILURE_MUST_NOT_BREAK_DETERMINISTIC_CORE",
        "SIDE_EFFECTING_TOOLS_MUST_REQUIRE_EXPLICIT_AUTHORITY",
        "DUPLICATE_TOOL_CALLS_MUST_NOT_CREATE_DUPLICATE_SIDE_EFFECTS",
    )

    missing = [invariant for invariant in required_invariants if invariant not in text]

    assert missing == []


def test_agent_harness_draft_does_not_require_document_lock_registration() -> None:
    frontmatter = repository_validator._frontmatter(STANDARD_PATH)
    assert frontmatter is not None
    knowledge = repository_validator._knowledge_object(
        "docs/standards/standard_agent_harness_engineering.md",
        frontmatter,
    )

    assert repository_validator._requires_governed_document_lock(knowledge) is False

"""Regression coverage for fail-closed authority-graph impact analysis."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.governance.authority import (
    AuthorityEdge,
    AuthorityEdgeFamily,
    AuthorityRelation,
    analyze_authority_impact,
    load_authority_graph,
)

SCHEMA_ROOT = Path(__file__).parents[3] / "schemas"


def test_authority_impact_is_governed_research_only_and_live_blocked() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    impact = analyze_authority_impact(graph, ("core",))

    assert impact.changed_node_ids == ("core",)
    assert impact.direct_impacted_node_ids == (
        "authority-layer-development-matrix",
        "claude-provider",
        "claude-root-adapter",
        "codex-provider",
        "compliance-matrix",
        "custom-instructions",
        "gemini-root-adapter",
        "repository-agent-instructions",
        "repository-file-governance",
        "repository-naming-standard",
        "technology-language-standard",
        "terminology-standard",
    )
    assert impact.transitive_impacted_node_ids == (
        "governance-enforcement-fabric",
        "technology-language-policy",
        "terminology-policy",
    )
    assert impact.change_class == "C3_GOVERNED"
    assert impact.promotion_status == "RESEARCH_ONLY"
    assert impact.execution_allowed is False
    assert impact.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert impact.required_sync_paths == tuple(sorted(impact.required_sync_paths))
    assert "tests/test_repository_validator.py" in impact.required_test_paths


def test_authority_impact_follows_specialization_from_parent_to_specialist() -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)
    nested_specialization = AuthorityEdge(
        edge_id="custom-instructions-specializes-codex-provider",
        from_node_id="custom-instructions",
        to_node_id="codex-provider",
        relation=AuthorityRelation.SPECIALIZES,
        edge_family=AuthorityEdgeFamily.AUTHORITY,
    )
    graph = replace(graph, edges=(*graph.edges, nested_specialization))

    impact = analyze_authority_impact(graph, ("repository-agent-instructions",))

    assert impact.direct_impacted_node_ids == (
        "claude-provider",
        "claude-root-adapter",
        "codex-provider",
        "gemini-root-adapter",
    )
    assert impact.transitive_impacted_node_ids == ("custom-instructions",)
    assert impact.required_sync_paths == (
        "CLAUDE.md",
        "GEMINI.md",
        "docs/governance/instruction_core_custom_instructions.md",
        "docs/providers/instruction_claude_provider.md",
        "docs/providers/instruction_codex_provider.md",
    )


@pytest.mark.parametrize(
    ("changed_node_ids", "error"),
    [
        ((), "requires changed nodes"),
        (("missing",), "contains unknown nodes"),
        (("core", "core"), "identifiers must be unique"),
    ],
)
def test_authority_impact_rejects_ambiguous_or_unknown_change_subjects(
    changed_node_ids: tuple[str, ...], error: str
) -> None:
    graph = load_authority_graph(schema_root=SCHEMA_ROOT)

    with pytest.raises(ValueError, match=error):
        analyze_authority_impact(graph, changed_node_ids)

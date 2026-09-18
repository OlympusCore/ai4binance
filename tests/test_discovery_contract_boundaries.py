"""Skill discovery rejects invalid evidence and implicit promotion."""

from dataclasses import replace
from datetime import datetime
from typing import Any

import pytest

from ai4binance.skills import (
    ContinuousSkillDiscoveryEngine,
    StaticCandidateScout,
    StaticDocumentationFetcher,
)
from ai4binance.skills.continuous_discovery import DocumentationReadPlan, SourceDocument
from tests.test_continuous_skill_discovery import NOW, candidate, documents


@pytest.fixture(scope="module")
def discovery_subjects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("discovery")
    engine = ContinuousSkillDiscoveryEngine(
        scout=StaticCandidateScout((candidate(),)),
        fetcher=StaticDocumentationFetcher({candidate().repository: documents()}),
        staging_directory=root / "staging",
        state_path=root / "state.json",
        ledger_path=root / "ledger.jsonl",
    )
    report = engine.run_once(
        queries=("agent workflow",), max_candidates=1, min_score=0.85, now=NOW
    )
    return {
        "candidate": candidate(),
        "plan": DocumentationReadPlan(candidate(), ("README.md",)),
        "filter": report.filter_decisions[0],
        "score": report.scores[0],
        "workflow": report.scores[0].workflow,
        "draft": report.drafts[0],
        "admission": report.admission_records[0],
        "review": report.stage_reviews[0],
        "cycle": report,
    }


@pytest.mark.parametrize(
    ("kind", "changes", "message"),
    [
        ("candidate", {"repository": "invalid"}, "owner/name"),
        ("candidate", {"pinned_revision": "bad revision!"}, "revision"),
        ("candidate", {"pushed_at": datetime(2026, 9, 1)}, "timezone-aware"),
        ("candidate", {"source_url": "http://example.com"}, "HTTPS"),
        ("candidate", {"topics": ("duplicate", "duplicate")}, "unique"),
        ("candidate", {"language": ""}, "text fields"),
        ("candidate", {"live_eligibility_status": "LIVE"}, "live blocked"),
        ("filter", {"reasons": ()}, "reason"),
        ("plan", {"max_bytes_per_file": 0}, "byte limit"),
        ("plan", {"paths": ("../secret",)}, "relative"),
        ("plan", {"paths": ("/absolute",)}, "relative"),
        ("workflow", {"skill_name": "BAD NAME"}, "skill name"),
        ("score", {"checks": ()}, "checks"),
        ("score", {"confidence": 1.1}, "confidence"),
        ("score", {"blockers": ("MISSING_EVIDENCE",)}, "passing score"),
        ("draft", {"skill_name": "BAD NAME"}, "skill name"),
        ("draft", {"review_rule": "AUTO"}, "human review"),
        ("admission", {"skill_name": "BAD NAME"}, "skill name"),
        ("admission", {"approval_marker": "wrong"}, "marker"),
        ("admission", {"review_rule": "AUTO"}, "human review"),
        (
            "admission",
            {"status": "READY_FOR_LIBRARY_PR", "approval_marker_present": False},
            "approval marker",
        ),
        ("review", {"input_sha256": "bad"}, "input hash"),
        ("review", {"output_sha256": "bad"}, "output hash"),
        ("review", {"citations": ()}, "citations"),
        ("review", {"blockers": ("UNSAFE",)}, "passed stage"),
        ("cycle", {"candidates_seen": -1}, "negative"),
        ("cycle", {"candidates_seen": 0}, "exceed"),
        ("cycle", {"drafts_created": 0}, "draft count"),
        ("cycle", {"workspace_component_reviews": ()}, "workspace component"),
    ],
)
def test_discovery_rejects_invalid_contracts(
    discovery_subjects: dict[str, Any], kind: str, changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(discovery_subjects[kind], **changes)


def test_discovery_rejects_duplicate_reviews(
    discovery_subjects: dict[str, Any],
) -> None:
    report = discovery_subjects["cycle"]
    with pytest.raises(ValueError, match="stage reviews must be unique"):
        replace(report, stage_reviews=report.stage_reviews * 2)
    with pytest.raises(ValueError, match="workspace component reviews must be unique"):
        replace(
            report,
            drafts_created=2,
            drafts=report.drafts * 2,
            workspace_component_reviews=report.workspace_component_reviews * 2,
        )
    with pytest.raises(ValueError, match="too large"):
        SourceDocument("README.md", "x" * 512001)

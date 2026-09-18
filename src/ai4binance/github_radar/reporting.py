"""Deterministic JSON reporting for the standalone Radar command."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ai4binance.external_intel.technology.research_intake import (
    assess_finding,
    research_topics_payload,
)
from ai4binance.github_radar.engine import RadarAssessment
from ai4binance.github_radar.models import DiscoveryCandidate, LocalCapabilityAssessment
from ai4binance.reporting import to_primitive


def baseline_payload(
    assessments: tuple[LocalCapabilityAssessment, ...],
) -> dict[str, object]:
    counts: dict[str, int] = {}
    for item in assessments:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return {
        "engine": "AI4BINANCE_GITHUB_RADAR_ENGINE",
        "mode": "LOCAL_BASELINE",
        "summary_counts": dict(sorted(counts.items())),
        "capability_count": len(assessments),
        "assessments": to_primitive(assessments),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def assessment_payload(assessment: RadarAssessment) -> dict[str, object]:
    return {
        "engine": "AI4BINANCE_GITHUB_RADAR_ENGINE",
        "mode": "REPOSITORY_CAPABILITY_EVALUATION",
        "evaluation": to_primitive(assessment.evaluation),
        "catalog_entry": to_primitive(assessment.catalog_entry),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def discovery_payload(
    candidates: tuple[DiscoveryCandidate, ...],
) -> dict[str, object]:
    return {
        "engine": "AI4BINANCE_GITHUB_RADAR_ENGINE",
        "mode": "GITHUB_DISCOVERY",
        "candidate_count": len(candidates),
        "research_topics": research_topics_payload(),
        "candidates": tuple(_discovery_candidate_payload(item) for item in candidates),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _discovery_candidate_payload(candidate: DiscoveryCandidate) -> dict[str, object]:
    """Project pinned GitHub evidence into conservative research triage fields."""
    payload = to_primitive(candidate)
    if not isinstance(payload, dict):
        raise TypeError("discovery candidate payload must be a mapping")
    license_known = candidate.source.license_id.upper() not in {
        "UNKNOWN",
        "NOASSERTION",
        "NONE",
    }
    assessment = assess_finding(
        finding_id=f"{candidate.source.repository}@{candidate.source.pinned_revision}:{candidate.capability_id}",
        text=f"{candidate.capability_id} {candidate.query}",
        evidence_strength=min(0.8, 0.3 + 0.1 * len(candidate.evidence)),
        source_authority=0.7 if license_known else 0.5,
        novelty_score=0.5,
        system_relevance=0.6,
        canonical_compatibility=0.5,
        expected_benefit=0.5,
        implementation_cost=0.6,
        security_risk=min(1.0, 0.25 + 0.1 * len(candidate.risks)),
        trading_risk=0.6 if "execution" in candidate.query.casefold() else 0.2,
    )
    payload["research_assessment"] = to_primitive(assessment)
    return payload


def write_json_atomic(path: Path, payload: object) -> None:
    """Write one report without leaving a partially-written destination."""
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_suffix(f"{resolved.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, resolved)

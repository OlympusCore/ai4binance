"""Compact advisory risk impact adapter for Decision Governance."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from ai4binance.external_intel.core.enums import DecisionImpact, VerificationStatus
from ai4binance.external_intel.core.models import (
    ExternalDecisionImpact,
    ExternalEvidence,
    ExternalFinding,
)
from ai4binance.intelligence.event_context import EventObservation


def to_compact_decision_payload(impact: ExternalDecisionImpact) -> dict[str, object]:
    return {
        "symbol": impact.symbol,
        "external_bias": impact.external_bias.value,
        "news_risk": impact.news_risk,
        "social_risk": impact.social_risk,
        "security_risk": impact.security_risk,
        "regulatory_risk": impact.regulatory_risk,
        "manipulation_risk": impact.manipulation_risk,
        "decision_impact": impact.decision_impact.value,
        "confidence": impact.confidence,
        "blockers": impact.blockers,
        "evidence_ids": impact.evidence_ids,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def to_event_observation(
    finding: ExternalFinding,
    evidence: tuple[ExternalEvidence, ...],
    *,
    published_at: datetime,
    first_seen_at: datetime,
    root_ids: tuple[str, ...],
    market_type: Literal["SPOT", "USD_M_FUTURES"],
) -> EventObservation:
    """Project verified EIEF lineage; caller supplies publication and original roots.

    A finding timestamp is not substituted for a missing publication timestamp.
    Original-source and duplicate resolution remain owned by EIEF.
    """
    by_id = {row.evidence_id: row for row in evidence}
    if len(by_id) != len(evidence):
        raise ValueError("event projection rejects duplicate evidence identities")
    if (
        not finding.symbol
        or not finding.evidence_ids
        or set(finding.evidence_ids) - by_id.keys()
    ):
        raise ValueError(
            "event projection requires symbol and every referenced evidence"
        )
    rows = tuple(by_id[key] for key in finding.evidence_ids)
    available_at = max(finding.observed_at, *(row.observed_at for row in rows))
    verification: Literal["VERIFIED", "UNVERIFIED", "CONFLICTING"] = "UNVERIFIED"
    if finding.verification_status is VerificationStatus.VERIFIED:
        verification = "VERIFIED"
    elif finding.verification_status is VerificationStatus.CONFLICTING:
        verification = "CONFLICTING"
    return EventObservation(
        observation_id=finding.finding_id,
        symbol=finding.symbol,
        market_type=market_type,
        source_refs=tuple(sorted({row.source_uri for row in rows})),
        root_ids=root_ids,
        published_at=published_at,
        first_seen_at=first_seen_at,
        available_at=available_at,
        window_start=published_at,
        window_end=finding.observed_at,
        verification=verification,
        source_quality=finding.source_credibility,
        event_severity="CRITICAL"
        if finding.decision_impact is DecisionImpact.CRITICAL_RISK
        else "UNKNOWN",
        narrative=finding.event_type,
        risk_review_required=finding.decision_impact
        in {
            DecisionImpact.RISK,
            DecisionImpact.CRITICAL_RISK,
            DecisionImpact.MANUAL_REVIEW_REQUIRED,
            DecisionImpact.NO_TRADE_RECOMMENDED,
        },
    )

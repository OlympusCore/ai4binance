"""Compact advisory risk impact adapter for Decision Governance."""

from __future__ import annotations

from ai4binance.external_intel.core.models import ExternalDecisionImpact


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

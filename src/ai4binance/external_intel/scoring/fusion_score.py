"""Cross-radar advisory fusion."""

from __future__ import annotations

from ai4binance.external_intel.core.enums import DecisionImpact, RadarName
from ai4binance.external_intel.core.models import ExternalFinding


def fused_confidence(findings: tuple[ExternalFinding, ...]) -> float:
    if not findings:
        return 0.0
    unique_radars = len({finding.radar for finding in findings})
    average_confidence = sum(finding.confidence for finding in findings) / len(findings)
    diversity_bonus = min(0.2, unique_radars * 0.04)
    manipulation_penalty = max(finding.manipulation_risk for finding in findings)
    return max(
        0.0,
        min(1.0, average_confidence + diversity_bonus - manipulation_penalty * 0.25),
    )


def fused_decision_impact(findings: tuple[ExternalFinding, ...]) -> DecisionImpact:
    if not findings:
        return DecisionImpact.DATA_UNAVAILABLE
    impacts = {finding.decision_impact for finding in findings}
    if DecisionImpact.CRITICAL_RISK in impacts:
        return DecisionImpact.CRITICAL_RISK
    if DecisionImpact.RISK in impacts:
        return DecisionImpact.RISK
    if DecisionImpact.CONFLICT in impacts:
        return DecisionImpact.CONFLICT
    if DecisionImpact.DATA_UNAVAILABLE in impacts and len(impacts) == 1:
        return DecisionImpact.DATA_UNAVAILABLE
    if _has_social_only_confirmation(findings):
        return DecisionImpact.LOW_CONFIDENCE
    if DecisionImpact.CONFIRM in impacts:
        return DecisionImpact.CONFIRM
    if DecisionImpact.WEAK_CONFIRM in impacts:
        return DecisionImpact.WEAK_CONFIRM
    return DecisionImpact.NEUTRAL


def _has_social_only_confirmation(findings: tuple[ExternalFinding, ...]) -> bool:
    social = {RadarName.X_RADAR, RadarName.REDDIT_RADAR, RadarName.TELEGRAM_RADAR}
    confirming = tuple(
        item
        for item in findings
        if item.decision_impact in {DecisionImpact.CONFIRM, DecisionImpact.WEAK_CONFIRM}
    )
    return bool(confirming) and all(item.radar in social for item in confirming)

"""Cross-radar verification and fusion engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    RadarName,
    VerificationStatus,
)
from ai4binance.external_intel.core.models import (
    ExternalDecisionImpact,
    ExternalFinding,
)
from ai4binance.external_intel.core.validation import require_aware
from ai4binance.external_intel.scoring.fusion_score import (
    fused_confidence,
    fused_decision_impact,
)

_MARKET_ADVISORY_MISSIONS = frozenset(
    {
        MissionName.BINANCE_OPPORTUNITY_NEWS,
        MissionName.MARKET_NARRATIVE,
        MissionName.REGULATORY_RISK,
        MissionName.SECURITY_RISK,
    }
)
_OPERATIONAL_RISK_IMPACTS = frozenset(
    {DecisionImpact.RISK, DecisionImpact.CRITICAL_RISK}
)
_FAIL_CLOSED_MARKET_IMPACTS = frozenset(
    {
        DecisionImpact.CONFLICT,
        DecisionImpact.CRITICAL_RISK,
        DecisionImpact.DATA_UNAVAILABLE,
        DecisionImpact.LOW_CONFIDENCE,
        DecisionImpact.MANUAL_REVIEW_REQUIRED,
        DecisionImpact.NO_TRADE_RECOMMENDED,
        DecisionImpact.RISK,
    }
)
_POSITIVE_MARKET_IMPACTS = frozenset(
    {
        DecisionImpact.CONFIRM,
        DecisionImpact.NEUTRAL,
        DecisionImpact.WEAK_CONFIRM,
    }
)


@dataclass(frozen=True, slots=True)
class FusionEngine:
    """Reduce market-lane findings while retaining cross-lane blockers."""

    def fuse(
        self,
        findings: tuple[ExternalFinding, ...],
        *,
        generated_at: datetime,
        symbol: str | None = None,
    ) -> ExternalDecisionImpact:
        require_aware("fusion generated_at", generated_at)
        scoped_findings = tuple(
            finding for finding in findings if _is_symbol_relevant(finding, symbol)
        )
        cross_symbol_findings = tuple(
            finding for finding in findings if not _is_symbol_relevant(finding, symbol)
        )
        (
            deduplicated_findings,
            identical_replay_detected,
            identity_conflict_detected,
        ) = _deduplicate_findings_by_identity(scoped_findings)
        identity_consistent_findings = (
            () if identity_conflict_detected else deduplicated_findings
        )
        run_ids = frozenset(finding.run_id for finding in identity_consistent_findings)
        mixed_run_findings = identity_consistent_findings if len(run_ids) > 1 else ()
        cycle_consistent_findings = (
            () if mixed_run_findings else identity_consistent_findings
        )
        temporally_valid_findings = tuple(
            finding
            for finding in cycle_consistent_findings
            if finding.observed_at <= generated_at
        )
        future_dated_findings = tuple(
            finding
            for finding in cycle_consistent_findings
            if finding.observed_at > generated_at
        )
        market_findings = tuple(
            finding
            for finding in temporally_valid_findings
            if _is_market_advisory(finding)
        )
        future_market_findings = tuple(
            finding for finding in future_dated_findings if _is_market_advisory(finding)
        )
        verified_market_findings = tuple(
            finding
            for finding in market_findings
            if finding.verification_status is VerificationStatus.VERIFIED
        )
        fusion_findings = tuple(
            finding for finding in market_findings if _is_fusion_eligible(finding)
        )
        non_verified_market_findings = tuple(
            finding
            for finding in market_findings
            if finding.verification_status is not VerificationStatus.VERIFIED
        )
        excluded_market_findings = tuple(
            finding for finding in market_findings if not _is_fusion_eligible(finding)
        )
        operational_findings = tuple(
            finding
            for finding in temporally_valid_findings
            if not _is_market_advisory(finding)
        )
        blockers = ["LIVE_ORDER_BLOCKED"]
        if cross_symbol_findings:
            blockers.append("CROSS_SYMBOL_FINDINGS_ISOLATED")
        if identical_replay_detected and not identity_conflict_detected:
            blockers.append("DUPLICATE_FINDING_REPLAY_COLLAPSED")
        if identity_conflict_detected:
            blockers.extend(
                (
                    "FINDING_IDENTITY_CONFLICT",
                    "EVIDENCE_INTEGRITY_FAILED",
                    "MANUAL_REVIEW_REQUIRED",
                )
            )
        if mixed_run_findings:
            blockers.extend(
                (
                    "MIXED_RUN_FINDINGS_REJECTED",
                    "CYCLE_INTEGRITY_FAILED",
                    "MANUAL_REVIEW_REQUIRED",
                )
            )
        if future_dated_findings:
            blockers.append("FUTURE_DATED_FINDINGS_EXCLUDED")
        if future_market_findings:
            blockers.extend(
                ("MARKET_TEMPORAL_INTEGRITY_FAILED", "MANUAL_REVIEW_REQUIRED")
            )
        if not market_findings:
            blockers.extend(("DATA_UNAVAILABLE", "MARKET_ADVISORY_DATA_UNAVAILABLE"))
        if non_verified_market_findings:
            blockers.extend(("MARKET_EVIDENCE_NOT_VERIFIED", "MANUAL_REVIEW_REQUIRED"))
        if excluded_market_findings:
            blockers.append("NON_VERIFIED_MARKET_INFLUENCE_EXCLUDED")
        if operational_findings:
            blockers.append("NON_MARKET_ADVISORY_FINDINGS_ISOLATED")
        if any(
            finding.decision_impact in _OPERATIONAL_RISK_IMPACTS
            for finding in operational_findings
        ):
            blockers.append("OPERATIONAL_RESEARCH_RISK_PRESENT")
        blockers.extend(
            blocker
            for finding in temporally_valid_findings
            for blocker in finding.blockers
        )
        social_risk = _max_risk(
            market_findings,
            {"X_RADAR", "REDDIT_RADAR", "TELEGRAM_RADAR"},
        )
        news_risk = _max_risk(market_findings, {"NEWS_RADAR"})
        security_risk = _max_risk(market_findings, {"SECURITY_RADAR"})
        regulatory_risk = _max_risk(market_findings, {"REGULATORY_RADAR"})
        manipulation_risk = max(
            (item.manipulation_risk for item in market_findings), default=0.0
        )
        impact = fused_decision_impact(fusion_findings)
        if not fusion_findings and excluded_market_findings:
            impact = DecisionImpact.LOW_CONFIDENCE
        if future_market_findings and impact in _POSITIVE_MARKET_IMPACTS:
            impact = DecisionImpact.LOW_CONFIDENCE
        if impact in {DecisionImpact.RISK, DecisionImpact.CRITICAL_RISK}:
            blockers.append("EXTERNAL_RISK_REVIEW_REQUIRED")
        return ExternalDecisionImpact(
            symbol=symbol,
            generated_at=generated_at,
            external_bias=impact,
            decision_impact=impact,
            confidence=fused_confidence(verified_market_findings),
            news_risk=news_risk,
            social_risk=social_risk,
            security_risk=security_risk,
            regulatory_risk=regulatory_risk,
            manipulation_risk=manipulation_risk,
            evidence_ids=tuple(
                dict.fromkeys(
                    evidence_id
                    for finding in temporally_valid_findings
                    for evidence_id in finding.evidence_ids
                )
            ),
            blockers=tuple(dict.fromkeys(blockers)),
        )


def _is_market_advisory(finding: ExternalFinding) -> bool:
    return (
        finding.mission in _MARKET_ADVISORY_MISSIONS
        and finding.radar is not RadarName.GITHUB_RADAR
    )


def _deduplicate_findings_by_identity(
    findings: tuple[ExternalFinding, ...],
) -> tuple[tuple[ExternalFinding, ...], bool, bool]:
    findings_by_id: dict[str, ExternalFinding] = {}
    unique_findings: list[ExternalFinding] = []
    identical_replay_detected = False
    identity_conflict_detected = False
    for finding in findings:
        existing = findings_by_id.get(finding.finding_id)
        if existing is None:
            findings_by_id[finding.finding_id] = finding
            unique_findings.append(finding)
        elif existing == finding:
            identical_replay_detected = True
        else:
            identity_conflict_detected = True
    return (
        tuple(unique_findings),
        identical_replay_detected,
        identity_conflict_detected,
    )


def _is_symbol_relevant(finding: ExternalFinding, symbol: str | None) -> bool:
    return symbol is None or finding.symbol is None or finding.symbol == symbol


def _is_fusion_eligible(finding: ExternalFinding) -> bool:
    return (
        finding.verification_status is VerificationStatus.VERIFIED
        or finding.decision_impact in _FAIL_CLOSED_MARKET_IMPACTS
    )


def _max_risk(findings: tuple[ExternalFinding, ...], radar_names: set[str]) -> float:
    return max(
        (
            max(item.risk_score, item.manipulation_risk)
            for item in findings
            if item.radar.value in radar_names
        ),
        default=0.0,
    )

"""Fail-closed radar connector used until a legal provider is configured."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.external_intel.core.enums import (
    DecisionImpact,
    MissionName,
    RadarName,
    SourceType,
    VerificationStatus,
)
from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.interfaces import RadarRequest
from ai4binance.external_intel.core.models import ExternalFinding


@dataclass(frozen=True, slots=True)
class UnavailableRadarConnector:
    radar_name: RadarName
    source_type: SourceType
    mission: MissionName
    provider_name: str

    def run(self, request: RadarRequest) -> tuple[ExternalFinding, ...]:
        blocker = f"{self.provider_name.upper()}_PROVIDER_UNAVAILABLE"
        finding_id = eief_id(
            "extfind",
            request.run_id,
            self.radar_name.value,
            request.symbol or "MARKET_WIDE",
            blocker,
        )
        return (
            ExternalFinding(
                finding_id=finding_id,
                run_id=request.run_id,
                radar=self.radar_name,
                mission=self.mission,
                observed_at=request.observed_at,
                source_type=self.source_type,
                event_type="provider_unavailable",
                claim=f"{self.provider_name} provider is unavailable",
                verification_status=VerificationStatus.DATA_UNAVAILABLE,
                decision_impact=DecisionImpact.DATA_UNAVAILABLE,
                evidence_ids=(),
                symbol=request.symbol,
                evidence_score=0.0,
                confidence=0.0,
                blockers=(
                    "DATA_UNAVAILABLE",
                    blocker,
                    "MANUAL_REVIEW_REQUIRED",
                    "LIVE_ORDER_BLOCKED",
                ),
                audit_trace_id=eief_id("audit", finding_id),
            ),
        )

"""Supplementary, research-only agent adapter for snapshot-bound fusion results."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from ai4binance.agents.base import BaseAgent
from ai4binance.agents.registry import AgentDefinition
from ai4binance.schemas import AgentResult, AgentStatus, MarketSnapshot

_FATAL_BLOCKERS = frozenset(
    {
        "INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT",
        "DERIVATIVES_SYMBOL_MISMATCH",
        "DERIVATIVES_FEATURES_BLOCKED",
    }
)


@dataclass(frozen=True, slots=True)
class WhaleFusionAgent(BaseAgent):
    """Expose fusion as advisory AgentResult without hard-gate authority."""

    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        del prior_results
        raw = snapshot.onchain_snapshot.get("whale_fusion")
        if not isinstance(raw, Mapping):
            return self._insufficient(snapshot, ("WHALE_FUSION_SNAPSHOT_MISSING",))
        payload = cast(Mapping[str, object], raw)
        if payload.get("snapshot_id") != snapshot.snapshot_id:
            return self._insufficient(snapshot, ("WHALE_FUSION_SNAPSHOT_ID_MISMATCH",))
        if payload.get("symbol") != snapshot.symbol:
            return self._insufficient(snapshot, ("WHALE_FUSION_SYMBOL_MISMATCH",))
        if payload.get("execution_allowed") is not False:
            return self._insufficient(snapshot, ("WHALE_FUSION_AUTHORITY_INVALID",))
        if payload.get("promotion_status") != "RESEARCH_ONLY":
            return self._insufficient(snapshot, ("WHALE_FUSION_PROMOTION_INVALID",))
        direction = self._decimal(payload.get("direction_score"))
        score = self._decimal(payload.get("fusion_score"))
        confidence = self._decimal(payload.get("confidence"))
        as_of = self._timestamp(payload.get("as_of"))
        blockers = self._strings(payload.get("blockers"))
        channels = self._strings(payload.get("active_channels"))
        if direction is None or score is None or confidence is None or as_of is None:
            return self._insufficient(snapshot, ("WHALE_FUSION_PAYLOAD_INVALID",))
        if as_of > snapshot.created_at:
            return self._insufficient(snapshot, ("WHALE_FUSION_FROM_FUTURE",))
        fatal = tuple(blocker for blocker in blockers if blocker in _FATAL_BLOCKERS)
        if fatal:
            return self._insufficient(snapshot, fatal)
        bounded_direction = max(Decimal("-1"), min(Decimal("1"), direction))
        bounded_score = max(Decimal("0"), min(Decimal("100"), score))
        bounded_confidence = max(Decimal("0"), min(Decimal("1"), confidence))
        return self.result(
            snapshot,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=float(bounded_direction),
            score=float(bounded_score),
            confidence=float(bounded_confidence),
            evidence=("SNAPSHOT_BOUND_WHALE_FUSION",),
            warnings=("SUPPLEMENTARY_SPOT_EVIDENCE_ONLY", *blockers),
            reason_codes=("WHALE_FUSION_EVALUATED",),
            calculation_metadata={
                "active_channels": channels,
                "as_of": as_of.isoformat(),
                "contradiction_count": payload.get("contradiction_count", 0),
                "promotion_status": "RESEARCH_ONLY",
            },
        )

    def _insufficient(
        self, snapshot: MarketSnapshot, blockers: tuple[str, ...]
    ) -> AgentResult:
        return self.result(
            snapshot,
            status=AgentStatus.INSUFFICIENT_DATA,
            data_quality=snapshot.data_quality,
            applicable=False,
            blockers=blockers,
            warnings=("RESEARCH_ONLY_AGENT",),
            reason_codes=("WHALE_FUSION_INSUFFICIENT_DATA",),
        )

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return (
            parsed
            if parsed.tzinfo is not None and parsed.utcoffset() is not None
            else None
        )

    @staticmethod
    def _strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) for item in value
        ):
            return ()
        return tuple(item for item in value if isinstance(item, str))


def build_whale_fusion_agent(definition: AgentDefinition) -> WhaleFusionAgent | None:
    return WhaleFusionAgent(definition) if definition.name == "whale" else None

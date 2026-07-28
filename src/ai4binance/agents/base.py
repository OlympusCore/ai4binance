"""Fail-closed specialist-agent base contract."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from ai4binance.agents.registry import AgentDefinition
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OOSValidationStatus,
)


@dataclass(frozen=True, slots=True)
class BaseAgent(ABC):
    """Run one deterministic agent without execution authority."""

    definition: AgentDefinition

    def run(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Validate dependencies and convert failures into safe agent results."""
        blocked_dependencies = tuple(
            dependency
            for dependency in self.definition.dependencies
            if dependency not in prior_results
            or prior_results[dependency].status
            not in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}
        )
        if blocked_dependencies:
            return self.result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=tuple(
                    f"DEPENDENCY_NOT_READY:{name}" for name in blocked_dependencies
                ),
                reason_codes=("AGENT_DEPENDENCY_BLOCKED",),
            )
        try:
            result = self.analyze(snapshot, prior_results)
        except Exception as error:
            return self.result(
                snapshot,
                status=AgentStatus.FAILED,
                data_quality=DataQuality.DATA_INVALID,
                applicable=False,
                blockers=("AGENT_INTERNAL_ERROR",),
                reason_codes=("AGENT_FAILED_CLOSED",),
                calculation_metadata={"error_type": type(error).__name__},
            )
        if result.agent_name != self.definition.name:
            return self.result(
                snapshot,
                status=AgentStatus.FAILED,
                data_quality=DataQuality.DATA_INVALID,
                applicable=False,
                blockers=("AGENT_IDENTITY_MISMATCH",),
                reason_codes=("AGENT_FAILED_CLOSED",),
            )
        return result

    @abstractmethod
    def analyze(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Calculate one side-effect-free specialist result."""

    def result(
        self,
        snapshot: MarketSnapshot,
        *,
        status: AgentStatus,
        data_quality: DataQuality,
        applicable: bool,
        directional_vote: float = 0.0,
        score: float = 0.0,
        confidence: float = 0.0,
        evidence: tuple[str, ...] = (),
        counter_evidence: tuple[str, ...] = (),
        invalidation: str | None = None,
        blockers: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        detected_setups: tuple[str, ...] = (),
        regime_compatibility: str = "UNVALIDATED",
        reason_codes: tuple[str, ...],
        calculation_metadata: Mapping[str, object] | None = None,
    ) -> AgentResult:
        """Build a standardized result tied to the shared snapshot."""
        return AgentResult(
            agent_name=self.definition.name,
            agent_version=self.definition.version,
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframes=snapshot.timeframes,
            status=status,
            data_quality=data_quality,
            applicable=applicable,
            directional_vote=directional_vote,
            score=score,
            confidence=confidence,
            evidence=evidence,
            counter_evidence=counter_evidence,
            invalidation=invalidation,
            blockers=blockers,
            warnings=warnings,
            detected_setups=detected_setups,
            regime_compatibility=regime_compatibility,
            false_positive_risk=self.definition.false_positive_risk,
            hard_gate_eligible=False,
            oos_validation_status=OOSValidationStatus.UNVALIDATED,
            promotion_status=self.definition.promotion_status,
            reason_codes=reason_codes,
            calculation_metadata=calculation_metadata or {},
        )

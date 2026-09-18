"""Deterministic independent-cluster evidence fusion with no decision authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import fsum

from ai4binance.agents.registry import AgentDefinition, AgentRegistry, AgentStage
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OOSValidationStatus,
    is_usable_agent_result,
)


@dataclass(frozen=True, slots=True)
class EvidenceFusionEngine:
    """Fuse independent analytical evidence without risk or execution authority."""

    definition: AgentDefinition
    registry: AgentRegistry

    def __post_init__(self) -> None:
        if (
            self.definition.name != "confluence"
            or self.definition.stage is not AgentStage.SYNTHESIS
        ):
            raise ValueError("evidence fusion requires the confluence definition")
        if self.registry.get(self.definition.name) != self.definition:
            raise ValueError("evidence fusion definition must belong to its registry")

    def fuse(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Return one fail-closed `confluence` result for the shared snapshot."""
        blocked_dependencies = tuple(
            dependency
            for dependency in self.definition.dependencies
            if dependency not in prior_results
            or prior_results[dependency].status
            not in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}
        )
        if blocked_dependencies:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=tuple(
                    f"DEPENDENCY_NOT_READY:{dependency}"
                    for dependency in blocked_dependencies
                ),
                reason_codes=("AGENT_DEPENDENCY_BLOCKED",),
            )
        try:
            return self._fuse(snapshot, prior_results)
        except Exception as error:
            return self._result(
                snapshot,
                status=AgentStatus.FAILED,
                data_quality=DataQuality.DATA_INVALID,
                applicable=False,
                blockers=("AGENT_INTERNAL_ERROR",),
                reason_codes=("AGENT_FAILED_CLOSED",),
                calculation_metadata={"error_type": type(error).__name__},
            )

    def _fuse(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        cluster_results: dict[str, AgentResult] = {}
        rejected_correlated: list[str] = []
        for name, result in prior_results.items():
            definition = self.registry.by_name.get(name)
            if definition is None or definition.stage is not AgentStage.ANALYSIS:
                continue
            if not is_usable_agent_result(result):
                continue
            current = cluster_results.get(definition.evidence_cluster)
            if current is None or (
                result.confidence,
                result.score,
                result.agent_name,
            ) > (
                current.confidence,
                current.score,
                current.agent_name,
            ):
                if current is not None:
                    rejected_correlated.append(current.agent_name)
                cluster_results[definition.evidence_cluster] = result
            else:
                rejected_correlated.append(result.agent_name)

        selected = tuple(cluster_results[name] for name in sorted(cluster_results))
        if not selected:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("NO_VALIDATED_SPECIALIST_EVIDENCE",),
                reason_codes=("CONFLUENCE_BLOCKED",),
            )
        weights = tuple(max(result.confidence, 0.01) for result in selected)
        weight_total = fsum(weights)
        score = (
            fsum(
                result.score * weight
                for result, weight in zip(selected, weights, strict=True)
            )
            / weight_total
        )
        vote = (
            fsum(
                result.directional_vote * weight
                for result, weight in zip(selected, weights, strict=True)
            )
            / weight_total
        )
        confidence = fsum(result.confidence for result in selected) / len(selected)
        aligned_weight = fsum(
            weight
            for result, weight in zip(selected, weights, strict=True)
            if vote == 0 or result.directional_vote * vote >= 0
        )
        directional_agreement = aligned_weight / weight_total
        return self._result(
            snapshot,
            status=AgentStatus.PARTIAL,
            data_quality=snapshot.data_quality,
            applicable=True,
            directional_vote=round(vote, 6),
            score=round(score, 6),
            confidence=round(confidence, 6),
            evidence=tuple(result.agent_name for result in selected),
            warnings=(
                ("OOS_VALIDATION_INCOMPLETE", "DIRECTIONAL_CONFLICT")
                if directional_agreement < 0.67
                else ("OOS_VALIDATION_INCOMPLETE",)
            ),
            reason_codes=("INDEPENDENT_CONFLUENCE_CALCULATED",),
            calculation_metadata={
                "independent_confluence_count": len(selected),
                "evidence_clusters": tuple(sorted(cluster_results)),
                "selected_agents": tuple(result.agent_name for result in selected),
                "rejected_correlated_agents": tuple(sorted(rejected_correlated)),
                "directional_agreement": round(directional_agreement, 6),
            },
        )

    def _result(
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
        blockers: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        reason_codes: tuple[str, ...],
        calculation_metadata: Mapping[str, object] | None = None,
    ) -> AgentResult:
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
            blockers=blockers,
            warnings=warnings,
            false_positive_risk=self.definition.false_positive_risk,
            hard_gate_eligible=False,
            oos_validation_status=OOSValidationStatus.UNVALIDATED,
            promotion_status=self.definition.promotion_status,
            reason_codes=reason_codes,
            calculation_metadata=calculation_metadata or {},
        )

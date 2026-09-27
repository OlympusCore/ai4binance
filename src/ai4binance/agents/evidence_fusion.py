"""Deterministic dependency-aware evidence fusion with no decision authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import fsum

from ai4binance.agents.registry import AgentDefinition, AgentRegistry, AgentStage
from ai4binance.intelligence.method_registry import (
    current_method_registry,
    recorded_lineage,
)
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OOSValidationStatus,
    is_usable_agent_result,
)


def _root_keys(definition: AgentDefinition, result: AgentResult) -> frozenset[str]:
    """Declarations can add dependencies, never erase canonical shared inputs."""
    roots = {f"input:{name}" for name in definition.required_data}
    for field in ("evidence_root_ids", "duplicate_root_ids", "pivot_ids"):
        values = result.calculation_metadata.get(field, ())
        if (
            not isinstance(values, (tuple, list))
            or len(values) > 100
            or any(
                not isinstance(value, str) or not value.strip() or len(value) > 500
                for value in values
            )
        ):
            raise ValueError("evidence dependency roots must be nonblank strings")
        roots.update(f"root:{value}" for value in values)
    return frozenset(roots or {"input:UNKNOWN"})


def _dependency_groups(
    registry: AgentRegistry, results: tuple[AgentResult, ...]
) -> tuple[tuple[AgentResult, ...], ...]:
    """Connected components include transitive shared roots and legacy clusters."""
    groups: list[tuple[set[str], list[AgentResult]]] = []
    for result in sorted(results, key=lambda row: row.agent_name):
        definition = registry.get(result.agent_name)
        roots = set(_root_keys(definition, result))
        roots.add(f"cluster:{definition.evidence_cluster}")
        roots.update(_registry_dependency_roots(result))
        rows = [result]
        retained = []
        for group_roots, group_rows in groups:
            if roots & group_roots:
                roots.update(group_roots)
                rows.extend(group_rows)
            else:
                retained.append((group_roots, group_rows))
        groups = [*retained, (roots, rows)]
    return tuple(
        sorted(
            (tuple(sorted(rows, key=lambda row: row.agent_name)) for _, rows in groups),
            key=lambda rows: rows[0].agent_name,
        )
    )


def _registry_dependency_roots(result: AgentResult) -> frozenset[str]:
    """Declared shared inputs only add dependencies to verified method lineage."""
    lineage = recorded_lineage(result.calculation_metadata)
    if lineage is None:
        return frozenset()
    registry = current_method_registry()
    method = registry.method(lineage.method_id)
    identities = {method.method_id, method.family}
    return frozenset(
        "registry_dependency:" + "|".join(sorted((edge.left, edge.right)))
        for edge in registry.interactions
        if edge.relationship in {"SHARED_INPUT", "SHARED_PIVOTS"}
        and identities & {edge.left, edge.right}
    )


@dataclass(frozen=True, slots=True)
class EvidenceFusionEngine:
    """Fuse dependency-filtered evidence without claiming statistical independence."""

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
        usable: list[AgentResult] = []
        observations: list[dict[str, object]] = []
        for name, result in prior_results.items():
            definition = self.registry.by_name.get(name)
            if definition is None or definition.stage is not AgentStage.ANALYSIS:
                continue
            if (
                result.agent_name,
                result.snapshot_id,
                result.symbol,
                result.timestamp,
            ) != (name, snapshot.snapshot_id, snapshot.symbol, snapshot.created_at):
                return self._result(
                    snapshot,
                    status=AgentStatus.BLOCKED,
                    data_quality=DataQuality.DATA_INVALID,
                    applicable=False,
                    blockers=("EVIDENCE_IDENTITY_MISMATCH",),
                    reason_codes=("CONFLUENCE_BLOCKED",),
                )
            observations.append(
                {
                    "agent": name,
                    "evidence_family": definition.evidence_cluster,
                    "vote": result.directional_vote,
                    "blockers": result.blockers,
                    "warnings": result.warnings,
                    "evidence": result.evidence,
                    "status": result.status.value,
                    "counter_evidence": result.counter_evidence,
                }
            )
            if is_usable_agent_result(result) and name not in {"news", "sentiment"}:
                usable.append(result)
        groups = _dependency_groups(self.registry, tuple(usable))
        selected = tuple(
            max(rows, key=lambda row: (row.confidence, row.score, row.agent_name))
            for rows in groups
        )
        selected_names = {row.agent_name for row in selected}
        rejected_correlated = sorted(
            row.agent_name for row in usable if row.agent_name not in selected_names
        )
        clusters = sorted(
            {self.registry.get(row.agent_name).evidence_cluster for row in usable}
        )
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
            warnings=("OOS_VALIDATION_INCOMPLETE", "INDEPENDENCE_NOT_MEASURED")
            + (
                ("DIRECTIONAL_CONFLICT",)
                if any(row.directional_vote > 0 for row in usable)
                and any(row.directional_vote < 0 for row in usable)
                else ()
            ),
            reason_codes=("DEPENDENCY_AWARE_CONFLUENCE_CALCULATED",),
            calculation_metadata={
                "independent_confluence_count": 0,
                "independence_status": "NOT_MEASURED",
                "method_lineage": current_method_registry()
                .lineage(
                    "method_interactions.dependency_aware_confluence", "1.1.0", "1.1.0"
                )
                .to_payload(),
                "effective_dependency_group_count": len(groups),
                "method_diversity_count": len(clusters),
                "dependency_groups": tuple(
                    tuple(row.agent_name for row in rows) for rows in groups
                ),
                "observations": tuple(
                    sorted(observations, key=lambda row: str(row["agent"]))
                ),
                "opposing_agents": tuple(
                    sorted(
                        row.agent_name
                        for row in usable
                        if row.directional_vote * vote < 0
                    )
                ),
                "evidence_clusters": tuple(clusters),
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

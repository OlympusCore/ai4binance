"""Enterprise bridge for the MultiOps control plane."""

from __future__ import annotations

from dataclasses import dataclass, field

from ai4binance.enterprise.contracts import (
    DepartmentId,
    OpinionVerdict,
    OpsReadiness,
    WorkflowIdentity,
)
from ai4binance.enterprise.departments import (
    DepartmentRegistry,
    build_default_department_registry,
)
from ai4binance.multiops import (
    MultiOpsRegistry,
    OpsBlocker,
    OpsCapability,
    OpsCheckResult,
    OpsControlPlanePolicy,
    OpsDomain,
    OpsVerdict,
    build_default_multiops_registry,
)


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class MultiOpsControlPlane:
    """Validate MultiOps capability checks without granting execution authority."""

    multiops_registry: MultiOpsRegistry
    department_registry: DepartmentRegistry
    policy: OpsControlPlanePolicy = field(default_factory=OpsControlPlanePolicy)

    @classmethod
    def default(cls) -> MultiOpsControlPlane:
        return cls(
            multiops_registry=build_default_multiops_registry(),
            department_registry=build_default_department_registry(),
        )

    def evaluate_capability(
        self,
        *,
        check_id: str,
        domain: OpsDomain,
        capability: OpsCapability,
        subject_ref: str,
        evidence_refs: tuple[str, ...],
    ) -> OpsCheckResult:
        self.multiops_registry.validate_capability(
            domain=domain,
            capability=capability,
        )
        department = self.department_registry.get(DepartmentId.MULTI_OPS)
        if not department.independent_control or not department.veto_authority:
            return _blocked_check(
                check_id=check_id,
                domain=domain,
                capability=capability,
                subject_ref=subject_ref,
                evidence_refs=evidence_refs,
                blockers=(
                    "MULTIOPS_DEPARTMENT_CONTROL_INVALID",
                    OpsBlocker.LIVE_BLOCKED.value,
                ),
                next_actions=("Restore independent MultiOps veto authority.",),
            )
        if self.policy.evidence_required and not evidence_refs:
            return _blocked_check(
                check_id=check_id,
                domain=domain,
                capability=capability,
                subject_ref=subject_ref,
                evidence_refs=evidence_refs,
                blockers=(
                    OpsBlocker.EVIDENCE_REQUIRED.value,
                    OpsBlocker.HUMAN_REVIEW_REQUIRED.value,
                    OpsBlocker.LIVE_BLOCKED.value,
                ),
                next_actions=("Attach evidence before accepting the ops check.",),
            )
        return OpsCheckResult(
            check_id=check_id,
            domain=domain,
            capability=capability,
            subject_ref=subject_ref,
            verdict=OpsVerdict.PASSED,
            evidence_refs=evidence_refs,
            blockers=(),
        )

    def to_ops_readiness(
        self,
        *,
        identity: WorkflowIdentity,
        result: OpsCheckResult,
    ) -> OpsReadiness:
        department = self.department_registry.get(DepartmentId.MULTI_OPS)
        return OpsReadiness(
            identity=identity,
            readiness_id=f"multiops-readiness:{result.check_id}",
            reviewer_id=department.manager_role,
            subject_ref=result.subject_ref,
            verdict=_readiness_verdict(result.verdict),
            evidence_refs=(result.check_id, *result.evidence_refs),
            blockers=result.blockers,
        )


def build_default_multiops_control_plane() -> MultiOpsControlPlane:
    return MultiOpsControlPlane.default()


def _blocked_check(
    *,
    check_id: str,
    domain: OpsDomain,
    capability: OpsCapability,
    subject_ref: str,
    evidence_refs: tuple[str, ...],
    blockers: tuple[str, ...],
    next_actions: tuple[str, ...],
) -> OpsCheckResult:
    return OpsCheckResult(
        check_id=check_id,
        domain=domain,
        capability=capability,
        subject_ref=subject_ref,
        verdict=OpsVerdict.INSUFFICIENT_EVIDENCE,
        evidence_refs=evidence_refs,
        blockers=_stable_unique(blockers),
        next_actions=_stable_unique(next_actions),
    )


def _readiness_verdict(verdict: OpsVerdict) -> OpinionVerdict:
    if verdict is OpsVerdict.PASSED:
        return OpinionVerdict.ACCEPTED
    if verdict is OpsVerdict.REVISION_REQUIRED:
        return OpinionVerdict.REVISION_REQUIRED
    if verdict is OpsVerdict.INSUFFICIENT_EVIDENCE:
        return OpinionVerdict.INSUFFICIENT_EVIDENCE
    return OpinionVerdict.REJECTED

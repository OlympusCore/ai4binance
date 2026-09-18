"""Enterprise bridge for the MultiOps control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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
from ai4binance.ops.jobs import (
    JobRequest,
    RunnerAdmissionReport,
    RunnerAdmissionStatus,
    RunnerManifest,
    assess_runner_admission,
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

    def evaluate_runner_admission(
        self,
        *,
        identity: WorkflowIdentity,
        runner_manifest: RunnerManifest,
        request: JobRequest,
        domain: OpsDomain,
        capability: OpsCapability,
        subject_ref: str,
        evidence_refs: tuple[str, ...],
        observed_at: datetime,
    ) -> MultiOpsRunnerAdmissionReview:
        runner_report = assess_runner_admission(
            runner_manifest,
            request,
            observed_at=observed_at,
        )
        runner_evidence_refs = (
            runner_report.run_card.run_card_id,
            runner_report.persistent_evidence.record_id,
            runner_report.audit_record.event_id,
        )
        check_id = (
            f"multiops-runner-check:{runner_manifest.runner_id}:"
            f"{request.idempotency_key}"
        )
        if runner_report.status is RunnerAdmissionStatus.BLOCKED:
            result = _blocked_check(
                check_id=check_id,
                domain=domain,
                capability=capability,
                subject_ref=subject_ref,
                evidence_refs=runner_evidence_refs,
                blockers=(
                    *runner_report.blockers,
                    OpsBlocker.HUMAN_REVIEW_REQUIRED.value,
                    OpsBlocker.LIVE_BLOCKED.value,
                ),
                next_actions=("Resolve runner admission blockers before execution.",),
            )
        elif not evidence_refs:
            result = _blocked_check(
                check_id=check_id,
                domain=domain,
                capability=capability,
                subject_ref=subject_ref,
                evidence_refs=runner_evidence_refs,
                blockers=(
                    OpsBlocker.EVIDENCE_REQUIRED.value,
                    "RUNNER_SUBJECT_EVIDENCE_REQUIRED",
                    OpsBlocker.HUMAN_REVIEW_REQUIRED.value,
                    OpsBlocker.LIVE_BLOCKED.value,
                ),
                next_actions=("Attach subject evidence before admitting the runner.",),
            )
        else:
            result = self.evaluate_capability(
                check_id=check_id,
                domain=domain,
                capability=capability,
                subject_ref=subject_ref,
                evidence_refs=(*runner_evidence_refs, *evidence_refs),
            )
        readiness = self.to_ops_readiness(identity=identity, result=result)
        status = (
            "RUNNER_BLOCKED"
            if runner_report.status is RunnerAdmissionStatus.BLOCKED
            or result.verdict is not OpsVerdict.PASSED
            else "RUNNER_READY_REPORT_ONLY"
            if runner_report.status is RunnerAdmissionStatus.ADMITTED_REPORT_ONLY
            else "RUNNER_READY_RESEARCH_ONLY"
        )
        return MultiOpsRunnerAdmissionReview(
            runner_report=runner_report,
            ops_check=result,
            readiness=readiness,
            status=status,
            blockers=result.blockers,
        )


def build_default_multiops_control_plane() -> MultiOpsControlPlane:
    return MultiOpsControlPlane.default()


@dataclass(frozen=True, slots=True)
class MultiOpsRunnerAdmissionReview:
    runner_report: RunnerAdmissionReport
    ops_check: OpsCheckResult
    readiness: OpsReadiness
    status: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {
            "RUNNER_BLOCKED",
            "RUNNER_READY_REPORT_ONLY",
            "RUNNER_READY_RESEARCH_ONLY",
        }:
            raise ValueError("multiops runner admission review status is invalid")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("multiops runner admission blockers must be unique")
        if self.status == "RUNNER_BLOCKED" and not self.blockers:
            raise ValueError(
                "blocked multiops runner admission review requires blockers"
            )
        if self.status != "RUNNER_BLOCKED" and self.blockers:
            raise ValueError(
                "ready multiops runner admission review cannot contain blockers"
            )
        if self.execution_allowed:
            raise ValueError(
                "multiops runner admission review cannot authorize execution"
            )
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError(
                "multiops runner admission review cannot promote production state"
            )
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError(
                "multiops runner admission review must remain live blocked"
            )


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

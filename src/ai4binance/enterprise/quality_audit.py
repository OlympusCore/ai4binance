"""Quality department system audit for enterprise governance controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from ai4binance.enterprise.agent_lifecycle import AgentLifecycleStateMachine
from ai4binance.enterprise.communication import (
    CommunicationDecisionStatus,
    DepartmentCommunicationGate,
)
from ai4binance.enterprise.contracts import (
    DepartmentId,
    InterdepartmentalQuestion,
    OpinionVerdict,
    Priority,
    QualityOpinion,
    WorkflowIdentity,
)
from ai4binance.enterprise.departments import build_default_department_registry
from ai4binance.enterprise.executive import GeneralManagerController
from ai4binance.enterprise.prompt_intake import (
    PromptAccessPolicy,
    PromptAccessStatus,
    contains_restricted_prompt_content,
)
from ai4binance.enterprise.storage import EnterpriseAuditJournal
from ai4binance.enterprise.task_tracker import EnterpriseTaskTracker
from ai4binance.privacy_boundary import (
    PrivacyBoundaryReport,
    PrivacyBoundaryStatus,
    scan_privacy_boundary,
)
from ai4binance.rag_corrective import evaluate_retrieval_quality
from ai4binance.skills.linter import lint_skill_manifest


class QualitySystemAuditStatus(StrEnum):
    PASSED = "PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class QualitySystemAuditEvidence:
    workspace_root: Path
    command_names: tuple[str, ...]
    observed_at: datetime
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    privacy_boundary_report: PrivacyBoundaryReport | None = None

    def __post_init__(self) -> None:
        _require_aware("quality audit observed_at", self.observed_at)
        _require_unique_text("quality audit command names", self.command_names)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("quality audit evidence cannot authorize execution")


@dataclass(frozen=True, slots=True)
class QualitySystemAuditCheck:
    check_id: str
    subject_ref: str
    passed: bool
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    corrective_actions: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("quality check id", self.check_id)
        _require_text("quality check subject", self.subject_ref)
        _require_unique_text("quality check evidence refs", self.evidence_refs)
        _require_unique_text("quality check blockers", self.blockers)
        _require_unique_text(
            "quality check corrective actions", self.corrective_actions
        )
        if self.passed == bool(self.blockers):
            raise ValueError("quality check status and blockers disagree")
        if self.execution_allowed:
            raise ValueError("quality check cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("quality check cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("quality check must remain live blocked")


@dataclass(frozen=True, slots=True)
class QualitySystemAuditReport:
    audit_id: str
    observed_at: datetime
    manager_id: str
    checks: tuple[QualitySystemAuditCheck, ...]
    status: QualitySystemAuditStatus
    blockers: tuple[str, ...]
    corrective_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("quality audit id", self.audit_id)
        _require_text("quality audit manager", self.manager_id)
        _require_aware("quality audit observed_at", self.observed_at)
        if not self.checks:
            raise ValueError("quality audit report requires checks")
        _require_unique_text("quality audit blockers", self.blockers)
        _require_unique_text("quality audit actions", self.corrective_actions)
        expected_status = (
            QualitySystemAuditStatus.REVISION_REQUIRED
            if self.blockers
            else QualitySystemAuditStatus.PASSED
        )
        if self.status is not expected_status:
            raise ValueError("quality audit status does not match blockers")
        if self.execution_allowed:
            raise ValueError("quality audit cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("quality audit cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("quality audit must remain live blocked")

    def to_quality_opinion(self, identity: WorkflowIdentity) -> QualityOpinion:
        verdict = (
            OpinionVerdict.REVISION_REQUIRED
            if self.blockers
            else OpinionVerdict.ACCEPTED
        )
        return QualityOpinion(
            identity=identity,
            opinion_id=f"quality-opinion:{self.audit_id}",
            reviewer_id=self.manager_id,
            subject_ref=self.audit_id,
            verdict=verdict,
            evidence_refs=tuple(check.check_id for check in self.checks),
            blockers=self.blockers,
        )


def run_quality_system_audit(
    evidence: QualitySystemAuditEvidence,
) -> QualitySystemAuditReport:
    registry = build_default_department_registry()
    manager_id = registry.get(DepartmentId.QUALITY_AUDIT).manager_role
    privacy_report = evidence.privacy_boundary_report or scan_privacy_boundary(
        evidence.workspace_root
    )
    checks = (
        _audit_quality_department_independence(manager_id),
        _audit_computer_md_privacy_boundary(privacy_report),
        _audit_prompt_intake(evidence.observed_at),
        _audit_interdepartmental_prompt_leak_block(evidence.observed_at),
        _audit_enterprise_audit_journal(),
        _audit_agentic_governance_surfaces(),
        _audit_cli_governance_commands(evidence.command_names),
        _audit_holding_governance_doc(evidence.workspace_root),
    )
    blockers = _stable_unique(
        tuple(blocker for check in checks for blocker in check.blockers)
    )
    corrective_actions = _stable_unique(
        tuple(action for check in checks for action in check.corrective_actions)
    )
    return QualitySystemAuditReport(
        audit_id=f"quality-system-audit:{int(evidence.observed_at.timestamp())}",
        observed_at=evidence.observed_at,
        manager_id=manager_id,
        checks=checks,
        status=(
            QualitySystemAuditStatus.REVISION_REQUIRED
            if blockers
            else QualitySystemAuditStatus.PASSED
        ),
        blockers=blockers,
        corrective_actions=corrective_actions,
    )


def _audit_quality_department_independence(
    manager_id: str,
) -> QualitySystemAuditCheck:
    registry = build_default_department_registry()
    department = registry.get(DepartmentId.QUALITY_AUDIT)
    passed = (
        department.manager_role == manager_id
        and department.independent_control
        and department.veto_authority
        and not department.execution_allowed
        and department.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    )
    return _check(
        "QUALITY_DEPARTMENT_INDEPENDENCE",
        "department:QUALITY_AUDIT",
        passed=passed,
        evidence_refs=("department-registry:QUALITY_AUDIT",),
        blockers=("QUALITY_DEPARTMENT_INDEPENDENCE_INVALID",),
        corrective_actions=("Restore independent quality veto authority.",),
    )


def _audit_computer_md_privacy_boundary(
    report: PrivacyBoundaryReport,
) -> QualitySystemAuditCheck:
    passed = (
        report.status is PrivacyBoundaryStatus.PASSED
        and report.computer_profile_ref == "Computer.md"
        and not report.findings
        and not report.blockers
        and not report.execution_allowed
        and report.promotion_status == "RESEARCH_ONLY"
        and report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    )
    blockers = tuple(str(blocker.value) for blocker in report.blockers)
    if report.computer_profile_ref != "Computer.md":
        blockers = (*blockers, "COMPUTER_PROFILE_REF_NOT_REPO_LOCAL")
    if report.status is not PrivacyBoundaryStatus.PASSED and not blockers:
        blockers = (*blockers, f"PRIVACY_BOUNDARY_{report.status.value}")
    return _check(
        "COMPUTER_MD_PRIVACY_BOUNDARY",
        "privacy:Computer.md",
        passed=passed,
        evidence_refs=(
            f"profile-ref:{report.computer_profile_ref}",
            f"scanned-file-count:{report.scanned_file_count}",
            f"finding-count:{report.finding_count}",
        ),
        blockers=blockers,
        corrective_actions=(
            (
                "Move local machine profile details back behind the "
                "Computer.md boundary.",
            )
            if blockers
            else ()
        ),
    )


def _audit_prompt_intake(observed_at: datetime) -> QualitySystemAuditCheck:
    identity = _identity("quality-prompt-intake", observed_at)
    registry = build_default_department_registry()
    controller = GeneralManagerController(registry)
    intake = controller.intake_prompt(
        identity=identity,
        prompt_id="quality-audit-prompt",
        submitted_by="quality-audit",
        raw_prompt="CODEX_PROMPT: audit system. SECRET=hidden",
    )
    directive = intake.to_board_directive(
        directive_id="quality-audit-directive",
        resource_budget="cpu-light",
        time_budget_seconds=120,
    )
    policy = PromptAccessPolicy(registry)
    general_manager = policy.authorize_raw_prompt(
        actor_department_id=DepartmentId.EXECUTIVE_OFFICE,
        actor_role="GeneralManagerController",
        intake=intake,
    )
    software_manager = policy.authorize_raw_prompt(
        actor_department_id=DepartmentId.SOFTWARE_ENGINEERING,
        actor_role="SoftwareDepartmentManager",
        intake=intake,
    )
    passed = (
        general_manager.status is PromptAccessStatus.ALLOWED
        and software_manager.status is PromptAccessStatus.BLOCKED
        and not contains_restricted_prompt_content(directive.objective)
        and directive.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    )
    return _check(
        "GENERAL_MANAGER_PROMPT_INTAKE",
        "enterprise:prompt-intake",
        passed=passed,
        evidence_refs=(
            f"prompt-sha256:{intake.raw_prompt_sha256}",
            "prompt-access:GENERAL_MANAGER_ONLY",
        ),
        blockers=("GENERAL_MANAGER_PROMPT_INTAKE_INVALID",),
        corrective_actions=("Route raw prompts through ExecutivePromptIntake only.",),
    )


def _audit_interdepartmental_prompt_leak_block(
    observed_at: datetime,
) -> QualitySystemAuditCheck:
    registry = build_default_department_registry()
    gate = DepartmentCommunicationGate(registry)
    message = InterdepartmentalQuestion(
        identity=_identity("quality-communication", observed_at),
        message_id="quality-audit-message",
        sender_department_id=DepartmentId.SOFTWARE_ENGINEERING,
        sender_manager_id="SoftwareDepartmentManager",
        recipient_department_id=DepartmentId.QUALITY_AUDIT,
        recipient_manager_id="QualityDepartmentManager",
        question="BEGIN_RAW_PROMPT do not forward END_RAW_PROMPT",
        evidence_refs=("artifact:quality-audit",),
        priority=Priority.P1,
        deadline=observed_at + timedelta(minutes=30),
    )
    decision = gate.validate_question(message)
    passed = (
        decision.status is CommunicationDecisionStatus.BLOCKED
        and "PROMPT_ACCESS_BLOCKED" in decision.reason_codes
        and decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    )
    return _check(
        "INTERDEPARTMENTAL_PROMPT_LEAK_BLOCK",
        "enterprise:communication",
        passed=passed,
        evidence_refs=("communication-gate:PROMPT_ACCESS_BLOCKED",),
        blockers=("INTERDEPARTMENTAL_PROMPT_LEAK_NOT_BLOCKED",),
        corrective_actions=("Block raw prompt markers in department messages.",),
    )


def _audit_enterprise_audit_journal() -> QualitySystemAuditCheck:
    required = (
        "append_prompt_intake_verified",
        "append_prompt_access_decision_verified",
        "append_work_order_created_verified",
    )
    passed = all(hasattr(EnterpriseAuditJournal, name) for name in required)
    return _check(
        "ENTERPRISE_AUDIT_JOURNAL_EVENTS",
        "enterprise:storage",
        passed=passed,
        evidence_refs=tuple(f"EnterpriseAuditJournal.{name}" for name in required),
        blockers=("ENTERPRISE_AUDIT_JOURNAL_EVENTS_MISSING",),
        corrective_actions=(
            "Persist prompt intake, access and work-order audit events.",
        ),
    )


def _audit_agentic_governance_surfaces() -> QualitySystemAuditCheck:
    required = (
        ("agent-lifecycle-state-machine", AgentLifecycleStateMachine),
        ("skill-linter", lint_skill_manifest),
        ("task-tracker", EnterpriseTaskTracker),
        ("corrective-rag", evaluate_retrieval_quality),
    )
    model_adaptation_path = (
        Path(__file__).resolve().parents[1] / "learning" / "model_adaptation.py"
    )
    missing = tuple(name for name, value in required if value is None)
    if not model_adaptation_path.is_file():
        missing = (*missing, "model-adaptation-board")
    return _check(
        "AGENTIC_GOVERNANCE_SURFACES",
        "enterprise:agentic-governance",
        passed=not missing,
        evidence_refs=(
            *(f"governance-surface:{name}" for name, _ in required),
            "governance-surface:model-adaptation-board",
        ),
        blockers=tuple(
            f"AGENTIC_GOVERNANCE_SURFACE_MISSING:{name}" for name in missing
        ),
        corrective_actions=tuple(
            f"Restore agentic governance surface {name}." for name in missing
        ),
    )


def _audit_cli_governance_commands(
    command_names: tuple[str, ...],
) -> QualitySystemAuditCheck:
    required = {"enterprise-intake", "skills-audit", "quality-system-audit"}
    missing = tuple(sorted(required.difference(command_names)))
    return _check(
        "CLI_GOVERNANCE_COMMANDS",
        "cli:governance",
        passed=not missing,
        evidence_refs=tuple(f"cli-command:{name}" for name in sorted(required)),
        blockers=tuple(f"CLI_COMMAND_MISSING:{name}" for name in missing),
        corrective_actions=tuple(
            f"Add CLI governance command {name}." for name in missing
        ),
    )


def _audit_holding_governance_doc(workspace_root: Path) -> QualitySystemAuditCheck:
    doc_path = workspace_root / "Docs" / "HOLDING_GOVERNANCE.md"
    required_terms = (
        "GeneralManagerController",
        "EnterpriseAuditJournal",
        "COMPUTER_MD_PRIVACY_BOUNDARY",
        "Computer.md",
        "PROMPT_ACCESS_BLOCKED",
        "WRITTEN_APPROVAL_DOC_SYNC",
        "LIVE_ORDER_BLOCKED",
    )
    text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    missing = tuple(term for term in required_terms if term not in text)
    return _check(
        "HOLDING_GOVERNANCE_DOCUMENTED",
        "Docs/HOLDING_GOVERNANCE.md",
        passed=doc_path.is_file() and not missing,
        evidence_refs=("doc:Docs/HOLDING_GOVERNANCE.md",),
        blockers=(
            ("HOLDING_GOVERNANCE_DOC_MISSING",)
            if not doc_path.is_file()
            else tuple(
                f"HOLDING_GOVERNANCE_DOC_TERM_MISSING:{term}" for term in missing
            )
        ),
        corrective_actions=(
            ("Create Docs/HOLDING_GOVERNANCE.md.",)
            if not doc_path.is_file()
            else tuple(f"Document required governance term {term}." for term in missing)
        ),
    )


def _check(
    check_id: str,
    subject_ref: str,
    *,
    passed: bool,
    evidence_refs: tuple[str, ...],
    blockers: tuple[str, ...],
    corrective_actions: tuple[str, ...],
) -> QualitySystemAuditCheck:
    return QualitySystemAuditCheck(
        check_id=check_id,
        subject_ref=subject_ref,
        passed=passed,
        evidence_refs=evidence_refs,
        blockers=() if passed else blockers,
        corrective_actions=() if passed else corrective_actions,
    )


def _identity(label: str, observed_at: datetime) -> WorkflowIdentity:
    return WorkflowIdentity(
        work_order_id=f"wo:{label}",
        run_id=f"run:{label}",
        trace_id=f"trace:{label}",
        created_at=observed_at,
    )

"""Lean, Kaizen and Six Sigma governance for safe research operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


def _require_identity(**values: str) -> None:
    missing = tuple(name for name, value in values.items() if not value.strip())
    if missing:
        raise ValueError(f"lean governance identity cannot be empty: {missing[0]}")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class LeanPillar(StrEnum):
    """Operational excellence pillar names used by AI4BINANCE."""

    FIVE_S = "5S"
    HOSHIN_KANRI = "HOSHIN_KANRI"
    POKA_YOKE = "POKA_YOKE"
    KAIZEN = "KAIZEN"
    SIX_SIGMA = "SIX_SIGMA"


QAQC_AGENT_ID = "qaqc_agent"
QAQC_AGENT_DISPLAY_NAME = "QAQC-Agent"


class KaizenStage(StrEnum):
    """PDCA stage for a small, reversible improvement."""

    PLAN = "PLAN"
    DO = "DO"
    CHECK = "CHECK"
    ACT = "ACT"


class DmaicStage(StrEnum):
    """Six Sigma DMAIC stage for defect reduction."""

    DEFINE = "DEFINE"
    MEASURE = "MEASURE"
    ANALYZE = "ANALYZE"
    IMPROVE = "IMPROVE"
    CONTROL = "CONTROL"


class PokaYokeCheck(StrEnum):
    """Mandatory error-proofing checks before a governed workflow can pass."""

    LIVE_GATE_FAIL_CLOSED = "LIVE_GATE_FAIL_CLOSED"
    REDACTION_GATE = "REDACTION_GATE"
    WALLET_BACKTEST_ISOLATION = "WALLET_BACKTEST_ISOLATION"
    DATASET_REVISION_HASHED = "DATASET_REVISION_HASHED"
    RUN_CARD_PERSISTED = "RUN_CARD_PERSISTED"
    BLOCKER_DASHBOARD_PERSISTED = "BLOCKER_DASHBOARD_PERSISTED"
    QUALITY_GATE_GREEN = "QUALITY_GATE_GREEN"


@dataclass(frozen=True, slots=True)
class QAQCAgentProfile:
    """Named QA/QC agent profile for governed improvement reviews."""

    agent_id: str
    display_name: str
    methods: tuple[LeanPillar, ...]
    capabilities: tuple[str, ...]
    authority: str = "GOVERNED_EDITING_AND_IMPROVEMENT_REVIEW"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    promotion_status: str = "RESEARCH_ONLY"

    def __post_init__(self) -> None:
        _require_identity(
            agent_id=self.agent_id,
            display_name=self.display_name,
            authority=self.authority,
        )
        if not self.methods:
            raise ValueError("QAQC-Agent methods cannot be empty")
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("QAQC-Agent methods must be unique")
        if not self.capabilities:
            raise ValueError("QAQC-Agent capabilities cannot be empty")
        if any(not capability.strip() for capability in self.capabilities):
            raise ValueError("QAQC-Agent capabilities cannot be blank")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("QAQC-Agent capabilities must be unique")
        if self.execution_allowed:
            raise ValueError("QAQC-Agent cannot authorize trading execution")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("QAQC-Agent must remain live blocked")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("QAQC-Agent cannot promote research")


_POKA_YOKE_REQUIRED = tuple(PokaYokeCheck)
_DPMO_SCALE = 1_000_000.0
_DPMO_TOLERANCE = 1e-6


def build_qaqc_agent_profile() -> QAQCAgentProfile:
    """Return the named report-only QA/QC continuous-improvement agent."""
    return QAQCAgentProfile(
        agent_id=QAQC_AGENT_ID,
        display_name=QAQC_AGENT_DISPLAY_NAME,
        methods=(
            LeanPillar.FIVE_S,
            LeanPillar.HOSHIN_KANRI,
            LeanPillar.KAIZEN,
            LeanPillar.SIX_SIGMA,
            LeanPillar.POKA_YOKE,
        ),
        capabilities=(
            "FIVE_S_WORKSPACE_HYGIENE_REVIEW",
            "HOSHIN_KANRI_ALIGNMENT_REVIEW",
            "KAIZEN_PDCA_IMPROVEMENT_REVIEW",
            "SIX_SIGMA_DMAIC_DEFECT_REVIEW",
            "POKA_YOKE_ERROR_PROOFING_REVIEW",
            "SAFE_CODE_OR_PROCESS_IMPROVEMENT_PROPOSAL",
        ),
    )


@dataclass(frozen=True, slots=True)
class LeanGovernanceAssessment:
    """Machine-readable lean assessment with no trading authority."""

    pillar: LeanPillar
    subject_id: str
    passed: bool
    blockers: tuple[str, ...]
    kaizen_actions: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    promotion_status: str = "RESEARCH_ONLY"

    def __post_init__(self) -> None:
        _require_identity(subject_id=self.subject_id)
        if self.passed == bool(self.blockers):
            raise ValueError("lean assessment status and blockers disagree")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("lean blockers must be unique")
        if any(not action.strip() for action in self.kaizen_actions):
            raise ValueError("lean kaizen actions cannot be blank")
        if self.execution_allowed:
            raise ValueError("lean governance cannot authorize trading")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("lean governance must remain live blocked")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("lean governance cannot promote research")


@dataclass(frozen=True, slots=True)
class FiveSWorkspaceEvidence:
    """Evidence for applying 5S to repository and artifact operations."""

    workspace_id: str
    observed_at: datetime
    orphan_artifact_paths: tuple[str, ...] = ()
    stale_temp_paths: tuple[str, ...] = ()
    secret_like_paths: tuple[str, ...] = ()
    canonical_quality_command: str = ""
    documentation_index_present: bool = False
    sustain_owner: str = ""
    audit_interval_days: int = 7
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(workspace_id=self.workspace_id)
        _require_aware("5S observation time", self.observed_at)
        path_groups = (
            self.orphan_artifact_paths,
            self.stale_temp_paths,
            self.secret_like_paths,
        )
        if any(not path.strip() for paths in path_groups for path in paths):
            raise ValueError("5S paths cannot be blank")
        if self.audit_interval_days < 1:
            raise ValueError("5S audit interval must be positive")
        if self.execution_allowed:
            raise ValueError("5S evidence cannot authorize trading")


@dataclass(frozen=True, slots=True)
class HoshinObjective:
    """One strategy-deployment objective with explicit validation evidence."""

    objective_id: str
    annual_priority: str
    owner: str
    metric_name: str
    baseline: float
    target: float
    current: float
    due_at: datetime
    linked_blockers: tuple[str, ...]
    validation_artifact_ids: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            objective_id=self.objective_id,
            annual_priority=self.annual_priority,
            owner=self.owner,
            metric_name=self.metric_name,
        )
        _require_aware("Hoshin due_at", self.due_at)
        if any(
            not isfinite(value) for value in (self.baseline, self.target, self.current)
        ):
            raise ValueError("Hoshin metrics must be finite")
        if self.target == self.baseline:
            raise ValueError("Hoshin target must differ from baseline")
        if not self.linked_blockers:
            raise ValueError("Hoshin objective must link at least one blocker")
        if any(not item.strip() for item in self.linked_blockers):
            raise ValueError("Hoshin blockers cannot be blank")
        if len(set(self.validation_artifact_ids)) != len(self.validation_artifact_ids):
            raise ValueError("Hoshin validation artifacts must be unique")
        if any(not item.strip() for item in self.validation_artifact_ids):
            raise ValueError("Hoshin validation artifacts cannot be blank")
        if self.execution_allowed:
            raise ValueError("Hoshin objective cannot authorize trading")

    @property
    def progress_ratio(self) -> float:
        """Return bounded directional progress toward the target."""
        distance = self.target - self.baseline
        raw = (self.current - self.baseline) / distance
        return max(0.0, min(1.0, raw))


@dataclass(frozen=True, slots=True)
class HoshinPlan:
    """Strategy deployment plan for validation-first platform improvement."""

    plan_id: str
    created_at: datetime
    north_star: str
    objectives: tuple[HoshinObjective, ...]
    catchball_reviewed: bool
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(plan_id=self.plan_id, north_star=self.north_star)
        _require_aware("Hoshin plan created_at", self.created_at)
        if not self.objectives:
            raise ValueError("Hoshin plan requires objectives")
        ids = tuple(item.objective_id for item in self.objectives)
        if len(set(ids)) != len(ids):
            raise ValueError("Hoshin objectives must be unique")
        if self.execution_allowed:
            raise ValueError("Hoshin plan cannot authorize trading")


@dataclass(frozen=True, slots=True)
class PokaYokeEvidence:
    """Evidence that irreversible mistakes are prevented by deterministic checks."""

    workflow_id: str
    observed_at: datetime
    passed_checks: tuple[PokaYokeCheck, ...]
    failed_checks: tuple[PokaYokeCheck, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(workflow_id=self.workflow_id)
        _require_aware("Poka-Yoke observation time", self.observed_at)
        combined = (*self.passed_checks, *self.failed_checks)
        if len(set(combined)) != len(combined):
            raise ValueError("Poka-Yoke checks must be unique")
        if self.execution_allowed:
            raise ValueError("Poka-Yoke evidence cannot authorize trading")


@dataclass(frozen=True, slots=True)
class KaizenImprovementEvidence:
    """PDCA evidence for one small, reversible improvement."""

    improvement_id: str
    observed_at: datetime
    stage: KaizenStage
    problem_statement: str
    hypothesis: str
    owner: str
    metric_name: str
    baseline: float
    target: float
    current: float
    linked_blockers: tuple[str, ...]
    experiment_artifact_ids: tuple[str, ...] = ()
    reversible: bool = True
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            improvement_id=self.improvement_id,
            problem_statement=self.problem_statement,
            hypothesis=self.hypothesis,
            owner=self.owner,
            metric_name=self.metric_name,
        )
        _require_aware("Kaizen observation time", self.observed_at)
        if any(
            not isfinite(value) for value in (self.baseline, self.target, self.current)
        ):
            raise ValueError("Kaizen metrics must be finite")
        if self.target == self.baseline:
            raise ValueError("Kaizen target must differ from baseline")
        if not self.linked_blockers:
            raise ValueError("Kaizen improvement must link at least one blocker")
        if any(not item.strip() for item in self.linked_blockers):
            raise ValueError("Kaizen blockers cannot be blank")
        if len(set(self.experiment_artifact_ids)) != len(self.experiment_artifact_ids):
            raise ValueError("Kaizen artifacts must be unique")
        if any(not item.strip() for item in self.experiment_artifact_ids):
            raise ValueError("Kaizen artifacts cannot be blank")
        if self.execution_allowed:
            raise ValueError("Kaizen evidence cannot authorize trading")

    @property
    def progress_ratio(self) -> float:
        """Return bounded directional progress toward the target."""
        distance = self.target - self.baseline
        raw = (self.current - self.baseline) / distance
        return max(0.0, min(1.0, raw))


@dataclass(frozen=True, slots=True)
class SixSigmaProcessEvidence:
    """DMAIC defect-reduction evidence for one governed workflow."""

    process_id: str
    observed_at: datetime
    stage: DmaicStage
    defect_name: str
    opportunities: int
    defects: int
    baseline_dpmo: float
    current_dpmo: float
    target_dpmo: float
    sigma_level: float
    linked_blockers: tuple[str, ...]
    measurement_system_validated: bool = False
    control_plan_artifact_ids: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            process_id=self.process_id,
            defect_name=self.defect_name,
        )
        _require_aware("Six Sigma observation time", self.observed_at)
        if self.opportunities < 1 or self.defects < 0:
            raise ValueError("Six Sigma counts are invalid")
        if self.defects > self.opportunities:
            raise ValueError("Six Sigma defects cannot exceed opportunities")
        values = (
            self.baseline_dpmo,
            self.current_dpmo,
            self.target_dpmo,
            self.sigma_level,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("Six Sigma metrics must be finite")
        if min(values) < 0.0:
            raise ValueError("Six Sigma metrics cannot be negative")
        if abs(self.current_dpmo - self.calculated_dpmo) > _DPMO_TOLERANCE:
            raise ValueError("Six Sigma current DPMO must match defect counts")
        if not self.linked_blockers:
            raise ValueError("Six Sigma process must link at least one blocker")
        if any(not item.strip() for item in self.linked_blockers):
            raise ValueError("Six Sigma blockers cannot be blank")
        if len(set(self.control_plan_artifact_ids)) != len(
            self.control_plan_artifact_ids
        ):
            raise ValueError("Six Sigma control artifacts must be unique")
        if any(not item.strip() for item in self.control_plan_artifact_ids):
            raise ValueError("Six Sigma control artifacts cannot be blank")
        if self.execution_allowed:
            raise ValueError("Six Sigma evidence cannot authorize trading")

    @property
    def calculated_dpmo(self) -> float:
        """Return defects per million opportunities from raw observed counts."""
        return self.defects / self.opportunities * _DPMO_SCALE


def assess_five_s_workspace(
    evidence: FiveSWorkspaceEvidence,
) -> LeanGovernanceAssessment:
    """Assess 5S for repository and artifact hygiene without mutating files."""
    blockers: list[str] = []
    actions: list[str] = []
    if evidence.orphan_artifact_paths:
        blockers.append("FIVE_S_SORT_ORPHAN_ARTIFACTS")
        actions.append("Classify orphan artifacts before archiving or deletion.")
    if not evidence.canonical_quality_command.strip():
        blockers.append("FIVE_S_SET_IN_ORDER_QUALITY_COMMAND_MISSING")
        actions.append("Declare one canonical quality command for this workspace.")
    if evidence.stale_temp_paths:
        blockers.append("FIVE_S_SHINE_STALE_TEMP_REVIEW_REQUIRED")
        actions.append("Review stale temp paths; do not delete locked folders blindly.")
    if not evidence.documentation_index_present:
        blockers.append("FIVE_S_STANDARDIZE_DOC_INDEX_MISSING")
        actions.append("Keep a single documentation index for current operator flow.")
    if not evidence.sustain_owner.strip():
        blockers.append("FIVE_S_SUSTAIN_OWNER_MISSING")
        actions.append("Assign a sustain owner for periodic workspace audits.")
    if evidence.secret_like_paths:
        blockers.append("FIVE_S_SECRET_LIKE_PATH_REVIEW_REQUIRED")
        actions.append("Review secret-like paths with redaction; never print values.")
    return LeanGovernanceAssessment(
        pillar=LeanPillar.FIVE_S,
        subject_id=evidence.workspace_id,
        passed=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        kaizen_actions=tuple(actions),
    )


def assess_kaizen_improvement(
    evidence: KaizenImprovementEvidence,
) -> LeanGovernanceAssessment:
    """Assess a Kaizen improvement as a bounded, reversible PDCA loop."""
    blockers: list[str] = []
    actions: list[str] = []
    if not evidence.reversible:
        blockers.append("KAIZEN_REVERSIBILITY_MISSING")
        actions.append("Add rollback criteria before changing the workflow.")
    if evidence.stage in {KaizenStage.CHECK, KaizenStage.ACT} and not (
        evidence.experiment_artifact_ids
    ):
        blockers.append("KAIZEN_EXPERIMENT_ARTIFACT_MISSING")
        actions.append("Attach deterministic experiment evidence before Check/Act.")
    if evidence.stage is KaizenStage.ACT and evidence.progress_ratio < 1.0:
        blockers.append("KAIZEN_TARGET_NOT_REACHED")
        actions.append("Keep the improvement in Check until the target is reached.")
    return LeanGovernanceAssessment(
        pillar=LeanPillar.KAIZEN,
        subject_id=evidence.improvement_id,
        passed=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        kaizen_actions=tuple(dict.fromkeys(actions)),
    )


def assess_six_sigma_process(
    evidence: SixSigmaProcessEvidence,
) -> LeanGovernanceAssessment:
    """Assess DMAIC defect evidence without granting promotion authority."""
    blockers: list[str] = []
    actions: list[str] = []
    if not evidence.measurement_system_validated:
        blockers.append("SIX_SIGMA_MEASUREMENT_SYSTEM_UNVALIDATED")
        actions.append("Validate the measurement system before interpreting DPMO.")
    if evidence.current_dpmo > evidence.target_dpmo:
        blockers.append("SIX_SIGMA_TARGET_DPMO_NOT_MET")
        actions.append("Continue Analyze/Improve before moving to Control.")
    if evidence.stage is DmaicStage.CONTROL and not evidence.control_plan_artifact_ids:
        blockers.append("SIX_SIGMA_CONTROL_PLAN_MISSING")
        actions.append("Attach a control plan before accepting sustained capability.")
    if evidence.stage in {DmaicStage.IMPROVE, DmaicStage.CONTROL} and (
        evidence.current_dpmo >= evidence.baseline_dpmo
    ):
        blockers.append("SIX_SIGMA_DEFECT_REDUCTION_NOT_OBSERVED")
        actions.append("Recheck root cause and improve controls before claiming gain.")
    return LeanGovernanceAssessment(
        pillar=LeanPillar.SIX_SIGMA,
        subject_id=evidence.process_id,
        passed=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        kaizen_actions=tuple(dict.fromkeys(actions)),
    )


def assess_hoshin_plan(
    plan: HoshinPlan, *, as_of: datetime
) -> LeanGovernanceAssessment:
    """Assess strategic alignment and validation evidence for a Hoshin plan."""
    _require_aware("Hoshin assessment time", as_of)
    blockers: list[str] = []
    actions: list[str] = []
    if not plan.catchball_reviewed:
        blockers.append("HOSHIN_CATCHBALL_REVIEW_MISSING")
        actions.append("Run catchball review before treating objectives as aligned.")
    for objective in plan.objectives:
        if objective.due_at < as_of and objective.progress_ratio < 1.0:
            blockers.append(f"HOSHIN_OBJECTIVE_OVERDUE:{objective.objective_id}")
            actions.append(
                f"Escalate overdue objective {objective.objective_id} with a "
                "countermeasure owner."
            )
        if not objective.validation_artifact_ids:
            blockers.append(
                f"HOSHIN_VALIDATION_ARTIFACT_MISSING:{objective.objective_id}"
            )
            actions.append(
                "Attach validation artifacts before accepting "
                f"{objective.objective_id}."
            )
    return LeanGovernanceAssessment(
        pillar=LeanPillar.HOSHIN_KANRI,
        subject_id=plan.plan_id,
        passed=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        kaizen_actions=tuple(dict.fromkeys(actions)),
    )


def assess_poka_yoke_workflow(
    evidence: PokaYokeEvidence,
) -> LeanGovernanceAssessment:
    """Assess mandatory mistake-proofing checks for a governed workflow."""
    blockers: list[str] = []
    actions: list[str] = []
    passed = set(evidence.passed_checks)
    failed = set(evidence.failed_checks)
    for check in _POKA_YOKE_REQUIRED:
        if check in failed:
            blockers.append(f"POKA_YOKE_CHECK_FAILED:{check.value}")
            actions.append(f"Fix failed error-proofing check: {check.value}.")
        elif check not in passed:
            blockers.append(f"POKA_YOKE_CHECK_MISSING:{check.value}")
            actions.append(f"Add mandatory error-proofing check: {check.value}.")
    return LeanGovernanceAssessment(
        pillar=LeanPillar.POKA_YOKE,
        subject_id=evidence.workflow_id,
        passed=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        kaizen_actions=tuple(dict.fromkeys(actions)),
    )

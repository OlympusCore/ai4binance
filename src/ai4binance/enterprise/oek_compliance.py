"""OEK constitution compliance checks for enterprise governance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class OekComplianceStatus(StrEnum):
    PASSED = "PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class OekChangeKind(StrEnum):
    AGENT = "AGENT"
    SKILL = "SKILL"
    WORKFLOW = "WORKFLOW"
    CONFIG = "CONFIG"


_OEK_DOC_PATH = Path("docs") / "governance/policy_organization_constitution_handbook.md"
_EXPECTED_FRONTMATTER = {
    "canonical_path": "docs/governance/policy_organization_constitution_handbook.md",
    "document_code": "AI4B-OEK-003",
    "version": "3.0.0",
    "source_of_truth_scope": "family_index",
}
_REQUIRED_CONSTITUTION_TERMS = (
    "AI4BINANCE-OEK-CANONICAL-CONSTITUTION",
    "REPOSITORY CONTENT LANGUAGE LOCK",
    "repository_validator",
    "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
    "canonical constitution file is",
    "docs/governance/framework_core_vnext_governance.md",
    "Hierarchy of Norms",
    "IMMUTABLE CORE PRINCIPLES",
    "Capital Protection",
    "Human Oversight",
    "Fail-Closed",
    "Controlled Learning",
)
_REQUIRED_LIVE_BLOCKED_TERMS = (
    "NO_TRADE",
    "RESEARCH_ONLY",
    "LIVE_ORDER_BLOCKED",
    "does not grant permission for live trading",
)
_REQUIRED_GAP_ANALYSIS_TERMS = (
    "agent, workflow, config, model, strategy",
    "gap analysis",
    "risk, privacy/security",
    "test",
)
_DEFAULT_CHANGE_CONTROLS = (
    "OEK_CONSTITUTION_COMPLIANCE",
    "HUMAN_REVIEW_REQUIRED",
    "LIVE_ORDER_BLOCKED",
    "AUDIT_TRAIL_REQUIRED",
)
_CHANGE_KIND_CONTROLS: dict[OekChangeKind, tuple[str, ...]] = {
    OekChangeKind.AGENT: (
        "AGENT_CHARTER_REQUIRED",
        "OWNER_REQUIRED",
        "TOOL_ALLOWLIST_REQUIRED",
        "KILL_CRITERIA_REQUIRED",
    ),
    OekChangeKind.SKILL: (
        "SKILLS_AUDIT_REQUIRED",
        "NO_INSTALL_OR_EXECUTE_WITHOUT_REVIEW",
        "SUPPLY_CHAIN_REVIEW_REQUIRED",
    ),
    OekChangeKind.WORKFLOW: (
        "WORKFLOW_OWNER_REQUIRED",
        "SEGREGATION_OF_DUTIES_REQUIRED",
        "ROLLBACK_PLAN_REQUIRED",
    ),
    OekChangeKind.CONFIG: (
        "CONFIG_DIFF_REVIEW_REQUIRED",
        "RISK_PRIVACY_SECURITY_IMPACT_REQUIRED",
        "ROLLBACK_PLAN_REQUIRED",
    ),
}
_PROHIBITED_AUTHORITY_TERMS = (
    "FINAL_SIGNAL_AUTHORITY",
    "RISK_APPROVAL_AUTHORITY",
    "LIVE_ORDER_AUTHORITY",
    "SELF_AUTHORIZED_LIVE",
    "UNAPPROVED_RISK_INCREASE",
    "SECRET_ACCESS",
    "WITHDRAWAL_AUTHORITY",
)


@dataclass(frozen=True, slots=True)
class OekComplianceReport:
    document_path: str
    status: OekComplianceStatus
    version: str
    document_code: str
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    corrective_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.document_path.strip():
            raise ValueError("OEK document path cannot be empty")
        if self.status is OekComplianceStatus.PASSED and self.blockers:
            raise ValueError("passed OEK compliance cannot contain blockers")
        if self.status is OekComplianceStatus.REVISION_REQUIRED and not self.blockers:
            raise ValueError("revised OEK compliance requires blockers")
        if self.execution_allowed:
            raise ValueError("OEK compliance cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("OEK compliance cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("OEK compliance must remain live blocked")


@dataclass(frozen=True, slots=True)
class OekChangeManifest:
    change_id: str
    change_kind: OekChangeKind
    subject_ref: str
    changed_paths: tuple[str, ...]
    summary: str
    evidence_refs: tuple[str, ...]
    declared_controls: tuple[str, ...]
    requested_authorities: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("OEK change id", self.change_id)
        _require_text("OEK change subject", self.subject_ref)
        _require_text("OEK change summary", self.summary)
        _require_unique_text("OEK change paths", self.changed_paths)
        _require_unique_text("OEK change evidence refs", self.evidence_refs)
        _require_unique_text("OEK change controls", self.declared_controls)
        _require_unique_text("OEK requested authorities", self.requested_authorities)
        if self.execution_allowed:
            raise ValueError("OEK change manifest cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("OEK change manifest cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("OEK change manifest must remain live blocked")


@dataclass(frozen=True, slots=True)
class OekGapAnalysisReport:
    change_id: str
    change_kind: OekChangeKind
    subject_ref: str
    document_report: OekComplianceReport
    status: OekComplianceStatus
    required_controls: tuple[str, ...]
    missing_controls: tuple[str, ...]
    prohibited_authorities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    corrective_actions: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("OEK gap change id", self.change_id)
        _require_text("OEK gap subject", self.subject_ref)
        _require_unique_text("OEK gap required controls", self.required_controls)
        _require_unique_text("OEK gap missing controls", self.missing_controls)
        _require_unique_text(
            "OEK gap prohibited authorities", self.prohibited_authorities
        )
        _require_unique_text("OEK gap evidence refs", self.evidence_refs)
        _require_unique_text("OEK gap blockers", self.blockers)
        _require_unique_text("OEK gap corrective actions", self.corrective_actions)
        if self.status is OekComplianceStatus.PASSED and self.blockers:
            raise ValueError("passed OEK gap analysis cannot contain blockers")
        if self.status is OekComplianceStatus.REVISION_REQUIRED and not self.blockers:
            raise ValueError("revised OEK gap analysis requires blockers")
        if self.execution_allowed:
            raise ValueError("OEK gap analysis cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("OEK gap analysis cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("OEK gap analysis must remain live blocked")


def audit_oek_constitution(workspace_root: Path) -> OekComplianceReport:
    doc_path = workspace_root / _OEK_DOC_PATH
    if not doc_path.is_file():
        return OekComplianceReport(
            document_path=_OEK_DOC_PATH.as_posix(),
            status=OekComplianceStatus.REVISION_REQUIRED,
            version="",
            document_code="",
            evidence_refs=(
                "doc:docs/governance/policy_organization_constitution_handbook.md",
            ),
            blockers=("OEK_CONSTITUTION_DOC_MISSING",),
            corrective_actions=(
                "Create docs/governance/policy_organization_constitution_handbook.md.",
            ),
        )

    text = doc_path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    blockers: list[str] = []
    corrective_actions: list[str] = []

    for key, expected in _EXPECTED_FRONTMATTER.items():
        observed = frontmatter.get(key, "")
        if observed != expected:
            blockers.append(f"OEK_FRONTMATTER_INVALID:{key}")
            corrective_actions.append(f"Set OEK frontmatter {key} to {expected}.")

    missing_terms = tuple(
        term for term in _REQUIRED_CONSTITUTION_TERMS if term not in text
    )
    for term in missing_terms:
        blockers.append(f"OEK_CONSTITUTION_TERM_MISSING:{term}")
        corrective_actions.append(f"Restore OEK constitutional term {term}.")

    missing_live_terms = tuple(
        term for term in _REQUIRED_LIVE_BLOCKED_TERMS if term not in text
    )
    for term in missing_live_terms:
        blockers.append(f"OEK_LIVE_BOUNDARY_TERM_MISSING:{term}")
        corrective_actions.append(f"Restore OEK live-blocked boundary term {term}.")

    missing_gap_terms = tuple(
        term for term in _REQUIRED_GAP_ANALYSIS_TERMS if term not in text
    )
    for term in missing_gap_terms:
        blockers.append(f"OEK_GAP_ANALYSIS_TERM_MISSING:{term}")
        corrective_actions.append(f"Restore OEK gap-analysis term {term}.")

    version = frontmatter.get("version", "")
    document_code = frontmatter.get("document_code", "")
    return OekComplianceReport(
        document_path=_OEK_DOC_PATH.as_posix(),
        status=(
            OekComplianceStatus.REVISION_REQUIRED
            if blockers
            else OekComplianceStatus.PASSED
        ),
        version=version,
        document_code=document_code,
        evidence_refs=(
            "doc:docs/governance/policy_organization_constitution_handbook.md",
            f"oek-version:{version or 'missing'}",
            f"oek-document-code:{document_code or 'missing'}",
            f"constitution-term-count:{len(_REQUIRED_CONSTITUTION_TERMS)}",
            f"live-boundary-term-count:{len(_REQUIRED_LIVE_BLOCKED_TERMS)}",
            f"gap-analysis-term-count:{len(_REQUIRED_GAP_ANALYSIS_TERMS)}",
        ),
        blockers=tuple(dict.fromkeys(blockers)),
        corrective_actions=tuple(dict.fromkeys(corrective_actions)),
    )


def analyze_oek_change_gap(
    workspace_root: Path,
    manifest: OekChangeManifest,
) -> OekGapAnalysisReport:
    document_report = audit_oek_constitution(workspace_root)
    required_controls = _required_controls_for(manifest.change_kind)
    declared_controls = set(manifest.declared_controls)
    missing_controls = tuple(
        control for control in required_controls if control not in declared_controls
    )
    requested_authorities = set(manifest.requested_authorities)
    prohibited_authorities = tuple(
        authority
        for authority in _PROHIBITED_AUTHORITY_TERMS
        if authority in requested_authorities
    )
    blockers = [
        *(f"OEK_CHANGE_CONTROL_MISSING:{control}" for control in missing_controls),
        *(
            f"OEK_PROHIBITED_AUTHORITY_REQUESTED:{authority}"
            for authority in prohibited_authorities
        ),
        *document_report.blockers,
    ]
    corrective_actions = [
        *(
            f"Attach OEK change control evidence {control}."
            for control in missing_controls
        ),
        *(
            f"Remove prohibited authority request {authority}."
            for authority in prohibited_authorities
        ),
        *document_report.corrective_actions,
    ]
    evidence_refs = (
        f"change:{manifest.change_id}",
        f"change-kind:{manifest.change_kind.value}",
        f"subject:{manifest.subject_ref}",
        *(f"path:{path}" for path in manifest.changed_paths),
        *manifest.evidence_refs,
        *document_report.evidence_refs,
    )
    return OekGapAnalysisReport(
        change_id=manifest.change_id,
        change_kind=manifest.change_kind,
        subject_ref=manifest.subject_ref,
        document_report=document_report,
        status=(
            OekComplianceStatus.REVISION_REQUIRED
            if blockers
            else OekComplianceStatus.PASSED
        ),
        required_controls=required_controls,
        missing_controls=missing_controls,
        prohibited_authorities=prohibited_authorities,
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        blockers=tuple(dict.fromkeys(blockers)),
        corrective_actions=tuple(dict.fromkeys(corrective_actions)),
    )


def required_controls_for_change_kind(
    change_kind: OekChangeKind,
) -> tuple[str, ...]:
    """Return OEK controls that every change manifest must declare."""
    return _required_controls_for(change_kind)


def build_oek_change_manifest(
    *,
    change_id: str,
    change_kind: OekChangeKind,
    subject_ref: str,
    changed_paths: tuple[str, ...],
    summary: str,
    evidence_refs: tuple[str, ...],
    declared_controls: tuple[str, ...] = (),
    requested_authorities: tuple[str, ...] = (),
) -> OekChangeManifest:
    """Build a manifest with OEK-required controls included by default."""
    required_controls = required_controls_for_change_kind(change_kind)
    return OekChangeManifest(
        change_id=change_id,
        change_kind=change_kind,
        subject_ref=subject_ref,
        changed_paths=changed_paths,
        summary=summary,
        evidence_refs=evidence_refs,
        declared_controls=tuple(
            dict.fromkeys((*required_controls, *declared_controls))
        ),
        requested_authorities=requested_authorities,
    )


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    lines = text.splitlines()
    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        frontmatter[key.strip()] = raw_value.strip().strip('"')
    return frontmatter


def _required_controls_for(change_kind: OekChangeKind) -> tuple[str, ...]:
    return (
        *_DEFAULT_CHANGE_CONTROLS,
        *_CHANGE_KIND_CONTROLS[change_kind],
    )


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")

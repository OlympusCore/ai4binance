"""Typed contracts for read-only Agent Skills governance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SkillSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKER = "BLOCKER"


class SkillAuthority(StrEnum):
    ADVISORY_ONLY = "ADVISORY_ONLY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class SkillValidationIssue:
    code: str
    severity: SkillSeverity
    message: str
    path: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip() or not self.path.strip():
            raise ValueError("skill validation issue fields cannot be blank")


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_dir: str
    skill_file: str
    name: str
    description: str
    license: str | None
    compatibility: str | None
    metadata: dict[str, str]
    allowed_tools: str | None
    body: str
    referenced_files: tuple[str, ...]
    optional_directories: tuple[str, ...]
    root_files: tuple[str, ...]
    version: str | None = None
    owner: str | None = None
    trust_level: str | None = None
    last_reviewed: str | None = None
    trigger_examples: tuple[str, ...] = ()
    source_kind: str = "LOCAL_REPO_SKILL"
    authority: SkillAuthority = SkillAuthority.ADVISORY_ONLY
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("skill manifests cannot grant execution authority")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("skill manifests cannot promote beyond research")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("skill manifests must remain live blocked")
        if self.authority not in SkillAuthority:
            raise ValueError("skill authority is invalid")


@dataclass(frozen=True, slots=True)
class SkillAuditReport:
    root: str
    skill_count: int
    issue_count: int
    blocker_count: int
    high_risk_capability_count: int
    skills: tuple[SkillManifest, ...]
    issues: tuple[SkillValidationIssue, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.skill_count != len(self.skills):
            raise ValueError("skill audit count does not match skills")
        if self.issue_count != len(self.issues):
            raise ValueError("skill audit count does not match issues")
        if self.blocker_count != len(self.blockers):
            raise ValueError("skill audit blocker count does not match blockers")
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("skill audit cannot grant authority")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("skill audit cannot promote beyond research")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("skill audit must remain live blocked")

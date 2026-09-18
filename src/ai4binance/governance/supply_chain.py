"""Quarantine-first external skill and plugin supply-chain governance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

from ai4binance.research_catalog import CatalogStatus, ResearchCatalogEntry

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class ExternalCapability(StrEnum):
    ADVISORY_READ_ONLY = "ADVISORY_READ_ONLY"
    FILESYSTEM_WRITE = "FILESYSTEM_WRITE"
    NETWORK = "NETWORK"
    SECRET_READ = "SECRET_READ"  # noqa: S105  # nosec B105
    SUBPROCESS = "SUBPROCESS"
    ARBITRARY_CODE = "ARBITRARY_CODE"


_HIGH_RISK_CAPABILITIES = frozenset(
    {
        ExternalCapability.FILESYSTEM_WRITE,
        ExternalCapability.NETWORK,
        ExternalCapability.SECRET_READ,
        ExternalCapability.SUBPROCESS,
        ExternalCapability.ARBITRARY_CODE,
    }
)

_QUARANTINE_ALLOWED_CATALOG_STATUSES = frozenset(
    {CatalogStatus.DISCOVERED, CatalogStatus.HYPOTHESIS_REGISTERED}
)


@dataclass(frozen=True, slots=True)
class ExternalComponentManifest:
    """Pinned evidence for review; the manifest cannot install or execute code."""

    component_id: str
    source_url: str
    pinned_revision: str
    license_id: str
    license_sha256: str
    content_sha256: str
    declared_capabilities: tuple[ExternalCapability, ...]
    reviewed_at: datetime
    execution_allowed: bool = False
    installation_allowed: bool = False

    def __post_init__(self) -> None:
        text_values = (self.component_id, self.license_id)
        if any(not item.strip() or len(item) > 200 for item in text_values):
            raise ValueError("external component identity fields are invalid")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError("external component source must be credential-free HTTPS")
        if not _GIT_COMMIT.fullmatch(self.pinned_revision):
            raise ValueError("external component revision must be a pinned commit SHA")
        if not _SHA256.fullmatch(self.license_sha256) or not _SHA256.fullmatch(
            self.content_sha256
        ):
            raise ValueError("external component evidence hashes are invalid")
        if not self.declared_capabilities or len(
            set(self.declared_capabilities)
        ) != len(self.declared_capabilities):
            raise ValueError(
                "external component capabilities must be non-empty and unique"
            )
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError(
                "external component review timestamp must be timezone-aware"
            )
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("external component manifest cannot grant authority")


@dataclass(frozen=True, slots=True)
class SupplyChainAssessment:
    component_id: str
    approved_for_isolated_experiment: bool
    quarantine_required: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    installation_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.approved_for_isolated_experiment == bool(self.blockers):
            raise ValueError("supply-chain assessment and blockers disagree")
        if self.quarantine_required != bool(self.blockers):
            raise ValueError("supply-chain quarantine and blockers disagree")
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("supply-chain assessment cannot grant authority")


@dataclass(frozen=True, slots=True)
class ExternalSkillManifest:
    """External Agent Skill evidence bound to supply-chain review.

    The Agent Skills `allowed-tools` field is treated as an advisory declaration,
    not as an enforceable security gate.
    """

    component: ExternalComponentManifest
    skill_name: str
    allowed_tools_declared: str | None = None
    scripts_declared: bool = False
    references_declared: bool = False
    execution_allowed: bool = False
    installation_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _SKILL_NAME.fullmatch(self.skill_name) or "--" in self.skill_name:
            raise ValueError("external skill name is invalid")
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("external skill manifest cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("external skill manifest must remain live-order blocked")


def assess_external_component(
    manifest: ExternalComponentManifest,
    *,
    license_compatible: bool,
    security_scan_passed: bool,
    sandbox_review_passed: bool,
    human_approved: bool,
) -> SupplyChainAssessment:
    blockers: list[str] = []
    checks = (
        (license_compatible, "EXTERNAL_LICENSE_NOT_APPROVED"),
        (security_scan_passed, "EXTERNAL_SECURITY_SCAN_MISSING"),
        (sandbox_review_passed, "EXTERNAL_SANDBOX_REVIEW_MISSING"),
        (human_approved, "EXTERNAL_HUMAN_APPROVAL_MISSING"),
    )
    blockers.extend(code for passed, code in checks if not passed)
    if set(manifest.declared_capabilities) & _HIGH_RISK_CAPABILITIES:
        blockers.append("EXTERNAL_HIGH_RISK_CAPABILITY_DECLARED")
    return SupplyChainAssessment(
        component_id=manifest.component_id,
        approved_for_isolated_experiment=not blockers,
        quarantine_required=bool(blockers),
        blockers=tuple(blockers),
    )


def assess_external_skill(
    manifest: ExternalSkillManifest,
    *,
    license_compatible: bool,
    security_scan_passed: bool,
    sandbox_review_passed: bool,
    human_approved: bool,
) -> SupplyChainAssessment:
    base = assess_external_component(
        manifest.component,
        license_compatible=license_compatible,
        security_scan_passed=security_scan_passed,
        sandbox_review_passed=sandbox_review_passed,
        human_approved=human_approved,
    )
    blockers = list(base.blockers)
    if manifest.allowed_tools_declared:
        blockers.append("EXTERNAL_ALLOWED_TOOLS_UNENFORCED")
    if manifest.scripts_declared:
        blockers.append("EXTERNAL_SKILL_SCRIPT_DECLARED")
    if manifest.references_declared and not security_scan_passed:
        blockers.append("EXTERNAL_SKILL_REFERENCES_UNREVIEWED")
    blockers = list(dict.fromkeys(blockers))
    return SupplyChainAssessment(
        component_id=manifest.component.component_id,
        approved_for_isolated_experiment=not blockers,
        quarantine_required=bool(blockers),
        blockers=tuple(blockers),
    )


@dataclass(frozen=True, slots=True)
class ExternalResearchIntake:
    """Bind an external research record to its immutable supply-chain evidence.

    This is intentionally an intake-only contract.  Passing its checks permits
    at most a human-governed, isolated reproduction task; it cannot install,
    execute, or authorize any trading capability.
    """

    catalog_entry: ResearchCatalogEntry
    manifest: ExternalComponentManifest
    assessment: SupplyChainAssessment
    execution_allowed: bool = False
    installation_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        entry = self.catalog_entry
        manifest = self.manifest
        assessment = self.assessment
        if entry.entry_id != manifest.component_id:
            raise ValueError("external intake component identity must match catalog")
        if entry.source_url != manifest.source_url:
            raise ValueError("external intake source URL must match manifest")
        if entry.source_revision != manifest.pinned_revision:
            raise ValueError("external intake revision must match pinned manifest")
        if entry.license_id != manifest.license_id:
            raise ValueError("external intake license must match manifest")
        if assessment.component_id != manifest.component_id:
            raise ValueError("external intake assessment identity must match manifest")
        if self.execution_allowed or self.installation_allowed:
            raise ValueError("external research intake cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("external research intake must remain live-order blocked")
        if assessment.quarantine_required:
            missing_blockers = set(assessment.blockers).difference(entry.blockers)
            if missing_blockers:
                raise ValueError(
                    "external intake catalog must retain supply-chain blockers"
                )
            if entry.status not in _QUARANTINE_ALLOWED_CATALOG_STATUSES:
                raise ValueError(
                    "quarantined external intake cannot enter reproduction queue"
                )

    @property
    def reproduction_allowed(self) -> bool:
        """Whether a reviewed source may be queued for isolated reproduction."""
        return (
            self.assessment.approved_for_isolated_experiment
            and self.catalog_entry.status is CatalogStatus.REPRODUCTION_PENDING
        )

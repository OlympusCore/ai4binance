"""Deterministic quality and governance gates for repository evidence controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from ai4binance import governance_primitives as governance_primitives_module
from ai4binance.enterprise.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    WorkflowIdentity,
)
from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    ConsequentialTraceKind,
    TraceabilityAuditReport,
    TraceabilityRequirement,
    TraceabilityStatus,
    canonical_trace_journal_path,
)
from ai4binance.governance.constitution_sync import (
    GovernanceAlignmentAuditReport,
    GovernanceAlignmentStatus,
    QualityGateEvidence,
    WorkspaceAttestation,
    audit_governance_alignment,
    build_quality_gate_workspace_attestation,
)
from ai4binance.governance.framework import (
    ChangeApprovalClass,
    ConstitutionalChangeControl,
)
from ai4binance.governance_primitives import TECHNICAL_QUALITY_PRIMARY_STATUS

DEFAULT_APPROVAL_RECORD_REPORT = (
    "runtime/artifacts/quality/gate/approval_record_latest.json"
)


class GovernanceGateStatus(StrEnum):
    PASS = "P" + "ASS"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


class DeterministicSubGateStatus(StrEnum):
    PASS = "P" + "ASS"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


class DeterministicGateDecision(StrEnum):
    PASS = "P" + "ASS"
    PASS_WITH_WARNINGS = "PASS_WITH_" + "WARNINGS"
    BLOCKED = "BLOCKED"


class GovernanceEvidenceLifecycleStage(StrEnum):
    CHANGESET_IDENTIFIED = "CHANGESET_IDENTIFIED"
    TECHNICAL_TRUTH_CONFIRMED = "TECHNICAL_TRUTH_CONFIRMED"
    POLICY_ELIGIBLE = "POLICY_ELIGIBLE"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    CONSEQUENTIAL_AUTHORITY_CONFIRMED = "CONSEQUENTIAL_AUTHORITY_CONFIRMED"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class ApprovalVerificationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PASS = "P" + "ASS"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


@dataclass(frozen=True, slots=True)
class GovernanceTestEvidence:
    check_id: str
    command: str
    selected_tests: tuple[str, ...]
    passed: bool
    failure_detail: str = ""
    evidence_source: str = ""
    evidence_path: str = ""
    evidence_sha256: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("governance check id", self.check_id)
        _require_non_empty("governance check command", self.command)
        _require_unique_nonblank("governance selected tests", self.selected_tests)
        _validate_optional_artifact_lineage(
            artifact_name="governance test evidence",
            evidence_source=self.evidence_source,
            evidence_path=self.evidence_path,
            evidence_sha256=self.evidence_sha256,
        )
        if self.passed and self.failure_detail.strip():
            raise ValueError("passing governance test evidence cannot contain failure")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("governance test evidence cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "command": self.command,
            "selected_tests": list(self.selected_tests),
            "passed": self.passed,
            "failure_detail": self.failure_detail,
            "evidence_source": self.evidence_source,
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class SecurityScanEvidence:
    check_id: str
    command: str
    passed: bool
    failure_detail: str = ""
    evidence_source: str = ""
    evidence_path: str = ""
    evidence_sha256: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("security scan id", self.check_id)
        _require_non_empty("security scan command", self.command)
        _validate_optional_artifact_lineage(
            artifact_name="security scan evidence",
            evidence_source=self.evidence_source,
            evidence_path=self.evidence_path,
            evidence_sha256=self.evidence_sha256,
        )
        if self.passed and self.failure_detail.strip():
            raise ValueError("passing security scan cannot contain failure")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("security scan evidence cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "command": self.command,
            "passed": self.passed,
            "failure_detail": self.failure_detail,
            "evidence_source": self.evidence_source,
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class RepositoryValidatorEvidence:
    status: str
    report_path: str
    blocker_count: int
    finding_count: int
    repository_health_score: int
    blocker_ids: tuple[str, ...]
    findings: tuple[RepositoryValidatorFindingEvidence, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("repository validator status", self.status)
        _require_non_empty("repository validator report path", self.report_path)
        _require_unique_nonblank("repository validator blocker ids", self.blocker_ids)
        for name, value in (
            ("repository validator blocker_count", self.blocker_count),
            ("repository validator finding_count", self.finding_count),
            (
                "repository validator repository_health_score",
                self.repository_health_score,
            ),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.repository_health_score > 100:
            raise ValueError(
                "repository validator repository_health_score must be <= 100"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("repository validator evidence cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "report_path": self.report_path,
            "blocker_count": self.blocker_count,
            "finding_count": self.finding_count,
            "repository_health_score": self.repository_health_score,
            "blocker_ids": list(self.blocker_ids),
            "findings": [finding.to_payload() for finding in self.findings],
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class RepositoryValidatorFindingEvidence:
    control_family: str
    domain: str
    severity: str
    rule_id: str
    path: str
    blocker: bool
    finding_id: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(
            "repository validator finding control_family",
            self.control_family,
        )
        _require_non_empty("repository validator finding domain", self.domain)
        _require_non_empty("repository validator finding severity", self.severity)
        _require_non_empty("repository validator finding rule_id", self.rule_id)
        _require_non_empty("repository validator finding path", self.path)
        if self.finding_id:
            _require_non_empty("repository validator finding_id", self.finding_id)

    def to_payload(self) -> dict[str, object]:
        return {
            "control_family": self.control_family,
            "domain": self.domain,
            "severity": self.severity,
            "rule_id": self.rule_id,
            "path": self.path,
            "blocker": self.blocker,
            "finding_id": self.finding_id,
        }


@dataclass(frozen=True, slots=True)
class DeterministicSubGateCheck:
    check_id: str
    status: DeterministicSubGateStatus
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("sub-gate check_id", self.check_id)
        _require_unique_nonblank("sub-gate blockers", self.blockers)
        if self.status is DeterministicSubGateStatus.PASS and self.blockers:
            raise ValueError("passing sub-gate check cannot contain blockers")
        if (
            self.status is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
            and not self.blockers
        ):
            raise ValueError("blocked sub-gate check requires blockers")

    def to_payload(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class RepositoryHygieneGateEvidence:
    status: DeterministicSubGateStatus
    checks: tuple[DeterministicSubGateCheck, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_unique_nonblank("repository hygiene blockers", self.blockers)
        if self.status is DeterministicSubGateStatus.PASS and self.blockers:
            raise ValueError("passing repository hygiene gate cannot contain blockers")
        if (
            self.status is DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
            and not self.blockers
        ):
            raise ValueError("blocked repository hygiene gate requires blockers")

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "checks": [check.to_payload() for check in self.checks],
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class AuthorityDocumentSnapshot:
    authority_document_id: str
    version: str
    canonical_path: str
    sha256: str
    authority_level: str
    source_of_truth: bool

    def __post_init__(self) -> None:
        _require_non_empty("authority document id", self.authority_document_id)
        _require_non_empty("authority document version", self.version)
        _require_non_empty("authority canonical path", self.canonical_path)
        _require_non_empty("authority sha256", self.sha256)
        _require_non_empty("authority level", self.authority_level)
        if "\\" in self.canonical_path or self.canonical_path.startswith("/"):
            raise ValueError(
                "authority canonical path must be repository-relative posix path"
            )
        if not _SEMVER_RE.fullmatch(self.version):
            raise ValueError(
                "authority document version must be semantic MAJOR.MINOR.PATCH"
            )
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError(
                "authority document sha256 must be a lowercase sha256 hex digest"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "authority_document_id": self.authority_document_id,
            "version": self.version,
            "canonical_path": self.canonical_path,
            "sha256": self.sha256,
            "authority_level": self.authority_level,
            "source_of_truth": self.source_of_truth,
        }


@dataclass(frozen=True, slots=True)
class AuthorityBaselineEvidence:
    status: DeterministicSubGateStatus
    blockers: tuple[str, ...]
    authority_snapshot: tuple[AuthorityDocumentSnapshot, ...]
    authority_snapshot_sha256: str

    def __post_init__(self) -> None:
        _require_unique_nonblank("authority baseline blockers", self.blockers)
        _require_unique_nonblank(
            "authority baseline document ids",
            tuple(item.authority_document_id for item in self.authority_snapshot),
        )
        _require_unique_nonblank(
            "authority baseline canonical paths",
            tuple(item.canonical_path for item in self.authority_snapshot),
        )
        _require_non_empty(
            "authority baseline snapshot sha256", self.authority_snapshot_sha256
        )
        if not _SHA256_RE.fullmatch(self.authority_snapshot_sha256):
            raise ValueError(
                "authority baseline snapshot sha256 must be a lowercase "
                "sha256 hex digest"
            )
        if self.status is DeterministicSubGateStatus.PASS:
            if self.blockers:
                raise ValueError("passing authority baseline cannot contain blockers")
            if not self.authority_snapshot:
                raise ValueError(
                    "passing authority baseline requires authority snapshot"
                )
        elif not self.blockers:
            raise ValueError("blocked authority baseline requires blockers")

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "blockers": list(self.blockers),
            "authority_snapshot": [
                snapshot.to_payload() for snapshot in self.authority_snapshot
            ],
            "authority_snapshot_sha256": self.authority_snapshot_sha256,
            "authority_sources": [
                snapshot.canonical_path for snapshot in self.authority_snapshot
            ],
        }


@dataclass(frozen=True, slots=True)
class ConstitutionSyncGateEvidence:
    status: DeterministicSubGateStatus
    blockers: tuple[str, ...]
    selected_tests: tuple[str, ...]
    command: str
    alignment_status: str
    alignment_findings: tuple[dict[str, str], ...]

    def __post_init__(self) -> None:
        _require_non_empty("constitution sync command", self.command)
        _require_unique_nonblank(
            "constitution sync selected tests", self.selected_tests
        )
        _require_unique_nonblank("constitution sync blockers", self.blockers)

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "blockers": list(self.blockers),
            "selected_tests": list(self.selected_tests),
            "command": self.command,
            "alignment_status": self.alignment_status,
            "alignment_findings": list(self.alignment_findings),
        }


@dataclass(frozen=True, slots=True)
class RepositoryConformanceGateEvidence:
    status: DeterministicSubGateStatus
    blockers: tuple[str, ...]
    validator: RepositoryValidatorEvidence

    def __post_init__(self) -> None:
        _require_unique_nonblank("repository conformance gate blockers", self.blockers)

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "blockers": list(self.blockers),
            "validator": self.validator.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class QualityEvidenceGateEvidence:
    status: DeterministicSubGateStatus
    blockers: tuple[str, ...]
    quality_gate: QualityGateEvidence

    def __post_init__(self) -> None:
        _require_unique_nonblank("quality evidence gate blockers", self.blockers)

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "blockers": list(self.blockers),
            "quality_gate": _quality_gate_payload(self.quality_gate),
        }


@dataclass(frozen=True, slots=True)
class GovernanceChangeSet:
    repository_root: Path
    git_commit: str
    staged_paths: tuple[str, ...] = ()
    unstaged_paths: tuple[str, ...] = ()
    untracked_governed_paths: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    change_set_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError("governance change set repository_root must be absolute")
        _require_non_empty("governance change set git_commit", self.git_commit)
        staged_paths = _normalize_paths(self.staged_paths)
        unstaged_paths = _normalize_paths(self.unstaged_paths)
        untracked_paths = _normalize_paths(self.untracked_governed_paths)
        changed_paths = _normalize_paths(self.changed_paths)
        if staged_paths or unstaged_paths or untracked_paths:
            derived_paths = tuple(
                dict.fromkeys((*staged_paths, *unstaged_paths, *untracked_paths))
            )
            if changed_paths and changed_paths != derived_paths:
                raise ValueError(
                    "governance change set changed_paths must match derived paths"
                )
            changed_paths = derived_paths
        object.__setattr__(self, "staged_paths", staged_paths)
        object.__setattr__(self, "unstaged_paths", unstaged_paths)
        object.__setattr__(self, "untracked_governed_paths", untracked_paths)
        object.__setattr__(self, "changed_paths", changed_paths)
        recorded_sha256 = self.change_set_sha256.lower()
        calculated_sha256 = _canonical_sha256(
            {
                "repository_root": str(self.repository_root),
                "git_commit": self.git_commit,
                "staged_paths": list(staged_paths),
                "unstaged_paths": list(unstaged_paths),
                "untracked_governed_paths": list(untracked_paths),
                "changed_paths": list(changed_paths),
            }
        )
        if recorded_sha256:
            if not _SHA256_RE.fullmatch(recorded_sha256):
                raise ValueError(
                    "governance change set change_set_sha256 must be a lowercase "
                    "sha256 hex digest"
                )
            if recorded_sha256 != calculated_sha256:
                raise ValueError("governance change set hash does not match payload")
        object.__setattr__(
            self, "change_set_sha256", recorded_sha256 or calculated_sha256
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "repository_root": str(self.repository_root),
            "git_commit": self.git_commit,
            "staged_paths": list(self.staged_paths),
            "unstaged_paths": list(self.unstaged_paths),
            "untracked_governed_paths": list(self.untracked_governed_paths),
            "changed_paths": list(self.changed_paths),
            "change_set_sha256": self.change_set_sha256,
            "lifecycle_stage": (
                GovernanceEvidenceLifecycleStage.CHANGESET_IDENTIFIED.value
            ),
        }


@dataclass(frozen=True, slots=True)
class GovernanceSubjectDigest:
    repository_root: Path
    subject_scope: str
    authority_family_sha256: str
    repository_tree_sha256: str
    subject_sha256: str
    entry_count: int
    git_commit: str = "UNKNOWN"
    change_set_sha256: str = ""
    subject_id: str = ""
    changed_path_count: int = 0

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError("governance subject repository_root must be absolute")
        _require_non_empty("governance subject scope", self.subject_scope)
        _require_non_empty("governance subject git_commit", self.git_commit)
        for name, value in (
            (
                "governance subject authority_family_sha256",
                self.authority_family_sha256,
            ),
            ("governance subject repository_tree_sha256", self.repository_tree_sha256),
            ("governance subject subject_sha256", self.subject_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase sha256 hex digest")
        change_set_sha256 = self.change_set_sha256.lower() or _EMPTY_CHANGE_SET_SHA256
        if not _SHA256_RE.fullmatch(change_set_sha256):
            raise ValueError(
                "governance subject change_set_sha256 must be a lowercase sha256 "
                "hex digest"
            )
        object.__setattr__(self, "change_set_sha256", change_set_sha256)
        subject_id = self.subject_id.lower() or self.subject_sha256
        if not _SHA256_RE.fullmatch(subject_id):
            raise ValueError("governance subject subject_id must be a sha256 digest")
        object.__setattr__(self, "subject_id", subject_id)
        if self.entry_count < 0:
            raise ValueError("governance subject entry_count must be non-negative")
        if self.changed_path_count < 0:
            raise ValueError(
                "governance subject changed_path_count must be non-negative"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "repository_root": str(self.repository_root),
            "subject_scope": self.subject_scope,
            "authority_family_sha256": self.authority_family_sha256,
            "repository_tree_sha256": self.repository_tree_sha256,
            "subject_sha256": self.subject_sha256,
            "entry_count": self.entry_count,
            "git_commit": self.git_commit,
            "change_set_sha256": self.change_set_sha256,
            "subject_id": self.subject_id,
            "changed_path_count": self.changed_path_count,
        }


@dataclass(frozen=True, slots=True)
class ApprovalVerificationEvidence:
    change_class: ChangeApprovalClass
    status: ApprovalVerificationStatus
    lifecycle_stage: GovernanceEvidenceLifecycleStage
    approval_required: bool
    required_approval_count: int
    observed_approval_count: int
    subject_id: str
    scope_hash: str
    deterministic_quality_gate_evidence_sha256: str
    deterministic_governance_gate_evidence_sha256: str
    evidence_hash: str
    authority_family_sha256: str
    lifecycle_definition_sha256: str
    approval_ids: tuple[str, ...] = ()
    approver_ids: tuple[str, ...] = ()
    principal_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    high_assurance_required: bool = False
    constitution_sync_required: bool = False
    enforced: bool = False
    hard_veto: bool = False

    def __post_init__(self) -> None:
        _require_unique_nonblank(
            "approval verification approval_ids", self.approval_ids
        )
        _require_unique_identity_or_collision_blocker(
            "approval verification approver_ids",
            self.approver_ids,
            self.blockers,
            "APPROVAL_APPROVER_IDENTITY_COLLISION",
        )
        _require_unique_identity_or_collision_blocker(
            "approval verification principal_ids",
            self.principal_ids,
            self.blockers,
            "APPROVAL_PRINCIPAL_IDENTITY_COLLISION",
        )
        _require_unique_nonblank("approval verification blockers", self.blockers)
        for name, value in (
            ("approval verification subject_id", self.subject_id),
            ("approval verification scope_hash", self.scope_hash),
            (
                "approval verification deterministic_quality_gate_evidence_sha256",
                self.deterministic_quality_gate_evidence_sha256,
            ),
            (
                "approval verification deterministic_governance_gate_evidence_sha256",
                self.deterministic_governance_gate_evidence_sha256,
            ),
            ("approval verification evidence_hash", self.evidence_hash),
            (
                "approval verification authority_family_sha256",
                self.authority_family_sha256,
            ),
            (
                "approval verification lifecycle_definition_sha256",
                self.lifecycle_definition_sha256,
            ),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase sha256 hex digest")
        if self.required_approval_count < 0 or self.observed_approval_count < 0:
            raise ValueError("approval verification counts must be non-negative")
        if not self.approval_required:
            if self.status is not ApprovalVerificationStatus.NOT_REQUIRED:
                raise ValueError(
                    "non-required approval verification must be NOT_REQUIRED"
                )
            if self.hard_veto:
                raise ValueError(
                    "non-required approval verification cannot be a hard veto"
                )
            if self.required_approval_count != 0:
                raise ValueError(
                    "non-required approval verification cannot require approvals"
                )
            if (
                self.lifecycle_stage
                is not GovernanceEvidenceLifecycleStage.POLICY_ELIGIBLE
            ):
                raise ValueError(
                    "non-required approval verification must remain policy eligible"
                )
        elif self.status is ApprovalVerificationStatus.PASS:
            if not self.hard_veto:
                raise ValueError(
                    "required approval verification must remain a hard veto"
                )
            confirmed_stage = (
                GovernanceEvidenceLifecycleStage.CONSEQUENTIAL_AUTHORITY_CONFIRMED
            )
            if self.lifecycle_stage is not confirmed_stage:
                raise ValueError(
                    "passing approval verification must confirm consequential authority"
                )
            if self.observed_approval_count < self.required_approval_count:
                raise ValueError(
                    "passing approval verification requires enough approvals"
                )
            if self.blockers:
                raise ValueError(
                    "passing approval verification cannot contain blockers"
                )
        elif (
            self.status is ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
            and not self.blockers
        ):
            raise ValueError("blocked approval verification requires blockers")
        elif self.approval_required and not self.hard_veto:
            raise ValueError("required approval verification must remain a hard veto")

    def to_payload(self) -> dict[str, object]:
        return {
            "change_class": self.change_class.value,
            "status": self.status.value,
            "lifecycle_stage": self.lifecycle_stage.value,
            "approval_required": self.approval_required,
            "required_approval_count": self.required_approval_count,
            "observed_approval_count": self.observed_approval_count,
            "subject_id": self.subject_id,
            "scope_hash": self.scope_hash,
            "deterministic_quality_gate_evidence_sha256": (
                self.deterministic_quality_gate_evidence_sha256
            ),
            "deterministic_governance_gate_evidence_sha256": (
                self.deterministic_governance_gate_evidence_sha256
            ),
            "evidence_hash": self.evidence_hash,
            "authority_family_sha256": self.authority_family_sha256,
            "lifecycle_definition_sha256": self.lifecycle_definition_sha256,
            "approval_ids": list(self.approval_ids),
            "approver_ids": list(self.approver_ids),
            "principal_ids": list(self.principal_ids),
            "blockers": list(self.blockers),
            "high_assurance_required": self.high_assurance_required,
            "constitution_sync_required": self.constitution_sync_required,
            "enforced": self.enforced,
            "hard_veto": self.hard_veto,
        }


@dataclass(frozen=True, slots=True)
class DeterministicGateResolverEvidence:
    decision: DeterministicGateDecision
    hard_blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_nonblank("deterministic gate hard_blockers", self.hard_blockers)
        _require_unique_nonblank("deterministic gate warnings", self.warnings)
        if self.decision is DeterministicGateDecision.PASS and self.hard_blockers:
            raise ValueError(
                "passing deterministic gate resolver cannot contain blockers"
            )
        if self.decision is DeterministicGateDecision.PASS_WITH_WARNINGS and (
            self.hard_blockers or not self.warnings
        ):
            raise ValueError(
                "PASS_WITH_WARNINGS requires warnings and cannot contain blockers"
            )
        if (
            self.decision is DeterministicGateDecision.BLOCKED
            and not self.hard_blockers
        ):
            raise ValueError("blocked deterministic gate resolver requires blockers")

    def to_payload(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "hard_blockers": list(self.hard_blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class DeterministicQualityGateReport:
    gate_id: str
    repository_root: Path
    quality_evidence_gate: QualityEvidenceGateEvidence
    security_scan: SecurityScanEvidence
    blockers: tuple[str, ...]
    status: GovernanceGateStatus
    change_set: GovernanceChangeSet | None = None
    subject_digest: GovernanceSubjectDigest | None = None
    lifecycle_stage: GovernanceEvidenceLifecycleStage | None = None
    gate_evidence_sha256: str = ""
    authority_role: str = "TECHNICAL_TRUTH"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError(
                "deterministic quality gate repository_root must be absolute"
            )
        _require_non_empty("deterministic quality gate id", self.gate_id)
        if self.authority_role != "TECHNICAL_TRUTH":
            raise ValueError(
                "deterministic quality gate authority_role must be TECHNICAL_TRUTH"
            )
        _require_unique_nonblank("deterministic quality gate blockers", self.blockers)
        if self.status is GovernanceGateStatus.PASS and self.blockers:
            raise ValueError(
                "passing deterministic quality gate cannot contain blockers"
            )
        if (
            self.status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
            and not self.blockers
        ):
            raise ValueError("blocked deterministic quality gate requires blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("deterministic quality gate cannot authorize execution")
        if self.subject_digest is None:
            object.__setattr__(
                self,
                "subject_digest",
                _build_governance_subject_digest(
                    self.repository_root.resolve(),
                    self.change_set,
                ),
            )
        if self.subject_digest is None:
            raise ValueError("deterministic quality gate requires subject digest")
        if self.subject_digest.repository_root != self.repository_root.resolve():
            raise ValueError(
                "deterministic quality gate subject digest must match repository_root"
            )
        if self.change_set is not None:
            if self.change_set.repository_root != self.repository_root.resolve():
                raise ValueError(
                    "deterministic quality gate change set must match repository_root"
                )
            if (
                self.subject_digest.change_set_sha256
                != self.change_set.change_set_sha256
            ):
                raise ValueError(
                    "deterministic quality gate subject digest must match change set"
                )
        lifecycle_stage = self.lifecycle_stage
        if lifecycle_stage is None:
            lifecycle_stage = (
                GovernanceEvidenceLifecycleStage.TECHNICAL_TRUTH_CONFIRMED
                if self.status is GovernanceGateStatus.PASS
                else GovernanceEvidenceLifecycleStage.BLOCKED
            )
            object.__setattr__(self, "lifecycle_stage", lifecycle_stage)
        gate_evidence_sha256 = self.gate_evidence_sha256.lower()
        if gate_evidence_sha256:
            if not _SHA256_RE.fullmatch(gate_evidence_sha256):
                raise ValueError(
                    "deterministic quality gate gate_evidence_sha256 must be sha256"
                )
        else:
            gate_evidence_sha256 = _canonical_sha256(self._gate_evidence_payload())
            object.__setattr__(self, "gate_evidence_sha256", gate_evidence_sha256)

    def to_summary_payload(
        self, *, report_path: str | None = None
    ) -> dict[str, object]:
        if self.subject_digest is None:
            raise ValueError("deterministic quality gate requires subject digest")
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "authority_role": self.authority_role,
            "report_path": report_path,
            "blocker_count": len(self.blockers),
            "blockers": list(self.blockers),
            "quality_evidence_gate_status": self.quality_evidence_gate.status.value,
            "security_scan_passed": self.security_scan.passed,
            "pytest_pass_count": (
                self.quality_evidence_gate.quality_gate.pytest_pass_count
            ),
            "coverage_percent": (
                self.quality_evidence_gate.quality_gate.coverage_percent
            ),
            "subject_sha256": self.subject_digest.subject_sha256,
            "subject_id": self.subject_digest.subject_id,
            "change_set_sha256": self.subject_digest.change_set_sha256,
            "lifecycle_stage": (
                None if self.lifecycle_stage is None else self.lifecycle_stage.value
            ),
            "gate_evidence_sha256": self.gate_evidence_sha256,
        }

    def _gate_evidence_payload(self) -> dict[str, object]:
        if self.subject_digest is None:
            raise ValueError("deterministic quality gate requires subject digest")
        return {
            "gate_id": self.gate_id,
            "repository_root": str(self.repository_root),
            "status": self.status.value,
            "authority_role": self.authority_role,
            "quality_evidence_gate": self.quality_evidence_gate.to_payload(),
            "security_scan": self.security_scan.to_payload(),
            "change_set": (
                None if self.change_set is None else self.change_set.to_payload()
            ),
            "subject_digest": self.subject_digest.to_payload(),
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }

    def to_payload(self) -> dict[str, object]:
        payload = self._gate_evidence_payload()
        payload["lifecycle_stage"] = (
            None if self.lifecycle_stage is None else self.lifecycle_stage.value
        )
        payload["gate_evidence_sha256"] = self.gate_evidence_sha256
        return payload


@dataclass(frozen=True, slots=True)
class GovernanceGateReport:
    gate_id: str
    repository_root: Path
    authority_baseline: AuthorityBaselineEvidence
    repository_hygiene: RepositoryHygieneGateEvidence
    constitution_sync: ConstitutionSyncGateEvidence
    repository_conformance: RepositoryConformanceGateEvidence
    deterministic_gate_resolver: DeterministicGateResolverEvidence
    repository_validator: RepositoryValidatorEvidence
    docs_hygiene: GovernanceTestEvidence
    artifact_hygiene: GovernanceTestEvidence
    constitution_sync_tests: GovernanceTestEvidence
    alignment_status: str
    alignment_findings: tuple[dict[str, str], ...]
    blockers: tuple[str, ...]
    deterministic_quality_gate: DeterministicQualityGateReport | None = None
    change_set: GovernanceChangeSet | None = None
    subject_digest: GovernanceSubjectDigest | None = None
    quality_subject_match: bool | None = None
    status: GovernanceGateStatus | None = None
    quality_evidence_gate: QualityEvidenceGateEvidence | None = None
    quality_gate: QualityGateEvidence | None = None
    change_class: ChangeApprovalClass | None = None
    approval_verification: ApprovalVerificationEvidence | None = None
    traceability_audit: TraceabilityAuditReport | None = None
    traceability_hard_veto: bool = False
    lifecycle_stage: GovernanceEvidenceLifecycleStage | None = None
    gate_evidence_sha256: str = ""
    authority_role: str = "POLICY_ELIGIBILITY"
    human_governance_role: str = "CONSEQUENTIAL_AUTHORITY"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.repository_root.is_absolute():
            raise ValueError("governance gate repository_root must be absolute")
        _require_non_empty("governance gate id", self.gate_id)
        if self.authority_role != "POLICY_ELIGIBILITY":
            raise ValueError(
                "governance gate authority_role must be POLICY_ELIGIBILITY"
            )
        if self.human_governance_role != "CONSEQUENTIAL_AUTHORITY":
            raise ValueError(
                "governance gate human_governance_role must be CONSEQUENTIAL_AUTHORITY"
            )
        _require_unique_nonblank("governance gate blockers", self.blockers)
        deterministic_quality_gate = self.deterministic_quality_gate
        if deterministic_quality_gate is None:
            raise ValueError("governance gate requires deterministic quality gate")
        quality_evidence_gate = self.quality_evidence_gate
        if quality_evidence_gate is None:
            object.__setattr__(
                self,
                "quality_evidence_gate",
                deterministic_quality_gate.quality_evidence_gate,
            )
        traceability_audit = self.traceability_audit
        if traceability_audit is None:
            traceability_audit = _build_traceability_audit(
                self.repository_root.resolve()
            )
            object.__setattr__(self, "traceability_audit", traceability_audit)
        if not self.traceability_hard_veto:
            object.__setattr__(
                self,
                "traceability_hard_veto",
                _traceability_hard_veto_required(traceability_audit),
            )
        if (
            self.traceability_hard_veto
            and traceability_audit.status is TraceabilityStatus.RUNNING_WITH_BLOCKERS
        ):
            object.__setattr__(
                self,
                "blockers",
                tuple(dict.fromkeys((*self.blockers, *traceability_audit.blockers))),
            )
        if self.subject_digest is None:
            object.__setattr__(
                self,
                "subject_digest",
                _build_governance_subject_digest(
                    self.repository_root.resolve(),
                    self.change_set,
                ),
            )
        if self.subject_digest is None:
            raise ValueError("governance gate requires subject digest")
        if self.subject_digest.repository_root != self.repository_root.resolve():
            raise ValueError(
                "governance gate subject digest must match repository_root"
            )
        if self.change_set is not None:
            if self.change_set.repository_root != self.repository_root.resolve():
                raise ValueError(
                    "governance gate change set must match repository_root"
                )
            if (
                self.subject_digest.change_set_sha256
                != self.change_set.change_set_sha256
            ):
                raise ValueError("governance gate subject digest must match change set")
        if self.quality_subject_match is None:
            object.__setattr__(
                self,
                "quality_subject_match",
                _subject_digests_match(
                    self.subject_digest,
                    deterministic_quality_gate.subject_digest,
                ),
            )
        resolved_status = (
            self.status
            if self.status is not None
            else (
                GovernanceGateStatus.PASS
                if not self.blockers
                else GovernanceGateStatus.RUNNING_WITH_BLOCKERS
            )
        )
        object.__setattr__(self, "status", resolved_status)
        if resolved_status is GovernanceGateStatus.PASS and self.blockers:
            raise ValueError("passing governance gate cannot contain blockers")
        if (
            resolved_status is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
            and not self.blockers
        ):
            raise ValueError("blocked governance gate requires blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("governance gate cannot authorize execution")
        if self.change_class is None:
            object.__setattr__(
                self,
                "change_class",
                _classify_change_set(self.change_set),
            )
        lifecycle_stage = self.lifecycle_stage
        if lifecycle_stage is None:
            lifecycle_stage = (
                GovernanceEvidenceLifecycleStage.POLICY_ELIGIBLE
                if resolved_status is GovernanceGateStatus.PASS
                else GovernanceEvidenceLifecycleStage.BLOCKED
            )
            object.__setattr__(self, "lifecycle_stage", lifecycle_stage)
        gate_evidence_sha256 = self.gate_evidence_sha256.lower()
        if gate_evidence_sha256:
            if not _SHA256_RE.fullmatch(gate_evidence_sha256):
                raise ValueError("governance gate gate_evidence_sha256 must be sha256")
        else:
            gate_evidence_sha256 = _canonical_sha256(self._gate_evidence_payload())
            object.__setattr__(self, "gate_evidence_sha256", gate_evidence_sha256)

    def _gate_evidence_payload(self) -> dict[str, object]:
        if self.status is None:
            raise ValueError("governance gate status must be resolved before payload")
        deterministic_quality_gate = self.deterministic_quality_gate
        if deterministic_quality_gate is None:
            raise ValueError(
                "governance gate requires deterministic quality gate before payload"
            )
        subject_digest = self.subject_digest
        if subject_digest is None:
            raise ValueError("governance gate requires subject digest before payload")
        return {
            "gate_id": self.gate_id,
            "repository_root": str(self.repository_root),
            "status": self.status.value,
            "authority_role": self.authority_role,
            "change_set": (
                None if self.change_set is None else self.change_set.to_payload()
            ),
            "subject_digest": subject_digest.to_payload(),
            "quality_subject_match": self.quality_subject_match,
            "human_governance_role": self.human_governance_role,
            "deterministic_quality_gate": (
                deterministic_quality_gate.to_summary_payload()
            ),
            "authority_baseline": self.authority_baseline.to_payload(),
            "repository_hygiene": self.repository_hygiene.to_payload(),
            "constitution_sync": self.constitution_sync.to_payload(),
            "repository_conformance": self.repository_conformance.to_payload(),
            "repository_validator_gate": self.repository_conformance.to_payload(),
            "deterministic_gate_resolver": (
                self.deterministic_gate_resolver.to_payload()
            ),
            "repository_validator": self.repository_validator.to_payload(),
            "docs_hygiene": self.docs_hygiene.to_payload(),
            "artifact_hygiene": self.artifact_hygiene.to_payload(),
            "constitution_sync_tests": self.constitution_sync_tests.to_payload(),
            "alignment_status": self.alignment_status,
            "alignment_findings": list(self.alignment_findings),
            "blockers": list(self.blockers),
            "change_class": (
                None if self.change_class is None else self.change_class.value
            ),
            "traceability_audit": (
                None
                if self.traceability_audit is None
                else self.traceability_audit.to_payload()
            ),
            "traceability_hard_veto": self.traceability_hard_veto,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }

    def to_payload(self) -> dict[str, object]:
        payload = self._gate_evidence_payload()
        payload["lifecycle_stage"] = (
            None if self.lifecycle_stage is None else self.lifecycle_stage.value
        )
        payload["gate_evidence_sha256"] = self.gate_evidence_sha256
        payload["approval_verification"] = (
            None
            if self.approval_verification is None
            else self.approval_verification.to_payload()
        )
        return payload


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_EMPTY_CHANGE_SET_SHA256 = hashlib.sha256(b"[]").hexdigest()
_GOVERNED_RELEASE_CONTROL = ConstitutionalChangeControl()
_AUTHORITY_BASELINE_PATHS: tuple[str, ...] = (
    "docs/governance/framework_core_vnext_governance.md",
    "docs/governance/instruction_core_custom_instructions.md",
    "docs/providers/instruction_codex_provider.md",
    "docs/compliance/registry_compliance_matrix.md",
)
_TRACEABILITY_REQUIREMENT_ARTIFACT_PATHS: tuple[str, ...] = (
    "runtime/artifacts/auto_audit/auto-audit-latest.json",
    "runtime/artifacts/auto_audit/latest.json",
)
_SUBJECT_DIGEST_SCOPE = "REPOSITORY_WITHOUT_RUNTIME_OUTPUTS"
_SUBJECT_DIGEST_IGNORED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        ".codex",
        "runtime",
        "secrets",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".hypothesis",
        "ai4binance.egg-info",
        "htmlcov",
    }
)
_CONSEQUENTIAL_CHANGE_PREFIXES: tuple[str, ...] = (
    "src/ai4binance/execution/live",
    "src/ai4binance/execution/manual_approval.py",
    "src/ai4binance/cli/live.py",
)
_GOVERNED_CHANGE_PREFIXES: tuple[str, ...] = (
    "src/ai4binance/governance/",
    "src/ai4binance/enterprise/",
    "config/governance/",
    "docs/governance/",
    "docs/compliance/",
    "docs/standards/",
    "docs/providers/",
    "docs/controls/",
    "policies/",
    "scripts/quality.ps1",
    "AGENTS.md",
)


def build_deterministic_quality_gate_report(
    *,
    repository_root: Path,
    quality_gate: QualityGateEvidence,
    security_scan: SecurityScanEvidence,
    change_set: GovernanceChangeSet | None = None,
) -> DeterministicQualityGateReport:
    resolved_repository_root = repository_root.resolve()
    selected_change_set = change_set or resolve_governance_change_set(
        resolved_repository_root
    )
    quality_evidence_gate = _build_quality_evidence_gate(quality_gate)
    blockers = list(quality_evidence_gate.blockers)
    if not security_scan.passed:
        blockers.append("SECURITY_SCAN_FAILED")
    normalized_blockers = tuple(dict.fromkeys(blockers))
    return DeterministicQualityGateReport(
        gate_id="deterministic-quality-gate:v3",
        repository_root=resolved_repository_root,
        quality_evidence_gate=quality_evidence_gate,
        security_scan=security_scan,
        blockers=normalized_blockers,
        status=(
            GovernanceGateStatus.PASS
            if not normalized_blockers
            else GovernanceGateStatus.RUNNING_WITH_BLOCKERS
        ),
        change_set=selected_change_set,
        subject_digest=_build_governance_subject_digest(
            resolved_repository_root,
            selected_change_set,
        ),
    )


def build_governance_gate_report(
    *,
    repository_root: Path,
    repository_validator: RepositoryValidatorEvidence,
    docs_hygiene: GovernanceTestEvidence,
    artifact_hygiene: GovernanceTestEvidence,
    constitution_sync_tests: GovernanceTestEvidence,
    deterministic_quality_gate: DeterministicQualityGateReport | None = None,
    change_set: GovernanceChangeSet | None = None,
    approval_records: tuple[ApprovalRecord, ...] = (),
    require_change_set: bool = False,
    enforce_approval: bool = False,
) -> GovernanceGateReport:
    """Combine policy eligibility sub-gates on top of proven quality evidence."""

    if deterministic_quality_gate is None:
        raise ValueError("governance gate requires deterministic quality gate")
    resolved_repository_root = repository_root.resolve()
    selected_change_set = (
        change_set
        or deterministic_quality_gate.change_set
        or resolve_governance_change_set(resolved_repository_root)
    )
    change_scope_known = not require_change_set or selected_change_set is not None
    alignment_report = audit_governance_alignment(
        resolved_repository_root,
        changed_paths=(
            () if selected_change_set is None else selected_change_set.changed_paths
        ),
        quality_gate=deterministic_quality_gate.quality_evidence_gate.quality_gate,
        change_scope_known=change_scope_known,
    )
    alignment_findings = tuple(
        {
            "kind": finding.kind.value,
            "path": finding.path,
            "detail": finding.detail,
            "severity": finding.severity,
        }
        for finding in alignment_report.findings
    )
    authority_baseline = _build_authority_baseline(resolved_repository_root)
    subject_digest = _build_governance_subject_digest(
        resolved_repository_root,
        selected_change_set,
    )
    subject_blockers: tuple[str, ...] = ()
    quality_subject_match = _subject_digests_match(
        subject_digest,
        deterministic_quality_gate.subject_digest,
    )
    if not quality_subject_match:
        subject_blockers = ("DETERMINISTIC_QUALITY_GATE_SUBJECT_MISMATCH",)
    change_set_blockers: tuple[str, ...] = ()
    if require_change_set and selected_change_set is None:
        change_set_blockers = ("UNKNOWN_CHANGESET",)
    elif (
        selected_change_set is not None
        and deterministic_quality_gate.change_set is not None
        and selected_change_set.change_set_sha256
        != deterministic_quality_gate.change_set.change_set_sha256
    ):
        change_set_blockers = ("DETERMINISTIC_QUALITY_GATE_CHANGE_SET_MISMATCH",)
    repository_hygiene = _build_repository_hygiene_gate(
        repository_validator=repository_validator,
        docs_hygiene=docs_hygiene,
        artifact_hygiene=artifact_hygiene,
    )
    constitution_sync = _build_constitution_sync_gate(
        constitution_sync_tests=constitution_sync_tests,
        alignment_report=alignment_report,
        alignment_findings=alignment_findings,
    )
    repository_conformance = _build_repository_conformance_gate(repository_validator)
    deterministic_gate_resolver = _build_deterministic_gate_resolver(
        authority_baseline=authority_baseline,
        repository_hygiene=repository_hygiene,
        constitution_sync=constitution_sync,
        repository_conformance=repository_conformance,
        deterministic_quality_gate=deterministic_quality_gate,
        subject_blockers=(*subject_blockers, *change_set_blockers),
    )
    blockers = [
        *authority_baseline.blockers,
        *repository_hygiene.blockers,
        *constitution_sync.blockers,
        *repository_conformance.blockers,
    ]
    if deterministic_quality_gate.status is not GovernanceGateStatus.PASS:
        blockers.append("DETERMINISTIC_QUALITY_GATE_NOT_PASSING")
    blockers.extend(subject_blockers)
    blockers.extend(change_set_blockers)
    provisional_report = GovernanceGateReport(
        gate_id="deterministic-governance-gate:v1",
        repository_root=resolved_repository_root,
        deterministic_quality_gate=deterministic_quality_gate,
        change_set=selected_change_set,
        subject_digest=subject_digest,
        quality_subject_match=quality_subject_match,
        authority_baseline=authority_baseline,
        repository_hygiene=repository_hygiene,
        constitution_sync=constitution_sync,
        repository_conformance=repository_conformance,
        deterministic_gate_resolver=deterministic_gate_resolver,
        repository_validator=repository_validator,
        docs_hygiene=docs_hygiene,
        artifact_hygiene=artifact_hygiene,
        constitution_sync_tests=constitution_sync_tests,
        alignment_status=alignment_report.status.value,
        alignment_findings=alignment_findings,
        blockers=tuple(dict.fromkeys(blockers)),
    )
    approval_verification = _build_approval_verification(
        change_set=selected_change_set,
        deterministic_quality_gate=deterministic_quality_gate,
        governance_gate=provisional_report,
        approval_records=approval_records,
        enforced=enforce_approval,
    )
    final_blockers = list(provisional_report.blockers)
    traceability_blockers: tuple[str, ...] = ()
    if (
        provisional_report.traceability_hard_veto
        and provisional_report.traceability_audit is not None
        and provisional_report.traceability_audit.status
        is TraceabilityStatus.RUNNING_WITH_BLOCKERS
    ):
        traceability_blockers = provisional_report.traceability_audit.blockers
    approval_hard_veto = enforce_approval or approval_verification.hard_veto
    if approval_hard_veto and (
        approval_verification.status is ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
    ):
        final_blockers.extend(approval_verification.blockers)
    final_blockers = list(dict.fromkeys(final_blockers))
    return GovernanceGateReport(
        gate_id=provisional_report.gate_id,
        repository_root=provisional_report.repository_root,
        deterministic_quality_gate=deterministic_quality_gate,
        change_set=selected_change_set,
        subject_digest=subject_digest,
        quality_subject_match=quality_subject_match,
        authority_baseline=authority_baseline,
        repository_hygiene=repository_hygiene,
        constitution_sync=constitution_sync,
        repository_conformance=repository_conformance,
        deterministic_gate_resolver=_build_deterministic_gate_resolver(
            authority_baseline=authority_baseline,
            repository_hygiene=repository_hygiene,
            constitution_sync=constitution_sync,
            repository_conformance=repository_conformance,
            deterministic_quality_gate=deterministic_quality_gate,
            subject_blockers=traceability_blockers
            + tuple(approval_verification.blockers if approval_hard_veto else ())
            + tuple(subject_blockers)
            + tuple(change_set_blockers),
        ),
        repository_validator=repository_validator,
        docs_hygiene=docs_hygiene,
        artifact_hygiene=artifact_hygiene,
        constitution_sync_tests=constitution_sync_tests,
        alignment_status=alignment_report.status.value,
        alignment_findings=alignment_findings,
        blockers=tuple(final_blockers),
        change_class=provisional_report.change_class,
        approval_verification=approval_verification,
        traceability_audit=provisional_report.traceability_audit,
        traceability_hard_veto=provisional_report.traceability_hard_veto,
        gate_evidence_sha256=provisional_report.gate_evidence_sha256,
    )


def _build_authority_baseline(repository_root: Path) -> AuthorityBaselineEvidence:
    snapshots: list[AuthorityDocumentSnapshot] = []
    blockers: list[str] = []
    seen_document_ids: set[str] = set()
    seen_canonical_paths: set[str] = set()
    for relative_path in _AUTHORITY_BASELINE_PATHS:
        absolute_path = repository_root / relative_path
        if not absolute_path.is_file():
            blockers.append(f"AUTHORITY_BASELINE_DOCUMENT_MISSING:{relative_path}")
            continue
        metadata = _frontmatter(absolute_path)
        if metadata is None:
            blockers.append(f"AUTHORITY_BASELINE_METADATA_MISSING:{relative_path}")
            continue
        missing_fields = tuple(
            field
            for field in (
                "document_id",
                "version",
                "canonical_path",
                "authority_level",
                "source_of_truth",
            )
            if not str(metadata.get(field, "")).strip()
        )
        if missing_fields:
            blockers.append(
                "AUTHORITY_BASELINE_METADATA_FIELDS_MISSING:"
                f"{relative_path}:{','.join(missing_fields)}"
            )
            continue
        if metadata["canonical_path"] != relative_path:
            blockers.append(
                f"AUTHORITY_BASELINE_CANONICAL_PATH_MISMATCH:{relative_path}"
            )
            continue
        try:
            snapshot = AuthorityDocumentSnapshot(
                authority_document_id=metadata["document_id"],
                version=metadata["version"],
                canonical_path=metadata["canonical_path"],
                sha256=_sha256(absolute_path),
                authority_level=metadata["authority_level"],
                source_of_truth=_metadata_bool(
                    "source_of_truth",
                    metadata["source_of_truth"],
                ),
            )
        except ValueError as exc:
            blockers.append(
                f"AUTHORITY_BASELINE_METADATA_INVALID:{relative_path}:{exc}"
            )
            continue
        if snapshot.authority_document_id in seen_document_ids:
            blockers.append(
                "AUTHORITY_BASELINE_DUPLICATE_DOCUMENT_ID:"
                f"{snapshot.authority_document_id}"
            )
            continue
        if snapshot.canonical_path in seen_canonical_paths:
            blockers.append(
                f"AUTHORITY_BASELINE_DUPLICATE_CANONICAL_PATH:{snapshot.canonical_path}"
            )
            continue
        seen_document_ids.add(snapshot.authority_document_id)
        seen_canonical_paths.add(snapshot.canonical_path)
        snapshots.append(snapshot)
    snapshot_sha256 = _authority_snapshot_sha256(tuple(snapshots))
    return AuthorityBaselineEvidence(
        status=(
            DeterministicSubGateStatus.PASS
            if not blockers
            else DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
        ),
        blockers=tuple(dict.fromkeys(blockers)),
        authority_snapshot=tuple(snapshots),
        authority_snapshot_sha256=snapshot_sha256,
    )


def _build_repository_hygiene_gate(
    *,
    repository_validator: RepositoryValidatorEvidence,
    docs_hygiene: GovernanceTestEvidence,
    artifact_hygiene: GovernanceTestEvidence,
) -> RepositoryHygieneGateEvidence:
    validator_findings = tuple(
        finding for finding in repository_validator.findings if finding.blocker
    )
    checks = (
        _build_hygiene_check(
            "DOC_HYGIENE",
            tuple(
                blocker
                for blocker in (
                    ("DOCS_HYGIENE_TESTS_FAILED",) if not docs_hygiene.passed else ()
                )
                + tuple(
                    _finding_gate_blocker_id(finding)
                    for finding in validator_findings
                    if finding.control_family == "DOC_HYGIENE"
                )
            ),
        ),
        _build_hygiene_check(
            "ARTIFACT_HYGIENE",
            tuple(
                blocker
                for blocker in (
                    ("ARTIFACT_HYGIENE_TESTS_FAILED",)
                    if not artifact_hygiene.passed
                    else ()
                )
                + tuple(
                    _finding_gate_blocker_id(finding)
                    for finding in validator_findings
                    if finding.control_family == "ARTIFACT_HYGIENE"
                )
            ),
        ),
        _build_hygiene_check(
            "RUNTIME_HYGIENE",
            tuple(
                _finding_gate_blocker_id(finding)
                for finding in validator_findings
                if finding.control_family == "RUNTIME_HYGIENE"
            ),
        ),
        _build_hygiene_check(
            "CONFIG_HYGIENE",
            tuple(
                _finding_gate_blocker_id(finding)
                for finding in validator_findings
                if finding.control_family == "CONFIG_HYGIENE"
            ),
        ),
        _build_hygiene_check(
            "SCHEMA_HYGIENE",
            tuple(
                _finding_gate_blocker_id(finding)
                for finding in validator_findings
                if finding.control_family == "SCHEMA_HYGIENE"
            ),
        ),
        _build_hygiene_check(
            "POLICY_HYGIENE",
            tuple(
                _finding_gate_blocker_id(finding)
                for finding in validator_findings
                if finding.control_family == "POLICY_HYGIENE"
            ),
        ),
        _build_hygiene_check(
            "SOURCE_HYGIENE",
            tuple(
                _finding_gate_blocker_id(finding)
                for finding in validator_findings
                if finding.control_family == "SOURCE_HYGIENE"
            ),
        ),
    )
    blockers = tuple(blocker for check in checks for blocker in check.blockers)
    return RepositoryHygieneGateEvidence(
        status=(
            DeterministicSubGateStatus.PASS
            if not blockers
            else DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
        ),
        checks=checks,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _build_constitution_sync_gate(
    *,
    constitution_sync_tests: GovernanceTestEvidence,
    alignment_report: GovernanceAlignmentAuditReport,
    alignment_findings: tuple[dict[str, str], ...],
) -> ConstitutionSyncGateEvidence:
    blockers: list[str] = []
    if not constitution_sync_tests.passed:
        blockers.append("CONSTITUTION_SYNC_TESTS_FAILED")
    if alignment_report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS:
        blockers.extend(
            f"{finding.kind.value}:{finding.path}"
            for finding in alignment_report.findings
        )
    normalized_blockers = tuple(dict.fromkeys(blockers))
    return ConstitutionSyncGateEvidence(
        status=(
            DeterministicSubGateStatus.PASS
            if not normalized_blockers
            else DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
        ),
        blockers=normalized_blockers,
        selected_tests=constitution_sync_tests.selected_tests,
        command=constitution_sync_tests.command,
        alignment_status=alignment_report.status.value,
        alignment_findings=alignment_findings,
    )


def _build_repository_conformance_gate(
    repository_validator: RepositoryValidatorEvidence,
) -> RepositoryConformanceGateEvidence:
    blockers = tuple(
        repository_validator.blocker_ids or ("REPOSITORY_VALIDATOR_NOT_PASSING",)
    )
    if repository_validator.status == "PASS":
        blockers = ()
    return RepositoryConformanceGateEvidence(
        status=(
            DeterministicSubGateStatus.PASS
            if not blockers
            else DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
        ),
        blockers=blockers,
        validator=repository_validator,
    )


def _build_quality_evidence_gate(
    quality_gate: QualityGateEvidence,
) -> QualityEvidenceGateEvidence:
    pytest_pass_count = quality_gate.pytest_pass_count
    if pytest_pass_count is None:
        raise ValueError("quality gate evidence requires pytest_pass_count")
    blockers: tuple[str, ...] = ()
    if pytest_pass_count <= 0:
        blockers = ("PYTEST_EVIDENCE_MISSING",)
    return QualityEvidenceGateEvidence(
        status=(
            DeterministicSubGateStatus.PASS
            if not blockers
            else DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
        ),
        blockers=blockers,
        quality_gate=quality_gate,
    )


def _build_deterministic_gate_resolver(
    *,
    authority_baseline: AuthorityBaselineEvidence,
    repository_hygiene: RepositoryHygieneGateEvidence,
    constitution_sync: ConstitutionSyncGateEvidence,
    repository_conformance: RepositoryConformanceGateEvidence,
    deterministic_quality_gate: DeterministicQualityGateReport,
    subject_blockers: tuple[str, ...] = (),
) -> DeterministicGateResolverEvidence:
    hard_blockers = tuple(
        dict.fromkeys(
            (
                *authority_baseline.blockers,
                *constitution_sync.blockers,
                *repository_hygiene.blockers,
                *repository_conformance.blockers,
                *subject_blockers,
                *(
                    ("DETERMINISTIC_QUALITY_GATE_NOT_PASSING",)
                    if deterministic_quality_gate.status
                    is GovernanceGateStatus.RUNNING_WITH_BLOCKERS
                    else ()
                ),
            )
        )
    )
    if hard_blockers:
        return DeterministicGateResolverEvidence(
            decision=DeterministicGateDecision.BLOCKED,
            hard_blockers=hard_blockers,
        )
    return DeterministicGateResolverEvidence(
        decision=DeterministicGateDecision.PASS,
        hard_blockers=(),
    )


def resolve_governance_change_set(
    repository_root: Path,
) -> GovernanceChangeSet | None:
    resolved_repository_root = repository_root.resolve()
    git_repository_root = _git_repository_root(resolved_repository_root)
    if git_repository_root != resolved_repository_root:
        return None
    git_executable = _git_executable()
    if git_executable is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [
                git_executable,
                "-C",
                str(resolved_repository_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    staged_paths: list[str] = []
    unstaged_paths: list[str] = []
    untracked_paths: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 3:
            continue
        status_code = line[:2]
        path = _parse_git_status_path(line[3:])
        if not path or not _is_subject_path(path):
            continue
        if status_code == "??":
            untracked_paths.append(path)
            continue
        if status_code[0] not in {" ", "?"}:
            staged_paths.append(path)
        if status_code[1] not in {" ", "?"}:
            unstaged_paths.append(path)
    return GovernanceChangeSet(
        repository_root=resolved_repository_root,
        git_commit=_repository_git_commit(resolved_repository_root),
        staged_paths=tuple(staged_paths),
        unstaged_paths=tuple(unstaged_paths),
        untracked_governed_paths=tuple(untracked_paths),
    )


def _build_approval_verification(
    *,
    change_set: GovernanceChangeSet | None,
    deterministic_quality_gate: DeterministicQualityGateReport,
    governance_gate: GovernanceGateReport,
    approval_records: tuple[ApprovalRecord, ...],
    enforced: bool,
) -> ApprovalVerificationEvidence:
    change_class = governance_gate.change_class or _classify_change_set(change_set)
    required_count, constitution_sync_required, high_assurance_required = (
        _approval_requirements(change_class)
    )
    subject_digest = governance_gate.subject_digest
    if subject_digest is None:
        raise ValueError("approval verification requires governance subject digest")
    scope_hash = (
        change_set.change_set_sha256
        if change_set is not None
        else subject_digest.change_set_sha256
    )
    evidence_hash = _approval_evidence_hash(
        deterministic_quality_gate=deterministic_quality_gate,
        governance_gate=governance_gate,
    )
    authority_family_sha256 = subject_digest.authority_family_sha256
    lifecycle_definition_sha256 = _lifecycle_definition_sha256()
    if required_count == 0:
        return ApprovalVerificationEvidence(
            change_class=change_class,
            status=ApprovalVerificationStatus.NOT_REQUIRED,
            lifecycle_stage=GovernanceEvidenceLifecycleStage.POLICY_ELIGIBLE,
            approval_required=False,
            required_approval_count=0,
            observed_approval_count=0,
            subject_id=subject_digest.subject_id,
            scope_hash=scope_hash,
            deterministic_quality_gate_evidence_sha256=(
                deterministic_quality_gate.gate_evidence_sha256
            ),
            deterministic_governance_gate_evidence_sha256=(
                governance_gate.gate_evidence_sha256
            ),
            evidence_hash=evidence_hash,
            authority_family_sha256=authority_family_sha256,
            lifecycle_definition_sha256=lifecycle_definition_sha256,
            constitution_sync_required=constitution_sync_required,
            high_assurance_required=high_assurance_required,
            enforced=enforced,
            hard_veto=False,
        )
    blockers: list[str] = []
    approval_ids: list[str] = []
    approver_ids: list[str] = []
    principal_ids: list[str] = []
    valid_count = 0
    now = datetime.now(UTC)
    for record in approval_records:
        if record.status not in {
            ApprovalStatus.APPROVED_FOR_RESEARCH,
            ApprovalStatus.APPROVED_FOR_IMPLEMENTATION,
        }:
            blockers.append(f"APPROVAL_STATUS_NOT_APPROVED:{record.approval_id}")
            continue
        approval_ids.append(record.approval_id)
        approver_ids.append(record.approver_id)
        principal_ids.append(record.principal_id or record.approver_id)
        if record.subject_sha256 != subject_digest.subject_id:
            blockers.append(f"APPROVAL_SUBJECT_MISMATCH:{record.approval_id}")
            continue
        if record.scope_hash != scope_hash:
            blockers.append(f"APPROVAL_SCOPE_MISMATCH:{record.approval_id}")
            continue
        if record.change_class is not change_class:
            blockers.append(f"APPROVAL_CHANGE_CLASS_MISMATCH:{record.approval_id}")
            continue
        if (
            record.quality_gate_evidence_sha256
            != deterministic_quality_gate.gate_evidence_sha256
        ):
            blockers.append(f"APPROVAL_DQG_EVIDENCE_MISMATCH:{record.approval_id}")
            continue
        if (
            record.governance_gate_evidence_sha256
            != governance_gate.gate_evidence_sha256
        ):
            blockers.append(f"APPROVAL_DGG_EVIDENCE_MISMATCH:{record.approval_id}")
            continue
        if not record.evidence_hash:
            blockers.append(f"APPROVAL_EVIDENCE_HASH_MISSING:{record.approval_id}")
            continue
        if record.evidence_hash != evidence_hash:
            blockers.append(f"APPROVAL_EVIDENCE_HASH_MISMATCH:{record.approval_id}")
            continue
        if not record.authority_family_sha256:
            blockers.append(f"APPROVAL_AUTHORITY_FAMILY_MISSING:{record.approval_id}")
            continue
        if record.authority_family_sha256 != authority_family_sha256:
            blockers.append(f"APPROVAL_AUTHORITY_FAMILY_MISMATCH:{record.approval_id}")
            continue
        if not record.lifecycle_definition_sha256:
            blockers.append(
                f"APPROVAL_LIFECYCLE_DEFINITION_MISSING:{record.approval_id}"
            )
            continue
        if record.lifecycle_definition_sha256 != lifecycle_definition_sha256:
            blockers.append(
                f"APPROVAL_LIFECYCLE_DEFINITION_MISMATCH:{record.approval_id}"
            )
            continue
        if record.revoked_at is not None:
            blockers.append(f"APPROVAL_REVOKED:{record.approval_id}")
            continue
        if record.expires_at is not None and record.expires_at <= now:
            blockers.append(f"APPROVAL_EXPIRED:{record.approval_id}")
            continue
        valid_count += 1
    if len(set(approver_ids)) != len(approver_ids):
        blockers.append("APPROVAL_APPROVER_IDENTITY_COLLISION")
    if len(set(principal_ids)) != len(principal_ids):
        blockers.append("APPROVAL_PRINCIPAL_IDENTITY_COLLISION")
    if valid_count < required_count:
        blockers.append("APPROVAL_REQUIRED")
    status = (
        ApprovalVerificationStatus.PASS
        if not blockers
        else ApprovalVerificationStatus.RUNNING_WITH_BLOCKERS
    )
    lifecycle_stage = (
        GovernanceEvidenceLifecycleStage.CONSEQUENTIAL_AUTHORITY_CONFIRMED
        if status is ApprovalVerificationStatus.PASS
        else GovernanceEvidenceLifecycleStage.HUMAN_APPROVAL_REQUIRED
    )
    if any(blocker.startswith("APPROVAL_EXPIRED:") for blocker in blockers):
        lifecycle_stage = GovernanceEvidenceLifecycleStage.EXPIRED
    elif any(
        blocker.startswith(prefix)
        for prefix in (
            "APPROVAL_SUBJECT_MISMATCH:",
            "APPROVAL_SCOPE_MISMATCH:",
            "APPROVAL_DQG_EVIDENCE_MISMATCH:",
            "APPROVAL_DGG_EVIDENCE_MISMATCH:",
            "APPROVAL_EVIDENCE_HASH_MISSING:",
            "APPROVAL_EVIDENCE_HASH_MISMATCH:",
            "APPROVAL_AUTHORITY_FAMILY_MISSING:",
            "APPROVAL_AUTHORITY_FAMILY_MISMATCH:",
            "APPROVAL_LIFECYCLE_DEFINITION_MISSING:",
            "APPROVAL_LIFECYCLE_DEFINITION_MISMATCH:",
            "APPROVAL_CHANGE_CLASS_MISMATCH:",
            "APPROVAL_REVOKED:",
        )
        for blocker in blockers
    ):
        lifecycle_stage = GovernanceEvidenceLifecycleStage.INVALIDATED
    return ApprovalVerificationEvidence(
        change_class=change_class,
        status=status,
        lifecycle_stage=lifecycle_stage,
        approval_required=True,
        required_approval_count=required_count,
        observed_approval_count=valid_count,
        subject_id=subject_digest.subject_id,
        scope_hash=scope_hash,
        deterministic_quality_gate_evidence_sha256=(
            deterministic_quality_gate.gate_evidence_sha256
        ),
        deterministic_governance_gate_evidence_sha256=(
            governance_gate.gate_evidence_sha256
        ),
        evidence_hash=evidence_hash,
        authority_family_sha256=authority_family_sha256,
        lifecycle_definition_sha256=lifecycle_definition_sha256,
        approval_ids=tuple(approval_ids),
        approver_ids=tuple(approver_ids),
        principal_ids=tuple(principal_ids),
        blockers=tuple(dict.fromkeys(blockers)),
        high_assurance_required=high_assurance_required,
        constitution_sync_required=constitution_sync_required,
        enforced=enforced,
        hard_veto=True,
    )


def _approval_requirements(
    change_class: ChangeApprovalClass,
) -> tuple[int, bool, bool]:
    required_count = 0
    if (
        change_class
        in _GOVERNED_RELEASE_CONTROL.approval_packet_required_change_classes
    ):
        required_count = 1
    if change_class in _GOVERNED_RELEASE_CONTROL.double_approval_change_classes:
        required_count = 2
    return (
        required_count,
        change_class in _GOVERNED_RELEASE_CONTROL.constitution_sync_change_classes,
        change_class in _GOVERNED_RELEASE_CONTROL.high_assurance_change_classes,
    )


def _build_traceability_audit(repository_root: Path) -> TraceabilityAuditReport:
    resolved_repository_root = repository_root.resolve()
    journal_path = canonical_trace_journal_path(resolved_repository_root)
    requirements, resolver_blockers = _resolve_traceability_requirements(
        resolved_repository_root
    )
    journal = CanonicalTraceJournal(journal_path)
    try:
        record_count = len(journal.records())
    except ValueError:
        return TraceabilityAuditReport(
            journal_path=journal_path.resolve(),
            status=TraceabilityStatus.RUNNING_WITH_BLOCKERS,
            requirement_count=len(requirements),
            record_count=0,
            blockers=tuple(
                dict.fromkeys(("CANONICAL_TRACE_JOURNAL_INVALID", *resolver_blockers))
            ),
        )
    if resolver_blockers:
        return TraceabilityAuditReport(
            journal_path=journal_path.resolve(),
            status=TraceabilityStatus.RUNNING_WITH_BLOCKERS,
            requirement_count=len(requirements),
            record_count=record_count,
            blockers=tuple(dict.fromkeys(resolver_blockers)),
        )
    return journal.audit(requirements)


def _traceability_hard_veto_required(audit: TraceabilityAuditReport) -> bool:
    return audit.requirement_count > 0 or bool(audit.blockers)


def _resolve_traceability_requirements(
    repository_root: Path,
) -> tuple[tuple[TraceabilityRequirement, ...], tuple[str, ...]]:
    requirements: list[TraceabilityRequirement] = []
    blockers: list[str] = []
    for relative_path in _TRACEABILITY_REQUIREMENT_ARTIFACT_PATHS:
        artifact_path = repository_root / relative_path
        if not artifact_path.is_file():
            continue
        try:
            payload = _load_json_report_object(
                artifact_path,
                artifact_name="traceability requirement artifact",
            )
            requirements.extend(
                _traceability_requirements_from_auto_audit_artifact(
                    payload,
                    report_path=str(artifact_path),
                )
            )
        except ValueError:
            blockers.append(
                "CANONICAL_TRACE_REQUIREMENT_ARTIFACT_INVALID:"
                f"{_traceability_artifact_token(relative_path)}"
            )
    return tuple(dict.fromkeys(requirements)), tuple(dict.fromkeys(blockers))


def _traceability_requirements_from_auto_audit_artifact(
    payload: dict[str, object],
    *,
    report_path: str,
) -> tuple[TraceabilityRequirement, ...]:
    cycles = payload.get("cycles")
    if not isinstance(cycles, list):
        raise ValueError("auto-audit traceability artifact cycles must be a list")
    requirements: list[TraceabilityRequirement] = []
    for cycle in cycles:
        if not isinstance(cycle, dict):
            raise ValueError("auto-audit cycle payload must be a JSON object")
        continuous = cycle.get("continuous_assurance")
        if continuous is None:
            continue
        if not isinstance(continuous, dict):
            raise ValueError("continuous_assurance payload must be a JSON object")
        trust = continuous.get("trust_assurance")
        if not isinstance(trust, dict):
            raise ValueError("continuous_assurance trust_assurance is required")
        provenance = trust.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("continuous_assurance provenance is required")
        decision_id = _traceability_required_payload_string(
            provenance,
            "decision_id",
            report_path=report_path,
        )
        requirements.append(
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.DECISION,
                subject_ref=decision_id,
                event_name="DECISION_PROVENANCE_RECORDED",
                subject_type="DECISION_PROVENANCE_RECORD",
            )
        )
        evaluations = trust.get("policy_evaluations")
        if not isinstance(evaluations, list):
            raise ValueError("continuous_assurance policy_evaluations must be a list")
        for evaluation in evaluations:
            if not isinstance(evaluation, dict):
                raise ValueError("policy evaluation payload must be a JSON object")
            evaluation_id = _traceability_required_payload_string(
                evaluation,
                "evaluation_id",
                report_path=report_path,
            )
            requirements.append(
                TraceabilityRequirement(
                    trace_kind=ConsequentialTraceKind.POLICY_EVALUATION,
                    subject_ref=evaluation_id,
                    event_name="POLICY_EVALUATION_RECORDED",
                    subject_type="POLICY_EVALUATION_RECORD",
                )
            )
    return tuple(dict.fromkeys(requirements))


def _traceability_artifact_token(relative_path: str) -> str:
    return (
        _normalize_path(relative_path)
        .replace("/", "_")
        .replace("-", "_")
        .replace(".", "_")
        .upper()
    )


def _classify_change_set(
    change_set: GovernanceChangeSet | None,
) -> ChangeApprovalClass:
    if change_set is None or not change_set.changed_paths:
        return ChangeApprovalClass.C0_NON_BEHAVIORAL
    if any(
        _matches_any(path, _CONSEQUENTIAL_CHANGE_PREFIXES)
        for path in change_set.changed_paths
    ):
        return ChangeApprovalClass.C4_CONSEQUENTIAL
    if any(
        _matches_any(path, _GOVERNED_CHANGE_PREFIXES)
        for path in change_set.changed_paths
    ):
        return ChangeApprovalClass.C3_GOVERNED
    if any(
        path.startswith(("src/", "scripts/", "config/", "pyproject.toml"))
        for path in change_set.changed_paths
    ):
        return ChangeApprovalClass.C2_BEHAVIORAL
    return ChangeApprovalClass.C1_LOW_RISK


def _build_governance_subject_digest(
    repository_root: Path,
    change_set: GovernanceChangeSet | None = None,
) -> GovernanceSubjectDigest:
    resolved_repository_root = repository_root.resolve()
    repository_entries = tuple(_subject_digest_entries(resolved_repository_root))
    repository_tree_sha256 = hashlib.sha256(
        "\n".join(repository_entries).encode("utf-8")
    ).hexdigest()
    authority_family_sha256 = _authority_family_sha256(resolved_repository_root)
    git_commit = "UNKNOWN" if change_set is None else change_set.git_commit
    change_set_sha256 = (
        _EMPTY_CHANGE_SET_SHA256 if change_set is None else change_set.change_set_sha256
    )
    subject_sha256 = hashlib.sha256(
        json.dumps(
            {
                "repository_root": str(resolved_repository_root),
                "subject_scope": _SUBJECT_DIGEST_SCOPE,
                "authority_family_sha256": authority_family_sha256,
                "repository_tree_sha256": repository_tree_sha256,
                "git_commit": git_commit,
                "change_set_sha256": change_set_sha256,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return GovernanceSubjectDigest(
        repository_root=resolved_repository_root,
        subject_scope=_SUBJECT_DIGEST_SCOPE,
        authority_family_sha256=authority_family_sha256,
        repository_tree_sha256=repository_tree_sha256,
        subject_sha256=subject_sha256,
        entry_count=len(repository_entries),
        git_commit=git_commit,
        change_set_sha256=change_set_sha256,
        subject_id=subject_sha256,
        changed_path_count=0 if change_set is None else len(change_set.changed_paths),
    )


def _subject_digest_entries(repository_root: Path) -> Iterable[str]:
    for current_root, dirnames, filenames in os.walk(repository_root):
        current_path = Path(current_root)
        relative_parts = (
            ()
            if current_path == repository_root
            else current_path.relative_to(repository_root).parts
        )
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _subject_digest_ignores((*relative_parts, name))
        )
        if relative_parts:
            yield f"D:{Path(*relative_parts).as_posix()}"
        for filename in sorted(filenames):
            relative_file_parts = (*relative_parts, filename)
            if _subject_digest_ignores(relative_file_parts):
                continue
            relative = Path(*relative_file_parts).as_posix()
            yield f"F:{relative}:{_sha256(repository_root / relative)}"


def _subject_digest_ignores(parts: tuple[str, ...]) -> bool:
    for part in parts:
        normalized = part.lower()
        if normalized in _SUBJECT_DIGEST_IGNORED_PARTS:
            return True
        if normalized.startswith(".pytest-tmp"):
            return True
        if normalized == ".coverage" or normalized.startswith(".coverage."):
            return True
    return False


def _authority_family_sha256(repository_root: Path) -> str:
    payload = [
        f"{relative}|{_sha256(repository_root / relative)}"
        if (repository_root / relative).is_file()
        else f"{relative}|MISSING"
        for relative in _AUTHORITY_BASELINE_PATHS
    ]
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


def _approval_evidence_hash(
    *,
    deterministic_quality_gate: DeterministicQualityGateReport,
    governance_gate: GovernanceGateReport,
) -> str:
    return _canonical_sha256(
        {
            "deterministic_governance_gate_evidence_sha256": (
                governance_gate.gate_evidence_sha256
            ),
            "deterministic_quality_gate_evidence_sha256": (
                deterministic_quality_gate.gate_evidence_sha256
            ),
        }
    )


def _lifecycle_definition_sha256() -> str:
    return _sha256(Path(governance_primitives_module.__file__).resolve())


def _subject_digests_match(
    current_subject: GovernanceSubjectDigest,
    recorded_subject: GovernanceSubjectDigest | None,
) -> bool:
    if recorded_subject is None:
        return False
    return (
        current_subject.repository_root == recorded_subject.repository_root
        and current_subject.subject_scope == recorded_subject.subject_scope
        and current_subject.authority_family_sha256
        == recorded_subject.authority_family_sha256
        and current_subject.repository_tree_sha256
        == recorded_subject.repository_tree_sha256
        and current_subject.git_commit == recorded_subject.git_commit
        and current_subject.change_set_sha256 == recorded_subject.change_set_sha256
        and current_subject.subject_sha256 == recorded_subject.subject_sha256
        and current_subject.subject_id == recorded_subject.subject_id
    )


def _build_hygiene_check(
    check_id: str,
    blockers: tuple[str, ...],
) -> DeterministicSubGateCheck:
    normalized_blockers = tuple(dict.fromkeys(blockers))
    return DeterministicSubGateCheck(
        check_id=check_id,
        status=(
            DeterministicSubGateStatus.PASS
            if not normalized_blockers
            else DeterministicSubGateStatus.RUNNING_WITH_BLOCKERS
        ),
        blockers=normalized_blockers,
    )


def _matches_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_paths(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(_normalize_path(value) for value in values)
    _require_unique_nonblank("normalized paths", normalized)
    return normalized


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip()


def _parse_git_status_path(raw_value: str) -> str:
    value = raw_value.strip()
    if " -> " in value:
        value = value.rsplit(" -> ", maxsplit=1)[-1]
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return _normalize_path(value)


def _repository_git_commit(repository_root: Path) -> str:
    git_executable = _git_executable()
    if git_executable is None:
        return "WORKTREE_UNCOMMITTED"
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [git_executable, "-C", str(repository_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return "WORKTREE_UNCOMMITTED"
    if completed.returncode != 0:
        return "WORKTREE_UNCOMMITTED"
    commit = completed.stdout.strip()
    return commit or "WORKTREE_UNCOMMITTED"


def _git_repository_root(repository_root: Path) -> Path | None:
    git_executable = _git_executable()
    if git_executable is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [
                git_executable,
                "-C",
                str(repository_root),
                "rev-parse",
                "--show-toplevel",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    if not output:
        return None
    return Path(output).resolve()


def _git_executable() -> str | None:
    return shutil.which("git")


def _is_subject_path(relative_path: str) -> bool:
    normalized_path = _normalize_path(relative_path)
    parts = tuple(part for part in normalized_path.split("/") if part)
    return bool(parts) and not _subject_digest_ignores(parts)


def _cli_change_set(
    *,
    repository_root: Path,
    changed_paths: list[str],
    git_commit: str | None,
    required: bool,
) -> GovernanceChangeSet | None:
    resolved_repository_root = repository_root.resolve()
    if changed_paths:
        return GovernanceChangeSet(
            repository_root=resolved_repository_root,
            git_commit=git_commit or _repository_git_commit(resolved_repository_root),
            changed_paths=tuple(changed_paths),
        )
    resolved_change_set = resolve_governance_change_set(resolved_repository_root)
    if resolved_change_set is not None:
        return resolved_change_set
    if required:
        raise ValueError("governance gate requires deterministic change set evidence")
    return None


def _load_json_report_object(
    report_path: Path, *, artifact_name: str
) -> dict[str, object]:
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{artifact_name} must be a JSON object")
    return cast(dict[str, object], payload)


def load_repository_validator_evidence(
    report_path: Path,
) -> RepositoryValidatorEvidence:
    """Load the summarized repository validator artifact used by the gate."""

    payload = _load_json_report_object(
        report_path,
        artifact_name="repository validator report",
    )
    blockers = payload.get("blockers", [])
    findings = payload.get("findings", [])
    if not isinstance(blockers, list) or not isinstance(findings, list):
        raise ValueError("repository validator report blockers/findings must be arrays")
    repository_health_score = payload.get("repository_health_score", -1)
    if not isinstance(repository_health_score, int):
        raise ValueError(
            "repository validator report repository_health_score must be an int"
        )
    return RepositoryValidatorEvidence(
        status=str(payload.get("status", "")),
        report_path=report_path.as_posix(),
        blocker_count=len(blockers),
        finding_count=len(findings),
        repository_health_score=repository_health_score,
        blocker_ids=tuple(str(item) for item in blockers),
        findings=tuple(
            _repository_validator_finding_evidence(
                item,
                report_path=report_path.as_posix(),
            )
            for item in findings
        ),
    )


def load_deterministic_quality_gate_report(
    report_path: Path,
) -> DeterministicQualityGateReport:
    payload = _load_json_report_object(
        report_path,
        artifact_name="deterministic quality gate report",
    )
    quality_evidence = payload.get("quality_evidence_gate")
    security_scan = payload.get("security_scan")
    subject_digest = payload.get("subject_digest")
    if (
        not isinstance(quality_evidence, dict)
        or not isinstance(security_scan, dict)
        or not isinstance(subject_digest, dict)
    ):
        raise ValueError(
            "deterministic quality gate report requires quality, security, "
            "and subject digest evidence"
        )
    quality_gate = quality_evidence.get("quality_gate")
    if not isinstance(quality_gate, dict):
        raise ValueError(
            "deterministic quality gate report requires quality gate payload"
        )
    report_blockers = payload.get("blockers", [])
    if not isinstance(report_blockers, list):
        raise ValueError("deterministic quality gate report blockers must be an array")
    change_set_payload = payload.get("change_set")
    if change_set_payload is not None and not isinstance(change_set_payload, dict):
        raise ValueError(
            "deterministic quality gate report change_set must be an object"
        )
    return DeterministicQualityGateReport(
        gate_id=str(payload.get("gate_id", "")),
        repository_root=Path(str(payload.get("repository_root", ""))),
        quality_evidence_gate=QualityEvidenceGateEvidence(
            status=DeterministicSubGateStatus(str(quality_evidence.get("status", ""))),
            blockers=tuple(str(item) for item in quality_evidence.get("blockers", [])),
            quality_gate=QualityGateEvidence(
                status=str(quality_gate.get("status", "")),
                command=str(quality_gate.get("command", "")),
                pytest_pass_count=int(quality_gate.get("pytest_pass_count", 0)),
                coverage_percent=float(quality_gate.get("coverage_percent", 0.0)),
                coverage_source=str(quality_gate.get("coverage_source", "")),
                coverage_realism_proof_path=str(
                    quality_gate.get("coverage_realism_proof_path", "")
                ),
                coverage_realism_proof_sha256=str(
                    quality_gate.get("coverage_realism_proof_sha256", "")
                ).lower(),
                execution_allowed=bool(quality_gate.get("execution_allowed", True)),
                promotion_status=str(quality_gate.get("promotion_status", "")),
                live_eligibility_status=str(
                    quality_gate.get("live_eligibility_status", "")
                ),
                generated_at_utc=cast(
                    str | None,
                    quality_gate.get("generated_at_utc"),
                ),
                workspace_attestation=(
                    None
                    if not isinstance(
                        quality_gate.get("workspace_attestation"),
                        dict,
                    )
                    else WorkspaceAttestation(
                        repository_root=Path(
                            str(
                                cast(
                                    dict[str, object],
                                    quality_gate["workspace_attestation"],
                                ).get("repository_root", "")
                            )
                        ),
                        repository_tree_sha256=str(
                            cast(
                                dict[str, object],
                                quality_gate["workspace_attestation"],
                            ).get("repository_tree_sha256", "")
                        ).lower(),
                        git_commit=str(
                            cast(
                                dict[str, object],
                                quality_gate["workspace_attestation"],
                            ).get("git_commit", "")
                        ),
                        change_set_sha256=str(
                            cast(
                                dict[str, object],
                                quality_gate["workspace_attestation"],
                            ).get("change_set_sha256", "")
                        ).lower(),
                    )
                ),
            ),
        ),
        security_scan=SecurityScanEvidence(
            check_id=str(security_scan.get("check_id", "")),
            command=str(security_scan.get("command", "")),
            passed=bool(security_scan.get("passed", False)),
            failure_detail=str(security_scan.get("failure_detail", "")),
            evidence_source=str(security_scan.get("evidence_source", "")),
            evidence_path=str(security_scan.get("evidence_path", "")),
            evidence_sha256=str(security_scan.get("evidence_sha256", "")).lower(),
            execution_allowed=bool(security_scan.get("execution_allowed", True)),
            promotion_status=str(security_scan.get("promotion_status", "")),
            live_eligibility_status=str(
                security_scan.get("live_eligibility_status", "")
            ),
        ),
        change_set=(
            None
            if change_set_payload is None
            else GovernanceChangeSet(
                repository_root=Path(
                    str(change_set_payload.get("repository_root", ""))
                ),
                git_commit=str(change_set_payload.get("git_commit", "")),
                staged_paths=tuple(
                    str(item) for item in change_set_payload.get("staged_paths", [])
                ),
                unstaged_paths=tuple(
                    str(item) for item in change_set_payload.get("unstaged_paths", [])
                ),
                untracked_governed_paths=tuple(
                    str(item)
                    for item in change_set_payload.get(
                        "untracked_governed_paths",
                        [],
                    )
                ),
                changed_paths=tuple(
                    str(item) for item in change_set_payload.get("changed_paths", [])
                ),
                change_set_sha256=str(
                    change_set_payload.get("change_set_sha256", "")
                ).lower(),
            )
        ),
        subject_digest=GovernanceSubjectDigest(
            repository_root=Path(str(subject_digest.get("repository_root", ""))),
            subject_scope=str(subject_digest.get("subject_scope", "")),
            authority_family_sha256=str(
                subject_digest.get("authority_family_sha256", "")
            ).lower(),
            repository_tree_sha256=str(
                subject_digest.get("repository_tree_sha256", "")
            ).lower(),
            subject_sha256=str(subject_digest.get("subject_sha256", "")).lower(),
            entry_count=int(subject_digest.get("entry_count", -1)),
            git_commit=str(subject_digest.get("git_commit", "UNKNOWN")),
            change_set_sha256=str(
                subject_digest.get("change_set_sha256", _EMPTY_CHANGE_SET_SHA256)
            ).lower(),
            subject_id=str(
                subject_digest.get(
                    "subject_id",
                    subject_digest.get("subject_sha256", ""),
                )
            ).lower(),
            changed_path_count=int(subject_digest.get("changed_path_count", 0)),
        ),
        blockers=tuple(str(item) for item in report_blockers),
        status=GovernanceGateStatus(str(payload.get("status", ""))),
        lifecycle_stage=(
            None
            if payload.get("lifecycle_stage") is None
            else GovernanceEvidenceLifecycleStage(str(payload.get("lifecycle_stage")))
        ),
        gate_evidence_sha256=str(payload.get("gate_evidence_sha256", "")).lower(),
        execution_allowed=bool(payload.get("execution_allowed", True)),
        promotion_status=str(payload.get("promotion_status", "")),
        live_eligibility_status=str(payload.get("live_eligibility_status", "")),
    )


def load_approval_records(report_path: Path) -> tuple[ApprovalRecord, ...]:
    payload = _load_json_report_object(
        report_path,
        artifact_name="approval record report",
    )
    raw_records = payload.get("approval_records", [])
    if not isinstance(raw_records, list):
        raise ValueError("approval record report approval_records must be an array")
    approvals: list[ApprovalRecord] = []
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError("approval record report approval_records must be objects")
        evidence_refs = item.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            raise ValueError("approval record evidence_refs must be an array")
        approved_at = _parse_approval_timestamp(
            "approval record approved_at_utc",
            item.get("approved_at_utc"),
        )
        expires_at_raw = item.get("expires_at_utc")
        expires_at = (
            None
            if expires_at_raw in (None, "")
            else _parse_approval_timestamp(
                "approval record expires_at_utc",
                expires_at_raw,
            )
        )
        revoked_at_raw = item.get("revoked_at_utc")
        revoked_at = (
            None
            if revoked_at_raw in (None, "")
            else _parse_approval_timestamp(
                "approval record revoked_at_utc",
                revoked_at_raw,
            )
        )
        approvals.append(
            ApprovalRecord(
                identity=WorkflowIdentity(
                    work_order_id=str(
                        item.get("work_order_id", f"approval-work-order-{index}")
                    ),
                    run_id=str(item.get("run_id", f"approval-run-{index}")),
                    trace_id=str(item.get("trace_id", f"approval-trace-{index}")),
                    created_at=approved_at,
                ),
                approval_id=str(item.get("approval_id", "")),
                approver_id=str(item.get("approver_id", "")),
                subject_ref=str(
                    item.get(
                        "subject_ref",
                        "runtime/artifacts/quality/gate/governance_gate_latest.json",
                    )
                ),
                status=ApprovalStatus(str(item.get("status", ""))),
                evidence_refs=tuple(str(value) for value in evidence_refs),
                approver_role=str(item.get("approver_role", "")),
                change_class=(
                    None
                    if item.get("change_class") is None
                    else ChangeApprovalClass(str(item.get("change_class", "")))
                ),
                subject_sha256=str(item.get("subject_sha256", "")).lower(),
                scope_hash=str(item.get("scope_hash", "")).lower(),
                quality_gate_evidence_sha256=str(
                    item.get("quality_gate_evidence_sha256", "")
                ).lower(),
                governance_gate_evidence_sha256=str(
                    item.get("governance_gate_evidence_sha256", "")
                ).lower(),
                evidence_hash=str(item.get("evidence_hash", "")).lower(),
                authority_family_sha256=str(
                    item.get("authority_family_sha256", "")
                ).lower(),
                lifecycle_definition_sha256=str(
                    item.get("lifecycle_definition_sha256", "")
                ).lower(),
                approved_at=approved_at,
                expires_at=expires_at,
                revoked_at=revoked_at,
                principal_id=str(item.get("principal_id", item.get("approver_id", ""))),
                execution_allowed=bool(item.get("execution_allowed", False)),
                live_eligibility_status=str(
                    item.get("live_eligibility_status", "LIVE_ORDER_BLOCKED")
                ),
            )
        )
    return tuple(approvals)


def load_approval_records_with_fallback(
    repository_root: Path,
    report_path: Path | None = None,
) -> tuple[ApprovalRecord, ...]:
    default_candidate = repository_root.resolve() / DEFAULT_APPROVAL_RECORD_REPORT
    if report_path is not None and report_path.is_file():
        return load_approval_records(report_path)
    if not default_candidate.is_file():
        return ()
    return load_approval_records(default_candidate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic quality or governance gate reports."
    )
    parser.add_argument(
        "--mode",
        choices=("deterministic-quality", "governance"),
    )
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--repository-validator-report")
    parser.add_argument("--docs-hygiene-command")
    parser.add_argument("--docs-hygiene-tests", nargs="+")
    parser.add_argument("--docs-hygiene-passed", choices=("true", "false"))
    parser.add_argument("--docs-hygiene-evidence-source")
    parser.add_argument("--docs-hygiene-evidence-path")
    parser.add_argument("--docs-hygiene-evidence-sha256")
    parser.add_argument("--artifact-hygiene-command")
    parser.add_argument("--artifact-hygiene-tests", nargs="+")
    parser.add_argument("--artifact-hygiene-passed", choices=("true", "false"))
    parser.add_argument("--artifact-hygiene-evidence-source")
    parser.add_argument("--artifact-hygiene-evidence-path")
    parser.add_argument("--artifact-hygiene-evidence-sha256")
    parser.add_argument("--constitution-sync-command")
    parser.add_argument("--constitution-sync-tests", nargs="+")
    parser.add_argument("--constitution-sync-passed", choices=("true", "false"))
    parser.add_argument("--constitution-sync-evidence-source")
    parser.add_argument("--constitution-sync-evidence-path")
    parser.add_argument("--constitution-sync-evidence-sha256")
    parser.add_argument("--quality-gate-command")
    parser.add_argument("--pytest-pass-count", type=int)
    parser.add_argument("--coverage-percent", type=float)
    parser.add_argument("--coverage-source")
    parser.add_argument("--coverage-realism-proof-path")
    parser.add_argument("--coverage-realism-proof-sha256")
    parser.add_argument("--bandit-command")
    parser.add_argument("--bandit-passed", choices=("true", "false"))
    parser.add_argument("--bandit-evidence-source")
    parser.add_argument("--bandit-evidence-path")
    parser.add_argument("--bandit-evidence-sha256")
    parser.add_argument("--deterministic-quality-gate-report")
    parser.add_argument("--approval-record-report")
    parser.add_argument(
        "--changed-path",
        action="append",
        dest="changed_paths",
        default=[],
    )
    parser.add_argument("--git-commit")
    parser.add_argument("--output-json", required=True)
    parsed = parser.parse_args(argv)

    repository_root = Path(parsed.repository_root)
    output_path = Path(parsed.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected_mode = parsed.mode
    if selected_mode is None:
        selected_mode = (
            "governance"
            if parsed.repository_validator_report is not None
            else "deterministic-quality"
        )

    if selected_mode == "deterministic-quality":
        _require_arg(parsed.quality_gate_command, "quality gate command")
        _require_arg(parsed.coverage_source, "coverage source")
        _require_arg(parsed.coverage_realism_proof_path, "coverage realism proof path")
        _require_arg(
            parsed.coverage_realism_proof_sha256, "coverage realism proof sha256"
        )
        _require_arg(parsed.bandit_command, "bandit command")
        if parsed.pytest_pass_count is None:
            raise ValueError("pytest pass count is required")
        if parsed.coverage_percent is None:
            raise ValueError("coverage percent is required")
        if parsed.bandit_passed is None:
            raise ValueError("bandit passed is required")
        change_set = _cli_change_set(
            repository_root=repository_root,
            changed_paths=parsed.changed_paths,
            git_commit=parsed.git_commit,
            required=True,
        )
        quality_gate = QualityGateEvidence(
            status=TECHNICAL_QUALITY_PRIMARY_STATUS,
            command=parsed.quality_gate_command,
            pytest_pass_count=parsed.pytest_pass_count,
            coverage_percent=parsed.coverage_percent,
            coverage_source=parsed.coverage_source,
            coverage_realism_proof_path=parsed.coverage_realism_proof_path,
            coverage_realism_proof_sha256=parsed.coverage_realism_proof_sha256.lower(),
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
            workspace_attestation=build_quality_gate_workspace_attestation(
                repository_root
            ),
        )
        quality_report = build_deterministic_quality_gate_report(
            repository_root=repository_root,
            quality_gate=quality_gate,
            security_scan=SecurityScanEvidence(
                check_id="BANDIT",
                command=parsed.bandit_command,
                passed=parsed.bandit_passed == "true",
                failure_detail=(
                    ""
                    if parsed.bandit_passed == "true"
                    else "Bandit security scan failed."
                ),
                evidence_source=parsed.bandit_evidence_source or "",
                evidence_path=parsed.bandit_evidence_path or "",
                evidence_sha256=(parsed.bandit_evidence_sha256 or "").lower(),
            ),
            change_set=change_set,
        )
        output_path.write_text(
            json.dumps(quality_report.to_payload(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(quality_report.to_payload()))
        return 0 if quality_report.status is GovernanceGateStatus.PASS else 2

    _require_arg(parsed.repository_validator_report, "repository validator report")
    _require_arg(parsed.docs_hygiene_command, "docs hygiene command")
    _require_arg(parsed.artifact_hygiene_command, "artifact hygiene command")
    _require_arg(parsed.constitution_sync_command, "constitution sync command")
    if (
        parsed.docs_hygiene_tests is None
        or parsed.artifact_hygiene_tests is None
        or parsed.constitution_sync_tests is None
        or parsed.docs_hygiene_passed is None
        or parsed.artifact_hygiene_passed is None
        or parsed.constitution_sync_passed is None
    ):
        raise ValueError("governance gate requires full test evidence arguments")
    _require_arg(
        parsed.deterministic_quality_gate_report,
        "deterministic quality gate report",
    )
    change_set = _cli_change_set(
        repository_root=repository_root,
        changed_paths=parsed.changed_paths,
        git_commit=parsed.git_commit,
        required=True,
    )

    deterministic_quality_gate = load_deterministic_quality_gate_report(
        Path(parsed.deterministic_quality_gate_report)
    )
    governance_report = build_governance_gate_report(
        repository_root=repository_root,
        repository_validator=load_repository_validator_evidence(
            Path(parsed.repository_validator_report)
        ),
        docs_hygiene=GovernanceTestEvidence(
            check_id="DOCS_HYGIENE",
            command=parsed.docs_hygiene_command,
            selected_tests=tuple(parsed.docs_hygiene_tests),
            passed=parsed.docs_hygiene_passed == "true",
            failure_detail=(
                ""
                if parsed.docs_hygiene_passed == "true"
                else "Docs hygiene evidence is not satisfied."
            ),
            evidence_source=parsed.docs_hygiene_evidence_source or "",
            evidence_path=parsed.docs_hygiene_evidence_path or "",
            evidence_sha256=(parsed.docs_hygiene_evidence_sha256 or "").lower(),
        ),
        artifact_hygiene=GovernanceTestEvidence(
            check_id="ARTIFACT_HYGIENE",
            command=parsed.artifact_hygiene_command,
            selected_tests=tuple(parsed.artifact_hygiene_tests),
            passed=parsed.artifact_hygiene_passed == "true",
            failure_detail=(
                ""
                if parsed.artifact_hygiene_passed == "true"
                else "Artifact hygiene evidence is not satisfied."
            ),
            evidence_source=parsed.artifact_hygiene_evidence_source or "",
            evidence_path=parsed.artifact_hygiene_evidence_path or "",
            evidence_sha256=(parsed.artifact_hygiene_evidence_sha256 or "").lower(),
        ),
        constitution_sync_tests=GovernanceTestEvidence(
            check_id="CONSTITUTION_SYNC",
            command=parsed.constitution_sync_command,
            selected_tests=tuple(parsed.constitution_sync_tests),
            passed=parsed.constitution_sync_passed == "true",
            failure_detail=(
                ""
                if parsed.constitution_sync_passed == "true"
                else "Constitution sync evidence is not satisfied."
            ),
            evidence_source=parsed.constitution_sync_evidence_source or "",
            evidence_path=parsed.constitution_sync_evidence_path or "",
            evidence_sha256=(parsed.constitution_sync_evidence_sha256 or "").lower(),
        ),
        deterministic_quality_gate=deterministic_quality_gate,
        change_set=change_set,
        approval_records=load_approval_records_with_fallback(
            repository_root,
            (
                None
                if parsed.approval_record_report is None
                else Path(parsed.approval_record_report)
            ),
        ),
        require_change_set=True,
    )
    output_path.write_text(
        json.dumps(governance_report.to_payload(), indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(governance_report.to_payload()))
    return 0 if governance_report.status is GovernanceGateStatus.PASS else 2


def _quality_gate_payload(quality_gate: QualityGateEvidence) -> dict[str, object]:
    return {
        "status": quality_gate.status,
        "command": quality_gate.command,
        "pytest_pass_count": quality_gate.pytest_pass_count,
        "coverage_percent": quality_gate.coverage_percent,
        "coverage_source": quality_gate.coverage_source,
        "coverage_realism_proof_path": quality_gate.coverage_realism_proof_path,
        "coverage_realism_proof_sha256": quality_gate.coverage_realism_proof_sha256,
        "generated_at_utc": quality_gate.generated_at_utc,
        "workspace_attestation": (
            None
            if quality_gate.workspace_attestation is None
            else quality_gate.workspace_attestation.to_payload()
        ),
        "execution_allowed": False,
        "promotion_status": quality_gate.promotion_status,
        "live_eligibility_status": quality_gate.live_eligibility_status,
    }


def _parse_approval_timestamp(name: str, value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _frontmatter(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if text.startswith("---\r\n"):
        offset = 5
    elif text.startswith("---\n"):
        offset = 4
    else:
        return None
    end = text.find("\n---", offset)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    for raw_line in text[offset:end].splitlines():
        if raw_line[:1].isspace():
            continue
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("\"'")
    return fields


def _metadata_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be true or false")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority_snapshot_sha256(
    authority_snapshot: tuple[AuthorityDocumentSnapshot, ...],
) -> str:
    payload = json.dumps(
        [snapshot.to_payload() for snapshot in authority_snapshot],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _repository_validator_finding_evidence(
    payload: object,
    *,
    report_path: str,
) -> RepositoryValidatorFindingEvidence:
    if not isinstance(payload, dict):
        raise ValueError(
            f"repository validator findings must be objects in {report_path}"
        )
    control_family = _required_payload_string(
        payload,
        "control_family",
        report_path=report_path,
    )
    domain = _required_payload_string(
        payload,
        "domain",
        report_path=report_path,
    )
    severity = _required_payload_string(
        payload,
        "severity",
        report_path=report_path,
    )
    rule_id = _required_payload_string(
        payload,
        "rule_id",
        report_path=report_path,
    )
    path = _required_payload_string(
        payload,
        "path",
        report_path=report_path,
    )
    finding_id = _required_payload_string(
        payload,
        "finding_id",
        report_path=report_path,
    )
    return RepositoryValidatorFindingEvidence(
        control_family=control_family,
        domain=domain,
        severity=severity,
        rule_id=rule_id,
        path=path,
        blocker=bool(payload.get("blocker", False)),
        finding_id=finding_id,
    )


def _required_payload_string(
    payload: dict[str, object],
    field_name: str,
    *,
    report_path: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "repository validator finding "
            f"{field_name} must be a non-empty string in {report_path}"
        )
    return value


def _traceability_required_payload_string(
    payload: dict[str, object],
    field_name: str,
    *,
    report_path: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "traceability requirement "
            f"{field_name} must be a non-empty string in {report_path}"
        )
    return value


def _finding_gate_blocker_id(finding: RepositoryValidatorFindingEvidence) -> str:
    return f"{finding.rule_id}:{finding.path}"


def _validate_optional_artifact_lineage(
    *,
    artifact_name: str,
    evidence_source: str,
    evidence_path: str,
    evidence_sha256: str,
) -> None:
    lineage_values = (
        evidence_source.strip(),
        evidence_path.strip(),
        evidence_sha256.strip().lower(),
    )
    if not any(lineage_values):
        return
    if not all(lineage_values):
        raise ValueError(f"{artifact_name} requires complete artifact lineage")
    if Path(evidence_path).is_absolute():
        raise ValueError(f"{artifact_name} evidence_path must be repository-relative")
    if not _SHA256_RE.fullmatch(evidence_sha256.strip().lower()):
        raise ValueError(f"{artifact_name} evidence_sha256 must be lowercase sha256")


def _require_arg(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _require_unique_identity_or_collision_blocker(
    name: str,
    values: tuple[str, ...],
    blockers: tuple[str, ...],
    collision_blocker: str,
) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) == len(values):
        return
    if collision_blocker not in blockers:
        raise ValueError(f"{name} must be unique")


if __name__ == "__main__":
    raise SystemExit(main())

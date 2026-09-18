"""Admission gate for capability-bounded unattended jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class JobCapability(StrEnum):
    READ_REPOSITORY = "READ_REPOSITORY"
    WRITE_ARTIFACT = "WRITE_ARTIFACT"
    RUN_FIXED_QUALITY_COMMANDS = "RUN_FIXED_QUALITY_COMMANDS"
    RUN_LOCAL_ADVISORY_FIXTURES = "RUN_LOCAL_ADVISORY_FIXTURES"


class JobAuthorityCeiling(StrEnum):
    REPORT_ONLY = "REPORT_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class JobSideEffect(StrEnum):
    READ_REPOSITORY = "READ_REPOSITORY"
    WRITE_RUNTIME_ARTIFACTS = "WRITE_RUNTIME_ARTIFACTS"
    APPEND_AUDIT_EVIDENCE = "APPEND_AUDIT_EVIDENCE"
    RUN_FIXED_QUALITY_COMMANDS = "RUN_FIXED_QUALITY_COMMANDS"
    RUN_LOCAL_ADVISORY_FIXTURES = "RUN_LOCAL_ADVISORY_FIXTURES"


class RunnerAdmissionStatus(StrEnum):
    ADMITTED_REPORT_ONLY = "ADMITTED_REPORT_ONLY"
    ADMITTED_RESEARCH_ONLY = "ADMITTED_RESEARCH_ONLY"
    BLOCKED = "BLOCKED"


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_fail_closed(
    *,
    execution_allowed: bool,
    promotion_status: str,
    live_eligibility_status: str,
    label: str,
) -> None:
    if execution_allowed:
        raise ValueError(f"{label} cannot authorize trading")
    if promotion_status != "RESEARCH_ONLY":
        raise ValueError(f"{label} cannot promote production state")
    if live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError(f"{label} must remain live blocked")


@dataclass(frozen=True, slots=True)
class JobManifest:
    job_id: str
    allowed_capabilities: tuple[JobCapability, ...]
    allowed_roots: tuple[Path, ...]
    timeout_seconds: int
    maximum_output_bytes: int
    maximum_concurrency: int
    lock_path: Path
    network_allowed: bool = False
    secret_access_allowed: bool = False
    trading_authority: bool = False

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job manifest identity is required")
        if not self.allowed_capabilities or len(set(self.allowed_capabilities)) != len(
            self.allowed_capabilities
        ):
            raise ValueError("job capabilities must be non-empty and unique")
        if not self.allowed_roots or any(
            not path.is_absolute() for path in self.allowed_roots
        ):
            raise ValueError("job roots must be non-empty absolute paths")
        if not self.lock_path.is_absolute():
            raise ValueError("job lock path must be absolute")
        if not 1 <= self.timeout_seconds <= 3_600:
            raise ValueError("job timeout must be between 1 and 3600 seconds")
        if not 1_024 <= self.maximum_output_bytes <= 10_000_000:
            raise ValueError("job output limit is invalid")
        if not 1 <= self.maximum_concurrency <= 16:
            raise ValueError("job concurrency limit is invalid")
        if self.network_allowed or self.secret_access_allowed or self.trading_authority:
            raise ValueError(
                "unattended research jobs cannot receive elevated authority"
            )


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    manifest_id: str
    job_id: str
    allowed_capabilities: tuple[JobCapability, ...]
    authority_ceiling: JobAuthorityCeiling
    side_effect_allowlist: tuple[JobSideEffect, ...]
    allowed_roots: tuple[Path, ...]
    fixed_command_refs: tuple[str, ...] = ()
    required_audit_channels: tuple[str, ...] = (
        "RUN_CARD",
        "PERSISTENT_EVIDENCE",
        "AUDIT",
    )
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.manifest_id.strip() or not self.job_id.strip():
            raise ValueError("capability manifest identity is required")
        if not self.allowed_capabilities or len(set(self.allowed_capabilities)) != len(
            self.allowed_capabilities
        ):
            raise ValueError(
                "capability manifest capabilities must be non-empty and unique"
            )
        if not self.allowed_roots or any(
            not path.is_absolute() for path in self.allowed_roots
        ):
            raise ValueError(
                "capability manifest roots must be non-empty absolute paths"
            )
        if not self.side_effect_allowlist:
            raise ValueError("capability manifest side effects must be non-empty")
        if len(set(self.side_effect_allowlist)) != len(self.side_effect_allowlist):
            raise ValueError("capability manifest side effects must be unique")
        _require_unique_text(
            "capability manifest command refs",
            self.fixed_command_refs,
        )
        _require_unique_text(
            "capability manifest audit channels",
            self.required_audit_channels,
        )
        if not _required_side_effects_for_capabilities(
            self.allowed_capabilities
        ).issubset(self.side_effect_allowlist):
            raise ValueError(
                "capability manifest side effects must cover every allowed capability"
            )
        command_capabilities = {
            JobCapability.RUN_FIXED_QUALITY_COMMANDS,
            JobCapability.RUN_LOCAL_ADVISORY_FIXTURES,
        }
        if command_capabilities.intersection(self.allowed_capabilities) and not (
            self.fixed_command_refs
        ):
            raise ValueError(
                "capability manifest requires fixed command refs for runnable work"
            )
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="capability manifest",
        )


@dataclass(frozen=True, slots=True)
class RunnerManifest:
    runner_id: str
    job_manifest: JobManifest
    capability_manifest: CapabilityManifest
    evidence_root: Path
    audit_root: Path
    universal_enforcement: tuple[str, ...] = (
        "TIMEOUT_ENFORCED",
        "LOCK_ACQUIRED",
        "PATH_SCOPE_ENFORCED",
        "LIVE_ORDER_BLOCKED",
    )
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.runner_id.strip():
            raise ValueError("runner manifest identity is required")
        if self.job_manifest.job_id != self.capability_manifest.job_id:
            raise ValueError("runner manifest job and capability manifests must agree")
        if not self.evidence_root.is_absolute() or not self.audit_root.is_absolute():
            raise ValueError("runner evidence and audit roots must be absolute")
        _require_unique_text(
            "runner universal enforcement",
            self.universal_enforcement,
        )
        required_enforcement = {
            "TIMEOUT_ENFORCED",
            "LOCK_ACQUIRED",
            "PATH_SCOPE_ENFORCED",
            "LIVE_ORDER_BLOCKED",
        }
        if not required_enforcement.issubset(self.universal_enforcement):
            raise ValueError(
                "runner manifest must include universal enforcement controls"
            )
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="runner manifest",
        )


@dataclass(frozen=True, slots=True)
class JobRequest:
    job_id: str
    idempotency_key: str
    requested_capabilities: tuple[JobCapability, ...]
    target_paths: tuple[Path, ...]
    timeout_enforced_by_runner: bool
    lock_acquired: bool
    network_requested: bool = False
    requested_side_effects: tuple[JobSideEffect, ...] = ()
    runner_id: str = ""
    command_ref: str = ""

    def __post_init__(self) -> None:
        if not self.job_id.strip() or not self.idempotency_key.strip():
            raise ValueError("job request identity is required")
        if not self.requested_capabilities:
            raise ValueError("job request capabilities cannot be empty")
        if any(not path.is_absolute() for path in self.target_paths):
            raise ValueError("job request paths must be absolute")
        if len(set(self.requested_capabilities)) != len(self.requested_capabilities):
            raise ValueError("job request capabilities must be unique")
        if len(set(self.requested_side_effects)) != len(self.requested_side_effects):
            raise ValueError("job request side effects must be unique")


@dataclass(frozen=True, slots=True)
class JobAdmission:
    job_id: str
    idempotency_key: str
    admitted: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_unique_text("job admission blockers", self.blockers)
        if self.admitted == bool(self.blockers):
            raise ValueError("job admission and blockers disagree")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="job admission",
        )


@dataclass(frozen=True, slots=True)
class RunnerRunCard:
    run_card_id: str
    runner_id: str
    job_id: str
    manifest_ref: str
    status: RunnerAdmissionStatus
    authority_ceiling: JobAuthorityCeiling
    requested_capabilities: tuple[JobCapability, ...]
    requested_side_effects: tuple[JobSideEffect, ...]
    target_paths: tuple[Path, ...]
    enforcement_applied: tuple[str, ...]
    created_at: datetime
    blockers: tuple[str, ...] = ()
    command_ref: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.run_card_id,
            self.runner_id,
            self.job_id,
            self.manifest_ref,
        ):
            if not value.strip():
                raise ValueError("runner run card identity is required")
        _require_unique_text("runner run card blockers", self.blockers)
        _require_unique_text("runner run card enforcement", self.enforcement_applied)
        _require_aware("runner run card created_at", self.created_at)
        if any(not path.is_absolute() for path in self.target_paths):
            raise ValueError("runner run card target paths must be absolute")
        if self.status is RunnerAdmissionStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked runner run card requires blockers")
        if self.status is not RunnerAdmissionStatus.BLOCKED and self.blockers:
            raise ValueError("admitted runner run card cannot contain blockers")
        if (
            JobCapability.RUN_FIXED_QUALITY_COMMANDS in self.requested_capabilities
            and self.status is not RunnerAdmissionStatus.BLOCKED
            and not self.command_ref.strip()
        ):
            raise ValueError("admitted fixed-command run card requires command_ref")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="runner run card",
        )


@dataclass(frozen=True, slots=True)
class RunnerPersistentEvidence:
    record_id: str
    run_card_id: str
    manifest_ref: str
    artifact_path: Path
    audit_path: Path
    audit_channels: tuple[str, ...]
    created_at: datetime
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (self.record_id, self.run_card_id, self.manifest_ref):
            if not value.strip():
                raise ValueError("runner persistent evidence identity is required")
        if not self.artifact_path.is_absolute() or not self.audit_path.is_absolute():
            raise ValueError("runner persistent evidence paths must be absolute")
        _require_unique_text(
            "runner persistent evidence audit channels",
            self.audit_channels,
        )
        _require_unique_text("runner persistent evidence blockers", self.blockers)
        _require_aware("runner persistent evidence created_at", self.created_at)
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="runner persistent evidence",
        )


@dataclass(frozen=True, slots=True)
class RunnerAuditRecord:
    event_id: str
    event_type: str
    runner_id: str
    subject_ref: str
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    created_at: datetime
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (self.event_id, self.event_type, self.runner_id, self.subject_ref):
            if not value.strip():
                raise ValueError("runner audit record identity is required")
        if self.event_type.upper() != self.event_type or " " in self.event_type:
            raise ValueError(
                "runner audit record event_type must be uppercase snake case"
            )
        _require_unique_text("runner audit evidence refs", self.evidence_refs)
        _require_unique_text("runner audit blockers", self.blockers)
        _require_aware("runner audit created_at", self.created_at)
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="runner audit record",
        )


@dataclass(frozen=True, slots=True)
class RunnerAdmissionReport:
    runner_id: str
    job_id: str
    authority_ceiling: JobAuthorityCeiling
    status: RunnerAdmissionStatus
    admission: JobAdmission
    run_card: RunnerRunCard
    persistent_evidence: RunnerPersistentEvidence
    audit_record: RunnerAuditRecord
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.runner_id.strip() or not self.job_id.strip():
            raise ValueError("runner admission report identity is required")
        _require_unique_text("runner admission blockers", self.blockers)
        if self.status is RunnerAdmissionStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked runner admission report requires blockers")
        if self.status is not RunnerAdmissionStatus.BLOCKED and self.blockers:
            raise ValueError("admitted runner admission report cannot contain blockers")
        if self.admission.job_id != self.job_id or self.run_card.job_id != self.job_id:
            raise ValueError("runner admission report job identifiers must agree")
        if self.run_card.runner_id != self.runner_id:
            raise ValueError("runner admission report runner identifiers must agree")
        if bool(self.blockers) != (self.status is RunnerAdmissionStatus.BLOCKED):
            raise ValueError("runner admission report status and blockers disagree")
        _require_fail_closed(
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            label="runner admission report",
        )


def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
    candidate = path.resolve(strict=False)
    resolved_roots = tuple(root.resolve(strict=False) for root in roots)
    return any(
        candidate == root or root in candidate.parents for root in resolved_roots
    )


def assess_job_admission(manifest: JobManifest, request: JobRequest) -> JobAdmission:
    blockers: list[str] = []
    if manifest.job_id != request.job_id:
        blockers.append("JOB_IDENTITY_MISMATCH")
    if not set(request.requested_capabilities).issubset(manifest.allowed_capabilities):
        blockers.append("JOB_CAPABILITY_NOT_ALLOWED")
    if any(
        not _is_within(path, manifest.allowed_roots) for path in request.target_paths
    ):
        blockers.append("JOB_PATH_NOT_ALLOWED")
    if request.network_requested:
        blockers.append("JOB_NETWORK_NOT_ALLOWED")
    if not request.timeout_enforced_by_runner:
        blockers.append("JOB_TIMEOUT_NOT_ENFORCED")
    if not request.lock_acquired:
        blockers.append("JOB_LOCK_NOT_ACQUIRED")
    return JobAdmission(
        job_id=request.job_id,
        idempotency_key=request.idempotency_key,
        admitted=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def assess_runner_admission(
    runner_manifest: RunnerManifest,
    request: JobRequest,
    *,
    observed_at: datetime,
) -> RunnerAdmissionReport:
    _require_aware("runner admission observed_at", observed_at)
    blockers = list(
        assess_job_admission(runner_manifest.job_manifest, request).blockers
    )
    capability_manifest = runner_manifest.capability_manifest
    if request.runner_id and request.runner_id != runner_manifest.runner_id:
        blockers.append("RUNNER_IDENTITY_MISMATCH")
    if not set(request.requested_capabilities).issubset(
        capability_manifest.allowed_capabilities
    ):
        blockers.append("RUNNER_CAPABILITY_MANIFEST_MISMATCH")
    if any(
        not _is_within(path, capability_manifest.allowed_roots)
        for path in request.target_paths
    ):
        blockers.append("RUNNER_CAPABILITY_ROOT_NOT_ALLOWED")
    if request.requested_side_effects and not set(
        request.requested_side_effects
    ).issubset(capability_manifest.side_effect_allowlist):
        blockers.append("RUNNER_SIDE_EFFECT_NOT_ALLOWED")
    required_side_effects = _required_side_effects_for_capabilities(
        request.requested_capabilities
    )
    if not required_side_effects.issubset(request.requested_side_effects):
        blockers.append("RUNNER_SIDE_EFFECT_REQUIRED")
    command_requested = bool(
        {
            JobCapability.RUN_FIXED_QUALITY_COMMANDS,
            JobCapability.RUN_LOCAL_ADVISORY_FIXTURES,
        }.intersection(request.requested_capabilities)
    )
    if command_requested and not request.command_ref.strip():
        blockers.append("RUNNER_COMMAND_REF_REQUIRED")
    if (
        command_requested
        and request.command_ref.strip()
        and request.command_ref not in capability_manifest.fixed_command_refs
    ):
        blockers.append("RUNNER_COMMAND_NOT_ALLOWLISTED")
    if request.command_ref.strip() and not command_requested:
        blockers.append("RUNNER_COMMAND_CAPABILITY_REQUIRED")
    blockers = list(dict.fromkeys(blockers))
    status = (
        RunnerAdmissionStatus.BLOCKED
        if blockers
        else RunnerAdmissionStatus.ADMITTED_REPORT_ONLY
        if capability_manifest.authority_ceiling is JobAuthorityCeiling.REPORT_ONLY
        else RunnerAdmissionStatus.ADMITTED_RESEARCH_ONLY
    )
    admission = JobAdmission(
        job_id=request.job_id,
        idempotency_key=request.idempotency_key,
        admitted=not blockers,
        blockers=tuple(blockers),
    )
    run_card_id = (
        f"runner-run-card:{runner_manifest.runner_id}:{request.idempotency_key}"
    )
    evidence_id = (
        "runner-persistent-evidence:"
        f"{runner_manifest.runner_id}:{request.idempotency_key}"
    )
    audit_event_id = (
        f"runner-audit:{runner_manifest.runner_id}:{request.idempotency_key}"
    )
    run_card = RunnerRunCard(
        run_card_id=run_card_id,
        runner_id=runner_manifest.runner_id,
        job_id=request.job_id,
        manifest_ref=capability_manifest.manifest_id,
        status=status,
        authority_ceiling=capability_manifest.authority_ceiling,
        requested_capabilities=request.requested_capabilities,
        requested_side_effects=request.requested_side_effects,
        target_paths=request.target_paths,
        enforcement_applied=runner_manifest.universal_enforcement,
        created_at=observed_at,
        blockers=tuple(blockers),
        command_ref=request.command_ref,
    )
    persistent_evidence = RunnerPersistentEvidence(
        record_id=evidence_id,
        run_card_id=run_card_id,
        manifest_ref=capability_manifest.manifest_id,
        artifact_path=(
            runner_manifest.evidence_root
            / f"{request.job_id}-{request.idempotency_key}.json"
        ),
        audit_path=(
            runner_manifest.audit_root
            / f"{request.job_id}-{request.idempotency_key}.jsonl"
        ),
        audit_channels=capability_manifest.required_audit_channels,
        created_at=observed_at,
        blockers=tuple(blockers),
    )
    audit_record = RunnerAuditRecord(
        event_id=audit_event_id,
        event_type=(
            "RUNNER_ADMISSION_BLOCKED" if blockers else "RUNNER_ADMISSION_ACCEPTED"
        ),
        runner_id=runner_manifest.runner_id,
        subject_ref=request.job_id,
        evidence_refs=(run_card_id, evidence_id),
        blockers=tuple(dict.fromkeys((*blockers, "LIVE_ORDER_BLOCKED"))),
        created_at=observed_at,
    )
    return RunnerAdmissionReport(
        runner_id=runner_manifest.runner_id,
        job_id=request.job_id,
        authority_ceiling=capability_manifest.authority_ceiling,
        status=status,
        admission=admission,
        run_card=run_card,
        persistent_evidence=persistent_evidence,
        audit_record=audit_record,
        blockers=tuple(blockers),
    )


def nightly_quality_job_manifest(
    repository_root: Path,
    output_directory: Path,
) -> JobManifest:
    """Return the least-privilege manifest for the existing quality loop."""
    if not repository_root.is_absolute() or not output_directory.is_absolute():
        raise ValueError("nightly quality paths must be absolute")
    return JobManifest(
        job_id="nightly-quality-triage",
        allowed_capabilities=(
            JobCapability.READ_REPOSITORY,
            JobCapability.WRITE_ARTIFACT,
            JobCapability.RUN_FIXED_QUALITY_COMMANDS,
        ),
        allowed_roots=(repository_root, output_directory),
        timeout_seconds=600,
        maximum_output_bytes=1_000_000,
        maximum_concurrency=1,
        lock_path=output_directory / ".quality-triage.lock",
    )


def nightly_quality_runner_manifest(
    repository_root: Path,
    output_directory: Path,
) -> RunnerManifest:
    """Return the governed runner manifest for the canonical quality loop."""
    job_manifest = nightly_quality_job_manifest(repository_root, output_directory)
    capability_manifest = CapabilityManifest(
        manifest_id="runner-manifest:nightly-quality-triage:v1",
        job_id=job_manifest.job_id,
        allowed_capabilities=job_manifest.allowed_capabilities,
        authority_ceiling=JobAuthorityCeiling.REPORT_ONLY,
        side_effect_allowlist=(
            JobSideEffect.READ_REPOSITORY,
            JobSideEffect.WRITE_RUNTIME_ARTIFACTS,
            JobSideEffect.APPEND_AUDIT_EVIDENCE,
            JobSideEffect.RUN_FIXED_QUALITY_COMMANDS,
        ),
        allowed_roots=job_manifest.allowed_roots,
        fixed_command_refs=(
            "powershell.exe -NoProfile -ExecutionPolicy Bypass "
            "-File .\\scripts\\quality.ps1",
        ),
    )
    return RunnerManifest(
        runner_id="runner:nightly-quality-triage",
        job_manifest=job_manifest,
        capability_manifest=capability_manifest,
        evidence_root=output_directory,
        audit_root=repository_root / "runtime" / "logs",
    )


def local_advisory_fixture_job_manifest(
    repository_root: Path,
    output_directory: Path,
) -> JobManifest:
    """Return the least-privilege manifest for manually admitted local fixtures."""
    if not repository_root.is_absolute() or not output_directory.is_absolute():
        raise ValueError("local advisory fixture paths must be absolute")
    return JobManifest(
        job_id="local-advisory-fixture-evaluation",
        allowed_capabilities=(
            JobCapability.READ_REPOSITORY,
            JobCapability.WRITE_ARTIFACT,
            JobCapability.RUN_LOCAL_ADVISORY_FIXTURES,
        ),
        allowed_roots=(repository_root, output_directory),
        timeout_seconds=300,
        maximum_output_bytes=1_000_000,
        maximum_concurrency=1,
        lock_path=output_directory / ".local-advisory-fixture.lock",
    )


def local_advisory_fixture_runner_manifest(
    repository_root: Path,
    output_directory: Path,
) -> RunnerManifest:
    """Return the research-only admission manifest for local fixture batches."""
    job_manifest = local_advisory_fixture_job_manifest(
        repository_root,
        output_directory,
    )
    capability_manifest = CapabilityManifest(
        manifest_id="runner-manifest:local-advisory-fixture-evaluation:v1",
        job_id=job_manifest.job_id,
        allowed_capabilities=job_manifest.allowed_capabilities,
        authority_ceiling=JobAuthorityCeiling.RESEARCH_ONLY,
        side_effect_allowlist=(
            JobSideEffect.READ_REPOSITORY,
            JobSideEffect.WRITE_RUNTIME_ARTIFACTS,
            JobSideEffect.APPEND_AUDIT_EVIDENCE,
            JobSideEffect.RUN_LOCAL_ADVISORY_FIXTURES,
        ),
        allowed_roots=job_manifest.allowed_roots,
        fixed_command_refs=(
            "ai4binance.local_agent.advisory_harness.LocalAdvisoryFixtureHarness.run",
        ),
    )
    return RunnerManifest(
        runner_id="runner:local-advisory-fixture-evaluation",
        job_manifest=job_manifest,
        capability_manifest=capability_manifest,
        evidence_root=output_directory,
        audit_root=repository_root / "runtime" / "logs",
    )


def _required_side_effects_for_capabilities(
    capabilities: tuple[JobCapability, ...],
) -> set[JobSideEffect]:
    mapping = {
        JobCapability.READ_REPOSITORY: JobSideEffect.READ_REPOSITORY,
        JobCapability.WRITE_ARTIFACT: JobSideEffect.WRITE_RUNTIME_ARTIFACTS,
        JobCapability.RUN_FIXED_QUALITY_COMMANDS: (
            JobSideEffect.RUN_FIXED_QUALITY_COMMANDS
        ),
        JobCapability.RUN_LOCAL_ADVISORY_FIXTURES: (
            JobSideEffect.RUN_LOCAL_ADVISORY_FIXTURES
        ),
    }
    return {mapping[capability] for capability in capabilities}

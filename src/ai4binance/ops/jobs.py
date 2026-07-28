"""Admission gate for capability-bounded unattended jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class JobCapability(StrEnum):
    READ_REPOSITORY = "READ_REPOSITORY"
    WRITE_ARTIFACT = "WRITE_ARTIFACT"
    RUN_FIXED_QUALITY_COMMANDS = "RUN_FIXED_QUALITY_COMMANDS"


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
class JobRequest:
    job_id: str
    idempotency_key: str
    requested_capabilities: tuple[JobCapability, ...]
    target_paths: tuple[Path, ...]
    timeout_enforced_by_runner: bool
    lock_acquired: bool
    network_requested: bool = False

    def __post_init__(self) -> None:
        if not self.job_id.strip() or not self.idempotency_key.strip():
            raise ValueError("job request identity is required")
        if not self.requested_capabilities:
            raise ValueError("job request capabilities cannot be empty")
        if any(not path.is_absolute() for path in self.target_paths):
            raise ValueError("job request paths must be absolute")


@dataclass(frozen=True, slots=True)
class JobAdmission:
    job_id: str
    idempotency_key: str
    admitted: bool
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.admitted == bool(self.blockers):
            raise ValueError("job admission and blockers disagree")
        if self.execution_allowed:
            raise ValueError("job admission cannot authorize trading")


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

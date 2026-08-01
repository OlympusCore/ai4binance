"""Optional security-scanner adapter contract with evidence-first artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

_SECURITY_SCANNER_FAILURES = (RuntimeError, OSError, TimeoutError, ValueError)


class SecurityScanStatus(StrEnum):
    """Security scan lifecycle without automatic remediation authority."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class SecuritySeverity(StrEnum):
    """Bounded finding severities suitable for SARIF-compatible adapters."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class SecurityScanRequest:
    """Explicit scan scope; external targets are not accepted."""

    scan_id: str
    repository_root: Path
    created_at: datetime
    commit_sha: str | None = None
    diff_base: str | None = None

    def __post_init__(self) -> None:
        if not self.scan_id.strip() or not self.repository_root.is_absolute():
            raise ValueError("security scan requires identity and absolute local scope")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("security scan timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    """Validated scanner finding with evidence and remediation guidance."""

    finding_id: str
    title: str
    severity: SecuritySeverity
    evidence: str
    remediation: str
    file_path: str | None = None
    cwe: str | None = None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.finding_id, self.title, self.evidence, self.remediation)
        ):
            raise ValueError("security finding requires evidence and remediation")
        if self.file_path is not None and Path(self.file_path).is_absolute():
            raise ValueError("security finding file path must be repository-relative")


@dataclass(frozen=True, slots=True)
class SecurityScanArtifact:
    """Human-reviewed scan output; never auto-applies a patch."""

    scan_id: str
    scanner_name: str | None
    status: SecurityScanStatus
    findings: tuple[SecurityFinding, ...]
    blockers: tuple[str, ...]
    sarif_path: Path | None = None
    auto_fix_allowed: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.scan_id.strip():
            raise ValueError("security artifact requires identity")
        if self.status is SecurityScanStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked security scan requires blockers")
        if self.status is SecurityScanStatus.COMPLETED and self.blockers:
            raise ValueError("completed security scan cannot contain blockers")
        if self.auto_fix_allowed or self.execution_allowed:
            raise ValueError("security scan cannot auto-fix or execute trading actions")


class SecurityScanner(Protocol):
    """Adapter implemented by a pinned, separately authorized scanner."""

    @property
    def name(self) -> str:
        """Return scanner identity and version."""

    def scan(self, request: SecurityScanRequest) -> SecurityScanArtifact:
        """Scan only the request's local repository scope."""


@dataclass(frozen=True, slots=True)
class SecurityScanService:
    """Fail closed when an external scanner has not been configured."""

    scanner: SecurityScanner | None = None

    def run(self, request: SecurityScanRequest) -> SecurityScanArtifact:
        if self.scanner is None:
            return SecurityScanArtifact(
                scan_id=request.scan_id,
                scanner_name=None,
                status=SecurityScanStatus.BLOCKED,
                findings=(),
                blockers=("SECURITY_SCANNER_NOT_CONFIGURED",),
            )
        try:
            artifact = self.scanner.scan(request)
        except _SECURITY_SCANNER_FAILURES:
            return SecurityScanArtifact(
                scan_id=request.scan_id,
                scanner_name=self.scanner.name,
                status=SecurityScanStatus.BLOCKED,
                findings=(),
                blockers=("SECURITY_SCANNER_FAILED",),
            )
        if artifact.scan_id != request.scan_id:
            return SecurityScanArtifact(
                scan_id=request.scan_id,
                scanner_name=self.scanner.name,
                status=SecurityScanStatus.BLOCKED,
                findings=(),
                blockers=("SECURITY_SCAN_IDENTITY_MISMATCH",),
            )
        return artifact

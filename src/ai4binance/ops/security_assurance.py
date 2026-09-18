"""Report-only EAACIE security assurance evidence and weekly deep audit."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import cast

from ai4binance.ops.continuous_assurance import (
    EAACIE_INSTRUCTION_REFS,
    CentralAuditTriggerEngine,
    ContinuousAssurancePlan,
    SecurityAuditTriggerType,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import write_json_object_verified

__all__ = [
    "SbomComponent",
    "SecurityAssuranceResult",
    "SecurityAssuranceStatus",
    "SecurityControlCheck",
    "VulnerabilityRecord",
    "metadata",
    "run_security_weekly_deep_audit",
]


class SecurityAssuranceStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class SbomComponent:
    name: str
    version: str
    purl: str


@dataclass(frozen=True, slots=True)
class VulnerabilityRecord:
    package_name: str
    installed_version: str
    cve_id: str
    cvss_score: float
    severity: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class SecurityControlCheck:
    control_id: str
    status: str
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SecurityAssuranceResult:
    status: SecurityAssuranceStatus
    observed_at: datetime
    sbom_components: tuple[SbomComponent, ...]
    sbom_sha256: str
    vulnerability_records: tuple[VulnerabilityRecord, ...]
    control_checks: tuple[SecurityControlCheck, ...]
    continuous_assurance_plan: ContinuousAssurancePlan
    json_path: Path
    latest_json_path: Path
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def to_payload(self) -> dict[str, object]:
        return {
            "command": "security-weekly-deep-audit",
            "status": self.status.value,
            "observed_at": self.observed_at.isoformat(),
            "instruction_refs": list(EAACIE_INSTRUCTION_REFS),
            "sbom": {
                "format": "AI4BINANCE-SBOM-LITE-1.0",
                "component_count": len(self.sbom_components),
                "sha256": self.sbom_sha256,
                "components": to_primitive(self.sbom_components),
            },
            "dependency_scan": {
                "scanner": "AI4BINANCE-CVE-EVIDENCE-LITE-1.0",
                "vulnerability_count": len(self.vulnerability_records),
                "vulnerabilities": to_primitive(self.vulnerability_records),
            },
            "control_checks": to_primitive(self.control_checks),
            "scheduler_integration": {
                "cadence": "weekly",
                "trigger_type": SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP.value,
                "cli_command": (
                    ".venv\\scripts\\python.exe -m ai4binance.cli "
                    "security-weekly-deep-audit --security-evidence-file "
                    "runtime\\artifacts\\assurance\\security\\security-evidence.json"
                ),
                "creates_os_task": False,
                "manual_registration_required": True,
            },
            "continuous_assurance": self.continuous_assurance_plan.to_payload(),
            "json_path": str(self.json_path),
            "latest_json_path": str(self.latest_json_path),
            "blockers": list(self.blockers),
            "execution_allowed": self.execution_allowed,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def run_security_weekly_deep_audit(
    *,
    repository_root: Path | None = None,
    evidence_file: Path | None = None,
    observed_at: datetime | None = None,
) -> SecurityAssuranceResult:
    """Produce SBOM and verify weekly deep-audit evidence without remediation."""

    root = repository_root or Path.cwd()
    observed = observed_at or datetime.now(UTC)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("security assurance timestamp must be timezone-aware")

    evidence = _load_evidence(evidence_file)
    components = _installed_components()
    sbom_sha256 = _sbom_sha256(components)
    vulnerabilities = _vulnerability_records(evidence)
    checks = (
        _dependency_check(evidence, vulnerabilities),
        _mfa_provider_check(evidence),
        _backup_restore_check(evidence),
        _worm_storage_check(evidence),
        _weekly_scheduler_check(),
    )
    blockers = tuple(blocker for check in checks for blocker in check.blockers)
    security_event = CentralAuditTriggerEngine().security_event(
        SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP,
        observed_at=observed,
        evidence_refs=(
            "security-assurance:weekly-deep",
            f"sbom-sha256:{sbom_sha256}",
        ),
    )
    plan = CentralAuditTriggerEngine().build_security_plan((security_event,))
    status = (
        SecurityAssuranceStatus.READY
        if not blockers
        else SecurityAssuranceStatus.BLOCKED
    )
    stamp = observed.strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = root / "runtime" / "artifacts" / "security"
    result = SecurityAssuranceResult(
        status=status,
        observed_at=observed,
        sbom_components=components,
        sbom_sha256=sbom_sha256,
        vulnerability_records=vulnerabilities,
        control_checks=checks,
        continuous_assurance_plan=plan,
        json_path=artifact_dir / f"security-weekly-deep-{stamp}.json",
        latest_json_path=artifact_dir / "security-weekly-deep-latest.json",
        blockers=blockers,
    )
    payload = result.to_payload()
    write_json_object_verified(
        result.json_path,
        payload,
        blocker="SECURITY_ASSURANCE_DESTINATION_VERIFY_FAILED",
        subject_id=f"security-weekly-deep:{stamp}",
        indent=2,
    )
    write_json_object_verified(
        result.latest_json_path,
        payload,
        blocker="SECURITY_ASSURANCE_DESTINATION_VERIFY_FAILED",
        subject_id="security-weekly-deep:latest",
        indent=2,
    )
    return result


def _installed_components() -> tuple[SbomComponent, ...]:
    components = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name", "").strip()
        version = distribution.metadata.get("Version", "").strip()
        if not name or not version:
            continue
        normalized = name.lower().replace("_", "-")
        components.append(
            SbomComponent(
                name=name,
                version=version,
                purl=f"pkg:pypi/{normalized}@{version}",
            )
        )
    return tuple(sorted(components, key=lambda item: item.purl))


def _load_evidence(evidence_file: Path | None) -> Mapping[str, object]:
    if evidence_file is None:
        return {}
    try:
        payload = json.loads(evidence_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("security evidence file is invalid") from error
    if not isinstance(payload, Mapping):
        raise ValueError("security evidence file must contain a JSON object")
    _reject_secret_like_evidence(payload)
    return cast(Mapping[str, object], payload)


def _dependency_check(
    evidence: Mapping[str, object],
    vulnerabilities: tuple[VulnerabilityRecord, ...],
) -> SecurityControlCheck:
    if "vulnerabilities" not in evidence:
        return _blocked(
            "DEPENDENCY_CVE_SCAN",
            "CVE_ADVISORY_SOURCE_MISSING",
        )
    if vulnerabilities:
        return SecurityControlCheck(
            "DEPENDENCY_CVE_SCAN",
            "REVIEW_REQUIRED",
            ("CVE_FINDINGS_REQUIRE_REVIEW",),
            tuple(record.evidence_ref for record in vulnerabilities),
        )
    return SecurityControlCheck(
        "DEPENDENCY_CVE_SCAN",
        "PASSED_BY_PROVIDED_ADVISORY",
        (),
        ("evidence:vulnerabilities",),
    )


def _mfa_provider_check(evidence: Mapping[str, object]) -> SecurityControlCheck:
    provider = evidence.get("mfa_provider")
    if not isinstance(provider, Mapping):
        return _blocked("MFA_PROVIDER", "MFA_PROVIDER_ATTESTATION_MISSING")
    refs = _evidence_refs(provider)
    if (
        str(provider.get("provider", "")).strip()
        and provider.get("mfa_enforced") is True
        and provider.get("rbac_reviewed") is True
        and provider.get("least_privilege_reviewed") is True
        and refs
    ):
        return SecurityControlCheck("MFA_PROVIDER", "PASSED", (), refs)
    return _blocked("MFA_PROVIDER", "MFA_PROVIDER_ATTESTATION_INCOMPLETE")


def _backup_restore_check(evidence: Mapping[str, object]) -> SecurityControlCheck:
    proof = evidence.get("backup_restore")
    if not isinstance(proof, Mapping):
        return _blocked("BACKUP_RESTORE_TEST", "RESTORE_TEST_EVIDENCE_MISSING")
    refs = _evidence_refs(proof)
    if (
        str(proof.get("backup_ref", "")).strip()
        and str(proof.get("restore_report_ref", "")).strip()
        and proof.get("restore_test_passed") is True
        and refs
    ):
        return SecurityControlCheck("BACKUP_RESTORE_TEST", "PASSED", (), refs)
    return _blocked("BACKUP_RESTORE_TEST", "RESTORE_TEST_EVIDENCE_INCOMPLETE")


def _worm_storage_check(evidence: Mapping[str, object]) -> SecurityControlCheck:
    proof = evidence.get("worm_storage")
    if not isinstance(proof, Mapping):
        return _blocked("EXTERNAL_WORM_STORAGE", "WORM_STORAGE_EVIDENCE_MISSING")
    refs = _evidence_refs(proof)
    retention = proof.get("immutable_retention_days")
    if (
        str(proof.get("provider", "")).strip()
        and proof.get("external_storage") is True
        and proof.get("append_only") is True
        and isinstance(retention, int)
        and retention > 0
        and refs
    ):
        return SecurityControlCheck("EXTERNAL_WORM_STORAGE", "PASSED", (), refs)
    return _blocked("EXTERNAL_WORM_STORAGE", "WORM_STORAGE_EVIDENCE_INCOMPLETE")


def _weekly_scheduler_check() -> SecurityControlCheck:
    return SecurityControlCheck(
        "WEEKLY_DEEP_AUDIT_CLI",
        "CLI_READY",
        (),
        ("cli:security-weekly-deep-audit",),
    )


def _vulnerability_records(
    evidence: Mapping[str, object],
) -> tuple[VulnerabilityRecord, ...]:
    raw_records = evidence.get("vulnerabilities", ())
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, str):
        raise ValueError("vulnerabilities evidence must be a list")
    records: list[VulnerabilityRecord] = []
    for item in raw_records:
        if not isinstance(item, Mapping):
            raise ValueError("vulnerability record must be an object")
        cve_id = str(item.get("cve_id", "")).strip().upper()
        score = item.get("cvss_score")
        if not cve_id.startswith("CVE-") or not isinstance(score, int | float):
            raise ValueError("vulnerability record requires CVE id and CVSS score")
        if score < 0 or score > 10:
            raise ValueError("CVSS score must be between 0 and 10")
        records.append(
            VulnerabilityRecord(
                package_name=str(item.get("package_name", "")).strip(),
                installed_version=str(item.get("installed_version", "")).strip(),
                cve_id=cve_id,
                cvss_score=float(score),
                severity=str(item.get("severity", "UNKNOWN")).strip().upper(),
                evidence_ref=str(item.get("evidence_ref", cve_id)).strip(),
            )
        )
    return tuple(records)


def _evidence_refs(payload: Mapping[str, object]) -> tuple[str, ...]:
    refs = payload.get("evidence_refs", ())
    if not isinstance(refs, Sequence) or isinstance(refs, str):
        return ()
    result = tuple(str(item).strip() for item in refs if str(item).strip())
    return tuple(dict.fromkeys(result))


def _blocked(control_id: str, blocker: str) -> SecurityControlCheck:
    return SecurityControlCheck(control_id, "BLOCKED", (blocker,), ())


def _sbom_sha256(components: tuple[SbomComponent, ...]) -> str:
    payload = json.dumps(
        to_primitive(components),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _reject_secret_like_evidence(payload: Mapping[str, object]) -> None:
    forbidden = ("api_key", "password", "private_key", "secret", "seed", "token")

    def walk(value: object) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lowered = str(key).lower()
                if any(term in lowered for term in forbidden):
                    raise ValueError("security evidence must not contain secrets")
                walk(item)
        elif isinstance(value, Sequence) and not isinstance(value, str):
            for item in value:
                walk(item)

    walk(payload)

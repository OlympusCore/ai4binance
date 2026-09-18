from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.cli import main
from ai4binance.ops import security_assurance as security_assurance_module
from ai4binance.ops.continuous_assurance import SecurityAuditTriggerType
from ai4binance.ops.security_assurance import (
    SecurityAssuranceStatus,
    run_security_weekly_deep_audit,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def test_weekly_deep_security_audit_blocks_missing_external_evidence(
    tmp_path: Path,
) -> None:
    result = run_security_weekly_deep_audit(
        repository_root=tmp_path,
        observed_at=NOW,
    )
    payload = result.to_payload()
    continuous = cast(Mapping[str, object], payload["continuous_assurance"])
    security_audit = cast(Mapping[str, object], continuous["security_audit"])
    sbom = cast(Mapping[str, object], payload["sbom"])
    scheduler = cast(Mapping[str, object], payload["scheduler_integration"])

    assert result.status is SecurityAssuranceStatus.BLOCKED
    assert result.json_path.exists()
    assert result.latest_json_path.exists()
    assert "CVE_ADVISORY_SOURCE_MISSING" in result.blockers
    assert "MFA_PROVIDER_ATTESTATION_MISSING" in result.blockers
    assert "RESTORE_TEST_EVIDENCE_MISSING" in result.blockers
    assert "WORM_STORAGE_EVIDENCE_MISSING" in result.blockers
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    component_count = sbom["component_count"]
    assert isinstance(component_count, int)
    assert component_count > 0
    assert len(str(sbom["sha256"])) == 64
    assert security_audit["trigger_types"] == [
        SecurityAuditTriggerType.SCHEDULED_WEEKLY_DEEP.value
    ]
    assert scheduler["creates_os_task"] is False
    assert scheduler["manual_registration_required"] is True


def test_weekly_deep_security_audit_accepts_complete_attestation_bundle(
    tmp_path: Path,
) -> None:
    evidence_file = _write_evidence(tmp_path, vulnerabilities=[])

    result = run_security_weekly_deep_audit(
        repository_root=tmp_path,
        evidence_file=evidence_file,
        observed_at=NOW,
    )

    assert result.status is SecurityAssuranceStatus.READY
    assert result.blockers == ()
    assert {check.control_id: check.status for check in result.control_checks} == {
        "DEPENDENCY_CVE_SCAN": "PASSED_BY_PROVIDED_ADVISORY",
        "MFA_PROVIDER": "PASSED",
        "BACKUP_RESTORE_TEST": "PASSED",
        "EXTERNAL_WORM_STORAGE": "PASSED",
        "WEEKLY_DEEP_AUDIT_CLI": "CLI_READY",
    }


def test_weekly_deep_security_audit_routes_cve_findings_to_review(
    tmp_path: Path,
) -> None:
    evidence_file = _write_evidence(
        tmp_path,
        vulnerabilities=[
            {
                "package_name": "demo",
                "installed_version": "1.0",
                "cve_id": "CVE-2026-0001",
                "cvss_score": 7.5,
                "severity": "high",
                "evidence_ref": "advisory:CVE-2026-0001",
            }
        ],
    )

    result = run_security_weekly_deep_audit(
        repository_root=tmp_path,
        evidence_file=evidence_file,
        observed_at=NOW,
    )

    assert result.status is SecurityAssuranceStatus.BLOCKED
    assert result.blockers == ("CVE_FINDINGS_REQUIRE_REVIEW",)
    assert result.vulnerability_records[0].cve_id == "CVE-2026-0001"


def test_weekly_deep_security_audit_rejects_secret_like_evidence(
    tmp_path: Path,
) -> None:
    evidence_file = tmp_path / "bad-security-evidence.json"
    evidence_file.write_text(
        json.dumps({"mfa_provider": {"api_key": "do-not-store"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not contain secrets"):
        run_security_weekly_deep_audit(
            repository_root=tmp_path,
            evidence_file=evidence_file,
            observed_at=NOW,
        )


def test_installed_components_skip_distributions_without_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDistribution:
        def __init__(self, name: str, version: str | None) -> None:
            self.metadata = {"Name": name}
            if version is not None:
                self.metadata["Version"] = version

        @property
        def version(self) -> str:
            raise AssertionError("distribution.version must not be accessed")

    monkeypatch.setattr(
        security_assurance_module.metadata,
        "distributions",
        lambda: (
            FakeDistribution("missing-version", None),
            FakeDistribution("present-version", "1.2.3"),
        ),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        components = security_assurance_module._installed_components()

    assert caught == []
    assert components == (
        security_assurance_module.SbomComponent(
            name="present-version",
            version="1.2.3",
            purl="pkg:pypi/present-version@1.2.3",
        ),
    )


def test_security_weekly_deep_audit_cli_is_report_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    evidence_file = _write_evidence(tmp_path, vulnerabilities=[])

    assert (
        main(
            [
                "security-deep-audit",
                "--security-evidence-file",
                str(evidence_file),
                "--format",
                "json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "security-weekly-deep-audit"
    assert payload["status"] == "READY"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def _write_evidence(
    tmp_path: Path,
    *,
    vulnerabilities: list[dict[str, Any]],
) -> Path:
    evidence_file = tmp_path / "security-evidence.json"
    evidence_file.write_text(
        json.dumps(
            {
                "vulnerabilities": vulnerabilities,
                "mfa_provider": {
                    "provider": "example-idp",
                    "mfa_enforced": True,
                    "rbac_reviewed": True,
                    "least_privilege_reviewed": True,
                    "evidence_refs": ["attestation:mfa:2026-08-09"],
                },
                "backup_restore": {
                    "backup_ref": "backup:state:2026-08-09",
                    "restore_report_ref": "restore-test:2026-08-09",
                    "restore_test_passed": True,
                    "evidence_refs": ["restore:report:2026-08-09"],
                },
                "worm_storage": {
                    "provider": "external-immutable-store",
                    "external_storage": True,
                    "append_only": True,
                    "immutable_retention_days": 30,
                    "evidence_refs": ["worm:attestation:2026-08-09"],
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return evidence_file

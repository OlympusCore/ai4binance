from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.enterprise.contracts import OpinionVerdict, WorkflowIdentity
from ai4binance.enterprise.quality_audit import (
    QualitySystemAuditCheck,
    QualitySystemAuditEvidence,
    QualitySystemAuditStatus,
    run_quality_system_audit,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def docs_root(tmp_path: Path, text: str | None = None) -> Path:
    (tmp_path / "Computer.md").write_text(
        "\n".join(
            (
                "# Local Computer Profile",
                "Device: LOCAL-DEVICE-ALPHA",
                "GPU: PRIVATEGPU123",
            )
        ),
        encoding="utf-8",
    )
    docs = tmp_path / "Docs"
    docs.mkdir()
    if text is not None:
        (docs / "HOLDING_GOVERNANCE.md").write_text(text, encoding="utf-8")
    return tmp_path


def required_doc_text() -> str:
    return "\n".join(
        (
            "GeneralManagerController",
            "EnterpriseAuditJournal",
            "COMPUTER_MD_PRIVACY_BOUNDARY",
            "Computer.md",
            "PROMPT_ACCESS_BLOCKED",
            "WRITTEN_APPROVAL_DOC_SYNC",
            "LIVE_ORDER_BLOCKED",
        )
    )


def evidence(tmp_path: Path, commands: tuple[str, ...]) -> QualitySystemAuditEvidence:
    return QualitySystemAuditEvidence(
        workspace_root=tmp_path,
        command_names=commands,
        observed_at=NOW,
    )


def test_quality_department_system_audit_passes_core_controls(tmp_path: Path) -> None:
    root = docs_root(tmp_path, required_doc_text())
    report = run_quality_system_audit(
        evidence(
            root,
            ("enterprise-intake", "skills-audit", "quality-system-audit"),
        )
    )

    assert report.status is QualitySystemAuditStatus.PASSED
    assert report.blockers == ()
    assert report.corrective_actions == ()
    assert report.manager_id == "QualityDepartmentManager"
    assert {check.check_id for check in report.checks} == {
        "QUALITY_DEPARTMENT_INDEPENDENCE",
        "COMPUTER_MD_PRIVACY_BOUNDARY",
        "GENERAL_MANAGER_PROMPT_INTAKE",
        "INTERDEPARTMENTAL_PROMPT_LEAK_BLOCK",
        "ENTERPRISE_AUDIT_JOURNAL_EVENTS",
        "AGENTIC_GOVERNANCE_SURFACES",
        "CLI_GOVERNANCE_COMMANDS",
        "HOLDING_GOVERNANCE_DOCUMENTED",
    }
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_quality_system_audit_surfaces_missing_docs_and_commands(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path)
    report = run_quality_system_audit(evidence(root, ("enterprise-intake",)))

    assert report.status is QualitySystemAuditStatus.REVISION_REQUIRED
    assert "HOLDING_GOVERNANCE_DOC_MISSING" in report.blockers
    assert "CLI_COMMAND_MISSING:quality-system-audit" in report.blockers
    assert "CLI_COMMAND_MISSING:skills-audit" in report.blockers
    assert "Create Docs/HOLDING_GOVERNANCE.md." in report.corrective_actions


def test_quality_system_audit_blocks_computer_profile_leak(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text())
    (root / "Docs" / "leak.md").write_text(
        "Do not copy LOCAL-DEVICE-ALPHA into docs.",
        encoding="utf-8",
    )

    report = run_quality_system_audit(
        evidence(
            root,
            ("enterprise-intake", "skills-audit", "quality-system-audit"),
        )
    )

    assert report.status is QualitySystemAuditStatus.REVISION_REQUIRED
    assert "PERSONAL_INFO_OUTSIDE_COMPUTER_MD" in report.blockers
    privacy_check = next(
        check
        for check in report.checks
        if check.check_id == "COMPUTER_MD_PRIVACY_BOUNDARY"
    )
    assert privacy_check.passed is False
    assert privacy_check.subject_ref == "privacy:Computer.md"
    assert privacy_check.evidence_refs == (
        "profile-ref:Computer.md",
        "scanned-file-count:2",
        "finding-count:1",
    )
    assert all("LOCAL-DEVICE-ALPHA" not in ref for ref in privacy_check.evidence_refs)


def test_quality_system_audit_builds_fail_closed_quality_opinion(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text())
    report = run_quality_system_audit(
        evidence(
            root,
            ("enterprise-intake", "skills-audit", "quality-system-audit"),
        )
    )

    opinion = report.to_quality_opinion(identity())

    assert opinion.verdict is OpinionVerdict.ACCEPTED
    assert opinion.evidence_refs == tuple(check.check_id for check in report.checks)
    assert opinion.execution_allowed is False
    assert opinion.promotion_status == "RESEARCH_ONLY"
    assert opinion.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_quality_system_audit_rejects_inconsistent_check_shape() -> None:
    with pytest.raises(ValueError, match="status and blockers"):
        QualitySystemAuditCheck(
            "CHECK",
            "subject",
            True,
            ("evidence",),
            blockers=("SHOULD_NOT_EXIST",),
        )

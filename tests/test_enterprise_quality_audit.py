from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.enterprise.agent_stack import modern_agent_stack_requirements
from ai4binance.enterprise.contracts import OpinionVerdict, WorkflowIdentity
from ai4binance.enterprise.oek_compliance import (
    OekChangeKind,
    OekChangeManifest,
    OekComplianceReport,
    OekComplianceStatus,
    OekGapAnalysisReport,
    analyze_oek_change_gap,
    audit_oek_constitution,
    build_oek_change_manifest,
    required_controls_for_change_kind,
)
from ai4binance.enterprise.quality_audit import (
    QualitySystemAuditCheck,
    QualitySystemAuditEvidence,
    QualitySystemAuditStatus,
    run_quality_system_audit,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity("wo-1", "run-1", "trace-1", NOW)


def docs_root(
    tmp_path: Path,
    text: str | None = None,
    *,
    oek_text: str | None = None,
) -> Path:
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
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "quality.ps1").write_text(
        "\n".join(
            (
                "$payload = @{",
                '    status = "QUALITY_GATE_GREEN"',
                '    live_eligibility_status = "LIVE_ORDER_BLOCKED"',
                "}",
                'Set-Content -LiteralPath "Artifacts\\quality-gate\\latest.json"',
            )
        ),
        encoding="utf-8",
    )
    docs = tmp_path / "Docs"
    docs.mkdir()
    if text is not None:
        (docs / "HOLDING_GOVERNANCE.md").write_text(text, encoding="utf-8")
    if oek_text is not None:
        (docs / "AI4Binance_OEK.md").write_text(oek_text, encoding="utf-8")
    for requirement in modern_agent_stack_requirements():
        for relative_path in requirement.required_paths:
            if relative_path == "Docs/AI4Binance_OEK.md" and oek_text is None:
                continue
            path = tmp_path / relative_path
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("RESEARCH_ONLY\nLIVE_ORDER_BLOCKED\n", encoding="utf-8")
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


def required_oek_text() -> str:
    return "\n".join(
        (
            "---",
            'canonical_file: "AI4Binance_OEK.md"',
            'document_code: "AI4B-OEK-003"',
            'version: "3.0"',
            "frontmatter-note-without-colon",
            "---",
            "AI4BINANCE-OEK-CANONICAL-CONSTITUTION",
            "KANONİK ANAYASA DOSYASI",
            "OEK production yetkisi oluşturmaz.",
            "Normlar Hiyerarşisi",
            "DEĞİŞTİRİLEMEZ ÇEKİRDEK İLKELER",
            "Sermaye Koruma",
            "İnsan Üst Gözetimi",
            "Fail-Closed",
            "Kontrollü Öğrenme",
            "NO_TRADE",
            "RESEARCH_ONLY",
            "LIVE_ORDER_BLOCKED",
            "agent, workflow, config, model, strategy",
            "gap analizi",
            "risk, privacy/security",
            "test",
        )
    )


def evidence(tmp_path: Path, commands: tuple[str, ...]) -> QualitySystemAuditEvidence:
    return QualitySystemAuditEvidence(
        workspace_root=tmp_path,
        command_names=commands,
        observed_at=NOW,
    )


def required_command_names() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "agent-stack-audit",
                "enterprise-intake",
                "oek-gap-analysis",
                "quality-system-audit",
                "skills-audit",
                *(
                    command
                    for requirement in modern_agent_stack_requirements()
                    for command in requirement.required_commands
                ),
            }
        )
    )


def test_quality_department_system_audit_passes_core_controls(tmp_path: Path) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())
    report = run_quality_system_audit(evidence(root, required_command_names()))

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
        "QUALITY_GATE_GREEN",
        "HOLDING_GOVERNANCE_DOCUMENTED",
        "OEK_CONSTITUTION_COMPLIANCE",
        "MODERN_AGENT_STACK_GOVERNED",
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
    assert "OEK_CONSTITUTION_DOC_MISSING" in report.blockers
    assert "CLI_COMMAND_MISSING:agent-stack-audit" in report.blockers
    assert "CLI_COMMAND_MISSING:oek-gap-analysis" in report.blockers
    assert "CLI_COMMAND_MISSING:quality-system-audit" in report.blockers
    assert "CLI_COMMAND_MISSING:skills-audit" in report.blockers
    assert "Create Docs/HOLDING_GOVERNANCE.md." in report.corrective_actions


def test_quality_system_audit_blocks_computer_profile_leak(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())
    (root / "Docs" / "leak.md").write_text(
        "Do not copy LOCAL-DEVICE-ALPHA into docs.",
        encoding="utf-8",
    )

    report = run_quality_system_audit(
        evidence(
            root,
            required_command_names(),
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
    assert privacy_check.evidence_refs[0] == "profile-ref:Computer.md"
    assert privacy_check.evidence_refs[-1] == "finding-count:1"
    assert any(
        ref.startswith("scanned-file-count:") for ref in privacy_check.evidence_refs
    )
    assert all("LOCAL-DEVICE-ALPHA" not in ref for ref in privacy_check.evidence_refs)


def test_quality_system_audit_builds_fail_closed_quality_opinion(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())
    report = run_quality_system_audit(evidence(root, required_command_names()))

    opinion = report.to_quality_opinion(identity())

    assert opinion.verdict is OpinionVerdict.ACCEPTED
    assert opinion.evidence_refs == tuple(check.check_id for check in report.checks)
    assert opinion.execution_allowed is False
    assert opinion.promotion_status == "RESEARCH_ONLY"
    assert opinion.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_oek_constitution_compliance_reports_version_and_boundaries(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())

    report = audit_oek_constitution(root)

    assert report.status is OekComplianceStatus.PASSED
    assert report.version == "3.0"
    assert report.document_code == "AI4B-OEK-003"
    assert report.blockers == ()
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_oek_constitution_compliance_blocks_missing_live_boundary(
    tmp_path: Path,
) -> None:
    weakened_oek = required_oek_text().replace("LIVE_ORDER_BLOCKED", "")
    root = docs_root(tmp_path, required_doc_text(), oek_text=weakened_oek)

    report = audit_oek_constitution(root)

    assert report.status is OekComplianceStatus.REVISION_REQUIRED
    assert "OEK_LIVE_BOUNDARY_TERM_MISSING:LIVE_ORDER_BLOCKED" in report.blockers
    assert report.execution_allowed is False


def test_oek_constitution_compliance_blocks_missing_gap_analysis_term(
    tmp_path: Path,
) -> None:
    weakened_oek = required_oek_text().replace("gap analizi", "")
    root = docs_root(tmp_path, required_doc_text(), oek_text=weakened_oek)

    report = audit_oek_constitution(root)

    assert report.status is OekComplianceStatus.REVISION_REQUIRED
    assert "OEK_GAP_ANALYSIS_TERM_MISSING:gap analizi" in report.blockers
    assert report.execution_allowed is False


def test_oek_gap_analysis_accepts_safe_agent_manifest(tmp_path: Path) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())
    manifest = OekChangeManifest(
        change_id="oek-change:agent:001",
        change_kind=OekChangeKind.AGENT,
        subject_ref="agent:new-research-agent",
        changed_paths=("src/ai4binance/agents/new_research.py",),
        summary="Add advisory-only research agent.",
        evidence_refs=("test:tests/test_new_research_agent.py",),
        declared_controls=(
            "OEK_CONSTITUTION_COMPLIANCE",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
            "AUDIT_TRAIL_REQUIRED",
            "AGENT_CHARTER_REQUIRED",
            "OWNER_REQUIRED",
            "TOOL_ALLOWLIST_REQUIRED",
            "KILL_CRITERIA_REQUIRED",
        ),
    )

    report = analyze_oek_change_gap(root, manifest)

    assert report.status is OekComplianceStatus.PASSED
    assert report.missing_controls == ()
    assert report.prohibited_authorities == ()
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_oek_change_manifest_builder_includes_required_controls_by_default(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())
    manifest = build_oek_change_manifest(
        change_id="oek-change:workflow:001",
        change_kind=OekChangeKind.WORKFLOW,
        subject_ref="workflow:quality-gate",
        changed_paths=("Scripts/quality.ps1",),
        summary="Make quality gate evidence explicit.",
        evidence_refs=("test:tests/test_enterprise_quality_audit.py",),
    )

    report = analyze_oek_change_gap(root, manifest)

    assert manifest.declared_controls == required_controls_for_change_kind(
        OekChangeKind.WORKFLOW
    )
    assert "WORKFLOW_OWNER_REQUIRED" in manifest.declared_controls
    assert report.status is OekComplianceStatus.PASSED
    assert report.blockers == ()


def test_oek_gap_analysis_blocks_missing_controls_and_live_authority(
    tmp_path: Path,
) -> None:
    root = docs_root(tmp_path, required_doc_text(), oek_text=required_oek_text())
    manifest = OekChangeManifest(
        change_id="oek-change:config:001",
        change_kind=OekChangeKind.CONFIG,
        subject_ref="config:live-mode",
        changed_paths=("pyproject.toml",),
        summary="Attempt to widen live config authority.",
        evidence_refs=("diff:pyproject.toml",),
        declared_controls=("OEK_CONSTITUTION_COMPLIANCE",),
        requested_authorities=("LIVE_ORDER_AUTHORITY",),
    )

    report = analyze_oek_change_gap(root, manifest)

    assert report.status is OekComplianceStatus.REVISION_REQUIRED
    assert "LIVE_ORDER_BLOCKED" in report.missing_controls
    assert "LIVE_ORDER_AUTHORITY" in report.prohibited_authorities
    assert "OEK_PROHIBITED_AUTHORITY_REQUESTED:LIVE_ORDER_AUTHORITY" in (
        report.blockers
    )
    assert report.execution_allowed is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"change_id": ""}, "change id"),
        ({"subject_ref": ""}, "change subject"),
        ({"summary": ""}, "change summary"),
        ({"changed_paths": ("",)}, "paths"),
        ({"changed_paths": ("a.py", "a.py")}, "paths"),
        ({"evidence_refs": ("",)}, "evidence refs"),
        ({"declared_controls": ("",)}, "controls"),
        ({"requested_authorities": ("LIVE_ORDER_AUTHORITY",) * 2}, "authorities"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "STAGED_CANDIDATE"}, "cannot promote"),
        ({"live_eligibility_status": "LIVE_ELIGIBLE"}, "must remain live blocked"),
    ],
)
def test_oek_change_manifest_rejects_shape_or_authority_drift(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "change_id": "oek-change:agent:001",
        "change_kind": OekChangeKind.AGENT,
        "subject_ref": "agent:safe",
        "changed_paths": ("src/ai4binance/agents/safe.py",),
        "summary": "Safe advisory agent change.",
        "evidence_refs": ("test:tests/test_safe.py",),
        "declared_controls": ("OEK_CONSTITUTION_COMPLIANCE",),
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        OekChangeManifest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"change_id": ""}, "change id"),
        ({"subject_ref": ""}, "subject"),
        ({"required_controls": ("",)}, "required controls"),
        ({"missing_controls": ("DUP", "DUP")}, "missing controls"),
        ({"prohibited_authorities": ("",)}, "prohibited authorities"),
        ({"evidence_refs": ("",)}, "evidence refs"),
        ({"blockers": ("SHOULD_NOT_EXIST",)}, "passed OEK gap"),
        (
            {"status": OekComplianceStatus.REVISION_REQUIRED},
            "revised OEK gap analysis",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "STAGED_CANDIDATE"}, "cannot promote"),
        ({"live_eligibility_status": "LIVE_ELIGIBLE"}, "must remain live blocked"),
    ],
)
def test_oek_gap_analysis_report_rejects_shape_or_authority_drift(
    kwargs: dict[str, object],
    message: str,
) -> None:
    document_report = OekComplianceReport(
        document_path="Docs/AI4Binance_OEK.md",
        status=OekComplianceStatus.PASSED,
        version="3.0",
        document_code="AI4B-OEK-003",
        evidence_refs=("doc:Docs/AI4Binance_OEK.md",),
        blockers=(),
        corrective_actions=(),
    )
    values: dict[str, object] = {
        "change_id": "oek-change:agent:001",
        "change_kind": OekChangeKind.AGENT,
        "subject_ref": "agent:safe",
        "document_report": document_report,
        "status": OekComplianceStatus.PASSED,
        "required_controls": ("OEK_CONSTITUTION_COMPLIANCE",),
        "missing_controls": (),
        "prohibited_authorities": (),
        "evidence_refs": ("change:oek-change:agent:001",),
        "blockers": (),
        "corrective_actions": (),
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        OekGapAnalysisReport(**values)  # type: ignore[arg-type]


def test_oek_constitution_compliance_blocks_invalid_frontmatter(
    tmp_path: Path,
) -> None:
    invalid_oek = required_oek_text().replace('version: "3.0"', 'version: "2.0"')
    root = docs_root(tmp_path, required_doc_text(), oek_text=invalid_oek)

    report = audit_oek_constitution(root)

    assert report.status is OekComplianceStatus.REVISION_REQUIRED
    assert "OEK_FRONTMATTER_INVALID:version" in report.blockers
    assert report.version == "2.0"
    assert "oek-version:2.0" in report.evidence_refs


def test_oek_constitution_compliance_blocks_missing_frontmatter(
    tmp_path: Path,
) -> None:
    no_frontmatter_oek = "\n".join(
        (
            "AI4BINANCE-OEK-CANONICAL-CONSTITUTION",
            "KANONİK ANAYASA DOSYASI",
            "Normlar Hiyerarşisi",
            "DEĞİŞTİRİLEMEZ ÇEKİRDEK İLKELER",
            "Sermaye Koruma",
            "İnsan Üst Gözetimi",
            "Fail-Closed",
            "Kontrollü Öğrenme",
            "NO_TRADE",
            "RESEARCH_ONLY",
            "LIVE_ORDER_BLOCKED",
            "production yetkisi oluşturmaz",
        )
    )
    root = docs_root(tmp_path, required_doc_text(), oek_text=no_frontmatter_oek)

    report = audit_oek_constitution(root)

    assert report.status is OekComplianceStatus.REVISION_REQUIRED
    assert "OEK_FRONTMATTER_INVALID:canonical_file" in report.blockers
    assert "OEK_FRONTMATTER_INVALID:document_code" in report.blockers
    assert "OEK_FRONTMATTER_INVALID:version" in report.blockers
    assert "oek-version:missing" in report.evidence_refs


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"document_path": ""}, "document path"),
        ({"blockers": ("UNEXPECTED",)}, "passed OEK"),
        (
            {"status": OekComplianceStatus.REVISION_REQUIRED},
            "revised OEK compliance",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "STAGED_CANDIDATE"}, "cannot promote"),
        ({"live_eligibility_status": "LIVE_ELIGIBLE"}, "must remain live blocked"),
    ],
)
def test_oek_compliance_report_rejects_authority_or_shape_drift(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "document_path": "Docs/AI4Binance_OEK.md",
        "status": OekComplianceStatus.PASSED,
        "version": "3.0",
        "document_code": "AI4B-OEK-003",
        "evidence_refs": ("doc:Docs/AI4Binance_OEK.md",),
        "blockers": (),
        "corrective_actions": (),
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        OekComplianceReport(**values)  # type: ignore[arg-type]


def test_quality_system_audit_rejects_inconsistent_check_shape() -> None:
    with pytest.raises(ValueError, match="status and blockers"):
        QualitySystemAuditCheck(
            "CHECK",
            "subject",
            True,
            ("evidence",),
            blockers=("SHOULD_NOT_EXIST",),
        )

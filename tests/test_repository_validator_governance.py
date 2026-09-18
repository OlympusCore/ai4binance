from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai4binance.governance.repository_validator import (
    RepositoryFindingKind,
    RepositoryValidationFinding,
    RepositoryValidationReport,
    RepositoryValidationStatus,
    validate_repository,
)

FAMILY_INDEX_KNOWLEDGE_PATHS = {
    "docs/governance/policy_organization_constitution_handbook.md",
    "docs/registries/registry_documentation_index.md",
}

PROVIDER_ADAPTER_KNOWLEDGE_PATHS = {
    "CLAUDE.md",
    "GEMINI.md",
    "docs/governance/instruction_core_custom_instructions.md",
    "docs/providers/instruction_codex_provider.md",
    "docs/providers/instruction_claude_provider.md",
    "docs/providers/runbook_tradingview_mcp_codex_connection.md",
}

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VNEXT_LOCK_ALIGNMENT_PATHS = (
    "README.md",
    "docs/compliance/registry_compliance_matrix.md",
    "docs/registries/registry_strategy_registry.md",
)


def test_vnext_governed_document_locks_match_current_content() -> None:
    manifest_path = (
        REPOSITORY_ROOT / "config/governance/governed_document_lock_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    locked_documents = {entry["path"]: entry for entry in manifest["locked_documents"]}

    for relative_path in VNEXT_LOCK_ALIGNMENT_PATHS:
        current_sha256 = hashlib.sha256(
            (REPOSITORY_ROOT / relative_path).read_bytes()
        ).hexdigest()
        lock_entry = locked_documents[relative_path]
        assert lock_entry["lock_state"] == "LOCKED"
        assert lock_entry["sha256"] == current_sha256
        assert lock_entry["expected_hash"] == current_sha256

    strategy_lock = locked_documents["docs/registries/registry_strategy_registry.md"]
    assert strategy_lock["sha256"] == (
        "3708ead3d451b5382ad2d9253710a6a0af7f6912407304368306539e6a3d59d7"
    )


def _default_authority_scope(relative_path: str, path: Path) -> str:
    scope = (
        path.stem.removeprefix("instruction_")
        .removeprefix("procedure_")
        .removeprefix("runbook_")
        .removeprefix("standard_")
        .removeprefix("framework_")
        .removeprefix("registry_")
        .removeprefix("control_")
        .removeprefix("reference_")
        .removeprefix("entity_rule_")
        .lower()
        .replace("-", "_")
        .replace(".", "_")
    )
    if scope:
        return scope
    return relative_path.replace("/", "_").replace(".", "_").lower()


def _default_authority_layer(relative_path: str) -> str:
    if relative_path.startswith(("docs/references/", "docs/templates/")):
        return "L9_REFERENCES_TEMPLATES"
    if relative_path.startswith(("docs/archive/", "archive/")):
        return "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"
    if relative_path.startswith(("docs/reports/", "docs/inventories/", "runtime/")):
        return "L8_REPORTS_EVIDENCE_INVENTORIES"
    if relative_path.startswith(
        ("docs/workflows/", "docs/procedures/", "docs/runbooks/")
    ):
        return "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    if relative_path.startswith(("docs/architecture/", "docs/adr/", "docs/ontology/")):
        return "L6_ARCHITECTURE_ONTOLOGY_ADR"
    if relative_path.startswith(("docs/registries/", "docs/roadmap/")):
        return "L5_REGISTRIES_ROADMAP"
    if relative_path.startswith(("docs/standards/", "docs/controls/", "policies/")):
        return "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES"
    if relative_path.startswith(("docs/contracts/", "docs/schemas/", "schemas/")):
        return "L3_CANONICAL_CONTRACTS_SCHEMAS"
    if relative_path.startswith(("docs/compliance/",)):
        return "L2_GOVERNANCE_COMPLIANCE"
    if relative_path.startswith(("docs/governance/",)):
        return "L1_CORE_CONSTITUTION"
    return "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"


def _default_authority_effect(
    *,
    relative_path: str,
    source_of_truth: str,
    content_role: str,
) -> str | None:
    if relative_path.startswith(("docs/references/", "docs/templates/")):
        return "REFERENCE_ONLY"
    if relative_path.startswith(("docs/archive/", "archive/")):
        return "ARCHIVE_ONLY"
    if (
        content_role in {"EVIDENCE", "GENERATED", "DERIVED"}
        or source_of_truth != "true"
    ):
        return "EVIDENCE_ONLY"
    if relative_path.startswith(
        ("docs/workflows/", "docs/procedures/", "docs/runbooks/")
    ):
        return "OPERATIONAL_SPECIALIZATION"
    return "NORMATIVE_CONSTRAINT"


def _write_required_repository_fixture(root: Path) -> None:
    _write_canonical_root_files(root)
    _write_blocker_registry(root)
    for relative in (
        "docs/governance",
        "docs/providers",
        "docs/registries",
        "docs/compliance",
        "docs/standards",
        "config/governance",
        "src/ai4binance/governance",
        "tests",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    _write_governed_doc(
        root / "AGENTS.md",
        document_id="AI4B-GOV-INS-002",
        title="AI4BINANCE Codex Startup Instructions",
        document_type="INSTRUCTION",
        authority_level="REPOSITORY",
        content_role="OPERATIONAL",
    )
    _write_governed_doc(
        root / "CLAUDE.md",
        document_id="AI4B-GOV-AGT-CLAUDE-001",
        title="AI4BINANCE Claude Provider Adapter Instructions",
        document_type="INSTRUCTION",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "GEMINI.md",
        document_id="AI4B-GOV-AGT-GEMINI-001",
        title="AI4BINANCE Gemini Provider Adapter Instructions",
        document_type="INSTRUCTION",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "README.md",
        document_id="AI4B-DOC-README-001",
        title="AI4BINANCE Repository README",
        document_type="REGISTRY",
        authority_level="REPOSITORY",
        content_role="OPERATIONAL",
    )
    _write_governed_doc(
        root / "docs" / "governance" / "instruction_core_custom_instructions.md",
        document_id="AI4B-GOV-INS-001",
        title="AI4BINANCE Core Custom Instructions",
        document_type="INSTRUCTION",
    )
    _write_governed_doc(
        root / "docs" / "governance" / "framework_core_vnext_governance.md",
        document_id="AI4B-GOV-FRM-001",
        title="AI4BINANCE Core vNext Governance Framework",
        document_type="FRAMEWORK",
    )
    _write_governed_doc(
        root / "docs" / "governance" / "policy_organization_constitution_handbook.md",
        document_id="AI4B-GOV-OEK-003",
        title="AI4BINANCE Operational Ethical Constitution",
        document_type="FRAMEWORK",
    )
    _write_governed_doc(
        root / "docs" / "registries" / "registry_documentation_index.md",
        document_id="AI4B-GOV-REG-DOC-001",
        title="AI4BINANCE Documentation Registry Index",
        document_type="REGISTRY",
    )
    _write_governed_doc(
        root / "docs" / "compliance" / "registry_compliance_matrix.md",
        document_id="AI4B-GOV-REG-001",
        title="AI4BINANCE Compliance Matrix",
        document_type="REGISTRY",
    )
    _write_governed_doc(
        root / "docs" / "providers" / "instruction_codex_provider.md",
        document_id="AI4B-GOV-PRV-CODEX-001",
        title="AI4BINANCE Codex Provider Instructions",
        document_type="PROVIDER_ADAPTER",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "docs" / "providers" / "instruction_claude_provider.md",
        document_id="AI4B-GOV-PRV-CLAUDE-001",
        title="AI4BINANCE Claude Provider Instructions",
        document_type="PROVIDER_ADAPTER",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "docs" / "providers" / "runbook_tradingview_mcp_codex_connection.md",
        document_id="AI4B-GOV-RUN-CODEX-MCP-001",
        title="AI4BINANCE TradingView MCP Codex Connection Runbook",
        document_type="RUNBOOK",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "docs" / "standards" / "standard_repository_file_governance.md",
        document_id="AI4B-GOV-STD-RFG-001",
        title="AI4BINANCE Repository File Governance Standard",
        document_type="STANDARD",
    )
    _write_governed_doc(
        root / "docs" / "standards" / "standard_documentation_knowledge_governance.md",
        document_id="AI4B-GOV-STD-DKG-CORE-001",
        title="AI4BINANCE Documentation and Knowledge Governance Standard",
        document_type="STANDARD",
    )
    _write_governed_doc(
        root
        / "docs"
        / "standards"
        / "standard_engineering_python_clean_code_vscode_development.md",
        document_id="AI4B-ENG-STD-001",
        title="AI4BINANCE Python Clean Code and VS Code Development Guide",
        document_type="STANDARD",
    )
    _write_governed_doc(
        root / "docs" / "standards" / "standard_terminology_governance.md",
        document_id="AI4B-GOV-STD-TERM-001",
        title="AI4BINANCE Terminology Governance Standard",
        document_type="STANDARD",
    )


def _write_canonical_root_files(root: Path) -> None:
    files = {
        ".env.example": "# AI4BINANCE environment example.\n",
        ".gitattributes": "* text=auto eol=lf\n",
        ".gitignore": "__pycache__/\n",
        ".python-version": "3.12.10\n",
        "pyproject.toml": '[project]\nname = "ai4binance"\n',
        "uv.lock": "# Generated by uv.\n",
    }
    for filename, text in files.items():
        (root / filename).write_text(text, encoding="utf-8")


def _write_blocker_registry(root: Path) -> None:
    path = root / "config" / "governance" / "blocker_registry.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "---",
                'version: "1.0.0"',
                "blocker_definitions:",
                '  - definition_id: "AI4B-BLK-GOV-001"',
                '    blocker_code: "GOV.AUTHORITY_CONFLICT"',
                '    domain: "GOVERNANCE"',
                '    blocker_class: "HARD_BLOCKER"',
                '    severity: "CRITICAL"',
                '    scope: "GLOBAL"',
                '    authority: "GOVERNANCE_ENGINE"',
                "    effects:",
                '      - "QUALITY_GATE_BLOCKED"',
                '      - "LIVE_ORDER_BLOCKED"',
                "    waiver:",
                "      allowed: false",
                "    clearance:",
                '      detect_authorities: ["GOVERNANCE_ENGINE"]',
                '      clear_authorities: ["GOVERNANCE_ENGINE"]',
                '    semantic_key: "governance_authority_conflict"',
                '    description: "Authority conflict fixture."',
                '    policy_ref: "policy:governance:authority"',
                '    policy_version: "1.0.0"',
                '    control_ref: "control:governance:authority-conflict"',
                '    control_version: "1.0.0"',
                '    producer: "RepositoryValidatorFixture"',
                '    source_component: "tests.repository_validator_governance"',
                '    remediation: "Resolve authority conflict fixture."',
                "    precedence: 0",
                "aliases:",
                '  GOVERNANCE_CONFLICT: "GOV.AUTHORITY_CONFLICT"',
                "",
            )
        ),
        encoding="utf-8",
    )


def _write_governed_doc(
    path: Path,
    *,
    document_id: str,
    title: str,
    document_type: str = "STANDARD",
    version: str = "1.0.0",
    status: str = "ACTIVE",
    content_role: str = "AUTHORITATIVE",
    source_of_truth: str = "true",
    machine_enforceable: str = "true",
    authority_level: str = "NORMATIVE",
    authority_layer: str | None = None,
    authority_scope: str | None = None,
    authority_effect: str | None = None,
    canonical_path: str | None = None,
    source_of_truth_scope: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    relative = path.as_posix()
    canonical_path = canonical_path or relative
    if authority_scope is None:
        authority_scope = _default_authority_scope(relative, path)
    if authority_layer is None:
        authority_layer = _default_authority_layer(relative)
    if authority_effect is None:
        authority_effect = _default_authority_effect(
            relative_path=relative,
            source_of_truth=source_of_truth,
            content_role=content_role,
        )
    if source_of_truth_scope is None:
        if relative in FAMILY_INDEX_KNOWLEDGE_PATHS:
            source_of_truth_scope = "family_index"
        elif authority_scope is not None and relative.startswith("docs/workflows/"):
            source_of_truth_scope = f"{authority_scope}_workflow"
        elif authority_scope is not None and relative.startswith("docs/procedures/"):
            source_of_truth_scope = f"{authority_scope}_procedure"
        elif authority_scope is not None and relative.startswith("docs/runbooks/"):
            source_of_truth_scope = f"{authority_scope}_runbook"
        elif (
            relative in PROVIDER_ADAPTER_KNOWLEDGE_PATHS
            or authority_level == "PROVIDER_ADAPTER"
        ):
            source_of_truth_scope = "provider_adapter"
        elif source_of_truth == "true":
            source_of_truth_scope = "canonical"

    body = "\n".join(
        (
            "---",
            f"document_id: {document_id}",
            f"title: {title}",
            f"document_type: {document_type}",
            f"version: {version}",
            f"status: {status}",
            "owner: Enterprise Governance",
            f"authority_level: {authority_level}",
            f"authority_layer: {authority_layer}",
            f"authority_scope: {authority_scope}",
            *(
                (f"authority_effect: {authority_effect}",)
                if authority_effect is not None
                else ()
            ),
            f"content_role: {content_role}",
            f"source_of_truth: {source_of_truth}",
            *(
                (f"source_of_truth_scope: {source_of_truth_scope}",)
                if source_of_truth_scope is not None
                else ()
            ),
            f"machine_enforceable: {machine_enforceable}",
            "audit_required: true",
            "classification: INTERNAL",
            f"canonical_path: {canonical_path}",
            "---",
            "",
            "# Standard",
            "",
            "## ELI10",
            "",
            "Governed metadata contract.",
            "",
        )
    )
    path.write_text(body, encoding="utf-8")


def _findings_by_path(
    report: RepositoryValidationReport,
) -> dict[str, list[RepositoryValidationFinding]]:
    findings: dict[str, list[RepositoryValidationFinding]] = {}
    for finding in report.findings:
        findings.setdefault(finding.path, []).append(finding)
    return findings


def _rewrite_frontmatter_line(path: Path, prefix: str, replacement: str | None) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            replaced = True
            if replacement is not None:
                updated.append(replacement)
            continue
        updated.append(line)
    if not replaced:
        raise AssertionError(f"Expected frontmatter line starting with {prefix!r}")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def test_repository_validator_requires_canonical_path_for_governed_knowledge(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    framework_path = (
        tmp_path / "docs" / "governance" / "framework_core_vnext_governance.md"
    )
    _rewrite_frontmatter_line(framework_path, "canonical_path: ", None)

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING
        and "canonical_path" in finding.detail
        for finding in findings["docs/governance/framework_core_vnext_governance.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_requires_family_index_scope_for_governed_knowledge(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    handbook_path = (
        tmp_path
        / "docs"
        / "governance"
        / "policy_organization_constitution_handbook.md"
    )
    _rewrite_frontmatter_line(handbook_path, "source_of_truth_scope: ", None)

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING
        and "source_of_truth_scope" in finding.detail
        for finding in findings[
            "docs/governance/policy_organization_constitution_handbook.md"
        ]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_rejects_wrong_scope_for_family_index_document(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    handbook_path = (
        tmp_path
        / "docs"
        / "governance"
        / "policy_organization_constitution_handbook.md"
    )
    _rewrite_frontmatter_line(
        handbook_path,
        "source_of_truth_scope: ",
        "source_of_truth_scope: provider_adapter",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        and "family_index" in finding.detail
        for finding in findings[
            "docs/governance/policy_organization_constitution_handbook.md"
        ]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_requires_provider_adapter_scope_for_governed_knowledge(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    provider_path = tmp_path / "docs" / "providers" / "instruction_claude_provider.md"
    _rewrite_frontmatter_line(
        provider_path,
        "source_of_truth_scope: ",
        "source_of_truth_scope: canonical",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        and "provider_adapter" in finding.detail
        for finding in findings["docs/providers/instruction_claude_provider.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_rejects_wrong_scope_for_canonical_document(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    readme_path = tmp_path / "README.md"
    _rewrite_frontmatter_line(
        readme_path,
        "source_of_truth_scope: ",
        "source_of_truth_scope: family_index",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        and "canonical" in finding.detail
        for finding in findings["README.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_rejects_mismatched_canonical_path_for_governed_knowledge(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    framework_path = (
        tmp_path / "docs" / "governance" / "framework_core_vnext_governance.md"
    )
    _rewrite_frontmatter_line(
        framework_path,
        "canonical_path: ",
        "canonical_path: docs/governance/framework_core_vnext_governance_copy.md",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        and "canonical_path must match repository-relative path" in finding.detail
        for finding in findings["docs/governance/framework_core_vnext_governance.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_runtime_markdown_source_of_truth_claim(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    runtime_report = tmp_path / "runtime" / "reports" / "weekly.md"
    runtime_report.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        runtime_report,
        document_id="AI4B-GOV-EVID-RUNTIME-001",
        title="Runtime Weekly Report",
        document_type="EVIDENCE_REQUIREMENT",
        authority_level="ADVISORY",
        content_role="GENERATED",
        canonical_path="runtime/reports/weekly.md",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        and "source_of_truth=true" in finding.detail
        for finding in findings["runtime/reports/weekly.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_excludes_non_active_maintenance_archive_markdown(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    archived_report = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "maintenance_archive"
        / "legacy-capture"
        / "governance.md"
    )
    archived_report.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        archived_report,
        document_id="AI4B-GOV-EVID-ARCHIVE-001",
        title="Archived Governance Capture",
        document_type="EVIDENCE_REQUIREMENT",
        authority_level="NORMATIVE",
        content_role="AUTHORITATIVE",
        canonical_path=(
            "runtime/artifacts/maintenance_archive/legacy-capture/governance.md"
        ),
    )
    active_report = tmp_path / "runtime" / "reports" / "active-governance.md"
    active_report.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        active_report,
        document_id="AI4B-GOV-EVID-ACTIVE-001",
        title="Active Runtime Governance Claim",
        document_type="EVIDENCE_REQUIREMENT",
        authority_level="NORMATIVE",
        content_role="AUTHORITATIVE",
        canonical_path="runtime/reports/active-governance.md",
    )

    report = validate_repository(tmp_path)

    findings = _findings_by_path(report)
    assert (
        "runtime/artifacts/maintenance_archive/legacy-capture/governance.md"
        not in findings
    )
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        for finding in findings["runtime/reports/active-governance.md"]
    )
    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_excludes_non_active_vnext_worktree_markdown(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    worktree_report = (
        tmp_path / "runtime" / "tmp" / "vnext_worktrees" / "vnxt-019-r4" / "AGENTS.md"
    )
    worktree_report.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        worktree_report,
        document_id="AI4B-GOV-EVID-WORKTREE-001",
        title="Inactive Vnext Worktree Governance Copy",
        document_type="INSTRUCTION",
        authority_level="REPOSITORY",
        content_role="AUTHORITATIVE",
        canonical_path="runtime/tmp/vnext_worktrees/vnxt-019-r4/AGENTS.md",
    )
    active_report = tmp_path / "runtime" / "reports" / "active-governance.md"
    active_report.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        active_report,
        document_id="AI4B-GOV-EVID-ACTIVE-002",
        title="Active Runtime Governance Claim",
        document_type="EVIDENCE_REQUIREMENT",
        authority_level="NORMATIVE",
        content_role="AUTHORITATIVE",
        canonical_path="runtime/reports/active-governance.md",
    )

    report = validate_repository(tmp_path)

    findings = _findings_by_path(report)
    assert "runtime/tmp/vnext_worktrees/vnxt-019-r4/AGENTS.md" not in findings
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        for finding in findings["runtime/reports/active-governance.md"]
    )
    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_excludes_process_scoped_test_fixture_markdown(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    fixture_copy = (
        tmp_path
        / "runtime"
        / "tmp"
        / "process"
        / "pytest"
        / "run-001"
        / "docs"
        / "governance.md"
    )
    fixture_copy.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        fixture_copy,
        document_id="AI4B-GOV-EVID-PROCESS-TEMP-001",
        title="Process Temporary Governance Copy",
        document_type="INSTRUCTION",
        authority_level="REPOSITORY",
        content_role="AUTHORITATIVE",
        canonical_path=("runtime/tmp/process/pytest/run-001/docs/governance.md"),
    )

    report = validate_repository(tmp_path)

    findings = _findings_by_path(report)
    assert "runtime/tmp/process/pytest/run-001/docs/governance.md" not in findings


def test_repository_validator_keeps_runtime_non_authoritative_even_with_live_terms(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    runtime_report = tmp_path / "runtime" / "reports" / "authority-summary.md"
    runtime_report.parent.mkdir(parents=True, exist_ok=True)
    runtime_report.write_text(
        "\n".join(
            (
                "---",
                "document_id: AI4B-GOV-EVID-RUNTIME-003",
                "title: Runtime Authority Summary",
                "document_type: EVIDENCE_REQUIREMENT",
                "version: 1.0.0",
                "status: ACTIVE",
                "owner: Enterprise Governance",
                "authority_level: ADVISORY",
                "content_role: GENERATED",
                "source_of_truth: true",
                "source_of_truth_scope: canonical",
                "machine_enforceable: true",
                "audit_required: true",
                "classification: INTERNAL",
                "canonical_path: runtime/reports/authority-summary.md",
                "---",
                "",
                "# Runtime Summary",
                "",
                "Docs are authority.",
                "Validator is enforcement.",
                "Quality gate is evidence.",
                "Human governance is consequential authority.",
                "Runtime is not source-of-truth.",
                "LLM is not authority.",
                "Scores cannot hide blockers.",
                "LIVE remains blocked.",
            )
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        and "source_of_truth=true" in finding.detail
        for finding in findings["runtime/reports/authority-summary.md"]
    )
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        and "source_of_truth_scope" in finding.detail
        for finding in findings["runtime/reports/authority-summary.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_runtime_markdown_canonical_scope_claim(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    runtime_report = tmp_path / "runtime" / "audit" / "repository-validator" / "run.md"
    runtime_report.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        runtime_report,
        document_id="AI4B-GOV-EVID-RUNTIME-002",
        title="Runtime Validator Report",
        document_type="EVIDENCE_REQUIREMENT",
        authority_level="ADVISORY",
        content_role="GENERATED",
        source_of_truth="false",
        canonical_path="runtime/audit/repository-validator/run.md",
        source_of_truth_scope="canonical",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        and "source_of_truth_scope" in finding.detail
        for finding in findings["runtime/audit/repository-validator/run.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_surfaces_non_utf8_runtime_markdown_without_crashing(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    runtime_report = tmp_path / "runtime" / "reports" / "utf16-authority-summary.md"
    runtime_report.parent.mkdir(parents=True, exist_ok=True)
    runtime_report.write_text(
        "---\nsource_of_truth: true\n---\n# UTF-16 runtime report\n",
        encoding="utf-16",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION
        for finding in findings["runtime/reports/utf16-authority-summary.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_treats_factory_brief_as_governed_operational_exception(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    factory_brief = tmp_path / "factory" / "brief.md"
    factory_brief.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        factory_brief,
        document_id="AI4B-FACTORY-WFLOW-001",
        title="AI4BINANCE Factory Brief",
        document_type="WORKFLOW",
        authority_level="NORMATIVE",
        content_role="AUTHORITATIVE",
        canonical_path="factory/brief_copy.md",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        and "canonical_path must match repository-relative path" in finding.detail
        for finding in findings["factory/brief.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_noncanonical_operational_markdown_authority_claim(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    factory_state = tmp_path / "factory" / "state.md"
    factory_state.parent.mkdir(parents=True, exist_ok=True)
    _write_governed_doc(
        factory_state,
        document_id="AI4B-FACTORY-STATE-001",
        title="AI4BINANCE Factory State",
        document_type="STATE",
        authority_level="NORMATIVE",
        content_role="AUTHORITATIVE",
        canonical_path="factory/state.md",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = _findings_by_path(report)
    assert any(
        finding.kind is RepositoryFindingKind.RUNTIME_MARKDOWN_AUTHORITY_VIOLATION
        and "Non-canonical operational Markdown must not declare source_of_truth=true."
        in finding.detail
        for finding in findings["factory/state.md"]
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_allows_noncanonical_operational_markdown(
    tmp_path: Path,
) -> None:
    _write_required_repository_fixture(tmp_path)
    factory_state = tmp_path / "factory" / "state.md"
    factory_state.parent.mkdir(parents=True, exist_ok=True)
    factory_state.write_text(
        "# AI4BINANCE Factory State\n\nOperational note only.\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    findings = _findings_by_path(report)
    assert "factory/state.md" not in findings

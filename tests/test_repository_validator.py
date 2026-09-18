from __future__ import annotations

# ruff: noqa: E501
import json
import runpy
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.governance import repository_validator as repository_validator_module
from ai4binance.governance.blockers import BLOCKER_REGISTRY_PATH
from ai4binance.governance.repository_validator import (
    DKG_CORE_REQUIRED_SECTION_TITLES,
    GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH,
    GovernedKnowledgeObject,
    KnowledgeAuthorityEffect,
    KnowledgeAuthorityLevel,
    KnowledgeClassification,
    KnowledgeContentRole,
    KnowledgeLifecycleStatus,
    KnowledgeObjectType,
    RepositoryArtifact,
    RepositoryArtifactClass,
    RepositoryArtifactLifecycle,
    RepositoryArtifactType,
    RepositoryFindingKind,
    RepositoryFindingSeverity,
    RepositoryPolicy,
    RepositoryValidationFinding,
    RepositoryValidationReport,
    RepositoryValidationStatus,
    validate_repository,
)
from tests.documentation_hygiene_helpers import stale_knowledge_template_offenders

pytestmark = [
    pytest.mark.governance,
    pytest.mark.validator,
    pytest.mark.runtime_io,
    pytest.mark.slow,
]

ROOT = Path(__file__).resolve().parents[1]

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

CANONICAL_TOP_LEVEL_PATHS = {
    "config",
    "docs",
    "migrations",
    "runtime",
    "schemas",
    "scripts",
    "src",
    "tests",
    "tools",
}


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


def _write_required_knowledge_docs(root: Path) -> None:
    _write_canonical_root_files(root)
    _create_canonical_top_level_dirs(root)
    _write_blocker_registry(root)
    _write_repository_validator_policy(
        root / repository_validator_module.REPOSITORY_VALIDATOR_POLICY_PATH
    )
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    _write_governed_doc(
        root / "AGENTS.md",
        root=root,
        document_id="AI4B-GOV-INS-002",
        title="AI4BINANCE Codex Startup Instructions",
        document_type="INSTRUCTION",
        authority_level="REPOSITORY",
        content_role="OPERATIONAL",
    )
    _write_governed_doc(
        root / "CLAUDE.md",
        root=root,
        document_id="AI4B-GOV-AGT-CLAUDE-001",
        title="AI4BINANCE Claude Provider Adapter Instructions",
        document_type="INSTRUCTION",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "GEMINI.md",
        root=root,
        document_id="AI4B-GOV-AGT-GEMINI-001",
        title="AI4BINANCE Gemini Provider Adapter Instructions",
        document_type="INSTRUCTION",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        docs / "providers" / "instruction_codex_provider.md",
        root=root,
        document_id="AI4B-GOV-PRV-CODEX-001",
        title="AI4BINANCE Codex Provider Instructions",
        document_type="PROVIDER_ADAPTER",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    _write_governed_doc(
        root / "README.md",
        root=root,
        document_id="AI4B-DOC-README-001",
        title="AI4BINANCE Repository README",
        document_type="REGISTRY",
        authority_level="REPOSITORY",
        content_role="OPERATIONAL",
    )
    _write_governed_doc(
        docs / "governance" / "instruction_core_custom_instructions.md",
        root=root,
        document_id="AI4B-GOV-INS-001",
        title="AI4BINANCE Core Custom Instructions",
        document_type="INSTRUCTION",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
        source_of_truth_scope="provider_adapter",
    )
    _write_governed_doc(
        docs / "governance/framework_core_vnext_governance.md",
        root=root,
        document_id="AI4B-GOV-FRM-001",
        title="AI4BINANCE Core vNext Governance Framework",
        document_type="FRAMEWORK",
    )
    _write_governed_doc(
        docs / "governance/policy_organization_constitution_handbook.md",
        root=root,
        document_id="AI4B-GOV-OEK-003",
        title="AI4BINANCE Operational Ethical Constitution",
        document_type="FRAMEWORK",
        source_of_truth_scope="family_index",
    )
    _write_governed_doc(
        docs / "compliance/registry_compliance_matrix.md",
        root=root,
        document_id="AI4B-GOV-REG-001",
        title="AI4BINANCE Compliance Matrix",
        document_type="REGISTRY",
    )
    _write_governed_doc(
        docs / "standards" / "standard_repository_file_governance.md",
        root=root,
        document_id="AI4B-GOV-STD-RFG-001",
        title="AI4BINANCE Repository File Governance Standard",
    )
    _write_governed_doc(
        docs
        / "standards"
        / "standard_engineering_python_clean_code_vscode_development.md",
        root=root,
        document_id="AI4B-ENG-STD-001",
        title="AI4BINANCE Python Clean Code and VS Code Development Guide",
    )
    _write_governed_doc(
        docs / "standards" / "standard_documentation_knowledge_governance.md",
        root=root,
        document_id="AI4B-GOV-STD-DKG-CORE-001",
        title="AI4BINANCE Documentation and Knowledge Governance Standard",
    )
    _write_governed_doc(
        docs / "standards" / "standard_terminology_governance.md",
        root=root,
        document_id="AI4B-GOV-STD-TERM-001",
        title="AI4BINANCE Terminology Governance Standard",
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


def _create_canonical_top_level_dirs(root: Path) -> None:
    for name in (
        "config",
        "docs",
        "migrations",
        "runtime",
        "schemas",
        "scripts",
        "src",
        "tests",
        "tools",
        "policies",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)


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
                '    source_component: "tests.repository_validator"',
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
    root: Path | None = None,
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
    extra_frontmatter: tuple[str, ...] = (),
) -> None:
    body = ["# Standard", "", "## ELI10", "", "Governed metadata contract."]
    if path.name == "standard_documentation_knowledge_governance.md":
        for title in DKG_CORE_REQUIRED_SECTION_TITLES:
            body.extend(("", f"## {title}", "", f"Test fixture for {title}."))
    path.parent.mkdir(parents=True, exist_ok=True)
    relative_path = _repository_relative_path(path, root)
    canonical_path = canonical_path or relative_path
    if authority_scope is None:
        authority_scope = _default_authority_scope(relative_path, path)
    if authority_layer is None:
        authority_layer = _default_authority_layer(relative_path)
    if authority_effect is None:
        authority_effect = _default_authority_effect(
            relative_path=relative_path,
            source_of_truth=source_of_truth,
            content_role=content_role,
        )
    if source_of_truth_scope is None:
        if authority_scope is not None and relative_path.startswith("docs/workflows/"):
            source_of_truth_scope = f"{authority_scope}_workflow"
        elif authority_scope is not None and relative_path.startswith(
            "docs/procedures/"
        ):
            source_of_truth_scope = f"{authority_scope}_procedure"
        elif authority_scope is not None and relative_path.startswith("docs/runbooks/"):
            source_of_truth_scope = f"{authority_scope}_runbook"
        elif relative_path in FAMILY_INDEX_KNOWLEDGE_PATHS:
            source_of_truth_scope = "family_index"
        elif (
            relative_path in PROVIDER_ADAPTER_KNOWLEDGE_PATHS
            or authority_level == "PROVIDER_ADAPTER"
        ):
            source_of_truth_scope = "provider_adapter"
        elif source_of_truth == "true":
            source_of_truth_scope = "canonical"
    canonical_path_lines = (f"canonical_path: {canonical_path}",)
    scope_lines = (
        (f"source_of_truth_scope: {source_of_truth_scope}",)
        if source_of_truth_scope is not None
        else ()
    )
    authority_lines = tuple(
        line
        for line in (
            (
                f"authority_layer: {authority_layer}"
                if authority_layer is not None
                else None
            ),
            (
                f"authority_scope: {authority_scope}"
                if authority_scope is not None
                else None
            ),
            (
                f"authority_effect: {authority_effect}"
                if authority_effect is not None
                else None
            ),
        )
        if line is not None
    )
    path.write_text(
        "\n".join(
            (
                "---",
                f"document_id: {document_id}",
                f"title: {title}",
                f"document_type: {document_type}",
                f"version: {version}",
                f"status: {status}",
                "owner: Enterprise Governance",
                f"authority_level: {authority_level}",
                *authority_lines,
                f"content_role: {content_role}",
                f"source_of_truth: {source_of_truth}",
                *scope_lines,
                f"machine_enforceable: {machine_enforceable}",
                "audit_required: true",
                "classification: INTERNAL",
                *extra_frontmatter,
                *canonical_path_lines,
                "---",
                "",
                *body,
            )
        ),
        encoding="utf-8",
    )


def _repository_relative_path(path: Path, root: Path | None = None) -> str:
    if root is not None:
        return path.relative_to(root).as_posix()
    inferred_root = _infer_repository_root(path)
    if inferred_root is not None:
        return path.relative_to(inferred_root).as_posix()
    parts = path.parts
    for index, part in enumerate(parts[:-1]):
        if part in CANONICAL_TOP_LEVEL_PATHS:
            return Path(*parts[index:]).as_posix()
    return path.name


def _infer_repository_root(path: Path) -> Path | None:
    canonical_markers = {
        "config",
        "docs",
        "migrations",
        "runtime",
        "schemas",
        "scripts",
        "src",
        "tests",
        "tools",
    }
    for ancestor in path.resolve().parents:
        if not ancestor.is_dir():
            continue
        marker_count = sum(
            1 for marker in canonical_markers if (ancestor / marker).exists()
        )
        if marker_count >= 4:
            return ancestor
    return None


def _write_mirror_policy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                'policy_id: "AI4B-GOV-MIRROR-HYGIENE-001"',
                'version: "1.0.0"',
                'status: "ACTIVE"',
                "canonical_repository:",
                '  authority: "AUTHORITATIVE"',
                "mirror:",
                '  role: "NON_CANONICAL_MIRROR"',
                '  authority: "NONE"',
                "  may_be_source_of_truth: false",
                "  may_override_canonical: false",
                "sync:",
                '  default_action: "EXCLUDE"',
                "  allowed_exact_paths:",
                '    - "./README.md"',
                '    - "AGENTS.md"',
                "  allowed_prefixes:",
                '    - "src"',
                '    - "tests"',
                '    - "docs"',
                '    - "config"',
                '    - "tools"',
                "retention:",
                "  selective_prefixes:",
                '    - "runtime/reports"',
                '    - "runtime/artifacts/quality/gate"',
                "exclusions:",
                "  hard_exclude_patterns:",
                '    - ".pytest_cache"',
                '    - ".pytest_cache/**"',
                '    - "**/*.pyc"',
                "  private_patterns:",
                '    - ".env"',
                '    - ".env.*"',
                '    - "**/*secret*"',
                "  local_only_prefixes:",
                '    - "state"',
                '    - "runtime/data"',
                '    - "runtime/logs"',
                '    - "logs"',
                "  never_mirror_prefixes:",
                '    - "artifacts/test_temp"',
                '    - "runtime/tmp"',
                "",
            )
        ),
        encoding="utf-8",
    )


def _write_repository_validator_policy(path: Path) -> None:
    _write_json(path, asdict(RepositoryPolicy.ai4binance_vnext()))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_document_lock_manifest(
    root: Path,
    paths: tuple[str, ...],
    *,
    baseline_sha256: dict[str, str] | None = None,
    approvals: dict[str, str] | None = None,
) -> None:
    manifest_path = root / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def lock_entry(relative: str) -> dict[str, object]:
        metadata = _test_frontmatter(root / relative)
        expected_hash = (
            baseline_sha256[relative]
            if baseline_sha256 and relative in baseline_sha256
            else _sha256(root / relative)
        )
        return {
            "path": relative,
            "canonical_path": metadata.get("canonical_path", relative),
            "authority_level": metadata["authority_level"],
            "authority_layer": metadata.get("authority_layer"),
            "authority_effect": metadata.get("authority_effect"),
            "authority_scope": metadata.get("authority_scope"),
            "document_status": metadata["status"],
            "version": metadata["version"],
            "expected_hash": expected_hash,
            "sha256": expected_hash,
            "source_of_truth": metadata["source_of_truth"].lower() == "true",
            "supersedes": [],
            "allowed_change_process": "WRITTEN_OWNER_APPROVAL_REQUIRED",
            "lock_state": "LOCKED",
            "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
        }

    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "ACTIVE",
        "owner": "Enterprise Governance",
        "written_owner_approval_required": True,
        "manifest_lock_policy": {
            "lock_state": "LOCKED",
            "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
            "written_owner_approval_required": True,
            "filesystem_lock_required": True,
        },
        "locked_documents": [lock_entry(relative) for relative in paths],
        "approval_records": [],
    }
    if approvals:
        payload["approval_records"] = [
            {
                "approval_id": "AI4B-GOV-DOCLOCK-TEST-001",
                "approval_status": "APPROVED",
                "approved_by": "Huseyin",
                "approved_at_utc": "2026-08-20T00:00:00Z",
                "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
                "written_owner_approval": True,
                "approved_sha256": approvals,
            }
        ]
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _test_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("\"'`")
    return fields


def _git_commit_all(root: Path) -> bool:
    git = "git"
    try:
        subprocess.run(  # noqa: S603
            [git, "init"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # noqa: S603
            [git, "config", "user.email", "tests@example.invalid"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # noqa: S603
            [git, "config", "user.name", "AI4BINANCE Tests"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # noqa: S603
            [git, "add", "."],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # noqa: S603
            [git, "commit", "-m", "baseline"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def _fixture_lock_paths(root: Path) -> tuple[str, ...]:
    policy = RepositoryPolicy.ai4binance_vnext()
    locked_paths: list[str] = []
    for relative in (*policy.knowledge_metadata_required_paths, "README.md"):
        path = root / relative
        if not path.is_file():
            continue
        metadata = _test_frontmatter(path)
        knowledge_object = repository_validator_module._knowledge_object(
            relative,
            metadata,
        )
        if repository_validator_module._requires_governed_document_lock(
            knowledge_object
        ):
            locked_paths.append(relative)
    return tuple(locked_paths)


def _repository_artifact(**overrides: object) -> RepositoryArtifact:
    values: dict[str, Any] = {
        "artifact_id": "artifact-1",
        "artifact_type": RepositoryArtifactType.SOURCE_CODE,
        "artifact_class": RepositoryArtifactClass.SOURCE,
        "domain": "Engineering",
        "owner": "Engineering",
        "canonical_path": "src/ai4binance/example.py",
        "filename": "example.py",
        "schema_version": None,
        "lifecycle_status": RepositoryArtifactLifecycle.ACTIVE,
        "generated": False,
        "immutable": False,
        "sensitive": False,
        "git_tracked": True,
        "checksum": "a" * 64,
        "source_of_truth": False,
        "machine_enforceable": False,
        "audit_required": False,
        "classification": KnowledgeClassification.INTERNAL,
    }
    values.update(overrides)
    return RepositoryArtifact(**values)


def _knowledge_object(**overrides: object) -> GovernedKnowledgeObject:
    values: dict[str, Any] = {
        "knowledge_id": "AI4B-GOV-STD-001",
        "knowledge_type": KnowledgeObjectType.STANDARD,
        "title": "Repository Governance Standard",
        "version": "1.0.0",
        "lifecycle_status": KnowledgeLifecycleStatus.ACTIVE,
        "authority_level": KnowledgeAuthorityLevel.NORMATIVE,
        "authority_layer": "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        "authority_effect": KnowledgeAuthorityEffect.NORMATIVE_CONSTRAINT,
        "content_role": KnowledgeContentRole.AUTHORITATIVE,
        "owner": "Enterprise Governance",
        "source_of_truth": True,
        "machine_enforceable": True,
        "audit_required": True,
        "classification": KnowledgeClassification.INTERNAL,
        "path": "docs/standards/standard_repository_file_governance.md",
        "canonical_path": "docs/standards/standard_repository_file_governance.md",
        "authority_scope": "repository_file_governance",
    }
    values.update(overrides)
    return GovernedKnowledgeObject(**values)


def _validation_report(**overrides: object) -> RepositoryValidationReport:
    values: dict[str, Any] = {
        "policy_id": "AI4B-GOV-REPO-POLICY",
        "policy_version": "1.1.0",
        "repository_root": "C:/repo",
        "analyzed_at_utc": "2026-08-23T00:00:00+00:00",
        "status": RepositoryValidationStatus.PASS,
        "artifact_count": 1,
        "governed_knowledge_count": 0,
        "artifacts": (_repository_artifact(),),
        "findings": (),
        "recommended_actions": (),
        "blockers": (),
        "repository_health_score": 100,
    }
    values.update(overrides)
    return RepositoryValidationReport(**values)


def _remediation_action(
    **overrides: object,
) -> repository_validator_module.RepositoryRemediationAction:
    values: dict[str, Any] = {
        "action_id": "action-id",
        "finding_kind": RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID,
        "action_type": "FIX_METADATA",
        "current_path": "docs/example.md",
        "proposed_path": "docs/example-fixed.md",
        "reason": "Fix metadata.",
        "destructive": False,
        "requires_approval": True,
        "evidence_required": (
            "pre_change_validation_report",
            "impact_analysis",
        ),
    }
    values.update(overrides)
    return repository_validator_module.RepositoryRemediationAction(**values)


def _mirror_hygiene_report(
    **overrides: object,
) -> repository_validator_module.MirrorHygieneReport:
    finding = RepositoryValidationFinding(
        kind=RepositoryFindingKind.MIRROR_UNKNOWN_PATH,
        severity=RepositoryFindingSeverity.HIGH,
        path="unknown/path.bin",
        detail="Unknown mirror path.",
        blocker=True,
    )
    cleanup_entry = repository_validator_module.MirrorCleanupPlanEntry(
        path="unknown/path.bin",
        classification=repository_validator_module.MirrorPathClassification.UNKNOWN,
        canonical_required=False,
        mirror_action=repository_validator_module.MirrorCleanupAction.QUARANTINE_FOR_REVIEW,
        local_action="KEEP_UNTIL_CLASSIFIED",
        risk="MEDIUM",
        approval_required=True,
    )
    values: dict[str, Any] = {
        "policy_id": "AI4B-GOV-MIRROR-HYGIENE-001",
        "policy_version": "1.0.0",
        "mirror_manifest_path": "runtime/artifacts/repository_validation/mirror-manifest.json",
        "analyzed_at_utc": "2026-08-24T00:00:00+00:00",
        "status": RepositoryValidationStatus.RUNNING_WITH_BLOCKERS,
        "mirror_role": "NON_CANONICAL_MIRROR",
        "mirror_authority": "NONE",
        "mirror_source_of_truth": False,
        "entry_count": 1,
        "findings": (finding,),
        "cleanup_plan": (cleanup_entry,),
        "blockers": ("MIRROR_UNKNOWN_PATH:unknown/path.bin",),
        "dashboard_metrics": {"mirror_noise_ratio": 1.0},
    }
    values.update(overrides)
    return repository_validator_module.MirrorHygieneReport(**values)


def test_repository_validator_dataclasses_fail_closed_on_invalid_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="must be en-US"):
        replace(
            RepositoryPolicy.ai4binance_vnext(),
            non_code_content_language="tr-TR",
        )
    with pytest.raises(ValueError, match="repository-relative posix"):
        _repository_artifact(canonical_path=r"src\ai4binance\example.py")
    with pytest.raises(ValueError, match="must not be hashed"):
        _repository_artifact(sensitive=True, checksum="a" * 64)
    with pytest.raises(ValueError, match="size cannot be negative"):
        _repository_artifact(size=-1)
    with pytest.raises(ValueError, match="source_of_truth must be boolean"):
        _repository_artifact(source_of_truth="true")
    with pytest.raises(ValueError, match="machine_enforceable must be boolean"):
        _repository_artifact(machine_enforceable="true")
    with pytest.raises(ValueError, match="audit_required must be boolean"):
        _repository_artifact(audit_required="true")
    with pytest.raises(
        ValueError,
        match="classification must use the canonical knowledge classification",
    ):
        _repository_artifact(classification="INTERNAL")
    with pytest.raises(ValueError, match="authority_basis must be unique"):
        _repository_artifact(authority_basis=("L4", "L4"))
    with pytest.raises(ValueError, match="repository-relative posix"):
        repository_validator_module.MirrorInventoryEntry(path=r"runtime\report.json")
    with pytest.raises(ValueError, match="finding_id"):
        RepositoryValidationFinding(
            kind=RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
            severity=RepositoryFindingSeverity.HIGH,
            path="docs/missing.md",
            detail="Missing canonical document.",
            blocker=True,
            finding_id=" ",
        )
    with pytest.raises(ValueError, match="passing repository validation"):
        _validation_report(blockers=("BLOCKER",))
    with pytest.raises(ValueError, match="cannot authorize execution"):
        _validation_report(execution_allowed=True)
    with pytest.raises(ValueError, match="cannot authorize live trading"):
        _validation_report(live_eligibility_status="READY")
    with pytest.raises(ValueError, match="repository_health_score"):
        _validation_report(repository_health_score=101)

    monkeypatch.setattr(repository_validator_module, "to_primitive", lambda _: ())
    with pytest.raises(RuntimeError, match="REPOSITORY_VALIDATION_PAYLOAD_INVALID"):
        _validation_report().to_payload()
    with pytest.raises(RuntimeError, match="MIRROR_HYGIENE_PAYLOAD_INVALID"):
        _mirror_hygiene_report().to_payload()


def test_health_score_applies_critical_penalty() -> None:
    finding = RepositoryValidationFinding(
        kind=RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
        severity=RepositoryFindingSeverity.CRITICAL,
        path="docs/missing.md",
        detail="Missing canonical document.",
        blocker=True,
    )

    assert repository_validator_module._health_score((finding,)) == 75


def test_health_score_applies_warning_penalty_and_ignores_info() -> None:
    warning_finding = RepositoryValidationFinding(
        kind=RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
        severity=RepositoryFindingSeverity.WARNING,
        path="docs/warning.md",
        detail="Warning finding.",
        blocker=False,
    )
    info_finding = RepositoryValidationFinding(
        kind=RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
        severity=RepositoryFindingSeverity.INFO,
        path="docs/info.md",
        detail="Informational finding.",
        blocker=False,
    )

    assert repository_validator_module._health_score((warning_finding,)) == 98
    assert repository_validator_module._health_score((info_finding,)) == 100


def test_repository_validation_finding_populates_structured_classification() -> None:
    finding = RepositoryValidationFinding(
        kind=RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC,
        severity=RepositoryFindingSeverity.HIGH,
        path="src/ai4binance/runtime/latest.json",
        detail="Generated runtime artifact must not live under src.",
        blocker=True,
    )

    assert (
        finding.control_family
        is repository_validator_module.RepositoryControlFamily.RUNTIME_HYGIENE
    )
    assert finding.domain == "runtime"
    assert finding.rule_id == "RV-GENERATED_ARTIFACT_INSIDE_SRC"
    assert finding.finding_id.startswith("RFG-GENERATED_ARTIFACT_INSIDE_SRC-")


def test_governed_knowledge_object_rejects_invalid_authority_metadata() -> None:
    with pytest.raises(ValueError, match="repository-relative posix"):
        _knowledge_object(canonical_path="/docs/standard.md")
    with pytest.raises(ValueError, match="must match repository-relative path"):
        _knowledge_object(canonical_path="docs/other.md")
    with pytest.raises(ValueError, match="knowledge_id must match"):
        _knowledge_object(knowledge_id="BAD-ID")
    with pytest.raises(ValueError, match="semantic"):
        _knowledge_object(version="1")
    with pytest.raises(ValueError, match="source_of_truth=true"):
        _knowledge_object(source_of_truth=False)
    with pytest.raises(ValueError, match="requires content_role"):
        _knowledge_object(
            content_role=KnowledgeContentRole.EXPLANATORY,
            source_of_truth=True,
        )
    with pytest.raises(ValueError, match="secret values"):
        _knowledge_object(
            content_role=KnowledgeContentRole.OPERATIONAL,
            classification=KnowledgeClassification.SECRET,
        )


def test_repository_validator_main_writes_requested_outputs(tmp_path: Path) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True, exist_ok=True)
    (source / "repository_validator.py").write_text(
        "from pathlib import Path\n\nROOT = Path(__file__).resolve()\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_repository_validator.py").write_text(
        "def test_contract():\n    assert True\n",
        encoding="utf-8",
    )
    output_json = tmp_path / "reports" / "repository.json"
    output_markdown = tmp_path / "reports" / "repository.md"
    output_migration = tmp_path / "reports" / "migration.md"
    output_findings = tmp_path / "reports" / "findings.json"
    output_policy_snapshot = tmp_path / "reports" / "policy-snapshot.json"

    exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
            "--output-migration-map",
            str(output_migration),
            "--output-findings-json",
            str(output_findings),
            "--output-policy-snapshot",
            str(output_policy_snapshot),
            "--quiet",
        ]
    )

    assert exit_code == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["status"] == "PASS"
    findings_payload = json.loads(output_findings.read_text(encoding="utf-8"))
    assert findings_payload["status"] == "PASS"
    assert findings_payload["policy_source_path"] == (
        "policies/repository-validator/manifest-policy.json"
    )
    snapshot_payload = json.loads(output_policy_snapshot.read_text(encoding="utf-8"))
    assert snapshot_payload["policy"]["policy_id"] == "AI4B-GOV-REPO-POLICY"
    assert snapshot_payload["policy_source_path"] == (
        "policies/repository-validator/manifest-policy.json"
    )
    assert "Repository Governance Validation" in output_markdown.read_text(
        encoding="utf-8"
    )
    assert "Repository Governance Migration Map" in output_migration.read_text(
        encoding="utf-8"
    )


def test_repository_validator_module_entrypoint_exits_with_main_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True, exist_ok=True)
    (source / "repository_validator.py").write_text(
        "from pathlib import Path\n\nROOT = Path(__file__).resolve()\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_repository_validator.py").write_text(
        "def test_contract():\n    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repository_validator.py",
            "--repository-root",
            str(tmp_path),
            "--quiet",
        ],
    )

    with pytest.raises(SystemExit, match="0"):
        runpy.run_path(
            str(Path(repository_validator_module.__file__).resolve()),
            run_name="__main__",
        )


def test_validate_repository_requires_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="existing directory"):
        validate_repository(tmp_path / "missing")


def test_document_lock_manifest_helpers_reject_invalid_payload_shapes() -> None:
    policy_cases = (
        (None, "declare manifest_lock_policy"),
        ({"lock_state": "OPEN"}, "lock_state must be LOCKED"),
        (
            {
                "lock_state": "LOCKED",
                "approval_policy": "OTHER",
                "written_owner_approval_required": True,
                "filesystem_lock_required": True,
            },
            "approval_policy must be",
        ),
        (
            {
                "lock_state": "LOCKED",
                "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
                "written_owner_approval_required": False,
                "filesystem_lock_required": True,
            },
            "must require written owner approval",
        ),
        (
            {
                "lock_state": "LOCKED",
                "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
                "written_owner_approval_required": True,
                "filesystem_lock_required": False,
            },
            "must require filesystem",
        ),
    )
    for policy_payload, message in policy_cases:
        policy_error = repository_validator_module._document_lock_manifest_policy(
            policy_payload
        )
        assert policy_error is not None
        assert message in policy_error

    valid_entry: dict[str, object] = {
        "path": "AGENTS.md",
        "canonical_path": "AGENTS.md",
        "authority_level": "REPOSITORY",
        "document_status": "ACTIVE",
        "version": "1.0.0",
        "source_of_truth": True,
        "supersedes": [],
        "allowed_change_process": "WRITTEN_OWNER_APPROVAL_REQUIRED",
        "sha256": "a" * 64,
        "expected_hash": "a" * 64,
        "lock_state": "LOCKED",
        "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
    }
    entry_cases: tuple[tuple[object, str], ...] = (
        (None, "must contain locked_documents"),
        ([object()], "must be a JSON object"),
        ([valid_entry | {"path": "../AGENTS.md"}], "entry path is invalid"),
        (
            [valid_entry | {"canonical_path": "../AGENTS.md"}],
            "canonical_path is invalid",
        ),
        ([valid_entry | {"canonical_path": "README.md"}], "canonical_path must match"),
        ([valid_entry | {"authority_level": ""}], "authority_level is invalid"),
        ([valid_entry | {"document_status": ""}], "document_status is invalid"),
        ([valid_entry | {"version": "1"}], "version is invalid"),
        ([valid_entry | {"source_of_truth": "true"}], "source_of_truth is invalid"),
        ([valid_entry | {"supersedes": [" "]}], "supersedes is invalid"),
        ([valid_entry | {"allowed_change_process": "OTHER"}], "allowed_change_process"),
        ([valid_entry | {"sha256": "bad"}], "invalid sha256"),
        ([valid_entry | {"expected_hash": "b" * 64}], "expected_hash must match"),
        ([valid_entry | {"lock_state": "OPEN"}], "lock_state must be LOCKED"),
        ([valid_entry | {"approval_policy": "OTHER"}], "approval policy is invalid"),
        ([valid_entry, valid_entry], "entry is duplicated"),
    )
    for entry_payload, message in entry_cases:
        _, error = repository_validator_module._document_lock_entries(entry_payload)
        assert error is not None
        assert message in error

    entries, error = repository_validator_module._document_lock_entries([valid_entry])
    assert error is None
    assert entries["AGENTS.md"].expected_hash == "a" * 64


def test_document_lock_approvals_and_manifest_file_errors(tmp_path: Path) -> None:
    approval_cases = (
        (None, "approval_records must be a JSON array"),
        ([object()], "approval record must be a JSON object"),
        (
            [
                {
                    "approval_status": "APPROVED",
                    "written_owner_approval": False,
                }
            ],
            "require written approval",
        ),
        (
            [
                {
                    "approval_status": "APPROVED",
                    "written_owner_approval": True,
                    "approved_sha256": {},
                }
            ],
            "must include approved_sha256",
        ),
        (
            [
                {
                    "approval_status": "APPROVED",
                    "written_owner_approval": True,
                    "approved_sha256": {"../AGENTS.md": "a" * 64},
                }
            ],
            "path is invalid",
        ),
        (
            [
                {
                    "approval_status": "APPROVED",
                    "written_owner_approval": True,
                    "approved_sha256": {"AGENTS.md": "bad"},
                }
            ],
            "sha256 is invalid",
        ),
    )
    for payload, message in approval_cases:
        _, error = repository_validator_module._document_lock_approvals(
            payload,
            tmp_path,
        )
        assert error is not None
        assert message in error

    approvals, error = repository_validator_module._document_lock_approvals(
        [
            {"approval_status": "PENDING"},
            {
                "approval_status": "APPROVED",
                "written_owner_approval": True,
                "approved_sha256": {"AGENTS.md": "a" * 64},
            },
        ]
    )
    assert error is None
    assert approvals == frozenset({("AGENTS.md", "a" * 64)})

    evidence_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "governance"
        / "approval.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        "artifact_origin": "governed_document_lock_written_owner_approval",
        "approval_id": "AI4B-GOV-DOCLOCK-TEST-001",
        "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
        "approval_status": "APPROVED",
        "approved_by": "Huseyin",
        "approved_at_utc": "2026-08-20T00:00:00Z",
        "written_owner_approval": True,
        "verification_status": "VERIFIED",
        "approved_sha256": {"AGENTS.md": "a" * 64},
    }
    evidence_path.write_text(
        json.dumps(evidence_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    valid_approval_with_evidence = [
        {
            "approval_id": "AI4B-GOV-DOCLOCK-TEST-001",
            "approval_status": "APPROVED",
            "approved_by": "Huseyin",
            "approved_at_utc": "2026-08-20T00:00:00Z",
            "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
            "written_owner_approval": True,
            "approved_sha256": {"AGENTS.md": "a" * 64},
            "approval_evidence_path": (
                "runtime/artifacts/repository_validation/governance/approval.json"
            ),
            "approval_evidence_sha256": repository_validator_module._sha256(
                evidence_path
            ),
        }
    ]
    approvals, error = repository_validator_module._document_lock_approvals(
        valid_approval_with_evidence,
        tmp_path,
    )
    assert error is None
    assert approvals == frozenset({("AGENTS.md", "a" * 64)})

    _, error = repository_validator_module._document_lock_approvals(
        [valid_approval_with_evidence[0] | {"approval_evidence_sha256": "b" * 64}],
        tmp_path,
    )
    assert error == (
        "Approved document lock evidence sha256 mismatch: "
        "runtime/artifacts/repository_validation/governance/approval.json."
    )

    mirror_error = repository_validator_module._document_lock_written_owner_approvals(
        [
            {
                "approval_id": "AI4B-GOV-DOCLOCK-TEST-ORPHAN-001",
                "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
                "approval_status": "APPROVED",
                "approved_by": "Huseyin",
                "approved_at_utc": "2026-08-20T00:00:00Z",
                "written_owner_approval": True,
                "approved_sha256": {"AGENTS.md": "a" * 64},
            }
        ],
        valid_approval_with_evidence,
    )
    assert mirror_error == (
        "Written owner approval must be mirrored in approval_records: "
        "AI4B-GOV-DOCLOCK-TEST-ORPHAN-001."
    )

    mirror_error = repository_validator_module._document_lock_written_owner_approvals(
        [
            valid_approval_with_evidence[0]
            | {"approval_status": "PENDING", "approval_evidence_sha256": "b" * 64}
        ],
        valid_approval_with_evidence,
    )
    assert mirror_error == (
        "Written owner approval mirror mismatch for "
        "AI4B-GOV-DOCLOCK-TEST-001: approval_status."
    )

    manifest_path = tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    entries, approvals, error = repository_validator_module._document_lock_manifest(
        tmp_path
    )
    assert entries == {}
    assert approvals == frozenset()
    assert error is not None
    assert "manifest is missing" in error
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{", encoding="utf-8")
    _, _, error = repository_validator_module._document_lock_manifest(tmp_path)
    assert error is not None
    assert "manifest is invalid" in error
    manifest_path.write_text("[]", encoding="utf-8")
    _, _, error = repository_validator_module._document_lock_manifest(tmp_path)
    assert error is not None
    assert "must be a JSON object" in error
    manifest_path.write_text(
        json.dumps({"status": "DRAFT"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _, _, error = repository_validator_module._document_lock_manifest(tmp_path)
    assert error == "Governed document lock manifest status must be ACTIVE."
    manifest_path.write_text(
        json.dumps(
            {"status": "ACTIVE", "written_owner_approval_required": False},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _, _, error = repository_validator_module._document_lock_manifest(tmp_path)
    assert (
        error == "Governed document lock manifest must require written owner approval."
    )
    manifest_path.write_text(
        json.dumps(
            {
                "status": "ACTIVE",
                "written_owner_approval_required": True,
                "manifest_lock_policy": {
                    "lock_state": "LOCKED",
                    "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
                    "written_owner_approval_required": True,
                    "filesystem_lock_required": True,
                },
                "locked_documents": None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _, _, error = repository_validator_module._document_lock_manifest(tmp_path)
    assert error == "Governed document lock manifest must contain locked_documents."
    manifest_path.write_text(
        json.dumps(
            {
                "status": "ACTIVE",
                "written_owner_approval_required": True,
                "manifest_lock_policy": {
                    "lock_state": "LOCKED",
                    "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
                    "written_owner_approval_required": True,
                    "filesystem_lock_required": True,
                },
                "locked_documents": [
                    {
                        "path": "AGENTS.md",
                        "canonical_path": "AGENTS.md",
                        "authority_level": "REPOSITORY",
                        "document_status": "ACTIVE",
                        "version": "1.0.0",
                        "sha256": "a" * 64,
                        "expected_hash": "a" * 64,
                        "source_of_truth": True,
                        "supersedes": [],
                        "allowed_change_process": "WRITTEN_OWNER_APPROVAL_REQUIRED",
                        "lock_state": "LOCKED",
                        "approval_policy": "WRITTEN_OWNER_APPROVAL_REQUIRED",
                    }
                ],
                "approval_records": None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _, _, error = repository_validator_module._document_lock_manifest(tmp_path)
    assert error == "approval_records must be a JSON array."


def test_repository_validator_private_text_and_remediation_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crlf = tmp_path / "crlf.md"
    crlf.write_text(
        "---\r\n"
        "document_id: AI4B-GOV-STD-001\r\n"
        "supersedes:\r\n"
        "  - AI4B-GOV-OLD-001\r\n"
        "---\r\n"
        "# Title\r\n",
        encoding="utf-8",
    )
    no_frontmatter = tmp_path / "plain.md"
    no_frontmatter.write_text("# Title\n", encoding="utf-8")
    unclosed = tmp_path / "unclosed.md"
    unclosed.write_text("---\ndocument_id: AI4B-GOV-STD-001\n", encoding="utf-8")

    metadata = repository_validator_module._frontmatter(crlf)
    assert metadata is not None
    assert metadata["document_id"] == "AI4B-GOV-STD-001"
    exact_crlf = tmp_path / "exact-crlf.md"
    exact_crlf.write_bytes(
        b"---\r\n"
        b"document_id: AI4B-GOV-STD-CRLF-001\r\n"
        b"supersedes:\r\n"
        b"  - AI4B-GOV-STD-CRLF-LEGACY-001\r\n"
        b"title: Exact CRLF\r\n"
        b"---\r\n"
        b"# Title\r\n"
    )
    original_read_text = Path.read_text

    def read_text_with_exact_crlf(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == exact_crlf:
            return (
                "---\r\n"
                "document_id: AI4B-GOV-STD-CRLF-001\r\n"
                "supersedes:\r\n"
                "  - AI4B-GOV-STD-CRLF-LEGACY-001\r\n"
                "title: Exact CRLF\r\n"
                "---\r\n"
                "# Title\r\n"
            )
        kwargs: dict[str, str] = {}
        if encoding is not None:
            kwargs["encoding"] = encoding
        if errors is not None:
            kwargs["errors"] = errors
        return original_read_text(path, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text_with_exact_crlf)
    exact_crlf_metadata = repository_validator_module._frontmatter(exact_crlf)
    assert exact_crlf_metadata is not None
    assert exact_crlf_metadata["document_id"] == "AI4B-GOV-STD-CRLF-001"
    assert repository_validator_module._frontmatter_sequence(
        exact_crlf,
        "supersedes",
    ) == ("AI4B-GOV-STD-CRLF-LEGACY-001",)
    assert repository_validator_module._frontmatter(no_frontmatter) is None
    assert repository_validator_module._frontmatter(unclosed) is None
    assert (
        repository_validator_module._frontmatter_sequence(
            unclosed,
            "supersedes",
        )
        == ()
    )
    assert repository_validator_module._frontmatter_sequence(crlf, "supersedes") == (
        "AI4B-GOV-OLD-001",
    )
    inline_supersedes = tmp_path / "inline-supersedes.md"
    inline_supersedes.write_text(
        "---\n"
        "document_id: AI4B-GOV-STD-INLINE-001\n"
        "supersedes: AI4B-GOV-STD-INLINE-LEGACY-001\n"
        "---\n"
        "# Title\n",
        encoding="utf-8",
    )
    assert repository_validator_module._frontmatter_sequence(
        inline_supersedes,
        "supersedes",
    ) == ("AI4B-GOV-STD-INLINE-LEGACY-001",)
    malformed_supersedes = tmp_path / "malformed-supersedes.md"
    malformed_supersedes.write_text(
        "---\n"
        "document_id: AI4B-GOV-STD-MALFORMED-001\n"
        "supersedes:\n"
        "  not-a-list-item\n"
        "---\n"
        "# Title\n",
        encoding="utf-8",
    )
    assert (
        repository_validator_module._frontmatter_sequence(
            malformed_supersedes,
            "supersedes",
        )
        == ()
    )
    mixed_supersedes = tmp_path / "mixed-supersedes.md"
    mixed_supersedes.write_text(
        "---\n"
        "document_id: AI4B-GOV-STD-MIXED-001\n"
        "supersedes:\n"
        "  - AI4B-GOV-STD-MIXED-LEGACY-001\n"
        "  not-a-list-item\n"
        "---\n"
        "# Title\n",
        encoding="utf-8",
    )
    assert repository_validator_module._frontmatter_sequence(
        mixed_supersedes,
        "supersedes",
    ) == ("AI4B-GOV-STD-MIXED-LEGACY-001",)
    assert (
        repository_validator_module._frontmatter_sequence(
            no_frontmatter,
            "supersedes",
        )
        == ()
    )
    legacy_supersedes = tmp_path / "legacy-supersedes.md"
    legacy_supersedes.write_text(
        "---\n"
        "document_id: AI4B-GOV-STD-001\n"
        "title: Repository Governance Standard\n"
        "document_type: STANDARD\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Enterprise Governance\n"
        "authority_level: NORMATIVE\n"
        "content_role: AUTHORITATIVE\n"
        "source_of_truth: true\n"
        "machine_enforceable: true\n"
        "audit_required: true\n"
        "classification: INTERNAL\n"
        "canonical_path: legacy-supersedes.md\n"
        "supersedes_document_ids:\n"
        "  - AI4B-GOV-STD-LEGACY-001\n"
        "---\n\n"
        "# ELI10\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    assert (
        repository_validator_module._document_lock_registration_error(
            _knowledge_object(
                path="legacy-supersedes.md",
                canonical_path="legacy-supersedes.md",
            ),
            repository_validator_module.GovernedDocumentLockEntry(
                path="legacy-supersedes.md",
                canonical_path="legacy-supersedes.md",
                authority_level="NORMATIVE",
                document_status="ACTIVE",
                version="1.0.0",
                expected_hash=_sha256(legacy_supersedes),
                source_of_truth=True,
                supersedes=("AI4B-GOV-STD-LEGACY-001",),
                allowed_change_process="WRITTEN_OWNER_APPROVAL_REQUIRED",
            ),
            tmp_path,
        )
        is None
    )
    direct_supersedes = tmp_path / "direct-supersedes.md"
    direct_supersedes.write_text(
        "---\n"
        "document_id: AI4B-GOV-STD-002\n"
        "title: Direct Supersedes Standard\n"
        "document_type: STANDARD\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Enterprise Governance\n"
        "authority_level: NORMATIVE\n"
        "content_role: AUTHORITATIVE\n"
        "source_of_truth: true\n"
        "machine_enforceable: true\n"
        "audit_required: true\n"
        "classification: INTERNAL\n"
        "canonical_path: direct-supersedes.md\n"
        "supersedes:\n"
        "  - AI4B-GOV-STD-OLDER-001\n"
        "---\n\n"
        "# ELI10\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    assert (
        repository_validator_module._document_lock_registration_error(
            _knowledge_object(
                knowledge_id="AI4B-GOV-STD-002",
                title="Direct Supersedes Standard",
                path="direct-supersedes.md",
                canonical_path="direct-supersedes.md",
            ),
            repository_validator_module.GovernedDocumentLockEntry(
                path="direct-supersedes.md",
                canonical_path="direct-supersedes.md",
                authority_level="NORMATIVE",
                document_status="ACTIVE",
                version="1.0.0",
                expected_hash=_sha256(direct_supersedes),
                source_of_truth=True,
                supersedes=("AI4B-GOV-STD-OLDER-001",),
                allowed_change_process="WRITTEN_OWNER_APPROVAL_REQUIRED",
            ),
            tmp_path,
        )
        is None
    )
    assert (
        repository_validator_module._document_lock_registration_error(
            _knowledge_object(
                knowledge_id="AI4B-GOV-STD-003",
                title="Unreadable Metadata Standard",
                path="plain.md",
                canonical_path="plain.md",
            ),
            repository_validator_module.GovernedDocumentLockEntry(
                path="plain.md",
                canonical_path="plain.md",
                authority_level="NORMATIVE",
                document_status="ACTIVE",
                version="1.0.0",
                expected_hash=_sha256(no_frontmatter),
                source_of_truth=True,
                supersedes=(),
                allowed_change_process="WRITTEN_OWNER_APPROVAL_REQUIRED",
            ),
            tmp_path,
        )
        == "Locked governed document metadata could not be read."
    )
    assert repository_validator_module._metadata_bool("flag", {"flag": "true"}) is True
    assert (
        repository_validator_module._metadata_bool("flag", {"flag": "false"}) is False
    )
    with pytest.raises(ValueError, match="must be true or false"):
        repository_validator_module._metadata_bool("flag", {"flag": "maybe"})

    text = (
        "```kod içinde sistem```\n`veri`\nhttps://example.invalid/uyum\nThis is safe."
    )
    assert repository_validator_module._non_english_markers(text) == ()
    assert repository_validator_module._non_english_markers("sistem ç") == (
        "ç",
        "sistem",
    )
    assert repository_validator_module._has_markdown_heading(
        "# 1. Purpose\n",
        "Purpose",
    )
    assert repository_validator_module._markdown_table_cell("a|b\nc") == "a\\|b c"
    assert repository_validator_module._markdown_proposed_path(None) == ""
    assert repository_validator_module._markdown_proposed_path("docs/target.md") == (
        " -> `docs/target.md`"
    )
    assert repository_validator_module._snake_case_filename("FinalReport_v2.PY") == (
        "final_report.py"
    )

    invalid_governed = tmp_path / "docs" / "invalid.md"
    invalid_governed.parent.mkdir(parents=True, exist_ok=True)
    invalid_governed.write_text(
        "\n".join(
            (
                "---",
                "document_id: ",
                "title: Invalid Fixture",
                "document_type: STANDARD",
                "version: 1.0.0",
                "status: ACTIVE",
                "owner: Enterprise Governance",
                "authority_level: NORMATIVE",
                "content_role: AUTHORITATIVE",
                "source_of_truth: true",
                "machine_enforceable: true",
                "audit_required: true",
                "classification: INTERNAL",
                "---",
                "",
                "# Fixture",
            )
        ),
        encoding="utf-8",
    )
    assert (
        repository_validator_module._authority_metadata_by_path(
            tmp_path,
            ("docs/invalid.md",),
        )
        == {}
    )

    invalid_enum = tmp_path / "docs" / "invalid-enum.md"
    invalid_enum.write_text(
        "\n".join(
            (
                "---",
                "document_id: AI4B-GOV-STD-999",
                "title: Invalid Enum Fixture",
                "document_type: STANDARD",
                "version: 1.0.0",
                "status: ACTIVE",
                "owner: Enterprise Governance",
                "authority_level: NOT_REAL",
                "content_role: AUTHORITATIVE",
                "source_of_truth: true",
                "machine_enforceable: true",
                "audit_required: true",
                "classification: INTERNAL",
                "---",
                "",
                "# Fixture",
            )
        ),
        encoding="utf-8",
    )
    assert (
        repository_validator_module._authority_metadata_by_path(
            tmp_path,
            ("docs/invalid-enum.md",),
        )
        == {}
    )


def test_repository_validator_artifact_finding_and_remediation_helpers(
    tmp_path: Path,
) -> None:
    policy = RepositoryPolicy.ai4binance_vnext()
    assert repository_validator_module._artifact_type(".coverage", policy) is (
        RepositoryArtifactType.CACHE
    )
    assert repository_validator_module._artifact_type(
        "docs/archive/old.md", policy
    ) is (RepositoryArtifactType.ARCHIVE)
    assert repository_validator_module._artifact_type("reports/latest.md", policy) is (
        RepositoryArtifactType.EVIDENCE
    )
    assert repository_validator_module._artifact_type(
        "runtime/state/runtime.json", policy
    ) is (RepositoryArtifactType.RUNTIME)
    assert repository_validator_module._artifact_type("schemas/x.json", policy) is (
        RepositoryArtifactType.SCHEMA
    )
    assert repository_validator_module._artifact_type("policies/x.yaml", policy) is (
        RepositoryArtifactType.POLICY
    )
    assert repository_validator_module._artifact_type("ontology/x.yaml", policy) is (
        RepositoryArtifactType.ONTOLOGY
    )
    assert repository_validator_module._artifact_type("workflows/x.yaml", policy) is (
        RepositoryArtifactType.WORKFLOW
    )
    assert repository_validator_module._artifact_type("migrations/001.sql", policy) is (
        RepositoryArtifactType.MIGRATION
    )
    assert repository_validator_module._artifact_type("data/sample.csv", policy) is (
        RepositoryArtifactType.DATA
    )

    finding_cases = (
        (
            RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION,
            "src/ai4binance/BadName.py",
            "src/ai4binance/bad_name.py",
        ),
        (
            RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC,
            "src/ai4binance/reports/latest.md",
            "runtime/artifacts/repository_validation/governance/remediation/latest.md",
        ),
        (
            RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC,
            "src/ai4binance/runtime/state/runtime.json",
            "runtime/state/governance/runtime.json",
        ),
        (
            RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
            "schemas",
            "schemas",
        ),
    )
    findings = tuple(
        RepositoryValidationFinding(
            kind=kind,
            severity=RepositoryFindingSeverity.HIGH,
            path=path,
            detail="Test finding.",
            blocker=True,
        )
        for kind, path, _ in finding_cases
    )
    actions = tuple(repository_validator_module._recommended_actions(findings))
    assert tuple(action.proposed_path for action in actions) == tuple(
        expected for _, _, expected in finding_cases
    )
    assert all(action.requires_approval for action in actions)
    assert actions[1].destructive is True

    source = tmp_path / "src" / "ai4binance" / "BadPackage" / "BadName_final_v2.py"
    source.parent.mkdir(parents=True)
    source.write_text('ROOT = "C:/machine/specific/path"\n', encoding="utf-8")
    artifact = _repository_artifact(
        canonical_path=source.relative_to(tmp_path).as_posix()
    )
    findings = tuple(
        repository_validator_module._artifact_findings(tmp_path, policy, artifact)
    )
    assert {finding.kind for finding in findings} >= {
        RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION,
        RepositoryFindingKind.SOURCE_VERSION_FILENAME,
        RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION,
        RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH,
    }


def test_repository_validator_mirror_policy_loader_and_helper_validation(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "config" / "governance" / "repository_mirror_policy.yaml"
    _write_mirror_policy(policy_path)

    policy = repository_validator_module.load_repository_mirror_policy(policy_path)

    assert policy.policy_id == "AI4B-GOV-MIRROR-HYGIENE-001"
    assert policy.allowed_exact_paths == ("README.md", "AGENTS.md")
    assert policy.allowed_prefixes == ("src", "tests", "docs", "config", "tools")
    assert policy.selective_prefixes == (
        "runtime/reports",
        "runtime/artifacts/quality/gate",
    )
    assert repository_validator_module._yaml_string_tuple(
        {"items": ["./docs//guide.md/", "tests"]},
        "items",
    ) == ("docs/guide.md", "tests")

    bad_policy = tmp_path / "bad-policy.yaml"
    _write_json(bad_policy, [])
    with pytest.raises(ValueError, match="mirror policy must be a mapping"):
        repository_validator_module.load_repository_mirror_policy(bad_policy)

    bad_canonical = tmp_path / "bad-canonical.yaml"
    _write_json(
        bad_canonical,
        {
            "policy_id": "X",
            "version": "1.0.0",
            "status": "ACTIVE",
            "canonical_repository": [],
            "mirror": {},
            "sync": {},
            "exclusions": {},
            "retention": {},
        },
    )
    with pytest.raises(ValueError, match="canonical_repository must be a mapping"):
        repository_validator_module.load_repository_mirror_policy(bad_canonical)

    bad_mirror = tmp_path / "bad-mirror.yaml"
    _write_json(
        bad_mirror,
        {
            "policy_id": "X",
            "version": "1.0.0",
            "status": "ACTIVE",
            "canonical_repository": {"authority": "AUTHORITATIVE"},
            "mirror": [],
            "sync": {},
            "exclusions": {},
            "retention": {},
        },
    )
    with pytest.raises(ValueError, match="mirror must be a mapping"):
        repository_validator_module.load_repository_mirror_policy(bad_mirror)

    bad_authority = tmp_path / "bad-authority.yaml"
    _write_json(
        bad_authority,
        {
            "policy_id": "X",
            "version": "1.0.0",
            "status": "ACTIVE",
            "canonical_repository": {"authority": "ADVISORY"},
            "mirror": {},
            "sync": {},
            "exclusions": {},
            "retention": {},
        },
    )
    with pytest.raises(
        ValueError, match="canonical repository must remain authoritative"
    ):
        repository_validator_module.load_repository_mirror_policy(bad_authority)

    with pytest.raises(ValueError, match="flag must be a boolean"):
        repository_validator_module._yaml_bool({"flag": "true"}, "flag")
    with pytest.raises(ValueError, match="items must be a non-empty list"):
        repository_validator_module._yaml_string_tuple({"items": []}, "items")
    with pytest.raises(ValueError, match="items entries must be non-empty strings"):
        repository_validator_module._yaml_string_tuple({"items": ["ok", " "]}, "items")

    repository_policy = RepositoryPolicy.ai4binance_vnext()
    forbidden_source = tmp_path / "src" / "ai4binance" / "good_name" / "helper.py"
    forbidden_source.parent.mkdir(parents=True, exist_ok=True)
    forbidden_source.write_text("VALUE = 1\n", encoding="utf-8")
    forbidden_artifact = _repository_artifact(
        canonical_path=forbidden_source.relative_to(tmp_path).as_posix()
    )
    forbidden_findings = tuple(
        repository_validator_module._artifact_findings(
            tmp_path,
            repository_policy,
            forbidden_artifact,
        )
    )
    forbidden_kinds = {finding.kind for finding in forbidden_findings}
    assert RepositoryFindingKind.FORBIDDEN_SOURCE_FILENAME in forbidden_kinds
    assert RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION not in forbidden_kinds


def test_repository_validator_mirror_hygiene_reports_cleanup_actions(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "mirror-manifest.json"
    _write_json(
        manifest_path,
        {
            "source_of_truth": True,
            "authority": "REPOSITORY",
            "entries": [
                ".git/config",
                {"path": "runtime/state/runtime.db", "git_tracked": True},
                {"path": "runtime/data/snapshot.json"},
                {"path": "runtime/logs/app.log"},
                {"path": "artifacts/test_temp/run.json"},
                {"path": "src/ai4binance/module.py", "git_tracked": True},
                {"path": "docs/guide.md"},
                {"path": "tools/helper.ps1"},
                {"path": "unknown/place.txt"},
                {"path": ".env.secret"},
                {"path": "runtime/reports/weekly.md"},
                {"path": "runtime/artifacts/quality/gate/latest.json"},
                {"path": "custom/output.bin", "source_of_truth": True},
                {"source_path": "config/settings.yaml"},
            ],
        },
    )

    report = repository_validator_module.validate_mirror_hygiene(
        manifest_path,
        policy=repository_validator_module.RepositoryMirrorPolicy.ai4binance_vnext(),
    )
    cleanup_by_path = {entry.path: entry for entry in report.cleanup_plan}
    finding_kinds = {finding.kind for finding in report.findings}

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.entry_count == 14
    assert RepositoryFindingKind.MIRROR_FORBIDDEN_PATH in finding_kinds
    assert RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION in finding_kinds
    assert RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION in finding_kinds
    assert RepositoryFindingKind.MIRROR_CACHE_POLLUTION in finding_kinds
    assert RepositoryFindingKind.MIRROR_UNKNOWN_PATH in finding_kinds
    assert RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION in finding_kinds
    assert cleanup_by_path["src/ai4binance/module.py"].mirror_action == (
        repository_validator_module.MirrorCleanupAction.KEEP_IN_MIRROR
    )
    assert cleanup_by_path["unknown/place.txt"].mirror_action == (
        repository_validator_module.MirrorCleanupAction.QUARANTINE_FOR_REVIEW
    )
    assert cleanup_by_path["unknown/place.txt"].approval_required is True
    assert cleanup_by_path[".env.secret"].local_action == "KEEP_LOCAL_ONLY"
    assert cleanup_by_path["runtime/state/runtime.db"].mirror_action == (
        repository_validator_module.MirrorCleanupAction.REMOVE_FROM_MIRROR
    )
    assert cleanup_by_path["runtime/reports/weekly.md"].canonical_required is True
    assert report.dashboard_metrics["mirrored_runtime_pollution_count"] == 3
    assert report.dashboard_metrics["mirrored_cache_count"] == 1
    assert report.dashboard_metrics["source_of_truth_violation_count"] == 3
    assert report.dashboard_metrics["tracked_pollution_count"] == 1
    assert report.dashboard_metrics["filesystem_pollution_count"] == 8
    assert report.dashboard_metrics["mirror_noise_ratio"] == 0.5714


def test_repository_validator_main_validates_mirror_manifest_outputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy_path = tmp_path / repository_validator_module.REPOSITORY_MIRROR_POLICY_PATH
    _write_mirror_policy(policy_path)
    manifest_path = tmp_path / "mirror-manifest.json"
    _write_json(
        manifest_path,
        {
            "entries": [
                "src/ai4binance/module.py",
                "tests/test_module.py",
                "docs/guide.md",
                "config/policy.yaml",
                "tools/helper.ps1",
                "runtime/reports/summary.md",
                "runtime/artifacts/quality/gate/latest.json",
            ]
        },
    )
    output_json = tmp_path / "artifacts" / "mirror-report.json"
    output_markdown = tmp_path / "artifacts" / "mirror-report.md"
    output_cleanup = tmp_path / "artifacts" / "mirror-cleanup.json"

    exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--check-mirror-manifest",
            str(manifest_path),
            "--mirror-policy",
            str(policy_path),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
            "--output-cleanup-plan",
            str(output_cleanup),
        ]
    )

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert '"status": "PASS"' in stdout
    assert output_json.is_file()
    assert output_markdown.is_file()
    assert output_cleanup.is_file()
    markdown_text = output_markdown.read_text(encoding="utf-8")
    assert "AI4BINANCE Repository Mirror Hygiene Validation" in markdown_text
    cleanup_payload = json.loads(output_cleanup.read_text(encoding="utf-8"))
    assert cleanup_payload["execution_allowed"] is False
    assert cleanup_payload["promotion_status"] == "RESEARCH_ONLY"
    assert cleanup_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_repository_validator_main_exports_deterministic_mirror_manifest(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_mirror_policy(
        tmp_path / repository_validator_module.REPOSITORY_MIRROR_POLICY_PATH
    )
    (tmp_path / "src" / "ai4binance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "ai4binance" / "module.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_module.py").write_text(
        "from ai4binance.module import VALUE\n",
        encoding="utf-8",
    )
    (tmp_path / "runtime" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "reports" / "weekly.md").write_text(
        "# Weekly\n",
        encoding="utf-8",
    )
    (tmp_path / "runtime" / "tmp").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "tmp" / "ephemeral.txt").write_text(
        "temp\n",
        encoding="utf-8",
    )

    output_manifest = tmp_path / "artifacts" / "mirror-manifest.json"
    exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--mirror-policy",
            str(tmp_path / repository_validator_module.REPOSITORY_MIRROR_POLICY_PATH),
            "--output-mirror-manifest",
            str(output_manifest),
            "--quiet",
        ]
    )

    payload = json.loads(output_manifest.read_text(encoding="utf-8"))
    exported_paths = [entry["path"] for entry in payload["root_inventory"]]

    assert exit_code == 0
    assert payload["policy_id"] == "AI4B-GOV-MIRROR-HYGIENE-001"
    assert payload["mirror_role"] == "NON_CANONICAL_MIRROR"
    assert payload["authority"] == "NONE"
    assert payload["source_of_truth"] is False
    assert exported_paths == sorted(exported_paths)
    assert "src/ai4binance/module.py" in exported_paths
    assert "tests/test_module.py" in exported_paths
    assert "runtime/tmp/ephemeral.txt" not in exported_paths
    assert all(entry["authority"] == "NONE" for entry in payload["root_inventory"])
    assert all(entry["source_of_truth"] is False for entry in payload["root_inventory"])
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_repository_validator_mirror_classification_helper_branches() -> None:
    classification = repository_validator_module.MirrorPathClassification

    assert (
        repository_validator_module._hard_exclude_classification(
            ".hypothesis/examples/case.json"
        )
        is classification.TEST_CACHE
    )
    assert (
        repository_validator_module._hard_exclude_classification(
            ".pytest-tmp/session/output.txt"
        )
        is classification.TEST_TEMP
    )
    assert (
        repository_validator_module._hard_exclude_classification(
            "runtime/tmp/pytest/session/output.txt"
        )
        is classification.TEST_TEMP
    )
    assert (
        repository_validator_module._hard_exclude_classification(
            "package/__pycache__/module.pyc"
        )
        is classification.GENERATED
    )
    assert (
        repository_validator_module._hard_exclude_classification(
            "src/project.egg-info/PKG-INFO"
        )
        is classification.GENERATED
    )
    assert (
        repository_validator_module._hard_exclude_classification(".coverage")
        is classification.CACHE
    )

    assert (
        repository_validator_module._allowed_exact_classification(".env.example")
        is classification.CONFIG
    )
    assert (
        repository_validator_module._allowed_exact_classification("pyproject.toml")
        is classification.CONFIG
    )
    assert (
        repository_validator_module._allowed_exact_classification(".python-version")
        is classification.CONFIG
    )
    assert (
        repository_validator_module._allowed_exact_classification("README.md")
        is classification.GOVERNED_KNOWLEDGE
    )

    assert (
        repository_validator_module._selective_prefix_classification(
            "runtime/reports/weekly.md"
        )
        is classification.REPORT
    )
    assert (
        repository_validator_module._selective_prefix_classification(
            "runtime/artifacts/quality/gate/latest.json"
        )
        is classification.SELECTIVE_ARCHIVE
    )
    assert (
        repository_validator_module._selective_prefix_classification(
            "artifacts/audit/report.json"
        )
        is classification.AUDIT_EVIDENCE
    )

    assert (
        repository_validator_module._allowed_prefix_classification(
            "src/ai4binance/module.py"
        )
        is classification.SOURCE
    )
    assert (
        repository_validator_module._allowed_prefix_classification(
            "tests/test_module.py"
        )
        is classification.TEST
    )
    assert (
        repository_validator_module._allowed_prefix_classification("docs/guide.md")
        is classification.GOVERNED_KNOWLEDGE
    )
    assert (
        repository_validator_module._allowed_prefix_classification("schemas/model.json")
        is classification.CONTRACT
    )
    assert (
        repository_validator_module._allowed_prefix_classification("config/policy.yaml")
        is classification.CONFIG
    )
    assert (
        repository_validator_module._allowed_prefix_classification(
            "migrations/001_init.sql"
        )
        is classification.MIGRATION
    )
    assert (
        repository_validator_module._allowed_prefix_classification("tools/helper.ps1")
        is classification.TOOLING
    )
    assert (
        repository_validator_module._allowed_prefix_classification("scripts/run.ps1")
        is classification.OPERATIONAL_SURFACE
    )

    assert repository_validator_module._matches_mirror_pattern(
        "runtime/private/state.json",
        ("runtime/private/**",),
    )
    assert repository_validator_module._matches_mirror_pattern(
        "runtime/private",
        ("runtime/private/**",),
    )
    assert repository_validator_module._matches_mirror_pattern(
        "src/pkg/__pycache__",
        ("**/__pycache__",),
    )
    assert repository_validator_module._matches_mirror_pattern(
        "src/pkg/.pytest_cache",
        ("**/.pytest_cache",),
    )
    assert repository_validator_module._matches_mirror_pattern(
        "src/pkg/build/.pytest_cache",
        ("**/.pytest_cache",),
    )
    assert not repository_validator_module._matches_mirror_pattern(
        "docs/readme.md",
        ("runtime/private/**",),
    )


def test_repository_validator_mirror_path_cleanup_edge_branches() -> None:
    classification = repository_validator_module.MirrorPathClassification
    cleanup_action = repository_validator_module.MirrorCleanupAction
    policy = repository_validator_module.RepositoryMirrorPolicy.ai4binance_vnext()

    assert (
        repository_validator_module._mirror_path_classification(
            "pyproject.toml",
            policy,
        )
        is classification.CONFIG
    )
    assert (
        repository_validator_module._mirror_path_classification(".env.example", policy)
        is classification.CONFIG
    )
    assert (
        repository_validator_module._mirror_path_classification(".git/config", policy)
        is classification.SCM_INTERNAL
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "runtime/private/session.json",
            policy,
        )
        is classification.PRIVATE
    )
    assert (
        repository_validator_module._mirror_path_classification(".env.secret", policy)
        is classification.SECRET
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "artifacts/test_temp/run.json",
            policy,
        )
        is classification.TEST_TEMP
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "runtime/tmp/run.json",
            policy,
        )
        is classification.TEMP
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "src/__pycache__/module.cpython-312.pyc",
            policy,
        )
        is classification.GENERATED
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "package.egg-info/PKG-INFO",
            policy,
        )
        is classification.GENERATED
    )
    assert (
        repository_validator_module._mirror_path_classification(
            ".pytest_cache/v/cache/nodeids",
            policy,
        )
        is classification.TEST_CACHE
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "runtime/data/frame.parquet",
            policy,
        )
        is classification.RUNTIME_DATA
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "runtime/logs/app.log",
            policy,
        )
        is classification.RUNTIME_LOG
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "runtime/state/cache.db",
            policy,
        )
        is classification.RUNTIME_STATE
    )
    assert (
        repository_validator_module._mirror_path_classification(
            "runtime/reports/weekly.md",
            policy,
        )
        is classification.REPORT
    )

    entries = (
        repository_validator_module.MirrorInventoryEntry(path="unknown/path.bin"),
        repository_validator_module.MirrorInventoryEntry(
            path="runtime/private/audit.md"
        ),
        repository_validator_module.MirrorInventoryEntry(path="docs/guide.md"),
    )
    findings = (
        RepositoryValidationFinding(
            kind=RepositoryFindingKind.MIRROR_UNKNOWN_PATH,
            severity=RepositoryFindingSeverity.HIGH,
            path="unknown/path.bin",
            detail="Unknown mirror path.",
            blocker=True,
        ),
        RepositoryValidationFinding(
            kind=RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION,
            severity=RepositoryFindingSeverity.HIGH,
            path="runtime/private/audit.md",
            detail="Private evidence must remain local-only.",
            blocker=True,
        ),
    )
    cleanup_plan = tuple(
        repository_validator_module._mirror_cleanup_plan(entries, findings, policy)
    )
    cleanup_by_path = {entry.path: entry for entry in cleanup_plan}

    assert cleanup_by_path["unknown/path.bin"].mirror_action is (
        cleanup_action.QUARANTINE_FOR_REVIEW
    )
    assert cleanup_by_path["unknown/path.bin"].local_action == "KEEP_UNTIL_CLASSIFIED"
    assert cleanup_by_path["unknown/path.bin"].risk == "MEDIUM"
    assert cleanup_by_path["unknown/path.bin"].approval_required is True
    assert cleanup_by_path["unknown/path.bin"].canonical_required is False

    assert cleanup_by_path["runtime/private/audit.md"].mirror_action is (
        cleanup_action.QUARANTINE_FOR_REVIEW
    )
    assert cleanup_by_path["runtime/private/audit.md"].local_action == "KEEP_LOCAL_ONLY"
    assert cleanup_by_path["runtime/private/audit.md"].risk == "HIGH"
    assert cleanup_by_path["runtime/private/audit.md"].approval_required is True
    assert cleanup_by_path["runtime/private/audit.md"].canonical_required is False

    assert cleanup_by_path["docs/guide.md"].mirror_action is (
        cleanup_action.KEEP_IN_MIRROR
    )
    assert cleanup_by_path["docs/guide.md"].local_action == "KEEP_CANONICAL"
    assert cleanup_by_path["docs/guide.md"].canonical_required is True

    dashboard_metrics = repository_validator_module._mirror_dashboard_metrics(
        entries,
        findings,
        cleanup_plan,
    )
    assert dashboard_metrics["unknown_mirror_classification_count"] == 1
    assert dashboard_metrics["mirrored_private_evidence_count"] == 1
    assert dashboard_metrics["filesystem_pollution_count"] == 2
    assert dashboard_metrics["tracked_pollution_count"] == 0
    assert dashboard_metrics["mirror_cleanup_destructive_unknowns"] == 0
    assert dashboard_metrics["mirror_noise_ratio"] == 0.6667


def test_repository_validator_mirror_invalid_payload_branches(
    tmp_path: Path,
) -> None:
    policy = repository_validator_module.RepositoryMirrorPolicy.ai4binance_vnext()

    missing_manifest = tmp_path / "missing-mirror-manifest.json"
    with pytest.raises(ValueError, match="mirror_manifest must be an existing file"):
        repository_validator_module.validate_mirror_hygiene(
            missing_manifest,
            policy=policy,
        )

    invalid_json_manifest = tmp_path / "invalid-mirror-manifest.json"
    invalid_json_manifest.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        repository_validator_module.validate_mirror_hygiene(
            invalid_json_manifest,
            policy=policy,
        )

    with pytest.raises(
        ValueError,
        match="mirror inventory manifest must be a list or mapping",
    ):
        tuple(repository_validator_module._mirror_inventory_entries("invalid"))

    with pytest.raises(
        ValueError,
        match="mirror manifest must contain entries, files, artifacts or paths",
    ):
        repository_validator_module._mirror_manifest_entry_values({})

    with pytest.raises(ValueError, match="mirror manifest entries must be a list"):
        repository_validator_module._mirror_manifest_entry_values({"entries": {}})

    assert tuple(
        repository_validator_module._mirror_inventory_entries(
            {"files": ["src/ai4binance/module.py"]}
        )
    ) == (
        repository_validator_module.MirrorInventoryEntry(
            path="src/ai4binance/module.py"
        ),
    )

    with pytest.raises(
        ValueError, match="mirror inventory entries must be strings or mappings"
    ):
        repository_validator_module._mirror_inventory_entry(123)

    with pytest.raises(
        ValueError, match="mirror inventory entry path must be a string"
    ):
        repository_validator_module._mirror_inventory_entry({"path": 1})

    with pytest.raises(
        ValueError,
        match="mirror inventory entry source_of_truth must be boolean",
    ):
        repository_validator_module._mirror_inventory_entry(
            {"path": "docs/guide.md", "source_of_truth": "true"}
        )

    with pytest.raises(
        ValueError, match="mirror inventory entry authority must be a string"
    ):
        repository_validator_module._mirror_inventory_entry(
            {"path": "docs/guide.md", "authority": 1}
        )

    with pytest.raises(
        ValueError, match="mirror inventory entry git_tracked must be boolean"
    ):
        repository_validator_module._mirror_inventory_entry(
            {"path": "docs/guide.md", "git_tracked": "yes"}
        )

    target = "docs/guide.md"
    valid_source = tmp_path / "notes.md"
    valid_source.write_text(f"See {target} for details.", encoding="utf-8")

    invalid_source = tmp_path / "broken.md"
    invalid_source.write_bytes(b"\xff\xfe\x00\x81")

    counts = repository_validator_module._downstream_usage_counts(
        tmp_path,
        (valid_source, invalid_source),
        (target,),
    )
    assert counts == {target: 1}

    entry = repository_validator_module._mirror_inventory_entry(
        {"source_path": "./config//settings.yaml/"}
    )
    assert entry == repository_validator_module.MirrorInventoryEntry(
        path="config/settings.yaml"
    )

    with pytest.raises(ValueError, match="mirror path must be repository-relative"):
        repository_validator_module._normalize_mirror_path(" ")
    with pytest.raises(ValueError, match="mirror path must be repository-relative"):
        repository_validator_module._normalize_mirror_path(".")
    with pytest.raises(ValueError, match="mirror path must be repository-relative"):
        repository_validator_module._normalize_mirror_path("../secret.txt")

    assert (
        repository_validator_module._normalize_mirror_path(
            ".\\runtime\\reports\\weekly.md/"
        )
        == "runtime/reports/weekly.md"
    )

    invalid_entry_manifest = tmp_path / "invalid-entry-mirror-manifest.json"
    _write_json(invalid_entry_manifest, {"entries": [123]})
    with pytest.raises(
        ValueError, match="mirror inventory entries must be strings or mappings"
    ):
        repository_validator_module.validate_mirror_hygiene(
            invalid_entry_manifest,
            policy=policy,
        )


def test_repository_validator_mirror_authority_and_finding_branches(
    tmp_path: Path,
) -> None:
    classification = repository_validator_module.MirrorPathClassification
    policy = repository_validator_module.RepositoryMirrorPolicy.ai4binance_vnext()

    assert repository_validator_module._is_authoritative_mirror_authority(None) is False
    assert (
        repository_validator_module._is_authoritative_mirror_authority("none") is False
    )
    assert (
        repository_validator_module._is_authoritative_mirror_authority("BACKUP_ONLY")
        is False
    )
    assert (
        repository_validator_module._is_authoritative_mirror_authority(
            "evidence_mirror"
        )
        is False
    )
    assert (
        repository_validator_module._is_authoritative_mirror_authority("REPOSITORY")
        is True
    )

    assert (
        tuple(repository_validator_module._mirror_manifest_authority_findings([])) == ()
    )
    assert (
        tuple(
            repository_validator_module._mirror_manifest_authority_findings(
                {"source_of_truth": False, "authority": "NONE"}
            )
        )
        == ()
    )

    authority_findings = tuple(
        repository_validator_module._mirror_manifest_authority_findings(
            {"source_of_truth": True, "authority": "REPOSITORY"}
        )
    )
    assert len(authority_findings) == 2
    assert all(
        finding.kind is RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION
        for finding in authority_findings
    )
    assert {finding.path for finding in authority_findings} == {"__manifest__"}

    path_finding_cases = {
        classification.SCM_INTERNAL: RepositoryFindingKind.MIRROR_FORBIDDEN_PATH,
        classification.CACHE: RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
        classification.TEST_CACHE: RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
        classification.TEST_TEMP: RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
        classification.GENERATED: RepositoryFindingKind.MIRROR_GENERATED_ARTIFACT,
        classification.PRIVATE: (
            RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION
        ),
        classification.SECRET: (
            RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION
        ),
        classification.RUNTIME_STATE: RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
        classification.RUNTIME_DATA: RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
        classification.RUNTIME_LOG: RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
        classification.TEMP: RepositoryFindingKind.MIRROR_RUNTIME_POLLUTION,
        classification.UNKNOWN: RepositoryFindingKind.MIRROR_UNKNOWN_PATH,
    }
    for path_classification, expected_kind in path_finding_cases.items():
        finding = repository_validator_module._mirror_path_finding(
            "sample/path.txt",
            path_classification,
        )
        assert finding is not None
        assert finding.kind is expected_kind
        assert finding.blocker is True

    assert (
        repository_validator_module._mirror_path_finding(
            "docs/guide.md",
            classification.GOVERNED_KNOWLEDGE,
        )
        is None
    )

    manifest_path = tmp_path / "mirror-authority-manifest.json"
    _write_json(
        manifest_path,
        {
            "source_of_truth": True,
            "authority": "REPOSITORY",
            "entries": [
                {"path": "src/ai4binance/module.py", "authority": "NONE"},
                {"path": "docs/guide.md", "source_of_truth": True},
                {"path": "unknown/path.bin", "authority": "REPOSITORY"},
            ],
        },
    )

    report = repository_validator_module.validate_mirror_hygiene(
        manifest_path,
        policy=policy,
    )

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert len(report.blockers) == len(set(report.blockers))
    assert "MIRROR_SOURCE_OF_TRUTH_VIOLATION:__manifest__" in report.blockers
    assert "MIRROR_SOURCE_OF_TRUTH_VIOLATION:docs/guide.md" in report.blockers
    assert "MIRROR_SOURCE_OF_TRUTH_VIOLATION:unknown/path.bin" in report.blockers
    assert "MIRROR_UNKNOWN_PATH:unknown/path.bin" in report.blockers
    assert report.dashboard_metrics["source_of_truth_violation_count"] == 4


def test_repository_validator_mirror_report_writer_branches(tmp_path: Path) -> None:
    empty_report = repository_validator_module.MirrorHygieneReport(
        policy_id="AI4B-GOV-MIRROR-HYGIENE-001",
        policy_version="1.0.0",
        mirror_manifest_path="runtime/artifacts/repository_validation/mirror-manifest.json",
        analyzed_at_utc="2026-08-24T00:00:00+00:00",
        status=RepositoryValidationStatus.PASS,
        mirror_role="NON_CANONICAL_MIRROR",
        mirror_authority="NONE",
        mirror_source_of_truth=False,
        entry_count=0,
        findings=(),
        cleanup_plan=(),
        blockers=(),
        dashboard_metrics={"mirror_noise_ratio": 0.0},
    )
    empty_json = tmp_path / "artifacts" / "mirror-empty.json"
    empty_markdown = tmp_path / "artifacts" / "mirror-empty.md"
    empty_cleanup = tmp_path / "artifacts" / "mirror-empty-cleanup.json"

    repository_validator_module._write_mirror_report_json(empty_json, empty_report)
    repository_validator_module._write_mirror_report_markdown(
        empty_markdown,
        empty_report,
    )
    repository_validator_module._write_mirror_cleanup_plan(
        empty_cleanup,
        empty_report,
    )

    empty_json_payload = json.loads(empty_json.read_text(encoding="utf-8"))
    empty_markdown_text = empty_markdown.read_text(encoding="utf-8")
    empty_cleanup_payload = json.loads(empty_cleanup.read_text(encoding="utf-8"))

    assert empty_json_payload["status"] == "PASS"
    assert empty_json_payload["mirror_source_of_truth"] is False
    assert "- No mirror hygiene findings." in empty_markdown_text
    assert empty_cleanup_payload["cleanup_plan"] == []
    assert empty_cleanup_payload["execution_allowed"] is False
    assert empty_cleanup_payload["promotion_status"] == "RESEARCH_ONLY"
    assert empty_cleanup_payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    populated_findings = (
        RepositoryValidationFinding(
            kind=RepositoryFindingKind.MIRROR_UNKNOWN_PATH,
            severity=RepositoryFindingSeverity.HIGH,
            path="unknown|path.txt",
            detail="Unknown\nmirror path.",
            blocker=True,
        ),
    )
    populated_cleanup = (
        repository_validator_module.MirrorCleanupPlanEntry(
            path="unknown/path.txt",
            classification=repository_validator_module.MirrorPathClassification.UNKNOWN,
            canonical_required=False,
            mirror_action=repository_validator_module.MirrorCleanupAction.QUARANTINE_FOR_REVIEW,
            local_action="KEEP_UNTIL_CLASSIFIED",
            risk="MEDIUM",
            approval_required=True,
        ),
    )
    populated_report = repository_validator_module.MirrorHygieneReport(
        policy_id="AI4B-GOV-MIRROR-HYGIENE-001",
        policy_version="1.0.0",
        mirror_manifest_path="runtime/artifacts/repository_validation/mirror-manifest.json",
        analyzed_at_utc="2026-08-24T00:00:00+00:00",
        status=RepositoryValidationStatus.RUNNING_WITH_BLOCKERS,
        mirror_role="NON_CANONICAL_MIRROR",
        mirror_authority="NONE",
        mirror_source_of_truth=False,
        entry_count=1,
        findings=populated_findings,
        cleanup_plan=populated_cleanup,
        blockers=("MIRROR_UNKNOWN_PATH:unknown/path.txt",),
        dashboard_metrics={"mirror_noise_ratio": 1.0},
    )
    populated_markdown = tmp_path / "artifacts" / "mirror-populated.md"
    populated_cleanup_path = tmp_path / "artifacts" / "mirror-populated-cleanup.json"

    repository_validator_module._write_mirror_report_markdown(
        populated_markdown,
        populated_report,
    )
    repository_validator_module._write_mirror_cleanup_plan(
        populated_cleanup_path,
        populated_report,
    )

    populated_markdown_text = populated_markdown.read_text(encoding="utf-8")
    populated_cleanup_payload = json.loads(
        populated_cleanup_path.read_text(encoding="utf-8")
    )

    expected_markdown_line = (
        "`HIGH` `MIRROR_UNKNOWN_PATH` `unknown\\|path.txt` - Unknown mirror path."
    )
    assert expected_markdown_line in populated_markdown_text
    assert populated_cleanup_payload["cleanup_plan"][0]["mirror_action"] == (
        "QUARANTINE_FOR_REVIEW"
    )
    assert populated_cleanup_payload["cleanup_plan"][0]["approval_required"] is True


def test_repository_validator_mirror_cli_quiet_and_exit_code_branches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy_path = tmp_path / repository_validator_module.REPOSITORY_MIRROR_POLICY_PATH
    _write_mirror_policy(policy_path)

    pass_manifest = tmp_path / "mirror-pass.json"
    _write_json(
        pass_manifest,
        {
            "entries": [
                "src/ai4binance/module.py",
                "tests/test_module.py",
                "docs/guide.md",
            ]
        },
    )

    quiet_exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--check-mirror-manifest",
            str(pass_manifest),
            "--quiet",
        ]
    )
    quiet_stdout = capsys.readouterr().out
    assert quiet_exit_code == 0
    assert quiet_stdout == ""

    blocker_manifest = tmp_path / "mirror-blocker.json"
    _write_json(
        blocker_manifest,
        {
            "entries": [
                "unknown/path.bin",
                {"path": "docs/guide.md", "source_of_truth": True},
            ]
        },
    )
    blocker_output = tmp_path / "artifacts" / "mirror-blocker.json"

    blocker_exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--check-mirror-manifest",
            str(blocker_manifest),
            "--output-json",
            str(blocker_output),
        ]
    )
    blocker_stdout = capsys.readouterr().out
    blocker_payload = json.loads(blocker_output.read_text(encoding="utf-8"))

    assert blocker_exit_code == 2
    assert '"status": "RUNNING_WITH_BLOCKERS"' in blocker_stdout
    assert blocker_payload["status"] == "RUNNING_WITH_BLOCKERS"
    assert "MIRROR_UNKNOWN_PATH:unknown/path.bin" in blocker_payload["blockers"]
    assert (
        "MIRROR_SOURCE_OF_TRUTH_VIOLATION:docs/guide.md" in blocker_payload["blockers"]
    )


def test_repository_validator_repository_writer_branches(tmp_path: Path) -> None:
    _write_required_knowledge_docs(tmp_path)
    clean_report = validate_repository(tmp_path)

    clean_json = tmp_path / "artifacts" / "repository-clean.json"
    clean_markdown = tmp_path / "artifacts" / "repository-clean.md"
    clean_migration = tmp_path / "artifacts" / "migration-clean.md"

    repository_validator_module._write_report_json(clean_json, clean_report)
    repository_validator_module._write_report_markdown(clean_markdown, clean_report)
    repository_validator_module._write_migration_map_markdown(
        clean_migration,
        clean_report,
    )

    clean_json_payload = json.loads(clean_json.read_text(encoding="utf-8"))
    clean_markdown_text = clean_markdown.read_text(encoding="utf-8")
    clean_migration_text = clean_migration.read_text(encoding="utf-8")

    assert clean_json_payload["status"] == "PASS"
    assert "- No findings." in clean_markdown_text
    assert "- No recommended actions." in clean_markdown_text
    assert "repository_health_score" in clean_markdown_text
    assert (
        "| NO_CHANGE | NO_CHANGE | No migration is currently recommended. |"
        in clean_migration_text
    )

    bad_package = tmp_path / "src" / "ai4binance" / "BadPackage"
    bad_package.mkdir(parents=True)
    (bad_package / "final_v2.py").write_text("VALUE = 1\n", encoding="utf-8")
    (bad_package / "BadName.py").write_text("VALUE = 1\n", encoding="utf-8")
    state = tmp_path / "src" / "ai4binance" / "trading" / "state"
    state.mkdir(parents=True)
    (state / "runtime_state.py").write_text("VALUE = 1\n", encoding="utf-8")

    blocker_report = validate_repository(tmp_path)
    blocker_markdown = tmp_path / "artifacts" / "repository-blocker.md"
    blocker_migration = tmp_path / "artifacts" / "migration-blocker.md"

    repository_validator_module._write_report_markdown(
        blocker_markdown,
        blocker_report,
    )
    repository_validator_module._write_migration_map_markdown(
        blocker_migration,
        blocker_report,
    )

    blocker_markdown_text = blocker_markdown.read_text(encoding="utf-8")
    blocker_migration_text = blocker_migration.read_text(encoding="utf-8")

    assert "`HIGH` `PYTHON_PACKAGE_NAMING_VIOLATION`" in blocker_markdown_text
    assert "`RENAME_REVIEW_REQUIRED`" in blocker_markdown_text
    assert "requires_approval=`True`" in blocker_markdown_text
    assert "Live eligibility remains `LIVE_ORDER_BLOCKED`." in blocker_markdown_text
    assert "src/ai4binance/BadPackage/BadName.py" in blocker_migration_text
    assert "src/ai4binance/BadPackage/bad_name.py" in blocker_migration_text
    assert "runtime/state/governance/runtime_state.py" in blocker_migration_text


def test_repository_validator_repository_cli_quiet_and_output_branches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_required_knowledge_docs(tmp_path)

    quiet_exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--quiet",
        ]
    )
    quiet_stdout = capsys.readouterr().out
    assert quiet_exit_code == 0
    assert quiet_stdout == ""

    output_json = tmp_path / "artifacts" / "repository-cli.json"
    output_markdown = tmp_path / "artifacts" / "repository-cli.md"
    output_migration = tmp_path / "artifacts" / "repository-cli-migration.md"
    output_findings = tmp_path / "artifacts" / "repository-cli-findings.json"
    output_policy_snapshot = tmp_path / "artifacts" / "repository-cli-policy.json"

    output_exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
            "--output-migration-map",
            str(output_migration),
            "--output-findings-json",
            str(output_findings),
            "--output-policy-snapshot",
            str(output_policy_snapshot),
        ]
    )
    output_stdout = capsys.readouterr().out
    output_payload = json.loads(output_json.read_text(encoding="utf-8"))

    assert output_exit_code == 0
    assert '"status": "PASS"' in output_stdout
    assert output_payload["status"] == "PASS"
    assert output_payload["policy_source_path"] == (
        "policies/repository-validator/manifest-policy.json"
    )
    assert output_markdown.is_file()
    assert output_migration.is_file()
    assert output_findings.is_file()
    assert output_policy_snapshot.is_file()

    bad_package = tmp_path / "src" / "ai4binance" / "BadPackage"
    bad_package.mkdir(parents=True)
    (bad_package / "final_v2.py").write_text("VALUE = 1\n", encoding="utf-8")
    (bad_package / "BadName.py").write_text("VALUE = 1\n", encoding="utf-8")
    state = tmp_path / "src" / "ai4binance" / "trading" / "state"
    state.mkdir(parents=True)
    (state / "runtime_state.py").write_text("VALUE = 1\n", encoding="utf-8")

    blocked_output_json = tmp_path / "artifacts" / "repository-cli-blocked.json"
    blocked_output_markdown = tmp_path / "artifacts" / "repository-cli-blocked.md"
    blocked_output_migration = (
        tmp_path / "artifacts" / "repository-cli-blocked-migration.md"
    )

    blocked_exit_code = repository_validator_module.main(
        [
            "--repository-root",
            str(tmp_path),
            "--output-json",
            str(blocked_output_json),
            "--output-markdown",
            str(blocked_output_markdown),
            "--output-migration-map",
            str(blocked_output_migration),
        ]
    )
    blocked_stdout = capsys.readouterr().out
    blocked_payload = json.loads(blocked_output_json.read_text(encoding="utf-8"))

    assert blocked_exit_code == 2
    assert '"status": "RUNNING_WITH_BLOCKERS"' in blocked_stdout
    assert blocked_payload["status"] == "RUNNING_WITH_BLOCKERS"
    assert (
        "PYTHON_PACKAGE_NAMING_VIOLATION:src/ai4binance/BadPackage/BadName.py"
        in blocked_payload["blockers"]
    )
    assert (
        "PYTHON_PACKAGE_NAMING_VIOLATION:src/ai4binance/BadPackage/final_v2.py"
        in blocked_payload["blockers"]
    )
    assert (
        "RUNTIME_STATE_INSIDE_SRC:src/ai4binance/trading/state/runtime_state.py"
        in blocked_payload["blockers"]
    )


def test_repository_validator_repository_reporting_edge_branches(
    tmp_path: Path,
) -> None:
    archive_artifact = RepositoryArtifact(
        artifact_id="archive-artifact",
        artifact_type=RepositoryArtifactType.GOVERNANCE,
        artifact_class=RepositoryArtifactClass.ARCHIVE,
        domain="docs",
        owner="Governance",
        canonical_path="docs/archive/reference_local_computer_profile.md",
        filename="reference_local_computer_profile.md",
        schema_version=None,
        lifecycle_status=RepositoryArtifactLifecycle.DEPRECATED,
        generated=False,
        immutable=False,
        sensitive=False,
        git_tracked=False,
        checksum="a" * 64,
        file_id="archive-artifact",
        path="docs/archive/reference_local_computer_profile.md",
        mime_type="text/markdown",
        size=10,
        modified_time="2026-08-24T00:00:00+00:00",
        authority_layer="L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS",
        observed_expected_layer="L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS",
        authority_basis=(
            "metadata:authority_level=ADVISORY;document_type=REFERENCE;content_role=EVIDENCE;source_of_truth=false",
            "registered_policy:knowledge_metadata_required",
            "canonical_path:verified",
            "validation:governed_metadata_validated",
            "downstream_usage:0",
        ),
        action="ARCHIVE_RECOMMENDED",
        result="ARCHIVE_RECOMMENDED",
        proposed_path="docs/archive/reference_local_computer_profile.md",
    )
    artifact_result = repository_validator_module._artifact_result(
        archive_artifact.action
    )
    no_change_result = repository_validator_module._artifact_result("NO_CHANGE")
    counts = repository_validator_module._result_counts(
        (archive_artifact, replace(archive_artifact, result="COMPLIANT"))
    )

    finding = RepositoryValidationFinding(
        kind=RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID,
        severity=RepositoryFindingSeverity.HIGH,
        path="docs|bad.md",
        detail="Broken\nmetadata entry.",
        blocker=True,
    )
    report = RepositoryValidationReport(
        policy_id="AI4B-GOV-REPO-POLICY",
        policy_version="1.1.0",
        repository_root=str(tmp_path),
        analyzed_at_utc="2026-08-24T00:00:00+00:00",
        analysis_scope="AGGRESSIVE_ALL_FILES",
        status=RepositoryValidationStatus.RUNNING_WITH_BLOCKERS,
        artifacts=(archive_artifact,),
        artifact_count=1,
        governed_knowledge_count=0,
        findings=(finding,),
        blockers=("KNOWLEDGE_METADATA_INVALID:docs|bad.md",),
        recommended_actions=(),
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
        repository_health_score=42,
    )

    markdown_path = tmp_path / "artifacts" / "repository-reporting-edge.md"
    migration_path = tmp_path / "artifacts" / "repository-reporting-edge-migration.md"

    repository_validator_module._write_report_markdown(markdown_path, report)
    repository_validator_module._write_migration_map_markdown(migration_path, report)

    markdown_text = markdown_path.read_text(encoding="utf-8")
    migration_text = migration_path.read_text(encoding="utf-8")
    metrics = repository_validator_module._dashboard_metrics(report)

    assert artifact_result == "ARCHIVE_RECOMMENDED"
    assert no_change_result == "COMPLIANT"
    assert counts["ARCHIVE_RECOMMENDED"] == 1
    assert counts["COMPLIANT"] == 1
    assert metrics["root_clutter_count"] == 0
    assert metrics["stale_document_count"] == 1
    assert metrics["broken_canonical_path_count"] == 1
    assert "`HIGH` `KNOWLEDGE_METADATA_INVALID` `docs|bad.md`: Broken" in markdown_text
    assert "metadata entry." in markdown_text
    assert "- No recommended actions." in markdown_text
    assert "broken_canonical_path_count: `1`" in markdown_text
    assert "docs/archive/reference_local_computer_profile.md" in migration_text
    assert "separate_local_or_historical_context_from_governed_source" in migration_text
    assert "ARCHIVE_RECOMMENDED" in migration_text


def test_repository_validator_report_dataclass_guard_branches(
    tmp_path: Path,
) -> None:
    artifact = RepositoryArtifact(
        artifact_id="artifact-id",
        artifact_type=RepositoryArtifactType.GOVERNANCE,
        artifact_class=RepositoryArtifactClass.GOVERNANCE,
        domain="docs",
        owner="Governance",
        canonical_path="docs/example.md",
        filename="example.md",
        schema_version=None,
        lifecycle_status=RepositoryArtifactLifecycle.ACTIVE,
        generated=False,
        immutable=False,
        sensitive=False,
        git_tracked=False,
        checksum="a" * 64,
        file_id="artifact-id",
        path="docs/example.md",
        mime_type="text/markdown",
        size=10,
        modified_time="2026-08-24T00:00:00+00:00",
        authority_layer="L2_GOVERNANCE_COMPLIANCE",
        observed_expected_layer="L2_GOVERNANCE_COMPLIANCE",
        authority_basis=(
            "metadata:authority_level=ADVISORY;document_type=STANDARD;content_role=AUTHORITATIVE;source_of_truth=false",
            "registered_policy:knowledge_metadata_required",
            "canonical_path:verified",
            "validation:governed_metadata_validated",
            "downstream_usage:0",
        ),
        action="NO_CHANGE",
        result="COMPLIANT",
        proposed_path=None,
    )

    common_kwargs = {
        "repository_root": str(tmp_path),
        "analyzed_at_utc": "2026-08-24T00:00:00+00:00",
        "status": RepositoryValidationStatus.RUNNING_WITH_BLOCKERS,
        "governed_knowledge_count": 1,
        "artifacts": (artifact,),
        "blockers": ("BLOCKER_A",),
        "repository_health_score": 50,
    }

    report = _validation_report(**common_kwargs)
    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS

    with pytest.raises(ValueError, match="validation blockers"):
        _validation_report(**(common_kwargs | {"blockers": ("BLOCKER_A", "BLOCKER_A")}))

    with pytest.raises(
        ValueError, match="passing repository validation cannot contain blockers"
    ):
        _validation_report(
            **(common_kwargs | {"status": RepositoryValidationStatus.PASS})
        )

    with pytest.raises(
        ValueError, match="repository validation cannot authorize execution"
    ):
        _validation_report(**(common_kwargs | {"execution_allowed": True}))

    with pytest.raises(
        ValueError, match="repository validation cannot authorize execution"
    ):
        _validation_report(**(common_kwargs | {"promotion_status": "LIVE_APPROVED"}))

    with pytest.raises(
        ValueError, match="repository validation cannot authorize live trading"
    ):
        _validation_report(
            **(common_kwargs | {"live_eligibility_status": "LIVE_ELIGIBLE"})
        )

    with pytest.raises(ValueError, match=r"repository_health_score must be 0\.\.100"):
        _validation_report(**(common_kwargs | {"repository_health_score": -1}))

    with pytest.raises(ValueError, match=r"repository_health_score must be 0\.\.100"):
        _validation_report(**(common_kwargs | {"repository_health_score": 101}))

    with pytest.raises(ValueError, match="analysis_scope"):
        _validation_report(**(common_kwargs | {"analysis_scope": ""}))


def test_repository_validator_remediation_dataclass_guard_branches() -> None:
    action = _remediation_action()
    assert action.action_type == "FIX_METADATA"

    with pytest.raises(ValueError, match="action_id"):
        _remediation_action(action_id="")

    with pytest.raises(ValueError, match="action_type"):
        _remediation_action(action_type="")

    with pytest.raises(ValueError, match="current_path"):
        _remediation_action(current_path="")

    with pytest.raises(ValueError, match="remediation reason"):
        _remediation_action(reason="")

    with pytest.raises(ValueError, match="evidence_required"):
        _remediation_action(
            evidence_required=(
                "pre_change_validation_report",
                "pre_change_validation_report",
            )
        )

    with pytest.raises(ValueError, match="evidence_required"):
        _remediation_action(evidence_required=("impact_analysis", " "))


def test_repository_validator_mirror_report_dataclass_guard_branches() -> None:
    report = _mirror_hygiene_report()
    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS

    with pytest.raises(
        ValueError, match="mirror reports cannot grant source-of-truth authority"
    ):
        _mirror_hygiene_report(mirror_source_of_truth=True)

    with pytest.raises(
        ValueError, match="passing mirror validation cannot contain blockers"
    ):
        _mirror_hygiene_report(status=RepositoryValidationStatus.PASS)

    with pytest.raises(
        ValueError, match="mirror validation cannot authorize execution"
    ):
        _mirror_hygiene_report(execution_allowed=True)

    with pytest.raises(
        ValueError, match="mirror validation cannot authorize execution"
    ):
        _mirror_hygiene_report(promotion_status="LIVE_APPROVED")

    with pytest.raises(
        ValueError, match="mirror validation cannot authorize live trading"
    ):
        _mirror_hygiene_report(live_eligibility_status="LIVE_ELIGIBLE")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda policy: replace(policy, mirror_role="AUTHORITATIVE"),
            "mirror role must be NON_CANONICAL_MIRROR",
        ),
        (
            lambda policy: replace(policy, mirror_authority="REPOSITORY"),
            "mirror authority must be NONE",
        ),
        (
            lambda policy: replace(policy, may_be_source_of_truth=True),
            "mirror policy cannot grant repository authority",
        ),
        (
            lambda policy: replace(policy, may_override_canonical=True),
            "mirror policy cannot grant repository authority",
        ),
        (
            lambda policy: replace(policy, default_action="ALLOW"),
            "mirror policy must be allowlist-first",
        ),
    ],
)
def test_repository_validator_mirror_policy_dataclass_guard_branches(
    mutate: Callable[
        [repository_validator_module.RepositoryMirrorPolicy],
        repository_validator_module.RepositoryMirrorPolicy,
    ],
    message: str,
) -> None:
    policy = repository_validator_module.RepositoryMirrorPolicy.ai4binance_vnext()

    with pytest.raises(ValueError, match=message):
        mutate(policy)


def test_repository_validator_remaining_helper_decision_branches() -> None:
    assert (
        repository_validator_module._yaml_string({"policy_id": "X"}, "policy_id") == "X"
    )
    assert repository_validator_module._yaml_bool({"flag": True}, "flag") is True
    assert tuple(
        repository_validator_module._mirror_inventory_entries(["docs/list-entry.md"])
    ) == (repository_validator_module.MirrorInventoryEntry(path="docs/list-entry.md"),)
    assert tuple(
        repository_validator_module._mirror_inventory_entries(
            {"paths": ["docs/guide.md"]}
        )
    ) == (repository_validator_module.MirrorInventoryEntry(path="docs/guide.md"),)
    assert tuple(
        repository_validator_module._mirror_inventory_entries(
            {"artifacts": ["src/ai4binance/module.py"]}
        )
    ) == (
        repository_validator_module.MirrorInventoryEntry(
            path="src/ai4binance/module.py"
        ),
    )
    assert tuple(
        repository_validator_module._mirror_inventory_entries(
            {"root_inventory": ["config/settings.yaml"]}
        )
    ) == (
        repository_validator_module.MirrorInventoryEntry(path="config/settings.yaml"),
    )

    canonical_entry = repository_validator_module._mirror_inventory_entry(
        {"canonical_path": "./docs//canonical.md/"}
    )
    assert canonical_entry == repository_validator_module.MirrorInventoryEntry(
        path="docs/canonical.md"
    )

    assert (
        repository_validator_module._normalize_mirror_path("./docs//nested/file.md/")
        == "docs/nested/file.md"
    )

    with pytest.raises(ValueError, match="policy_id must be a non-empty string"):
        repository_validator_module._yaml_string({"policy_id": 1}, "policy_id")

    with pytest.raises(ValueError, match="policy_id must be a non-empty string"):
        repository_validator_module._yaml_string({"policy_id": " "}, "policy_id")

    with pytest.raises(ValueError, match="flag must be a boolean"):
        repository_validator_module._yaml_bool({"flag": "true"}, "flag")


def test_repository_validator_top_level_and_blocker_registry_helper_branches(
    tmp_path: Path,
) -> None:
    policy = RepositoryPolicy.ai4binance_vnext()

    missing_registry_findings = tuple(
        repository_validator_module._blocker_registry_findings(tmp_path)
    )
    assert len(missing_registry_findings) == 1
    assert missing_registry_findings[0].kind is (
        RepositoryFindingKind.BLOCKER_REGISTRY_INVALID
    )
    assert (
        "Canonical blocker registry is missing." in missing_registry_findings[0].detail
    )

    _write_blocker_registry(tmp_path)
    blocker_registry_path = tmp_path / BLOCKER_REGISTRY_PATH
    blocker_registry_path.write_text("blocker_definitions: [", encoding="utf-8")
    invalid_registry_findings = tuple(
        repository_validator_module._blocker_registry_findings(tmp_path)
    )
    assert len(invalid_registry_findings) == 1
    assert invalid_registry_findings[0].kind is (
        RepositoryFindingKind.BLOCKER_REGISTRY_INVALID
    )
    assert "failed validation" in invalid_registry_findings[0].detail

    unknown_dir = tmp_path / "scratchpad"
    unknown_dir.mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / ".git").mkdir()
    missing_canonical = tmp_path / "schemas"

    top_level_findings = tuple(
        repository_validator_module._top_level_findings(tmp_path, policy)
    )
    finding_pairs = {(finding.kind, finding.path) for finding in top_level_findings}

    assert (
        RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH,
        "scratchpad",
    ) in finding_pairs
    assert (
        RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH,
        "data",
    ) not in finding_pairs
    assert (
        RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH,
        ".git",
    ) not in finding_pairs
    assert (
        RepositoryFindingKind.CANONICAL_TOP_LEVEL_MISSING,
        missing_canonical.name,
    ) in finding_pairs
    assert all(finding.blocker is False for finding in top_level_findings)


def test_repository_validator_blocks_nonempty_legacy_runtime_root_paths(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    legacy_state = tmp_path / "state"
    legacy_state.mkdir()
    (legacy_state / "runtime.json").write_text("{}", encoding="utf-8")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE
        and finding.path == "state"
        and "runtime/state" in finding.detail
        for finding in report.findings
    )
    assert any(
        action.finding_kind is RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE
        and action.current_path == "state"
        and action.proposed_path == "runtime/state"
        for action in report.recommended_actions
    )


def test_repository_validator_warns_on_empty_legacy_runtime_root_paths(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    empty_legacy_state = tmp_path / "state" / "runtime_research"
    empty_legacy_state.mkdir(parents=True)

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.PASS
    assert not any(
        finding.kind is RepositoryFindingKind.LEGACY_RUNTIME_ROOT_LEAKAGE
        and finding.path == "state"
        for finding in report.findings
    )
    assert any(
        finding.kind is RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH
        and finding.path == "state"
        for finding in report.findings
    )


def test_repository_validator_governed_knowledge_skip_and_missing_file_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required_relative = "docs/required.md"
    optional_relative = "docs/optional.md"
    missing_section_relative = "docs/missing-section.md"
    english_relative = "docs/english-only.md"

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "skip-missing-field.md").write_text(
        "---\n"
        'document_id: ""\n'
        "title: Missing ID\n"
        "document_type: STANDARD\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Governance\n"
        "authority_level: REPOSITORY\n"
        "content_role: OPERATIONAL\n"
        "source_of_truth: false\n"
        "machine_enforceable: false\n"
        "audit_required: true\n"
        "classification: INTERNAL\n"
        "language: en-US\n"
        "---\n\n"
        "# ELI10\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (docs / "skip-invalid-metadata.md").write_text(
        "---\n"
        "document_id: DOC-001\n"
        "title: Invalid Metadata\n"
        "document_type: STANDARD\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Governance\n"
        "authority_level: NOT_REAL\n"
        "authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES\n"
        "authority_scope: invalid_metadata\n"
        "authority_effect: NORMATIVE_CONSTRAINT\n"
        "content_role: OPERATIONAL\n"
        "source_of_truth: false\n"
        "canonical_path: docs/skip-invalid-metadata.md\n"
        "machine_enforceable: false\n"
        "audit_required: true\n"
        "classification: INTERNAL\n"
        "language: en-US\n"
        "---\n\n"
        "# ELI10\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (tmp_path / required_relative).write_text(
        "---\n"
        "document_id: DOC-REQ-001\n"
        "title: Required Doc\n"
        "document_type: STANDARD\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Governance\n"
        "authority_level: REPOSITORY\n"
        "authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES\n"
        "authority_scope: required_doc\n"
        "authority_effect: NORMATIVE_CONSTRAINT\n"
        "content_role: OPERATIONAL\n"
        "source_of_truth: false\n"
        "machine_enforceable: false\n"
        "audit_required: true\n"
        "classification: INTERNAL\n"
        "language: en-US\n"
        "---\n\n"
        "# ELI10\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (tmp_path / missing_section_relative).write_text(
        "# Wrong Section\n\nStill English.\n",
        encoding="utf-8",
    )
    (tmp_path / english_relative).write_text(
        "# ELI10\n\nsistem\n",
        encoding="utf-8",
    )

    knowledge_findings = tuple(
        repository_validator_module._knowledge_findings(
            tmp_path,
            RepositoryPolicy.ai4binance_vnext(),
        )
    )
    knowledge_pairs = {(finding.kind, finding.path) for finding in knowledge_findings}
    assert (
        RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
        "docs/skip-missing-field.md",
    ) in knowledge_pairs
    assert (
        RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID,
        "docs/skip-invalid-metadata.md",
    ) in knowledge_pairs
    assert (
        RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
        missing_section_relative,
    ) in knowledge_pairs
    assert (
        RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING,
        optional_relative,
    ) not in knowledge_pairs

    monkeypatch.setattr(
        repository_validator_module,
        "_governed_markdown_knowledge_paths",
        lambda _: (optional_relative,),
    )
    skipped_optional_findings = tuple(
        repository_validator_module._knowledge_findings(
            tmp_path,
            RepositoryPolicy.ai4binance_vnext(),
        )
    )
    assert not any(
        finding.path == optional_relative for finding in skipped_optional_findings
    )

    section_policy = replace(
        RepositoryPolicy.ai4binance_vnext(),
        knowledge_section_requirements={
            missing_section_relative: ("ELI10",),
            "docs/absent-section.md": ("ELI10",),
        },
        english_only_knowledge_paths=(english_relative, "docs/absent-english.md"),
    )
    section_findings = tuple(
        repository_validator_module._knowledge_required_section_findings(
            tmp_path,
            section_policy,
        )
    )
    assert len(section_findings) == 1
    assert section_findings[0].path == missing_section_relative

    english_findings = tuple(
        repository_validator_module._english_only_knowledge_findings(
            tmp_path,
            section_policy,
        )
    )
    assert len(english_findings) == 1
    assert english_findings[0].path == english_relative


def test_repository_validator_git_tracked_files_fail_closed_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert repository_validator_module._git_tracked_files(tmp_path) == set()
    assert repository_validator_module._git_has_head(tmp_path) is False

    monkeypatch.setattr(shutil, "which", lambda _: "git")

    def raise_called_process_error(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(1, ("git", "ls-files", "-z"))

    monkeypatch.setattr(subprocess, "run", raise_called_process_error)
    assert repository_validator_module._git_tracked_files(tmp_path) == set()

    def raise_timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(("git", "ls-files", "-z"), timeout=30)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    assert repository_validator_module._git_tracked_files(tmp_path) == set()
    assert repository_validator_module._git_has_head(tmp_path) is False


def test_repository_validator_classification_layer_and_authority_helpers(
    tmp_path: Path,
) -> None:
    policy = RepositoryPolicy.ai4binance_vnext()
    type_cases = {
        "models/model.bin": RepositoryArtifactType.MODEL,
        "tmp/.ruff_cache/report.txt": RepositoryArtifactType.CACHE,
        ".agents/skills/example/SKILL.md": RepositoryArtifactType.GOVERNANCE,
        "docs/contracts/agent_contract_technical_analysis_agents.md": RepositoryArtifactType.GOVERNANCE,
        "README.md": RepositoryArtifactType.GOVERNANCE,
        (
            "docs/standards/"
            "standard_engineering_python_clean_code_vscode_development.md"
        ): RepositoryArtifactType.GOVERNANCE,
        "tools/script.py": RepositoryArtifactType.ARTIFACT,
        "misc/file.bin": RepositoryArtifactType.ARTIFACT,
    }
    for relative, expected in type_cases.items():
        assert repository_validator_module._artifact_type(relative, policy) is expected

    assert (
        repository_validator_module._artifact_class(
            "docs/archive/old.md",
            RepositoryArtifactType.ARCHIVE,
        )
        is RepositoryArtifactClass.ARCHIVE
    )
    assert (
        repository_validator_module._artifact_class(
            ".coverage",
            RepositoryArtifactType.CACHE,
        )
        is RepositoryArtifactClass.CACHE
    )
    assert (
        repository_validator_module._artifact_class(
            "reports/latest.md",
            RepositoryArtifactType.EVIDENCE,
        )
        is RepositoryArtifactClass.REPORT
    )
    assert (
        repository_validator_module._artifact_class(
            "data/sample.csv",
            RepositoryArtifactType.DATA,
        )
        is RepositoryArtifactClass.RUNTIME
    )
    assert (
        repository_validator_module._artifact_class(
            "schemas/schema.json",
            RepositoryArtifactType.SCHEMA,
        )
        is RepositoryArtifactClass.GOVERNANCE
    )
    assert (
        repository_validator_module._artifact_class(
            "src/ai4binance/module.py",
            RepositoryArtifactType.SOURCE_CODE,
        )
        is RepositoryArtifactClass.SOURCE
    )

    markdown = tmp_path / "report.unknown"
    markdown.write_text("text", encoding="utf-8")
    assert repository_validator_module._mime_type(markdown) == (
        "application/octet-stream"
    )
    plain = tmp_path / "README.md"
    plain.write_text("text", encoding="utf-8")
    assert repository_validator_module._mime_type(plain) == "text/markdown"
    factory = tmp_path / "factory"
    factory.mkdir()
    (factory / "guide.md").write_text("# ELI10\n\nBody.\n", encoding="utf-8")
    governed_paths = repository_validator_module._governed_markdown_knowledge_paths(
        tmp_path
    )
    assert "README.md" in governed_paths
    assert "factory/guide.md" in governed_paths
    assert not (tmp_path / "docs").exists()

    metadata_cases = (
        (
            _knowledge_object(
                authority_level=KnowledgeAuthorityLevel.EXTERNAL_AUTHORITY,
                authority_layer="L0_EXTERNAL_MANDATORY_CONSTRAINTS",
                authority_effect=KnowledgeAuthorityEffect.MANDATORY_CONSTRAINT,
            ),
            "L0_EXTERNAL_MANDATORY_CONSTRAINTS",
        ),
        (
            _knowledge_object(
                knowledge_id="AI4B-GOV-OEK-003",
                title="Core Constitution",
                authority_layer="L1_CORE_CONSTITUTION",
            ),
            "L1_CORE_CONSTITUTION",
        ),
        (
            _knowledge_object(
                authority_level=KnowledgeAuthorityLevel.PROVIDER_ADAPTER,
                authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
                authority_effect=KnowledgeAuthorityEffect.OPERATIONAL_SPECIALIZATION,
                authority_scope="provider_adapter_operational",
                content_role=KnowledgeContentRole.OPERATIONAL,
            ),
            "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        ),
        (
            _knowledge_object(
                authority_level=KnowledgeAuthorityLevel.ENFORCEABLE,
                authority_layer="L3_CANONICAL_CONTRACTS_SCHEMAS",
                authority_effect=KnowledgeAuthorityEffect.IMPLEMENTATION,
            ),
            "L3_CANONICAL_CONTRACTS_SCHEMAS",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.SCHEMA,
                authority_layer="L3_CANONICAL_CONTRACTS_SCHEMAS",
                content_role=KnowledgeContentRole.OPERATIONAL,
            ),
            "L3_CANONICAL_CONTRACTS_SCHEMAS",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.ENTITY_RULE,
                authority_layer="L6_ARCHITECTURE_ONTOLOGY_ADR",
                content_role=KnowledgeContentRole.AUTHORITATIVE,
            ),
            "L6_ARCHITECTURE_ONTOLOGY_ADR",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.INSTRUCTION,
                authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
                authority_effect=KnowledgeAuthorityEffect.OPERATIONAL_SPECIALIZATION,
                authority_scope="instruction_fixture",
                content_role=KnowledgeContentRole.OPERATIONAL,
            ),
            "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.POLICY,
                authority_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
                content_role=KnowledgeContentRole.OPERATIONAL,
            ),
            "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.REGISTRY,
                authority_layer="L5_REGISTRIES_ROADMAP",
                content_role=KnowledgeContentRole.OPERATIONAL,
            ),
            "L5_REGISTRIES_ROADMAP",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.ADR,
                authority_layer="L6_ARCHITECTURE_ONTOLOGY_ADR",
                content_role=KnowledgeContentRole.AUTHORITATIVE,
            ),
            "L6_ARCHITECTURE_ONTOLOGY_ADR",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.EVIDENCE_REQUIREMENT,
                authority_layer="L8_REPORTS_EVIDENCE_INVENTORIES",
                authority_effect=KnowledgeAuthorityEffect.EVIDENCE_ONLY,
                content_role=KnowledgeContentRole.EVIDENCE,
                source_of_truth=False,
            ),
            "L8_REPORTS_EVIDENCE_INVENTORIES",
        ),
        (
            _knowledge_object(
                knowledge_type=KnowledgeObjectType.REFERENCE,
                authority_layer="L9_REFERENCES_TEMPLATES",
                authority_effect=KnowledgeAuthorityEffect.REFERENCE_ONLY,
                content_role=KnowledgeContentRole.OPERATIONAL,
                source_of_truth=False,
                machine_enforceable=False,
            ),
            "L9_REFERENCES_TEMPLATES",
        ),
        (
            _knowledge_object(
                authority_level=KnowledgeAuthorityLevel.REPOSITORY,
                knowledge_type=KnowledgeObjectType.PROVIDER_ADAPTER,
                authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
                authority_effect=KnowledgeAuthorityEffect.OPERATIONAL_SPECIALIZATION,
                authority_scope="provider_adapter_fixture",
                content_role=KnowledgeContentRole.OPERATIONAL,
            ),
            "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        ),
        (
            _knowledge_object(
                authority_level=KnowledgeAuthorityLevel.ADVISORY,
                knowledge_type=KnowledgeObjectType.PROVIDER_ADAPTER,
                authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
                authority_effect=KnowledgeAuthorityEffect.OPERATIONAL_SPECIALIZATION,
                content_role=KnowledgeContentRole.OPERATIONAL,
                source_of_truth=False,
                machine_enforceable=False,
            ),
            "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        ),
    )
    for metadata, expected_layer in metadata_cases:
        assert (
            repository_validator_module._metadata_authority_layer(metadata)
            == expected_layer
        )

    placement_cases = {
        "docs/governance/policy_organization_constitution_handbook.md": (
            "L1_CORE_CONSTITUTION"
        ),
        "AGENTS.md": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "README.md": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "docs/providers/instruction_codex_provider.md": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "docs/providers/example.md": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "docs/governance/example.md": "L2_GOVERNANCE_COMPLIANCE",
        "schemas/example.json": "L3_CANONICAL_CONTRACTS_SCHEMAS",
        "docs/standards/example.md": (
            "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES"
        ),
        "docs/registries/example.md": "L5_REGISTRIES_ROADMAP",
        "docs/roadmap/example.md": "L5_REGISTRIES_ROADMAP",
        "ontology/example.yaml": "L6_ARCHITECTURE_ONTOLOGY_ADR",
        "docs/architecture/example.md": "L6_ARCHITECTURE_ONTOLOGY_ADR",
        "docs/workflows/example.md": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "docs/other.md": "L2_GOVERNANCE_COMPLIANCE",
        "src/ai4binance/example.py": "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "runtime/logs/runtime.log": "L8_REPORTS_EVIDENCE_INVENTORIES",
        "docs/references/example.md": "L9_REFERENCES_TEMPLATES",
        "docs/templates/example.md": "L9_REFERENCES_TEMPLATES",
        "misc/file.bin": "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS",
    }
    for relative, expected_layer in placement_cases.items():
        artifact_type = repository_validator_module._artifact_type(relative, policy)
        assert (
            repository_validator_module._policy_placement_layer(
                relative,
                artifact_type,
            )
            == expected_layer
        )
    assert (
        repository_validator_module._policy_placement_layer(
            "archive/old.zip",
            RepositoryArtifactType.ARCHIVE,
        )
        == "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"
    )

    absent = repository_validator_module.AuthorityEvidence(
        metadata=None,
        registered_policy=False,
        canonical_path_verified=False,
        downstream_usage_count=3,
    )
    present = repository_validator_module.AuthorityEvidence(
        metadata=_knowledge_object(),
        registered_policy=True,
        canonical_path_verified=True,
        downstream_usage_count=1,
    )
    assert repository_validator_module._authority_basis(
        absent,
        observed_expected_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
    ) == (
        "metadata:missing",
        "registered_policy:repository_policy",
        "canonical_path:invalid",
        "validation:authority_metadata_missing",
        "validation:placement_hint_only",
        "placement_hint:L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        "downstream_usage:3",
    )
    assert repository_validator_module._authority_basis(
        present,
        observed_expected_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
    )[0] == (
        "metadata:authority_layer="
        "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES;"
        "authority_effect=NORMATIVE_CONSTRAINT;"
        "authority_scope=repository_file_governance;"
        "authority_level_legacy=NORMATIVE;"
        "document_type=STANDARD;"
        "content_role=AUTHORITATIVE;"
        "source_of_truth=true"
    )
    assert repository_validator_module._authority_basis(
        present,
        observed_expected_layer="L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
    )[1:] == (
        "registered_policy:knowledge_metadata_required",
        "canonical_path:verified",
        "validation:governed_metadata_validated",
        "validation:placement_hint_only",
        "placement_hint:L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        "downstream_usage:1",
    )

    assert (
        repository_validator_module._artifact_action(
            "docs/archive/reference_local_computer_profile.md",
            RepositoryArtifactType.GOVERNANCE,
            "docs/archive/reference_local_computer_profile.md",
        )
        == "ARCHIVE_RECOMMENDED"
    )
    assert (
        repository_validator_module._artifact_action(
            ".coverage",
            RepositoryArtifactType.CACHE,
            None,
        )
        == "ARCHIVE_RECOMMENDED"
    )
    assert (
        repository_validator_module._proposed_artifact_path(
            "clean_codes.md",
            policy,
        )
        == "docs/standards/standard_engineering_python_clean_code_vscode_development.md"
    )
    assert (
        repository_validator_module._artifact_action(
            "clean_codes.md",
            RepositoryArtifactType.ARTIFACT,
            "docs/standards/standard_engineering_python_clean_code_vscode_development.md",
        )
        == "MOVE_RECOMMENDED"
    )
    assert repository_validator_module._artifact_result("NO_CHANGE") == "COMPLIANT"
    archive_artifact = _repository_artifact(
        artifact_type=RepositoryArtifactType.GOVERNANCE,
        action="ARCHIVE_RECOMMENDED",
        authority_basis=(
            "metadata:authority_layer="
            "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES;"
            "authority_effect=NORMATIVE_CONSTRAINT;"
            "authority_scope=repository_file_governance;"
            "authority_level_legacy=NORMATIVE;"
            "document_type=STANDARD;"
            "content_role=AUTHORITATIVE;"
            "source_of_truth=true",
        ),
    )
    move_artifact = _repository_artifact(
        artifact_type=RepositoryArtifactType.GOVERNANCE,
        action="MOVE_RECOMMENDED",
        authority_basis=(),
    )
    mixed_basis_artifact = _repository_artifact(
        artifact_type=RepositoryArtifactType.ARTIFACT,
        authority_basis=(
            "registered_policy:knowledge_metadata_required",
            "metadata:authority_layer=L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS;"
            "authority_effect=EVIDENCE_ONLY;"
            "authority_scope=artifact_fixture;"
            "authority_level_legacy=ADVISORY;"
            "document_type=STANDARD;"
            "content_role=OPERATIONAL;"
            "source_of_truth=false",
        ),
    )
    assert repository_validator_module._migration_reason(archive_artifact) == (
        "separate_local_or_historical_context_from_governed_source"
    )
    assert repository_validator_module._migration_reason(move_artifact) == (
        "normalize_governed_document_path_to_document_type_domain_subject"
    )
    assert repository_validator_module._artifact_authority_level(archive_artifact) == (
        "NORMATIVE"
    )
    assert repository_validator_module._artifact_authority_level(move_artifact) == (
        "NORMATIVE"
    )
    assert repository_validator_module._artifact_authority_level(
        mixed_basis_artifact
    ) == ("ADVISORY")
    assert (
        repository_validator_module._artifact_authority_level(
            _repository_artifact(
                artifact_type=RepositoryArtifactType.ARTIFACT,
                authority_basis=("registered_policy:knowledge_metadata_required",),
            )
        )
        == "REPOSITORY"
    )
    assert repository_validator_module._migration_risk(archive_artifact) == (
        "LOW_WITH_REVIEW"
    )
    assert repository_validator_module._migration_risk(move_artifact) == (
        "REFERENCE_UPDATE_REQUIRED"
    )
    assert repository_validator_module._owner("src/ai4binance/example.py", policy) == (
        "Engineering"
    )
    assert repository_validator_module._owner("unknown/file.txt", policy) == (
        "RepositoryGovernance"
    )
    assert repository_validator_module._domain("src/ai4binance/governance/file.py") == (
        "governance"
    )
    assert repository_validator_module._domain("README.md") == "README.md"
    assert repository_validator_module._is_immutable(
        "artifacts/evidence.json",
        RepositoryArtifactType.EVIDENCE,
    )
    assert repository_validator_module._is_sensitive("secrets/key.txt", policy)
    assert repository_validator_module._is_under("src/ai4binance/x.py", ("src",))


def test_repository_policy_artifact_schema_and_validator_pass_for_governed_layout(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_validator.py").write_text(
        "from pathlib import Path\n\nROOT = Path(__file__).resolve()\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_repository_validator.py").write_text(
        "def test_contract():\n    assert True\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_required_knowledge_docs(tmp_path)

    policy = RepositoryPolicy.ai4binance_vnext()
    report = validate_repository(tmp_path, policy=policy)

    assert policy.policy_id == "AI4B-GOV-REPO-POLICY"
    assert policy.non_code_content_language == "en-US"
    assert report.status is RepositoryValidationStatus.PASS
    assert report.blockers == ()
    assert report.artifact_count == 22
    assert report.analyzed_at_utc
    assert report.analysis_scope == "AGGRESSIVE_ALL_FILES"
    assert len(report.artifacts) == report.artifact_count
    assert {action.current_path for action in report.recommended_actions} == set()
    assert {artifact.canonical_path for artifact in report.artifacts} >= {
        "AGENTS.md",
        "docs/providers/instruction_codex_provider.md",
        "docs/standards/standard_repository_file_governance.md",
        "src/ai4binance/governance/repository_validator.py",
    }
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.repository_health_score == 100
    payload = report.to_payload()
    assert payload["allowed_results"] == (
        "COMPLIANT",
        "WARNING",
        "BLOCKER",
        "MOVE_RECOMMENDED",
        "ARCHIVE_RECOMMENDED",
        "QUARANTINE_REQUIRED",
        "NO_CHANGE",
    )
    dashboard_metrics = cast(dict[str, object], payload["dashboard_metrics"])
    assert dashboard_metrics["unresolved_governance_blocker_count"] == 0
    artifacts = cast(list[dict[str, object]], payload["artifacts"])
    first_artifact = artifacts[0]
    assert {
        "file_id",
        "path",
        "mime_type",
        "size",
        "modified_time",
        "owner",
        "shared_status",
        "artifact_type",
        "artifact_class",
        "authority_layer",
        "authority_effect",
        "authority_scope",
        "observed_expected_layer",
        "authority_basis",
        "action",
        "result",
        "source_of_truth",
        "machine_enforceable",
        "audit_required",
        "classification",
    } <= set(first_artifact)

    artifact = RepositoryArtifact(
        artifact_id="artifact-id",
        artifact_type=RepositoryArtifactType.SOURCE_CODE,
        artifact_class=RepositoryArtifactClass.SOURCE,
        domain="governance",
        owner="Engineering",
        canonical_path="src/ai4binance/governance/repository_validator.py",
        filename="repository_validator.py",
        schema_version="1.0.0",
        lifecycle_status=RepositoryArtifactLifecycle.ACTIVE,
        generated=False,
        immutable=False,
        sensitive=False,
        git_tracked=False,
        checksum="a" * 64,
    )
    assert artifact.artifact_type is RepositoryArtifactType.SOURCE_CODE
    assert artifact.artifact_class is RepositoryArtifactClass.SOURCE

    with pytest.raises(
        ValueError,
        match="authority_layer must use the canonical authority pyramid",
    ):
        RepositoryArtifact(
            artifact_id="bad-layer",
            artifact_type=RepositoryArtifactType.SOURCE_CODE,
            artifact_class=RepositoryArtifactClass.SOURCE,
            domain="governance",
            owner="Engineering",
            canonical_path="src/ai4binance/governance/repository_validator.py",
            filename="repository_validator.py",
            schema_version="1.0.0",
            lifecycle_status=RepositoryArtifactLifecycle.ACTIVE,
            generated=False,
            immutable=False,
            sensitive=False,
            git_tracked=False,
            checksum="a" * 64,
            authority_layer="L7_CODE_CONFIGURATION",
        )


def test_repository_validator_uses_metadata_driven_authority_layer(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    reference_path = tmp_path / "docs" / "references" / "reference_exchange_terms.md"
    _write_governed_doc(
        reference_path,
        document_id="AI4B-EXT-REG-999",
        title="AI4BINANCE Exchange Terms Reference",
        document_type="REGULATION",
        authority_level="EXTERNAL_AUTHORITY",
        authority_layer="L0_EXTERNAL_MANDATORY_CONSTRAINTS",
        authority_effect="MANDATORY_CONSTRAINT",
        canonical_path="docs/references/reference_exchange_terms.md",
        extra_frontmatter=(
            "external_constraint_id: AI4B-EXT-BINANCE-TERMS-001",
            "source_uri: https://example.com/binance-terms",
            "jurisdiction_or_provider: binance",
            "effective_version: 2026-08-30",
            "effective_date: 2026-08-30",
            "retrieved_at: 2026-08-30T12:00:00Z",
            f"content_hash: {'a' * 64}",
            "validation_status: VERIFIED",
            "affected_objects: spot_orders,futures_orders",
        ),
    )
    with (tmp_path / "README.md").open("a", encoding="utf-8") as handle:
        handle.write("\nSee `docs/references/reference_exchange_terms.md`.\n")

    report = validate_repository(tmp_path)
    artifact = next(
        item
        for item in report.artifacts
        if item.canonical_path == "docs/references/reference_exchange_terms.md"
    )

    assert report.status is RepositoryValidationStatus.PASS
    assert artifact.authority_layer == "L0_EXTERNAL_MANDATORY_CONSTRAINTS"
    assert artifact.source_of_truth is True
    assert artifact.machine_enforceable is True
    assert artifact.audit_required is True
    assert artifact.classification is KnowledgeClassification.INTERNAL
    assert artifact.observed_expected_layer == "L9_REFERENCES_TEMPLATES"
    assert any(
        basis.startswith("metadata:authority_layer=L0_EXTERNAL_MANDATORY_CONSTRAINTS;")
        and "authority_level_legacy=EXTERNAL_AUTHORITY;" in basis
        for basis in artifact.authority_basis
    )
    assert "canonical_path:verified" in artifact.authority_basis
    assert "validation:governed_metadata_validated" in artifact.authority_basis
    assert "downstream_usage:1" in artifact.authority_basis


def test_repository_validator_requires_external_constraint_envelope_for_l0_authority(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    reference_path = tmp_path / "docs" / "references" / "reference_exchange_terms.md"
    _write_governed_doc(
        reference_path,
        document_id="AI4B-EXT-REG-999",
        title="AI4BINANCE Exchange Terms Reference",
        document_type="REGULATION",
        authority_level="EXTERNAL_AUTHORITY",
        authority_layer="L0_EXTERNAL_MANDATORY_CONSTRAINTS",
        authority_effect="MANDATORY_CONSTRAINT",
        canonical_path="docs/references/reference_exchange_terms.md",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = [
        finding
        for finding in report.findings
        if finding.path == "docs/references/reference_exchange_terms.md"
    ]
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING
        and "external_constraint_id" in finding.detail
        and "source_uri" in finding.detail
        and "validation_status" in finding.detail
        and "affected_objects" in finding.detail
        for finding in findings
    )


def test_repository_validator_requires_explicit_operational_authority_metadata(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    workflow_path = (
        tmp_path / "docs" / "workflows" / "instruction_explicit_authority_metadata.md"
    )
    _write_governed_doc(
        workflow_path,
        document_id="AI4B-GOV-INS-EXPLICIT-001",
        title="AI4BINANCE Explicit Operational Authority Metadata",
    )

    content = workflow_path.read_text(encoding="utf-8")
    for line in (
        "authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS\n",
        "authority_scope: explicit_authority_metadata\n",
        "authority_effect: OPERATIONAL_SPECIALIZATION\n",
    ):
        content = content.replace(line, "")
    content = content.replace(
        "source_of_truth_scope: explicit_authority_metadata_workflow\n",
        "source_of_truth_scope: canonical\n",
    )
    workflow_path.write_text(content, encoding="utf-8")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    findings = [
        finding
        for finding in report.findings
        if finding.path == "docs/workflows/instruction_explicit_authority_metadata.md"
    ]
    assert findings
    assert {
        finding.detail
        for finding in findings
        if finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING
    } == {
        "Governed knowledge metadata missing fields: authority_layer, authority_scope, authority_effect.",
    }


def test_repository_validator_reports_no_migration_map_for_canonical_docs(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    report = validate_repository(tmp_path)
    payload = report.to_payload()
    migration_map = cast(list[dict[str, Any]], payload["migration_map"])
    assert all(
        not str(entry["source_path"]).startswith("docs/") for entry in migration_map
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_docs_markdown_does_not_reference_stale_template_path() -> (
    None
):
    assert stale_knowledge_template_offenders(ROOT) == []


def test_repository_validator_allows_runtime_top_level_without_warning(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)

    report = validate_repository(tmp_path)

    assert not any(
        finding.kind is RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH
        and finding.path == "runtime"
        for finding in report.findings
    )
    assert "runtime" in RepositoryPolicy.ai4binance_vnext().allowed_top_level_paths
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_ignores_temporary_top_level_directories(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    (tmp_path / ".tmp").mkdir()
    (tmp_path / ".tmp-alias-check").mkdir()

    report = validate_repository(tmp_path)

    assert not any(
        finding.kind is RepositoryFindingKind.UNKNOWN_TOP_LEVEL_PATH
        and finding.path in {".tmp", ".tmp-alias-check"}
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_unsafe_source_and_runtime_state_layout(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    bad_package = tmp_path / "src" / "ai4binance" / "BadPackage"
    bad_package.mkdir(parents=True)
    (bad_package / "final_v2.py").write_text("VALUE = 1\n", encoding="utf-8")
    (bad_package / "BadName.py").write_text("VALUE = 1\n", encoding="utf-8")
    state = tmp_path / "src" / "ai4binance" / "trading" / "state"
    state.mkdir(parents=True)
    (state / "runtime_state.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = validate_repository(tmp_path)
    finding_kinds = {finding.kind for finding in report.findings}

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION in finding_kinds
    assert RepositoryFindingKind.PYTHON_FILE_NAMING_VIOLATION in finding_kinds
    assert RepositoryFindingKind.SOURCE_VERSION_FILENAME in finding_kinds
    assert RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC in finding_kinds
    assert report.blockers
    assert report.recommended_actions
    assert all(action.current_path for action in report.recommended_actions)
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_disposable_generated_artifacts_inside_src(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    package = tmp_path / "src" / "ai4binance"
    package.mkdir(parents=True, exist_ok=True)
    tracked_source = package / "tracked_source.py"
    tracked_source.write_text("VALUE = 1\n", encoding="utf-8")
    if not _git_commit_all(tmp_path):
        pytest.skip("git is unavailable for tracked source distinction")

    pycache = package / "__pycache__"
    pycache.mkdir()
    (pycache / "tracked_source.cpython-312.pyc").write_bytes(b"\0\0")
    (pycache / "BadName.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "compiled.pyc").write_bytes(b"\0\0")
    egg_info = tmp_path / "src" / "ai4binance.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("Metadata-Version: 2.1\n", encoding="utf-8")
    runtime = package / "runtime"
    runtime.mkdir()
    (runtime / "latest.json").write_text('{"status": "generated"}\n', encoding="utf-8")

    report = validate_repository(tmp_path)
    artifacts_by_path = {
        artifact.canonical_path: artifact for artifact in report.artifacts
    }
    generated_finding_paths = {
        finding.path
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC
    }
    runtime_finding_paths = {
        finding.path
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.RUNTIME_STATE_INSIDE_SRC
    }
    disposable_paths = {
        "src/ai4binance/__pycache__/tracked_source.cpython-312.pyc",
        "src/ai4binance/__pycache__/BadName.py",
        "src/ai4binance/compiled.pyc",
        "src/ai4binance.egg-info/PKG-INFO",
    }

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert disposable_paths <= generated_finding_paths
    assert "src/ai4binance/runtime/latest.json" in runtime_finding_paths
    assert artifacts_by_path["src/ai4binance/tracked_source.py"].git_tracked is True
    assert artifacts_by_path["src/ai4binance/tracked_source.py"].generated is False
    for disposable_path in disposable_paths:
        artifact = artifacts_by_path[disposable_path]
        assert artifact.git_tracked is False
        assert artifact.generated is True
        assert artifact.artifact_type is RepositoryArtifactType.CACHE
    runtime_artifact = artifacts_by_path["src/ai4binance/runtime/latest.json"]
    assert runtime_artifact.git_tracked is False
    assert runtime_artifact.generated is True
    assert runtime_artifact.artifact_type is RepositoryArtifactType.RUNTIME
    generated_findings = tuple(
        finding
        for finding in report.findings
        if finding.path in disposable_paths
        and finding.kind is RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC
    )
    package_naming_paths = {
        finding.path
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.PYTHON_PACKAGE_NAMING_VIOLATION
    }
    assert "src/ai4binance/__pycache__/BadName.py" not in package_naming_paths
    rerun = validate_repository(tmp_path)
    rerun_ids = {
        finding.path: finding.finding_id
        for finding in rerun.findings
        if finding.path in disposable_paths
        and finding.kind is RepositoryFindingKind.GENERATED_ARTIFACT_INSIDE_SRC
    }
    assert {finding.path: finding.finding_id for finding in generated_findings} == (
        rerun_ids
    )
    assert all(finding.finding_id.startswith("RFG-") for finding in generated_findings)
    payload = report.to_payload()
    payload_findings = cast(list[dict[str, object]], payload["findings"])
    assert all("finding_id" in finding for finding in payload_findings)
    assert all(finding.blocker for finding in generated_findings)
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_allows_canonical_layer_dependencies(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    package_root = tmp_path / "src" / "ai4binance"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "domain.py").write_text(
        "from ai4binance.core import contracts\n",
        encoding="utf-8",
    )
    (package_root / "core").mkdir()
    (package_root / "core" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "core" / "contracts.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (package_root / "application").mkdir()
    (package_root / "application" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "application" / "service.py").write_text(
        "from ai4binance import domain\nfrom ai4binance.core import contracts\n",
        encoding="utf-8",
    )
    (package_root / "infrastructure").mkdir()
    (package_root / "infrastructure" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "infrastructure" / "gateway.py").write_text(
        "from ai4binance.application import service\nfrom ai4binance import domain\n",
        encoding="utf-8",
    )
    (package_root / "integrations").mkdir()
    (package_root / "integrations" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "integrations" / "provider.py").write_text(
        (
            "from ai4binance.application import service\n"
            "from ai4binance.core import contracts\n"
            "from ai4binance.domain import universe\n"
        ),
        encoding="utf-8",
    )
    (package_root / "cli.py").write_text(
        (
            "from ai4binance.infrastructure import gateway\n"
            "from ai4binance.integrations import provider\n"
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert not any(
        finding.kind is RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_allows_only_declared_compatibility_imports(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    package_root = tmp_path / "src" / "ai4binance"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "application").mkdir()
    (package_root / "application" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "application" / "facade.py").write_text(
        "from ai4binance.compatibility.adapter import VALUE\n",
        encoding="utf-8",
    )
    (package_root / "compatibility").mkdir()
    (package_root / "compatibility" / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )
    (package_root / "compatibility" / "adapter.py").write_text(
        "from ai4binance.legacy.service import VALUE\n",
        encoding="utf-8",
    )
    (package_root / "legacy").mkdir()
    (package_root / "legacy" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "legacy" / "service.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    declared_policy = replace(
        RepositoryPolicy.ai4binance_vnext(),
        compatibility_imports={
            "ai4binance.application.facade": ("ai4binance.compatibility.adapter",),
            "ai4binance.compatibility.adapter": ("ai4binance.legacy.service",),
        },
    )

    report = validate_repository(tmp_path, policy=declared_policy)

    assert not any(
        finding.kind is RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION
        for finding in report.findings
    )
    undeclared_policy = replace(
        declared_policy,
        compatibility_imports={
            "ai4binance.application.facade": ("ai4binance.compatibility.adapter",),
        },
    )
    undeclared_report = validate_repository(tmp_path, policy=undeclared_policy)
    assert any(
        finding.path == "src/ai4binance/compatibility/adapter.py"
        and finding.kind is RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION
        for finding in undeclared_report.findings
    )


def test_repository_validator_blocks_canonical_import_boundary_violations(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    package_root = tmp_path / "src" / "ai4binance"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "domain.py").write_text(
        "from ai4binance.application import service\n",
        encoding="utf-8",
    )
    (package_root / "application").mkdir()
    (package_root / "application" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "application" / "service.py").write_text(
        "from ai4binance.integrations import provider\n",
        encoding="utf-8",
    )
    (package_root / "integrations").mkdir()
    (package_root / "integrations" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "integrations" / "provider.py").write_text(
        "from ai4binance.cli import main\n",
        encoding="utf-8",
    )
    (package_root / "cli.py").write_text(
        "def main() -> int:\n    return 0\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)
    findings = [
        finding
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.CANONICAL_IMPORT_BOUNDARY_VIOLATION
    ]
    finding_paths = {finding.path for finding in findings}

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert finding_paths == {
        "src/ai4binance/domain.py",
        "src/ai4binance/application/service.py",
        "src/ai4binance/integrations/provider.py",
    }
    assert any(
        "Canonical layer 'domain' may depend only on core, domain" in finding.detail
        for finding in findings
        if finding.path == "src/ai4binance/domain.py"
    )
    assert any(
        "ai4binance.application (application)" in finding.detail
        for finding in findings
        if finding.path == "src/ai4binance/domain.py"
    )
    assert any(
        "ai4binance.integrations (integrations)" in finding.detail
        for finding in findings
        if finding.path == "src/ai4binance/application/service.py"
    )
    assert any(
        "ai4binance.cli (cli)" in finding.detail
        for finding in findings
        if finding.path == "src/ai4binance/integrations/provider.py"
    )
    assert all(finding.blocker for finding in findings)
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_opportunity_module_ownership_ambiguity(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    package_root = tmp_path / "src" / "ai4binance"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "opportunities.py").write_text(
        (
            "import json\n"
            "from pathlib import Path\n\n"
            "class VWAPOpportunity:\n"
            "    pass\n\n"
            "class VWAPOpportunityConfig:\n"
            "    pass\n\n"
            "class VWAPOpportunityEvaluator:\n"
            "    pass\n\n"
            "class OpportunityInboxItem:\n"
            "    pass\n\n"
            "class OpportunityInbox:\n"
            "    pass\n\n"
            "class OpportunityInboxBuilder:\n"
            "    def build(self, path: Path) -> dict[str, object]:\n"
            '        return json.loads(path.read_text(encoding="utf-8"))\n'
        ),
        encoding="utf-8",
    )
    (package_root / "opportunity_radar.py").write_text(
        (
            "from pathlib import Path\n\n"
            "def build_opportunity_radar_snapshot() -> dict[str, object]:\n"
            '    return {"status": "READY"}\n\n'
            "def write_opportunity_radar_snapshot(path: Path) -> Path:\n"
            '    path.write_text("{}", encoding="utf-8")\n'
            "    return path\n"
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)
    findings = [
        finding
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.CANONICAL_LAYER_OWNERSHIP_AMBIGUITY
    ]

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert {finding.path for finding in findings} == {
        "src/ai4binance/opportunities.py",
        "src/ai4binance/opportunity_radar.py",
    }
    assert any(
        "domain opportunity observation contracts" in finding.detail
        for finding in findings
        if finding.path == "src/ai4binance/opportunities.py"
    )
    assert any(
        "application radar assembly with local artifact persistence" in finding.detail
        for finding in findings
        if finding.path == "src/ai4binance/opportunity_radar.py"
    )
    assert all(finding.blocker for finding in findings)
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_allows_opportunities_module_without_local_artifact_io(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    package_root = tmp_path / "src" / "ai4binance"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    infrastructure = package_root / "infrastructure"
    infrastructure.mkdir()
    (infrastructure / "__init__.py").write_text("", encoding="utf-8")
    filesystem = infrastructure / "filesystem"
    filesystem.mkdir()
    (filesystem / "__init__.py").write_text(
        (
            "from ai4binance.infrastructure.filesystem."
            "opportunity_artifact_loader import load_optional_json_mapping\n"
        ),
        encoding="utf-8",
    )
    (filesystem / "opportunity_artifact_loader.py").write_text(
        (
            "from collections.abc import Mapping\n"
            "from pathlib import Path\n\n"
            "def load_optional_json_mapping(\n"
            "    path: Path,\n"
            ") -> Mapping[str, object] | None:\n"
            "    return None\n"
        ),
        encoding="utf-8",
    )
    (package_root / "opportunities.py").write_text(
        (
            "from pathlib import Path\n"
            "from ai4binance.infrastructure.filesystem import (\n"
            "    load_optional_json_mapping,\n"
            ")\n\n"
            "class VWAPOpportunity:\n"
            "    pass\n\n"
            "class VWAPOpportunityConfig:\n"
            "    pass\n\n"
            "class VWAPOpportunityEvaluator:\n"
            "    pass\n\n"
            "class OpportunityInboxItem:\n"
            "    pass\n\n"
            "class OpportunityInbox:\n"
            "    pass\n\n"
            "class OpportunityInboxBuilder:\n"
            "    def build(self, path: Path) -> object:\n"
            "        return load_optional_json_mapping(path)\n"
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert not any(
        finding.kind is RepositoryFindingKind.CANONICAL_LAYER_OWNERSHIP_AMBIGUITY
        and finding.path == "src/ai4binance/opportunities.py"
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_unapproved_absolute_paths_and_reports_json(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "path_policy.py").write_text(
        'DATA_ROOT = "H:/BackUP/Downloads"\n',
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert any(
        finding.kind is RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH
        for finding in report.findings
    )
    payload = report.to_payload()
    assert payload["status"] == "RUNNING_WITH_BLOCKERS"
    assert payload["execution_allowed"] is False


def test_repository_validator_blocks_hardcoded_active_repository_root(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "path_policy.py").write_text(
        f'REPOSITORY_ROOT = "{tmp_path.as_posix()}"\n',
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert any(
        finding.kind is RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH
        and finding.path == "src/ai4binance/governance/path_policy.py"
        for finding in report.findings
    )
    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert report.execution_allowed is False


def test_repository_validator_scans_absolute_paths_match_by_match(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "path_policy.py").write_text(
        'ALLOWED = "C:/approved/root"\nBLOCKED = "H:/BackUP/Downloads"\n',
        encoding="utf-8",
    )
    policy = RepositoryPolicy.ai4binance_vnext()
    policy = RepositoryPolicy(
        policy_id=policy.policy_id,
        version=policy.version,
        allowed_top_level_paths=policy.allowed_top_level_paths,
        source_roots=policy.source_roots,
        test_roots=policy.test_roots,
        docs_roots=policy.docs_roots,
        generated_roots=policy.generated_roots,
        protected_roots=policy.protected_roots,
        ignored_parts=policy.ignored_parts,
        cache_parts=policy.cache_parts,
        legacy_path_targets=policy.legacy_path_targets,
        forbidden_python_filenames=policy.forbidden_python_filenames,
        allowed_absolute_path_literals=("C:/approved/root",),
        knowledge_metadata_required_paths=policy.knowledge_metadata_required_paths,
        english_only_knowledge_paths=policy.english_only_knowledge_paths,
        non_code_content_language=policy.non_code_content_language,
        knowledge_section_requirements=policy.knowledge_section_requirements,
        owner_by_top_level=policy.owner_by_top_level,
        compatibility_imports=policy.compatibility_imports,
    )

    report = validate_repository(tmp_path, policy=policy)
    details = [
        finding.detail
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.HARDCODED_ABSOLUTE_PATH
    ]

    assert len(details) == 1
    assert "H:/BackUP/Downloads" in details[0]
    assert "C:/approved/root" not in details[0]


def test_repository_validator_blocks_invalid_governed_knowledge_metadata(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    _write_governed_doc(
        docs / "standards" / "standard_repository_file_governance.md",
        document_id="AI4B-GOV-STD-RFG-001",
        title="AI4BINANCE Repository File Governance Standard",
        version="1",
    )
    _write_governed_doc(
        docs / "standards" / "standard_documentation_knowledge_governance.md",
        document_id="AI4B-GOV-STD-RFG-001",
        title="Duplicate Standard",
    )

    report = validate_repository(tmp_path)
    finding_kinds = {finding.kind for finding in report.findings}

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID in finding_kinds
    assert RepositoryFindingKind.KNOWLEDGE_ID_DUPLICATE not in finding_kinds
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_draft_machine_enforceable_source_of_truth(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "docs" / "registries" / "registry_agent_registry.md",
        document_id="AI4B-GOV-REG-999",
        title="AI4BINANCE Draft Machine Registry",
        document_type="REGISTRY",
        status="DRAFT",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION
        and finding.path == "docs/registries/registry_agent_registry.md"
        and "Use lifecycle_status as the canonical field; status is the frontmatter alias."
        in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_accepts_lifecycle_status_frontmatter_alias(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    path = tmp_path / "docs" / "registries" / "registry_agent_registry.md"
    _write_governed_doc(
        path,
        document_id="AI4B-GOV-REG-997",
        title="AI4BINANCE Draft Alias Registry",
        document_type="REGISTRY",
        status="DRAFT",
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "status: DRAFT",
            "lifecycle_status: DRAFT",
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION
        and finding.path == "docs/registries/registry_agent_registry.md"
        and "Use lifecycle_status as the canonical field; status is the frontmatter alias."
        in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_conflicting_lifecycle_status_alias(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    path = tmp_path / "docs" / "registries" / "registry_agent_registry.md"
    _write_governed_doc(
        path,
        document_id="AI4B-GOV-REG-996",
        title="AI4BINANCE Conflicting Alias Registry",
        document_type="REGISTRY",
        status="DRAFT",
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "status: DRAFT",
            "status: DRAFT\nlifecycle_status: ACTIVE",
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION
        and finding.path == "docs/registries/registry_agent_registry.md"
        and "Use lifecycle_status as the canonical field; status is the frontmatter alias."
        in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_active_entries_inside_draft_registry(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    path = tmp_path / "docs" / "registries" / "registry_agent_registry.md"
    _write_governed_doc(
        path,
        document_id="AI4B-GOV-REG-998",
        title="AI4BINANCE Draft Advisory Registry",
        document_type="REGISTRY",
        status="DRAFT",
        content_role="EXPLANATORY",
        source_of_truth="false",
        machine_enforceable="false",
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n| agent_id | lifecycle_status |\n"
            "| --- | --- |\n"
            "| AIO-AGT-999 | ACTIVE |\n"
        )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_LIFECYCLE_VIOLATION
        and finding.path == "docs/registries/registry_agent_registry.md"
        and "cannot contain ACTIVE registry entries" in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_non_english_governed_standard(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    _write_governed_doc(
        docs / "standards" / "standard_documentation_knowledge_governance.md",
        document_id="AI4B-GOV-STD-DKG-001",
        title="AI4BINANCE Documentation and Knowledge Governance Standard",
    )
    with (docs / "standards" / "standard_documentation_knowledge_governance.md").open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write("\n\nBu belge sistem bilgisini yonetir.\n")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_LANGUAGE_VIOLATION
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_non_english_non_code_repository_content(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    config = tmp_path / "config" / "governance"
    config.mkdir(parents=True, exist_ok=True)
    (config / "policy.yaml").write_text(
        "purpose: Bu belge dosya yonetisim kuralini anlatir.\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION
        and finding.path == "config/governance/policy.yaml"
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_non_english_dynamic_governed_markdown(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    workflow = tmp_path / "docs" / "workflows"
    workflow.mkdir(parents=True, exist_ok=True)
    (workflow / "instruction_dynamic_scope.md").write_text(
        "---\n"
        "document_id: AI4B-GOV-DYNAMIC-001\n"
        "title: Dynamic Scope Instruction\n"
        "document_type: INSTRUCTION\n"
        "version: 1.0.0\n"
        "status: ACTIVE\n"
        "owner: Governance\n"
        "authority_level: REPOSITORY\n"
        "authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS\n"
        "authority_scope: dynamic_scope_instruction\n"
        "authority_effect: OPERATIONAL_SPECIALIZATION\n"
        "content_role: OPERATIONAL\n"
        "source_of_truth: true\n"
        "source_of_truth_scope: dynamic_scope_instruction\n"
        "machine_enforceable: false\n"
        "audit_required: true\n"
        "classification: INTERNAL\n"
        "---\n\n"
        "# Dynamic Scope\n\n"
        "Bu belge governed markdown dynamic language taramasini ihlal eder.\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_LANGUAGE_VIOLATION
        and finding.path == "docs/workflows/instruction_dynamic_scope.md"
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_transliterated_non_english_repository_content(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    config = tmp_path / "config" / "governance"
    config.mkdir(parents=True, exist_ok=True)
    (config / "policy.yaml").write_text(
        "purpose: This file uses veya and arastirma residue in prose.\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION
        and finding.path == "config/governance/policy.yaml"
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_ignores_language_markers_inside_urls_and_code(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    config = tmp_path / "config" / "governance"
    config.mkdir(parents=True, exist_ok=True)
    (config / "policy.yaml").write_text(
        (
            "purpose: Professional English prose.\n"
            "reference: https://example.invalid/Kullanici-Guvenligine\n"
            "marker: `.çzüö`\n"
            "command: `echo veya`\n"
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert not any(
        finding.kind is RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION
        and finding.path == "config/governance/policy.yaml"
        for finding in report.findings
    )


def test_repository_validator_skips_missing_non_code_content_artifact(
    tmp_path: Path,
) -> None:
    findings = tuple(
        repository_validator_module._non_code_content_language_findings(
            tmp_path,
            RepositoryPolicy.ai4binance_vnext(),
            (
                _repository_artifact(
                    artifact_type=RepositoryArtifactType.GOVERNANCE,
                    artifact_class=RepositoryArtifactClass.GOVERNANCE,
                    canonical_path="config/governance/missing-policy.yaml",
                    filename="missing-policy.yaml",
                ),
            ),
        )
    )
    assert findings == ()


def test_repository_validator_blocks_non_utf8_non_code_repository_content(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    config = tmp_path / "config" / "governance"
    config.mkdir(parents=True, exist_ok=True)
    (config / "policy.yaml").write_bytes(b"\xff\xfe\x00\x81")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.NON_CODE_CONTENT_LANGUAGE_VIOLATION
        and finding.path == "config/governance/policy.yaml"
        and finding.detail == "Non-code repository content must be UTF-8 English text."
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_unmet_dynamic_markdown_knowledge_contract(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    nested_docs = tmp_path / "docs" / "architecture"
    nested_docs.mkdir(parents=True)
    (nested_docs / "framework_decision_governance_engine.md").write_text(
        "# Decision Governance Engine\n\nGoverned recursive document.\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)
    finding_kinds = {finding.kind for finding in report.findings}

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING in finding_kinds
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_governed_markdown_without_eli10(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "README.md",
        document_id="AI4B-DOC-README-001",
        title="AI4BINANCE Repository README",
        document_type="REGISTRY",
    )
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    (tmp_path / "README.md").write_text(
        text.replace("\n## ELI10\n", "\n## Summary\n"),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_REQUIRED_SECTION_MISSING
        and finding.path == "README.md"
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_backup_manifest_schema_preserves_backup_only_authority() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "governance"
        / "repository_backup_manifest.schema.json"
    )

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]

    assert "authority" in schema["required"]
    assert "source_of_truth" in schema["required"]
    assert "contains_secrets" in schema["required"]
    assert properties["authority"]["const"] == "BACKUP_ONLY"
    assert properties["source_of_truth"]["const"] is False
    assert properties["contains_secrets"]["const"] is False
    assert properties["may_override_repository"]["const"] is False
    assert properties["may_define_authority"]["const"] is False
    assert properties["may_promote_runtime_artifacts"]["const"] is False


def test_repository_artifact_schema_requires_governance_enforcement_fields() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "governance"
        / "repository_artifact.schema.json"
    )

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]
    required = set(schema["required"])

    assert {
        "source_of_truth",
        "machine_enforceable",
        "audit_required",
        "classification",
    }.issubset(required)
    assert properties["source_of_truth"]["type"] == "boolean"
    assert properties["machine_enforceable"]["type"] == "boolean"
    assert properties["audit_required"]["type"] == "boolean"
    assert properties["classification"]["enum"] == [
        "PUBLIC",
        "INTERNAL",
        "CONFIDENTIAL",
        "RESTRICTED",
        "SECRET",
    ]


def test_repository_validator_blocks_duplicate_governed_knowledge_id(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    _write_governed_doc(
        docs / "standards/standard_repository_file_governance.md",
        document_id="AI4B-GOV-REPO-001",
        title="AI4BINANCE Repository File Governance Standard",
    )
    _write_governed_doc(
        docs / "standards/standard_documentation_knowledge_governance.md",
        document_id="AI4B-GOV-REPO-001",
        title="Duplicate Standard",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_ID_DUPLICATE
        for finding in report.findings
    )
    assert report.execution_allowed is False


def test_repository_validator_blocks_duplicate_source_of_truth_concept(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "docs" / "providers" / "instruction_codex_provider.md",
        document_id="AI4B-GOV-INS-002",
        title="Duplicate Instruction Concept",
        document_type="INSTRUCTION",
        authority_level="PROVIDER_ADAPTER",
        authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        authority_scope="codex_provider",
        authority_effect="OPERATIONAL_SPECIALIZATION",
        content_role="OPERATIONAL",
    )
    _write_governed_doc(
        tmp_path / "docs" / "governance" / "instruction_core_custom_instructions.md",
        document_id="AI4B-GOV-INS-001",
        title="Duplicate Instruction Concept",
        document_type="INSTRUCTION",
    )
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_lower_authority_scope_reuse_even_with_different_title(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "docs" / "governance" / "framework_core_constitution.md",
        root=tmp_path,
        document_id="AI4B-GOV-FRM-099",
        title="Core Constitution Owner",
        document_type="FRAMEWORK",
        authority_level="NORMATIVE",
        authority_layer="L1_CORE_CONSTITUTION",
        authority_scope="core_constitution",
        authority_effect="NORMATIVE_CONSTRAINT",
        content_role="AUTHORITATIVE",
        source_of_truth_scope="canonical",
    )
    _write_governed_doc(
        tmp_path / "docs" / "runbooks" / "runbook_core_constitution_shadow.md",
        root=tmp_path,
        document_id="AI4B-GOV-RBK-001",
        title="Core Constitution Shadow Runbook",
        document_type="RUNBOOK",
        authority_level="REPOSITORY",
        authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        authority_scope="core_constitution",
        authority_effect="OPERATIONAL_SPECIALIZATION",
        content_role="OPERATIONAL",
        source_of_truth_scope="core_constitution_runbook",
    )
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT
        and finding.path == "docs/runbooks/runbook_core_constitution_shadow.md"
        and "core_constitution" in finding.detail
        for finding in report.findings
    )
    assert any(
        action.finding_kind
        is RepositoryFindingKind.KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT
        and action.action_type == "REALIGN_AUTHORITY_SCOPE"
        for action in report.recommended_actions
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_allows_lower_authority_with_derived_scope(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "docs" / "runbooks" / "runbook_constitution_review.md",
        root=tmp_path,
        document_id="AI4B-GOV-RBK-002",
        title="Constitution Review Runbook",
        document_type="RUNBOOK",
        authority_level="REPOSITORY",
        authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        authority_scope="constitution_review",
        authority_effect="OPERATIONAL_SPECIALIZATION",
        content_role="OPERATIONAL",
        source_of_truth_scope="constitution_review_runbook",
    )
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.PASS
    assert not any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT
        for finding in report.findings
    )


def test_repository_validator_blocks_missing_scope_for_family_index_document(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    handbook_path = (
        tmp_path
        / "docs"
        / "governance"
        / "policy_organization_constitution_handbook.md"
    )
    text = handbook_path.read_text(encoding="utf-8")
    handbook_path.write_text(
        text.replace("source_of_truth_scope: family_index\n", ""),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_MISSING
        and finding.path
        == "docs/governance/policy_organization_constitution_handbook.md"
        and "source_of_truth_scope" in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_wrong_scope_for_provider_adapter_document(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    provider_path = tmp_path / "docs" / "providers" / "instruction_claude_provider.md"
    _write_governed_doc(
        provider_path,
        root=tmp_path,
        document_id="AI4B-GOV-PRV-CLAUDE-001",
        title="AI4BINANCE Claude Provider Instructions",
        document_type="PROVIDER_ADAPTER",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
    )
    text = provider_path.read_text(encoding="utf-8")
    provider_path.write_text(
        text.replace(
            "source_of_truth_scope: provider_adapter\n",
            "source_of_truth_scope: canonical\n",
        ),
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_METADATA_INVALID
        and finding.path == "docs/providers/instruction_claude_provider.md"
        and "provider_adapter" in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_uppercase_source_of_truth_filename(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "docs" / "governance" / "Policy_Source.md",
        document_id="AI4B-GOV-POL-999",
        title="AI4BINANCE Uppercase Source Policy",
        document_type="POLICY",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION
        and finding.path == "docs/governance/Policy_Source.md"
        for finding in report.findings
    )
    assert any(
        action.finding_kind
        is RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION
        and action.action_type == "RENAME_SOURCE_OF_TRUTH_FILE"
        and action.proposed_path == "docs/governance/policy_source.md"
        for action in report.recommended_actions
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_locked_document_change_without_written_approval(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_path = "docs/standards/standard_repository_file_governance.md"
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    if not _git_commit_all(tmp_path):
        return
    with (tmp_path / locked_path).open("a", encoding="utf-8") as handle:
        handle.write("\nUnauthorized condition change.\n")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        and finding.path == locked_path
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_missing_document_lock_manifest_policy(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    manifest_path = tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("manifest_lock_policy")
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        and finding.path == GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_document_lock_registration_mismatch(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    manifest_path = tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["locked_documents"][0]["authority_level"] = "ADVISORY"
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        and finding.detail
        == "Governed document lock manifest registration mismatch for authority_level."
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_stale_extra_document_lock_manifest_entry(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    extra_path = "docs/advisory-extra.md"
    _write_governed_doc(
        tmp_path / extra_path,
        document_id="AI4B-GOV-TEST-EXTRA-001",
        title="Advisory Extra",
        document_type="STANDARD",
        authority_level="REPOSITORY",
        content_role="OPERATIONAL",
        source_of_truth="false",
        machine_enforceable="false",
    )
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    manifest_path = tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    extra_entry = dict(payload["locked_documents"][0])
    extra_entry["path"] = extra_path
    extra_entry["canonical_path"] = extra_path
    payload["locked_documents"].append(extra_entry)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        and finding.path == extra_path
        and "no longer an active source-of-truth or machine-enforceable"
        in finding.detail
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_blocks_missing_locked_document_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_path = "docs/standards/standard_repository_file_governance.md"
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    original_is_file = Path.is_file

    def missing_locked_file(path: Path) -> bool:
        if path == tmp_path / locked_path:
            return False
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", missing_locked_file)

    findings = tuple(
        repository_validator_module._governed_document_lock_findings(
            tmp_path,
            [_knowledge_object(path=locked_path, canonical_path=locked_path)],
        )
    )
    assert any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        and finding.path == locked_path
        and finding.detail == "Locked governed document is missing from the repository."
        for finding in findings
    )


def test_repository_validator_locks_active_policy_as_code_markdown(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    policy_as_code_path = "docs/governance/policy_machine_rule.md"
    _write_governed_doc(
        tmp_path / policy_as_code_path,
        document_id="AI4B-GOV-PAC-001",
        title="AI4BINANCE Policy as Code Rule",
        document_type="POLICY",
        content_role="POLICY_AS_CODE",
        source_of_truth="false",
        machine_enforceable="false",
    )
    _write_document_lock_manifest(tmp_path, _fixture_lock_paths(tmp_path))

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        and finding.path == policy_as_code_path
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_validator_allows_locked_document_change_with_written_approval(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_path = "docs/standards/standard_repository_file_governance.md"
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    baseline_sha256 = {
        relative: _sha256(tmp_path / relative) for relative in locked_paths
    }
    if not _git_commit_all(tmp_path):
        return
    with (tmp_path / locked_path).open("a", encoding="utf-8") as handle:
        handle.write("\nApproved condition change.\n")
    _write_document_lock_manifest(
        tmp_path,
        locked_paths,
        baseline_sha256=baseline_sha256,
        approvals={locked_path: _sha256(tmp_path / locked_path)},
    )

    report = validate_repository(tmp_path)

    assert not any(
        finding.kind is RepositoryFindingKind.GOVERNED_DOCUMENT_LOCK_VIOLATION
        for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_governed_document_lock_approval_script_exports_verified_chain(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_path = "docs/standards/standard_repository_file_governance.md"
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    approved_sha256 = {locked_path: _sha256(tmp_path / locked_path)}
    payload = json.loads(
        (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    payload["approval_records"] = [
        {
            "approval_id": "AI4B-GOV-DOCLOCK-TEST-001",
            "approval_status": "APPROVED",
            "approved_by": "Huseyin",
            "approved_at_utc": "2026-08-20T00:00:00Z",
            "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
            "written_owner_approval": True,
            "approved_sha256": approved_sha256,
        }
    ]
    (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    output_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "governance"
        / "governed_document_lock_approval_test.json"
    )
    argv_before = sys.argv[:]
    try:
        sys.argv = [
            "export_governed_document_lock_approval.py",
            "--repository-root",
            str(tmp_path),
            "--approval-id",
            "AI4B-GOV-DOCLOCK-TEST-001",
            "--output-path",
            str(output_path),
        ]
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(
                str(ROOT / "scripts" / "export_governed_document_lock_approval.py"),
                run_name="__main__",
            )
        assert excinfo.value.code == 0
    finally:
        sys.argv = argv_before

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert (
        evidence["artifact_origin"] == "governed_document_lock_written_owner_approval"
    )
    assert evidence["approval_id"] == "AI4B-GOV-DOCLOCK-TEST-001"
    assert evidence["approved_sha256"] == approved_sha256
    assert evidence["verification_status"] == "VERIFIED"
    assert evidence["current_alignment_status"] == "VERIFIED"
    assert evidence["approved_documents"][0]["hash_matches_current_content"] is True


def test_governed_document_lock_approval_script_exports_historical_chain(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_path = "docs/standards/standard_repository_file_governance.md"
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    payload = json.loads(
        (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    payload["approval_records"] = [
        {
            "approval_id": "AI4B-GOV-DOCLOCK-TEST-HISTORICAL-001",
            "approval_status": "APPROVED",
            "approved_by": "Huseyin",
            "approved_at_utc": "2026-08-20T00:00:00Z",
            "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
            "written_owner_approval": True,
            "approved_sha256": {locked_path: "a" * 64},
        }
    ]
    (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    output_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "governance"
        / "governed_document_lock_approval_historical.json"
    )
    argv_before = sys.argv[:]
    try:
        sys.argv = [
            "export_governed_document_lock_approval.py",
            "--repository-root",
            str(tmp_path),
            "--approval-id",
            "AI4B-GOV-DOCLOCK-TEST-HISTORICAL-001",
            "--output-path",
            str(output_path),
        ]
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(
                str(ROOT / "scripts" / "export_governed_document_lock_approval.py"),
                run_name="__main__",
            )
        assert excinfo.value.code == 0
    finally:
        sys.argv = argv_before

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["verification_status"] == "VERIFIED"
    assert evidence["current_alignment_status"] == "RUNNING_WITH_BLOCKERS"
    assert evidence["approved_documents"][0]["hash_matches_current_content"] is False


def test_governed_document_lock_approval_script_handles_missing_manifest_entry(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    payload = json.loads(
        (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    historical_path = "docs/reports/governance/report_platform_blocker_closure_map.md"
    historical_file = tmp_path / historical_path
    historical_file.parent.mkdir(parents=True, exist_ok=True)
    historical_file.write_text("historical report\n", encoding="utf-8")
    historical_sha = _sha256(historical_file)
    payload["approval_records"] = [
        {
            "approval_id": "AI4B-GOV-DOCLOCK-TEST-MISSING-ENTRY-001",
            "approval_status": "APPROVED",
            "approved_by": "Huseyin",
            "approved_at_utc": "2026-08-20T00:00:00Z",
            "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
            "written_owner_approval": True,
            "approved_sha256": {historical_path: historical_sha},
        }
    ]
    (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    output_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "governance"
        / "governed_document_lock_approval_missing_entry.json"
    )
    argv_before = sys.argv[:]
    try:
        sys.argv = [
            "export_governed_document_lock_approval.py",
            "--repository-root",
            str(tmp_path),
            "--approval-id",
            "AI4B-GOV-DOCLOCK-TEST-MISSING-ENTRY-001",
            "--output-path",
            str(output_path),
        ]
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(
                str(ROOT / "scripts" / "export_governed_document_lock_approval.py"),
                run_name="__main__",
            )
        assert excinfo.value.code == 0
    finally:
        sys.argv = argv_before

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["verification_status"] == "VERIFIED"
    assert evidence["current_alignment_status"] == "RUNNING_WITH_BLOCKERS"
    assert evidence["approved_documents"][0]["manifest_entry_status"] == "MISSING"


def test_governed_document_lock_approval_script_handles_missing_approved_document(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    payload = json.loads(
        (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    historical_path = "docs/ontology/repository_artifact.md"
    payload["approval_records"] = [
        {
            "approval_id": "AI4B-GOV-DOCLOCK-TEST-MISSING-DOC-001",
            "approval_status": "APPROVED",
            "approved_by": "Huseyin",
            "approved_at_utc": "2026-08-20T00:00:00Z",
            "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
            "written_owner_approval": True,
            "approved_sha256": {historical_path: "a" * 64},
        }
    ]
    (tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    output_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "governance"
        / "governed_document_lock_approval_missing_doc.json"
    )
    argv_before = sys.argv[:]
    try:
        sys.argv = [
            "export_governed_document_lock_approval.py",
            "--repository-root",
            str(tmp_path),
            "--approval-id",
            "AI4B-GOV-DOCLOCK-TEST-MISSING-DOC-001",
            "--output-path",
            str(output_path),
        ]
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(
                str(ROOT / "scripts" / "export_governed_document_lock_approval.py"),
                run_name="__main__",
            )
        assert excinfo.value.code == 0
    finally:
        sys.argv = argv_before

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["verification_status"] == "VERIFIED"
    assert evidence["current_alignment_status"] == "RUNNING_WITH_BLOCKERS"
    assert evidence["approved_documents"][0]["document_presence_status"] == "MISSING"
    assert evidence["approved_documents"][0]["hash_matches_current_content"] is False


def test_governed_document_lock_sync_script_normalizes_legacy_written_owner_orphans(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    locked_paths = _fixture_lock_paths(tmp_path)
    _write_document_lock_manifest(tmp_path, locked_paths)
    approved_sha256 = {
        "docs/compliance/registry_compliance_matrix.md": _sha256(
            tmp_path / "docs/compliance/registry_compliance_matrix.md"
        )
    }
    manifest_path = tmp_path / GOVERNED_DOCUMENT_LOCK_MANIFEST_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["approval_records"] = []
    payload["written_owner_approvals"] = [
        {
            "approval_id": "AI4B-GOV-DOCLOCK-TEST-LEGACY-ORPHAN-001",
            "approval_scope": "TEST_WRITTEN_OWNER_APPROVAL",
            "approved_at_utc": "2026-08-20T00:00:00Z",
            "approved_by": "Huseyin",
            "approved_sha256": approved_sha256,
            "written_owner_approval": True,
        }
    ]
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    argv_before = sys.argv[:]
    sys_path_before = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        sys.argv = [
            "sync_governed_document_lock_approval_evidence.py",
            "--repository-root",
            str(tmp_path),
        ]
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(
                str(
                    ROOT
                    / "scripts"
                    / "sync_governed_document_lock_approval_evidence.py"
                ),
                run_name="__main__",
            )
        assert excinfo.value.code == 0
    finally:
        sys.argv = argv_before
        sys.path[:] = sys_path_before

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    approval_record = manifest["approval_records"][0]
    written_owner_approval = manifest["written_owner_approvals"][0]
    assert approval_record["approval_id"] == "AI4B-GOV-DOCLOCK-TEST-LEGACY-ORPHAN-001"
    assert approval_record["approval_status"] == "APPROVED"
    assert approval_record["written_owner_approval"] is True
    assert approval_record["approved_sha256"] == approved_sha256
    assert approval_record["approval_evidence_path"].endswith(
        "governed_document_lock_approval_ai4b_gov_doclock_test_legacy_orphan_001.json"
    )
    assert len(approval_record["approval_evidence_sha256"]) == 64
    assert written_owner_approval == approval_record


def test_repository_validator_allows_reserved_source_of_truth_filename(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "analysis" / "AGENTS.md",
        document_id="AI4B-AGENT-CONTRACT-TEST",
        title="AI4BINANCE Scoped Agent Contract",
        document_type="AGENT_CONTRACT",
    )

    report = validate_repository(tmp_path)

    assert not [
        finding
        for finding in report.findings
        if finding.kind is RepositoryFindingKind.SOURCE_OF_TRUTH_FILENAME_CASE_VIOLATION
    ]


def test_repository_validator_allows_deprecated_duplicate_knowledge_concept(
    tmp_path: Path,
) -> None:
    _write_required_knowledge_docs(tmp_path)
    _write_governed_doc(
        tmp_path / "docs" / "providers" / "instruction_codex_provider.md",
        document_id="AI4B-GOV-INS-003",
        title="Shared Historical Instruction Concept",
        document_type="INSTRUCTION",
        status="DEPRECATED",
        authority_level="PROVIDER_ADAPTER",
        content_role="OPERATIONAL",
        source_of_truth="false",
        machine_enforceable="false",
    )
    _write_governed_doc(
        tmp_path / "docs" / "governance" / "instruction_core_custom_instructions.md",
        document_id="AI4B-GOV-INS-001",
        title="Shared Historical Instruction Concept",
        document_type="INSTRUCTION",
    )
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = validate_repository(tmp_path)

    assert report.status is RepositoryValidationStatus.PASS
    assert not any(
        finding.kind is RepositoryFindingKind.KNOWLEDGE_SOURCE_OF_TRUTH_CONFLICT
        for finding in report.findings
    )


def test_repository_validator_cli_is_deterministic_json(tmp_path: Path) -> None:
    _write_required_knowledge_docs(tmp_path)
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "repository_policy.py").write_text("VALUE = 1\n", encoding="utf-8")

    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "ai4binance.governance.repository_validator",
            "--repository-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["status"] == "PASS"
    assert payload["artifact_count"] == 21
    assert payload["analyzed_at_utc"]
    assert payload["analysis_scope"] == "AGGRESSIVE_ALL_FILES"
    assert len(payload["artifacts"]) == 21
    assert {
        action["current_path"] for action in payload["recommended_actions"]
    } == set()
    assert {artifact["canonical_path"] for artifact in payload["artifacts"]} >= {
        "AGENTS.md",
        "src/ai4binance/governance/repository_policy.py",
    }
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert "root_inventory" in payload

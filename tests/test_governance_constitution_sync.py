from __future__ import annotations

# ruff: noqa: E501
import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.governance import constitution_sync as constitution_sync_module
from ai4binance.governance.constitution_sync import (
    GovernanceAlignmentStatus,
    LooseCodeGapKind,
    QualityGateEvidence,
    audit_governance_alignment,
)
from tests.documentation_hygiene_helpers import stale_knowledge_template_offenders

ROOT = Path(__file__).resolve().parents[1]


def test_quality_attestation_does_not_inherit_an_ancestor_git_repository(
    tmp_path: Path,
) -> None:
    git = shutil.which("git")
    assert git is not None
    ancestor = tmp_path / "ancestor"
    requested_root = ancestor / "nested-workspace"
    requested_root.mkdir(parents=True)
    (ancestor / "parent.txt").write_text("initial\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", str(ancestor)], check=True
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(ancestor), "add", "parent.txt"], check=True
    )
    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(ancestor),
            "-c",
            "user.name=AI4Binance Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Initialize ancestor repository",
        ],
        check=True,
    )
    (ancestor / "parent.txt").write_text("changed\n", encoding="utf-8")

    attestation = constitution_sync_module.build_quality_gate_workspace_attestation(
        requested_root
    )

    assert attestation.git_commit == "WORKTREE_UNCOMMITTED"
    assert attestation.change_set_sha256 == sha256(b"").hexdigest()


def write_core_documents(root: Path, *, compliance_extra: str = "") -> None:
    (root / "AGENTS.md").write_text(
        "\n".join(
            (
                "# Root Agent Instructions",
                "",
                "## ELI10",
                "",
                "The canonical constitution is "
                "`docs/governance/framework_core_vnext_governance.md`.",
                "Use `docs/governance/policy_organization_constitution_handbook.md`.",
                "Use `docs/standards/standard_repository_file_governance.md`.",
                "Codex workflows must load "
                "`docs/providers/instruction_codex_provider.md`.",
                "Claude workflows must load "
                "`docs/providers/instruction_claude_provider.md`.",
                "GOVERNANCE_CONFLICT",
                "RUNNING_WITH_BLOCKERS",
                "RESEARCH_ONLY",
                "LIVE_ORDER_BLOCKED",
                "Repository root describes the system. `runtime/` describes what the system",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "governance").mkdir(parents=True, exist_ok=True)
    (docs / "governance/policy_organization_constitution_handbook.md").write_text(
        "\n".join(
            (
                "---",
                "document_id: AI4B-GOV-OEK-003",
                "title: AI4BINANCE Organization Constitution and Handbook",
                "document_type: POLICY",
                "version: 3.0.0",
                "status: ACTIVE",
                "owner: Enterprise Knowledge Governance",
                "authority_level: NORMATIVE",
                "content_role: AUTHORITATIVE",
                "source_of_truth: true",
                "machine_enforceable: true",
                "audit_required: true",
                "classification: INTERNAL",
                "---",
                "# AI4BINANCE DIGITAL MARKETS HOLDING",
                "",
                "## ELI10",
                "",
                "This document is the stable index for the Organization Constitution and Handbook family. Detailed authoritative sections are split into smaller governed policy files.",
                "",
                "This index remains the stable OEK entry point required by `OEK_AUTHORITY_SOURCE:docs/governance/policy_organization_constitution_handbook.md`.",
                "It organizes the governed policy family but does not replace the canonical constitution.",
                "The canonical constitution file is `docs/governance/framework_core_vnext_governance.md`.",
                "The detailed sections below are authoritative controlled parts of the same governed policy family.",
                "This document alone does not grant permission for live trading, fund transfers, production deployments, or authority expansion.",
                "",
                "## Mandatory Compliance Anchors",
                "",
                "`AI4BINANCE-OEK-CANONICAL-CONSTITUTION` identifies the canonical constitution",
                "for this policy family. The canonical constitution file is",
                "`docs/governance/framework_core_vnext_governance.md`. This handbook remains the",
                "stable family index inside the repository `Hierarchy of Norms` and preserves the",
                "`REPOSITORY CONTENT LANGUAGE LOCK` for professional English repository content.",
                "",
                "Repository governance is validated by `repository_validator`, including",
                "`NON_CODE_CONTENT_LANGUAGE_VIOLATION` checks. These controls support the",
                "`IMMUTABLE CORE PRINCIPLES` of `Capital Protection`, `Human Oversight`,",
                "`Fail-Closed`, and `Controlled Learning`.",
                "",
                "Live and research boundaries remain explicit: `NO_TRADE`, `RESEARCH_ONLY`, and",
                "`LIVE_ORDER_BLOCKED` are valid fail-closed outcomes. Every material change to an",
                "`agent, workflow, config, model, strategy` requires `gap analysis` covering",
                "`risk, privacy/security`, implementation impact, and `test` evidence.",
                "",
                "## Split Policy Files",
                "",
                "| File | Scope |",
                "| --- | --- |",
                "| `docs/governance/policy_organization_foundation_operating_model.md` | AI4BINANCE Organization Foundation and Operating Model Policy |",
                "| `docs/governance/policy_organization_authority_agent_lifecycle.md` | AI4BINANCE Organization Authority and Agent Lifecycle Policy |",
                "| `docs/governance/policy_organization_market_strategy_validation.md` | AI4BINANCE Organization Market Strategy and Validation Policy |",
                "| `docs/governance/policy_organization_risk_security_privacy.md` | AI4BINANCE Organization Risk Security and Privacy Policy |",
                "| `docs/governance/policy_organization_improvement_quality_reporting.md` | AI4BINANCE Organization Improvement Quality and Reporting Policy |",
                "| `docs/governance/policy_organization_incident_change_appendices.md` | AI4BINANCE Organization Incident Change and Appendices Policy |",
                "",
                "## Governance Boundary",
                "",
                "- Prompts, agent charters, workflows, configurations, models, strategies, SOPs, and production changes must align with this OEK policy family.",
                "- OEK content does not bypass risk, compliance, validation, security, or human-governed promotion.",
                "- Live eligibility remains `LIVE_ORDER_BLOCKED`.",
            )
        ),
        encoding="utf-8",
    )
    (docs / "governance/framework_core_vnext_governance.md").write_text(
        "\n".join(
            (
                "# Core",
                "",
                "## ELI10",
                "",
                "DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.",
                "DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.",
                "HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.",
                "Risk-tiered human governance applies only when the proven change is consequential.",
                "Approval Packet",
                "scope_hash",
                "Code/constitution divergence is prohibited.",
                "The canonical constitution file is `docs/governance/framework_core_vnext_governance.md`.",
                "The Organization Constitution and Handbook is a stable family index",
                "provider-facing custom-instruction files are adapters",
                "Cleanup audit registry evidence rule",
                "source, test, compliance matrix and core doc",
                "Constitution family mismatch visibility rule",
                "core, Custom Instructions, Codex and compliance matrix",
                "Loose changed source rule",
                "Capability OOS/operational evidence gap rule",
                "Capability OOS/operational evidence gaps remain visible",
                "Repository governance enforcement rule",
                "RepositoryPolicy",
                "RepositoryArtifact schema",
                "deterministic repository_validator",
                "Documentation and knowledge governance rule",
                "GovernedKnowledgeObject",
                "AI4B-GOV-DKG-001",
                "Duplicate active source-of-truth concepts",
                "Governed repository/file standards and machine governance contracts",
                "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
                "Docs are authority.",
                "Validator is enforcement.",
                "Quality gate is evidence.",
                "Human governance is consequential authority.",
                "Runtime is not source-of-truth.",
                "LLM is not authority.",
                "Scores cannot hide blockers.",
                "LIVE remains blocked.",
                "LIVE_ORDER_BLOCKED",
            )
        ),
        encoding="utf-8",
    )
    (docs / "standards").mkdir(parents=True, exist_ok=True)
    (docs / "standards/standard_repository_validator_governance.md").write_text(
        "\n".join(
            (
                "# Repository Validator Standard",
                "",
                "## ELI10",
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
    (docs / "governance" / "instruction_core_custom_instructions.md").write_text(
        "\n".join(
            (
                "# Core Custom Instructions",
                "",
                "## ELI10",
                "",
                "This file is the Codex-facing custom-instructions adapter for the system.",
                "DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.",
                "DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.",
                "HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.",
                "Risk-tiered human governance applies only when the proven change is consequential.",
                "Approval Packet",
                "scope_hash",
                "Code and written constitution must not diverge.",
                "This file is a provider-facing operational agreement, not the canonical constitution.",
                "Cleanup audit registry evidence rule",
                "Transparent proof rule",
                "Wide-scope audit rule",
                "Constitution family mismatch visibility rule",
                "Loose changed source rule",
                "Capability OOS/operational evidence gap rule",
                "Repository governance enforcement rule",
                "RepositoryPolicy + RepositoryArtifact schema",
                "deterministic repository_validator",
                "Documentation and knowledge governance rule",
                "GovernedKnowledgeObject",
                "AI4B-GOV-DKG-001",
                "Quality gate is evidence.",
                "Human governance is consequential authority.",
                "LIVE remains blocked.",
                "Duplicate active source-of-truth",
                "Governed repository/file standards and machine governance contracts",
                "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
                "* use BUY, SELL, HOLD, WAIT or NO_TRADE,",
                "* only A*, A and B+ quality,",
                "LIVE_ORDER_BLOCKED",
            )
        ),
        encoding="utf-8",
    )
    provider_docs = root / "docs" / "providers"
    provider_docs.mkdir(parents=True, exist_ok=True)
    (provider_docs / "instruction_codex_provider.md").write_text(
        "\n".join(
            (
                "# Codex Provider",
                "",
                "## ELI10",
                "",
                "ELI10",
                "Codex is a provider adapter",
                "must not redefine canonical governance",
                "DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.",
                "DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.",
                "HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.",
                "GOVERNANCE_CONFLICT",
                "source-of-truth definitions",
                "single source of truth",
                "Do not create hidden shortcuts around Governance",
                "Auto-Control may detect or block governance",
                "Never claim tests, lint, type checking, build, coverage",
                "LIVE_ORDER_BLOCKED",
                "",
            )
        ),
        encoding="utf-8",
    )
    (docs / "compliance").mkdir(parents=True, exist_ok=True)
    (docs / "compliance/registry_compliance_matrix.md").write_text(
        "\n".join(
            (
                "# Compliance",
                "",
                "## ELI10",
                "",
                "Constitutional change control",
                "TECHNICAL_TRUTH",
                "POLICY_ELIGIBILITY",
                "CONSEQUENTIAL_AUTHORITY",
                "risk-tiered human governance",
                "ELI10",
                "relevant policy/instructions",
                "TECHNICAL_QUALITY_PASS",
                "FULL_ASSURANCE_GREEN",
                "source, test, compliance matrix, and core documentation evidence",
                (
                    "coverage rate cannot be inferred from outside full "
                    "quality_gate evidence"
                ),
                "core/root/custom/codex/compliance",
                "empty-source-file change",
                "Capability OOS/operational evidence gap",
                "Repository & File Governance Standard",
                "RepositoryPolicy + RepositoryArtifact schema",
                "repository_validator",
                "Documentation & Knowledge Governance Standard",
                "GovernedKnowledgeObject",
                "AI4B-GOV-DKG-001",
                "Quality gate is evidence.",
                "Human governance is consequential authority.",
                "LIVE remains blocked.",
                "duplicate active source-of-truth concept",
                "governed repository/file standards and machine governance contracts",
                "NON_CODE_CONTENT_LANGUAGE_VIOLATION",
                "LIVE_ORDER_BLOCKED",
                compliance_extra,
            )
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text("LIVE_ORDER_BLOCKED\n", encoding="utf-8")


def write_quality_evidence(
    root: Path,
    *,
    pytest_pass_count: int | None = 2067,
    coverage_percent: float | None = 90.66,
) -> None:
    quality_dir = root / "runtime" / "artifacts" / "quality" / "gate"
    quality_dir.mkdir(parents=True, exist_ok=True)
    proof_path = quality_dir / "coverage_summary.md"
    proof_path.write_text(
        "\n".join(
            (
                "---",
                "document_id: AI4B-QUALITY-EVID-COVERAGE-REALISM-001",
                "document_type: EVIDENCE",
                "content_role: QUALITY_EVIDENCE",
                "machine_enforceable: true",
                "---",
                "",
                "# AI4BINANCE Coverage Policy Summary",
                "",
                "## Realism Proof",
                "",
                "- Coverage percentage is read from coverage.py JSON.",
            )
        ),
        encoding="utf-8",
    )
    payload: dict[str, object] = {
        "status": "TECHNICAL_QUALITY_PASS",
        "schema_version": 2,
        "legacy_status": "QUALITY_GATE_GREEN",
        "full_assurance_status": "FULL_ASSURANCE_GREEN",
        "verification_status": "FULL_VERIFIED",
        "canonical_quality_authority": True,
        "command": (
            "powershell.exe -NoProfile -ExecutionPolicy Bypass "
            "-File .\\scripts\\quality.ps1"
        ),
        "generated_at_utc": "2026-08-13T22:44:50Z",
        "coverage_source": "coverage.py json totals.percent_covered",
        "coverage_realism_proof": {
            "markdown_path": "runtime\\artifacts\\quality\\gate\\coverage_summary.md",
            "markdown_sha256": sha256(proof_path.read_bytes()).hexdigest(),
            "evidence_type": "GOVERNED_MARKDOWN_COVERAGE_REALISM_PROOF",
        },
        "workspace_attestation": (
            constitution_sync_module.build_quality_gate_workspace_attestation(
                root
            ).to_payload()
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "consequential_change_allowed": True,
    }
    if pytest_pass_count is not None:
        payload["pytest_pass_count"] = pytest_pass_count
    if coverage_percent is not None:
        payload["coverage_percent"] = coverage_percent
    (quality_dir / "latest.json").write_text(
        json.dumps(payload),
        encoding="utf-8-sig",
    )


def test_governance_alignment_passes_when_code_docs_tests_and_quality_are_synced(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "framework.py").write_text("class Core: ...\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_governance_framework_v2.py").write_text(
        "from ai4binance.governance.framework import Core\n",
        encoding="utf-8",
    )
    write_core_documents(
        tmp_path,
        compliance_extra="src/ai4binance/governance/framework.py",
    )
    write_quality_evidence(tmp_path)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=(
            "src/ai4binance/governance/framework.py",
            "tests/test_governance_framework_v2.py",
        ),
    )

    assert report.status is GovernanceAlignmentStatus.PASS
    assert report.findings == ()
    assert report.pytest_pass_count == 2067
    assert report.coverage_percent == 90.66
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.to_payload()["coverage_source"] == (
        "coverage.py json totals.percent_covered"
    )
    assert (
        report.to_payload()["coverage_realism_proof_path"]
        == "runtime/artifacts/quality/gate/coverage_summary.md"
    )


def test_governance_alignment_surfaces_loose_governance_code(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "ai4binance" / "governance"
    source.mkdir(parents=True)
    (source / "orphan.py").write_text("class Orphan: ...\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path, coverage_percent=None)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=("src/ai4binance/governance/orphan.py",),
    )
    finding_kinds = {finding.kind for finding in report.findings}

    assert report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
    assert LooseCodeGapKind.SOURCE_WITHOUT_TEST_EVIDENCE in finding_kinds
    assert LooseCodeGapKind.SOURCE_CHANGE_WITHOUT_TEST_DELTA in finding_kinds
    assert LooseCodeGapKind.GOVERNANCE_CODE_WITHOUT_COMPLIANCE in finding_kinds
    assert LooseCodeGapKind.SOURCE_WITHOUT_WRITTEN_RULE in finding_kinds
    assert LooseCodeGapKind.QUALITY_EVIDENCE_MISSING in finding_kinds
    assert report.coverage_percent is None
    assert "LIVE_ORDER_BLOCKED" in report.blockers


def test_governance_alignment_accepts_transitive_compliance_trace(
    tmp_path: Path,
) -> None:
    source_path = "src/ai4binance/governance/example_policy.py"
    source = tmp_path / source_path
    source.parent.mkdir(parents=True)
    source.write_text("class ExamplePolicy: ...\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example_policy.py").write_text(
        "from ai4binance.governance.example_policy import ExamplePolicy\n",
        encoding="utf-8",
    )
    write_core_documents(
        tmp_path,
        compliance_extra="docs/standards/example_policy_standard.md",
    )
    standard = tmp_path / "docs" / "standards" / "example_policy_standard.md"
    standard.parent.mkdir(parents=True, exist_ok=True)
    standard.write_text(
        "# Example Policy Standard\n\n"
        "## ELI10\n\n"
        "See `docs/references/example_policy_reference.md`.\n",
        encoding="utf-8",
    )
    reference = tmp_path / "docs" / "references" / "example_policy_reference.md"
    reference.parent.mkdir(parents=True)
    reference.write_text(
        f"# Example Policy Reference\n\n## ELI10\n\n`{source_path}`\n",
        encoding="utf-8",
    )
    write_quality_evidence(tmp_path)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=(source_path, "tests/test_example_policy.py"),
    )

    assert report.status is GovernanceAlignmentStatus.PASS
    assert report.findings == ()


def test_governance_alignment_rejects_unlinked_document_as_compliance_trace(
    tmp_path: Path,
) -> None:
    source_path = "src/ai4binance/governance/unlinked_policy.py"
    source = tmp_path / source_path
    source.parent.mkdir(parents=True)
    source.write_text("class UnlinkedPolicy: ...\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_unlinked_policy.py").write_text(
        "from ai4binance.governance.unlinked_policy import UnlinkedPolicy\n",
        encoding="utf-8",
    )
    write_core_documents(tmp_path)
    unlinked = tmp_path / "docs" / "references" / "unlinked_policy.md"
    unlinked.parent.mkdir(parents=True)
    unlinked.write_text(
        f"# Unlinked Policy\n\n## ELI10\n\n`{source_path}`\n",
        encoding="utf-8",
    )
    write_quality_evidence(tmp_path)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=(source_path, "tests/test_unlinked_policy.py"),
    )
    finding_kinds = {finding.kind for finding in report.findings}

    assert LooseCodeGapKind.GOVERNANCE_CODE_WITHOUT_COMPLIANCE in finding_kinds
    assert LooseCodeGapKind.SOURCE_WITHOUT_WRITTEN_RULE not in finding_kinds


def test_governance_alignment_accepts_publication_boundary_as_written_rule(
    tmp_path: Path,
) -> None:
    source_path = "src/ai4binance/ops/public_showcase.py"
    source = tmp_path / source_path
    source.parent.mkdir(parents=True)
    source.write_text("class PublicShowcase: ...\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_public_showcase.py").write_text(
        "from ai4binance.ops.public_showcase import PublicShowcase\n",
        encoding="utf-8",
    )
    write_core_documents(tmp_path)
    publication = tmp_path / "publication" / "README.md"
    publication.parent.mkdir()
    publication.write_text(
        f"# Publication Boundary\n\n`{source_path}`\n", encoding="utf-8"
    )
    write_quality_evidence(tmp_path)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=(source_path, "tests/test_public_showcase.py"),
    )
    finding_kinds = {finding.kind for finding in report.findings}

    assert LooseCodeGapKind.SOURCE_WITHOUT_WRITTEN_RULE not in finding_kinds


def test_governance_alignment_surfaces_constitution_family_mismatch(
    tmp_path: Path,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    provider_doc = tmp_path / "docs" / "providers" / "instruction_codex_provider.md"
    provider_doc.write_text(
        "# Codex Provider\n\n## ELI10\n\n"
        "ELI10\nCodex is a provider adapter\nLIVE_ORDER_BLOCKED\n",
        encoding="utf-8",
    )

    report = audit_governance_alignment(tmp_path)

    assert report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH
        and finding.path == "docs/providers/instruction_codex_provider.md"
        for finding in report.findings
    )
    assert "LIVE_ORDER_BLOCKED" in report.blockers


def test_governance_alignment_surfaces_root_agent_contract_mismatch(
    tmp_path: Path,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    root_instructions = tmp_path / "AGENTS.md"
    root_instructions.write_text(
        root_instructions.read_text(encoding="utf-8").replace(
            "`docs/providers/instruction_codex_provider.md`",
            "`docs/providers/missing_codex_provider.md`",
        ),
        encoding="utf-8",
    )

    report = audit_governance_alignment(tmp_path)

    assert report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH
        and finding.path == "AGENTS.md"
        and "instruction_codex_provider.md" in finding.detail
        for finding in report.findings
    )
    assert "LIVE_ORDER_BLOCKED" in report.blockers


def test_governance_alignment_surfaces_missing_decision_anchor_fragment(
    tmp_path: Path,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)
    standard_path = (
        tmp_path / "docs" / "standards" / "standard_repository_validator_governance.md"
    )
    standard_path.write_text(
        standard_path.read_text(encoding="utf-8").replace(
            "Runtime is not source-of-truth.\n",
            "",
        ),
        encoding="utf-8",
    )

    report = audit_governance_alignment(tmp_path)

    assert report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH
        and finding.path == "docs/standards/standard_repository_validator_governance.md"
        and "Runtime is not source-of-truth." in finding.detail
        for finding in report.findings
    )
    assert "LIVE_ORDER_BLOCKED" in report.blockers


def test_governance_alignment_surfaces_loose_changed_source_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "ai4binance" / "strategy"
    source.mkdir(parents=True)
    (source / "loose_alpha.py").write_text("def alpha(): return 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_unrelated.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=(
            "src/ai4binance/strategy/loose_alpha.py",
            "tests/test_unrelated.py",
        ),
    )
    finding_kinds = {finding.kind for finding in report.findings}

    assert report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
    assert LooseCodeGapKind.SOURCE_WITHOUT_TEST_EVIDENCE in finding_kinds
    assert LooseCodeGapKind.SOURCE_WITHOUT_WRITTEN_RULE in finding_kinds
    assert "LIVE_ORDER_BLOCKED" in report.blockers


def test_governance_alignment_flags_unknown_changeset_when_scope_is_not_known(
    tmp_path: Path,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=(),
        change_scope_known=False,
    )

    assert report.status is GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is LooseCodeGapKind.UNKNOWN_CHANGESET
        and finding.path == "CHANGESET"
        for finding in report.findings
    )
    assert "UNKNOWN_CHANGESET:CHANGESET" in report.blockers


def test_governance_alignment_skips_loose_code_blob_reads_without_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_core_documents(tmp_path)
    write_quality_evidence(tmp_path)

    def _fail(_: Path) -> str:
        raise AssertionError("loose-code blob read should have been skipped")

    monkeypatch.setattr(constitution_sync_module, "_read_docs_blob", _fail)
    monkeypatch.setattr(constitution_sync_module, "_read_tests_blob", _fail)

    report = audit_governance_alignment(
        tmp_path,
        changed_paths=("docs/governance/note.md",),
    )

    assert report.status is GovernanceAlignmentStatus.PASS
    assert report.findings == ()


def test_governance_alignment_docs_do_not_reference_stale_knowledge_template_path() -> (
    None
):
    assert stale_knowledge_template_offenders(ROOT) == []


def test_quality_gate_evidence_rejects_incomplete_or_executable_claims() -> None:
    with pytest.raises(ValueError, match="pytest_pass_count"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=None,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256="a" * 64,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )
    with pytest.raises(ValueError, match="coverage_percent"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=None,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256="a" * 64,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )
    with pytest.raises(ValueError, match="governed markdown proof"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="",
            coverage_realism_proof_sha256="a" * 64,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )
    with pytest.raises(ValueError, match="markdown proof hash"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256="bad",
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256="a" * 64,
            execution_allowed=True,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )


def test_constitution_sync_validation_helpers_cover_fail_closed_edges(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="severity is invalid"):
        constitution_sync_module.LooseCodeFinding(
            LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH,
            "src/ai4binance/governance/example.py",
            "Example detail",
            severity="INVALID",
        )

    proof_path = (
        tmp_path / "runtime" / "artifacts" / "quality" / "gate" / "coverage_summary.md"
    )
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text("# Proof\n", encoding="utf-8")
    proof_hash = sha256(proof_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="TECHNICAL_QUALITY_PASS"):
        QualityGateEvidence(
            status="QUALITY_GATE_RED",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256=proof_hash,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )

    with pytest.raises(ValueError, match="quality gate command"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command=" ",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256=proof_hash,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )

    with pytest.raises(ValueError, match="quality gate coverage source"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source=" ",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256=proof_hash,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )

    with pytest.raises(ValueError, match="governed markdown proof"):
        QualityGateEvidence(
            status="TECHNICAL_QUALITY_PASS",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=90.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/other.md",
            coverage_realism_proof_sha256=proof_hash,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )

    with pytest.raises(ValueError, match="coverage_percent"):
        QualityGateEvidence(
            status="QUALITY_GATE_GREEN",
            command="quality",
            pytest_pass_count=1,
            coverage_percent=101.0,
            coverage_source="coverage.py json totals.percent_covered",
            coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
            coverage_realism_proof_sha256=proof_hash,
            execution_allowed=False,
            promotion_status="RESEARCH_ONLY",
            live_eligibility_status="LIVE_ORDER_BLOCKED",
        )

    report_path = (
        tmp_path / "runtime" / "artifacts" / "quality" / "gate" / "latest.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_payload = {
        "schema_version": 2,
        "status": "TECHNICAL_QUALITY_PASS",
        "legacy_status": "QUALITY_GATE_GREEN",
        "full_assurance_status": "FULL_ASSURANCE_GREEN",
        "verification_status": "FULL_VERIFIED",
        "canonical_quality_authority": True,
        "generated_at_utc": "2026-09-02T00:00:00+00:00",
        "command": "quality",
        "pytest_pass_count": 1,
        "coverage_percent": 90.0,
        "coverage_source": "coverage.py json totals.percent_covered",
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "coverage_realism_proof": {
            "markdown_path": "runtime/artifacts/quality/gate/coverage_summary.md",
            "markdown_sha256": proof_hash,
            "evidence_type": "GOVERNED_MARKDOWN_COVERAGE_REALISM_PROOF",
        },
        "workspace_attestation": (
            constitution_sync_module.build_quality_gate_workspace_attestation(
                tmp_path
            ).to_payload()
        ),
    }
    report_path.write_text(json.dumps(report_payload), encoding="utf-8-sig")
    quality_evidence = constitution_sync_module.load_current_quality_gate_evidence(
        tmp_path
    )
    assert quality_evidence is not None
    assert quality_evidence.artifact_sha256 is not None

    report_payload["coverage_realism_proof"] = "invalid"
    report_path.write_text(json.dumps(report_payload), encoding="utf-8-sig")
    assert constitution_sync_module._load_quality_gate(tmp_path) is None

    report_payload["coverage_realism_proof"] = {
        "markdown_path": "runtime/artifacts/quality/gate/coverage_summary.md",
        "markdown_sha256": proof_hash,
        "evidence_type": "GOVERNED_MARKDOWN_COVERAGE_REALISM_PROOF",
    }
    report_payload["schema_version"] = 1
    report_path.write_text(json.dumps(report_payload), encoding="utf-8-sig")
    assert constitution_sync_module.load_current_quality_gate_evidence(tmp_path) is None

    report_payload["schema_version"] = 2
    report_payload["workspace_attestation"] = {
        **constitution_sync_module.build_quality_gate_workspace_attestation(
            tmp_path
        ).to_payload(),
        "repository_tree_sha256": "0" * 64,
    }
    report_path.write_text(json.dumps(report_payload), encoding="utf-8-sig")
    assert constitution_sync_module._load_quality_gate(tmp_path) is None

    with pytest.raises(ValueError, match="repository root must be absolute"):
        constitution_sync_module.GovernanceAlignmentAuditReport(
            status=GovernanceAlignmentStatus.PASS,
            repository_root=Path("relative"),
            changed_paths=(),
            findings=(),
            quality_gate=None,
            blockers=("LIVE_ORDER_BLOCKED",),
        )

    valid_root = tmp_path.resolve()
    finding = constitution_sync_module.LooseCodeFinding(
        LooseCodeGapKind.CONSTITUTION_FAMILY_MISMATCH,
        "docs/governance/example.md",
        "Missing canonical fragment.",
    )
    quality_gate = QualityGateEvidence(
        status="TECHNICAL_QUALITY_PASS",
        command="quality",
        pytest_pass_count=1,
        coverage_percent=90.0,
        coverage_source="coverage.py json totals.percent_covered",
        coverage_realism_proof_path="runtime/artifacts/quality/gate/coverage_summary.md",
        coverage_realism_proof_sha256=proof_hash,
        execution_allowed=False,
        promotion_status="RESEARCH_ONLY",
        live_eligibility_status="LIVE_ORDER_BLOCKED",
    )

    with pytest.raises(ValueError, match="cannot contain findings"):
        constitution_sync_module.GovernanceAlignmentAuditReport(
            status=GovernanceAlignmentStatus.PASS,
            repository_root=valid_root,
            changed_paths=("src/ai4binance/governance/example.py",),
            findings=(finding,),
            quality_gate=quality_gate,
            blockers=("LIVE_ORDER_BLOCKED",),
        )

    with pytest.raises(ValueError, match="requires findings"):
        constitution_sync_module.GovernanceAlignmentAuditReport(
            status=GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS,
            repository_root=valid_root,
            changed_paths=("src/ai4binance/governance/example.py",),
            findings=(),
            quality_gate=quality_gate,
            blockers=("LIVE_ORDER_BLOCKED",),
        )

    with pytest.raises(ValueError, match="cannot authorize execution"):
        constitution_sync_module.GovernanceAlignmentAuditReport(
            status=GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS,
            repository_root=valid_root,
            changed_paths=("src/ai4binance/governance/example.py",),
            findings=(finding,),
            quality_gate=quality_gate,
            blockers=("LIVE_ORDER_BLOCKED",),
            execution_allowed=True,
        )
